"""Resolved external-model configuration and approved stage routing."""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.services.model_api.types import ModelRoute, ModelStage

# OpenAI /images/* rejects these; ImageModelGateway routes them via Gemini
# v1beta generateContent instead.
IMAGE_FALLBACK_MODELS = (
    "gemini-3.1-flash-image",
    "gemini-3-pro-image-2k",
)


@dataclass(frozen=True, slots=True)
class ModelApiProfile:
    api_base: str
    api_key: str
    fast_text_model: str
    reasoning_text_model: str
    semantic_fallback_model: str
    image_model: str
    timeout_sec: float
    max_retries: int
    enable_legacy_local_models: bool
    enable_3d_generation: bool

    @classmethod
    def from_settings(cls, settings: Settings) -> "ModelApiProfile":
        api_base = settings.model_api_base or settings.gemini_api_base
        api_key = settings.model_api_key or settings.gemini_api_key
        return cls(
            api_base=api_base.rstrip("/"),
            api_key=api_key or "",
            fast_text_model=settings.model_fast_text,
            reasoning_text_model=settings.model_reasoning_text,
            semantic_fallback_model=settings.model_semantic_fallback,
            image_model=settings.model_image,
            timeout_sec=settings.model_api_timeout_sec,
            max_retries=settings.model_api_max_retries,
            enable_legacy_local_models=settings.enable_legacy_local_models,
            enable_3d_generation=settings.enable_3d_generation,
        )

    def route_for(self, stage: ModelStage) -> ModelRoute:
        if stage is ModelStage.IMAGE:
            return ModelRoute(self.image_model, None)
        if stage is ModelStage.PHENOMENON:
            return ModelRoute(self.fast_text_model, None)
        # Agile text stages: fast primary, reasoning only as spare.
        if stage in {
            ModelStage.INTENT,
            ModelStage.PERCEPTION,
            ModelStage.SEMANTIC_DIVERGENCE,
        }:
            return ModelRoute(self.fast_text_model, self.reasoning_text_model)
        return ModelRoute(self.reasoning_text_model, self.fast_text_model)

    def ordered_text_models(self, stage: ModelStage, *, extras: list[str] | None = None) -> list[str]:
        """Primary → configured fallbacks → optional extras, de-duplicated."""
        route = self.route_for(stage)
        ordered: list[str] = []
        for model in [
            route.primary_model,
            route.fallback_model,
            self.semantic_fallback_model,
            self.fast_text_model,
            self.reasoning_text_model,
            *(extras or []),
        ]:
            name = str(model or "").strip()
            if name and name not in ordered:
                ordered.append(name)
        return ordered

    def ordered_image_models(self, *, extras: list[str] | None = None) -> list[str]:
        """Primary image model → extras → built-in Gemini image fallbacks."""
        ordered: list[str] = []
        for model in [self.image_model, *(extras or []), *IMAGE_FALLBACK_MODELS]:
            name = str(model or "").strip()
            if name and name not in ordered:
                ordered.append(name)
        return ordered
