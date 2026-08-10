from __future__ import annotations

import asyncio
from typing import Any

from app.config import Settings
from app.models import (
    IntentIR,
    KnowledgeEvidence,
    KnowledgeRoute,
    SemanticDivergenceParams,
    SemanticDivergenceRequest,
)
from app.models.semantic_divergence import SemanticTarget
from app.services.divergence.semantic_model_clients import GatewaySemanticGenerator
from app.services.encoding.event_normalizer import EventNormalizer
from app.services.encoding.qwen_intent_encoder import ExternalIntentEncoder
from app.services.model_api.runtime import build_external_model_runtime
from app.services.model_api.config import ModelApiProfile
from app.services.model_api.text_gateway import StructuredModelResult
from app.services.model_api.types import ModelStage
from app.services.rerepresentation.gemini_client import ExternalDecisionClient


class _Gateway:
    def __init__(self, payload: dict[str, Any], model: str) -> None:
        self.payload = payload
        self.model = model
        self.stages: list[ModelStage] = []
        self.profile = ModelApiProfile.from_settings(
            Settings(
                _env_file=None,
                model_api_base="https://relay.example/v1",
                model_api_key="secret-key",
            )
        )

    async def complete_json(
        self,
        stage: ModelStage,
        messages: list[dict[str, Any]],
        *,
        validator,
        **_: Any,
    ) -> StructuredModelResult[Any]:
        self.stages.append(stage)
        return StructuredModelResult(
            value=validator(dict(self.payload)),
            model=self.model,
            provider="openai" if self.model.startswith("gpt") else "gemini",
            fallback_used=False,
        )


def _intent_payload() -> dict[str, Any]:
    return {
        "schema_version": "flowstudio.intent-ir.v1",
        "ir_id": "ir_external",
        "run_id": "run_external",
        "session_id": "session_external",
        "source_event_ids": ["evt_1"],
        "target": {"asset_id": "asset_1", "object_type": "snowman"},
        "observations": {"text": "make it cuter"},
        "intent": {
            "operation": "explore_variations",
            "scope": "whole",
            "goal": "make it cuter",
        },
        "confidence": 0.9,
        "ambiguity": 0.1,
        "provenance": {"encoder": "gemini-3.6-flash", "fallback_used": False},
    }


def _semantic_request() -> SemanticDivergenceRequest:
    return SemanticDivergenceRequest(
        run_id="run_1",
        decision_id="decision_1",
        session_id="session_1",
        asset_id="asset_1",
        object_identity="snowman",
        semantic_target=SemanticTarget(level="whole", label_en="snowman"),
        scope="whole",
        user_semantic_intent="make it cuter",
        constraints=[],
        behavior_summary="The user requested a softer whole-object silhouette.",
        behavior_window_id="window_1",
        params=SemanticDivergenceParams(temperature=0.5, strictness=0.7),
    )


def _semantic_payload() -> dict[str, Any]:
    return {
        "candidates": [
            {
                "candidate_id": f"candidate_{index}",
                "display_label_zh": f"方向{index}",
                "label_en": f"direction {index}",
                "group": "semantic_transfer" if index % 2 else "shape",
                "target_ref": {"asset_id": "asset_1", "type": "whole", "id": None},
                "operation": "refine silhouette",
                "semantic_anchor": "soft toy",
                "prompt_phrase": f"make snowman direction {index} cuter",
                "attribute_delta": {"attribute": "silhouette", "change": "rounder"},
                "scores": {
                    "identity": 0.9,
                    "scope": 0.9,
                    "relevance": 0.9,
                    "specificity": 0.9,
                    "novelty": 0.8,
                },
            }
            for index in range(9)
        ]
    }


def test_external_intent_encoder_uses_fast_multimodal_stage() -> None:
    gateway = _Gateway(_intent_payload(), "gemini-3.6-flash")
    encoder = ExternalIntentEncoder(gateway)
    bundle = EventNormalizer().normalize([], session_context={"session_id": "session_external"})

    result = asyncio.run(encoder.encode(bundle))

    assert isinstance(result, IntentIR)
    assert result.ir_id == "ir_external"
    assert gateway.stages == [ModelStage.INTENT]


def test_external_decision_client_uses_reasoning_stage_and_overlays_ids() -> None:
    gateway = _Gateway(
        {
            "schema_version": "flowstudio.decision-ir.v1",
            "summary": "Refine the central volume.",
            "recommended_scope": "whole",
            "options": [],
            "needs_clarification": True,
            "clarification_question": "Which volume should change?",
            "confidence": 0.6,
            "model": "gpt-5.5",
        },
        "gpt-5.5",
    )
    client = ExternalDecisionClient(gateway)

    result = asyncio.run(
        client.decide(
            {
                "intent_ir": {"ir_id": "ir_1"},
                "retrieval_evidence": {"retrieval_id": "retrieval_1"},
            },
            run_id="run_1",
        )
    )

    assert result.run_id == "run_1"
    assert result.intent_ir_id == "ir_1"
    assert result.retrieval_id == "retrieval_1"
    assert gateway.stages == [ModelStage.REREPRESENTATION]


def test_gateway_semantic_generator_uses_reasoning_stage() -> None:
    gateway = _Gateway(_semantic_payload(), "gpt-5.5")
    generator = GatewaySemanticGenerator(
        gateway,
        stage=ModelStage.SEMANTIC_DIVERGENCE,
        model="gpt-5.5",
    )
    evidence = KnowledgeEvidence(route=KnowledgeRoute(mode="model_only"))

    result = asyncio.run(generator.generate(_semantic_request(), evidence))

    assert len(result) == 9
    assert result[0].provenance.generator == "gpt-5.5"
    assert gateway.stages == [ModelStage.SEMANTIC_DIVERGENCE]


def test_default_runtime_builds_only_external_adapters(monkeypatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("legacy adapter was instantiated")

    monkeypatch.setattr(
        "app.services.encoding.qwen_intent_encoder.QwenIntentEncoder.__init__",
        forbidden,
    )
    monkeypatch.setattr(
        "app.services.divergence.semantic_model_clients.LocalVlmSemanticGenerator.__init__",
        forbidden,
    )

    runtime = build_external_model_runtime(
        Settings(
            _env_file=None,
            model_api_base="https://relay.example/v1",
            model_api_key="secret-key",
        )
    )

    assert isinstance(runtime.intent_encoder, ExternalIntentEncoder)
    assert isinstance(runtime.decision_client, ExternalDecisionClient)
    assert isinstance(runtime.semantic_primary, GatewaySemanticGenerator)
    assert isinstance(runtime.semantic_fallback, GatewaySemanticGenerator)
    assert runtime.semantic_primary.model == "gpt-5.5"
    assert runtime.semantic_fallback.model == "gemini-3.6-flash"


def test_application_default_wiring_uses_the_external_runtime() -> None:
    from app import main

    assert isinstance(
        main.four_stage_encoding_service.qwen_encoder,
        ExternalIntentEncoder,
    )
    assert isinstance(
        main.four_stage_decision_service.gemini_client,
        ExternalDecisionClient,
    )
    assert isinstance(
        main.semantic_divergence_service.gemini,
        GatewaySemanticGenerator,
    )
    assert isinstance(
        main.semantic_divergence_service.local_vlm,
        GatewaySemanticGenerator,
    )
