"""Lightweight connectivity probe for cloud text/image models."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from app.services.model_api.runtime import ExternalModelRuntime


async def probe_external_models(
    runtime: ExternalModelRuntime,
    *,
    include_image: bool = True,
) -> dict[str, Any]:
    profile = runtime.profile
    configured = bool(profile.api_base and profile.api_key)
    payload: dict[str, Any] = {
        "ok": False,
        "configured": configured,
        "api_base": profile.api_base,
        "legacy_local_models": profile.enable_legacy_local_models,
        "text": {
            "ok": False,
            "model": profile.fast_text_model,
            "latency_ms": None,
            "error": None,
        },
        "image": {
            "ok": False,
            "model": profile.image_model,
            "latency_ms": None,
            "bytes": 0,
            "error": None,
            "skipped": not include_image,
        },
        "hint": None,
    }
    if not configured:
        payload["hint"] = (
            "MODEL_API_BASE / MODEL_API_KEY 未配置。"
            "可先启用本地模型（ENABLE_LEGACY_LOCAL_MODELS）或补齐密钥后再测。"
        )
        return payload

    transport = runtime.text_gateway.transport
    text_started = time.monotonic()
    try:
        raw = await asyncio.to_thread(
            transport._request_json,
            f"{profile.api_base}/chat/completions",
            method="POST",
            payload={
                "model": profile.fast_text_model,
                "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
                "max_tokens": 8,
                "temperature": 0,
            },
            timeout_sec=min(30.0, profile.timeout_sec),
        )
        content = ""
        try:
            content = str(
                (((raw.get("choices") or [{}])[0].get("message") or {}).get("content"))
                or ""
            )
        except Exception:
            content = ""
        payload["text"]["ok"] = bool(content.strip() or raw.get("choices"))
        if not payload["text"]["ok"]:
            payload["text"]["error"] = "empty chat response"
    except Exception as exc:
        payload["text"]["error"] = str(exc)[:240]
    payload["text"]["latency_ms"] = int((time.monotonic() - text_started) * 1000)

    if include_image:
        image_started = time.monotonic()
        try:
            png = await runtime.image_gateway.generate(
                "tiny red square on white background",
                size="1024x1024",
            )
            payload["image"]["ok"] = bool(png and png[:8] == b"\x89PNG\r\n\x1a\n")
            payload["image"]["bytes"] = len(png or b"")
            if not payload["image"]["ok"]:
                payload["image"]["error"] = "response was not a PNG"
        except Exception as exc:
            payload["image"]["error"] = str(exc)[:240]
        payload["image"]["latency_ms"] = int((time.monotonic() - image_started) * 1000)

    payload["ok"] = bool(payload["text"]["ok"]) and (
        True if payload["image"]["skipped"] else bool(payload["image"]["ok"])
    )
    if not payload["ok"] and not payload["hint"]:
        if not payload["text"]["ok"] and (
            payload["image"]["skipped"] or payload["image"]["ok"]
        ):
            failed = "text"
        elif payload["text"]["ok"]:
            failed = "image"
        else:
            failed = "text+image"
        payload["hint"] = _hint_for_failure(profile.enable_legacy_local_models, failed)
    return payload


def _hint_for_failure(legacy_local: bool, which: str) -> str:
    if legacy_local:
        return (
            f"{which} 云端联通失败；本地遗留模型开关已开，可先等本地服务起来再试，"
            "或检查 MODEL_API_BASE / 额度。"
        )
    return (
        f"{which} 云端联通失败。可稍后再测、检查密钥/额度，"
        "或临时打开 ENABLE_LEGACY_LOCAL_MODELS 切本地部署模型。"
    )
