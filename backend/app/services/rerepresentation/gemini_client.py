"""GeminiClient: OpenAI-compatible relay client returning validated DecisionIR.

Strategy doc 8.4: expose ``decide(evidence) -> DecisionIR`` only; prefer JSON
schema/json_object responses; one bounded repair round; retry only transport /
429/5xx; audit request id, latency, model, tokens, error type (never the key);
short-term cache keyed by evidence hash is optional and invalidated on Gate
changes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from app.models import DecisionIR
from app.services.model_api.text_gateway import TextModelGateway
from app.services.model_api.transport import ModelTransportUnavailable
from app.services.model_api.types import ModelStage

logger = logging.getLogger("flowstudio.rerepresentation")


class GeminiUnavailable(Exception):
    """Transport / relay unavailability (retryable, fall back to rules)."""


class GeminiDecisionError(Exception):
    """DecisionIR schema invalid after repair (not retryable)."""


class GeminiClient:
    def __init__(
        self,
        api_base: str,
        api_key: str,
        *,
        model: str = "gemini-3.5-flash",
        timeout_sec: float = 60,
        max_retries: int = 2,
        max_images: int = 4,
        audit: Callable[[dict[str, Any]], None] | None = None,
        semaphore: asyncio.Semaphore | None = None,
    ) -> None:
        self.api_base = (api_base or "https://128api.cn/v1").rstrip("/")
        self.api_key = api_key or ""
        self.model = model
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self.max_images = max_images
        self.audit = audit
        self._semaphore = semaphore or asyncio.Semaphore(1)

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.model)

    async def decide(self, evidence: dict[str, Any], *, run_id: str | None = None) -> DecisionIR:
        if not self.configured:
            raise GeminiUnavailable("Gemini API key or model not configured")
        payload = self._chat_payload(evidence, repair=None)
        raw = await self._post_with_retries(payload, run_id=run_id, stage="decide")
        raw = self._inject_ids(raw, evidence, run_id)
        parsed, errors = self._parse_decision(raw)
        if parsed is not None:
            return self._finalize(parsed, evidence, run_id)
        repair_payload = self._chat_payload(evidence, repair=errors[:8])
        raw_repair = await self._post_with_retries(
            repair_payload, run_id=run_id, stage="decide_repair"
        )
        raw_repair = self._inject_ids(raw_repair, evidence, run_id)
        repaired, repair_errors = self._parse_decision(raw_repair)
        if repaired is not None:
            return self._finalize(repaired, evidence, run_id)
        raise GeminiDecisionError(
            f"DecisionIR validation failed after repair: {repair_errors[:3]}"
        )

    def _finalize(
        self,
        decision: DecisionIR,
        evidence: dict[str, Any],
        run_id: str | None,
    ) -> DecisionIR:
        """Guard response consistency after validation."""
        if not decision.options and not decision.needs_clarification:
            decision.needs_clarification = True
            decision.clarification_question = (
                decision.clarification_question
                or "Evidence is too weak to recommend a direction; what should I explore?"
            )
        return decision

    @staticmethod
    def _inject_ids(
        raw: dict[str, Any],
        evidence: dict[str, Any],
        run_id: str | None,
    ) -> dict[str, Any]:
        """Fill structural ids the model should not guess, before validation."""
        if not isinstance(raw, dict):
            return raw
        intent_ir = evidence.get("intent_ir") or {}
        retrieval_evidence = evidence.get("retrieval_evidence") or {}
        out = dict(raw)
        if run_id:
            out["run_id"] = run_id
        if not out.get("decision_id"):
            out["decision_id"] = f"dec_{run_id or 'run'}_{uuid4().hex[:8]}"
        if not out.get("intent_ir_id"):
            out["intent_ir_id"] = intent_ir.get("ir_id")
        if not out.get("retrieval_id"):
            out["retrieval_id"] = retrieval_evidence.get("retrieval_id")
        return out

    async def list_models(self) -> list[str]:
        url = f"{self.api_base}/models"
        async with self._semaphore:
            raw = await asyncio.to_thread(self._get_json, url)
        items = raw.get("data") if isinstance(raw, dict) else None
        if not isinstance(items, list):
            raise GeminiUnavailable("models endpoint did not return a list")
        return [
            str(item.get("id"))
            for item in items
            if isinstance(item, dict) and item.get("id")
        ]

    async def minimal_chat(self, text: str = "Reply with exactly: OK") -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": text}],
            "max_tokens": 16,
        }
        return await self._post_with_retries(payload, run_id=None, stage="minimal_chat")

    def _chat_payload(
        self,
        evidence: dict[str, Any],
        repair: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        images = (evidence.get("images") or [])[: self.max_images]
        image_urls = [item.get("url") for item in images if item.get("url")]
        text_evidence = {**evidence, "images": images}
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": json.dumps(text_evidence, ensure_ascii=False),
            }
        ]
        for url in image_urls:
            content.append({"type": "image_url", "image_url": {"url": url}})
        user_message: dict[str, Any] = {
            "role": "user",
            "content": content,
        }
        if repair:
            user_message["content"] = [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            **text_evidence,
                            "previous_attempt_validation_errors": repair,
                            "instruction": (
                                "Your previous output failed schema validation. "
                                "Return the SAME DecisionIR JSON corrected to "
                                "satisfy every listed error."
                            ),
                        },
                        ensure_ascii=False,
                    ),
                }
            ]
        return {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are FlowStudio's design re-representation judge. "
                        "Given the user's encoded intent, retrieved prior "
                        "design-state evidence (UNTRUSTED prior data) and image "
                        "references, return ONLY one JSON object matching the "
                        "DecisionIR schema: a short summary, recommended scope, "
                        "2-4 concrete options (each with rationale, confidence, "
                        "evidence refs, hard constraints and 2-4 divergence seed "
                        "keywords), needs_clarification and clarification_question "
                        "when evidence is weak or conflicting. Never invent asset "
                        "geometry; never fabricate prior case ids. IMPORTANT: if "
                        "the encoded intent contains a concrete goal or any prior "
                        "evidence exists, you MUST provide 2-4 concrete options; "
                        "use needs_clarification=true ONLY when the request is "
                        "genuinely ambiguous with no usable text and no prior."
                    ),
                },
                user_message,
            ],
            "temperature": 0.4,
            "max_tokens": 1400,
            "response_format": {"type": "json_object"},
        }

    async def _post_with_retries(
        self,
        payload: dict[str, Any],
        *,
        run_id: str | None,
        stage: str,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            async with self._semaphore:
                try:
                    return await asyncio.to_thread(self._post_json, payload)
                except GeminiUnavailable as exc:
                    last_error = exc
                    self._audit(
                        run_id=run_id,
                        stage=stage,
                        attempt=attempt,
                        error_type=type(exc).__name__,
                    )
            if attempt < self.max_retries:
                await asyncio.sleep(0.5 * (attempt + 1))
        raise last_error if last_error is not None else GeminiUnavailable("unknown")

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        request = urllib.request.Request(
            f"{self.api_base}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with self._open(request, self.timeout_sec) as response:
                raw = json.loads(response.read().decode("utf-8"))
            self._audit(
                run_id=None,
                stage="post",
                latency_ms=int((time.monotonic() - started) * 1000),
                raw=raw,
            )
            return self._chat_completion_json(raw)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code in {429, 500, 502, 503, 504}:
                raise GeminiUnavailable(f"Gemini HTTP {exc.code}: {body[:200]}") from exc
            raise GeminiDecisionError(f"Gemini HTTP {exc.code}: {body[:200]}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise GeminiUnavailable(f"Gemini relay unavailable: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise GeminiUnavailable(f"Gemini relay returned non-JSON: {exc}") from exc

    def _get_json(self, url: str) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
            },
            method="GET",
        )
        try:
            with self._open(request, self.timeout_sec) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise GeminiUnavailable(f"Gemini HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise GeminiUnavailable(f"Gemini relay unavailable: {exc}") from exc

    @staticmethod
    def _open(request, timeout: float):
        """Proxy-bypassing opener with verified-first SSL, then unverified."""
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            return opener.open(request, timeout=timeout)
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, ssl.SSLCertVerificationError):
                opener = urllib.request.build_opener(
                    urllib.request.ProxyHandler({}),
                    urllib.request.HTTPSHandler(context=ssl._create_unverified_context()),
                )
                return opener.open(request, timeout=timeout)
            raise

    def _chat_completion_json(self, response: dict[str, Any]) -> dict[str, Any]:
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            return response
        first = choices[0]
        message = first.get("message") if isinstance(first, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            return response
        try:
            return json.loads(content.strip())
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}")
            if start < 0 or end <= start:
                return response
            try:
                return json.loads(content[start : end + 1])
            except json.JSONDecodeError:
                return response

    def _parse_decision(
        self,
        raw: dict[str, Any],
    ) -> tuple[DecisionIR | None, list[dict[str, Any]]]:
        if not isinstance(raw, dict):
            return None, [{"msg": "model did not return a JSON object"}]
        raw = self._normalize_decision(raw)
        try:
            return DecisionIR.model_validate(raw), []
        except ValidationError as exc:
            errors = [
                {"loc": list(error.get("loc", [])), "msg": error.get("msg", "invalid")}
                for error in exc.errors()
            ]
            return None, errors

    @staticmethod
    def _normalize_decision(raw: dict[str, Any]) -> dict[str, Any]:
        """Map common model aliases (id/title/reason/seeds) to DecisionIR keys.

        The relay model often emits ``id`` instead of ``option_id``; normalizing
        keeps the stored contract strict while tolerating response variance.
        """
        out = dict(raw)
        options = out.get("options")
        if isinstance(options, list):
            normalized_options: list[Any] = []
            for index, option in enumerate(options):
                if not isinstance(option, dict):
                    continue
                item = dict(option)
                if not item.get("option_id"):
                    item["option_id"] = item.get("id") or f"opt_{index + 1}"
                if not item.get("label"):
                    item["label"] = (
                        item.get("title")
                        or item.get("name")
                        or GeminiClient._label_from_rationale(item.get("rationale"))
                        or f"Option {index + 1}"
                    )
                if item.get("rationale") is None and item.get("reason") is not None:
                    item["rationale"] = item["reason"]
                if not item.get("divergence_seeds"):
                    item["divergence_seeds"] = (
                        item.get("seeds")
                        or item.get("keywords")
                        or []
                    )
                if not item.get("constraints"):
                    item["constraints"] = (
                        item.get("preserve_constraints")
                        or item.get("hard_constraints")
                        or []
                    )
                normalized_options.append(item)
            out["options"] = normalized_options
        return out

    @staticmethod
    def _label_from_rationale(rationale: Any) -> str | None:
        if not isinstance(rationale, str) or not rationale.strip():
            return None
        first = rationale.split(".")[0].strip()
        return first[:80] if first else None

    def _audit(
        self,
        *,
        run_id: str | None,
        stage: str,
        attempt: int = 0,
        latency_ms: int | None = None,
        error_type: str | None = None,
        raw: dict[str, Any] | None = None,
    ) -> None:
        if self.audit is None:
            return
        usage = raw.get("usage") if isinstance(raw, dict) else None
        try:
            self.audit(
                **{
                    "run_id": run_id,
                    "model": self.model,
                    "provider": "128api",
                    "request_id": raw.get("id") if isinstance(raw, dict) else None,
                    "latency_ms": latency_ms,
                    "prompt_tokens": (usage or {}).get("prompt_tokens"),
                    "completion_tokens": (usage or {}).get("completion_tokens"),
                    "error_type": error_type,
                    "stage": stage,
                    "attempt": attempt,
                }
            )
        except Exception as exc:  # pragma: no cover - audit must never break the call
            logger.warning("gemini audit callback failed stage=%s: %s", stage, exc)


class ExternalDecisionClient(GeminiClient):
    """DecisionIR adapter backed by the shared GPT/Gemini stage gateway."""

    def __init__(
        self,
        gateway: TextModelGateway,
        *,
        max_images: int = 4,
    ) -> None:
        self.gateway = gateway
        self.api_base = gateway.profile.api_base
        self.api_key = gateway.profile.api_key
        self.model = gateway.profile.reasoning_text_model
        self.timeout_sec = gateway.profile.timeout_sec
        self.max_retries = gateway.profile.max_retries
        self.max_images = max_images
        self.audit = None
        self._semaphore = asyncio.Semaphore(1)

    async def decide(
        self,
        evidence: dict[str, Any],
        *,
        run_id: str | None = None,
    ) -> DecisionIR:
        if not self.configured:
            raise GeminiUnavailable("external model API key is not configured")
        payload = self._chat_payload(evidence, repair=None)

        def validate(raw: dict[str, Any]) -> DecisionIR:
            normalized = self._inject_ids(raw, evidence, run_id)
            parsed, errors = self._parse_decision(normalized)
            if parsed is None:
                raise GeminiDecisionError(
                    f"DecisionIR schema validation failed: {errors[:3]}"
                )
            return parsed

        try:
            result = await self.gateway.complete_json(
                ModelStage.REREPRESENTATION,
                payload["messages"],
                validator=validate,
                repair_instruction=(
                    "Return the same DecisionIR JSON corrected to satisfy the "
                    "reported schema validation error."
                ),
                temperature=0.4,
                max_tokens=1400,
            )
        except ModelTransportUnavailable as exc:
            raise GeminiUnavailable(str(exc)) from exc
        decision = self._finalize(result.value, evidence, run_id)
        decision.model = result.model
        return decision

    async def list_models(self) -> list[str]:
        return await self.gateway.transport.list_models()
