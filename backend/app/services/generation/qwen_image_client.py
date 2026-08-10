"""QwenImageClient: direct Qwen-Image generation for the four-stage path.

The Gate-selected option maps to concrete prompts; Qwen-Image is responsible
only for rendering them (strategy doc 9.2). Generation calls stay serialized by
the four-stage GPU scheduler lock held by the caller.
"""

from __future__ import annotations

import asyncio
import json
import ssl
import urllib.error
import urllib.request
from typing import Any

from pathlib import Path

from app.services.model_api.image_gateway import (
    ImageInputError,
    ImageModelGateway,
    ImageResponseError,
)
from app.services.model_api.transport import ModelTransportUnavailable


class QwenImageUnavailable(Exception):
    pass


class QwenImageClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_sec: float = 600,
        width: int = 512,
        height: int = 512,
        steps: int = 4,
        true_cfg_scale: float = 3.5,
        max_sequence_length: int = 256,
    ) -> None:
        self.base_url = (base_url or "http://127.0.0.1:18082").rstrip("/")
        self.timeout_sec = timeout_sec
        self.width = width
        self.height = height
        self.steps = steps
        self.true_cfg_scale = true_cfg_scale
        self.max_sequence_length = max_sequence_length

    async def generate(self, prompt: str, seed: int) -> bytes:
        payload: dict[str, Any] = {
            "prompt": prompt,
            "width": self.width,
            "height": self.height,
            "steps": self.steps,
            "true_cfg_scale": self.true_cfg_scale,
            "max_sequence_length": self.max_sequence_length,
            "seed": int(seed),
        }
        return await asyncio.to_thread(self._post_png, payload)

    async def generate_conditioned(
        self,
        prompt: str,
        seed: int,
        *,
        source_image_path: str,
        mask_image_path: str | None = None,
        strength: float = 0.6,
    ) -> bytes:
        """Generate while conditioning on the source identity.

        The worker exposes separate conditioned and masked endpoints.  Part
        changes use the mask when available; whole-object changes preserve the
        source image without a mask.  The source paths are deliberately
        explicit so a missing identity input cannot silently become a text-only
        generation in the product path.
        """
        payload: dict[str, Any] = {
            "prompt": prompt,
            "width": self.width,
            "height": self.height,
            "steps": self.steps,
            "true_cfg_scale": self.true_cfg_scale,
            "max_sequence_length": self.max_sequence_length,
            "seed": int(seed),
            "source_image_path": source_image_path,
            "strength": max(0.0, min(1.0, float(strength))),
        }
        endpoint = "generate-masked" if mask_image_path else "generate-conditioned"
        if mask_image_path:
            payload["mask_image_path"] = mask_image_path
        return await asyncio.to_thread(self._post_png, payload, endpoint=endpoint)

    def _post_png(self, payload: dict[str, Any], *, endpoint: str = "generate") -> bytes:
        request = urllib.request.Request(
            f"{self.base_url}/{endpoint.lstrip('/')}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._open(request, self.timeout_sec) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise QwenImageUnavailable(f"Qwen-Image HTTP {exc.code}: {body[:200]}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise QwenImageUnavailable(f"Qwen-Image unavailable: {exc}") from exc

    @staticmethod
    def _open(request, timeout: float):
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


class ExternalImageClient:
    """Compatibility-shaped adapter whose active implementation is GPT Image 2."""

    def __init__(self, gateway: ImageModelGateway) -> None:
        self.gateway = gateway

    async def generate(self, prompt: str, seed: int) -> bytes:
        del seed  # GPT Image 2 does not expose a seed parameter.
        try:
            return await self.gateway.generate(prompt)
        except (ModelTransportUnavailable, ImageResponseError) as exc:
            raise QwenImageUnavailable(f"external image API unavailable: {exc}") from exc

    async def generate_conditioned(
        self,
        prompt: str,
        seed: int,
        *,
        source_image_path: str,
        mask_image_path: str | None = None,
        strength: float = 0.6,
    ) -> bytes:
        del seed, strength
        source_path = Path(source_image_path)
        if not source_path.is_file():
            raise ImageInputError("source identity image is required for image editing")
        mask: bytes | None = None
        if mask_image_path:
            mask_path = Path(mask_image_path)
            if not mask_path.is_file():
                raise ImageInputError("mask image path does not exist")
            mask = mask_path.read_bytes()
        try:
            return await self.gateway.edit(
                prompt,
                source_path.read_bytes(),
                mask=mask,
            )
        except (ModelTransportUnavailable, ImageResponseError) as exc:
            raise QwenImageUnavailable(f"external image API unavailable: {exc}") from exc
