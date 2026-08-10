"""OpenAI-compatible generators for post-Gate semantic divergence."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from pydantic import ValidationError

from app.models import KnowledgeEvidence, SemanticCandidate, SemanticDivergenceRequest
from app.services.model_api.text_gateway import TextModelGateway
from app.services.model_api.transport import ModelTransportUnavailable
from app.services.model_api.types import ModelStage


_SYSTEM_PROMPT = """You are FlowStudio's semantic-divergence generator.
Return a JSON object whose candidates field contains 9–15 items. Each display_label_zh
must be 2–8个字, not a complete sentence. Never use Aesthetic, Structural, Functional,
Cross-domain, shape, connection, material, surface, silhouette, or ornament as a label.
Each item must contain group, target_ref, operation, semantic_anchor, prompt_phrase,
attribute_delta, and scores. candidate_id must be unique; label_en is required. group must
be exactly one of shape, connection, surface, semantic_transfer. scores must contain exactly
identity, scope, relevance, specificity, and novelty as numbers from 0 to 1. Preserve object identity and strictly stay within the Gate
target and scope. Knowledge evidence is an optional donor; do not copy source titles or
invent provenance. For scope material_region, target_ref.type must be material_region
and target_ref.id must equal semantic_target.mask_ref, falling back to part_id only when
mask_ref is absent. Return exactly 9 candidates, with terse field values and no Markdown
fences, so the complete JSON fits within the local model's output window. Use concrete
directions such as 鳄鱼压纹 or 珍珠光泽; reject generic labels such as 纹理变化, 调整,
优化, 建议, or 测试."""


class SemanticModelUnavailable(Exception):
    """A model endpoint cannot be reached or is not configured."""


class SemanticModelOutputError(Exception):
    """A model response remains outside the semantic candidate schema after repair."""


class _SemanticGenerator:
    """Shared payload, transport, repair, and candidate parsing for both providers."""

    def __init__(
        self,
        endpoint_url: str,
        *,
        model: str,
        timeout_sec: float,
        api_key: str = "",
        min_candidates: int = 9,
        max_candidates: int = 15,
    ) -> None:
        self.endpoint_url = endpoint_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_sec = timeout_sec
        self.min_candidates = min_candidates
        self.max_candidates = max_candidates

    @property
    def configured(self) -> bool:
        return bool(self.endpoint_url and self.model)

    async def generate(
        self,
        request: SemanticDivergenceRequest,
        evidence: KnowledgeEvidence,
    ) -> list[SemanticCandidate]:
        import asyncio

        return await asyncio.to_thread(self.generate_sync, request, evidence)

    def generate_sync(
        self,
        request: SemanticDivergenceRequest,
        evidence: KnowledgeEvidence,
    ) -> list[SemanticCandidate]:
        if not self.configured:
            raise SemanticModelUnavailable("semantic model endpoint or model is not configured")
        try:
            parsed, errors = self._request_and_parse(
                self.build_payload(request, evidence), evidence
            )
        except SemanticModelOutputError as exc:
            parsed, errors = None, [{"msg": str(exc)}]
        if parsed is not None:
            return parsed
        try:
            repaired, repair_errors = self._request_and_parse(
                self.build_payload(request, evidence, repair_errors=errors), evidence
            )
        except SemanticModelOutputError as exc:
            repaired, repair_errors = None, [{"msg": str(exc)}]
        if repaired is not None:
            return repaired
        raise SemanticModelOutputError(
            f"semantic candidate validation failed after one repair: {repair_errors[:3]}"
        )

    def build_payload(
        self,
        request: SemanticDivergenceRequest,
        evidence: KnowledgeEvidence,
        *,
        repair_errors: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        scope = request.scope.strip().lower()
        target_type = (
            "material_region"
            if scope == "material_region"
            else "part"
            if scope == "part"
            else "whole"
        )
        target_id = (
            request.semantic_target.mask_ref or request.semantic_target.part_id
            if target_type != "whole"
            else None
        )
        request_payload = request.model_dump(mode="json")
        request_payload["params"]["candidate_count"] = 9
        user_content: dict[str, Any] = {
            "request": request_payload,
            "knowledge_evidence": evidence.model_dump(mode="json"),
            "response_schema": {
                "candidates": [
                    {
                        "candidate_id": "unique_short_id",
                        "display_label_zh": "2–8个字",
                        "label_en": "short concrete English label",
                        "group": "shape | connection | surface | semantic_transfer",
                        "target_ref": {
                            "asset_id": request.asset_id,
                            "type": target_type,
                            "id": target_id,
                        },
                        "operation": "specific design operation",
                        "semantic_anchor": "concrete semantic donor or quality",
                        "prompt_phrase": "complete concise generation direction",
                        "attribute_delta": {
                            "attribute": "one explicit attribute",
                            "change": "one explicit change",
                        },
                        "scores": {
                            "identity": 0.9,
                            "scope": 0.9,
                            "relevance": 0.9,
                            "specificity": 0.9,
                            "novelty": 0.8,
                        },
                    }
                ],
                "candidate_count": 9,
                "requirements": [
                    "Return exactly 9 candidates and keep every text field concise.",
                    "Return only the JSON object; do not rename keys.",
                    "Use at least two relevant groups; at high temperature include at least two semantic_transfer items.",
                    "Copy target_ref asset_id/type/id exactly from this schema in every item.",
                ],
            },
        }
        if repair_errors is not None:
            user_content["previous_attempt_validation_errors"] = repair_errors[:8]
            user_content["instruction"] = (
                "Your previous output failed validation. Return the same JSON object corrected "
                "to satisfy every listed error."
            )
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_content, ensure_ascii=False)},
            ],
            "temperature": request.params.model_temperature,
            "max_tokens": 3600,
            "response_format": {"type": "json_object"},
        }

    def _request_and_parse(
        self, payload: dict[str, Any], evidence: KnowledgeEvidence
    ) -> tuple[list[SemanticCandidate] | None, list[dict[str, Any]]]:
        try:
            return self._parse_candidates(self._post_json(payload), evidence)
        except SemanticModelUnavailable:
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise SemanticModelUnavailable(f"semantic model unavailable: {exc}") from exc

    def _post_json(self, payload: dict[str, Any]) -> Any:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        http_request = urllib.request.Request(
            self.endpoint_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(http_request, timeout=self.timeout_sec) as response:
                return self._extract_json(json.loads(response.read().decode("utf-8")))
        except urllib.error.HTTPError as exc:
            if exc.code in {429, 500, 502, 503, 504}:
                raise SemanticModelUnavailable(f"semantic model HTTP {exc.code}") from exc
            raise SemanticModelOutputError(f"semantic model HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise SemanticModelUnavailable(f"semantic model unavailable: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise SemanticModelOutputError("semantic model returned invalid JSON") from exc

    @staticmethod
    def _extract_json(response: Any) -> Any:
        if not isinstance(response, dict):
            return response
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            return response
        first = choices[0]
        message = first.get("message") if isinstance(first, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            return response
        normalized = content.strip()
        if normalized.startswith("```"):
            normalized = normalized.split("\n", 1)[1] if "\n" in normalized else ""
            if normalized.endswith("```"):
                normalized = normalized[:-3].rstrip()
        try:
            return json.loads(normalized)
        except json.JSONDecodeError:
            return response

    def _parse_candidates(
        self, raw: Any, evidence: KnowledgeEvidence
    ) -> tuple[list[SemanticCandidate] | None, list[dict[str, Any]]]:
        if not isinstance(raw, dict) or not isinstance(raw.get("candidates"), list):
            return None, [{"msg": "model did not return a JSON object with candidates"}]
        candidate_data = raw["candidates"]
        if not self.min_candidates <= len(candidate_data) <= self.max_candidates:
            return None, [
                {
                    "loc": ["candidates"],
                    "msg": f"expected {self.min_candidates}–{self.max_candidates} candidates",
                }
            ]
        if not all(isinstance(candidate, dict) for candidate in candidate_data):
            return None, [{"loc": ["candidates"], "msg": "every candidate must be an object"}]
        provenance = {
            "generator": self.model,
            "mode": evidence.route.mode,
            "wikidata": evidence.wikidata,
            "getty_aat": evidence.getty_aat,
            "asknature": evidence.asknature,
        }
        group_aliases = {
            "form": "shape",
            "silhouette": "shape",
            "joint": "connection",
            "join": "connection",
            "attachment": "connection",
            "material": "surface",
            "texture": "surface",
            "finish": "surface",
            "semantic": "semantic_transfer",
            "semantic transfer": "semantic_transfer",
            "cross-domain": "semantic_transfer",
            "cross domain": "semantic_transfer",
        }
        normalized_candidates = []
        for candidate in candidate_data:
            normalized = dict(candidate)
            group = str(normalized.get("group") or "").strip().lower().replace("_", " ")
            normalized["group"] = group_aliases.get(group, normalized.get("group"))
            normalized_candidates.append(normalized)
        try:
            return [
                SemanticCandidate.model_validate({**candidate, "provenance": provenance})
                for candidate in normalized_candidates
            ], []
        except ValidationError as exc:
            return None, [
                {"loc": list(error.get("loc", [])), "msg": error.get("msg", "invalid")}
                for error in exc.errors()
            ]


class GeminiSemanticGenerator(_SemanticGenerator):
    """Gemini relay client for the semantic-divergence contract."""

    def __init__(
        self,
        api_base: str,
        api_key: str,
        *,
        model: str = "gemini-3.5-flash",
        timeout_sec: float = 25,
    ) -> None:
        super().__init__(
            f"{api_base.rstrip('/')}/chat/completions",
            api_key=api_key,
            model=model,
            timeout_sec=timeout_sec,
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key and super().configured)


class LocalVlmSemanticGenerator(_SemanticGenerator):
    """Local Qwen2.5-VL client with the exact Gemini candidate contract."""

    def __init__(
        self,
        endpoint_url: str,
        *,
        model: str = "qwen2.5-vl",
        timeout_sec: float = 35,
    ) -> None:
        super().__init__(endpoint_url, model=model, timeout_sec=timeout_sec)


class GatewaySemanticGenerator(_SemanticGenerator):
    """Semantic-candidate adapter using an approved external model stage."""

    def __init__(
        self,
        gateway: TextModelGateway,
        *,
        stage: ModelStage,
        model: str,
        min_candidates: int = 9,
        max_candidates: int = 15,
    ) -> None:
        super().__init__(
            gateway.profile.api_base,
            api_key=gateway.profile.api_key,
            model=model,
            timeout_sec=gateway.profile.timeout_sec,
            min_candidates=min_candidates,
            max_candidates=max_candidates,
        )
        self.gateway = gateway
        self.stage = stage

    async def generate(
        self,
        request: SemanticDivergenceRequest,
        evidence: KnowledgeEvidence,
    ) -> list[SemanticCandidate]:
        if not self.configured:
            raise SemanticModelUnavailable("external model API is not configured")
        payload = self.build_payload(request, evidence)

        def validate(raw: dict[str, Any]) -> list[SemanticCandidate]:
            parsed, errors = self._parse_candidates(raw, evidence)
            if parsed is None:
                raise SemanticModelOutputError(
                    f"semantic candidate validation failed: {errors[:3]}"
                )
            return parsed

        try:
            result = await self.gateway.complete_json(
                self.stage,
                payload["messages"],
                validator=validate,
                repair_instruction=(
                    "Return the same semantic candidates JSON corrected to "
                    "satisfy the reported validation error."
                ),
                temperature=request.params.model_temperature,
                max_tokens=3600,
            )
        except ModelTransportUnavailable as exc:
            raise SemanticModelUnavailable(str(exc)) from exc
        return result.value


__all__ = [
    "GatewaySemanticGenerator",
    "GeminiSemanticGenerator",
    "LocalVlmSemanticGenerator",
    "SemanticModelUnavailable",
    "SemanticModelOutputError",
]
