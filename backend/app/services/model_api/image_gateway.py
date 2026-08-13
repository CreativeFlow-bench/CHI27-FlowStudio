"""GPT Image 2 generation and identity-preserving edit boundary.

Gemini native image models (fallback) use v1beta generateContent — OpenAI
`/images/*` rejects them on 128api.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import io
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

from app.services.model_api.config import ModelApiProfile
from app.services.model_api.transport import ModelApiError, ModelTransportUnavailable


class ImageInputError(ModelApiError):
    """The source or mask cannot satisfy the image-edit contract."""


class ImageResponseError(ModelApiError):
    """The API response does not contain a valid PNG result."""


class ImageModelGateway:
    def __init__(
        self,
        profile: ModelApiProfile,
        *,
        open_request: Callable[[urllib.request.Request, float], Any] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.profile = profile
        self._open_request = open_request or self._default_open
        self._sleep = sleep or time.sleep

    async def generate(
        self,
        prompt: str,
        *,
        size: str = "1024x1024",
    ) -> bytes:
        prompt = self._require_prompt(prompt)
        last_error: Exception | None = None
        for model in self.profile.ordered_image_models():
            try:
                if self._is_gemini_native_image(model):
                    raw = await asyncio.to_thread(
                        self._gemini_generate_content,
                        model,
                        [{"text": prompt}],
                    )
                    return self._decode_inline_image(raw)
                payload = {
                    "model": model,
                    "prompt": prompt,
                    "n": 1,
                    "size": size,
                    "output_format": "png",
                }
                raw = await asyncio.to_thread(
                    self._post_json,
                    f"{self.profile.api_base}/images/generations",
                    payload,
                )
                return self._decode_openai_png(raw)
            except (ModelTransportUnavailable, ImageResponseError) as exc:
                last_error = exc
        raise last_error or ModelTransportUnavailable("image API unavailable")

    async def edit(
        self,
        prompt: str,
        source: bytes,
        *,
        mask: bytes | None = None,
        size: str = "1024x1024",
    ) -> bytes:
        prompt = self._require_prompt(prompt)
        source_png, source_size = self._normalize_source(source)
        mask_png = self._normalize_mask(mask, source_size) if mask is not None else None
        last_error: Exception | None = None
        for model in self.profile.ordered_image_models():
            try:
                if self._is_gemini_native_image(model):
                    # Masked OpenAI edits are not mapped 1:1; condition on source.
                    parts: list[dict[str, Any]] = [
                        {
                            "inlineData": {
                                "mimeType": "image/png",
                                "data": base64.b64encode(source_png).decode("ascii"),
                            }
                        },
                        {"text": prompt},
                    ]
                    raw = await asyncio.to_thread(
                        self._gemini_generate_content,
                        model,
                        parts,
                    )
                    return self._decode_inline_image(raw)
                fields = {
                    "model": model,
                    "prompt": prompt,
                    "n": "1",
                    "size": size,
                    "output_format": "png",
                }
                files = [("image", "source.png", "image/png", source_png)]
                if mask_png is not None:
                    files.append(("mask", "mask.png", "image/png", mask_png))
                content_type, body = self._multipart(fields, files)
                raw = await asyncio.to_thread(
                    self._post_bytes,
                    f"{self.profile.api_base}/images/edits",
                    body,
                    content_type,
                )
                return self._decode_openai_png(raw)
            except (ModelTransportUnavailable, ImageResponseError) as exc:
                last_error = exc
        raise last_error or ModelTransportUnavailable("image API unavailable")

    def _gemini_generate_content(
        self,
        model: str,
        parts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        }
        return self._post_json(
            f"{self._api_root()}/v1beta/models/{model}:generateContent",
            payload,
        )

    def _api_root(self) -> str:
        base = self.profile.api_base.rstrip("/")
        return base[:-3] if base.endswith("/v1") else base

    @staticmethod
    def _is_gemini_native_image(model: str) -> bool:
        name = model.lower()
        return name.startswith("gemini-") and "image" in name

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post_bytes(
            url,
            json.dumps(payload).encode("utf-8"),
            "application/json",
        )

    def _post_bytes(self, url: str, body: bytes, content_type: str) -> dict[str, Any]:
        last_error: ModelTransportUnavailable | None = None
        # Image edits are large multipart posts; give them more headroom than text.
        request_timeout = max(float(self.profile.timeout_sec), 120.0)
        for attempt in range(self.profile.max_retries + 1):
            request = urllib.request.Request(
                url,
                data=body,
                headers={
                    "Authorization": f"Bearer {self.profile.api_key}",
                    "Content-Type": content_type,
                },
                method="POST",
            )
            try:
                with self._open_request(request, request_timeout) as response:
                    raw = json.loads(response.read().decode("utf-8"))
                if not isinstance(raw, dict):
                    raise ImageResponseError("image API response must be a JSON object")
                return raw
            except urllib.error.HTTPError as exc:
                response_body = exc.read().decode("utf-8", errors="replace")
                if exc.code == 429 or exc.code == 408 or 500 <= exc.code <= 599:
                    last_error = ModelTransportUnavailable(
                        f"image API HTTP {exc.code}: {response_body[:200]}"
                    )
                else:
                    raise ImageResponseError(
                        f"image API HTTP {exc.code}: {response_body[:200]}"
                    ) from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = ModelTransportUnavailable(
                    f"image API unavailable: {exc}"
                )
            except json.JSONDecodeError as exc:
                raise ImageResponseError("image API returned invalid JSON") from exc
            if attempt < self.profile.max_retries:
                self._sleep(0.5 * (2**attempt))
        raise last_error or ModelTransportUnavailable("image API unavailable")

    @staticmethod
    def _require_prompt(prompt: str) -> str:
        normalized = str(prompt or "").strip()
        if not normalized:
            raise ImageInputError("image prompt is required")
        return normalized

    @staticmethod
    def _normalize_source(source: bytes) -> tuple[bytes, tuple[int, int]]:
        try:
            with Image.open(io.BytesIO(source)) as image:
                image.load()
                normalized = image.convert("RGBA")
                size = normalized.size
                output = io.BytesIO()
                normalized.save(output, format="PNG")
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ImageInputError("source identity image is not a valid image") from exc
        return output.getvalue(), size

    @staticmethod
    def _normalize_mask(mask: bytes, source_size: tuple[int, int]) -> bytes:
        try:
            with Image.open(io.BytesIO(mask)) as image:
                image.load()
                if image.size != source_size:
                    raise ImageInputError(
                        "mask dimensions must match the source image dimensions"
                    )
                if "A" not in image.getbands():
                    raise ImageInputError("mask must contain an alpha channel")
                rgba = image.convert("RGBA")
                alpha_min, _ = rgba.getchannel("A").getextrema()
                if alpha_min >= 255:
                    raise ImageInputError("mask alpha must contain transparent pixels")
                output = io.BytesIO()
                rgba.save(output, format="PNG")
        except ImageInputError:
            raise
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ImageInputError("mask is not a valid image") from exc
        return output.getvalue()

    @staticmethod
    def _multipart(
        fields: dict[str, str],
        files: list[tuple[str, str, str, bytes]],
    ) -> tuple[str, bytes]:
        boundary = f"flowstudio-{uuid4().hex}"
        chunks: list[bytes] = []
        for name, value in fields.items():
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode(),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                    value.encode("utf-8"),
                    b"\r\n",
                ]
            )
        for name, filename, mime_type, content in files:
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode(),
                    (
                        f'Content-Disposition: form-data; name="{name}"; '
                        f'filename="{filename}"\r\n'
                    ).encode(),
                    f"Content-Type: {mime_type}\r\n\r\n".encode(),
                    content,
                    b"\r\n",
                ]
            )
        chunks.append(f"--{boundary}--\r\n".encode())
        return f"multipart/form-data; boundary={boundary}", b"".join(chunks)

    @classmethod
    def _decode_openai_png(cls, response: dict[str, Any]) -> bytes:
        data = response.get("data")
        encoded = (
            data[0].get("b64_json")
            if isinstance(data, list) and data and isinstance(data[0], dict)
            else None
        )
        if not isinstance(encoded, str) or not encoded:
            raise ImageResponseError("image API response omitted data[0].b64_json")
        return cls._bytes_to_png(encoded)

    @classmethod
    def _decode_inline_image(cls, response: dict[str, Any]) -> bytes:
        candidates = response.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise ImageResponseError("gemini image response omitted candidates")
        content = candidates[0].get("content") if isinstance(candidates[0], dict) else None
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list):
            raise ImageResponseError("gemini image response omitted content.parts")
        for part in parts:
            if not isinstance(part, dict):
                continue
            inline = part.get("inlineData") or part.get("inline_data")
            if not isinstance(inline, dict):
                continue
            encoded = inline.get("data")
            if isinstance(encoded, str) and encoded:
                return cls._bytes_to_png(encoded)
        raise ImageResponseError("gemini image response omitted inline image data")

    @staticmethod
    def _bytes_to_png(encoded: str) -> bytes:
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ImageResponseError("image API returned invalid base64") from exc
        try:
            with Image.open(io.BytesIO(decoded)) as image:
                image.load()
                output = io.BytesIO()
                image.save(output, format="PNG")
                return output.getvalue()
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ImageResponseError("image API result is not a valid image") from exc

    # Back-compat alias used by older tests / callers.
    _decode_png = _decode_openai_png

    @staticmethod
    def _default_open(request: urllib.request.Request, timeout: float) -> Any:
        # Bypass system HTTP(S)_PROXY (e.g. local clash) for model API calls —
        # the proxy often stalls large multipart image edits.
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
        )
        return opener.open(request, timeout=timeout)
