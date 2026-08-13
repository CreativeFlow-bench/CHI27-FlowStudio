"""Phase 1 tests: EventNormalizer + QwenIntentEncoder + rule fallback."""

from __future__ import annotations

import asyncio
import json

import pytest

from app.models import (
    FourStageRun,
    FourStageRunCreateRequest,
    FourStageStage,
    IntentCore,
    IntentIR,
    IntentObservations,
    IntentProvenance,
    UserEvent,
)
from app.services.encoding.event_normalizer import EventNormalizer
from app.services.encoding.four_stage_encoding import (
    FourStageEncodingService,
    RuleIntentEncoder,
    infer_text_part,
    infer_text_parts,
)
from app.services.encoding.qwen_intent_encoder import (
    QwenEncodingError,
    QwenIntentEncoder,
)
from app.services.pipeline.four_stage_orchestrator import (
    FakeDecisionService,
    FakeRetrievalService,
    FourStageOrchestrator,
)
from app.services.storage.four_stage_store import FourStageStore


def _event(event_id: str, etype: str, payload: dict | None = None) -> UserEvent:
    return UserEvent(
        type=etype,
        event_id=event_id,
        session_id="sess_enc",
        payload=payload or {},
    )


def _bundle(events: list[UserEvent]):
    return EventNormalizer().normalize(
        events, session_context={"session_id": "sess_enc", "episode_id": "ep_1"}
    )


def test_orbit_only_aggregates_viewport_and_stays_observation() -> None:
    events = [
        _event("evt_1", "orbit", {"viewport_orbit_count": 1}),
        _event("evt_2", "zoom", {"zoom_count": 1}),
        _event("evt_3", "orbit", {"viewport_orbit_count": 1, "dwell_ms": 1200}),
        _event("evt_4", "camera_observation_ended", {"duration_ms": 900}),
    ]
    bundle = _bundle(events)
    assert bundle.viewport["orbit_count"] == 2
    assert bundle.viewport["zoom_count"] == 1
    assert bundle.viewport["dwell_ms_total"] == 2100
    assert bundle.viewport["dwell_ms_max"] == 1200
    assert bundle.interactions == []

    rule = RuleIntentEncoder()
    ir = asyncio.run(_encode_rule(rule, events))
    assert ir.intent.operation == "observe"
    assert ir.intent.scope == "whole"
    assert ir.provenance.fallback_used is True


async def _encode_rule(rule: RuleIntentEncoder, events: list[UserEvent]) -> IntentIR:
    run = FourStageRun(
        run_id="fsrun_enc",
        session_id="sess_enc",
        episode_id="ep_1",
        source_event_ids=[event.event_id for event in events],
        events=events,
    )
    return await rule.encode(run)


def test_orbit_plus_dwell_plus_drawing_locates_part_region() -> None:
    events = [
        _event("evt_1", "orbit", {"viewport_orbit_count": 2}),
        _event("evt_2", "part_select", {"part_id": "lid_knob", "label": "lid knob"}),
        _event(
            "evt_3",
            "brush_end",
            {
                "part_id": "lid_knob",
                "artifact_url": "http://files/brush_1.png",
                "bbox": {"x": 1, "y": 2, "w": 3, "h": 4},
            },
        ),
    ]
    bundle = _bundle(events)
    assert "part:lid_knob" in bundle.target_hints
    brush = bundle.interactions[-1]
    assert brush.artifact == {"url": "http://files/brush_1.png", "artifact_type": None}

    ir = asyncio.run(_encode_rule(RuleIntentEncoder(), events))
    assert ir.target.part_id == "lid_knob"
    assert ir.intent.scope == "part"
    assert ir.intent.operation == "explore_variations"


def test_text_plus_brush_encodes_operation_scope_constraints_zh_en() -> None:
    events = [
        _event("evt_1", "text", {"text": "make the lid knob more organic, 但保留 socket"}),
        _event("evt_2", "brush_end", {"part_id": "lid_knob", "mask": {"area_ratio": 0.3}}),
    ]
    bundle = _bundle(events)
    assert bundle.text_segments and "保留 socket" in bundle.text_segments[0]
    assert bundle.interactions[-1].stats["mask_stats"] == {"area_ratio": 0.3}

    ir = asyncio.run(_encode_rule(RuleIntentEncoder(), events))
    assert ir.intent.operation == "explore_variations"
    assert ir.intent.scope == "part"
    assert "preserve non-target region" in ir.intent.constraints


def test_drag_vector_preserves_coordinate_space_and_radius() -> None:
    events = [
        _event(
            "evt_1",
            "drag_end",
            {
                "part_id": "grip",
                "start": [0.1, 0.2, 0.3],
                "end": [0.4, 0.5, 0.6],
                "space": "world",
                "influence_radius": 0.35,
            },
        )
    ]
    bundle = _bundle(events)
    vector = bundle.interactions[0].vector
    assert vector["start"] == [0.1, 0.2, 0.3]
    assert vector["end"] == [0.4, 0.5, 0.6]
    assert vector["space"] == "world"
    assert vector["influence_radius"] == 0.35
    assert bundle.interactions[0].stats["drag_length"] == pytest.approx(
        ((0.3) ** 2 * 3) ** 0.5, abs=1e-3
    )
    ir = asyncio.run(_encode_rule(RuleIntentEncoder(), events))
    assert "respect drag influence radius" in ir.intent.constraints


def test_oversized_base64_and_coordinates_are_dropped_and_counted() -> None:
    events = [
        _event(
            "evt_1",
            "annotation",
            {
                "data_url": "data:image/png;base64," + "A" * 3000,
                "points": [[float(i), float(i), float(i)] for i in range(2000)],
                "artifact_url": "http://files/ann_1.png",
            },
        ),
        _event("evt_2", "malicious", {"__proto__": {"polluted": True}, "javascript": "<script>"}),
    ]
    bundle = _bundle(events)
    assert bundle.interactions[0].artifact == {
        "url": "http://files/ann_1.png",
        "artifact_type": None,
    }
    assert bundle.dropped_summary["dropped_base64_bytes"] >= 3000
    assert bundle.dropped_summary.get("dropped_malicious", 0) == 1
    assert "javascript" not in json.dumps(bundle.to_bounded_json(), ensure_ascii=False)


def test_qwen_encoder_valid_and_repair_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    encoder = QwenIntentEncoder("http://127.0.0.1:9/v1/chat/completions")
    valid_ir = {
        "schema_version": "flowstudio.intent-ir.v1",
        "ir_id": "ir_qwen",
        "run_id": "fsrun_qwen",
        "session_id": "sess_qwen",
        "source_event_ids": ["evt_1"],
        "target": {"part_id": "knob"},
        "observations": {"text": "organic knob"},
        "intent": {"operation": "explore_variations", "scope": "part", "goal": "organic knob"},
        "confidence": 0.8,
        "ambiguity": 0.2,
        "provenance": {"encoder": "qwen3-8b", "fallback_used": False},
    }

    def valid_post(payload: dict):
        return dict(valid_ir)

    monkeypatch.setattr(encoder, "_post_json", valid_post)
    bundle = _bundle([_event("evt_1", "text", {"text": "organic knob"})])
    ir = asyncio.run(encoder.encode(bundle))
    assert ir.ir_id == "ir_qwen"
    assert ir.provenance.fallback_used is False

    # Repair path: first response invalid, second valid.
    calls = {"count": 0}

    def repair_post(payload: dict):
        calls["count"] += 1
        if calls["count"] == 1:
            return {"bad": True}
        return dict(valid_ir)

    monkeypatch.setattr(encoder, "_post_json", repair_post)
    ir2 = asyncio.run(encoder.encode(bundle))
    assert ir2.ir_id == "ir_qwen"
    assert calls["count"] == 2

    # Double invalid -> QwenEncodingError.
    def always_bad(payload: dict):
        return {"bad": True}

    monkeypatch.setattr(encoder, "_post_json", always_bad)
    with pytest.raises(QwenEncodingError):
        asyncio.run(encoder.encode(bundle))


def test_encoding_service_falls_back_to_rules_when_qwen_unconfigured() -> None:
    service = FourStageEncodingService(
        normalizer=EventNormalizer(),
        qwen_encoder=QwenIntentEncoder(None),
        rule_encoder=RuleIntentEncoder(),
    )
    run = FourStageRun(
        run_id="fsrun_fb",
        session_id="sess_fb",
        source_event_ids=["evt_1"],
        events=[_event("evt_1", "text", {"text": "make it cute"})],
    )
    ir = asyncio.run(service.encode(run))
    assert ir.provenance.fallback_used is True
    assert ir.provenance.encoder == "rule-fallback"
    assert ir.intent.operation == "explore_variations"


def test_invalid_qwen_json_fails_encoding_stage_without_fabrication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class AlwaysInvalidEncoder(QwenIntentEncoder):
        async def encode(self, bundle):
            raise QwenEncodingError("invalid model JSON twice")

    store = FourStageStore()
    orchestrator = FourStageOrchestrator(
        store=store,
        encoding_service=AlwaysInvalidEncoder("http://127.0.0.1:9/v1/chat/completions"),
        retrieval_service=FakeRetrievalService(),
        decision_service=FakeDecisionService(),
    )

    async def scenario() -> None:
        run = await orchestrator.create_run(
            FourStageRunCreateRequest(
                session_id="sess_invalid",
                events=[_event("evt_1", "text", {"text": "x"})],
            )
        )
        assert run.stage == FourStageStage.failed
        assert run.failed_stage == FourStageStage.encoding
        assert run.intent_ir is None
        assert "invalid model JSON twice" in run.error["message"]

    asyncio.run(scenario())


def test_encoding_stability_100_runs_no_invalid_json() -> None:
    """Strategy doc 6.4: 100 consecutive runs produce schema-valid IntentIR."""
    rule = RuleIntentEncoder()
    events = [
        _event("evt_1", "orbit", {"viewport_orbit_count": 2}),
        _event("evt_2", "part_select", {"part_id": "lid_knob", "label": "lid knob"}),
        _event("evt_3", "text", {"text": "make the lid knob more organic, 保留 socket"}),
    ]
    run = FourStageRun(
        run_id="fsrun_stability",
        session_id="sess_enc",
        source_event_ids=[event.event_id for event in events],
        events=events,
    )
    for _ in range(100):
        ir = asyncio.run(rule.encode(run))
        IntentIR.model_validate(ir.model_dump(mode="json"))
        assert ir.intent.operation in {"observe", "explore_variations"}


def test_qwen_encoder_stability_100_runs_valid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Strategy doc 6.4: mocked Qwen path stays schema-valid over 100 runs."""
    encoder = QwenIntentEncoder("http://127.0.0.1:9/v1/chat/completions")
    valid_ir = {
        "schema_version": "flowstudio.intent-ir.v1",
        "ir_id": "ir_stable",
        "run_id": "fsrun_stability",
        "session_id": "sess_enc",
        "source_event_ids": ["evt_1"],
        "target": {"part_id": "lid_knob"},
        "observations": {"text": "organic knob"},
        "intent": {"operation": "explore_variations", "scope": "part", "goal": "organic knob"},
        "confidence": 0.8,
        "ambiguity": 0.2,
        "provenance": {"encoder": "qwen3-8b", "fallback_used": False},
    }

    def stable_post(payload):
        return dict(valid_ir)

    monkeypatch.setattr(encoder, "_post_json", stable_post)
    bundle = _bundle([_event("evt_1", "text", {"text": "organic knob"})])
    for _ in range(100):
        ir = asyncio.run(encoder.encode(bundle))
        IntentIR.model_validate(ir.model_dump(mode="json"))


def test_encoding_service_normalizes_qwen_ir_ids() -> None:
    class StubQwen:
        configured = True

        async def encode(self, bundle):
            return IntentIR(
                ir_id="generated",
                run_id="",
                session_id="",
                source_event_ids=[],
                observations=IntentObservations(text="x"),
                intent=IntentCore(operation="refine", scope="part", goal="x"),
                provenance=IntentProvenance(encoder="qwen3-8b", fallback_used=False),
            )

    service = FourStageEncodingService(
        normalizer=EventNormalizer(),
        qwen_encoder=StubQwen(),  # type: ignore[arg-type]
        rule_encoder=RuleIntentEncoder(),
    )
    run = FourStageRun(
        run_id="fsrun_norm",
        session_id="sess_norm",
        episode_id="ep_norm",
        source_event_ids=["evt_1"],
        events=[_event("evt_1", "text", {"text": "x"})],
    )
    ir = asyncio.run(service.encode(run))
    assert ir.ir_id.startswith("ir_")
    assert ir.ir_id != "generated"
    assert ir.run_id == "fsrun_norm"
    assert ir.session_id == "sess_norm"
    assert ir.episode_id == "ep_norm"
    assert ir.source_event_ids == ["evt_1"]


def test_text_part_matching_does_not_read_arm_inside_warm() -> None:
    assert infer_text_part("warm knitted wool material") is None
    assert infer_text_part("change the arm connection") == "arm"
    assert infer_text_parts("preserve the hat, nose, buttons, and arms") == [
        "hat",
        "nose",
        "arm",
        "button",
    ]
