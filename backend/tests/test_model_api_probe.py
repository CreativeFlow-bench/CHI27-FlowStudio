from __future__ import annotations

import asyncio

from app.services.model_api.config import ModelApiProfile
from app.services.model_api.probe import probe_external_models
from app.services.model_api.runtime import ExternalModelRuntime
from app.services.model_api.text_gateway import TextModelGateway
from app.services.model_api.image_gateway import ImageModelGateway


class _FakeTransport:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def _request_json(self, url, *, method, payload, timeout_sec=None):
        if self.fail:
            raise RuntimeError("text down")
        return {
            "choices": [{"message": {"content": "OK"}}],
        }


class _FakeImage:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.profile = ModelApiProfile(
            api_base="https://example.test/v1",
            api_key="k",
            fast_text_model="gemini-3.6-flash",
            reasoning_text_model="gemini-3.6-flash",
            semantic_fallback_model="gemini-3.6-flash",
            image_model="gpt-image-2",
            timeout_sec=30,
            max_retries=0,
            enable_legacy_local_models=False,
            enable_3d_generation=False,
        )

    async def generate(self, prompt: str, *, size: str = "1024x1024") -> bytes:
        if self.fail:
            raise RuntimeError("image down")
        return b"\x89PNG\r\n\x1a\n" + b"0" * 16


def _runtime(*, text_fail=False, image_fail=False) -> ExternalModelRuntime:
    profile = ModelApiProfile(
        api_base="https://example.test/v1",
        api_key="k",
        fast_text_model="gemini-3.6-flash",
        reasoning_text_model="gemini-3.6-flash",
        semantic_fallback_model="gemini-3.6-flash",
        image_model="gpt-image-2",
        timeout_sec=30,
        max_retries=0,
        enable_legacy_local_models=False,
        enable_3d_generation=False,
    )
    text = TextModelGateway(profile, transport=_FakeTransport(fail=text_fail))
    image = _FakeImage(fail=image_fail)
    return ExternalModelRuntime(
        profile=profile,
        text_gateway=text,
        intent_encoder=None,  # type: ignore[arg-type]
        decision_client=None,  # type: ignore[arg-type]
        semantic_primary=None,  # type: ignore[arg-type]
        semantic_fallback=None,  # type: ignore[arg-type]
        image_gateway=image,  # type: ignore[arg-type]
        image_client=None,  # type: ignore[arg-type]
        interaction_predictor=None,  # type: ignore[arg-type]
    )


def test_probe_text_and_image_ok() -> None:
    result = asyncio.run(probe_external_models(_runtime(), include_image=True))
    assert result["ok"] is True
    assert result["text"]["ok"] is True
    assert result["image"]["ok"] is True


def test_probe_image_skipped() -> None:
    result = asyncio.run(probe_external_models(_runtime(), include_image=False))
    assert result["ok"] is True
    assert result["image"]["skipped"] is True


def test_probe_text_failure_sets_hint() -> None:
    result = asyncio.run(probe_external_models(_runtime(text_fail=True), include_image=False))
    assert result["ok"] is False
    assert result["hint"]
