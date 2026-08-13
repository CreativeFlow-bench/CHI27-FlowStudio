"""Prompt chip package builder (refactor plan P2)."""

from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from app.models import PromptComposeRequest

_STORE: Any = None


def configure_prompt_chip(*, studio_store: Any) -> None:
    global _STORE
    _STORE = studio_store


def _build_prompt_chip_package(request: PromptComposeRequest) -> dict[str, object]:
    base_prompt = re.sub(r"\s+", " ", request.base_prompt or "").strip()
    tokens: list[dict[str, object]] = []
    seen_labels: set[str] = set()
    inferred_direction_ids: list[str] = []
    conflict_map: dict[str, list[str]] = {}
    for raw in request.selected_prompt_tokens:
        label = re.sub(
            r"\s+",
            " ",
            str(raw.get("label") or raw.get("text") or raw.get("value") or ""),
        ).strip(" ,.;")
        if not label and raw.get("full_phrase_zh"):
            label = re.sub(r"\s+", " ", str(raw["full_phrase_zh"])).strip(" ,.;")
        if not label or label.lower() in seen_labels:
            continue
        seen_labels.add(label.lower())
        delta = raw.get("attribute_delta")
        if isinstance(delta, dict) and delta.get("attribute") and delta.get("change"):
            conflict_map.setdefault(str(delta["attribute"]), []).append(
                f"{label[:40]}({delta['change']})"
            )
        source_direction_id = raw.get("source_direction_id") or raw.get("direction_id")
        if isinstance(source_direction_id, str) and source_direction_id:
            inferred_direction_ids.append(source_direction_id)
        weight = raw.get("weight")
        tokens.append(
            {
                "token_id": str(raw.get("token_id") or f"tok_user_{uuid4().hex[:8]}"),
                "label": label[:80],
                "dimension": str(raw.get("dimension") or "Cross-domain")[:40],
                "role": str(raw.get("role") or "keyword")[:40],
                "source_direction_id": source_direction_id if isinstance(source_direction_id, str) else None,
                "weight": float(weight) if isinstance(weight, (int, float)) else None,
                "full_phrase_zh": str(raw.get("full_phrase_zh") or label)[:240]
                if raw.get("full_phrase_zh")
                else None,
                "target_ref": raw.get("target_ref"),
                "operation": str(raw.get("operation") or "")[:40],
                "attribute_delta": delta if isinstance(delta, dict) else None,
                "provenance_path": raw.get("provenance_path"),
            }
        )
    conflicts = {
        attribute: list(dict.fromkeys(changes))
        for attribute, changes in conflict_map.items()
        if len({item.rsplit("(", 1)[-1].rstrip(")") for item in changes}) > 1
    }
    if conflicts and (request.metadata or {}).get("suggestion_mode") == "contextual_fragments_v1":
        raise HTTPException(
            status_code=409,
            detail=json.dumps(
                {
                    "status": "needs_resolution",
                    "message": "所选词片在属性变化上互相冲突，请先解决。",
                    "conflicts": conflicts,
                },
                ensure_ascii=False,
            ),
        )
    direction_ids = list(dict.fromkeys([*request.direction_ids, *inferred_direction_ids]))
    selected_directions: list[dict[str, object]] = []
    for direction_id in direction_ids:
        direction = _STORE.get_direction(direction_id)
        if direction is None:
            continue
        selected_directions.append(
            {
                "direction_id": direction.direction_id,
                "label": direction.label,
                "dimension": direction.dimension,
                "source_domain": direction.source_domain,
                "target_domain": direction.target_domain,
                "relation": direction.relation,
                "transfer_rationale": direction.transfer_rationale,
                "constraints": direction.constraints,
                "score": direction.score,
            }
        )
    selected_prompt_text = ", ".join(
        str(token.get("full_phrase_zh") or token["label"]) for token in tokens
    )
    final_prompt = base_prompt
    if selected_prompt_text and selected_prompt_text.lower() not in base_prompt.lower():
        final_prompt = f"{base_prompt}\nAnalogy keywords: {selected_prompt_text}".strip()
    return {
        "prompt_token_mode": "human_selectable_chips",
        "source": "backend_prompt_compose",
        "final_prompt": final_prompt,
        "selected_prompt_text": selected_prompt_text,
        "selected_prompt_tokens": tokens,
        "direction_ids": direction_ids,
        "selected_directions": selected_directions,
        "intent_draft_id": request.intent_draft_id,
        "metadata": request.metadata,
    }
