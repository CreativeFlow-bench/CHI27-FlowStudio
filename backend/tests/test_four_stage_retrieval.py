"""Phase 2 tests: sparse retrieval + metadata/outcome scoring + abstain + feedback."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.models import (
    FourStageRun,
    FourStageRunCreateRequest,
    FourStageStage,
    GateAction,
    GenerationSpec,
    IntentCore,
    IntentIR,
    IntentObservations,
    IntentProvenance,
    IntentTarget,
    RetrievalBundle,
    RetrievalMatch,
    UserEvent,
)
from app.services.intent.design_state_ir import DesignStateIRMatch, DesignStateIRRetriever
from app.services.pipeline.four_stage_orchestrator import (
    FakeDecisionService,
    FakeEncodingService,
    FourStageOrchestrator,
)
from app.services.retrieval import FourStageRetrievalService
from app.services.storage.four_stage_store import FourStageStore


def _ir(
    *,
    operation: str = "explore_variations",
    scope: str = "part",
    text: str = "make the lid knob more organic",
    part_id: str = "lid_knob",
) -> IntentIR:
    return IntentIR(
        ir_id="ir_q",
        run_id="run_q",
        session_id="sess_q",
        source_event_ids=["evt_1"],
        target=IntentTarget(part_id=part_id, object_type="teapot"),
        observations=IntentObservations(
            text=text,
            viewport={"orbit_count": 2},
            interaction_summary={
                "has_text": True,
                "selection_type": "part" if part_id else "none",
            },
        ),
        intent=IntentCore(operation=operation, scope=scope, goal=text),
        confidence=0.8,
        ambiguity=0.2,
        provenance=IntentProvenance(encoder="qwen3-8b", fallback_used=False),
    )


def _match(
    ir_id: str,
    case_id: str,
    score: float,
    *,
    scope_hint: str = "part",
    target_level: str = "part",
    design_state: str = "explore_variations",
    text: str = "make the lid knob more organic",
) -> DesignStateIRMatch:
    return DesignStateIRMatch(
        ir_id=ir_id,
        case_id=case_id,
        score=score,
        design_state=design_state,
        route="unknown",
        signals=[],
        scope_hint=scope_hint,
        target_level=target_level,
        recommended_axes=[],
        evidence_strength="high",
        text=text,
        confidence=0.7,
        vector_score=0.0,
        signal_overlap=[],
        term_overlap=[],
        scope_match=scope_hint == "part",
    )


class StubRetriever:
    def __init__(self, matches: list[DesignStateIRMatch]) -> None:
        self.matches = matches
        self.ready = True

    def retrieve(self, features: dict, top_k: int = 5) -> list[DesignStateIRMatch]:
        return sorted(self.matches, key=lambda item: item.score, reverse=True)[:top_k]


def test_real_sparse_retrieval_is_deterministic_and_auditable() -> None:
    service = FourStageRetrievalService()
    run = FourStageRun(run_id="run_r", session_id="sess_r", source_event_ids=["evt_1"])

    async def call():
        return await service.retrieve(run, _ir())

    first = asyncio.run(call())
    second = asyncio.run(call())
    assert first.retriever == "design-state-ir-sparse-v1"
    if not first.abstained:
        assert [m.case_id for m in first.matches] == [m.case_id for m in second.matches]
        final_scores = [m.final_score for m in first.matches]
        assert final_scores == sorted(final_scores, reverse=True)
        for match in first.matches:
            assert 0 <= match.sparse_score <= 1
            assert 0 <= match.metadata_score <= 1
            assert -0.25 <= match.outcome_score <= 0.25
            assert 0 <= match.final_score <= 1
            assert match.prior_ir_id
            assert match.evidence


def test_abstain_when_top_score_too_weak_or_tops_too_close() -> None:
    weak = FourStageRetrievalService(retriever=StubRetriever([_match("p1", "c1", 0.2)]))
    close = FourStageRetrievalService(
        retriever=StubRetriever(
            [
                _match("p1", "c1", 5.0, design_state="exploration"),
                _match("p2", "c2", 4.99, design_state="refinement"),
            ]
        )
    )
    clear = FourStageRetrievalService(
        retriever=StubRetriever(
            [
                _match("p1", "c1", 5.0, design_state="exploration"),
                _match("p2", "c2", 3.0, design_state="refinement"),
            ]
        )
    )
    run = FourStageRun(run_id="run_a", session_id="sess_a", source_event_ids=["evt_1"])

    async def run_service(service):
        return await service.retrieve(run, _ir())

    weak_bundle = asyncio.run(run_service(weak))
    assert weak_bundle.abstained is True
    assert "abstain threshold" in weak_bundle.abstain_reason
    close_bundle = asyncio.run(run_service(close))
    assert close_bundle.abstained is True
    assert "too close" in close_bundle.abstain_reason
    clear_bundle = asyncio.run(run_service(clear))
    assert clear_bundle.abstained is False
    assert clear_bundle.matches[0].case_id == "c1"


def test_metadata_and_outcome_scoring() -> None:
    store = FourStageStore()
    store.record_retrieval_feedback(
        run_id="run_f",
        session_id="sess_f",
        prior_ir_id="p1",
        case_id="c1",
        action="accepted",
    )
    service = FourStageRetrievalService(
        retriever=StubRetriever([_match("p1", "c1", 5.0), _match("p2", "c2", 3.0)]),
        store=store,
    )
    run = FourStageRun(run_id="run_f", session_id="sess_f", source_event_ids=["evt_1"])
    bundle = asyncio.run(service.retrieve(run, _ir()))
    c1 = next(item for item in bundle.matches if item.case_id == "c1")
    c2 = next(item for item in bundle.matches if item.case_id == "c2")
    assert c1.outcome_score == 0.25
    assert c1.outcome["accepted"] is True
    assert c2.outcome_score == 0.0
    # metadata favours the scope-matched/part-level prior
    assert c1.metadata_score >= c2.metadata_score
    # final score is the weighted blend
    weights = service.weights
    expected = (
        weights["sparse"] * c1.sparse_score
        + weights["metadata"] * c1.metadata_score
        + weights["outcome"] * c1.outcome_score
    ) / (weights["sparse"] + weights["metadata"] + weights["outcome"])
    assert c1.final_score == pytest.approx(expected, abs=1e-3)


def test_missing_prior_data_abstains() -> None:
    retriever = DesignStateIRRetriever(
        path=Path("/nonexistent/design_state_ir_retrieval.jsonl")
    )
    assert retriever.ready is False
    service = FourStageRetrievalService(retriever=retriever)
    run = FourStageRun(run_id="run_m", session_id="sess_m", source_event_ids=["evt_1"])
    bundle = asyncio.run(service.retrieve(run, _ir()))
    assert bundle.abstained is True
    assert bundle.matches == []


def test_gate_accept_and_reject_record_retrieval_feedback() -> None:
    class StubRetrieval:
        async def retrieve(self, run, intent_ir):
            return RetrievalBundle(
                retrieval_id="ret_g",
                run_id=run.run_id,
                query_ir_id=intent_ir.ir_id,
                matches=[
                    RetrievalMatch(
                        prior_ir_id="prior_1",
                        case_id="case_1",
                        sparse_score=0.8,
                        metadata_score=0.9,
                        outcome_score=0.0,
                        final_score=0.85,
                    )
                ],
                abstained=False,
            )

    class StubGeneration:
        def build_spec(self, run, selected_option_id):
            return GenerationSpec(
                generation_id="gen_1",
                run_id=run.run_id,
                decision_id=run.decision.decision_id,
                selected_option_id=selected_option_id,
                asset_id=None,
                candidate_count=4,
                seeds=[1, 2, 3, 4],
            )

        async def start_generation(self, run, spec):
            return {"job_id": "genjob_1", "status": "queued", "spec_id": spec.generation_id}

    store = FourStageStore()
    orchestrator = FourStageOrchestrator(
        store=store,
        encoding_service=FakeEncodingService(),
        retrieval_service=StubRetrieval(),
        decision_service=FakeDecisionService(),
        generation_service=StubGeneration(),
    )

    async def scenario() -> None:
        run = await orchestrator.create_run(
            FourStageRunCreateRequest(
                session_id="sess_g",
                events=[UserEvent(type="text", event_id="evt_1", session_id="sess_g")],
            )
        )
        assert run.stage == FourStageStage.awaiting_gate
        decision_id = run.decision.decision_id

        rejected = await orchestrator.resolve_gate(
            run.run_id,
            decision_id,
            GateAction.reject_all,
            reason="no",
        )
        assert rejected.stage == FourStageStage.awaiting_gate
        assert store.retrieval_outcome_score("case_1", "sess_g") == pytest.approx(-0.2)

        accepted = await orchestrator.resolve_gate(
            run.run_id,
            decision_id,
            GateAction.accept_option,
            selected_option_id="opt_1",
        )
        assert accepted.stage == FourStageStage.generation
        assert accepted.generation_spec is not None
        assert accepted.generation_spec.selected_option_id == "opt_1"
        assert store.retrieval_outcome_score("case_1", "sess_g") == pytest.approx(0.05)
        assert store.retrieval_case_accepted("case_1") is True

    asyncio.run(scenario())
