from __future__ import annotations

from app.config import Settings
from app.services.model_api.config import ModelApiProfile
from app.services.model_api.types import ModelStage


def test_neutral_credentials_override_compatibility_credentials() -> None:
    settings = Settings(
        _env_file=None,
        model_api_base="https://neutral.example/v1/",
        model_api_key="neutral-secret",
        gemini_api_base="https://compat.example/v1",
        gemini_api_key="compat-secret",
    )

    profile = ModelApiProfile.from_settings(settings)

    assert profile.api_base == "https://neutral.example/v1"
    assert profile.api_key == "neutral-secret"


def test_existing_gemini_credentials_are_a_compatibility_fallback() -> None:
    settings = Settings(
        _env_file=None,
        model_api_base=None,
        model_api_key=None,
        gemini_api_base="https://compat.example/v1/",
        gemini_api_key="compat-secret",
    )

    profile = ModelApiProfile.from_settings(settings)

    assert profile.api_base == "https://compat.example/v1"
    assert profile.api_key == "compat-secret"


def test_runtime_profile_keeps_legacy_models_and_3d_off_by_default() -> None:
    profile = ModelApiProfile.from_settings(Settings(_env_file=None))

    assert profile.enable_legacy_local_models is False
    assert profile.enable_3d_generation is False


def test_stage_routing_matches_the_approved_external_models() -> None:
    profile = ModelApiProfile.from_settings(Settings(_env_file=None))

    for stage in (ModelStage.INTENT, ModelStage.PERCEPTION, ModelStage.SEMANTIC_DIVERGENCE):
        route = profile.route_for(stage)
        assert route.primary_model == "gemini-3.6-flash"
        assert route.fallback_model == "gpt-5.5"

    for stage in (
        ModelStage.REREPRESENTATION,
        ModelStage.PROMPT_COMPOSITION,
    ):
        route = profile.route_for(stage)
        assert route.primary_model == "gpt-5.5"
        assert route.fallback_model == "gemini-3.6-flash"

    image_route = profile.route_for(ModelStage.IMAGE)
    assert image_route.primary_model == "gpt-image-2"
    assert image_route.fallback_model is None
    assert profile.ordered_image_models() == [
        "gpt-image-2",
        "grok-imagine-image-lite",
        "gemini-3.6-flash-image",
        "gemini-3.1-flash-image",
    ]
