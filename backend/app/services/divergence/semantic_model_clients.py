"""OpenAI-compatible generators for post-Gate semantic divergence."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from pydantic import ValidationError

from app.models import KnowledgeEvidence, SemanticCandidate, SemanticDivergenceRequest
from app.services.model_api.text_gateway import TextModelGateway
from app.services.model_api.transport import ModelHttpError, ModelTransportUnavailable
from app.services.model_api.types import ModelStage


_SYSTEM_PROMPT = """You are FlowStudio's semantic-divergence generator.
Return a JSON object whose candidates field follows the exact count and group quotas in
the response schema. Each display_label_zh
must be 2–8个字, not a complete sentence. Mix lengths in every group: some 2–4字 everyday
words a designer can picture at a glance (绒帽, 金缝, 扎染, 波点, 编织), plus some 5–7字
specific phrases (针织红帽, 荧光接缝). Do not pad every label to 6–8 stacked compounds
such as 分形切面多彩体 or 像素方块矩阵. Never use Aesthetic, Structural, Functional,
Cross-domain, shape, connection, material, surface, silhouette, or ornament as a label.
Each item must contain group, target_ref, operation, semantic_anchor, prompt_phrase,
attribute_delta, and scores. candidate_id must be unique; label_en is required. group must
be exactly one of shape, connection, surface, semantic_transfer. scores must contain exactly
identity, scope, relevance, specificity, and novelty as numbers from 0 to 1. Preserve object identity and strictly stay within the Gate
target and scope. Knowledge evidence is an optional donor; do not copy source titles or
invent provenance. For scope material_region, target_ref.type must be material_region
and target_ref.id must equal semantic_target.mask_ref, falling back to part_id only when
mask_ref is absent. Keep field values terse and return no Markdown fences. Use concrete
directions such as 鳄鱼压纹 or 珍珠光泽; reject generic labels such as 纹理变化, 调整,
优化, 建议, or 测试."""

DEFAULT_SEMANTIC_DIVERGENCE_SYSTEM_PROMPT = _SYSTEM_PROMPT


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
        max_candidates: int = 32,
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
        *,
        system_prompt: str | None = None,
    ) -> list[SemanticCandidate]:
        import asyncio

        return await asyncio.to_thread(
            self.generate_sync, request, evidence, system_prompt=system_prompt
        )

    def generate_sync(
        self,
        request: SemanticDivergenceRequest,
        evidence: KnowledgeEvidence,
        *,
        system_prompt: str | None = None,
    ) -> list[SemanticCandidate]:
        if not self.configured:
            raise SemanticModelUnavailable("semantic model endpoint or model is not configured")
        try:
            parsed, errors = self._request_and_parse(
                self.build_payload(request, evidence, system_prompt=system_prompt),
                evidence,
                request,
            )
        except SemanticModelOutputError as exc:
            parsed, errors = None, [{"msg": str(exc)}]
        if parsed is not None:
            return parsed
        try:
            repaired, repair_errors = self._request_and_parse(
                self.build_payload(
                    request,
                    evidence,
                    repair_errors=errors,
                    system_prompt=system_prompt,
                ),
                evidence,
                request,
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
        system_prompt: str | None = None,
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
        candidate_count = request.candidate_count
        per_group_count = request.params.per_group_count
        group_quotas = (
            {
                "shape": per_group_count,
                "connection": per_group_count,
                "surface": per_group_count,
                "semantic_transfer": per_group_count,
            }
            if per_group_count is not None
            else None
        )
        user_content: dict[str, Any] = {
            "request": request_payload,
            "knowledge_evidence": evidence.model_dump(mode="json"),
            "response_schema": {
                "candidates": [
                    {
                        "candidate_id": "unique_short_id",
                        "display_label_zh": "短词或短语，如绒帽/彩虹灯串",
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
                "candidate_count": candidate_count,
                **({"group_quotas": group_quotas} if group_quotas is not None else {}),
                "requirements": [
                    f"Return exactly {candidate_count} candidates and keep every text field concise.",
                    "Mix short (2–4字) and longer (5–7字) display_label_zh in each group; keep labels concrete and easy to read.",
                    "Return only the JSON object; do not rename keys.",
                    (
                        f"Return exactly {per_group_count} candidates in each of shape, connection, surface, and semantic_transfer."
                        if per_group_count is not None
                        else "Use at least two relevant groups; at high temperature include at least two semantic_transfer items."
                    ),
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
                {
                    "role": "system",
                    "content": (system_prompt or DEFAULT_SEMANTIC_DIVERGENCE_SYSTEM_PROMPT).strip()
                    or DEFAULT_SEMANTIC_DIVERGENCE_SYSTEM_PROMPT,
                },
                {"role": "user", "content": json.dumps(user_content, ensure_ascii=False)},
            ],
            "temperature": request.params.model_temperature,
            "max_tokens": min(12800, max(3600, candidate_count * 400)),
            "response_format": {"type": "json_object"},
        }

    def _request_and_parse(
        self,
        payload: dict[str, Any],
        evidence: KnowledgeEvidence,
        request: SemanticDivergenceRequest,
    ) -> tuple[list[SemanticCandidate] | None, list[dict[str, Any]]]:
        try:
            return self._parse_candidates(self._post_json(payload), evidence, request)
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
        self,
        raw: Any,
        evidence: KnowledgeEvidence,
        request: SemanticDivergenceRequest,
    ) -> tuple[list[SemanticCandidate] | None, list[dict[str, Any]]]:
        if not isinstance(raw, dict) or not isinstance(raw.get("candidates"), list):
            return None, [{"msg": "model did not return a JSON object with candidates"}]
        candidate_data = raw["candidates"]
        if (
            not self.min_candidates <= len(candidate_data) <= self.max_candidates
            or len(candidate_data) != request.candidate_count
        ):
            return None, [
                {
                    "loc": ["candidates"],
                    "msg": f"expected exactly {request.candidate_count} candidates",
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
            parsed = [
                SemanticCandidate.model_validate({**candidate, "provenance": provenance})
                for candidate in normalized_candidates
            ]
        except ValidationError as exc:
            return None, [
                {"loc": list(error.get("loc", [])), "msg": error.get("msg", "invalid")}
                for error in exc.errors()
            ]
        per_group_count = request.params.per_group_count
        if per_group_count is not None:
            group_counts = {
                group: sum(candidate.group == group for candidate in parsed)
                for group in ("shape", "connection", "surface", "semantic_transfer")
            }
            quota_errors = [
                {
                    "loc": ["candidates", group],
                    "msg": f"expected exactly {per_group_count} {group} candidates; got {count}",
                }
                for group, count in group_counts.items()
                if count != per_group_count
            ]
            if quota_errors:
                return None, quota_errors
        return parsed, []


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
        call_timeout_sec: float | None = None,
        max_retries: int = 1,
    ) -> None:
        super().__init__(
            gateway.profile.api_base,
            api_key=gateway.profile.api_key,
            model=model,
            timeout_sec=call_timeout_sec or gateway.profile.timeout_sec,
            min_candidates=min_candidates,
            max_candidates=max_candidates,
        )
        self.gateway = gateway
        self.stage = stage
        self.call_timeout_sec = call_timeout_sec or gateway.profile.timeout_sec
        self.max_retries = max(0, max_retries)
        self.last_used_model: str | None = None

    async def generate(
        self,
        request: SemanticDivergenceRequest,
        evidence: KnowledgeEvidence,
        *,
        system_prompt: str | None = None,
    ) -> list[SemanticCandidate]:
        if not self.configured:
            raise SemanticModelUnavailable("external model API is not configured")
        payload = self.build_payload(request, evidence, system_prompt=system_prompt)
        candidate_count = int(getattr(request, "candidate_count", None) or 20)
        max_tokens = min(12800, max(3600, candidate_count * 400))

        def validate(raw: dict[str, Any]) -> list[SemanticCandidate]:
            parsed, errors = self._parse_candidates(raw, evidence, request)
            if parsed is None:
                raise SemanticModelOutputError(
                    f"semantic candidate validation failed: {errors[:3]}"
                )
            return parsed

        try:
            # Pin self.model — service-layer fallback owns spare models.
            # Do not let stage route silently try gpt-5.5 inside primary_call.
            result = await self.gateway.complete_json(
                self.stage,
                payload["messages"],
                validator=validate,
                repair_instruction=(
                    "Return the same semantic candidates JSON corrected to "
                    "satisfy the reported validation error."
                ),
                temperature=request.params.model_temperature,
                max_tokens=max_tokens,
                models=[self.model],
                timeout_sec=self.call_timeout_sec,
                max_retries=self.max_retries,
                allow_repair=True,
            )
        except (ModelTransportUnavailable, ModelHttpError) as exc:
            raise SemanticModelUnavailable(str(exc)) from exc
        self.last_used_model = result.model
        return result.value


__all__ = [
    "DEFAULT_SEMANTIC_DIVERGENCE_SYSTEM_PROMPT",
    "GatewaySemanticGenerator",
    "GeminiSemanticGenerator",
    "LocalVlmSemanticGenerator",
    "SemanticModelUnavailable",
    "SemanticModelOutputError",
]
