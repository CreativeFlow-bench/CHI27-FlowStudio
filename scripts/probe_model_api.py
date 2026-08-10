#!/usr/bin/env python3
"""Bounded, opt-in external model capability and output probe."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[1]
_BACKEND_ROOT = _REPO_ROOT / "backend"
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.config import Settings  # noqa: E402
from app.services.model_api.config import ModelApiProfile  # noqa: E402
from app.services.model_api.image_gateway import ImageModelGateway  # noqa: E402
from app.services.model_api.text_gateway import TextModelGateway  # noqa: E402
from app.services.model_api.transport import OpenAICompatibleTransport  # noqa: E402
from app.services.model_api.types import ModelStage  # noqa: E402


class ProbeCapabilityError(RuntimeError):
    """The relay does not advertise an exact approved model id."""


@dataclass(frozen=True, slots=True)
class ProbeOptions:
    list_models: bool
    run_text: bool
    run_images: bool
    output_root: Path


@dataclass(frozen=True, slots=True)
class ProbeDependencies:
    profile: ModelApiProfile
    transport: OpenAICompatibleTransport
    text_gateway: TextModelGateway
    image_gateway: ImageModelGateway


def parse_args(argv: Sequence[str] | None = None) -> ProbeOptions:
    parser = argparse.ArgumentParser(
        description="Verify exact FlowStudio external model capabilities and outputs."
    )
    parser.add_argument("--list-models", action="store_true")
    parser.add_argument("--text-only", action="store_true")
    parser.add_argument("--with-images", action="store_true")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=_REPO_ROOT / "outputs" / "api_model_eval",
    )
    values = parser.parse_args(argv)
    run_images = bool(values.with_images)
    run_text = bool(values.text_only or run_images)
    return ProbeOptions(
        list_models=True,
        run_text=run_text,
        run_images=run_images,
        output_root=values.output_root,
    )


def build_dependencies(settings: Settings | None = None) -> ProbeDependencies:
    profile = ModelApiProfile.from_settings(settings or Settings())
    transport = OpenAICompatibleTransport(
        api_base=profile.api_base,
        api_key=profile.api_key,
        timeout_sec=profile.timeout_sec,
        max_retries=profile.max_retries,
    )
    return ProbeDependencies(
        profile=profile,
        transport=transport,
        text_gateway=TextModelGateway(profile, transport=transport),
        image_gateway=ImageModelGateway(profile),
    )


async def execute_probe(
    options: ProbeOptions,
    dependencies: ProbeDependencies,
    *,
    timestamp: str | None = None,
) -> Path:
    profile = dependencies.profile
    if not profile.api_key:
        raise ProbeCapabilityError("MODEL_API_KEY/GEMINI_API_KEY is not configured")

    available_models = await dependencies.transport.list_models()
    required: list[str] = []
    if options.run_text:
        required.extend([profile.fast_text_model, profile.reasoning_text_model])
    if options.run_images:
        required.append(profile.image_model)
    missing = [model for model in dict.fromkeys(required) if model not in available_models]
    if missing:
        raise ProbeCapabilityError(
            "relay does not advertise exact required model id(s): " + ", ".join(missing)
        )

    stamp = timestamp or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_dir = options.output_root / stamp
    output_dir.mkdir(parents=True, exist_ok=False)
    manifest: dict[str, Any] = {
        "timestamp": stamp,
        "api_base": profile.api_base,
        "credential_configured": bool(profile.api_key),
        "available_models": available_models,
        "models": {
            "fast_text": profile.fast_text_model,
            "reasoning_text": profile.reasoning_text_model,
            "image": profile.image_model,
        },
        "legacy_local_models": False,
        "3d_generation": False,
        "probes": {},
    }

    if options.run_text:
        gemini_result = await dependencies.text_gateway.complete_json(
            ModelStage.INTENT,
            [
                {
                    "role": "system",
                    "content": "Return only a compact JSON object.",
                },
                {
                    "role": "user",
                    "content": (
                        "Return {\"ok\": true, \"purpose\": "
                        "\"flowstudio_fast_probe\"}."
                    ),
                },
            ],
            validator=_require_object,
            repair_instruction="Return one valid JSON object.",
            max_tokens=80,
        )
        _write_json(output_dir / "gemini.json", gemini_result.value)
        manifest["probes"]["gemini"] = {
            "ok": True,
            "model": gemini_result.model,
            "provider": gemini_result.provider,
            "fallback_used": gemini_result.fallback_used,
        }

        gpt_result = await dependencies.text_gateway.complete_json(
            ModelStage.PROMPT_COMPOSITION,
            [
                {
                    "role": "system",
                    "content": "Return only a compact JSON object.",
                },
                {
                    "role": "user",
                    "content": (
                        "Return {\"ok\": true, \"purpose\": "
                        "\"flowstudio_reasoning_probe\"}."
                    ),
                },
            ],
            validator=_require_object,
            repair_instruction="Return one valid JSON object.",
            max_tokens=80,
        )
        _write_json(output_dir / "gpt-5.5.json", gpt_result.value)
        manifest["probes"]["gpt-5.5"] = {
            "ok": True,
            "model": gpt_result.model,
            "provider": gpt_result.provider,
            "fallback_used": gpt_result.fallback_used,
        }

    if options.run_images:
        generated = await dependencies.image_gateway.generate(
            (
                "A single cute white snowman product-design concept on a clean "
                "white studio background, front three-quarter view, yellow knitted "
                "hat, colorful scarf, centered, no text."
            )
        )
        (output_dir / "generated.png").write_bytes(generated)
        edited = await dependencies.image_gateway.edit(
            (
                "Preserve the exact same snowman identity, pose, camera, hat, scarf, "
                "and white background. Make only the torso slightly rounder and softer."
            ),
            generated,
        )
        (output_dir / "edited.png").write_bytes(edited)
        manifest["probes"]["gpt-image-2"] = {
            "ok": True,
            "model": profile.image_model,
            "generated_file": "generated.png",
            "edited_file": "edited.png",
        }

    _write_json(output_dir / "manifest.json", manifest)
    return output_dir


def _require_object(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        raise ValueError("model response must be a non-empty JSON object")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    options = parse_args(argv)
    try:
        output_dir = asyncio.run(execute_probe(options, build_dependencies()))
    except ProbeCapabilityError as exc:
        print(f"CAPABILITY_MISMATCH: {exc}", file=sys.stderr)
        return 2
    print(f"Model probe artifacts: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
