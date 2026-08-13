from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import urllib.error
import urllib.request

from app.models import GenerationMode, IntentHypothesis, IntentLabel, UserEvent
from app.services.model_api.text_gateway import TextModelGateway
from app.services.model_api.types import ModelStage


@dataclass
class IntentPrediction:
    hypotheses: list[IntentHypothesis]
    predictor: str
    predictor_version: str
    metadata: dict[str, object] = field(default_factory=dict)


class RuleBasedMultimodalIntentPredictor:
    """V0 predictor boundary.

    The implementation is intentionally rule-based, but the interface consumes
    the mixed-signal feature bundle that a later VLM/ranker should receive.
    """

    name = "rule_based_multisignal"
    version = "v0.3"

    def predict(self, event: UserEvent, features: dict[str, object]) -> IntentPrediction:
        hypotheses = self._generate_hypotheses(event, features)
        return IntentPrediction(
            hypotheses=hypotheses,
            predictor=self.name,
            predictor_version=self.version,
            metadata={
                "mode": "rule_based",
                "task": "intent_predict",
                "vlm_ready": True,
                "fallback_used": False,
                "consumed_signals": [
                    "geometric",
                    "semantic",
                    "temporal",
                    "visual_context",
                    "interaction",
                    "history",
                ],
            },
        )

    def predict_rules_only(self, event: UserEvent, features: dict[str, object]) -> IntentPrediction:
        """Fast path used before optional async VLM refinement."""
        prediction = self.predict(event, features)
        prediction.metadata = {
            **prediction.metadata,
            "mode": "rule_first_pending_vlm",
            "vlm_pending": False,
            "task": "intent_predict",
        }
        return prediction

    def _generate_hypotheses(
        self, event: UserEvent, features: dict[str, object]
    ) -> list[IntentHypothesis]:
        event_type = event.type
        hypotheses: list[IntentHypothesis] = []
        intent_text = str(features.get("intent_text") or "").lower()
        has_text = bool(intent_text)
        same_part_edits = int(features.get("same_part_recent_edits") or 0)
        image_ref_count = int(features.get("image_ref_count") or 0)
        boundary_language = any(
            term in intent_text
            for term in ["boundary", "edge", "seam", "preserve", "clean up", "refine"]
        )
        whole_object_aesthetic_language = any(
            term in intent_text
            for term in [
                "cute",
                "cuter",
                "adorable",
                "lovely",
                "playful",
                "more creative",
                "creative",
                "diverge",
                "variation",
                "可爱",
                "更可爱",
                "创意",
                "发散",
                "变化",
            ]
        )

        if event_type in {"part_select", "part_hover", "hover_focus", "semantic_hover_ended"}:
            hypotheses.append(
                IntentHypothesis(
                    intent=IntentLabel.target_part,
                    confidence=0.62,
                    evidence=["User focused a specific part."],
                )
            )

        if event_type == "brush_end":
            if boundary_language:
                hypotheses.append(
                    IntentHypothesis(
                        intent=IntentLabel.refine_boundary,
                        confidence=0.86,
                        evidence=[
                            "Brush selection ended on a region.",
                            "User text emphasizes boundary, edge, seam, or preservation.",
                        ],
                    )
                )
            if has_text:
                hypotheses.append(
                    IntentHypothesis(
                        intent=IntentLabel.replace_region,
                        confidence=0.72 if boundary_language else 0.84,
                        evidence=[
                            "Brush selection ended on a region.",
                            "User provided text intent for the selected region.",
                        ],
                    )
                )
            hypotheses.append(
                IntentHypothesis(
                    intent=IntentLabel.semantic_focus,
                    confidence=0.58,
                    evidence=["Brush selection indicates a semantically important region."],
                )
            )
            if same_part_edits >= 3:
                hypotheses.append(
                    IntentHypothesis(
                        intent=IntentLabel.refine_boundary,
                        confidence=0.67,
                        evidence=["The same part or region has been edited repeatedly."],
                    )
                )

        if event_type == "drag_end":
            drag_length = float(features.get("drag_length") or 0)
            if drag_length > 0.05:
                hypotheses.append(
                    IntentHypothesis(
                        intent=IntentLabel.extend_part,
                        confidence=0.71,
                        evidence=[
                            "Drag has meaningful distance.",
                            "Drag direction is interpreted as outward from the selected part.",
                        ],
                    )
                )
                hypotheses.append(
                    IntentHypothesis(
                        intent=IntentLabel.change_proportion,
                        confidence=0.47,
                        evidence=["Dragging a part may express proportion adjustment."],
                    )
                )
            hypotheses.append(
                IntentHypothesis(
                    intent=IntentLabel.explore_shape,
                    confidence=0.39 if not has_text else 0.28,
                evidence=["No precise semantic replacement request is required for drag."],
                )
            )

        if event_type == "smooth_end":
            strength = float(features.get("smooth_strength") or 0)
            preserve_boundary = bool(features.get("smooth_preserve_boundary"))
            hypotheses.append(
                IntentHypothesis(
                    intent=IntentLabel.deform_surface,
                    confidence=0.8 if strength > 0 else 0.72,
                    evidence=[
                        "Smooth tool ended on a local 3D surface region.",
                        "Smoothing brush parameters indicate surface refinement rather than replacement.",
                    ],
                )
            )
            if preserve_boundary:
                hypotheses.append(
                    IntentHypothesis(
                        intent=IntentLabel.refine_boundary,
                        confidence=0.64,
                        evidence=[
                            "Smooth operation requests boundary preservation.",
                            "Local geometry refinement should avoid changing adjacent regions.",
                        ],
                    )
                )

        if event_type in {"primitive_add_intent", "primitive_added"}:
            hypotheses.append(
                IntentHypothesis(
                    intent=IntentLabel.deform_surface,
                    confidence=0.76,
                    evidence=[
                        "User expressed an intent to add a 3D primitive.",
                        "Primitive type, transform, and relation provide structural edit evidence.",
                    ],
                )
            )
            hypotheses.append(
                IntentHypothesis(
                    intent=IntentLabel.explore_shape,
                    confidence=0.52,
                    evidence=["Adding a primitive may also be an exploratory rough-form move."],
                )
            )

        if event_type == "candidate_compared":
            hypotheses.append(
                IntentHypothesis(
                    intent=IntentLabel.compare_candidates,
                    confidence=0.76,
                    evidence=["User is inspecting generated alternatives."],
                )
            )
        if event_type == "candidate_accepted":
            hypotheses.append(
                IntentHypothesis(
                    intent=IntentLabel.accept_direction,
                    confidence=0.88,
                    evidence=["User accepted a candidate direction."],
                )
            )
        if event_type == "candidate_rejected":
            hypotheses.append(
                IntentHypothesis(
                    intent=IntentLabel.reject_direction,
                    confidence=0.83,
                    evidence=["User rejected a candidate direction."],
                )
            )
        if event_type == "generation_requested":
            mode = event.payload.get("mode") or event.payload.get("intent", {}).get("mode")
            creative_stage = str(features.get("creative_stage") or "")
            if creative_stage == "part" or mode == GenerationMode.replace:
                label = IntentLabel.replace_region
            elif creative_stage == "texture":
                label = IntentLabel.deform_surface
            else:
                label = IntentLabel.explore_shape
            hypotheses.append(
                IntentHypothesis(
                    intent=label,
                    confidence=0.8,
                    evidence=[
                        "User explicitly requested generation.",
                        f"Creative stage: {creative_stage or 'unspecified'}.",
                    ],
                )
            )
        if event_type in {
            "intent_text_changed",
            "intent_episode_sent",
            "intent_episode_submitted",
            "annotation_commit",
        }:
            if whole_object_aesthetic_language:
                hypotheses.append(
                    IntentHypothesis(
                        intent=IntentLabel.explore_shape,
                        confidence=0.74 if event_type in {"intent_episode_sent", "intent_episode_submitted"} else 0.68,
                        evidence=[
                            "User text asks for whole-object aesthetic or creative exploration.",
                            "No explicit local target overrides the whole-object scope.",
                        ],
                    )
                )
            if image_ref_count > 0:
                hypotheses.append(
                    IntentHypothesis(
                        intent=IntentLabel.explore_shape,
                        confidence=0.61 if whole_object_aesthetic_language else 0.56,
                        evidence=[
                            f"User attached {image_ref_count} reference image(s) as multimodal intent evidence.",
                            "Reference images should guide prompt expansion without overwriting confirmed object identity.",
                        ],
                    )
                )
            elif has_text and not whole_object_aesthetic_language:
                hypotheses.append(
                    IntentHypothesis(
                        intent=IntentLabel.unknown,
                        confidence=0.34,
                        evidence=[
                            "User provided natural language, but no executable target or operation is stable yet.",
                        ],
                    )
                )
        if event_type == "undo":
            hypotheses.append(
                IntentHypothesis(
                    intent=IntentLabel.reject_direction,
                    confidence=0.64,
                    evidence=["Undo indicates the previous operation was not satisfactory."],
                )
            )

        return hypotheses or [
            IntentHypothesis(
                intent=IntentLabel.unknown,
                confidence=0.2,
                evidence=["Event is recorded for memory but not interpreted in v0."],
            )
        ]


DEFAULT_PLANNER_SYSTEM_PROMPT = (
    "You are FlowStudio's interaction-understanding planner. "
    "Consume live interaction signals, retrieved design-state IR, current 3D context, "
    "and optional visual evidence. Return compact JSON only that matches the requested schema. "
    "Target priority (strict): "
    "(1) If the user text/image language clearly names a part or region "
    "(e.g. 鼻子/帽子/head/scarf, or a registered part label), treat that semantic target as primary "
    "— even if a different part is hovered or last-selected. "
    "(2) If language does NOT name a part/region, prefer stable interaction evidence: "
    "brush_end / drag_end / smooth_end / part_select with repeated edits on the same part. "
    "(3) Never treat hover-only or a single brief hover as proof of a part-change intent. "
    "(4) If semantic target and interaction target conflict, lower confidence, set "
    "needs_clarification=true, and ask a short clarification between the two targets. "
    "(5) Prefer concrete operation + scope (part|region|whole|material) over vague explore "
    "when evidence is sufficient; otherwise keep ambiguity explicit in hypotheses."
)


class VLMIntentPredictor:
    """HTTP VLM intent predictor with rule-based fallback.

    The endpoint should accept a JSON object with the raw user event, extracted
    six-signal features, valid intent labels, and the rule-based prior. It may
    return either {"hypotheses": [...]} or {"primary_intent": "..."}.
    """

    name = "vlm_multisignal"
    version = "v0.1"

    def __init__(
        self,
        endpoint_url: str,
        timeout_sec: float = 8,
        fallback: RuleBasedMultimodalIntentPredictor | None = None,
        fallback_to_rules: bool = True,
        fallback_endpoint_urls: list[str] | None = None,
        model_name: str = "qwen3-planner",
        system_prompt: str | None = None,
    ) -> None:
        self.endpoint_url = endpoint_url.rstrip("/")
        self.timeout_sec = timeout_sec
        self.fallback = fallback or RuleBasedMultimodalIntentPredictor()
        self.fallback_to_rules = fallback_to_rules
        self.fallback_endpoint_urls = [
            value.rstrip("/")
            for value in (fallback_endpoint_urls or [])
            if isinstance(value, str) and value.strip()
        ]
        self.model_name = model_name or "qwen3-planner"
        self.system_prompt = system_prompt or DEFAULT_PLANNER_SYSTEM_PROMPT
        self.system_prompt_override: str | None = None

    def predict_rules_only(self, event: UserEvent, features: dict[str, object]) -> IntentPrediction:
        prior = self.fallback.predict(event, features)
        return IntentPrediction(
            hypotheses=prior.hypotheses,
            predictor=self.name,
            predictor_version=self.version,
            metadata={
                "mode": "rule_first_pending_vlm",
                "task": "intent_predict",
                "endpoint_configured": True,
                "primary_endpoint": self.endpoint_url,
                "fallback_endpoint_count": len(self.fallback_endpoint_urls),
                "planner_model": self.model_name,
                "planner_role": "multimodal_planner",
                "vlm_pending": True,
                "fallback_used": False,
                "rule_based_prior": prior.metadata,
            },
        )

    def effective_system_prompt(self) -> str:
        override = getattr(self, "system_prompt_override", None)
        if isinstance(override, str) and override.strip():
            return override.strip()
        configured = getattr(self, "system_prompt", None)
        if isinstance(configured, str) and configured.strip():
            return configured.strip()
        return DEFAULT_PLANNER_SYSTEM_PROMPT

    def build_request_payload(
        self,
        event: UserEvent,
        features: dict[str, object],
        *,
        prior: IntentPrediction | None = None,
    ) -> dict[str, object]:
        prior = prior or self.fallback.predict(event, features)
        return {
            "task": "intent_predict",
            "event": event.model_dump(mode="json"),
            "features": features,
            "signals": features.get("signals", {}),
            "valid_intents": [item.value for item in IntentLabel],
            "rule_based_prior": {
                "predictor": prior.predictor,
                "predictor_version": prior.predictor_version,
                "hypotheses": [item.model_dump(mode="json") for item in prior.hypotheses],
            },
            "response_schema": {
                "hypotheses": [
                    {
                        "intent": "one of valid_intents",
                        "confidence": "number 0..1",
                        "evidence": ["short evidence strings"],
                    }
                ]
            },
        }

    def build_prompt_bundle(
        self,
        event: UserEvent,
        features: dict[str, object],
        *,
        system_prompt: str | None = None,
        prior: IntentPrediction | None = None,
    ) -> dict[str, object]:
        prior = prior or self.fallback.predict(event, features)
        payload = self.build_request_payload(event, features, prior=prior)
        system = (system_prompt or self.effective_system_prompt()).strip()
        user = json.dumps(payload, ensure_ascii=False, indent=2)
        return {
            "system": system,
            "user": user,
            "user_payload": payload,
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "rule_based_prior": payload["rule_based_prior"],
        }

    def predict(self, event: UserEvent, features: dict[str, object]) -> IntentPrediction:
        prior = self.fallback.predict(event, features)
        request_payload = self.build_request_payload(event, features, prior=prior)
        errors: list[str] = []
        try:
            response = self._post_json(request_payload)
            endpoint_used = self.endpoint_url
            endpoint_role = "primary"
        except Exception as exc:
            errors.append(f"primary:{type(exc).__name__}: {str(exc)[:220]}")
            response = {}
            endpoint_used = ""
            endpoint_role = ""
            for endpoint in self.fallback_endpoint_urls:
                try:
                    response = self._post_json_to_endpoint(endpoint, request_payload)
                    endpoint_used = endpoint
                    endpoint_role = "fallback"
                    break
                except Exception as fallback_exc:
                    errors.append(
                        f"fallback:{type(fallback_exc).__name__}: {str(fallback_exc)[:220]}"
                    )
            if not response:
                if not self.fallback_to_rules:
                    raise RuntimeError("; ".join(errors)) from exc
                prior.metadata = {
                    **prior.metadata,
                    "mode": "rule_fallback",
                    "task": "intent_predict",
                    "endpoint_configured": True,
                    "primary_endpoint": self.endpoint_url,
                    "fallback_endpoint_count": len(self.fallback_endpoint_urls),
                    "planner_model": self.model_name,
                    "planner_role": "multimodal_planner",
                    "vlm_error": "; ".join(errors)[:500],
                    "fallback_used": True,
                    "fallback_reason": "model_unavailable",
                }
                return prior
        try:
            hypotheses = self._parse_hypotheses(response)
            if self._should_trust_prior_over_unknown(prior.hypotheses, hypotheses):
                return IntentPrediction(
                    hypotheses=prior.hypotheses,
                    predictor=self.name,
                    predictor_version=self.version,
                    metadata={
                        "mode": "rule_based_prior_guardrail",
                        "task": "intent_predict",
                        "endpoint_configured": True,
                        "primary_endpoint": self.endpoint_url,
                        "endpoint_used": endpoint_used,
                        "endpoint_role": endpoint_role,
                        "fallback_endpoint_count": len(self.fallback_endpoint_urls),
                        "planner_model": self.model_name,
                        "planner_role": "multimodal_planner",
                        "fallback_used": False,
                        "guardrail_reason": "vlm_unknown_with_high_confidence_tool_prior",
                        "rule_based_prior": prior.metadata,
                        "raw_response_keys": sorted(response.keys()),
                        **self._planner_metadata(response),
                    },
                )
            if hypotheses:
                return IntentPrediction(
                    hypotheses=hypotheses,
                    predictor=self.name,
                    predictor_version=self.version,
                    metadata={
                        "mode": "vlm_http",
                        "task": "intent_predict",
                        "endpoint_configured": True,
                        "primary_endpoint": self.endpoint_url,
                        "endpoint_used": endpoint_used,
                        "endpoint_role": endpoint_role,
                        "fallback_endpoint_count": len(self.fallback_endpoint_urls),
                        "planner_model": self.model_name,
                        "planner_role": "multimodal_planner",
                        "fallback_used": False,
                        "vlm_pending": False,
                        "rule_based_prior": prior.metadata,
                        "raw_response_keys": sorted(response.keys()),
                        **self._planner_metadata(response),
                    },
                )
            raise ValueError("VLM response did not contain valid hypotheses")
        except Exception as exc:
            if not self.fallback_to_rules:
                raise
            # rule_fallback is reserved for model/transport unavailability only.
            prior.metadata = {
                **prior.metadata,
                "mode": "rule_fallback",
                "task": "intent_predict",
                "endpoint_configured": True,
                "primary_endpoint": self.endpoint_url,
                "endpoint_used": endpoint_used,
                "endpoint_role": endpoint_role,
                "fallback_endpoint_count": len(self.fallback_endpoint_urls),
                "planner_model": self.model_name,
                "planner_role": "multimodal_planner",
                "vlm_error": f"{'; '.join(errors)}; parse:{type(exc).__name__}: {str(exc)[:240]}"[:500],
                "fallback_used": True,
                "fallback_reason": "invalid_model_response",
            }
            return prior

    def _post_json(self, payload: dict[str, object]) -> dict[str, Any]:
        return self._post_json_to_endpoint(self.endpoint_url, payload)

    def _post_json_to_endpoint(self, endpoint_url: str, payload: dict[str, object]) -> dict[str, Any]:
        request_payload = self._chat_completion_payload(payload) if "/chat/completions" in endpoint_url else payload
        request = urllib.request.Request(
            endpoint_url,
            data=json.dumps(request_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
                raw = json.loads(response.read().decode("utf-8"))
                return self._chat_completion_json(raw) if "/chat/completions" in endpoint_url else raw
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"VLM HTTP {exc.code}: {body[:300]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"VLM unavailable: {exc}") from exc

    def _chat_completion_payload(self, payload: dict[str, object]) -> dict[str, object]:
        return {
            "model": self.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": self.effective_system_prompt(),
                },
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "temperature": 0.1,
            "max_tokens": 700,
            "response_format": {"type": "json_object"},
        }

    def _chat_completion_json(self, response: dict[str, Any]) -> dict[str, Any]:
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            return response
        first = choices[0]
        if not isinstance(first, dict):
            return response
        message = first.get("message")
        content = message.get("content") if isinstance(message, dict) else first.get("text")
        if not isinstance(content, str):
            return response
        try:
            parsed = json.loads(content.strip())
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}")
            if start < 0 or end <= start:
                return response
            try:
                parsed = json.loads(content[start : end + 1])
            except json.JSONDecodeError:
                return response
        return parsed if isinstance(parsed, dict) else response

    def _planner_metadata(self, response: dict[str, Any]) -> dict[str, object]:
        metadata: dict[str, object] = {}
        for key in (
            "scope",
            "change_scope",
            "recommended_axes",
            "divergent_keywords",
            "clarification_question",
            "needs_clarification",
            "planner_narration",
        ):
            value = response.get(key)
            if value is not None:
                metadata[key] = value
        return metadata

    def _parse_hypotheses(self, response: dict[str, Any]) -> list[IntentHypothesis]:
        raw_items = response.get("hypotheses")
        if not isinstance(raw_items, list) and response.get("primary_intent"):
            raw_items = [
                {
                    "intent": response.get("primary_intent"),
                    "confidence": response.get("confidence", 0.6),
                    "evidence": response.get("evidence", ["VLM selected primary intent."]),
                }
            ]
        hypotheses: list[IntentHypothesis] = []
        for item in raw_items if isinstance(raw_items, list) else []:
            if not isinstance(item, dict):
                continue
            try:
                intent = IntentLabel(str(item.get("intent")))
            except ValueError:
                continue
            confidence = item.get("confidence", 0.5)
            if not isinstance(confidence, int | float):
                confidence = 0.5
            evidence = item.get("evidence")
            if not isinstance(evidence, list):
                evidence = ["VLM hypothesis."]
            hypotheses.append(
                IntentHypothesis(
                    intent=intent,
                    confidence=max(0.0, min(1.0, float(confidence))),
                    evidence=[str(value) for value in evidence[:6]],
                )
            )
        return hypotheses

    def _should_trust_prior_over_unknown(
        self,
        prior_hypotheses: list[IntentHypothesis],
        vlm_hypotheses: list[IntentHypothesis],
    ) -> bool:
        if not prior_hypotheses or not vlm_hypotheses:
            return False
        best_prior = max(prior_hypotheses, key=lambda item: item.confidence)
        best_vlm = max(vlm_hypotheses, key=lambda item: item.confidence)
        return (
            best_vlm.intent == IntentLabel.unknown
            and best_prior.intent != IntentLabel.unknown
            and best_prior.confidence >= 0.7
        )


class ExternalInteractionIntentPredictor(VLMIntentPredictor):
    """Synchronous predictor facade backed by the shared external gateway."""

    version = "external-v1"

    def __init__(
        self,
        gateway: TextModelGateway,
        *,
        fallback: RuleBasedMultimodalIntentPredictor | None = None,
    ) -> None:
        self.gateway = gateway
        super().__init__(
            gateway.profile.api_base if gateway.profile.api_key else "",
            timeout_sec=gateway.profile.timeout_sec,
            fallback=fallback,
            fallback_to_rules=True,
            fallback_endpoint_urls=[],
            model_name=gateway.profile.fast_text_model,
        )

    def _post_json(self, payload: dict[str, object]) -> dict[str, Any]:
        request = self._chat_completion_payload(payload)

        async def complete() -> dict[str, Any]:
            result = await self.gateway.complete_json(
                ModelStage.INTENT,
                request["messages"],  # type: ignore[arg-type]
                validator=lambda raw: raw,
                temperature=0.1,
                max_tokens=700,
            )
            return result.value

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(complete())
        # ``predict`` is a synchronous boundary.  When a caller invokes it
        # inside an event loop, isolate the short async gateway run in a worker.
        with ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(asyncio.run, complete()).result()

    def predict(self, event: UserEvent, features: dict[str, object]) -> IntentPrediction:
        if not self.gateway.profile.api_key:
            prediction = self.fallback.predict(event, features)
            prediction.metadata = {
                **prediction.metadata,
                "mode": "rule_only_external_api_unconfigured",
                "fallback_used": True,
                "fallback_reason": "external_api_key_missing",
            }
            return prediction
        return super().predict(event, features)


def build_multimodal_intent_predictor(
    endpoint_url: str | None,
    timeout_sec: float = 8,
    fallback_to_rules: bool = True,
    fallback_endpoint_urls: list[str] | None = None,
    model_name: str = "qwen3-planner",
) -> RuleBasedMultimodalIntentPredictor | VLMIntentPredictor:
    if endpoint_url:
        return VLMIntentPredictor(
            endpoint_url,
            timeout_sec=timeout_sec,
            fallback_to_rules=fallback_to_rules,
            fallback_endpoint_urls=fallback_endpoint_urls,
            model_name=model_name,
        )
    return RuleBasedMultimodalIntentPredictor()
