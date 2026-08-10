from __future__ import annotations

import asyncio
import io
import json
import urllib.error
from collections.abc import Callable
from typing import Any

import pytest

from app.config import Settings
from app.services.model_api.config import ModelApiProfile
from app.services.model_api.text_gateway import TextModelGateway
from app.services.model_api.transport import (
    ModelHttpError,
    ModelTransportUnavailable,
    OpenAICompatibleTransport,
)
from app.services.model_api.types import ModelStage


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._body = json.dumps(payload).encode("utf-8")
        self.status = 200

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def _http_error(status: int, body: str = "failure") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="https://relay.example/v1/chat/completions",
        code=status,
        msg=body,
        hdrs=None,
        fp=io.BytesIO(body.encode("utf-8")),
    )


class _RecordingTransport:
    def __init__(self, replies: list[dict[str, Any] | Exception]) -> None:
        self.replies = list(replies)
        self.models: list[str] = []

    async def chat_json(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        stage: ModelStage,
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        self.models.append(model)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _profile() -> ModelApiProfile:
    return ModelApiProfile.from_settings(
        Settings(
            _env_file=None,
            model_api_base="https://relay.example/v1",
            model_api_key="secret-key",
        )
    )


def test_fast_stage_uses_gemini_then_gpt_on_transport_failure() -> None:
    transport = _RecordingTransport(
        [ModelTransportUnavailable("timeout"), {"intent": "observe"}]
    )
    gateway = TextModelGateway(_profile(), transport=transport)

    result = asyncio.run(
        gateway.complete_json(
            ModelStage.INTENT,
            [{"role": "user", "content": "observe"}],
            validator=lambda value: value["intent"],
        )
    )

    assert result.value == "observe"
    assert result.model == "gpt-5.5"
    assert result.fallback_used is True
    assert transport.models == ["gemini-3.6-flash", "gpt-5.5"]


def test_reasoning_stage_uses_gpt_then_gemini_on_transport_failure() -> None:
    transport = _RecordingTransport(
        [ModelTransportUnavailable("503"), {"decision": "refine"}]
    )
    gateway = TextModelGateway(_profile(), transport=transport)

    result = asyncio.run(
        gateway.complete_json(
            ModelStage.REREPRESENTATION,
            [{"role": "user", "content": "decide"}],
            validator=lambda value: value["decision"],
        )
    )

    assert result.value == "refine"
    assert result.model == "gemini-3.6-flash"
    assert result.fallback_used is True
    assert transport.models == ["gpt-5.5", "gemini-3.6-flash"]


def test_transport_retries_429_but_not_terminal_400() -> None:
    attempts: list[str] = []
    responses: list[object] = [
        _http_error(429),
        _Response(
            {
                "choices": [
                    {"message": {"content": '{"ok": true}'}}
                ]
            }
        ),
    ]

    def open_request(request: object, timeout: float) -> object:
        attempts.append(getattr(request, "full_url"))
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    transport = OpenAICompatibleTransport(
        api_base="https://relay.example/v1",
        api_key="secret-key",
        timeout_sec=1,
        max_retries=2,
        open_request=open_request,
        sleep=lambda _: None,
    )

    result = asyncio.run(
        transport.chat_json(
            model="gemini-3.6-flash",
            messages=[{"role": "user", "content": "hi"}],
            stage=ModelStage.INTENT,
            temperature=0,
            max_tokens=32,
        )
    )
    assert result == {"ok": True}
    assert len(attempts) == 2

    terminal_attempts = 0

    def terminal_open(request: object, timeout: float) -> object:
        nonlocal terminal_attempts
        terminal_attempts += 1
        raise _http_error(400, "invalid request")

    terminal = OpenAICompatibleTransport(
        api_base="https://relay.example/v1",
        api_key="secret-key",
        timeout_sec=1,
        max_retries=2,
        open_request=terminal_open,
        sleep=lambda _: None,
    )
    with pytest.raises(ModelHttpError):
        asyncio.run(
            terminal.chat_json(
                model="gpt-5.5",
                messages=[{"role": "user", "content": "hi"}],
                stage=ModelStage.REREPRESENTATION,
                temperature=0,
                max_tokens=32,
            )
        )
    assert terminal_attempts == 1


@pytest.mark.parametrize(
    "content",
    [
        '```json\n{"answer": 7}\n```',
        'Result follows: {"answer": 7}',
    ],
)
def test_transport_extracts_json_from_wrapped_chat_content(content: str) -> None:
    transport = OpenAICompatibleTransport(
        api_base="https://relay.example/v1",
        api_key="secret-key",
        open_request=lambda request, timeout: _Response(
            {"choices": [{"message": {"content": content}}]}
        ),
        sleep=lambda _: None,
    )

    result = asyncio.run(
        transport.chat_json(
            model="gemini-3.6-flash",
            messages=[{"role": "user", "content": "answer"}],
            stage=ModelStage.PERCEPTION,
            temperature=0,
            max_tokens=32,
        )
    )

    assert result == {"answer": 7}


def test_transport_lists_exact_available_model_ids() -> None:
    transport = OpenAICompatibleTransport(
        api_base="https://relay.example/v1",
        api_key="secret-key",
        open_request=lambda request, timeout: _Response(
            {"data": [{"id": "gemini-3.6-flash"}, {"id": "gpt-5.5"}]}
        ),
        sleep=lambda _: None,
    )

    assert asyncio.run(transport.list_models()) == [
        "gemini-3.6-flash",
        "gpt-5.5",
    ]


def test_structured_call_performs_only_one_schema_repair() -> None:
    transport = _RecordingTransport(
        [{"answer": "wrong"}, {"answer": "still-wrong"}]
    )
    gateway = TextModelGateway(_profile(), transport=transport)

    def validate(value: dict[str, Any]) -> int:
        if not isinstance(value.get("answer"), int):
            raise ValueError("answer must be an integer")
        return value["answer"]

    with pytest.raises(ValueError, match="answer must be an integer"):
        asyncio.run(
            gateway.complete_json(
                ModelStage.PROMPT_COMPOSITION,
                [{"role": "user", "content": "answer"}],
                validator=validate,
                repair_instruction="Return answer as an integer.",
            )
        )

    assert transport.models == ["gpt-5.5", "gpt-5.5"]


def test_audit_metadata_never_contains_key_or_message_content() -> None:
    events: list[dict[str, Any]] = []
    transport = OpenAICompatibleTransport(
        api_base="https://relay.example/v1",
        api_key="top-secret-key",
        open_request=lambda request, timeout: _Response(
            {
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3},
            }
        ),
        sleep=lambda _: None,
        audit=events.append,
    )

    asyncio.run(
        transport.chat_json(
            model="gemini-3.6-flash",
            messages=[
                {
                    "role": "user",
                    "content": "data:image/png;base64,SENSITIVE_IMAGE_BYTES",
                }
            ],
            stage=ModelStage.PERCEPTION,
            temperature=0,
            max_tokens=32,
        )
    )

    serialized = json.dumps(events)
    assert "top-secret-key" not in serialized
    assert "SENSITIVE_IMAGE_BYTES" not in serialized
    assert events[-1]["model"] == "gemini-3.6-flash"
    assert events[-1]["prompt_tokens"] == 12
