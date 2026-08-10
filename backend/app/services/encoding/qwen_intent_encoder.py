"""QwenIntentEncoder: OpenAI-compatible Qwen3 HTTP boundary for IntentIR JSON.

Contract (strategy doc 6.2):
- system prompt requires a single IntentIR JSON object;
- temperature 0 for encoding stability;
- one JSON repair round with validation errors, then fail (no fabricated IR);
- bounded request size, single-machine semaphore, timeout + bounded retries,
  no raw image/base64 content ever logged.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import ssl
import urllib.error
import urllib.request
from typing import Any

from pydantic import ValidationError

from app.models import IntentIR
from app.services.encoding.event_normalizer import NormalizedEventBundle
from app.services.model_api.text_gateway import TextModelGateway
from app.services.model_api.transport import ModelTransportUnavailable
from app.services.model_api.types import ModelStage

logger = logging.getLogger("flowstudio.encoding")


class QwenEncodingError(Exception):
    """IntentIR validation failed after the repair round (not retryable)."""


class QwenUnavailable(Exception):
    """Transport / model unavailability (retryable, fall back to rules)."""


class QwenIntentEncoder:
    MAX_IMAGE_REFS = 2
    MAX_IMAGE_BYTES = 2_500_000

    def __init__(
        self,
        endpoint_url: str | None,
        *,
        model_name: str = "qwen3-planner",
        timeout_sec: float = 60,
        max_retries: int = 2,
        temperature: float = 0.0,
        max_request_bytes: int = 64_000,
        semaphore: asyncio.Semaphore | None = None,
    ) -> None:
        self.endpoint_url = (endpoint_url or "").rstrip("/")
        self.model_name = model_name
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self.temperature = temperature
        self.max_request_bytes = max_request_bytes
        self._semaphore = semaphore or asyncio.Semaphore(1)

    @property
    def configured(self) -> bool:
        return bool(self.endpoint_url)

    async def encode(self, bundle: NormalizedEventBundle) -> IntentIR:
        if not self.configured:
            raise QwenUnavailable("no encoding endpoint configured")
        image_parts = await self._image_parts(bundle.image_refs)
        payload = self._chat_payload(bundle, repair=None, image_parts=image_parts)
        raw = await self._post_with_retries(payload)
        parsed, errors = self._parse_intent_ir(raw)
        if parsed is not None:
            return parsed
        # One bounded repair round: send only the validation errors back.
        repair_payload = self._chat_payload(bundle, repair=errors[:8], image_parts=image_parts)
        raw_repair = await self._post_with_retries(repair_payload)
        repaired, repair_errors = self._parse_intent_ir(raw_repair)
        if repaired is not None:
            return repaired
        raise QwenEncodingError(
            f"intent-ir validation failed after repair: {repair_errors[:3]}"
        )

    async def _image_parts(self, image_refs: list[str]) -> list[dict[str, Any]]:
        """Fetch up to MAX_IMAGE_REFS bounded images and return OpenAI image parts.

        Images are best-effort: any failure (fetch, size, decode) skips that ref
        so a broken reference can never block intent encoding.
        """
        parts: list[dict[str, Any]] = []
        for ref in (image_refs or [])[: self.MAX_IMAGE_REFS]:
            if not isinstance(ref, str) or not ref.startswith(("http://", "https://", "data:")):
                continue
            try:
                if ref.startswith("data:"):
                    data_url = ref
                else:
                    body = await asyncio.to_thread(self._fetch_bounded, ref)
                    if body is None or len(body) > self.MAX_IMAGE_BYTES:
                        continue
                    data_url = "data:image/png;base64," + base64.b64encode(body).decode("ascii")
                parts.append({"type": "image_url", "image_url": {"url": data_url}})
            except Exception:  # pragma: no cover - images are best-effort
                logger.warning("intent image ref skipped: %s", ref[:80], exc_info=True)
        return parts

    def _fetch_bounded(self, url: str) -> bytes | None:
        with urllib.request.urlopen(url, timeout=12) as response:
            return response.read(self.MAX_IMAGE_BYTES + 1)

    def _chat_payload(
        self,
        bundle: NormalizedEventBundle,
        repair: list[dict[str, Any]] | None,
        image_parts: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        user_content: dict[str, Any] = {
            "task": "intent_ir_encoding",
            "instructions": (
                "Encode the normalized interaction bundle into a single IntentIR "
                "JSON object. If the bundle is viewport-only observation with no "
                "text or selection, use operation 'observe'. Otherwise infer the "
                "generation operation (e.g. 'explore_variations'), scope "
                "('whole'/'part'/'region'), goal, constraints and preferred_axes. "
                "Do not invent specific 3D geometry; keep target fields null when "
                "unknown."
            ),
            "bundle": bundle.to_bounded_json(),
            "response_schema": {
                "schema_version": "flowstudio.intent-ir.v1",
                "ir_id": "generated",
                "run_id": "from bundle context",
                "session_id": "from bundle context",
                "source_event_ids": ["list of event ids"],
                "target": {"asset_id": "or null", "object_type": "or null", "part_id": "or null", "region": "or null"},
                "observations": {
                    "viewport": "bounded summary",
                    "interaction_summary": {"tools": ["brush"], "count": 1, "summary": "brief"},
                    "text": "user text or null",
                    "image_refs": [],
                    "model_refs": [],
                },
                "intent": {
                    "operation": "observe|explore_variations|refine|...",
                    "scope": "whole|part|region",
                    "goal": "short goal",
                    "constraints": ["hard constraints"],
                    "preferred_axes": ["Aesthetic", "Structural", "Functional"],
                },
                "hypotheses": [],
                "confidence": "0..1",
                "ambiguity": "0..1",
                "provenance": {"encoder": self.model_name, "encoder_version": self.model_name, "prompt_version": "intent-ir-v1", "fallback_used": False},
                "created_at": "ISO-8601",
            },
        }
        if repair:
            user_content["previous_attempt_validation_errors"] = repair
            user_content["instruction"] = (
                "Your previous output failed schema validation. Return the SAME "
                "IntentIR JSON, corrected to satisfy every listed error."
            )
        user_content_parts: list[dict[str, Any]] = [
            {"type": "text", "text": json.dumps(user_content, ensure_ascii=False)}
        ]
        user_content_parts.extend(image_parts or [])
        messages = [
            {
                "role": "system",
                "content": (
                    "You are FlowStudio's intent encoder. Return ONLY one JSON "
                    "object conforming exactly to the IntentIR schema in the user "
                    "message. No markdown, no prose, no code fences."
                ),
            },
            {"role": "user", "content": user_content_parts},
        ]
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": 900,
            "response_format": {"type": "json_object"},
        }
        size = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        if size > self.max_request_bytes:
            raise QwenEncodingError(
                f"encoding request exceeds {self.max_request_bytes} bytes ({size})"
            )
        return payload

    async def _post_with_retries(self, payload: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            async with self._semaphore:
                try:
                    return await asyncio.to_thread(self._post_json, payload)
                except QwenUnavailable as exc:
                    last_error = exc
            if attempt < self.max_retries:
                await asyncio.sleep(0.4 * (attempt + 1))
        raise last_error if last_error is not None else QwenUnavailable("unknown")

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            self.endpoint_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._open(request, self.timeout_sec) as response:
                raw = json.loads(response.read().decode("utf-8"))
                return self._chat_completion_json(raw)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code in {429, 500, 502, 503, 504}:
                raise QwenUnavailable(f"Qwen HTTP {exc.code}: {body[:200]}") from exc
            raise QwenEncodingError(f"Qwen HTTP {exc.code}: {body[:200]}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise QwenUnavailable(f"Qwen endpoint unavailable: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise QwenUnavailable(f"Qwen endpoint returned non-JSON: {exc}") from exc

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

    def _parse_intent_ir(
        self, raw: dict[str, Any]
    ) -> tuple[IntentIR | None, list[dict[str, Any]]]:
        if not isinstance(raw, dict):
            return None, [{"msg": "model did not return a JSON object"}]
        try:
            return IntentIR.model_validate(raw), []
        except ValidationError as exc:
            errors = [
                {
                    "loc": list(error.get("loc", [])),
                    "msg": error.get("msg", "invalid"),
                }
                for error in exc.errors()
            ]
            return None, errors


class ExternalIntentEncoder(QwenIntentEncoder):
    """IntentIR adapter using the shared external-model gateway.

    It inherits only the established prompt/image-bounding helpers.  The
    legacy Qwen transport remains available on ``QwenIntentEncoder`` and is
    not constructed by the default runtime.
    """

    def __init__(
        self,
        gateway: TextModelGateway,
        *,
        max_request_bytes: int = 64_000,
        semaphore: asyncio.Semaphore | None = None,
    ) -> None:
        self.gateway = gateway
        self.endpoint_url = ""
        self.model_name = gateway.profile.fast_text_model
        self.timeout_sec = gateway.profile.timeout_sec
        self.max_retries = gateway.profile.max_retries
        self.temperature = 0.0
        self.max_request_bytes = max_request_bytes
        self._semaphore = semaphore or asyncio.Semaphore(1)

    @property
    def configured(self) -> bool:
        return bool(self.gateway.profile.api_key)

    async def encode(self, bundle: NormalizedEventBundle) -> IntentIR:
        if not self.configured:
            raise QwenUnavailable("external model API key is not configured")
        image_parts = await self._image_parts(bundle.image_refs)
        payload = self._chat_payload(bundle, repair=None, image_parts=image_parts)
        try:
            result = await self.gateway.complete_json(
                ModelStage.INTENT,
                payload["messages"],
                validator=IntentIR.model_validate,
                repair_instruction=(
                    "Return the same IntentIR JSON corrected to satisfy the "
                    "reported schema validation error."
                ),
                temperature=self.temperature,
                max_tokens=900,
            )
        except ModelTransportUnavailable as exc:
            raise QwenUnavailable(str(exc)) from exc
        except ValidationError as exc:
            raise QwenEncodingError(
                f"intent-ir validation failed after repair: {exc.errors()[:3]}"
            ) from exc
        return result.value
