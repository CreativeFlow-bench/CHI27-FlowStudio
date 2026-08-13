"""Phase 5 end-to-end acceptance: three concrete objects (strategy doc 13)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app, four_stage_orchestrator, four_stage_store, studio_store
from app.models import (
    DecisionIR,
    FourStageStage,
    IntentIR,
    SemanticCandidate,
    SemanticDivergenceResponse,
    RetrievalBundle,
)
from app.services.encoding.four_stage_encoding import RuleIntentEncoder
from app.services.encoding import EventNormalizer, FourStageEncodingService
from app.services.encoding.qwen_intent_encoder import QwenIntentEncoder
from app.services.generation.four_stage_spec_builder import GenerationSpecBuilder
from app.services.rerepresentation import RuleDecisionService


client = TestClient(app)


class _StubGenerationService:
    def __init__(self, orchestrator) -> None:
        self.orchestrator = orchestrator
        self.builder = GenerationSpecBuilder()

    def build_spec(self, run, selected_option_id):
        return self.builder.build_spec(run, selected_option_id)

    async def start_generation(self, run, spec):
        run.generation_artifacts = [
            {
                "url": f"http://files/{spec.generation_id}_1.png",
                "candidate_id": "c1",
                "label": spec.prompt_candidates[0][:60],
            }
        ]
        await self.orchestrator.finalize_generation(
            run.run_id, artifacts=run.generation_artifacts
        )
        return {"job_id": "genjob_stub", "status": "completed", "spec_id": spec.generation_id}


class _StubSemanticDivergenceService:
    """Offline post-Gate fake; selection and prompt resolution remain real."""

    async def diverge(self, run, params):
        assert run.intent_ir is not None and run.decision is not None
        part_id = run.intent_ir.target.part_id
        target_type = "part" if run.intent_ir.intent.scope == "part" else "whole"
        candidates = [
            SemanticCandidate(
                candidate_id=f"candidate_{index}",
                display_label_zh=f"有机渐变{index}",
                label_en=f"organic taper {index}",
                group="shape" if index % 2 else "semantic_transfer",
                target_ref={
                    "asset_id": run.intent_ir.target.asset_id,
                    "type": target_type,
                    "id": part_id if target_type == "part" else None,
                },
                operation="deform",
                semantic_anchor="organic local transition",
                prompt_phrase=f"change only the confirmed target with organic taper variant {index}",
                attribute_delta={"attribute": f"contour_{index}", "change": f"taper_{index}"},
                scores={
                    "identity": 0.95,
                    "scope": 0.95,
                    "relevance": 0.95,
                    "specificity": 0.9,
                    "novelty": 0.8,
                },
                provenance={"generator": "offline-e2e", "mode": "model_only"},
            )
            for index in range(1, 10)
        ]
        response = SemanticDivergenceResponse(
            divergence_id=f"semantic_{run.run_id}",
            run_id=run.run_id,
            decision_id=run.decision.decision_id,
            request_key=f"request_{run.run_id}",
            generator_model="offline-e2e",
            candidates=candidates,
        )
        run.semantic_divergence = response
        four_stage_store.save_run(run)
        return response


def _encoding_service() -> FourStageEncodingService:
    return FourStageEncodingService(
        normalizer=EventNormalizer(),
        qwen_encoder=QwenIntentEncoder(None),
        rule_encoder=RuleIntentEncoder(),
        asset_lookup=lambda asset_id: (
            {"object_type": asset.object_type, "label": asset.label}
            if (asset := studio_store.get_asset(asset_id)) is not None
            else {}
        ),
    )


@pytest.fixture(autouse=True)
def hermetic_four_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    four_stage_store.clear()
    monkeypatch.setattr(four_stage_orchestrator, "encoding_service", _encoding_service())
    monkeypatch.setattr(four_stage_orchestrator, "decision_service", RuleDecisionService())
    monkeypatch.setattr(
        four_stage_orchestrator,
        "semantic_divergence_service",
        _StubSemanticDivergenceService(),
    )
    monkeypatch.setattr(
        four_stage_orchestrator,
        "generation_service",
        _StubGenerationService(four_stage_orchestrator),
    )
    yield
    four_stage_store.clear()


def _event(session_id: str, event_id: str, etype: str, payload: dict) -> dict:
    return {
        "type": etype,
        "event_id": event_id,
        "session_id": session_id,
        "payload": payload,
    }


_CASES = [
    (
        "teapot",
        [
            ("evt_t1", "orbit", {"viewport_orbit_count": 1}),
            ("evt_t2", "part_select", {"part_id": "lid_knob", "label": "lid knob"}),
            ("evt_t3", "text", {"text": "make the lid knob more organic, 保留 socket"}),
        ],
    ),
    (
        "snowman",
        [
            ("evt_s1", "orbit", {"viewport_orbit_count": 2, "dwell_ms": 1400}),
            (
                "evt_s2",
                "annotation",
                {
                    "part_id": "carrot_nose",
                    "artifact_url": "http://files/nose_ann.png",
                    "bbox": {"x": 1, "y": 1, "w": 2, "h": 3},
                },
            ),
            ("evt_s3", "text", {"text": "make the carrot nose pointier"}),
        ],
    ),
    (
        "water gun",
        [
            (
                "evt_w1",
                "brush_end",
                {
                    "part_id": "grip",
                    "mask": {"area_ratio": 0.35},
                    "artifact_url": "http://files/grip_mask.png",
                },
            ),
            ("evt_w2", "text", {"text": "more ergonomic grip, 保留扳机结构"}),
        ],
    ),
]


@pytest.mark.parametrize("object_type,raw_events", _CASES)
def test_four_stage_e2e_concrete_case(
    object_type: str,
    raw_events: list[tuple[str, str, dict]],
) -> None:
    session = client.post("/api/v1/sessions", json={"title": f"e2e {object_type}"}).json()
    sid = session["session_id"]
    asset = client.post(
        "/api/v1/assets",
        json={"session_id": sid, "object_type": object_type},
    ).json()
    events = [
        _event(sid, event_id, etype, {**payload, "asset_id": asset["asset_id"]})
        for event_id, etype, payload in raw_events
    ]
    response = client.post(
        "/api/v1/four-stage/runs",
        json={"session_id": sid, "events": events},
    )
    assert response.status_code == 200
    run = response.json()
    assert run["stage"] in {"awaiting_gate", "completed"}

    ir = IntentIR.model_validate(run["intent_ir"])
    assert ir.source_event_ids == [item["event_id"] for item in events]
    assert ir.intent.operation != "observe"  # generation intent, not observation
    assert ir.intent.scope in {"whole", "part"}

    retrieval = RetrievalBundle.model_validate(run["retrieval"])
    assert retrieval.query_ir_id == ir.ir_id
    assert retrieval.abstained or len(retrieval.matches) > 0

    decision = DecisionIR.model_validate(run["decision"])
    assert decision.intent_ir_id == ir.ir_id
    assert decision.retrieval_id == retrieval.retrieval_id
    assert decision.needs_clarification is False
    assert decision.options, "expected at least one gate option"

    selected = decision.options[0].option_id
    gate = client.post(
        f"/api/v1/four-stage/decisions/{decision.decision_id}/gate",
        json={"run_id": run["run_id"], "action": "accept_option", "selected_option_id": selected},
    )
    assert gate.status_code == 200
    gated = gate.json()
    assert gated["stage"] == FourStageStage.awaiting_gate.value
    assert len(gated["semantic_divergence"]["candidates"]) == 9
    chosen_candidate_id = gated["semantic_divergence"]["candidates"][0]["candidate_id"]
    selection = client.put(
        f"/api/v1/four-stage/runs/{run['run_id']}/divergence-selection",
        json={"selected_candidate_ids": [chosen_candidate_id]},
    )
    assert selection.status_code == 200, selection.text
    generated = client.post(f"/api/v1/four-stage/runs/{run['run_id']}/generation")
    assert generated.status_code == 200, generated.text
    final = client.get(f"/api/v1/four-stage/runs/{run['run_id']}").json()
    assert final["stage"] == FourStageStage.completed.value
    spec = final["generation_spec"]
    assert spec["decision_id"] == decision.decision_id
    assert spec["selected_option_id"] == selected
    assert spec["object_type"] == object_type
    assert spec["prompt_candidates"], "prompts must be built"
    assert spec["seeds"], "reproducible seeds required"
    assert final["generation_artifacts"], "artifacts required after gate"

    # Full traceability: events -> IR -> retrieval -> decision -> option -> generation.
    assert final["generation_spec"]["run_id"] == run["run_id"]
    assert final["generation_artifacts"][0]["candidate_id"] == "c1"
