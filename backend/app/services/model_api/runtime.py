"""Default external-model runtime composition."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.services.divergence.semantic_model_clients import GatewaySemanticGenerator
from app.services.encoding.qwen_intent_encoder import ExternalIntentEncoder
from app.services.generation.qwen_image_client import ExternalImageClient
from app.services.model_api.config import ModelApiProfile
from app.services.model_api.image_gateway import ImageModelGateway
from app.services.model_api.text_gateway import TextModelGateway
from app.services.model_api.transport import OpenAICompatibleTransport
from app.services.model_api.types import ModelStage
from app.services.rerepresentation.gemini_client import ExternalDecisionClient


@dataclass(frozen=True, slots=True)
class ExternalModelRuntime:
    profile: ModelApiProfile
    text_gateway: TextModelGateway
    intent_encoder: ExternalIntentEncoder
    decision_client: ExternalDecisionClient
    semantic_primary: GatewaySemanticGenerator
    semantic_fallback: GatewaySemanticGenerator
    image_gateway: ImageModelGateway
    image_client: ExternalImageClient


def build_external_model_runtime(
    settings: Settings,
    *,
    audit: Callable[..., None] | None = None,
) -> ExternalModelRuntime:
    profile = ModelApiProfile.from_settings(settings)

    def audit_sink(event: dict[str, Any]) -> None:
        if audit is not None:
            audit(**event)

    transport = OpenAICompatibleTransport(
        api_base=profile.api_base,
        api_key=profile.api_key,
        timeout_sec=profile.timeout_sec,
        max_retries=profile.max_retries,
        audit=audit_sink if audit is not None else None,
    )
    gateway = TextModelGateway(profile, transport=transport)
    image_gateway = ImageModelGateway(profile)
    return ExternalModelRuntime(
        profile=profile,
        text_gateway=gateway,
        intent_encoder=ExternalIntentEncoder(gateway),
        decision_client=ExternalDecisionClient(
            gateway,
            max_images=settings.gemini_max_images,
        ),
        semantic_primary=GatewaySemanticGenerator(
            gateway,
            stage=ModelStage.SEMANTIC_DIVERGENCE,
            model=profile.reasoning_text_model,
            min_candidates=settings.semantic_divergence_min_candidates,
            max_candidates=settings.semantic_divergence_max_candidates,
        ),
        semantic_fallback=GatewaySemanticGenerator(
            gateway,
            stage=ModelStage.PERCEPTION,
            model=profile.fast_text_model,
            min_candidates=settings.semantic_divergence_min_candidates,
            max_candidates=settings.semantic_divergence_max_candidates,
        ),
        image_gateway=image_gateway,
        image_client=ExternalImageClient(image_gateway),
    )
