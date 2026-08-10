from __future__ import annotations

import asyncio
import base64
import io
import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from app.config import Settings
from app.services.generation.qwen_image_client import ExternalImageClient
from app.services.model_api.config import ModelApiProfile
from app.services.model_api.image_gateway import (
    ImageInputError,
    ImageModelGateway,
    ImageResponseError,
)


def _png(
    size: tuple[int, int] = (4, 4),
    *,
    mode: str = "RGBA",
    alpha: int = 255,
    add_transparency: bool = True,
) -> bytes:
    color: tuple[int, ...] = (220, 230, 240, alpha) if mode == "RGBA" else (220, 230, 240)
    image = Image.new(mode, size, color)
    if mode == "RGBA" and alpha == 255 and add_transparency:
        image.putpixel((0, 0), (220, 230, 240, 0))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class _Response:
    def __init__(self, image_bytes: bytes | None = None, *, payload: dict[str, Any] | None = None) -> None:
        self._payload = payload or {
            "data": [{"b64_json": base64.b64encode(image_bytes or _png()).decode("ascii")}]
        }

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def _gateway(open_request) -> ImageModelGateway:
    profile = ModelApiProfile.from_settings(
        Settings(
            _env_file=None,
            model_api_base="https://relay.example/v1",
            model_api_key="secret-key",
        )
    )
    return ImageModelGateway(profile, open_request=open_request, sleep=lambda _: None)


def test_explicit_text_generation_posts_gpt_image_2_json() -> None:
    captured: dict[str, Any] = {}

    def open_request(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _Response()

    result = asyncio.run(
        _gateway(open_request).generate(
            "A cute snowman with a yellow knitted hat.",
            size="1024x1024",
        )
    )

    assert result.startswith(b"\x89PNG\r\n\x1a\n")
    assert captured["url"].endswith("/images/generations")
    assert captured["payload"] == {
        "model": "gpt-image-2",
        "prompt": "A cute snowman with a yellow knitted hat.",
        "n": 1,
        "size": "1024x1024",
        "output_format": "png",
    }


def test_whole_edit_posts_source_image_as_multipart() -> None:
    captured: dict[str, Any] = {}

    def open_request(request, timeout):
        captured["url"] = request.full_url
        captured["content_type"] = request.headers["Content-type"]
        captured["body"] = request.data
        return _Response()

    result = asyncio.run(
        _gateway(open_request).edit(
            "Keep this snowman's identity and make its torso rounder.",
            _png(),
        )
    )

    assert result.startswith(b"\x89PNG")
    assert captured["url"].endswith("/images/edits")
    assert captured["content_type"].startswith("multipart/form-data; boundary=")
    assert b'name="model"' in captured["body"]
    assert b"gpt-image-2" in captured["body"]
    assert b'name="image"; filename="source.png"' in captured["body"]
    assert b'name="mask"' not in captured["body"]


def test_region_edit_posts_same_size_alpha_mask() -> None:
    captured: dict[str, Any] = {}

    def open_request(request, timeout):
        captured["body"] = request.data
        return _Response()

    result = asyncio.run(
        _gateway(open_request).edit(
            "Change only the scarf while preserving everything else.",
            _png(),
            mask=_png(alpha=0),
        )
    )

    assert result.startswith(b"\x89PNG")
    assert b'name="image"; filename="source.png"' in captured["body"]
    assert b'name="mask"; filename="mask.png"' in captured["body"]


def test_mask_must_match_source_dimensions_and_contain_transparency() -> None:
    gateway = _gateway(lambda request, timeout: pytest.fail("network must not be called"))

    with pytest.raises(ImageInputError, match="dimensions"):
        asyncio.run(gateway.edit("edit", _png((4, 4)), mask=_png((3, 4), alpha=0)))

    with pytest.raises(ImageInputError, match="alpha"):
        asyncio.run(gateway.edit("edit", _png(), mask=_png(mode="RGB")))

    with pytest.raises(ImageInputError, match="transparent"):
        asyncio.run(
            gateway.edit(
                "edit",
                _png(),
                mask=_png(alpha=255, add_transparency=False),
            )
        )


def test_response_must_contain_decodable_png() -> None:
    invalid_b64 = _gateway(
        lambda request, timeout: _Response(payload={"data": [{"b64_json": "not-base64"}]})
    )
    with pytest.raises(ImageResponseError, match="base64"):
        asyncio.run(invalid_b64.generate("snowman"))

    invalid_image = _gateway(lambda request, timeout: _Response(b"not-an-image"))
    with pytest.raises(ImageResponseError, match="image"):
        asyncio.run(invalid_image.generate("snowman"))


def test_conditioned_product_path_never_falls_back_to_text_generation(tmp_path: Path) -> None:
    class RecordingGateway:
        def __init__(self) -> None:
            self.generate_calls = 0
            self.edit_calls = 0

        async def generate(self, *args: Any, **kwargs: Any) -> bytes:
            self.generate_calls += 1
            return _png()

        async def edit(self, *args: Any, **kwargs: Any) -> bytes:
            self.edit_calls += 1
            return _png()

    gateway = RecordingGateway()
    client = ExternalImageClient(gateway)  # type: ignore[arg-type]

    with pytest.raises(ImageInputError, match="source identity image"):
        asyncio.run(
            client.generate_conditioned(
                "make it cuter",
                42,
                source_image_path=str(tmp_path / "missing.png"),
            )
        )

    assert gateway.generate_calls == 0
    assert gateway.edit_calls == 0
