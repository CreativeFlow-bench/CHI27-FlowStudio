"""Phase 0 tests: contracts + state machine + idempotency + retry/cancel."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.main import app, four_stage_orchestrator, four_stage_store
from app.models import (
    DecisionIR,
    DivergenceSelection,
    FourStageRunCreateRequest,
    FourStageStage,
    GateAction,
    IntentIR,
    RetrievalBundle,
    SemanticDivergenceParams,
    SemanticDivergenceResponse,
    UserEvent,
)
from app.services.pipeline.four_stage_orchestrator import (
    FakeDecisionService,
    FakeEncodingService,
    FakeRetrievalService,
    FourStageConflict,
    FourStageOrchestrator,
)
from app.services.divergence.semantic_divergence_service import SemanticDivergenceService
from app.services.storage.four_stage_store import FourStageStore
from app.services.encoding.four_stage_encoding import RuleIntentEncoder
from app.services.rerepresentation import RuleDecisionService
from app.services.generation.four_stage_spec_builder import GenerationSpecBuilder


client = TestClient(app)


def _semantic_response(run, params: SemanticDivergenceParams) -> SemanticDivergenceResponse:
    asset_id = run.source_context.asset_id if run.source_context is not None else "asset_test"
    refreshed = params.temperature >= 0.8
    return SemanticDivergenceResponse.model_validate(
        {
            "divergence_id": f"div_{run.run_id}_{params.temperature}",
            "run_id": run.run_id,
            "decision_id": run.decision.decision_id,
            "request_key": f"key_{run.decision.decision_id}_{params.temperature}",
            "generator_model": "test-semantic",
            "candidates": [
                {
                    "candidate_id": "kw_hat_fold" if refreshed else "kw_hat_curve",
                    "display_label_zh": "折叠帽檐" if refreshed else "卷曲帽檐",
                    "label_en": "folded brim" if refreshed else "curled brim",
                    "group": "shape",
                    "target_ref": {
                        "asset_id": asset_id,
                        "type": "part",
                        "id": "hat",
                    },
                    "operation": "deform",
                    "semantic_anchor": "layered fold" if refreshed else "soft curl",
                    "prompt_phrase": (
                        "fold only the hat brim into two crisp layers"
                        if refreshed
                        else "curl only the hat brim"
                    ),
                    "attribute_delta": {
                        "attribute": "contour",
                        "change": "folded layers" if refreshed else "curled edge",
                    },
                    "scores": {
                        "identity": 0.95,
                        "scope": 0.95,
                        "relevance": 0.95,
                        "specificity": 0.9,
                        "novelty": 0.7,
                    },
                    "provenance": {"generator": "test-semantic", "mode": "model_only"},
                }
            ],
        }
    )


class _SemanticDivergenceFake:
    def __init__(self, store=four_stage_store) -> None:
        self.store = store
        self.calls: list[tuple[str, SemanticDivergenceParams]] = []

    async def diverge(self, run, params: SemanticDivergenceParams):
        self.calls.append((run.run_id, params.model_copy(deep=True)))
        response = _semantic_response(run, params)
        run.semantic_divergence = response
        self.store.save_run(run)
        return response


class _PostPersistBlockingSemantic:
    """Expose the window after atomic persist but before orchestrator reload."""

    def __init__(self) -> None:
        self.persisted = asyncio.Event()
        self.release = asyncio.Event()

    async def diverge(self, run, params: SemanticDivergenceParams):
        response = _semantic_response(run, params)
        updated = four_stage_store.update_semantic_divergence_if_current(
            run.run_id,
            expected_decision_id=run.decision.decision_id,
            response=response,
        )
        assert updated is True
        self.persisted.set()
        await self.release.wait()
        return response


class _StubGenerationService:
    def __init__(self, orchestrator: FourStageOrchestrator) -> None:
        self.orchestrator = orchestrator
        self.builder = GenerationSpecBuilder()

    def build_spec(self, run, selected_option_id):
        return self.builder.build_spec(run, selected_option_id)

    async def start_generation(self, run, spec):
        run.generation_artifacts = [
            {"url": "http://files/stub_1.png", "candidate_id": "c1", "label": "stub"}
        ]
        await self.orchestrator.finalize_generation(
            run.run_id, artifacts=run.generation_artifacts
        )
        return {"job_id": "genjob_stub", "status": "completed", "spec_id": spec.generation_id}


@pytest.fixture(autouse=True)
def hermetic_four_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    four_stage_store.clear()
    # Never let API tests hit the dev machine's .env VLM endpoint (doc 6.2.6).
    monkeypatch.setattr(four_stage_orchestrator, "encoding_service", RuleIntentEncoder())
    monkeypatch.setattr(four_stage_orchestrator, "decision_service", RuleDecisionService())
    monkeypatch.setattr(
        four_stage_orchestrator,
        "generation_service",
        _StubGenerationService(four_stage_orchestrator),
    )
    monkeypatch.setattr(
        four_stage_orchestrator,
        "semantic_divergence_service",
        _SemanticDivergenceFake(),
        raising=False,
    )
    yield
    four_stage_store.clear()


def _make_session() -> dict:
    return client.post("/api/v1/sessions", json={"title": "four-stage"}).json()


def _event(session_id: str, event_id: str, etype: str = "orbit", payload: dict | None = None) -> dict:
    return {
        "type": etype,
        "event_id": event_id,
        "session_id": session_id,
        "payload": payload or {},
    }


def test_create_run_reaches_awaiting_gate_with_valid_contracts() -> None:
    session = _make_session()
    sid = session["session_id"]
    response = client.post(
        "/api/v1/four-stage/runs",
        json={
            "session_id": sid,
            "idempotency_key": "idem-1",
            "episode_id": "ep-1",
            "events": [
                _event(sid, "evt_1", "orbit", {"viewport_orbit_count": 2}),
                _event(sid, "evt_2", "text", {"text": "make the lid knob more organic"}),
            ],
        },
    )
    assert response.status_code == 200
    run = response.json()
    assert run["stage"] == "awaiting_gate"
    assert run["schema_version"] == "flowstudio.four-stage-run.v1"
    assert run["source_event_ids"] == ["evt_1", "evt_2"]
    assert run["idempotency_key"] == "idem-1"
    assert run["episode_id"] == "ep-1"

    intent_ir = run["intent_ir"]
    assert IntentIR.model_validate(intent_ir)
    assert intent_ir["schema_version"] == "flowstudio.intent-ir.v1"
    assert intent_ir["run_id"] == run["run_id"]
    assert intent_ir["source_event_ids"] == ["evt_1", "evt_2"]
    assert intent_ir["provenance"]["fallback_used"] is True

    retrieval = run["retrieval"]
    assert RetrievalBundle.model_validate(retrieval)
    assert retrieval["retriever"] == "design-state-ir-sparse-v1"
    assert retrieval["abstained"] is True or bool(retrieval["matches"])

    decision = run["decision"]
    assert DecisionIR.model_validate(decision)
    assert decision["options"][0]["option_id"] == "opt_1"

    for stage in ("encoding", "retrieval", "re_representation"):
        timestamps = run["stage_timestamps"][stage]
        assert timestamps["started_at"]
        assert timestamps["completed_at"]
        assert "failed_at" not in timestamps


def test_subresource_endpoints_return_stage_outputs() -> None:
    session = _make_session()
    sid = session["session_id"]
    run = client.post(
        "/api/v1/four-stage/runs",
        json={"session_id": sid, "events": [_event(sid, "evt_a")]},
    ).json()
    run_id = run["run_id"]
    assert client.get(f"/api/v1/four-stage/runs/{run_id}/intent-ir").status_code == 200
    assert client.get(f"/api/v1/four-stage/runs/{run_id}/retrieval").status_code == 200
    assert client.get(f"/api/v1/four-stage/runs/{run_id}/decision").status_code == 200
    assert client.get("/api/v1/four-stage/runs/missing").status_code == 404


def test_idempotency_key_returns_existing_run() -> None:
    session = _make_session()
    sid = session["session_id"]
    body = {
        "session_id": sid,
        "idempotency_key": "same-key",
        "events": [_event(sid, "evt_a")],
    }
    first = client.post("/api/v1/four-stage/runs", json=body).json()
    second = client.post("/api/v1/four-stage/runs", json=body).json()
    assert first["run_id"] == second["run_id"]
    assert client.get(f"/api/v1/four-stage/runs/{first['run_id']}").status_code == 200


def test_cancel_then_conflicts() -> None:
    session = _make_session()
    sid = session["session_id"]
    run = client.post(
        "/api/v1/four-stage/runs",
        json={
            "session_id": sid,
            "events": [_event(sid, "evt_1", "text", {"text": "make it cute"})],
        },
    ).json()
    assert run["stage"] == "awaiting_gate"
    cancelled = client.post(f"/api/v1/four-stage/runs/{run['run_id']}/cancel").json()
    assert cancelled["stage"] == "cancelled"
    assert cancelled["completed_at"]
    assert client.post(f"/api/v1/four-stage/runs/{run['run_id']}/cancel").status_code == 409
    assert client.post(f"/api/v1/four-stage/runs/{run['run_id']}/retry").status_code == 409


def test_advance_to_re_representation_stops_at_awaiting_gate() -> None:
    """前端流式：点关键词 advance(re_representation) 后必须停在 awaiting_gate（Gate 打开）。"""
    session = _make_session()
    sid = session["session_id"]
    run = client.post(
        "/api/v1/four-stage/runs",
        json={
            "session_id": sid,
            "auto_advance": False,
            "events": [_event(sid, "evt_1", "brush", {"text": "make it cute"})],
        },
    ).json()
    run_id = run["run_id"]
    assert run["stage"] == "raw_events"

    appended = client.post(
        f"/api/v1/four-stage/runs/{run_id}/events?auto_advance=false",
        json={"session_id": sid, "events": [_event(sid, "evt_2", "text", {"text": "make it cute"})]},
    ).json()
    assert appended["stage"] == "encoding"

    retrieved = client.post(
        f"/api/v1/four-stage/runs/{run_id}/advance",
        json={"target": "retrieval"},
    ).json()
    assert retrieved["stage"] == "retrieval"
    assert retrieved["retrieval"] is not None

    decided = client.post(
        f"/api/v1/four-stage/runs/{run_id}/advance",
        json={"target": "re_representation"},
    ).json()
    assert decided["stage"] == "awaiting_gate"
    assert decided["decision"] is not None
    assert decided["decision"]["options"]


def test_advance_without_target_from_retrieval_reaches_gate() -> None:
    """Generate 按钮路径：run 停在 retrieval 时 advance() 无 target 必须到 awaiting_gate。"""
    session = _make_session()
    sid = session["session_id"]
    run = client.post(
        "/api/v1/four-stage/runs",
        json={
            "session_id": sid,
            "auto_advance": False,
            "events": [_event(sid, "evt_1", "text", {"text": "make it cute"})],
        },
    ).json()
    run_id = run["run_id"]
    client.post(
        f"/api/v1/four-stage/runs/{run_id}/advance",
        json={"target": "retrieval"},
    ).json()
    gated = client.post(
        f"/api/v1/four-stage/runs/{run_id}/advance",
        json={},
    ).json()
    assert gated["stage"] == "awaiting_gate"
    assert gated["decision"] is not None


def test_advance_to_gate_from_raw_events() -> None:
    """raw_events 直接 advance(re_representation) 也必须落在 awaiting_gate。"""
    session = _make_session()
    sid = session["session_id"]
    run = client.post(
        "/api/v1/four-stage/runs",
        json={
            "session_id": sid,
            "auto_advance": False,
            "events": [_event(sid, "evt_1", "text", {"text": "make it cute"})],
        },
    ).json()
    assert run["stage"] == "raw_events"
    gated = client.post(
        f"/api/v1/four-stage/runs/{run['run_id']}/advance",
        json={"target": "re_representation"},
    ).json()
    assert gated["stage"] == "awaiting_gate"
    assert gated["decision"] is not None


def test_stage_failure_is_retryable_and_retry_recovers() -> None:
    class FlakyEncoding:
        def __init__(self) -> None:
            self.failures = 1

        async def encode(self, run):
            if self.failures:
                self.failures -= 1
                raise RuntimeError("encoder down")
            return await FakeEncodingService().encode(run)

    store = FourStageStore()
    orchestrator = FourStageOrchestrator(
        store=store,
        encoding_service=FlakyEncoding(),
        retrieval_service=FakeRetrievalService(),
        decision_service=FakeDecisionService(),
    )

    async def scenario() -> None:
        run = await orchestrator.create_run(
            FourStageRunCreateRequest(session_id="sess_test", events=[])
        )
        assert run.stage == FourStageStage.failed
        assert run.failed_stage == FourStageStage.encoding
        assert run.error and run.error["retryable"] is True
        assert "failed_at" in run.stage_timestamps["encoding"]

        recovered = await orchestrator.retry_run(run.run_id)
        assert recovered.stage == FourStageStage.awaiting_gate
        assert recovered.retry_count == 1
        assert recovered.error is None
        assert recovered.intent_ir is not None
        assert recovered.retrieval is not None
        assert recovered.decision is not None

    asyncio.run(scenario())


def test_gate_reject_all_records_decision() -> None:
    session = _make_session()
    sid = session["session_id"]
    run = client.post(
        "/api/v1/four-stage/runs",
        json={"session_id": sid, "events": [_event(sid, "evt_1")]},
    ).json()
    decision_id = run["decision"]["decision_id"]
    response = client.post(
        f"/api/v1/four-stage/decisions/{decision_id}/gate",
        json={"run_id": run["run_id"], "action": "reject_all", "reason": "not useful"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["stage"] == "awaiting_gate"
    assert body["gate_decision"]["action"] == "reject_all"


def test_semantic_divergence_refresh_requires_accepted_gate() -> None:
    """Removing the accepted-Gate guard must not expose pre-confirmation keywords."""
    session = _make_session()
    sid = session["session_id"]
    run = client.post(
        "/api/v1/four-stage/runs",
        json={
            "session_id": sid,
            "events": [_event(sid, "evt_semantic_pre", "text", {"text": "curl the hat brim"})],
            "source_context": {
                "asset_id": "asset_snowman",
                "object_type": "snowman",
                "target_part_id": "hat",
            },
        },
    ).json()

    response = client.post(
        f"/api/v1/four-stage/runs/{run['run_id']}/semantic-divergence",
        json={"temperature": 0.2, "strictness": 0.6},
    )

    assert response.status_code == 409


def test_compatibility_gate_accept_propagates_params_without_generating() -> None:
    """Dropping Gate params or calling generation on accept would break the staged UI."""
    session = _make_session()
    sid = session["session_id"]
    run = client.post(
        "/api/v1/four-stage/runs",
        json={
            "session_id": sid,
            "events": [_event(sid, "evt_semantic_accept", "text", {"text": "curl the hat brim"})],
            "source_context": {
                "asset_id": "asset_snowman",
                "object_type": "snowman",
                "target_part_id": "hat",
            },
        },
    ).json()
    fake = four_stage_orchestrator.semantic_divergence_service

    response = client.post(
        f"/api/v1/four-stage/decisions/{run['decision']['decision_id']}/gate",
        json={
            "run_id": run["run_id"],
            "action": "accept_option",
            "selected_option_id": "opt_1",
            "auto_generate": False,
            "divergence_params": {"temperature": 0.7, "strictness": 0.8},
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["stage"] == "awaiting_gate"
    assert body["semantic_divergence"]["candidates"][0]["display_label_zh"] == "卷曲帽檐"
    assert len(fake.calls) == 1
    assert fake.calls[0][1].temperature == 0.7
    assert fake.calls[0][1].strictness == 0.8
    assert four_stage_store.list_generation_jobs(run["run_id"]) == []


def test_compatibility_gate_reject_never_calls_semantic_divergence() -> None:
    """Routing reject through semantic divergence would generate unwanted directions."""
    session = _make_session()
    sid = session["session_id"]
    run = client.post(
        "/api/v1/four-stage/runs",
        json={
            "session_id": sid,
            "events": [_event(sid, "evt_semantic_reject")],
        },
    ).json()
    fake = four_stage_orchestrator.semantic_divergence_service

    response = client.post(
        f"/api/v1/four-stage/decisions/{run['decision']['decision_id']}/gate",
        json={
            "run_id": run["run_id"],
            "action": "reject_all",
            "divergence_params": {"temperature": 0.9, "strictness": 0.2},
        },
    )

    assert response.status_code == 200
    assert fake.calls == []


def test_semantic_divergence_refresh_requires_unchanged_accepted_decision() -> None:
    """A stale slider refresh must not attach keywords to a replaced decision."""
    session = _make_session()
    sid = session["session_id"]
    run = client.post(
        "/api/v1/four-stage/runs",
        json={
            "session_id": sid,
            "events": [_event(sid, "evt_semantic_refresh", "text", {"text": "curl the hat brim"})],
            "source_context": {
                "asset_id": "asset_snowman",
                "object_type": "snowman",
                "target_part_id": "hat",
            },
        },
    ).json()
    accepted = client.post(
        f"/api/v1/four-stage/decisions/{run['decision']['decision_id']}/gate",
        json={
            "run_id": run["run_id"],
            "action": "accept_option",
            "auto_generate": False,
            "divergence_params": {"temperature": 0.2, "strictness": 0.6},
        },
    ).json()
    stored = four_stage_store.get_run(run["run_id"])
    stored.decision.decision_id = "decision_replaced"
    four_stage_store.save_run(stored)

    response = client.post(
        f"/api/v1/four-stage/runs/{accepted['run_id']}/semantic-divergence",
        json={"temperature": 0.8, "strictness": 0.6},
    )

    assert response.status_code == 409


def test_semantic_divergence_refresh_replaces_candidates_with_settled_params() -> None:
    """Ignoring refresh params would make settled slider values ineffective."""
    session = _make_session()
    sid = session["session_id"]
    run = client.post(
        "/api/v1/four-stage/runs",
        json={
            "session_id": sid,
            "events": [_event(sid, "evt_semantic_settled", "text", {"text": "curl the hat brim"})],
            "source_context": {
                "asset_id": "asset_snowman",
                "object_type": "snowman",
                "target_part_id": "hat",
            },
        },
    ).json()
    accepted = client.post(
        f"/api/v1/four-stage/decisions/{run['decision']['decision_id']}/gate",
        json={
            "run_id": run["run_id"],
            "action": "accept_option",
            "auto_generate": False,
            "divergence_params": {"temperature": 0.2, "strictness": 0.6},
        },
    ).json()

    response = client.post(
        f"/api/v1/four-stage/runs/{accepted['run_id']}/semantic-divergence",
        json={"temperature": 0.8, "strictness": 0.9},
    )

    assert response.status_code == 200, response.text
    assert response.json()["request_key"].endswith("_0.8")
    fake = four_stage_orchestrator.semantic_divergence_service
    assert len(fake.calls) == 2
    assert fake.calls[-1][1].temperature == 0.8
    assert fake.calls[-1][1].strictness == 0.9


def test_semantic_divergence_refresh_rejects_failed_empty_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailedRefresh(_SemanticDivergenceFake):
        async def diverge(self, run, params):
            response = _semantic_response(run, params).model_copy(
                update={"status": "failed", "candidates": []}
            )
            run.semantic_divergence = response
            four_stage_store.save_run(run)
            return response

    session = _make_session()
    sid = session["session_id"]
    run = client.post(
        "/api/v1/four-stage/runs",
        json={
            "session_id": sid,
            "events": [_event(sid, "evt_failed_refresh", "text", {"text": "curl the hat brim"})],
            "source_context": {
                "asset_id": "asset_snowman",
                "object_type": "snowman",
                "target_part_id": "hat",
            },
        },
    ).json()
    accepted = client.post(
        f"/api/v1/four-stage/decisions/{run['decision']['decision_id']}/gate",
        json={"run_id": run["run_id"], "action": "accept_option", "auto_generate": False},
    )
    assert accepted.status_code == 200
    monkeypatch.setattr(
        four_stage_orchestrator, "semantic_divergence_service", _FailedRefresh()
    )

    response = client.post(
        f"/api/v1/four-stage/runs/{run['run_id']}/semantic-divergence",
        json={"temperature": 0.8, "strictness": 0.9},
    )

    assert response.status_code == 400
    assert "no valid candidates" in response.json()["error"]["message"]


def test_generation_rejects_selection_superseded_by_semantic_refresh() -> None:
    session = _make_session()
    sid = session["session_id"]
    run = client.post(
        "/api/v1/four-stage/runs",
        json={
            "session_id": sid,
            "events": [_event(sid, "evt_refresh_selection", "text", {"text": "change the hat brim"})],
            "source_context": {
                "asset_id": "asset_snowman",
                "object_type": "snowman",
                "target_part_id": "hat",
            },
        },
    ).json()
    client.post(
        f"/api/v1/four-stage/decisions/{run['decision']['decision_id']}/gate",
        json={
            "run_id": run["run_id"],
            "action": "accept_option",
            "auto_generate": False,
            "divergence_params": {"temperature": 0.2, "strictness": 0.6},
        },
    )
    selected = client.put(
        f"/api/v1/four-stage/runs/{run['run_id']}/divergence-selection",
        json={"selected_candidate_ids": ["kw_hat_curve"]},
    )
    assert selected.status_code == 200, selected.text
    refreshed = client.post(
        f"/api/v1/four-stage/runs/{run['run_id']}/semantic-divergence",
        json={"temperature": 0.8, "strictness": 0.6},
    )
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["candidates"][0]["candidate_id"] == "kw_hat_fold"

    generated = client.post(f"/api/v1/four-stage/runs/{run['run_id']}/generation")

    assert generated.status_code == 409, generated.text
    stored = four_stage_store.get_run(run["run_id"])
    assert stored.stage == FourStageStage.awaiting_gate
    assert stored.generation_spec is None
    assert four_stage_store.list_generation_jobs(run["run_id"]) == []


def test_generation_rebuilds_stale_selection_labels_and_phrases_from_current_candidates() -> None:
    session = _make_session()
    sid = session["session_id"]
    run = client.post(
        "/api/v1/four-stage/runs",
        json={
            "session_id": sid,
            "events": [_event(sid, "evt_canonical_selection", "text", {"text": "curl the hat brim"})],
            "source_context": {
                "asset_id": "asset_snowman",
                "object_type": "snowman",
                "target_part_id": "hat",
            },
        },
    ).json()
    client.post(
        f"/api/v1/four-stage/decisions/{run['decision']['decision_id']}/gate",
        json={
            "run_id": run["run_id"],
            "action": "accept_option",
            "auto_generate": False,
            "divergence_params": {"temperature": 0.2, "strictness": 0.6},
        },
    )
    selected = client.put(
        f"/api/v1/four-stage/runs/{run['run_id']}/divergence-selection",
        json={"selected_candidate_ids": ["kw_hat_curve"]},
    )
    assert selected.status_code == 200, selected.text
    stored = four_stage_store.get_run(run["run_id"])
    stored.divergence_selection.selected_keywords = ["client stale label"]
    stored.divergence_selection.resolved_prompt_phrases = ["client stale phrase"]
    stored.divergence_selection.dimensions = {"surface": ["client stale label"]}
    four_stage_store.save_run(stored)

    generated = client.post(f"/api/v1/four-stage/runs/{run['run_id']}/generation")

    assert generated.status_code == 200, generated.text
    finished = four_stage_store.get_run(run["run_id"])
    assert finished.divergence_selection.selected_keywords == ["卷曲帽檐"]
    assert finished.divergence_selection.resolved_prompt_phrases == [
        "curl only the hat brim"
    ]
    assert finished.divergence_selection.dimensions == {"shape": ["卷曲帽檐"]}
    assert all(
        "curl only the hat brim" in prompt
        and "client stale phrase" not in prompt
        for prompt in finished.generation_spec.prompt_candidates
    )


def test_auto_generate_semantic_failure_blocks_image_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Falling back to planner seeds after model failure would fabricate UI intent."""
    class _FailingSemantic:
        async def diverge(self, run, params):
            raise RuntimeError("both semantic models unavailable")

    monkeypatch.setattr(
        four_stage_orchestrator,
        "semantic_divergence_service",
        _FailingSemantic(),
    )
    session = _make_session()
    sid = session["session_id"]
    run = client.post(
        "/api/v1/four-stage/runs",
        json={
            "session_id": sid,
            "events": [_event(sid, "evt_semantic_fail", "text", {"text": "curl the hat brim"})],
            "source_context": {
                "asset_id": "asset_snowman",
                "object_type": "snowman",
                "target_part_id": "hat",
            },
        },
    ).json()

    response = client.post(
        f"/api/v1/four-stage/decisions/{run['decision']['decision_id']}/gate",
        json={
            "run_id": run["run_id"],
            "action": "accept_option",
            "auto_generate": True,
            "divergence_params": {"temperature": 0.5, "strictness": 0.7},
        },
    )

    assert response.status_code == 400
    assert "semantic divergence failed" in response.json()["error"]["message"]
    assert four_stage_store.list_generation_jobs(run["run_id"]) == []
    stored = four_stage_store.get_run(run["run_id"])
    assert stored.divergence_selection is None


def test_compatibility_auto_generate_does_not_synthesize_selection() -> None:
    """Using every model candidate as if the user selected it corrupts intent semantics."""
    session = _make_session()
    sid = session["session_id"]
    run = client.post(
        "/api/v1/four-stage/runs",
        json={
            "session_id": sid,
            "events": [_event(sid, "evt_no_fake_selection", "text", {"text": "curl the hat brim"})],
            "source_context": {
                "asset_id": "asset_snowman",
                "object_type": "snowman",
                "target_part_id": "hat",
            },
        },
    ).json()

    response = client.post(
        f"/api/v1/four-stage/decisions/{run['decision']['decision_id']}/gate",
        json={
            "run_id": run["run_id"],
            "action": "accept_option",
            "auto_generate": True,
            "divergence_params": {"temperature": 0.5, "strictness": 0.7},
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["stage"] == "awaiting_gate"
    assert body["semantic_divergence"]["status"] == "completed"
    assert body["divergence_selection"] is None
    assert four_stage_store.list_generation_jobs(run["run_id"]) == []


def test_inflight_refresh_cannot_overwrite_same_decision_rejection() -> None:
    """A stale full-run save must not restore an accepted Gate after rejection."""
    class _BlockingPersistingService(SemanticDivergenceService):
        def __init__(self) -> None:
            super().__init__(
                store=four_stage_store,
                knowledge_router=None,
                gemini=None,
                local_vlm=None,
                validator=None,
            )
            self.started = asyncio.Event()
            self.release = asyncio.Event()

        async def _diverge_once(self, run, params, key):
            self.started.set()
            await self.release.wait()
            return self._persist(run, _semantic_response(run, params))

    async def scenario() -> None:
        session = _make_session()
        sid = session["session_id"]
        run = client.post(
            "/api/v1/four-stage/runs",
            json={
                "session_id": sid,
                "events": [_event(sid, "evt_inflight_reject", "text", {"text": "curl the hat brim"})],
                "source_context": {
                    "asset_id": "asset_snowman",
                    "object_type": "snowman",
                    "target_part_id": "hat",
                },
            },
        ).json()
        await four_stage_orchestrator.resolve_gate(
            run["run_id"],
            run["decision"]["decision_id"],
            GateAction.accept_option,
            auto_generate=False,
            divergence_params=SemanticDivergenceParams(temperature=0.2, strictness=0.6),
        )
        blocking = _BlockingPersistingService()
        four_stage_orchestrator.semantic_divergence_service = blocking
        refresh = asyncio.create_task(
            four_stage_orchestrator.refresh_semantic_divergence(
                run["run_id"],
                SemanticDivergenceParams(temperature=0.8, strictness=0.6),
            )
        )
        await blocking.started.wait()
        await four_stage_orchestrator.resolve_gate(
            run["run_id"],
            run["decision"]["decision_id"],
            GateAction.reject_all,
            auto_generate=False,
        )
        blocking.release.set()

        with pytest.raises(FourStageConflict):
            await refresh
        current = four_stage_store.get_run(run["run_id"])
        assert current.gate_decision.action == GateAction.reject_all
        assert current.scope_gate.status == "rejected"

    asyncio.run(scenario())


def test_gate_accept_rechecks_state_after_atomic_persist_before_return() -> None:
    """Post-persist rejection must survive the accepting caller's stale snapshot."""
    async def scenario() -> None:
        session = _make_session()
        sid = session["session_id"]
        run = client.post(
            "/api/v1/four-stage/runs",
            json={
                "session_id": sid,
                "events": [_event(sid, "evt_post_persist_gate", "text", {"text": "curl the hat brim"})],
                "source_context": {
                    "asset_id": "asset_snowman",
                    "object_type": "snowman",
                    "target_part_id": "hat",
                },
            },
        ).json()
        blocking = _PostPersistBlockingSemantic()
        four_stage_orchestrator.semantic_divergence_service = blocking
        accepting = asyncio.create_task(
            four_stage_orchestrator.resolve_gate(
                run["run_id"],
                run["decision"]["decision_id"],
                GateAction.accept_option,
                auto_generate=False,
                divergence_params=SemanticDivergenceParams(temperature=0.8),
            )
        )
        await blocking.persisted.wait()
        await four_stage_orchestrator.resolve_gate(
            run["run_id"],
            run["decision"]["decision_id"],
            GateAction.reject_all,
            auto_generate=False,
        )
        blocking.release.set()

        with pytest.raises(FourStageConflict):
            await accepting
        current = four_stage_store.get_run(run["run_id"])
        assert current.gate_decision.action == GateAction.reject_all
        assert current.scope_gate.status == "rejected"
        assert current.semantic_divergence is None

    asyncio.run(scenario())


def test_refresh_rechecks_full_gate_after_atomic_persist_before_return() -> None:
    """A post-persist same-decision rejection must make refresh return conflict."""
    async def scenario() -> None:
        session = _make_session()
        sid = session["session_id"]
        run = client.post(
            "/api/v1/four-stage/runs",
            json={
                "session_id": sid,
                "events": [_event(sid, "evt_post_persist_refresh", "text", {"text": "curl the hat brim"})],
                "source_context": {
                    "asset_id": "asset_snowman",
                    "object_type": "snowman",
                    "target_part_id": "hat",
                },
            },
        ).json()
        await four_stage_orchestrator.resolve_gate(
            run["run_id"],
            run["decision"]["decision_id"],
            GateAction.accept_option,
            auto_generate=False,
            divergence_params=SemanticDivergenceParams(temperature=0.2),
        )
        blocking = _PostPersistBlockingSemantic()
        four_stage_orchestrator.semantic_divergence_service = blocking
        refresh = asyncio.create_task(
            four_stage_orchestrator.refresh_semantic_divergence(
                run["run_id"],
                SemanticDivergenceParams(temperature=0.9),
            )
        )
        await blocking.persisted.wait()
        await four_stage_orchestrator.resolve_gate(
            run["run_id"],
            run["decision"]["decision_id"],
            GateAction.reject_all,
            auto_generate=False,
        )
        blocking.release.set()

        with pytest.raises(FourStageConflict):
            await refresh
        current = four_stage_store.get_run(run["run_id"])
        assert current.gate_decision.action == GateAction.reject_all
        assert current.scope_gate.status == "rejected"
        assert current.semantic_divergence is None

    asyncio.run(scenario())


def test_divergence_options_uses_persisted_semantic_candidates_not_decision_seeds() -> None:
    """Reintroducing planner seeds would surface taxonomy-like fallback keywords."""
    session = _make_session()
    sid = session["session_id"]
    run = client.post(
        "/api/v1/four-stage/runs",
        json={
            "session_id": sid,
            "events": [_event(sid, "evt_semantic_options", "text", {"text": "curl the hat brim"})],
            "source_context": {
                "asset_id": "asset_snowman",
                "object_type": "snowman",
                "target_part_id": "hat",
            },
        },
    ).json()
    client.post(
        f"/api/v1/four-stage/decisions/{run['decision']['decision_id']}/gate",
        json={
            "run_id": run["run_id"],
            "action": "accept_option",
            "auto_generate": False,
            "divergence_params": {"temperature": 0.2, "strictness": 0.6},
        },
    )

    response = client.get(f"/api/v1/four-stage/runs/{run['run_id']}/divergence-options")

    assert response.status_code == 200
    body = response.json()
    assert [item["label"] for item in body["options"]] == ["卷曲帽檐"]
    assert body["metadata"]["decision_seeds_deprecated"] is True


def test_gate_accept_then_explicit_selection_completes_generation() -> None:
    session = _make_session()
    sid = session["session_id"]
    run = client.post(
        "/api/v1/four-stage/runs",
        json={
            "session_id": sid,
            "events": [_event(sid, "evt_1", "text", {"text": "make it cute"})],
        },
    ).json()
    decision_id = run["decision"]["decision_id"]
    response = client.post(
        f"/api/v1/four-stage/decisions/{decision_id}/gate",
        json={
            "run_id": run["run_id"],
            "action": "accept_option",
            "selected_option_id": "opt_1",
            "auto_generate": False,
        },
    )
    assert response.status_code == 200
    assert response.json()["stage"] == "awaiting_gate"
    selection = client.put(
        f"/api/v1/four-stage/runs/{run['run_id']}/divergence-selection",
        json={"scope": "part", "selected_keywords": ["卷曲帽檐"]},
    )
    assert selection.status_code == 200, selection.text
    generated = client.post(f"/api/v1/four-stage/runs/{run['run_id']}/generation")
    assert generated.status_code == 200, generated.text
    body = client.get(f"/api/v1/four-stage/runs/{run['run_id']}").json()
    assert body["stage"] == "completed"
    assert body["generation_spec"]["selected_option_id"] == "opt_1"
    assert body["generation_spec"]["prompt_candidates"]
    assert body["generation_artifacts"][0]["url"].startswith("http://files/")


def test_openapi_contains_new_and_old_routes() -> None:
    spec = client.get("/openapi.json").json()
    paths = set(spec["paths"])
    assert "/api/v1/four-stage/runs" in paths
    assert "/api/v1/four-stage/runs/{run_id}/retry" in paths
    assert "/api/v1/four-stage/decisions/{decision_id}/gate" in paths
    assert "/api/v1/four-stage/runs/{run_id}/generation" in paths
    assert "/api/v1/interaction/interpret" in paths


def _drain_until(websocket, target_type: str, max_messages: int = 12) -> list[str]:
    seen: list[str] = []
    for _ in range(max_messages):
        message = websocket.receive_json()
        seen.append(message["type"])
        if message["type"] == target_type:
            break
    return seen


def test_four_stage_ws_events_reject_then_accept_gate() -> None:
    session = _make_session()
    sid = session["session_id"]
    with client.websocket_connect(f"/ws/sessions/{sid}") as websocket:
        assert websocket.receive_json()["type"] == "ack"
        run = client.post(
            "/api/v1/four-stage/runs",
            json={
                "session_id": sid,
                "events": [_event(sid, "evt_1", "text", {"text": "make it cute"})],
            },
        ).json()
        assert run["stage"] == "awaiting_gate"
        seen = _drain_until(websocket, "four_stage.awaiting_gate")
        assert "four_stage.encoding_completed" in seen
        assert "four_stage.retrieval_completed" in seen
        assert "four_stage.decision_completed" in seen

        decision_id = run["decision"]["decision_id"]
        rejected = client.post(
            f"/api/v1/four-stage/decisions/{decision_id}/gate",
            json={"run_id": run["run_id"], "action": "reject_all", "reason": "no"},
        ).json()
        assert rejected["stage"] == "awaiting_gate"
        seen = _drain_until(websocket, "four_stage.gate_resolved")
        assert "four_stage.gate_resolved" in seen

        accepted = client.post(
            f"/api/v1/four-stage/decisions/{decision_id}/gate",
            json={
                "run_id": run["run_id"],
                "action": "accept_option",
                "selected_option_id": "opt_1",
                "auto_generate": False,
            },
        ).json()
        assert accepted["stage"] == "awaiting_gate"
        selected = client.put(
            f"/api/v1/four-stage/runs/{run['run_id']}/divergence-selection",
            json={"scope": "part", "selected_keywords": ["卷曲帽檐"]},
        )
        assert selected.status_code == 200
        generated = client.post(
            f"/api/v1/four-stage/runs/{run['run_id']}/generation"
        )
        assert generated.status_code == 200
        seen = _drain_until(websocket, "four_stage.completed")
        assert "four_stage.gate_resolved" in seen
        assert "four_stage.generation_queued" in seen
        assert "four_stage.completed" in seen


def test_four_stage_ws_events_revise_and_clarify_gate() -> None:
    session = _make_session()
    sid = session["session_id"]
    with client.websocket_connect(f"/ws/sessions/{sid}") as websocket:
        assert websocket.receive_json()["type"] == "ack"
        run = client.post(
            "/api/v1/four-stage/runs",
            json={
                "session_id": sid,
                "events": [_event(sid, "evt_1", "text", {"text": "make it cute"})],
            },
        ).json()
        _drain_until(websocket, "four_stage.awaiting_gate")
        decision_id = run["decision"]["decision_id"]

        revised = client.post(
            f"/api/v1/four-stage/decisions/{decision_id}/gate",
            json={"run_id": run["run_id"], "action": "request_revision", "user_revision": "softer"},
        ).json()
        assert revised["stage"] == "awaiting_gate"
        assert revised["decision"]["decision_id"] != decision_id
        seen = _drain_until(websocket, "four_stage.awaiting_gate")
        assert "four_stage.decision_completed" in seen

        clarified = client.post(
            f"/api/v1/four-stage/decisions/{revised['decision']['decision_id']}/gate",
            json={"run_id": run["run_id"], "action": "clarify", "user_revision": "silhouette"},
        ).json()
        assert clarified["stage"] == "awaiting_gate"
        seen = _drain_until(websocket, "four_stage.gate_resolved")
        assert "four_stage.gate_resolved" in seen


def test_no_generation_job_before_gate() -> None:
    import asyncio

    from app.services.generation.four_stage_generation import FourStageGenerationService
    from app.services.generation.four_stage_spec_builder import GenerationSpecBuilder
    from app.services.storage.four_stage_store import FourStageStore

    store = FourStageStore()

    async def dispatch(run, spec):
        return {"remote_job_id": f"remote_{run.run_id}"}

    async def poll(remote_job_id):
        return {
            "status": "completed",
            "artifacts": [{"url": f"http://files/{remote_job_id}_1.png", "candidate_id": "c1"}],
        }

    generation = FourStageGenerationService(
        store,
        builder=GenerationSpecBuilder(),
        dispatch=dispatch,
        poll=poll,
        lock=asyncio.Lock(),
    )
    orchestrator = FourStageOrchestrator(
        store=store,
        encoding_service=RuleIntentEncoder(),
        retrieval_service=FakeRetrievalService(),
        decision_service=RuleDecisionService(),
        generation_service=generation,
        semantic_divergence_service=_SemanticDivergenceFake(store),
    )
    generation.set_completion_callbacks(
        on_complete=orchestrator.finalize_generation,
        on_failed=lambda run_id, error: orchestrator.finalize_generation(run_id, error=error),
    )

    async def scenario() -> None:
        run = await orchestrator.create_run(
            FourStageRunCreateRequest(
                session_id="sess_gate",
                events=[
                    UserEvent(
                        type="text",
                        event_id="evt_1",
                        session_id="sess_gate",
                        payload={"text": "make it cute"},
                    )
                ],
            )
        )
        assert run.stage == FourStageStage.awaiting_gate
        assert store.list_generation_jobs(run.run_id) == []

        await orchestrator.resolve_gate(
            run.run_id,
            run.decision.decision_id,
            GateAction.accept_option,
            selected_option_id="opt_1",
            auto_generate=False,
        )
        await orchestrator.save_divergence_selection(
            run.run_id,
            DivergenceSelection(
                scope="part",
                selected_keywords=["卷曲帽檐"],
            ),
        )
        await orchestrator.start_generation(run.run_id)
        for _ in range(100):
            if store.get_run(run.run_id).stage == FourStageStage.completed:
                break
            await asyncio.sleep(0.01)
        jobs = store.list_generation_jobs(run.run_id)
        assert len(jobs) == 1
        assert jobs[0]["status"] == "completed"

    asyncio.run(scenario())
