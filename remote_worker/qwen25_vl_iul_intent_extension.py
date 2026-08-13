from __future__ import annotations

import json
import re
import traceback
from typing import Any, Callable

import torch
from fastapi import HTTPException
from pydantic import BaseModel, Field


IUL_SYSTEM_PROMPT = (
    "You are FlowStudio's Interaction Understanding Layer for creative 3D design. "
    "Classify the user's latest interaction into intent hypotheses. "
    "Use the provided six-signal bundle: geometric, semantic, temporal, visual_context, "
    "interaction, and history. Return strict JSON only."
)


class IULIntentRequest(BaseModel):
    event: dict[str, Any] = Field(default_factory=dict)
    features: dict[str, Any] = Field(default_factory=dict)
    signals: dict[str, Any] = Field(default_factory=dict)
    valid_intents: list[str] = Field(default_factory=list)
    rule_based_prior: dict[str, Any] = Field(default_factory=dict)
    response_schema: dict[str, Any] = Field(default_factory=dict)


def install_iul_intent_endpoint(app: Any, model: Any, processor: Any) -> None:
    @app.post("/intent/interpret")
    def interpret_intent(req: IULIntentRequest) -> dict[str, Any]:
        valid_intents = req.valid_intents or _valid_intents_from_prior(req.rule_based_prior)
        if not valid_intents:
            raise HTTPException(status_code=400, detail="valid_intents is required")

        user_prompt = _build_intent_prompt(req, valid_intents)
        try:
            raw_response = _generate_json_from_text(model, processor, IUL_SYSTEM_PROMPT, user_prompt)
            parsed = _extract_json_object(raw_response) or {}
            hypotheses = _normalize_hypotheses(parsed, valid_intents)
        except Exception as exc:
            hypotheses = []
            raw_response = f"ERROR: {type(exc).__name__}: {str(exc)[:300]}\n{traceback.format_exc()[:2000]}"

        if not hypotheses:
            hypotheses = _fallback_prior_hypotheses(req.rule_based_prior, valid_intents)
            return {
                "hypotheses": hypotheses,
                "raw_response": raw_response,
                "fallback_used": True,
                "model": "qwen2.5-vl-iul-intent",
            }

        return {
            "hypotheses": hypotheses,
            "raw_response": raw_response,
            "fallback_used": False,
            "model": "qwen2.5-vl-iul-intent",
        }


def _build_intent_prompt(req: IULIntentRequest, valid_intents: list[str]) -> str:
    compact_payload = {
        "event": req.event,
        "signals": req.signals or req.features.get("signals", {}),
        "features": {
            key: value
            for key, value in req.features.items()
            if key
            in {
                "event_type",
                "asset_id",
                "part_id",
                "selection_type",
                "intent_text",
                "drag_vector",
                "drag_length",
                "axis_alignment",
                "creative_stage",
                "fidelity",
                "socket_compatibility_score",
                "same_part_recent_edits",
                "recent_accept_count",
                "recent_reject_count",
            }
        },
        "rule_based_prior": req.rule_based_prior,
    }
    return (
        "Classify this FlowStudio interaction.\n"
        f"valid_intents: {json.dumps(valid_intents, ensure_ascii=False)}\n"
        f"input: {json.dumps(compact_payload, ensure_ascii=False, default=str)}\n\n"
        "Return strict JSON only with this schema:\n"
        '{"hypotheses":[{"intent":"one valid_intent","confidence":0.0,'
        '"evidence":["short evidence string"]}]}\n'
        "Return 1 to 3 hypotheses. Confidence must be between 0 and 1. "
        "Prefer the user's action evidence over generic priors, but use the prior if signals are weak."
    )


def _generate_json_from_text(model: Any, processor: Any, system_prompt: str, user_prompt: str) -> str:
    prompt_text = (
        "<|im_start|>system\n"
        f"{system_prompt}<|im_end|>\n"
        "<|im_start|>user\n"
        f"{user_prompt}<|im_end|>\n"
        "<|im_start|>assistant\n"
    )
    tokenizer = getattr(processor, "tokenizer", None)
    if tokenizer is None or not callable(tokenizer):
        from transformers import AutoTokenizer

        model_name = getattr(getattr(model, "config", None), "_name_or_path", None)
        tokenizer = AutoTokenizer.from_pretrained(
            model_name or "/root/autodl-tmp/models/Qwen2.5-VL-7B-Instruct",
            trust_remote_code=True,
        )
    inputs = tokenizer(prompt_text, return_tensors="pt")
    inputs = {key: (value.to(model.device) if hasattr(value, "to") else value) for key, value in inputs.items()}

    with torch.inference_mode():
        generated_ids = model.generate(
            **inputs,
            max_new_tokens=256,
            do_sample=False,
            temperature=0.01,
        )

    input_token_len = inputs["input_ids"].shape[-1]
    new_tokens = generated_ids[:, input_token_len:]
    return tokenizer.batch_decode(
        new_tokens,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )[0]


def _extract_json_object(text: str) -> dict[str, Any] | None:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```[a-zA-Z]*\n?", "", candidate)
        candidate = re.sub(r"```$", "", candidate).strip()
    try:
        return json.loads(candidate)
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def _normalize_hypotheses(payload: dict[str, Any], valid_intents: list[str]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        raw_items = payload
    elif isinstance(payload, dict):
        raw_items = payload.get("hypotheses")
    else:
        raw_items = None
    if isinstance(payload, dict) and not isinstance(raw_items, list) and payload.get("primary_intent"):
        raw_items = [
            {
                "intent": payload.get("primary_intent"),
                "confidence": payload.get("confidence", 0.6),
                "evidence": payload.get("evidence", ["VLM selected primary intent."]),
            }
        ]

    hypotheses: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_items if isinstance(raw_items, list) else []:
        if not isinstance(item, dict):
            continue
        intent = str(item.get("intent") or "")
        if intent not in valid_intents or intent in seen:
            continue
        seen.add(intent)
        confidence = item.get("confidence", 0.5)
        try:
            score = max(0.0, min(1.0, float(confidence)))
        except Exception:
            score = 0.5
        evidence = item.get("evidence")
        if not isinstance(evidence, list):
            evidence = ["VLM hypothesis."]
        hypotheses.append(
            {
                "intent": intent,
                "confidence": round(score, 3),
                "evidence": [str(value) for value in evidence[:5]],
            }
        )
        if len(hypotheses) >= 3:
            break
    return hypotheses


def _fallback_prior_hypotheses(rule_based_prior: dict[str, Any], valid_intents: list[str]) -> list[dict[str, Any]]:
    raw_items = rule_based_prior.get("hypotheses") if isinstance(rule_based_prior, dict) else []
    normalized = _normalize_hypotheses({"hypotheses": raw_items}, valid_intents)
    if normalized:
        normalized[0]["evidence"] = [
            *normalized[0].get("evidence", []),
            "Qwen intent endpoint used rule-based prior fallback.",
        ][:5]
        return normalized
    return [
        {
            "intent": "unknown" if "unknown" in valid_intents else valid_intents[0],
            "confidence": 0.2,
            "evidence": ["No valid VLM or prior hypothesis was available."],
        }
    ]


def _valid_intents_from_prior(rule_based_prior: dict[str, Any]) -> list[str]:
    raw_items = rule_based_prior.get("hypotheses") if isinstance(rule_based_prior, dict) else []
    intents = []
    for item in raw_items if isinstance(raw_items, list) else []:
        if isinstance(item, dict) and item.get("intent"):
            intents.append(str(item["intent"]))
    return list(dict.fromkeys(intents))
