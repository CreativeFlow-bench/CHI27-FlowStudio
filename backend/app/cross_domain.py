"""Cross-domain direction response builders (refactor plan P2)."""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import uuid4

from app.models import (
    AnalogyDirection,
    CrossDomainDivergenceRequest,
    CrossDomainDivergenceResponse,
    IntentDraft,
    SessionRecord,
)
from app.services.intent.interaction_features import unique_ref_count as _request_image_ref_count

_STORE: Any = None
_PLANNER_CONTEXT: Any = None
_INTERACTION_SERVICE: Any = None
_SETTINGS: Any = None


def configure_cross_domain(
    *, studio_store: Any, planner_control_context: Any, interaction_service: Any, settings: Any
) -> None:
    global _STORE, _PLANNER_CONTEXT, _INTERACTION_SERVICE, _SETTINGS
    _STORE = studio_store
    _PLANNER_CONTEXT = planner_control_context
    _INTERACTION_SERVICE = interaction_service
    _SETTINGS = settings


def _build_cross_domain_response(
    request: CrossDomainDivergenceRequest,
    asset: object,
    draft: IntentDraft | None,
    session: SessionRecord,
) -> CrossDomainDivergenceResponse:
    object_type = str(getattr(asset, "object_type", None) or "object")
    label = str(getattr(asset, "label", None) or object_type)
    draft_text = draft.text if draft and draft.text else None
    control_context = _PLANNER_CONTEXT(session)
    reference_images = request.metadata.get("reference_images")
    if not isinstance(reference_images, list):
        reference_images = []
    image_refs = request.metadata.get("image_refs")
    if not isinstance(image_refs, list):
        image_refs = []
    image_ref_count = _request_image_ref_count(image_refs, reference_images)
    confirmed_intent = control_context.get("confirmed_intent")
    rejected_intent = control_context.get("rejected_intent")
    confirmed_intent_text = (
        str(confirmed_intent.get("primary_intent"))
        if isinstance(confirmed_intent, dict)
        else ""
    )
    rejected_intent_text = (
        str(rejected_intent.get("primary_intent"))
        if isinstance(rejected_intent, dict)
        else ""
    )
    source_summary = (
        request.source_summary
        or draft_text
        or f"{label}: a {object_type} with the current confirmed edits and constraints"
    )
    constraints = list(
        dict.fromkeys(
            [
                *request.constraints,
                "preserve object identity",
                *(
                    [f"honor confirmed planner intent: {confirmed_intent_text}"]
                    if confirmed_intent_text
                    else []
                ),
                *(
                    [f"do not act on rejected planner intent: {rejected_intent_text}"]
                    if rejected_intent_text
                    else []
                ),
            ]
        )
    )
    ir_matches = _cross_domain_ir_matches(
        request=request,
        object_type=object_type,
        source_summary=source_summary,
        draft=draft,
        control_context=control_context,
    )
    ir_reused = any(isinstance(match, dict) and match.get("ir_reuse") for match in ir_matches)
    ir_recommended_axes = _recommended_axes_from_ir_matches(ir_matches)
    selected_dimensions = request.dimensions or ir_recommended_axes or ["Aesthetic", "Functional", "Structural"]
    qwen_response = _qwen_cross_domain_response(
        request=request,
        asset_label=label,
        object_type=object_type,
        source_summary=source_summary,
        constraints=constraints,
        selected_dimensions=selected_dimensions,
        draft=draft,
        ir_matches=ir_matches,
        control_context=control_context,
    )
    if qwen_response is not None:
        qwen_response.metadata = {
            **qwen_response.metadata,
            "ir_reused_from_interpretation": ir_reused,
            "task": "direction_suggest",
            "interpretation_id": request.interpretation_id
            or request.metadata.get("interpretation_id"),
        }
        return qwen_response
    templates = [
        (
            "Aesthetic",
            "fashion accessory",
            "transfer softness, cuteness, color rhythm, and visual character",
            "Use fashion styling as an analogy source while keeping the base object's recognizability.",
        ),
        (
            "Structural",
            "architecture",
            "transfer layered support, openings, modules, and boundary logic",
            "Use architectural composition to suggest bigger form moves without overwriting protected regions.",
        ),
        (
            "Functional",
            "tool ergonomics",
            "transfer grasp, affordance, visibility, and action cues",
            "Use tool-use relations to turn ambiguous added shapes into purposeful parts.",
        ),
        (
            "Aesthetic",
            "toy design",
            "transfer friendliness, exaggeration, and simplified readable proportions",
            "Use toy-language proportions to make the object more approachable and emotionally legible.",
        ),
        (
            "Structural",
            "plant growth",
            "transfer branching, swelling, tapering, and organic continuity",
            "Use growth patterns to guide extensions while preserving attachment continuity.",
        ),
        (
            "Functional",
            "wearable product",
            "transfer comfort, wrap, fastening, and material-function coupling",
            "Use wearable constraints to reason about additions that touch or surround the object.",
        ),
    ]
    directions: list[AnalogyDirection] = []
    for index, (dimension, target_domain, relation, rationale) in enumerate(templates, start=1):
        if dimension not in selected_dimensions:
            continue
        direction = AnalogyDirection(
            direction_id=f"xdom_{uuid4().hex[:8]}",
            label=f"{dimension}: {object_type} as {target_domain}",
            dimension=dimension,  # type: ignore[arg-type]
            source_domain=f"current {object_type}",
            target_domain=target_domain,
            relation=relation,
            transfer_rationale=rationale,
            constraints=constraints,
            score=max(0.56, 0.86 - index * 0.035),
            metadata={
                "asset_label": label,
                "requested_dimensions": selected_dimensions,
                "intent_draft_id": request.intent_draft_id,
                "behavior_count": len(draft.behavior_atoms) if draft else 0,
                "image_ref_count": image_ref_count,
                "reference_images": reference_images[:6],
                "planner_control_gate": control_context,
                "uses_design_state_ir": bool(ir_matches),
                "ir_recommended_axes": ir_recommended_axes,
                "analogy_expansion_mode": "prompt_chip_composition",
                "retrieved_ir_cases": [match.get("case_id") for match in ir_matches[:3]],
                "prompt_tokens": _analogy_prompt_tokens(
                    dimension=dimension,
                    target_domain=target_domain,
                    relation=relation,
                    object_type=object_type,
                ),
            },
        )
        directions.append(direction)
        if len(directions) >= request.candidate_count:
            break
    return CrossDomainDivergenceResponse(
        session_id=request.session_id,
        asset_id=request.asset_id,
        intent_draft_id=request.intent_draft_id,
        source_summary=source_summary,
        directions=directions,
        evidence=[
            f"active_asset={label}",
            f"object_type={object_type}",
            f"intent_draft={request.intent_draft_id or 'none'}",
            f"planner_gate={control_context.get('status')}",
            f"image_refs={image_ref_count}",
            f"dimensions={','.join(selected_dimensions)}",
            f"design_state_ir={','.join(str(match.get('case_id')) for match in ir_matches[:3]) or 'none'}",
        ],
        metadata={
            "planner_mode": "whole_object_cross_domain_divergence",
            "direct_generation": False,
            "planner_source": "rule_fallback",
            "prompt_token_mode": "human_selectable_chips",
            "analogy_expansion_mode": "prompt_chip_composition",
            "planner_control_gate": control_context,
            "image_refs": image_refs,
            "reference_images": reference_images,
            "uses_design_state_ir": bool(ir_matches),
            "ir_reused_from_interpretation": ir_reused,
            "task": "direction_suggest",
            "interpretation_id": request.interpretation_id
            or request.metadata.get("interpretation_id"),
            "ir_recommended_axes": ir_recommended_axes,
            "retrieved_design_state_ir": ir_matches[:4],
            "retrieved_ir_cases": ir_matches[:4],
            "scope": request.metadata.get("scope"),
            "context_snapshot_id": request.metadata.get("context_snapshot_id"),
            "minimum_semantic_distance": request.metadata.get("minimum_semantic_distance"),
        },
    )


def _qwen_cross_domain_response(
    *,
    request: CrossDomainDivergenceRequest,
    asset_label: str,
    object_type: str,
    source_summary: str,
    constraints: list[str],
    selected_dimensions: list[str],
    draft: IntentDraft | None,
    ir_matches: list[dict[str, object]],
    control_context: dict[str, object],
) -> CrossDomainDivergenceResponse | None:
    endpoint = _SETTINGS.iul_vlm_intent_url
    if not endpoint:
        return None
    request_image_refs = (
        request.metadata.get("image_refs")
        if isinstance(request.metadata.get("image_refs"), list)
        else []
    )
    request_reference_images = (
        request.metadata.get("reference_images")
        if isinstance(request.metadata.get("reference_images"), list)
        else []
    )
    request_image_ref_count = _request_image_ref_count(
        request_image_refs,
        request_reference_images,
    )
    ir_recommended_axes = _recommended_axes_from_ir_matches(ir_matches)
    behavior_atoms = [
        {
            "tool": atom.tool,
            "target": atom.target,
            "evidence": atom.evidence,
            "order": atom.order,
        }
        for atom in (draft.behavior_atoms if draft else [])
    ][:12]
    prompt = {
        "task": "direction_suggest",
        "task_description": (
            "Generate cross-domain analogy directions for an interaction-aware 3D creative tool."
        ),
        "object_type": object_type,
        "asset_label": asset_label,
        "source_summary": source_summary,
        "confirmed_constraints": constraints,
        "planner_control_gate": control_context,
        "reference_images": request_reference_images,
        "image_refs": request_image_refs,
        "requested_dimensions": selected_dimensions,
        "ir_recommended_axes": ir_recommended_axes,
        "intent_draft": {
            "draft_id": draft.draft_id if draft else None,
            "title": draft.title if draft else None,
            "text": draft.text if draft else None,
            "behavior_atoms": behavior_atoms,
        },
        "retrieved_design_state_ir": ir_matches,
        "requirements": [
            "Return directions for the whole object, not only one part.",
            "Keep object identity and confirmed constraints.",
            "If planner_control_gate.status is confirmed, use confirmed_intent as the stable user-approved context.",
            "If planner_control_gate.status is rejected, do not act on rejected_intent; offer broader or clarification-oriented prompt tokens instead.",
            "This is prompt expansion, not the original CreativeFlow structured-transfer or KG generation pipeline.",
            "Each direction must be specific, explainable, and suitable for later human prompt composition.",
            "For each direction, include 3-6 short prompt_tokens that a human can click and combine into a final image prompt.",
            "Prompt tokens should be concrete words or short phrases, not full sentences.",
            "Do not imply that selecting a direction directly generates an image or mesh; generation happens only after the human confirms the composed prompt.",
            "Do not include prose outside JSON.",
        ],
        "response_schema": {
            "directions": [
                {
                    "label": "short readable label",
                    "dimension": "Aesthetic | Functional | Structural",
                    "source_domain": f"current {object_type}",
                    "target_domain": "cross-domain source",
                    "relation": "what relation transfers",
                    "transfer_rationale": "why the analogy helps this intent",
                    "prompt_tokens": [
                        {
                            "label": "short selectable word or phrase",
                            "dimension": "Aesthetic | Functional | Structural",
                            "role": "style | structure | material | behavior | mood"
                        }
                    ],
                    "constraints": ["constraint strings"],
                    "score": 0.0,
                }
            ],
            "evidence": ["short evidence strings"],
        },
    }
    payload = {
        "model": _SETTINGS.iul_vlm_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are the hidden Planner for FlowStudio. Return compact JSON only. "
                    "Do not call tools and do not generate final images or meshes. "
                    "The first character of your response must be { and the last character must be }."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(prompt, ensure_ascii=False),
            },
        ],
        "temperature": 0.2,
        "max_tokens": 900,
        "response_format": {"type": "json_object"},
    }
    try:
        http_request = UrlRequest(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(http_request, timeout=max(_SETTINGS.iul_vlm_timeout_sec, 30)) as response:
            raw = json.loads(response.read().decode("utf-8"))
        content = _chat_completion_content(raw)
        parsed = _extract_json_payload(content)
        raw_directions = parsed.get("directions")
        if not isinstance(raw_directions, list):
            return None
        directions: list[AnalogyDirection] = []
        for index, item in enumerate(raw_directions[: request.candidate_count], start=1):
            if not isinstance(item, dict):
                continue
            fallback_dimension = selected_dimensions[(index - 1) % len(selected_dimensions)]
            direction_dimension = _safe_direction_dimension(item.get("dimension"), fallback=fallback_dimension)
            try:
                direction = AnalogyDirection(
                    direction_id=f"xdom_qwen_{uuid4().hex[:8]}",
                    label=str(item.get("label") or f"Cross-domain direction {index}")[:96],
                    dimension=direction_dimension,
                    divergence_mode="cross_domain",
                    source_domain=str(item.get("source_domain") or f"current {object_type}")[:80],
                    target_domain=str(item.get("target_domain") or "cross-domain source")[:80],
                    relation=str(item.get("relation") or "transfer a relevant relation")[:240],
                    transfer_rationale=str(
                        item.get("transfer_rationale") or item.get("rationale") or ""
                    )[:360],
                    constraints=[
                        str(value)[:120]
                        for value in dict.fromkeys(
                            [
                                *(
                                    item.get("constraints")
                                    if isinstance(item.get("constraints"), list)
                                    else []
                                ),
                                *constraints,
                            ]
                        )
                    ][:8],
                    score=max(0.0, min(1.0, float(item.get("score", 0.74)))),
                    metadata={
                        "planner_source": "qwen3-planner",
                        "planner_model": _SETTINGS.iul_vlm_model,
                        "intent_draft_id": request.intent_draft_id,
                        "behavior_count": len(behavior_atoms),
                        "image_ref_count": request_image_ref_count,
                        "planner_control_gate": control_context,
                        "uses_design_state_ir": True,
                        "ir_recommended_axes": ir_recommended_axes,
                        "analogy_expansion_mode": "prompt_chip_composition",
                        "prompt_tokens": _coerce_prompt_tokens(
                            item.get("prompt_tokens"),
                            fallback_dimension=direction_dimension,
                            target_domain=str(item.get("target_domain") or "cross-domain source"),
                            relation=str(item.get("relation") or "transfer a relevant relation"),
                            object_type=object_type,
                        ),
                    },
                )
            except (TypeError, ValueError):
                continue
            directions.append(direction)
        if not directions:
            return None
        evidence = parsed.get("evidence")
        if not isinstance(evidence, list):
            evidence = [
                f"active_asset={asset_label}",
                f"object_type={object_type}",
                "planner=qwen3-planner",
            ]
        evidence = [
            *[str(value)[:160] for value in evidence[:8]],
            f"planner_gate={control_context.get('status')}",
        ]
        return CrossDomainDivergenceResponse(
            session_id=request.session_id,
            asset_id=request.asset_id,
            intent_draft_id=request.intent_draft_id,
            source_summary=source_summary,
            directions=directions,
            evidence=list(dict.fromkeys(evidence))[:9],
            metadata={
                "planner_mode": "whole_object_cross_domain_divergence",
                "direct_generation": False,
                "planner_source": "qwen3-planner",
                "planner_model": _SETTINGS.iul_vlm_model,
                "prompt_token_mode": "human_selectable_chips",
                "analogy_expansion_mode": "prompt_chip_composition",
                "planner_control_gate": control_context,
                "image_refs": request_image_refs,
                "reference_images": request_reference_images,
                "fallback_used": False,
                "uses_design_state_ir": True,
                "ir_recommended_axes": ir_recommended_axes,
                "retrieved_design_state_ir": ir_matches[:4],
                "retrieved_ir_cases": [match.get("case_id") for match in ir_matches[:4]],
                "scope": request.metadata.get("scope"),
                "context_snapshot_id": request.metadata.get("context_snapshot_id"),
                "minimum_semantic_distance": request.metadata.get("minimum_semantic_distance"),
            },
        )
    except Exception:
        return None


def _cross_domain_ir_matches(
    *,
    request: CrossDomainDivergenceRequest,
    object_type: str,
    source_summary: str,
    draft: IntentDraft | None,
    control_context: dict[str, object],
) -> list[dict[str, object]]:
    interpretation_id = request.interpretation_id or request.metadata.get("interpretation_id")
    if isinstance(interpretation_id, str) and interpretation_id:
        interpretation = _STORE.get_interpretation(interpretation_id)
        if interpretation is not None:
            ir_block = interpretation.features.get("design_state_ir")
            if isinstance(ir_block, dict):
                matches = ir_block.get("matches")
                if isinstance(matches, list) and matches:
                    reused: list[dict[str, object]] = []
                    for item in matches:
                        if isinstance(item, dict):
                            row = dict(item)
                            row.setdefault("ir_reuse", True)
                            row.setdefault("interpretation_id", interpretation_id)
                            reused.append(row)
                    if reused:
                        return reused

    retriever = _INTERACTION_SERVICE.ir_retriever
    if not retriever.ready:
        return []
    behavior_tools = [
        str(atom.tool)
        for atom in (draft.behavior_atoms if draft else [])
    ]
    confirmed = control_context.get("confirmed_intent")
    rejected = control_context.get("rejected_intent")
    confirmed_text = (
        str(confirmed.get("primary_intent"))
        if isinstance(confirmed, dict)
        else ""
    )
    rejected_text = (
        str(rejected.get("primary_intent"))
        if isinstance(rejected, dict)
        else ""
    )
    image_refs = request.metadata.get("image_refs")
    if not isinstance(image_refs, list):
        image_refs = []
    reference_images = request.metadata.get("reference_images")
    if not isinstance(reference_images, list):
        reference_images = []
    image_ref_count = _request_image_ref_count(image_refs, reference_images)
    live_signals = request.metadata.get("live_signals")
    if not isinstance(live_signals, dict):
        live_signals = {}
    features = {
        "event_type": "cross_domain_diverge",
        "selection_type": "none",
        "creative_stage": "global",
        "intent_text": " ".join(
            [
                source_summary,
                draft.text if draft and draft.text else "",
                confirmed_text,
                f"rejected:{rejected_text}" if rejected_text else "",
                f"image_refs:{image_ref_count}",
                " ".join(behavior_tools),
                object_type,
            ]
        ),
        "ir_scope_hint": "whole_object",
        "recent_reject_count": 0,
        "recent_accept_count": 1 if control_context.get("status") == "confirmed" else 0,
        "same_event_type_recent_count": len(behavior_tools),
        "live_signals": live_signals,
        "signals": {
            "interaction": {
                "event_type": "cross_domain_diverge",
                "behavior_tools": behavior_tools,
                "planner_gate_status": control_context.get("status"),
            },
            "semantic": {
                "object_type": object_type,
                "intent_text": source_summary,
                "confirmed_intent": confirmed_text,
                "rejected_intent": rejected_text,
                "image_ref_count": image_ref_count,
            },
            "visual_context": {
                "image_refs": image_refs,
                "reference_images": reference_images,
                "image_ref_count": image_ref_count,
            },
        },
    }
    return [match.to_feature() for match in retriever.retrieve(features, top_k=4)]


def _analogy_prompt_tokens(
    *,
    dimension: str,
    target_domain: str,
    relation: str,
    object_type: str,
) -> list[dict[str, object]]:
    base: list[tuple[str, str]] = [
        (target_domain, "source_domain"),
        (relation, "relation"),
    ]
    if dimension == "Aesthetic":
        base.extend([("cute proportion", "style"), ("soft color rhythm", "style")])
    elif dimension == "Structural":
        base.extend([("layered silhouette", "structure"), ("modular outline", "structure")])
    elif dimension == "Functional":
        base.extend([("clear affordance", "behavior"), ("purposeful detail", "behavior")])
    else:
        base.extend([("cross-domain analogy", "mood"), (f"recognizable {object_type}", "constraint")])
    tokens: list[dict[str, object]] = []
    seen: set[str] = set()
    for index, (label, role) in enumerate(base, start=1):
        clean = re.sub(r"\s+", " ", str(label)).strip(" .,:;")
        if not clean or clean.lower() in seen:
            continue
        seen.add(clean.lower())
        tokens.append(
            {
                "token_id": f"tok_{uuid4().hex[:8]}",
                "label": clean[:64],
                "dimension": dimension if dimension in {"Aesthetic", "Functional", "Structural"} else "Aesthetic",
                "role": role,
                "source": "planner_rule",
                "weight": max(0.55, 0.9 - index * 0.06),
            }
        )
        if len(tokens) >= 5:
            break
    return tokens


def _recommended_axes_from_ir_matches(matches: list[dict[str, object]]) -> list[str]:
    scores: dict[str, float] = {}
    for match in matches:
        strength = {"high": 1.0, "medium": 0.75, "low": 0.45}.get(
            str(match.get("evidence_strength") or "low"),
            0.45,
        )
        raw_axes = match.get("recommended_axes")
        if not isinstance(raw_axes, list):
            continue
        match_score = float(match.get("score") or 0.0)
        for rank, raw_axis in enumerate(raw_axes):
            axis = str(raw_axis)
            if axis not in {"Aesthetic", "Functional", "Structural"}:
                continue
            scores[axis] = scores.get(axis, 0.0) + match_score * strength * max(0.35, 1.0 - rank * 0.18)
    return [axis for axis, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)[:3]]


def _chat_completion_content(response: dict[str, object]) -> str:
    choices = response.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"]
            if isinstance(first.get("text"), str):
                return first["text"]
    if isinstance(response.get("content"), str):
        return response["content"]
    return json.dumps(response, ensure_ascii=False)


def _coerce_prompt_tokens(
    value: object,
    *,
    fallback_dimension: str,
    target_domain: str,
    relation: str,
    object_type: str,
) -> list[dict[str, object]]:
    tokens: list[dict[str, object]] = []
    if isinstance(value, list):
        for item in value[:8]:
            if isinstance(item, str):
                label = item
                dimension = fallback_dimension
                role = "analogy"
            elif isinstance(item, dict):
                label = str(item.get("label") or item.get("text") or "").strip()
                dimension = str(item.get("dimension") or fallback_dimension)
                role = str(item.get("role") or "analogy")
            else:
                continue
            label = re.sub(r"\s+", " ", label).strip(" .,:;")
            if not label:
                continue
            tokens.append(
                {
                    "token_id": f"tok_qwen_{uuid4().hex[:8]}",
                    "label": label[:64],
                    "dimension": dimension if dimension in {"Aesthetic", "Functional", "Structural"} else "Aesthetic",
                    "role": role[:32],
                    "source": "qwen3-planner",
                    "weight": 0.78,
                }
            )
    if tokens:
        return tokens[:6]
    return _analogy_prompt_tokens(
        dimension=fallback_dimension,
        target_domain=target_domain,
        relation=relation,
        object_type=object_type,
    )


def _extract_json_payload(content: str) -> dict[str, object]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.IGNORECASE).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if match is None:
            return {}
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return payload if isinstance(payload, dict) else {}


def _safe_direction_dimension(value: object, fallback: str = "Aesthetic") -> str:
    text = str(value or "").strip()
    if text in {"Aesthetic", "Functional", "Structural"}:
        return text
    return fallback if fallback in {"Aesthetic", "Functional", "Structural"} else "Aesthetic"


def _prompt_chip_evidence_rows(candidates: list[object]) -> str:
    rows = []
    for candidate in candidates:
        metadata = getattr(candidate, "metadata", {})
        evidence = metadata.get("pipeline_evidence") if isinstance(metadata, dict) else None
        if not isinstance(metadata, dict):
            metadata = {}
        if not isinstance(evidence, dict):
            evidence = {}
        package = metadata.get("analogy_prompt_package")
        if not isinstance(package, dict):
            package = {}
        tokens = (
            metadata.get("selected_prompt_tokens")
            or evidence.get("selected_prompt_tokens")
            or package.get("selected_prompt_tokens")
            or []
        )
        if isinstance(tokens, list):
            token_text = ", ".join(
                str(item.get("label") if isinstance(item, dict) else item)
                for item in tokens
                if item
            )
        else:
            token_text = ""
        direction_ids = (
            evidence.get("analogy_direction_ids")
            or package.get("direction_ids")
            or metadata.get("direction_ids")
            or []
        )
        if isinstance(direction_ids, list):
            direction_text = ", ".join(str(item) for item in direction_ids if item)
        else:
            direction_text = str(direction_ids or "")
        prompt = str(
            package.get("final_prompt")
            or metadata.get("execution_prompt")
            or evidence.get("execution_prompt")
            or ""
        )
        mode = str(
            metadata.get("prompt_token_mode")
            or evidence.get("prompt_token_mode")
            or package.get("prompt_token_mode")
            or ""
        )
        if not (mode or token_text or prompt):
            continue
        rows.append(
            "<tr>"
            f"<td>{escape(getattr(candidate, 'candidate_id', ''))}</td>"
            f"<td>{escape(mode)}</td>"
            f"<td>{escape(token_text)}</td>"
            f"<td>{escape(direction_text)}</td>"
            f"<td>{escape(prompt)}</td>"
            "</tr>"
        )
    return "\n".join(rows) or '<tr><td colspan="5">No prompt-chip evidence was recorded.</td></tr>'
