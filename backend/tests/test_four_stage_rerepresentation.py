"""Phase 3 tests: EvidenceAssembler + GeminiClient + DecisionService + Gate."""

from __future__ import annotations

import asyncio

import pytest

from app.models import (
    DecisionIR,
    FourStageRun,
    FourStageRunCreateRequest,
    FourStageStage,
    GateAction,
    IntentCore,
    IntentIR,
    IntentObservations,
    IntentProvenance,
    IntentTarget,
    RetrievalBundle,
    RetrievalMatch,
    UserEvent,
)
from app.services.pipeline.four_stage_orchestrator import (
    FakeEncodingService,
    FourStageOrchestrator,
)
from app.services.rerepresentation.decision_service import (
    FourStageDecisionService,
    RuleDecisionService,
)
from app.services.rerepresentation.evidence_assembler import EvidenceAssembler
from app.services.rerepresentation.gemini_client import (
    GeminiClient,
    GeminiDecisionError,
    GeminiUnavailable,
)
from app.services.storage.four_stage_store import FourStageStore


def _ir(goal: str = "organic lid knob", scope: str = "part") -> IntentIR:
    return IntentIR(
        ir_id="ir_r",
        run_id="run_r",
        session_id="sess_r",
        source_event_ids=["evt_1"],
        target=IntentTarget(part_id="lid_knob", object_type="teapot"),
        observations=IntentObservations(
            text=goal,
            image_refs=[
                "http://files/viewport.png",
                "http://files/brush.png",
                "http://files/ref1.png",
                "http://files/ref2.png",
                "http://files/ref3.png",
            ],
        ),
        intent=IntentCore(
            operation="explore_variations",
            scope=scope,
            goal=goal,
            constraints=["preserve socket"],
        ),
        confidence=0.8,
        ambiguity=0.2,
        provenance=IntentProvenance(encoder="qwen3-8b", fallback_used=False),
    )


def _retrieval() -> RetrievalBundle:
    return RetrievalBundle(
        retrieval_id="ret_r",
        run_id="run_r",
        query_ir_id="ir_r",
        matches=[
            RetrievalMatch(
                prior_ir_id=f"prior_{index}",
                case_id=f"case_{index}",
                sparse_score=0.8,
                metadata_score=0.9,
                outcome_score=0.0,
                final_score=0.85,
                prior_judgement={"recommended_axes": ["Structural"]},
            )
            for index in range(7)
        ],
        abstained=False,
    )


def _run() -> FourStageRun:
    return FourStageRun(
        run_id="run_r",
        session_id="sess_r",
        source_event_ids=["evt_1"],
    )


def test_evidence_assembler_bounds_images_and_marks_prior_untrusted() -> None:
    assembler = EvidenceAssembler(max_images=4)
    evidence = assembler.assemble(
        run=_run(),
        intent_ir=_ir(),
        retrieval=_retrieval(),
        feedback_lookup=lambda case_id: 0.25 if case_id == "case_0" else 0.0,
    )
    assert len(evidence["images"]) == 4
    assert evidence["images"][0]["role"] == "viewport"
    assert evidence["retrieval_evidence"]["untrusted_prior_data"] is True
    assert len(evidence["retrieval_evidence"]["matches"]) == 5
    assert evidence["hard_constraints"] == ["preserve socket"]
    assert evidence["context"]["recent_gate_feedback"]["case_0"] == 0.25
    assert "case_4" in evidence["context"]["recent_gate_feedback"]
    assert "prior_5" not in [m["prior_ir_id"] for m in evidence["retrieval_evidence"]["matches"]]


def test_gemini_client_decide_repair_and_failure_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    client = GeminiClient("https://127.0.0.1:9/v1", "sk-test")
    valid = {
        "schema_version": "flowstudio.decision-ir.v1",
        "decision_id": "decision_g",
        "run_id": "run_g",
        "intent_ir_id": "ir_g",
        "retrieval_id": "ret_g",
        "summary": "test",
        "recommended_scope": "part",
        "options": [
            {
                "option_id": "opt_1",
                "label": "gourd knob",
                "rationale": "r",
                "confidence": 0.7,
                "evidence_refs": ["prior_1"],
                "constraints": ["preserve socket"],
                "divergence_seeds": ["soft taper"],
            }
        ],
        "needs_clarification": False,
        "confidence": 0.7,
        "model": "gemini-3.5-flash",
    }

    def valid_post(payload):
        return dict(valid)

    monkeypatch.setattr(client, "_post_json", valid_post)
    decision = asyncio.run(client.decide({"evidence": "x"}, run_id="run_g"))
    assert decision.decision_id == "decision_g"

    calls = {"count": 0}

    def repair_post(payload):
        calls["count"] += 1
        if calls["count"] == 1:
            return {"bad": True}
        return dict(valid)

    monkeypatch.setattr(client, "_post_json", repair_post)
    repaired = asyncio.run(client.decide({"evidence": "x"}))
    assert repaired.decision_id == "decision_g"
    assert calls["count"] == 2

    def always_bad(payload):
        return {"bad": True}

    monkeypatch.setattr(client, "_post_json", always_bad)
    with pytest.raises(GeminiDecisionError):
        asyncio.run(client.decide({"evidence": "x"}))


def test_gemini_client_normalizes_option_id_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = GeminiClient("https://127.0.0.1:9/v1", "sk-test")

    def alias_post(payload):
        return {
            "schema_version": "flowstudio.decision-ir.v1",
            "decision_id": "decision_alias",
            "run_id": "run_a",
            "intent_ir_id": "ir_a",
            "retrieval_id": "ret_a",
            "summary": "alias test",
            "recommended_scope": "part",
            "options": [
                {
                    "id": "gemini_opt_1",
                    "title": "Gourd knob",
                    "reason": "soft",
                    "confidence": 0.8,
                    "seeds": ["gourd", "soft taper"],
                    "hard_constraints": ["preserve socket"],
                }
            ],
            "needs_clarification": False,
            "confidence": 0.8,
            "model": "gemini-3.5-flash",
        }

    monkeypatch.setattr(client, "_post_json", alias_post)
    decision = asyncio.run(client.decide({"evidence": "x"}))
    option = decision.options[0]
    assert option.option_id == "gemini_opt_1"
    assert option.label == "Gourd knob"
    assert option.rationale == "soft"
    assert option.divergence_seeds == ["gourd", "soft taper"]
    assert option.constraints == ["preserve socket"]


def test_gemini_client_unconfigured_raises_unavailable() -> None:
    client = GeminiClient("https://127.0.0.1:9/v1", "")
    with pytest.raises(GeminiUnavailable):
        asyncio.run(client.decide({"evidence": "x"}))


def test_gemini_client_consistency_guard_and_id_overlay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = GeminiClient("https://127.0.0.1:9/v1", "sk-test")

    def empty_options_post(payload):
        return {
            "schema_version": "flowstudio.decision-ir.v1",
            "run_id": "wrong_run",
            "intent_ir_id": None,
            "retrieval_id": None,
            "summary": "no options",
            "recommended_scope": "part",
            "options": [],
            "needs_clarification": False,
            "confidence": 0.2,
            "model": "gemini-3.5-flash",
        }

    monkeypatch.setattr(client, "_post_json", empty_options_post)
    decision = asyncio.run(
        client.decide(
            {
                "intent_ir": {"ir_id": "ir_overlay"},
                "retrieval_evidence": {"retrieval_id": "ret_overlay"},
            },
            run_id="run_overlay",
        )
    )
    assert decision.run_id == "run_overlay"
    assert decision.decision_id.startswith("dec_run_overlay_")
    assert decision.intent_ir_id == "ir_overlay"
    assert decision.retrieval_id == "ret_overlay"
    assert decision.needs_clarification is True
    assert decision.clarification_question


def test_decision_service_rule_fallback_and_clarification() -> None:
    service = FourStageDecisionService(
        assembler=EvidenceAssembler(),
        gemini_client=GeminiClient("https://127.0.0.1:9/v1", "sk-test"),
        rule_decision=RuleDecisionService(),
        enabled=False,
    )
    decision = asyncio.run(service.decide(_run(), _ir(), _retrieval()))
    assert decision.model == "rule-fallback"
    assert len(decision.options) >= 2
    assert decision.options[0].constraints == ["preserve socket"]

    weak = asyncio.run(service.decide(_run(), _ir(goal=""), _retrieval()))
    assert weak.needs_clarification is True
    assert weak.options == []


def test_decision_service_uses_gemini_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    class StubGemini:
        configured = True

        async def decide(self, evidence, *, run_id=None):
            return DecisionIR(
                decision_id="decision_gemini",
                run_id=run_id or "run_r",
                intent_ir_id="ir_r",
                retrieval_id="ret_r",
                summary="Gemini decision",
                recommended_scope="part",
                options=[],
                needs_clarification=False,
                confidence=0.9,
                model="gemini-3.5-flash",
            )

    service = FourStageDecisionService(
        assembler=EvidenceAssembler(),
        gemini_client=StubGemini(),  # type: ignore[arg-type]
        rule_decision=RuleDecisionService(),
        enabled=True,
    )
    decision = asyncio.run(service.decide(_run(), _ir(), _retrieval()))
    assert decision.model == "gemini-3.5-flash"
    assert decision.decision_id == "decision_gemini"


def test_decision_service_falls_back_to_rules_when_gemini_clarifies_with_evidence() -> None:
    class ClarifyingGemini:
        configured = True

        async def decide(self, evidence, *, run_id=None):
            return DecisionIR(
                decision_id="decision_clarify",
                run_id=run_id or "run_r",
                intent_ir_id="ir_r",
                retrieval_id="ret_r",
                summary="clarify",
                recommended_scope="part",
                options=[],
                needs_clarification=True,
                clarification_question="which direction?",
                confidence=0.3,
                model="gemini-3.5-flash",
            )

    service = FourStageDecisionService(
        assembler=EvidenceAssembler(),
        gemini_client=ClarifyingGemini(),  # type: ignore[arg-type]
        rule_decision=RuleDecisionService(),
        enabled=True,
    )
    # Evidence present (goal + retrieval matches) -> labeled rule fallback with options.
    decision = asyncio.run(service.decide(_run(), _ir(), _retrieval()))
    assert decision.model == "rule-fallback"
    assert decision.options
    assert decision.needs_clarification is False

    # No evidence -> keep the genuine clarification.
    weak = asyncio.run(
        service.decide(
            _run(),
            _ir(goal=""),
            RetrievalBundle(
                retrieval_id="ret_w",
                run_id="run_r",
                query_ir_id="ir_r",
                abstained=True,
                abstain_reason="no prior",
            ),
        )
    )
    assert weak.needs_clarification is True
    assert weak.options == []


def test_gate_request_revision_and_clarify() -> None:
    store = FourStageStore()
    orchestrator = FourStageOrchestrator(
        store=store,
        encoding_service=FakeEncodingService(),
        retrieval_service=None,  # replaced below
        decision_service=RuleDecisionService(),
    )

    class StubRetrieval:
        async def retrieve(self, run, intent_ir):
            return _retrieval()

    orchestrator.retrieval_service = StubRetrieval()  # type: ignore[assignment]

    async def scenario() -> None:
        run = await orchestrator.create_run(
            FourStageRunCreateRequest(
                session_id="sess_r",
                events=[
                    UserEvent(
                        type="text",
                        event_id="evt_1",
                        session_id="sess_r",
                        payload={"text": "make the lid knob organic"},
                    )
                ],
            )
        )
        assert run.stage == FourStageStage.awaiting_gate
        first_decision_id = run.decision.decision_id

        revised = await orchestrator.resolve_gate(
            run.run_id,
            first_decision_id,
            GateAction.request_revision,
            user_revision="more gourd-like",
        )
        assert revised.stage == FourStageStage.awaiting_gate
        assert revised.decision.decision_id != first_decision_id
        assert revised.gate_decision.action == GateAction.request_revision

        clarified = await orchestrator.resolve_gate(
            run.run_id,
            revised.decision.decision_id,
            GateAction.clarify,
            user_revision="focus on silhouette",
        )
        assert clarified.stage == FourStageStage.awaiting_gate
        assert clarified.gate_decision.action == GateAction.clarify

    asyncio.run(scenario())


def test_model_call_audits_store_rows_without_key_material() -> None:
    store = FourStageStore()
    store.record_model_call(
        model="gemini-3.5-flash",
        provider="128api",
        run_id="run_a",
        latency_ms=123,
        prompt_tokens=100,
        completion_tokens=50,
    )
    calls = store.recent_model_calls()
    assert len(calls) == 1
    assert calls[0]["model"] == "gemini-3.5-flash"
    assert calls[0]["latency_ms"] == 123
    serialized = str(calls)
    assert "sk-" not in serialized and "Bearer" not in serialized


def test_gemini_client_audit_callback_persists_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json as _json

    store = FourStageStore()
    client = GeminiClient(
        "https://127.0.0.1:9/v1",
        "sk-test",
        audit=store.record_model_call,
    )

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return _json.dumps(
                {
                    "id": "chatcmpl_audit_1",
                    "usage": {"prompt_tokens": 10, "completion_tokens": 20},
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    '{"schema_version":"flowstudio.decision-ir.v1",'
                                    '"decision_id":"d1","run_id":"run_a","intent_ir_id":"ir_a",'
                                    '"retrieval_id":"ret_a","summary":"s","recommended_scope":"part",'
                                    '"options":[{"option_id":"o1","label":"A","confidence":0.5}],'
                                    '"needs_clarification":false,"confidence":0.5,'
                                    '"model":"gemini-3.5-flash"}'
                                )
                            }
                        }
                    ],
                }
            ).encode("utf-8")

    monkeypatch.setattr(
        client,
        "_open",
        lambda request, timeout: FakeResponse(),
    )
    parsed = client._post_json(
        {"model": "gemini-3.5-flash", "messages": [{"role": "user", "content": "x"}]}
    )
    assert parsed["decision_id"] == "d1"
    calls = store.recent_model_calls()
    assert len(calls) == 1
    assert calls[0]["model"] == "gemini-3.5-flash"
    assert calls[0]["prompt_tokens"] == 10
    assert calls[0]["completion_tokens"] == 20
    assert calls[0]["request_id"] == "chatcmpl_audit_1"
    assert "sk-" not in str(calls)
