"""Shared OpenAI-compatible HTTP transport for external model calls."""

from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from app.services.model_api.types import ModelStage


class ModelApiError(Exception):
    """Base error raised by the external model boundary."""


class ModelTransportUnavailable(ModelApiError):
    """A retryable timeout, connection, rate-limit, or server failure."""


class ModelHttpError(ModelApiError):
    """A terminal HTTP or response-contract failure."""


OpenRequest = Callable[[urllib.request.Request, float], Any]
AuditSink = Callable[[dict[str, Any]], None]


class OpenAICompatibleTransport:
    """Small authenticated JSON transport with bounded retry and safe audit data."""

    def __init__(
        self,
        *,
        api_base: str,
        api_key: str,
        timeout_sec: float = 60,
        max_retries: int = 2,
        open_request: OpenRequest | None = None,
        sleep: Callable[[float], None] | None = None,
        audit: AuditSink | None = None,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.timeout_sec = timeout_sec
        self.max_retries = max(0, max_retries)
        self._open_request = open_request or self._default_open
        self._sleep = sleep or time.sleep
        self._audit_sink = audit

    async def chat_json(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        stage: ModelStage,
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._chat_json_sync,
            model=model,
            messages=messages,
            stage=stage,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _chat_json_sync(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        stage: ModelStage,
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        request_id = uuid4().hex
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        last_error: ModelTransportUnavailable | None = None
        for attempt in range(self.max_retries + 1):
            started = time.monotonic()
            try:
                response = self._request_json(
                    f"{self.api_base}/chat/completions",
                    method="POST",
                    payload=payload,
                )
                result = self.extract_json(response)
                usage = response.get("usage") if isinstance(response, dict) else {}
                self._audit(
                    request_id=request_id,
                    stage=stage.value,
                    model=model,
                    attempt=attempt,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    status="ok",
                    prompt_tokens=(usage or {}).get("prompt_tokens"),
                    completion_tokens=(usage or {}).get("completion_tokens"),
                )
                return result
            except ModelTransportUnavailable as exc:
                last_error = exc
                self._audit(
                    request_id=request_id,
                    stage=stage.value,
                    model=model,
                    attempt=attempt,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    status="retryable_error",
                    error_type=type(exc).__name__,
                )
                if attempt < self.max_retries:
                    self._sleep(0.25 * (2**attempt))
        raise last_error or ModelTransportUnavailable("model transport unavailable")

    async def list_models(self) -> list[str]:
        raw = await asyncio.to_thread(
            self._request_json,
            f"{self.api_base}/models",
            method="GET",
            payload=None,
        )
        items = raw.get("data") if isinstance(raw, dict) else None
        if not isinstance(items, list):
            raise ModelHttpError("models endpoint did not return a data list")
        return [
            str(item["id"])
            for item in items
            if isinstance(item, dict) and item.get("id")
        ]

    def _request_json(
        self,
        url: str,
        *,
        method: str,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self._open_request(request, self.timeout_sec) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code == 429 or exc.code == 408 or 500 <= exc.code <= 599:
                raise ModelTransportUnavailable(
                    f"model API HTTP {exc.code}: {body[:200]}"
                ) from exc
            raise ModelHttpError(f"model API HTTP {exc.code}: {body[:200]}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ModelTransportUnavailable(f"model API unavailable: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ModelHttpError("model API returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise ModelHttpError("model API response must be a JSON object")
        return decoded

    @staticmethod
    def extract_json(response: dict[str, Any]) -> dict[str, Any]:
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            return response
        first = choices[0]
        message = first.get("message") if isinstance(first, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, dict):
            return content
        if not isinstance(content, str):
            raise ModelHttpError("chat completion did not contain text or JSON content")
        normalized = content.strip()
        if normalized.startswith("```"):
            first_newline = normalized.find("\n")
            normalized = normalized[first_newline + 1 :] if first_newline >= 0 else ""
            if normalized.endswith("```"):
                normalized = normalized[:-3].rstrip()
        try:
            parsed = json.loads(normalized)
        except json.JSONDecodeError:
            start = normalized.find("{")
            end = normalized.rfind("}")
            if start < 0 or end <= start:
                raise ModelHttpError("chat completion did not contain a JSON object")
            try:
                parsed = json.loads(normalized[start : end + 1])
            except json.JSONDecodeError as exc:
                raise ModelHttpError("chat completion contained invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise ModelHttpError("chat completion JSON must be an object")
        return parsed

    @staticmethod
    def _default_open(request: urllib.request.Request, timeout: float) -> Any:
        return urllib.request.urlopen(request, timeout=timeout)

    def _audit(self, **event: Any) -> None:
        if self._audit_sink is not None:
            self._audit_sink(event)
