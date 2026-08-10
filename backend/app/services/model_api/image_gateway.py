"""GPT Image 2 generation and identity-preserving edit boundary."""

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
        payload = {
            "model": self.profile.image_model,
            "prompt": self._require_prompt(prompt),
            "n": 1,
            "size": size,
            "output_format": "png",
        }
        raw = await asyncio.to_thread(
            self._post_json,
            f"{self.profile.api_base}/images/generations",
            payload,
        )
        return self._decode_png(raw)

    async def edit(
        self,
        prompt: str,
        source: bytes,
        *,
        mask: bytes | None = None,
        size: str = "1024x1024",
    ) -> bytes:
        source_png, source_size = self._normalize_source(source)
        mask_png = self._normalize_mask(mask, source_size) if mask is not None else None
        fields = {
            "model": self.profile.image_model,
            "prompt": self._require_prompt(prompt),
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
        return self._decode_png(raw)

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post_bytes(
            url,
            json.dumps(payload).encode("utf-8"),
            "application/json",
        )

    def _post_bytes(self, url: str, body: bytes, content_type: str) -> dict[str, Any]:
        last_error: ModelTransportUnavailable | None = None
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
                with self._open_request(request, self.profile.timeout_sec) as response:
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

    @staticmethod
    def _decode_png(response: dict[str, Any]) -> bytes:
        data = response.get("data")
        encoded = (
            data[0].get("b64_json")
            if isinstance(data, list) and data and isinstance(data[0], dict)
            else None
        )
        if not isinstance(encoded, str) or not encoded:
            raise ImageResponseError("image API response omitted data[0].b64_json")
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ImageResponseError("image API returned invalid base64") from exc
        try:
            with Image.open(io.BytesIO(decoded)) as image:
                image.load()
                if image.format != "PNG":
                    raise ImageResponseError("image API result is not a PNG image")
        except ImageResponseError:
            raise
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ImageResponseError("image API result is not a valid image") from exc
        return decoded

    @staticmethod
    def _default_open(request: urllib.request.Request, timeout: float) -> Any:
        return urllib.request.urlopen(request, timeout=timeout)
