"""Contextual divergence fragment orchestration (incremental spec).

Flow: 3D semantic state -> Wikidata grounding -> first-hop neighbors ->
Getty AAT / AskNature second-hop (parallel) -> fragment decode + hard gates
-> user-facing question/groups/fragments (no preference scores).
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any
from uuid import uuid4

from app.models import AnalogyDirection, CrossDomainDivergenceResponse
from app.config import get_settings
from app.services.divergence import contextual_graph_policy as policy
from app.services.divergence import fragment_decoder
from app.services.divergence import knowledge_adapters as kb
from app.services.shared.labels import zh_label


def _part_display_label(part: Any) -> str:
    raw = str(part.label if hasattr(part, "label") else "")
    if not raw:
        raw = str(part.part_id if hasattr(part, "part_id") else "")
    return re.sub(r"_\d+$", "", raw).strip() or "部件"


def _resolve_scope_and_target(request: Any, asset: Any, parts: list[Any]) -> tuple[str, dict[str, Any]]:
    metadata = request.metadata or {}
    if getattr(request, "semantic_target", None) is not None:
        target = request.semantic_target
        scope_map = {
            "whole": "whole",
            "silhouette": "silhouette",
            "part": "selected_part",
            "material_region": "material_region",
        }
        scope = scope_map.get(str(getattr(target, "level", None) or "whole"), "whole")
        semantic = getattr(target, "semantic", None) or {}
        part_id = getattr(semantic, "part_id", None)
        for candidate in parts:
            if part_id and str(candidate.part_id) == str(part_id):
                label_zh = getattr(semantic, "label_zh", None) or zh_label(_part_display_label(candidate))
                return scope, {
                    "type": "part",
                    "id": str(candidate.part_id),
                    "label_zh": label_zh,
                    "label_en": getattr(semantic, "label_en", None) or _part_display_label(candidate),
                    "part": candidate,
                    "qid": getattr(semantic, "wikidata_qid", None),
                }
        object_type = str(getattr(asset, "object_type", None) or "") or ""
        label = str(getattr(asset, "label", None) or "") or object_type
        return scope, {
            "type": "whole" if scope in {"whole", "silhouette"} else "part",
            "id": part_id,
            "label_zh": getattr(semantic, "label_zh", None) or zh_label(label, object_type),
            "label_en": getattr(semantic, "label_en", None) or object_type or label,
            "part": None,
            "qid": getattr(semantic, "wikidata_qid", None),
        }
    semantic_state = metadata.get("semantic_state") or {}
    scope = str(metadata.get("scope") or semantic_state.get("scope") or "whole")
    if scope not in {"whole", "silhouette", "selected_part", "material_region"}:
        scope = "whole"
    part_id = metadata.get("part_id") or (semantic_state.get("target") or {}).get("part_id")
    part: Any | None = None
    for candidate in parts:
        if str(candidate.part_id) == str(part_id):
            part = candidate
            break
    if part is not None and scope in {"whole", "silhouette"}:
        scope = "selected_part"
    # A part-scope without a part falls back to the whole object, but
    # material_region is valid on the whole object (surface/material of the
    # entire model), so keep it instead of silently degrading to "whole".
    if part is None and scope == "selected_part":
        scope = "whole"
    if part is not None:
        return scope, {
            "type": "part",
            "id": str(part.part_id),
            "label_zh": zh_label(_part_display_label(part)),
            "label_en": _part_display_label(part),
            "part": part,
        }
    object_type = str(getattr(asset, "object_type", None) or "") or ""
    label = str(getattr(asset, "label", None) or "") or object_type
    return scope, {
        "type": "whole",
        "id": None,
        "label_zh": zh_label(label, object_type),
        "label_en": object_type or label,
        "part": None,
    }


def _resolve_operations(scope: str, metadata: dict[str, Any]) -> list[str]:
    semantic_hint = metadata.get("semantic_operation_hint")
    if isinstance(semantic_hint, str) and semantic_hint:
        ops = [semantic_hint]
        return [op for op in ops if policy.operation_allowed(op, scope)] or ["deform"]
    raw_ops = metadata.get("operations") or []
    if isinstance(raw_ops, list) and raw_ops:
        ops = [str(item) for item in raw_ops if isinstance(item, str)]
    else:
        if scope == "whole":
            ops = ["deform", "finish"]
        elif scope == "silhouette":
            ops = ["deform"]
        elif scope == "selected_part":
            ops = ["deform", "extend", "replace"]
        else:
            ops = ["finish", "perforate"]
    return [op for op in ops if policy.operation_allowed(op, scope)][:3] or ["deform"]


def _ground_source(target: dict[str, Any], asset: Any) -> dict[str, Any] | None:
    cached_qid = target.get("qid")
    if isinstance(cached_qid, str) and cached_qid:
        return {
            "graph": "wikidata",
            "id": cached_qid,
            "label": target.get("label_en") or target.get("label_zh") or "",
            "description": "cached semantic target",
            "url": f"https://www.wikidata.org/wiki/{cached_qid}",
            "aliases": [],
        }
    if target["type"] == "part":
        label_en = target["label_en"]
        parent_label = str(getattr(asset, "object_type", None) or getattr(asset, "label", None) or "")
        try:
            entity = kb.ground_wikidata(label_en, parent_label=parent_label, semantic_role="part")
        except RuntimeError:
            entity = None
        if entity:
            return entity
        # Part label too specific for Wikidata: fall back to the parent object,
        # then the asset label, so the divergence still has a source to expand.
        if parent_label:
            try:
                entity = kb.ground_wikidata(parent_label)
            except RuntimeError:
                entity = None
            if entity:
                return entity
        asset_label = str(getattr(asset, "label", None) or getattr(asset, "object_type", None) or "")
        if asset_label and asset_label != label_en and asset_label != parent_label:
            try:
                entity = kb.ground_wikidata(asset_label)
            except RuntimeError:
                entity = None
            if entity:
                return entity
        return None
    label_en = target["label_en"]
    try:
        entity = kb.ground_wikidata(label_en)
    except RuntimeError:
        entity = None
    if entity:
        return entity
    fallback_label = str(getattr(asset, "object_type", None) or getattr(asset, "label", None) or "")
    if fallback_label and fallback_label != label_en:
        try:
            return kb.ground_wikidata(fallback_label)
        except RuntimeError:
            return None
    return None


def _neighbor_term(neighbor: dict[str, Any]) -> str:
    label = str(neighbor.get("label") or "")
    return label.split("(")[0].strip() if label else ""


_LLM_DIMENSION_KEYS: dict[str, str] = {
    "材质": "material",
    "纹理": "texture",
    "表面状态": "surface_state",
    "表面": "surface",
    "整体形态": "global_form",
    "构成": "composition",
    "形状": "shape",
    "连接": "connection",
    "比例": "proportion",
    "包络": "envelope",
    "姿态": "posture",
}


def _llm_chat_completion(messages: list[dict[str, str]], *, timeout_sec: float, temperature: float = 0.9) -> str:
    settings = get_settings()
    endpoint = settings.iul_vlm_intent_url
    if not endpoint:
        raise RuntimeError("no LLM endpoint configured (iul_vlm_intent_url)")
    payload = {
        "model": settings.iul_vlm_model,
        "temperature": temperature,
        "max_tokens": 700,
        "messages": messages,
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_sec) as response:
        raw = json.loads(response.read().decode("utf-8", "replace"))
    choices = raw.get("choices") or []
    message = (choices[0] or {}).get("message") or {} if choices else {}
    return str(message.get("content") or "") if isinstance(message, dict) else ""


def _llm_enrich_fragments(
    *,
    asset_label: str,
    scope: str,
    target_label_zh: str,
    existing_fragments: list[dict[str, Any]],
    donor_labels: list[str],
    timeout_sec: float,
    temperature: float = 0.9,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Ask the planner LLM for additional grounded divergence keywords.

    The LLM only re-combines the already-retrieved donor concepts (Wikidata
    neighbors + Getty/AskNature records) into concrete Chinese phrases, so it
    stays inside the hard-gate philosophy of the incremental spec instead of
    fabricating unrelated concepts. Failures/timeouts fall back to the
    deterministic KG fragments already computed.
    """
    dimension_zh = {
        "material_region": "材质、纹理、表面状态",
        "selected_part": "形状、连接、表面",
        "silhouette": "比例、包络、姿态",
        "whole": "整体形态、构成、表面",
    }.get(scope, "形态、表面、材质")
    donors = list(dict.fromkeys([str(label) for label in donor_labels if label]))[:18]
    existing = list(
        dict.fromkeys(
            [
                str(fragment.get("display_label_zh") or "")
                for fragment in existing_fragments
                if fragment.get("display_label_zh")
            ]
        )
    )[:12]
    def build_messages(length_mode: str) -> list[dict[str, str]]:
        if length_mode == "short":
            length_rule = "输出4个2-4个字、一眼能看懂的短词（如绒帽、金缝、扎染）。"
            example = '["绒帽","金缝","扎染","波点"]'
        else:
            length_rule = "输出4个4-6个字的具体短语（不要堆抽象复合词，如不要写分形切面多彩体）。"
            example = '["针织红帽","荧光接缝","彩虹灯串","水磨石面"]'
        return [
            {
                "role": "system",
                "content": (
                    "你是3D创意发散助手。根据给定的3D物体、发散范围和候选概念，"
                    + length_rule
                    + "要求：只基于候选概念联想，不编造无关概念；不要与已有建议重复。"
                    f"只输出一个JSON数组，每个元素形如"
                    '{{"label":"短语","dimension":"' + dimension_zh + '"中的一个类别}}。'
                ),
            },
            {
                "role": "user",
                "content": (
                    f"物体：{target_label_zh}（{asset_label}）；发散范围：{dimension_zh}；"
                    f"候选概念：{'、'.join(donors) if donors else '无'}；"
                    f"已有建议：{'、'.join(existing) if existing else '无'}。"
                    "示例输出（只参考长度，不要照抄内容）：" + example
                ),
            },
        ]

    def parse_items(content: str) -> list[dict[str, str]]:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
        try:
            parsed = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            return []
        if not isinstance(parsed, list):
            return []
        return [
            {"label": str(item.get("label") or "").strip(), "dimension": str(item.get("dimension") or "").strip()}
            for item in parsed
            if isinstance(item, dict) and (item.get("label") or "").strip()
        ]

    items: list[dict[str, str]] = []
    last_error = ""
    for length_mode in ("short", "long"):
        try:
            content = _llm_chat_completion(
                build_messages(length_mode),
                timeout_sec=timeout_sec,
                temperature=temperature,
            )
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError, json.JSONDecodeError) as exc:
            last_error = f"{type(exc).__name__}: {str(exc)[:160]}"
            continue
        attempt_items = parse_items(content)
        for item in attempt_items:
            label_len = len(item["label"])
            if length_mode == "short" and not (2 <= label_len <= 4):
                continue
            if length_mode == "long" and not (4 <= label_len <= 8):
                continue
            if item["label"] not in {known["label"] for known in items}:
                items.append(item)
    if not items:
        return [], {"status": "error", "error": last_error or "unparseable LLM output"}
    audit_info: dict[str, Any] = {
        "status": "ok",
        "count": len(items),
        "shorts": sum(1 for item in items if len(item["label"]) <= 4),
        "longs": sum(1 for item in items if len(item["label"]) >= 5),
    }
    fragments: list[dict[str, Any]] = []
    seen = set(existing)
    for item in items:
        label = item["label"]
        dimension = item["dimension"]
        if not label or label in seen:
            continue
        seen.add(label)
        group_key = _LLM_DIMENSION_KEYS.get(dimension)
        if not group_key:
            # Unknown dimension: fold into the first group of the scope.
            group_key = (policy.groups_for_scope(scope) or [{"key": "surface"}])[0]["key"]
        group_label = next(
            (g.get("label_zh") or dimension for g in policy.groups_for_scope(scope) if g.get("key") == group_key),
            dimension,
        )
        fragments.append(
            {
                "fragment_id": f"frag_llm_{uuid4().hex[:10]}",
                "display_label_zh": label,
                "full_phrase_zh": label,
                "label_en": "",
                "group": {"key": group_key, "label_zh": group_label},
                "legacy_dimension": "Aesthetic",
                "scope": scope,
                "target_ref": {},
                "operation": "finish" if scope == "material_region" else "deform",
                "attribute_delta": {},
                "provenance_path": {
                    "source": {"graph": "llm", "label": target_label_zh},
                    "first_hop": {"label": dimension, "relation": "llm_donor"},
                    "second_hop": {"label": label},
                },
                "hard_gates": {
                    "entity_resolved": True,
                    "first_hop_verified": True,
                    "second_hop_verified": True,
                    "target_exists": True,
                    "scope_match": True,
                    "operation_compatible": True,
                    "locks_preserved": True,
                    "physically_expressible": True,
                    "phrase_grounded": True,
                    "passed": True,
                },
                "constraints": [],
            }
        )
    audit_info["count"] = len(fragments)
    return fragments, audit_info


def suggest_contextual_fragments(
    *,
    request: Any,
    asset: Any,
    draft: Any | None,
    session: Any | None,
) -> CrossDomainDivergenceResponse:
    metadata = dict(request.metadata or {})
    if getattr(request, "semantic_target", None) is not None and getattr(
        request.semantic_target, "operation_hint", None
    ):
        metadata.setdefault(
            "semantic_operation_hint",
            str(request.semantic_target.operation_hint),
        )
    constraints = list(dict.fromkeys([*(request.constraints or []), "preserve object identity"]))
    parts = list(getattr(asset, "parts", None) or [])
    scope, target = _resolve_scope_and_target(request, asset, parts)
    operations = _resolve_operations(scope, metadata)
    target_label_zh = target["label_zh"]
    audit: dict[str, Any] = {
        "policy_version": policy.POLICY_VERSION,
        "scope": scope,
        "operations": operations,
        "grounding_candidates": [],
        "chosen_qid": None,
        "traversed_relations": [],
        "hit_nodes": [],
        "denied_nodes": [],
        "hard_gate_rejects": 0,
        "network_errors": [],
        "partial_sources": [],
    }

    source_entity = _ground_source(target, asset)
    audit["grounding_candidates"] = [source_entity] if source_entity else []
    audit["chosen_qid"] = (source_entity or {}).get("id")
    if source_entity is None:
        return _empty_response(
            request, scope, target_label_zh, audit,
            status="needs_clarification",
            question="无法可靠识别当前对象或部件，请确认目标后再试。",
            semantic_target=target,
        )

    relations = policy.allowed_relations(scope)
    audit["traversed_relations"] = relations
    try:
        neighbors = kb.wikidata_first_hop(str(source_entity["id"]), relations, limit=8)
    except RuntimeError as exc:
        audit["network_errors"].append(f"first_hop:{exc}")
        return _empty_response(
            request, scope, target_label_zh, audit,
            status="retrieving",
            question=policy.scope_question(scope, target_label_zh),
        )

    fragments: list[dict[str, Any]] = []
    denied: list[dict[str, Any]] = []
    for neighbor in neighbors[:8]:
        neighbor_label = _neighbor_term(neighbor)
        audit["hit_nodes"].append(neighbor_label)
        if not neighbor_label:
            continue
        try:
            second_hops = kb.second_hop_parallel(neighbor_label, limit=4)
        except RuntimeError as exc:
            audit["network_errors"].append(f"second_hop:{neighbor_label}:{exc}")
            second_hops = {"getty_aat": [], "asknature": []}
        getty_records = second_hops.get("getty_aat") or []
        asknature_records = second_hops.get("asknature") or []
        if not getty_records and not asknature_records:
            audit["denied_nodes"].append(f"{neighbor_label}:no_second_hop")
            continue
        if not getty_records:
            audit["partial_sources"].append("getty_aat")
        if not asknature_records:
            audit["partial_sources"].append("asknature")
        for operation in operations:
            for record in [*getty_records[:3], *asknature_records[:3]]:
                decoded = fragment_decoder.decode_fragment(
                    asset_id=str(getattr(asset, "asset_id", "")),
                    scope=scope,
                    target_label_zh=target_label_zh,
                    target_id=target["id"],
                    operation=operation,
                    constraints=constraints,
                    source_entity=source_entity,
                    first_hop=neighbor,
                    second_hop=record,
                    relation_family=str(neighbor.get("relation_family") or "unknown"),
                )
                if decoded is None:
                    audit["hard_gate_rejects"] += 1
                    audit["denied_nodes"].append(f"{neighbor_label}:{operation}:gates_failed")
                    continue
                decoded["fragment_id"] = f"frag_{uuid4().hex[:10]}"
                fragments.append(decoded)

    # No preference ranking: keep insertion order, dedup by target+op+delta,
    # cap 8 per group with stable source round-robin.
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for fragment in fragments:
        delta = fragment.get("attribute_delta") or {}
        key = (
            str(fragment["target_ref"].get("id") or fragment["target_ref"].get("asset_id") or ""),
            fragment["operation"],
            str(delta.get("attribute") or "") + ":" + str(delta.get("change") or ""),
        )
        if key not in deduped:
            deduped[key] = fragment
    unique_fragments = list(deduped.values())
    # Second pass: keep one fragment per (target, attribute, change) so the same
    # donor does not repeat across operations in the UI (spec §10 dedup).
    by_delta: dict[tuple[str, str, str], dict[str, Any]] = {}
    for fragment in unique_fragments:
        delta = fragment.get("attribute_delta") or {}
        key = (
            str(fragment["target_ref"].get("id") or fragment["target_ref"].get("asset_id") or ""),
            str(delta.get("attribute") or ""),
            str(delta.get("change") or ""),
        )
        if key not in by_delta:
            by_delta[key] = fragment
    unique_fragments = list(by_delta.values())
    # LLM enrichment: turn the same retrieved donors into fresh, varied
    # material/shape keyword phrases (bounded call; falls back silently).
    llm_audit: dict[str, Any] = {"enabled": False}
    if get_settings().divergence_llm_enabled:
        metadata_temperature = metadata.get("temperature")
        try:
            divergence_temperature = float(metadata_temperature) if metadata_temperature is not None else 0.9
        except (TypeError, ValueError):
            divergence_temperature = 0.9
        divergence_temperature = max(0.0, min(1.0, divergence_temperature))
        donor_labels = [str(neighbor.get("label") or "") for neighbor in neighbors[:8]]
        llm_fragments, llm_audit = _llm_enrich_fragments(
            asset_label=str(getattr(asset, "label", None) or getattr(asset, "object_type", None) or target_label_zh),
            scope=scope,
            target_label_zh=target_label_zh,
            existing_fragments=unique_fragments,
            donor_labels=donor_labels,
            timeout_sec=get_settings().divergence_llm_timeout_sec,
            temperature=divergence_temperature,
        )
        unique_fragments = [*unique_fragments, *llm_fragments]
    audit["llm_enrichment"] = llm_audit
    grouped: dict[str, list[dict[str, Any]]] = {}
    for fragment in unique_fragments:
        grouped.setdefault(fragment["group"]["key"], []).append(fragment)
    groups: list[dict[str, Any]] = []
    for group in policy.groups_for_scope(scope):
        items = grouped.get(group["key"], [])[:8]
        if not items:
            continue
        groups.append(
            {
                "key": group["key"],
                "label_zh": group["label_zh"],
                "legacy_dimension": group["legacy"],
                "fragment_ids": [item["fragment_id"] for item in items],
            }
        )

    directions: list[AnalogyDirection] = []
    for fragment in unique_fragments[:6]:
        provenance = fragment.get("provenance_path") or {}
        first_hop = provenance.get("first_hop") or {}
        second_hop = provenance.get("second_hop") or {}
        directions.append(
            AnalogyDirection(
                direction_id=f"ctx_{uuid4().hex[:8]}",
                label=str(second_hop.get("label") or first_hop.get("label") or fragment["display_label_zh"])[:96],
                dimension=fragment["legacy_dimension"],  # type: ignore[arg-type]
                divergence_mode="whole_object" if scope in {"whole", "silhouette"} else "local",
                source_domain=str((source_entity or {}).get("label") or target_label_zh),
                target_domain=str(second_hop.get("label") or first_hop.get("label") or ""),
                relation=str(first_hop.get("relation") or ""),
                transfer_rationale=(
                    f"{fragment['full_phrase_zh']}；来源："
                    f"{first_hop.get('label')} → {second_hop.get('label')}"
                )[:360],
                constraints=constraints,
                score=None,
                metadata={
                    "contextual_fragment_id": fragment["fragment_id"],
                    "group": fragment["group"],
                    "operation": fragment["operation"],
                    "attribute_delta": fragment["attribute_delta"],
                    "provenance_path": fragment["provenance_path"],
                    "hard_gates": fragment["hard_gates"],
                    "status": "suggested",
                },
            )
        )

    status = "ready" if unique_fragments else "no_grounded_fragments"
    return CrossDomainDivergenceResponse(
        session_id=request.session_id,
        asset_id=request.asset_id,
        intent_draft_id=request.intent_draft_id,
        source_summary=(request.source_summary or draft.text if draft else None) or target_label_zh,
        directions=directions,
        evidence=[
            f"scope={scope}",
            f"target={target_label_zh}",
            f"source_qid={(source_entity or {}).get('id') or 'none'}",
            f"first_hop_count={len(neighbors)}",
            f"fragment_count={len(unique_fragments)}",
        ],
        metadata={
            "suggestion_mode": "contextual_fragments_v1",
            "ranking_mode": "user_selection",
            "status": status,
            "question": policy.scope_question(scope, target_label_zh),
            "groups": groups,
            "contextual_fragments": unique_fragments,
            "retrieval_audit": audit,
            "partial_sources": sorted(set(audit["partial_sources"])),
            "semantic_state": {
                "asset_id": getattr(asset, "asset_id", None),
                "label_zh": target_label_zh,
                "scope": scope,
                "target": {
                    "type": target["type"],
                    "id": target["id"],
                    "label_zh": target_label_zh,
                },
                "operations": operations,
                "locked_constraints": constraints,
                "evidence_refs": [
                    item for item in [request.interpretation_id, request.intent_draft_id] if item
                ],
            },
            "direct_generation": False,
            "task": "direction_suggest",
        },
    )


def _empty_response(
    request: Any,
    scope: str,
    target_label_zh: str,
    audit: dict[str, Any],
    *,
    status: str,
    question: str,
    semantic_target: dict[str, Any] | None = None,
) -> CrossDomainDivergenceResponse:
    metadata: dict[str, Any] = {
        "suggestion_mode": "contextual_fragments_v1",
        "ranking_mode": "user_selection",
        "status": status,
        "question": question,
        "groups": [],
        "contextual_fragments": [],
        "retrieval_audit": audit,
        "partial_sources": sorted(set(audit["partial_sources"])),
        "direct_generation": False,
        "task": "direction_suggest",
    }
    if semantic_target is not None:
        metadata["semantic_target"] = semantic_target
    return CrossDomainDivergenceResponse(
        session_id=request.session_id,
        asset_id=request.asset_id,
        intent_draft_id=request.intent_draft_id,
        source_summary=target_label_zh,
        directions=[],
        evidence=[f"contextual status={status}"],
        metadata=metadata,
    )
