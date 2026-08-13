"""Offline research acceptance for the three semantic-divergence scenarios.

These tests deliberately replace only external model/knowledge calls.  The
Gate, semantic service, shared validator, authoritative selection resolution,
and GenerationSpec builder are production components.
"""

from __future__ import annotations

import asyncio
from enum import StrEnum
from typing import Any

import pytest

from app.models import (
    DivergenceSelection,
    FourStageRun,
    FourStageRunCreateRequest,
    GateAction,
    KnowledgeEvidence,
    KnowledgeRoute,
    SemanticCandidate,
    SemanticCandidateProvenance,
    SemanticDivergenceParams,
    SemanticDivergenceRequest,
    SemanticScores,
    SemanticTargetRef,
    SourceContext,
    UserEvent,
)
from app.services.divergence.semantic_divergence_service import SemanticDivergenceService
from app.services.divergence.semantic_validator import SemanticCandidateValidator
from app.services.encoding import EventNormalizer, FourStageEncodingService
from app.services.encoding.four_stage_encoding import RuleIntentEncoder
from app.services.encoding.qwen_intent_encoder import QwenIntentEncoder
from app.services.generation.four_stage_spec_builder import GenerationSpecBuilder
from app.services.pipeline.four_stage_orchestrator import FourStageOrchestrator
from app.services.rerepresentation import RuleDecisionService
from app.services.retrieval.four_stage_retrieval import FourStageRetrievalService
from app.services.storage.four_stage_store import FourStageStore


class AblationMode(StrEnum):
    """Research/test-only modes; this enum is intentionally absent from the UI."""

    llm_only = "llm_only"
    knowledge_only = "knowledge_only"
    knowledge_augmented_llm = "knowledge_augmented_llm"


SCENARIOS: dict[str, dict[str, Any]] = {
    "stone_frog": {
        "object_identity": "frog character",
        "scope": "whole",
        "target_part": None,
        "intent": "turn the same little frog into a weathered stone statue narrative",
        "signals": ["text", "drag", "smooth"],
        "events": [
            {"type": "text", "payload": {"text": "turn the same little frog into a weathered stone statue narrative"}},
            {"type": "drag_end", "payload": {"start": [0, 0, 0], "end": [0.2, 0.1, 0], "space": "world", "influence_radius": 0.3}},
            {"type": "smooth_end", "payload": {"strength": 0.25, "radius": 0.2, "preserve_boundary": True}},
        ],
        "required_groups": {"surface", "semantic_transfer"},
        "labels": [
            "岩面肌理", "风化裂纹", "苔痕石像", "凿刻纹路", "玄武岩肤",
            "古碑残蚀", "石灰包浆", "雨蚀凹痕", "青苔嵌缝", "遗迹印记",
        ],
        "labels_en": [
            "rock grain", "weather cracks", "moss relic", "chisel marks", "basalt skin",
            "eroded stele", "lime patina", "rain pits", "moss seams", "relic imprint",
        ],
        "groups": ["surface", "semantic_transfer"],
        "phrase": "preserve the same frog character while transferring it into weathered carved stone",
        "prompt_markers": ["frog character", "narrative transfer", "stone"],
    },
    "handbag_material": {
        "object_identity": "handbag",
        "scope": "material_region",
        "target_part": "body_material",
        "intent": "keep the handbag form and explore materially diverse semantic surfaces",
        "signals": ["text", "intent", "2d_brush"],
        "events": [
            {"type": "text", "payload": {"text": "keep the handbag form and explore materially diverse semantic surfaces"}},
            {"type": "part_select", "payload": {"part_id": "body_material", "label": "handbag body material", "scope": "material_region"}},
            {"type": "annotation_end", "payload": {"part_id": "body_material", "artifact_url": "/files/handbag-mask.png", "target_mask_ref": "mask://handbag_material", "bbox": {"x": 0.1, "y": 0.1, "w": 0.7, "h": 0.7}, "projection": {"type": "uv"}}},
        ],
        "required_groups": {"surface"},
        "labels": [
            "鳄纹皮革", "磨砂硅胶", "编织藤面", "再生毛毡", "软木颗粒",
            "半透树脂", "细密帆布", "珠光陶瓷", "金属网织", "水晶切面",
        ],
        "labels_en": [
            "crocodile leather", "frosted silicone", "woven rattan", "recycled felt", "cork granules",
            "translucent resin", "dense canvas", "pearl ceramic", "metal mesh", "crystal facets",
        ],
        "groups": ["surface", "semantic_transfer"],
        "phrase": "apply a distinct material by semantic region while preserving the exact handbag geometry",
        "prompt_markers": ["handbag", "exact geometry", "material"],
    },
    "lava_table": {
        "object_identity": "coffee table",
        "scope": "part",
        "target_part": "support_system",
        "intent": "keep the coffee table identity and transfer its support structure into flowing lava",
        "signals": ["text", "3d_brush"],
        "events": [
            {"type": "text", "payload": {"text": "keep the coffee table identity and transfer its support structure into flowing lava"}},
            {"type": "part_select", "payload": {"part_id": "support_system", "label": "support system", "scope": "part"}},
            {"type": "brush_end", "payload": {"part_id": "support_system", "target_mask_ref": "mask://lava_table", "source_model_ref": "/files/coffee-table.glb", "projection": {"space": "world"}, "brush": {"area_ratio": 0.2}, "stroke_count": 3}},
        ],
        "required_groups": {"shape", "semantic_transfer"},
        "labels": [
            "熔岩桌沿", "流动支腿", "冷凝关节", "岩浆脉络", "悬滴底座",
            "熔壳边缘", "玄武支架", "液态桥接", "火山裂隙", "热流托面",
        ],
        "labels_en": [
            "lava rim", "flowing legs", "cooled joints", "magma veins", "dripping base",
            "melt crust", "basalt frame", "liquid bridge", "volcanic fissures", "thermal support",
        ],
        "groups": ["shape", "semantic_transfer"],
        "phrase": "reshape only the coffee table support system as flowing lava while retaining load-bearing topology",
        "prompt_markers": ["coffee table", "structure transfer", "support_system"],
    },
}


class _OfflineSparseRetriever:
    """External sparse-index boundary: ready, deterministic, and abstaining."""

    ready = True

    def retrieve(self, features: dict[str, Any], top_k: int = 20) -> list[Any]:
        return []


class _OfflineKnowledgeRouter:
    def choose_route(self, request: SemanticDivergenceRequest) -> KnowledgeRoute:
        return KnowledgeRoute(mode="model_only", reasons=["offline_fixture"])

    def collect(
        self, request: SemanticDivergenceRequest, route: KnowledgeRoute
    ) -> KnowledgeEvidence:
        return KnowledgeEvidence(route=route)


class _ScenarioGenerator:
    model = "deterministic-scenario-model"

    async def generate(
        self, request: SemanticDivergenceRequest, evidence: KnowledgeEvidence
    ) -> list[SemanticCandidate]:
        scenario = next(
            item
            for item in SCENARIOS.values()
            if item["object_identity"] == request.object_identity
        )
        assert request.user_semantic_intent == scenario["intent"]
        for event_spec in scenario["events"]:
            assert f'"type": "{event_spec["type"]}"' in request.behavior_summary
        if request.scope == "part":
            target_type = "part"
            target_id = request.semantic_target.part_id
        elif request.scope == "material_region":
            target_type = "material_region"
            target_id = request.semantic_target.mask_ref or request.semantic_target.part_id
        else:
            target_type = "whole"
            target_id = None
        candidates: list[SemanticCandidate] = []
        for index, label in enumerate(scenario["labels"]):
            candidates.append(
                SemanticCandidate(
                    candidate_id=f"{request.run_id}_candidate_{index + 1:02d}",
                    display_label_zh=label,
                    label_en=scenario["labels_en"][index],
                    group=scenario["groups"][index % len(scenario["groups"])],
                    target_ref=SemanticTargetRef(
                        asset_id=request.asset_id, type=target_type, id=target_id
                    ),
                    operation="semantic_transfer",
                    semantic_anchor=scenario["phrase"],
                    prompt_phrase=f"{scenario['phrase']}; variant {index + 1}: {label}",
                    attribute_delta={
                        "attribute": f"semantic_attribute_{index + 1}",
                        "change": f"scenario_delta_{index + 1}",
                    },
                    scores=SemanticScores(
                        identity=0.95,
                        scope=0.95,
                        relevance=0.95,
                        specificity=0.9,
                        novelty=0.8,
                    ),
                    provenance=SemanticCandidateProvenance(
                        generator=self.model, mode="model_only"
                    ),
                )
            )
        return candidates


class _FailIfCalledGenerator:
    model = "must-not-fallback"

    async def generate(self, request: Any, evidence: Any) -> list[SemanticCandidate]:
        raise AssertionError("valid scenario candidates must not call fallback")


class _SpecOnlyGenerationService:
    def __init__(self) -> None:
        self.builder = GenerationSpecBuilder(candidate_count=8)

    def build_spec(self, run: FourStageRun, selected_option_id: str):
        return self.builder.build_spec(run, selected_option_id)

    async def start_generation(self, run: FourStageRun, spec: Any) -> dict[str, Any]:
        return {"status": "spec_built", "generation_id": spec.generation_id}


def _event(
    session_id: str, index: int, event_spec: dict[str, Any], asset_id: str
) -> UserEvent:
    return UserEvent(
        type=event_spec["type"],
        event_id=f"event_{session_id}_{index}",
        session_id=session_id,
        payload={**event_spec["payload"], "asset_id": asset_id},
    )


def _orchestrator() -> FourStageOrchestrator:
    store = FourStageStore()
    semantic_service = SemanticDivergenceService(
        store=store,
        knowledge_router=_OfflineKnowledgeRouter(),
        gemini=_ScenarioGenerator(),
        local_vlm=_FailIfCalledGenerator(),
        validator=SemanticCandidateValidator(),
    )
    return FourStageOrchestrator(
        store,
        encoding_service=FourStageEncodingService(
            normalizer=EventNormalizer(),
            qwen_encoder=QwenIntentEncoder(None),
            rule_encoder=RuleIntentEncoder(),
        ),
        retrieval_service=FourStageRetrievalService(
            retriever=_OfflineSparseRetriever(), store=store
        ),
        decision_service=RuleDecisionService(),
        semantic_divergence_service=semantic_service,
        generation_service=_SpecOnlyGenerationService(),
    )


@pytest.mark.parametrize("scenario_name", tuple(SCENARIOS))
def test_three_scenarios_gate_then_semantic_selection_builds_eight_safe_prompts(
    scenario_name: str,
) -> None:
    """A pre-Gate model call or a generic/unsafe post-Gate prompt breaks this test."""
    scenario = SCENARIOS[scenario_name]
    orchestrator = _orchestrator()
    session_id = f"session_{scenario_name}"
    asset_id = f"asset_{scenario_name}"
    run = asyncio.run(
        orchestrator.create_run(
            FourStageRunCreateRequest(
                session_id=session_id,
                events=[
                    _event(session_id, index, event_spec, asset_id)
                    for index, event_spec in enumerate(scenario["events"], start=1)
                ],
                source_context=SourceContext(
                    asset_id=asset_id,
                    object_type=scenario["object_identity"],
                    target_part_id=scenario["target_part"],
                    target_mask_ref=(
                        f"mask://{scenario_name}" if scenario["scope"] != "whole" else None
                    ),
                ),
            )
        )
    )
    assert run.semantic_divergence is None
    assert run.intent_ir is not None
    assert run.intent_ir.provenance.encoder == "rule-fallback"
    assert run.intent_ir.intent.scope == scenario["scope"]
    assert run.retrieval is not None and run.retrieval.abstained is True
    assert run.decision is not None
    assert run.decision.model == "rule-fallback"
    if scenario["scope"] == "material_region":
        assert "表面材质" in (run.decision.gate_question or "")

    accepted = asyncio.run(
        orchestrator.resolve_gate(
            run.run_id,
            run.decision.decision_id,
            GateAction.accept_option,
            selected_option_id=run.decision.options[0].option_id,
            auto_generate=False,
            divergence_params=SemanticDivergenceParams(
                temperature=0.3, strictness=0.6, candidate_count=10
            ),
        )
    )
    response = accepted.semantic_divergence
    assert response is not None
    assert 9 <= len(response.candidates) <= 15
    assert scenario["required_groups"] <= {candidate.group for candidate in response.candidates}
    banned = {"Aesthetic", "Structural", "Functional", "Cross-domain"}
    for candidate in response.candidates:
        assert candidate.display_label_zh not in banned
        assert candidate.label_en not in banned
        assert 2 <= len(candidate.display_label_zh) <= 8
        assert 1 <= len(candidate.label_en.split()) <= 4
        assert candidate.target_ref.asset_id == asset_id
        if scenario["scope"] == "part":
            assert candidate.target_ref.type == "part"
            assert candidate.target_ref.id == scenario["target_part"]
        elif scenario["scope"] == "material_region":
            assert candidate.target_ref.type == "material_region"
            assert candidate.target_ref.id == f"mask://{scenario_name}"
        else:
            assert candidate.target_ref.type == "whole"
            assert candidate.target_ref.id is None

    chosen = [response.candidates[0], response.candidates[1]]
    selected = asyncio.run(
        orchestrator.save_divergence_selection(
            run.run_id,
            DivergenceSelection(
                selected_candidate_ids=[candidate.candidate_id for candidate in chosen]
            ),
        )
    )
    assert selected.divergence_selection is not None
    assert selected.divergence_selection.selected_candidate_ids == [
        candidate.candidate_id for candidate in chosen
    ]
    assert selected.divergence_selection.resolved_prompt_phrases == [
        candidate.prompt_phrase for candidate in chosen
    ]

    asyncio.run(orchestrator.start_generation(run.run_id))
    generated = orchestrator.store.get_run(run.run_id)
    assert generated is not None and generated.generation_spec is not None
    spec = generated.generation_spec
    assert spec.candidate_count == 8
    assert len(spec.prompt_candidates) == 8
    assert spec.target.scope == scenario["scope"]
    assert spec.target.part_id == scenario["target_part"]
    if scenario["scope"] != "whole":
        assert spec.source is not None
        assert spec.source.target_mask_ref == f"mask://{scenario_name}"
    for prompt in spec.prompt_candidates:
        normalized = prompt.casefold()
        assert f"preserve {scenario['object_identity']} identity" in normalized
        assert "one complete object only" in normalized
        assert "pure white rgb(255,255,255) background" in normalized
        assert "no crop" in normalized
        for marker in scenario["prompt_markers"]:
            assert marker.casefold() in normalized
        if scenario["scope"] == "part":
            assert f"change only {scenario['target_part']}" in normalized
            assert "preserve every non-target part" in normalized
        if scenario["scope"] == "material_region":
            assert "preserve exact geometry" in normalized
            assert "apply materials by semantic region" in normalized


_KNOWLEDGE_DONORS = [
    {"id": f"Q{10884 + index}", "label": label, "label_en": label_en}
    for index, (label, label_en) in enumerate(
        zip(
            ["砂岩层理", "花岗晶粒", "石灰包浆", "凿刻刀痕", "古碑风蚀", "青苔嵌缝", "玄武气孔", "雨蚀凹痕", "矿物色带", "断面结晶"],
            ["sandstone bedding", "granite grains", "lime patina", "chisel marks", "stele erosion", "moss seams", "basalt pores", "rain pits", "mineral bands", "fracture crystals"],
            strict=True,
        )
    )
]


def _fixed_ablation_request() -> SemanticDivergenceRequest:
    scenario = SCENARIOS["stone_frog"]
    return SemanticDivergenceRequest(
        run_id="ablation_fixed",
        decision_id="decision_ablation",
        session_id="session_ablation",
        asset_id="asset_ablation",
        object_identity=scenario["object_identity"],
        semantic_target={"level": scenario["scope"], "label_en": scenario["object_identity"]},
        scope=scenario["scope"],
        user_semantic_intent=scenario["intent"],
        behavior_summary='[{"type":"text"},{"type":"drag_end"},{"type":"smooth_end"}]',
        behavior_window_id="window_ablation",
        params={"temperature": 0.3, "strictness": 0.6, "candidate_count": 10},
    )


def _ablation_candidates(
    request: SemanticDivergenceRequest,
    *,
    labels: list[tuple[str, str]],
    generator: str,
    evidence: KnowledgeEvidence,
    prefix: str,
) -> list[SemanticCandidate]:
    uses_knowledge = bool(evidence.wikidata)
    return [
        SemanticCandidate(
            candidate_id=f"{prefix}_{index:02d}",
            display_label_zh=label_zh,
            label_en=label_en,
            group="surface" if index % 2 else "semantic_transfer",
            target_ref={"asset_id": request.asset_id, "type": "whole", "id": None},
            operation="semantic_transfer",
            semantic_anchor=f"{prefix} stone frog anchor",
            prompt_phrase=f"{prefix}: preserve the frog while applying {label_en}",
            attribute_delta={"attribute": f"{prefix}_attribute_{index}", "change": label_en},
            scores={"identity": 0.95, "scope": 0.95, "relevance": 0.95, "specificity": 0.9, "novelty": 0.8},
            provenance={
                "generator": generator,
                "mode": "knowledge_augmented" if uses_knowledge else "model_only",
                "wikidata": evidence.wikidata[:1] if uses_knowledge else [],
            },
        )
        for index, (label_zh, label_en) in enumerate(labels, start=1)
    ]


class _AblationLlmAdapter:
    def __init__(self) -> None:
        self.calls: list[KnowledgeEvidence] = []

    def generate(
        self, request: SemanticDivergenceRequest, evidence: KnowledgeEvidence
    ) -> list[SemanticCandidate]:
        self.calls.append(evidence)
        if evidence.wikidata:
            labels = [
                (f"蛙{donor['label'][:4]}", f"frog {donor['label_en']}")
                for donor in evidence.wikidata
            ]
            return _ablation_candidates(
                request,
                labels=labels,
                generator="fixed-contextual-llm",
                evidence=evidence,
                prefix="augmented",
            )
        scenario = SCENARIOS["stone_frog"]
        return _ablation_candidates(
            request,
            labels=list(zip(scenario["labels"], scenario["labels_en"], strict=True)),
            generator="fixed-llm",
            evidence=evidence,
            prefix="llm",
        )


class _KnowledgeOnlyAdapter:
    def __init__(self) -> None:
        self.calls: list[KnowledgeEvidence] = []

    def generate(
        self, request: SemanticDivergenceRequest, evidence: KnowledgeEvidence
    ) -> list[SemanticCandidate]:
        self.calls.append(evidence)
        labels = [
            (str(item["label"]), str(item["label_en"]))
            for item in evidence.wikidata
        ]
        return _ablation_candidates(
            request,
            labels=labels,
            generator="fixed-knowledge-adapter",
            evidence=evidence,
            prefix="knowledge",
        )


def test_ablation_modes_share_validator_and_candidate_count_without_ui_surface() -> None:
    """A mode-specific validator/count would make ablation results incomparable."""
    request = _fixed_ablation_request()
    validator = SemanticCandidateValidator()
    llm = _AblationLlmAdapter()
    knowledge = _KnowledgeOnlyAdapter()
    empty_evidence = KnowledgeEvidence(route={"mode": "model_only"})
    knowledge_evidence = KnowledgeEvidence(
        route={"mode": "knowledge_augmented", "use_wikidata": True},
        wikidata=_KNOWLEDGE_DONORS,
    )
    source_candidates = {
        AblationMode.llm_only: llm.generate(request, empty_evidence),
        AblationMode.knowledge_only: knowledge.generate(request, knowledge_evidence),
        AblationMode.knowledge_augmented_llm: llm.generate(request, knowledge_evidence),
    }
    validator_calls: list[SemanticCandidateValidator] = []
    reports = {}
    for mode, candidates in source_candidates.items():
        validator_calls.append(validator)
        reports[mode] = validator.validate(request, candidates)

    assert {mode.value for mode in reports} == {
        "llm_only",
        "knowledge_only",
        "knowledge_augmented_llm",
    }
    assert request.candidate_count == 10
    assert len(llm.calls) == 2
    assert llm.calls[0] is empty_evidence
    assert llm.calls[0].wikidata == []
    assert llm.calls[1] is knowledge_evidence
    assert knowledge.calls == [knowledge_evidence]
    assert all(call is validator for call in validator_calls)
    label_sets = {
        mode: {candidate.display_label_zh for candidate in candidates}
        for mode, candidates in source_candidates.items()
    }
    phrase_sets = {
        mode: {candidate.prompt_phrase for candidate in candidates}
        for mode, candidates in source_candidates.items()
    }
    attribute_sets = {
        mode: {candidate.attribute_delta.attribute for candidate in candidates}
        for mode, candidates in source_candidates.items()
    }
    assert len({frozenset(values) for values in label_sets.values()}) == 3
    assert len({frozenset(values) for values in phrase_sets.values()}) == 3
    assert len({frozenset(values) for values in attribute_sets.values()}) == 3
    for report in reports.values():
        assert report.needs_fallback is False
        assert len(report.accepted) == 10
