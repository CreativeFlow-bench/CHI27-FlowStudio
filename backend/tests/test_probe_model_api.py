from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from app.config import Settings
from app.services.model_api.config import ModelApiProfile
from app.services.model_api.text_gateway import StructuredModelResult
from app.services.model_api.types import ModelStage
from scripts.probe_model_api import (
    ProbeCapabilityError,
    ProbeDependencies,
    ProbeOptions,
    execute_probe,
    parse_args,
)


class _Transport:
    def __init__(self, models: list[str]) -> None:
        self.models = models

    async def list_models(self) -> list[str]:
        return list(self.models)


class _TextGateway:
    def __init__(self) -> None:
        self.stages: list[ModelStage] = []

    async def complete_json(self, stage, messages, *, validator, **kwargs):
        self.stages.append(stage)
        model = "gemini-3.6-flash" if stage is ModelStage.INTENT else "gpt-5.5"
        return StructuredModelResult(
            value=validator({"ok": True, "stage": stage.value}),
            model=model,
            provider="gemini" if model.startswith("gemini") else "openai",
            fallback_used=False,
        )


class _ImageGateway:
    def __init__(self, png: bytes) -> None:
        self.png = png
        self.generate_calls = 0
        self.edit_calls = 0

    async def generate(self, prompt: str, **kwargs: Any) -> bytes:
        self.generate_calls += 1
        return self.png

    async def edit(self, prompt: str, source: bytes, **kwargs: Any) -> bytes:
        self.edit_calls += 1
        assert source == self.png
        return self.png


def _deps(models: list[str], png: bytes) -> ProbeDependencies:
    profile = ModelApiProfile.from_settings(
        Settings(
            _env_file=None,
            model_api_base="https://relay.example/v1",
            model_api_key="super-secret-key",
        )
    )
    return ProbeDependencies(
        profile=profile,
        transport=_Transport(models),  # type: ignore[arg-type]
        text_gateway=_TextGateway(),  # type: ignore[arg-type]
        image_gateway=_ImageGateway(png),  # type: ignore[arg-type]
    )


def test_parse_args_keeps_paid_modes_opt_in(tmp_path: Path) -> None:
    options = parse_args(["--list-models", "--output-root", str(tmp_path)])

    assert options.list_models is True
    assert options.run_text is False
    assert options.run_images is False
    assert options.output_root == tmp_path


def test_missing_exact_model_stops_before_paid_calls(tmp_path: Path) -> None:
    deps = _deps(["gemini-3.6-flash", "gpt-5.5"], b"png")

    with pytest.raises(ProbeCapabilityError, match="gpt-image-2"):
        asyncio.run(
            execute_probe(
                ProbeOptions(
                    list_models=True,
                    run_text=True,
                    run_images=True,
                    output_root=tmp_path,
                ),
                deps,
                timestamp="20260810T120000Z",
            )
        )

    assert deps.text_gateway.stages == []  # type: ignore[attr-defined]
    assert deps.image_gateway.generate_calls == 0  # type: ignore[attr-defined]


def test_probe_writes_redacted_text_and_image_artifacts(tmp_path: Path) -> None:
    png = b"\x89PNG\r\n\x1a\nfixture"
    deps = _deps(["gemini-3.6-flash", "gpt-5.5", "gpt-image-2"], png)

    output_dir = asyncio.run(
        execute_probe(
            ProbeOptions(
                list_models=True,
                run_text=True,
                run_images=True,
                output_root=tmp_path,
            ),
            deps,
            timestamp="20260810T120000Z",
        )
    )

    assert output_dir == tmp_path / "20260810T120000Z"
    manifest = json.loads((output_dir / "manifest.json").read_text())
    serialized = json.dumps(manifest)
    assert "super-secret-key" not in serialized
    assert manifest["models"]["fast_text"] == "gemini-3.6-flash"
    assert manifest["models"]["reasoning_text"] == "gpt-5.5"
    assert manifest["models"]["image"] == "gpt-image-2"
    assert (output_dir / "gemini.json").is_file()
    assert (output_dir / "gpt-5.5.json").is_file()
    assert (output_dir / "generated.png").read_bytes() == png
    assert (output_dir / "edited.png").read_bytes() == png
    assert deps.text_gateway.stages == [  # type: ignore[attr-defined]
        ModelStage.INTENT,
        ModelStage.PROMPT_COMPOSITION,
    ]
    assert deps.image_gateway.generate_calls == 1  # type: ignore[attr-defined]
    assert deps.image_gateway.edit_calls == 1  # type: ignore[attr-defined]
