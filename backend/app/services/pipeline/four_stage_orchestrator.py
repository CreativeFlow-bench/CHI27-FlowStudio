"""FourStageOrchestrator: the four-stage state machine.

Stages: raw_events -> encoding -> retrieval -> re_representation ->
awaiting_gate -> generation -> completed | failed | cancelled.

Phase 0 scope: state transitions + schema-valid fake adapters. Later phases
replace the fake services with the real Qwen encoder, sparse retriever, Gemini
decision service and generation spec builder/scheduler without changing the
orchestrator's transition rules.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol
from uuid import uuid4

from app.models import (
    FOUR_STAGE_RUN_SCHEMA_VERSION,
    DecisionIR,
    DecisionOption,
    FourStageRun,
    FourStageRunCreateRequest,
    FourStageStage,
    GateAction,
    GateDecision,
    IntentCore,
    IntentIR,
    IntentObservations,
    IntentProvenance,
    IntentTarget,
    RetrievalBundle,
    SemanticDivergenceParams,
    SemanticDivergenceResponse,
    ScopeGate,
    DivergenceSelection,
    is_concrete_object_type,
    UserEvent,
    now_utc,
)
from app.services.storage.four_stage_store import FourStageStore
from app.services.storage.websocket_manager import WebSocketManager
from app.services.divergence.semantic_divergence_service import (
    SemanticDivergenceStateConflict,
    SemanticDivergenceProgress,
)

logger = logging.getLogger("flowstudio.four_stage")


class FourStageError(Exception):
    """Base error for four-stage pipeline failures."""


class FourStageInvalidTransition(FourStageError):
    pass


class FourStageConflict(FourStageError):
    pass


class EncodingService(Protocol):
    async def encode(self, run: FourStageRun) -> IntentIR: ...


class RetrievalService(Protocol):
    async def retrieve(self, run: FourStageRun, intent_ir: IntentIR) -> RetrievalBundle: ...


class DecisionService(Protocol):
    async def decide(
        self,
        run: FourStageRun,
        intent_ir: IntentIR,
        retrieval: RetrievalBundle,
    ) -> DecisionIR: ...


class GenerationService(Protocol):
    def build_spec(self, run: FourStageRun, selected_option_id: str) -> Any: ...


class SemanticDivergenceServiceProtocol(Protocol):
    async def diverge(
        self,
        run: FourStageRun,
        params: SemanticDivergenceParams,
    ) -> SemanticDivergenceResponse: ...


_ALLOWED_NEXT: dict[FourStageStage, set[FourStageStage]] = {
    FourStageStage.raw_events: {FourStageStage.encoding, FourStageStage.failed, FourStageStage.cancelled},
    FourStageStage.encoding: {FourStageStage.retrieval, FourStageStage.failed, FourStageStage.cancelled},
    FourStageStage.retrieval: {FourStageStage.re_representation, FourStageStage.failed, FourStageStage.cancelled},
    FourStageStage.re_representation: {FourStageStage.awaiting_gate, FourStageStage.failed, FourStageStage.cancelled},
    FourStageStage.awaiting_gate: {FourStageStage.generation, FourStageStage.failed, FourStageStage.cancelled},
    FourStageStage.generation: {FourStageStage.completed, FourStageStage.failed, FourStageStage.cancelled},
    FourStageStage.completed: set(),
    FourStageStage.failed: set(),
    FourStageStage.cancelled: set(),
}

_PIPELINE_ORDER = (
    FourStageStage.encoding,
    FourStageStage.retrieval,
    FourStageStage.re_representation,
)


class FakeEncodingService:
    """Phase 0 schema-valid encoding adapter (clearly marked as fallback)."""

    async def encode(self, run: FourStageRun) -> IntentIR:
        text: str | None = None
        orbit_count = 0
        selection_type: str | None = None
        part_id: str | None = None
        asset_id: str | None = None
        object_type: str | None = None
        for event in run.source_event_ids:
            pass  # source details live in the run row; fake keeps event-level summary minimal
        # The fake adapter only has event ids; pull text from a stored summary is
        # not possible at phase 0, so the encoder output is intentionally a
        # neutral observation until Phase 1 wires the real normalizer.
        del text, orbit_count, selection_type, part_id, asset_id, object_type
        return IntentIR(
            ir_id=f"ir_{uuid4().hex[:10]}",
            run_id=run.run_id,
            session_id=run.session_id,
            episode_id=run.episode_id,
            source_event_ids=list(run.source_event_ids),
            target=IntentTarget(asset_id=None),
            observations=IntentObservations(
                interaction_summary={"event_count": len(run.source_event_ids)}
            ),
            intent=IntentCore(
                operation="observe",
                scope="whole",
                goal=None,
                constraints=[],
                preferred_axes=[],
            ),
            confidence=0.35,
            ambiguity=0.65,
            provenance=IntentProvenance(
                encoder="rule-fallback",
                encoder_version="phase0-fake",
                prompt_version="intent-ir-v1",
                fallback_used=True,
            ),
        )


class FakeRetrievalService:
    """Phase 0 adapter: abstains honestly instead of fabricating matches."""

    async def retrieve(self, run: FourStageRun, intent_ir: IntentIR) -> RetrievalBundle:
        return RetrievalBundle(
            retrieval_id=f"ret_{uuid4().hex[:10]}",
            run_id=run.run_id,
            query_ir_id=intent_ir.ir_id,
            retriever="fake/phase0",
            matches=[],
            abstained=True,
            abstain_reason="phase0 fake retriever: no real index consulted",
        )


class FakeDecisionService:
    """Phase 0 adapter: emits a single schema-valid option from the IntentIR."""

    async def decide(
        self,
        run: FourStageRun,
        intent_ir: IntentIR,
        retrieval: RetrievalBundle,
    ) -> DecisionIR:
        goal = intent_ir.intent.goal or "explore design variations"
        return DecisionIR(
            decision_id=f"decision_{uuid4().hex[:10]}",
            run_id=run.run_id,
            intent_ir_id=intent_ir.ir_id,
            retrieval_id=retrieval.retrieval_id,
            summary=f"Phase 0 fake decision for: {goal}",
            recommended_scope=intent_ir.intent.scope,
            options=[
                DecisionOption(
                    option_id="opt_1",
                    label=goal,
                    rationale="Phase 0 fake option — replace with Gemini in Phase 3.",
                    confidence=0.4,
                    evidence_refs=[],
                    constraints=list(intent_ir.intent.constraints),
                    divergence_seeds=["silhouette", "material", "ornament"],
                )
            ],
            needs_clarification=False,
            confidence=0.4,
            model="fake/phase0",
        )


class FourStageOrchestrator:
    def __init__(
        self,
        store: FourStageStore,
        *,
        encoding_service: EncodingService,
        retrieval_service: RetrievalService,
        decision_service: DecisionService,
        generation_service: GenerationService | None = None,
        semantic_divergence_service: SemanticDivergenceServiceProtocol | None = None,
        websocket_manager: WebSocketManager | None = None,
    ) -> None:
        self.store = store
        self.encoding_service = encoding_service
        self.retrieval_service = retrieval_service
        self.decision_service = decision_service
        self.generation_service = generation_service
        self.semantic_divergence_service = semantic_divergence_service
        self.websocket_manager = websocket_manager

    async def create_run(
        self,
        request: FourStageRunCreateRequest,
        *,
        auto_advance: bool = True,
    ) -> FourStageRun:
        if request.idempotency_key:
            existing = self.store.find_by_idempotency(
                request.session_id, request.idempotency_key
            )
            if existing is not None:
                return existing
        run = FourStageRun(
            run_id=f"fsrun_{uuid4().hex[:10]}",
            session_id=request.session_id,
            idempotency_key=request.idempotency_key,
            episode_id=request.episode_id,
            stage=FourStageStage.raw_events,
            run_hy3d=request.run_hy3d,
            events=list(request.events),
            source_event_ids=[event.event_id for event in request.events],
            source_context=request.source_context,
        )
        self.store.save_run(run)
        await self._emit(
            run,
            "four_stage.encoding_started",
            {"event_count": len(request.events), "episode_id": request.episode_id},
        )
        if auto_advance:
            await self._run_pipeline(run)
        return self.store.get_run(run.run_id) or run

    async def append_events(
        self,
        run_id: str,
        events: list[UserEvent],
        *,
        auto_advance: bool = True,
    ) -> FourStageRun:
        """把新行为事件追加进已有 run（交互中持续编码），并可选推进阶段。"""
        run = self.store.get_run(run_id)
        if run is None:
            raise FourStageError("run not found")
        if run.stage in {
            FourStageStage.completed,
            FourStageStage.failed,
            FourStageStage.cancelled,
        }:
            raise FourStageConflict(f"cannot append events to run in stage {run.stage}")
        existing_ids = set(run.source_event_ids)
        fresh = [event for event in events if event.event_id not in existing_ids]
        if not fresh:
            return run
        run.events = [*run.events, *fresh]
        run.source_event_ids = [*run.source_event_ids, *(event.event_id for event in fresh)]
        self.store.save_run(run)
        if run.stage == FourStageStage.raw_events:
            # 首次编码：事件足够即编码，编码完成停在 encoding，
            # 由前端在意图判断 / 点关键词时 advance 推进检索与决策。
            ok = await self._execute_stage(run, FourStageStage.encoding)
            if ok:
                await self._emit(
                    run,
                    "four_stage.encoding_completed",
                    {"stage": FourStageStage.encoding.value},
                )
        elif run.stage == FourStageStage.encoding:
            # 已在编码阶段：新事件更新 run 即可（intent_ir 保持不变），
            # 前端明确 advance 时才重跑编码+推进。
            pass
        return self.store.get_run(run.run_id) or run

    async def advance_run(self, run_id: str, target: str | None = None) -> FourStageRun:
        """从编码开始推进到目标阶段（默认跑到 awaiting_gate）。

        交互流式：意图判断 → target=retrieval（停在检索）；
        点关键词 → 无 target 或 target=re_representation（跑到 Gate）。
        """
        run = self.store.get_run(run_id)
        if run is None:
            raise FourStageError("run not found")
        if run.stage in {
            FourStageStage.completed,
            FourStageStage.failed,
            FourStageStage.cancelled,
        }:
            raise FourStageConflict(f"cannot advance run in stage {run.stage}")
        if target:
            try:
                target_stage = FourStageStage(target)
            except ValueError as exc:
                raise FourStageError(f"unknown target stage: {target}") from exc
            if target_stage not in _PIPELINE_ORDER and target_stage != FourStageStage.awaiting_gate:
                raise FourStageError(f"stage {target} is not a pipeline stage")
            if target_stage == FourStageStage.re_representation:
                # 阶段3：重新编码（run.events 已含最新行为与关键词）→ 重新检索 →
                # 决策 → awaiting_gate。不切换中间阶段，避免非法转移。
                return await self._reencode_to_gate(run)
            # target == retrieval：从当前阶段继续，跳过已完成阶段。
            start_idx = _PIPELINE_ORDER.index(run.stage) if run.stage in _PIPELINE_ORDER else 0
            for stage in _PIPELINE_ORDER[start_idx:]:
                if stage == run.stage:
                    # 已在该阶段：不重复执行（例如已停在 retrieval 时 target=retrieval）。
                    if stage == target_stage:
                        return self.store.get_run(run.run_id) or run
                    continue
                ok = await self._execute_stage(run, stage)
                if not ok:
                    return self.store.get_run(run.run_id) or run
                if stage == target_stage:
                    await self._emit(
                        run,
                        {
                            FourStageStage.encoding: "four_stage.encoding_completed",
                            FourStageStage.retrieval: "four_stage.retrieval_completed",
                            FourStageStage.re_representation: "four_stage.decision_completed",
                        }[stage],
                        {"stage": stage.value},
                    )
                    return self.store.get_run(run.run_id) or run
            # target 是 awaiting_gate：跑完全部后停在 Gate。
            self._transition(run, FourStageStage.awaiting_gate)
            self.store.save_run(run)
            await self._emit(
                run,
                "four_stage.awaiting_gate",
                {
                    "decision_id": run.decision.decision_id if run.decision else None,
                    "gate_question": run.scope_gate.question if run.scope_gate else None,
                },
            )
        else:
            if run.stage == FourStageStage.awaiting_gate:
                # Gate 已打开：无需推进。
                return run
            if run.stage in _PIPELINE_ORDER:
                # 已在编码/检索/决策阶段：用最新事件重新编码到 Gate，
                # 避免重复执行已完成阶段（非法转移）。
                return await self._reencode_to_gate(run)
            await self._run_pipeline(run)
        return self.store.get_run(run.run_id) or run

    async def _reencode_to_gate(self, run: FourStageRun) -> FourStageRun:
        """阶段3：用最新事件（含点选关键词）重新编码→检索→决策，停在 awaiting_gate。"""
        try:
            run.intent_ir = await self.encoding_service.encode(run)
            run.retrieval = await self.retrieval_service.retrieve(run, run.intent_ir)
            run.decision = await self.decision_service.decide(run, run.intent_ir, run.retrieval)
            self._set_scope_gate(run)
        except Exception as exc:
            logger.exception("four-stage re-encode failed run=%s", run.run_id)
            run.error = {
                "code": "stage_failed",
                "message": str(exc),
                "retryable": True,
            }
            run.failed_stage = FourStageStage.re_representation
            self.store.save_run(run)
            await self._emit(
                run,
                "four_stage.failed",
                {
                    "stage": FourStageStage.re_representation.value,
                    "message": str(exc),
                },
            )
            return run
        if run.stage == FourStageStage.raw_events:
            self._transition(run, FourStageStage.encoding)
        if run.stage == FourStageStage.encoding:
            self._transition(run, FourStageStage.retrieval)
        if run.stage == FourStageStage.retrieval:
            self._transition(run, FourStageStage.re_representation)
        if run.stage == FourStageStage.re_representation:
            self._transition(run, FourStageStage.awaiting_gate)
        self.store.save_run(run)
        await self._emit(
            run,
            "four_stage.awaiting_gate",
            {
                "decision_id": run.decision.decision_id if run.decision else None,
                "gate_question": run.scope_gate.question if run.scope_gate else None,
            },
        )
        return run

    async def retry_run(self, run_id: str) -> FourStageRun:
        run = self.store.get_run(run_id)
        if run is None:
            raise FourStageError("run not found")
        if run.stage != FourStageStage.failed:
            raise FourStageConflict(
                f"retry only allowed on failed runs, current stage={run.stage}"
            )
        target = run.failed_stage or FourStageStage.encoding
        run.retry_count += 1
        run.error = None
        run.failed_stage = None
        if target == FourStageStage.encoding:
            run.intent_ir = None
            run.retrieval = None
            run.decision = None
        elif target == FourStageStage.retrieval:
            run.retrieval = None
            run.decision = None
        elif target == FourStageStage.re_representation:
            run.decision = None
        run.stage = FourStageStage.raw_events
        self.store.save_run(run)
        await self._run_pipeline(run, start_at=target)
        return self.store.get_run(run.run_id) or run

    async def cancel_run(self, run_id: str) -> FourStageRun:
        run = self.store.get_run(run_id)
        if run is None:
            raise FourStageError("run not found")
        if run.stage in {
            FourStageStage.completed,
            FourStageStage.failed,
            FourStageStage.cancelled,
        }:
            raise FourStageConflict(f"cannot cancel run in stage {run.stage}")
        if self.generation_service is not None and hasattr(self.generation_service, "cancel_job"):
            for job in self.store.list_generation_jobs(run.run_id):
                if job.get("status") in {"queued", "running"}:
                    await self.generation_service.cancel_job(str(job["job_id"]))
        self._transition(run, FourStageStage.cancelled)
        run.completed_at = now_utc()
        self.store.save_run(run)
        await self._emit(
            run,
            "four_stage.cancelled",
            {"reason": "user requested cancel"},
        )
        return run

    async def resolve_gate(
        self,
        run_id: str,
        decision_id: str,
        action: GateAction,
        *,
        selected_option_id: str | None = None,
        user_revision: str | None = None,
        reason: str | None = None,
        auto_generate: bool = True,
        divergence_params: SemanticDivergenceParams | None = None,
        run_divergence: bool = True,
    ) -> FourStageRun:
        """Resolve the user Gate. Implemented fully from Phase 3 on.

        ``run_divergence=False`` accepts the Gate and returns immediately so the
        browser SSE can own the progress stream without racing a silent worker.
        """
        run = self.store.get_run(run_id)
        if run is None:
            raise FourStageError("run not found")
        if run.stage != FourStageStage.awaiting_gate:
            raise FourStageConflict(
                f"gate requires awaiting_gate stage, current stage={run.stage}"
            )
        if run.decision is None or run.decision.decision_id != decision_id:
            raise FourStageError("decision not found for this run")

        if action == GateAction.accept_option:
            if selected_option_id is None and run.decision.options:
                selected_option_id = max(
                    run.decision.options,
                    key=lambda option: option.confidence,
                ).option_id
            # Fast Gate may ship with an empty options list (scope question only).
            # Synthesize a stable direction id so keyword Generate can proceed.
            if selected_option_id is None:
                selected_option_id = f"scope_{run.decision.decision_id}"
            option_ids = {option.option_id for option in run.decision.options}
            if option_ids and selected_option_id not in option_ids:
                raise FourStageError(
                    f"unknown option {selected_option_id}; valid={sorted(option_ids)}"
                )
            run.gate_decision = GateDecision(
                decision_id=decision_id,
                run_id=run.run_id,
                action=GateAction.accept_option,
                selected_option_id=selected_option_id,
                reason=reason,
            )
            if run.scope_gate is None:
                self._set_scope_gate(run)
            if run.scope_gate is not None:
                run.scope_gate.status = "accepted"
                run.scope_gate.user_action = "accept"
            self._record_retrieval_feedback(run, "accepted", selected_option_id)
            self.store.save_run(run)
            await self._emit(
                run,
                "four_stage.gate_resolved",
                {
                    "action": action.value,
                    "selected_option_id": selected_option_id,
                    "auto_generate": auto_generate,
                },
            )
            if not run_divergence:
                return self.store.get_run(run.run_id) or run
            if self.semantic_divergence_service is None:
                # Keep the lower-level four-stage API usable for callers that
                # intentionally provide only the legacy adapters. The
                # interaction orchestrator always supplies the durable
                # divergence worker; this branch is a compatibility fallback,
                # not the user-facing Gate path.
                if auto_generate:
                    if self.generation_service is None or run.gate_decision.selected_option_id is None:
                        raise FourStageError("generation service or selected direction is not ready")
                    run.generation_spec = self.generation_service.build_spec(
                        run, run.gate_decision.selected_option_id
                    )
                    self._transition(run, FourStageStage.generation)
                    self.store.save_run(run)
                    await self._emit(
                        run,
                        "four_stage.generation_queued",
                        {
                            "generation_id": run.generation_spec.generation_id,
                            "candidate_count": run.generation_spec.candidate_count,
                        },
                    )
                    await self.generation_service.start_generation(
                        run, run.generation_spec
                    )
                    return self.store.get_run(run.run_id) or run
                return run
            params = divergence_params or SemanticDivergenceParams()
            try:
                semantic_divergence = await self.semantic_divergence_service.diverge(
                    run, params
                )
            except SemanticDivergenceStateConflict as exc:
                raise FourStageConflict(str(exc)) from exc
            except Exception as exc:
                raise FourStageError(f"semantic divergence failed: {exc}") from exc
            if semantic_divergence.status != "completed" or not semantic_divergence.candidates:
                reason = semantic_divergence.fallback_reason or semantic_divergence.status
                raise FourStageError(
                    f"semantic divergence failed: no valid candidates ({reason})"
                )
            current = self.store.get_run(run.run_id)
            if not self._has_current_accepted_gate(current, decision_id):
                raise FourStageConflict(
                    "run decision or accepted Gate changed during semantic divergence"
                )
            if (
                current.semantic_divergence is None
                or current.semantic_divergence.request_key
                != semantic_divergence.request_key
            ):
                raise FourStageConflict("semantic divergence response was superseded")
            if auto_generate:
                # Legacy callers may combine Gate + Generate only after an
                # explicit selection has already been persisted. Task 7 owns
                # candidate-ID and prompt-phrase resolution.
                if current.divergence_selection is not None:
                    await self.start_generation(current.run_id)
                    current = self.store.get_run(current.run_id) or current
            return current

        if action == GateAction.reject_all:
            # Deprecated path (V1.1): frontend now maps "reject" to request_revision
            # so a rejected direction always re-decides and re-opens the Gate.
            # Kept for API compatibility and retrieval feedback semantics.
            logger.warning(
                "gate action reject_all is deprecated run=%s decision=%s; "
                "frontend should send request_revision instead",
                run.run_id,
                decision_id,
            )
            self._record_retrieval_feedback(run, "rejected", None)
            run.gate_decision = GateDecision(
                decision_id=decision_id,
                run_id=run.run_id,
                action=GateAction.reject_all,
                reason=reason,
            )
            if run.scope_gate is not None:
                run.scope_gate.status = "rejected"
                run.scope_gate.user_action = "reject"
            run.semantic_divergence = None
            self.store.save_run(run)
            await self._emit(
                run,
                "four_stage.gate_resolved",
                {"action": action.value, "selected_option_id": None},
            )
            return run

        if action == GateAction.request_revision:
            revised = await self.decision_service.decide(
                run,
                run.intent_ir,
                run.retrieval,
            )
            run.decision = revised
            self._set_scope_gate(run)
            run.semantic_divergence = None
            run.gate_decision = GateDecision(
                decision_id=decision_id,
                run_id=run.run_id,
                action=GateAction.request_revision,
                user_revision=user_revision,
                reason=reason,
            )
            self.store.save_run(run)
            await self._emit(
                run,
                "four_stage.decision_completed",
                {"decision_id": revised.decision_id},
            )
            await self._emit(
                run,
                "four_stage.awaiting_gate",
                {
                    "decision_id": revised.decision_id,
                    "gate_question": run.scope_gate.question if run.scope_gate else None,
                },
            )
            return run

        if action == GateAction.clarify:
            run.gate_decision = GateDecision(
                decision_id=decision_id,
                run_id=run.run_id,
                action=GateAction.clarify,
                user_revision=user_revision,
                reason=reason,
            )
            self.store.save_run(run)
            await self._emit(
                run,
                "four_stage.gate_resolved",
                {"action": action.value, "selected_option_id": None},
            )
            return run

        raise FourStageError(f"unsupported gate action: {action}")

    async def refresh_semantic_divergence(
        self,
        run_id: str,
        params: SemanticDivergenceParams,
    ) -> SemanticDivergenceResponse:
        run = self.store.get_run(run_id)
        if run is None:
            raise FourStageError("run not found")
        if run.stage != FourStageStage.awaiting_gate:
            raise FourStageConflict(
                "semantic divergence refresh requires an awaiting_gate run"
            )
        preflight = bool(getattr(params, "preflight", False))
        if not preflight and not self._has_current_accepted_gate(run):
            raise FourStageConflict(
                "semantic divergence refresh requires an unchanged accepted Gate"
            )
        if self.semantic_divergence_service is None:
            raise FourStageError("semantic divergence service is not configured")
        decision_id = run.decision.decision_id
        try:
            response = await self.semantic_divergence_service.diverge(run, params)
        except SemanticDivergenceStateConflict as exc:
            raise FourStageConflict(str(exc)) from exc
        except Exception as exc:
            raise FourStageError(f"semantic divergence failed: {exc}") from exc
        if response.status != "completed" or not response.candidates:
            reason = response.fallback_reason or response.status
            raise FourStageError(
                f"semantic divergence failed: no valid candidates ({reason})"
            )
        current = self.store.get_run(run_id)
        if preflight:
            if (
                current is None
                or current.stage != FourStageStage.awaiting_gate
                or current.decision is None
                or current.decision.decision_id != decision_id
            ):
                raise FourStageConflict("run decision changed during semantic divergence")
        elif not self._has_current_accepted_gate(current, decision_id):
            raise FourStageConflict("run decision changed during semantic divergence")
        if (
            current.semantic_divergence is None
            or current.semantic_divergence.request_key != response.request_key
        ):
            raise FourStageConflict("semantic divergence response was superseded")
        return current.semantic_divergence

    async def refresh_semantic_divergence_stream(
        self,
        run_id: str,
        params: SemanticDivergenceParams,
        on_progress: SemanticDivergenceProgress,
    ) -> SemanticDivergenceResponse:
        """SSE-friendly variant of :meth:`refresh_semantic_divergence`.

        Emits incremental ``phase`` events through ``on_progress`` while
        preserving the same guard contract as the JSON variant.
        """
        run = self.store.get_run(run_id)
        if run is None:
            raise FourStageError("run not found")
        if run.stage != FourStageStage.awaiting_gate:
            raise FourStageConflict(
                "semantic divergence refresh requires an awaiting_gate run"
            )
        preflight = bool(getattr(params, "preflight", False))
        if not preflight and not self._has_current_accepted_gate(run):
            raise FourStageConflict(
                "semantic divergence refresh requires an unchanged accepted Gate"
            )
        if self.semantic_divergence_service is None:
            raise FourStageError("semantic divergence service is not configured")
        decision_id = run.decision.decision_id
        try:
            response = await self.semantic_divergence_service.diverge_with_progress(
                run, params, on_progress=on_progress
            )
        except SemanticDivergenceStateConflict as exc:
            raise FourStageConflict(str(exc)) from exc
        except Exception as exc:
            raise FourStageError(f"semantic divergence failed: {exc}") from exc
        if response.status != "completed" or not response.candidates:
            reason = response.fallback_reason or response.status
            raise FourStageError(
                f"semantic divergence failed: no valid candidates ({reason})"
            )
        current = self.store.get_run(run_id)
        if preflight:
            if (
                current is None
                or current.stage != FourStageStage.awaiting_gate
                or current.decision is None
                or current.decision.decision_id != decision_id
            ):
                raise FourStageConflict("run decision changed during semantic divergence")
        elif not self._has_current_accepted_gate(current, decision_id):
            raise FourStageConflict("run decision changed during semantic divergence")
        if (
            current.semantic_divergence is None
            or current.semantic_divergence.request_key != response.request_key
        ):
            raise FourStageConflict("semantic divergence response was superseded")
        return current.semantic_divergence

    @staticmethod
    def _has_current_accepted_gate(
        run: FourStageRun | None,
        decision_id: str | None = None,
    ) -> bool:
        if (
            run is None
            or run.stage != FourStageStage.awaiting_gate
            or run.decision is None
            or run.gate_decision is None
            or run.gate_decision.action != GateAction.accept_option
            or run.gate_decision.decision_id != run.decision.decision_id
            or run.scope_gate is None
            or run.scope_gate.status != "accepted"
        ):
            return False
        return decision_id is None or run.decision.decision_id == decision_id

    async def start_generation(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        if run is None:
            raise FourStageError("run not found")
        # Soft-revive a failed Generate so selected keywords can fire again.
        if run.stage == FourStageStage.failed and self._has_current_accepted_gate(run):
            run.stage = FourStageStage.awaiting_gate
            run.error = None
            run.failed_stage = None
            run.generation_spec = None
            run.generation_artifacts = []
            self.store.save_run(run)
        if run.stage == FourStageStage.awaiting_gate:
            # Keyword Generate can outrun a failed/empty-options Gate accept.
            # Lazily accept the scope Gate when the user already picked keywords.
            if not self._has_current_accepted_gate(run):
                if run.decision is None or run.divergence_selection is None:
                    raise FourStageConflict("generation requires an accepted scope Gate")
                await self.resolve_gate(
                    run.run_id,
                    run.decision.decision_id,
                    GateAction.accept_option,
                    selected_option_id=(
                        run.gate_decision.selected_option_id if run.gate_decision else None
                    ),
                    auto_generate=False,
                    run_divergence=False,
                )
                run = self.store.get_run(run_id) or run
            if not self._has_current_accepted_gate(run):
                raise FourStageConflict("generation requires an accepted scope Gate")
            if run.divergence_selection is None:
                raise FourStageError("divergence selection is required before Generate")
            if self.generation_service is None or run.gate_decision is None or run.gate_decision.selected_option_id is None:
                raise FourStageError("generation service or selected direction is not ready")
            # Prefer the user's selected keywords/phrases as-is. Canonicalize when
            # candidate IDs are present; otherwise keep the chip labels as prompts.
            try:
                run.divergence_selection = self._canonicalize_divergence_selection(
                    run,
                    run.divergence_selection,
                    allow_label_lookup=True,
                    include_trusted_inherited=True,
                )
            except FourStageConflict:
                selection = run.divergence_selection
                keywords = list(selection.selected_keywords or [])
                phrases = list(selection.resolved_prompt_phrases or keywords)
                if not keywords:
                    raise
                run.divergence_selection = selection.model_copy(
                    deep=True,
                    update={
                        "selected_keywords": keywords,
                        "resolved_prompt_phrases": phrases or keywords,
                        "selected_candidate_ids": list(
                            selection.selected_candidate_ids
                            or [f"kw_{index}" for index, _ in enumerate(keywords)]
                        ),
                    },
                )
            run.generation_spec = self.generation_service.build_spec(
                run, run.gate_decision.selected_option_id
            )
            self._transition(run, FourStageStage.generation)
            self.store.save_run(run)
            await self._emit(
                run,
                "four_stage.generation_queued",
                {
                    "generation_id": run.generation_spec.generation_id,
                    "candidate_count": run.generation_spec.candidate_count,
                },
            )
        if run.stage != FourStageStage.generation:
            raise FourStageConflict(
                f"generation requires awaiting_gate or generation stage, current stage={run.stage}"
            )
        if run.generation_spec is None or self.generation_service is None:
            raise FourStageError("generation spec/service not ready")
        return await self.generation_service.start_generation(run, run.generation_spec)

    async def save_divergence_selection(
        self,
        run_id: str,
        selection: DivergenceSelection,
    ) -> FourStageRun:
        run = self.store.get_run(run_id)
        if run is None:
            raise FourStageError("run not found")
        if run.stage != FourStageStage.awaiting_gate:
            raise FourStageConflict(
                f"divergence selection requires awaiting_gate stage, current stage={run.stage}"
            )
        if run.gate_decision is None or run.gate_decision.action != GateAction.accept_option:
            raise FourStageConflict("accept the scope Gate before selecting divergence keywords")
        selection = self._canonicalize_divergence_selection(
            run,
            selection,
            allow_label_lookup=True,
            include_trusted_inherited=False,
        )
        run.divergence_selection = selection
        self.store.save_run(run)
        await self._emit(
            run,
            "four_stage.divergence_selection_saved",
            {
                "selected_keywords": selection.selected_keywords,
                "dimensions": selection.dimensions,
            },
        )
        return run

    def _canonicalize_divergence_selection(
        self,
        run: FourStageRun,
        selection: DivergenceSelection,
        *,
        allow_label_lookup: bool,
        include_trusted_inherited: bool,
    ) -> DivergenceSelection:
        canonical = self._canonicalize_current_divergence_selection(
            run,
            selection,
            allow_label_lookup=allow_label_lookup,
        )
        if not include_trusted_inherited:
            return canonical

        inherited_labels, inherited_phrases, inherited_dimensions = (
            self._trusted_inherited_divergence(run)
        )
        dimensions = {key: list(values) for key, values in inherited_dimensions.items()}
        for key, values in canonical.dimensions.items():
            dimensions.setdefault(key, []).extend(
                value for value in values if value not in dimensions.get(key, [])
            )
        return canonical.model_copy(
            deep=True,
            update={
                "selected_keywords": list(
                    dict.fromkeys([*inherited_labels, *canonical.selected_keywords])
                ),
                "resolved_prompt_phrases": list(
                    dict.fromkeys(
                        [*inherited_phrases, *canonical.resolved_prompt_phrases]
                    )
                ),
                "dimensions": dimensions,
            },
        )

    @staticmethod
    def _canonicalize_current_divergence_selection(
        run: FourStageRun,
        selection: DivergenceSelection,
        *,
        allow_label_lookup: bool,
    ) -> DivergenceSelection:
        response = run.semantic_divergence
        if (
            response is None
            or response.status != "completed"
            or run.decision is None
            or response.run_id != run.run_id
            or response.decision_id != run.decision.decision_id
        ):
            raise FourStageConflict(
                "explicit current semantic divergence candidates are required before selection"
            )
        candidates_by_id: dict[str, Any] = {}
        for candidate in response.candidates:
            if candidate.candidate_id in candidates_by_id:
                raise FourStageConflict("semantic divergence contains duplicate candidate IDs")
            candidates_by_id[candidate.candidate_id] = candidate

        selected_candidates: list[Any] = []
        requested_ids = list(dict.fromkeys(selection.selected_candidate_ids))
        if requested_ids:
            unknown = [candidate_id for candidate_id in requested_ids if candidate_id not in candidates_by_id]
            if unknown:
                raise FourStageConflict(
                    f"unknown semantic divergence candidate IDs: {', '.join(unknown)}"
                )
            selected_candidates = [candidates_by_id[candidate_id] for candidate_id in requested_ids]
        elif allow_label_lookup and selection.selected_keywords:
            for label in dict.fromkeys(selection.selected_keywords):
                matches = [
                    candidate
                    for candidate in response.candidates
                    if label in {candidate.display_label_zh, candidate.label_en}
                ]
                if len(matches) != 1:
                    raise FourStageConflict(
                        f"label-only semantic selection must match exactly one current candidate: {label}"
                    )
                selected_candidates.append(matches[0])
            requested_ids = [candidate.candidate_id for candidate in selected_candidates]
        else:
            raise FourStageConflict(
                "explicit semantic divergence candidate selection is required"
            )

        labels = [candidate.display_label_zh for candidate in selected_candidates]
        phrases = [candidate.prompt_phrase for candidate in selected_candidates]
        dimensions: dict[str, list[str]] = {}
        for candidate, label in zip(selected_candidates, labels, strict=True):
            dimensions.setdefault(candidate.group, []).append(label)
        selection = selection.model_copy(
            deep=True,
            update={
                "selected_candidate_ids": requested_ids,
                "selected_keywords": labels,
                "resolved_prompt_phrases": phrases,
                "dimensions": dimensions,
                "system_keywords": [],
            },
        )
        if run.intent_ir is not None:
            selection.scope = run.intent_ir.intent.scope
            if selection.target_part_id is None:
                selection.target_part_id = run.intent_ir.target.part_id
        return selection

    def _trusted_inherited_divergence(
        self,
        run: FourStageRun,
    ) -> tuple[list[str], list[str], dict[str, list[str]]]:
        """Rebuild inherited directions from prior server-owned revisions.

        Stored cumulative labels and prompt phrases are deliberately ignored.
        Each prior revision contributes only candidate IDs that still resolve
        against that prior run's own current semantic-divergence response.
        """
        revisions = self.store.list_revisions(run.session_id)
        current = next(
            (revision for revision in revisions if revision.run_id == run.run_id),
            None,
        )
        if current is None:
            return [], [], {}

        labels: list[str] = []
        phrases: list[str] = []
        dimensions: dict[str, list[str]] = {}
        eligible_statuses = {"accepted", "generating", "completed"}
        for revision in sorted(revisions, key=lambda item: item.intent_seq):
            if revision.intent_seq >= current.intent_seq:
                break
            if revision.status.value not in eligible_statuses or revision.run_id is None:
                continue
            prior_run = self.store.get_run(revision.run_id)
            if prior_run is None or prior_run.divergence_selection is None:
                continue
            try:
                prior = self._canonicalize_current_divergence_selection(
                    prior_run,
                    prior_run.divergence_selection,
                    allow_label_lookup=False,
                )
            except FourStageConflict:
                # A superseded or corrupt prior revision is not authoritative
                # inheritance and must never leak its stored text into prompts.
                continue
            labels.extend(value for value in prior.selected_keywords if value not in labels)
            phrases.extend(
                value for value in prior.resolved_prompt_phrases if value not in phrases
            )
            for key, values in prior.dimensions.items():
                bucket = dimensions.setdefault(key, [])
                bucket.extend(value for value in values if value not in bucket)
        return labels, phrases, dimensions

    async def finalize_generation(
        self,
        run_id: str,
        artifacts: list[dict[str, Any]] | None = None,
        error: Exception | None = None,
    ) -> None:
        run = self.store.get_run(run_id)
        if run is None or run.stage != FourStageStage.generation:
            return
        if error is not None:
            run.error = {
                "code": "generation_failed",
                "message": str(error)[:500],
                "retryable": True,
            }
            self._transition(run, FourStageStage.failed)
            self.store.save_run(run)
            await self._emit(
                run,
                "four_stage.failed",
                {"stage": "generation", "error_code": "generation_failed"},
            )
            return
        run.generation_artifacts = list(artifacts or [])
        run.completed_at = now_utc()
        self._transition(run, FourStageStage.completed)
        self.store.save_run(run)
        await self._emit(
            run,
            "four_stage.completed",
            {
                "artifact_count": len(run.generation_artifacts),
                "artifacts": run.generation_artifacts,
            },
        )

    def _record_retrieval_feedback(
        self,
        run: FourStageRun,
        action: str,
        selected_option_id: str | None,
    ) -> None:
        if run.retrieval is None or not run.retrieval.matches:
            return
        evidence_case_ids: set[str | None] = set()
        if selected_option_id and run.decision is not None:
            for option in run.decision.options:
                if option.option_id == selected_option_id:
                    for ref in option.evidence_refs:
                        for match in run.retrieval.matches:
                            if match.prior_ir_id == ref or match.case_id == ref:
                                evidence_case_ids.add(match.case_id)
        targets = [
            match
            for match in run.retrieval.matches[:3]
            if not evidence_case_ids or match.case_id in evidence_case_ids
        ] or run.retrieval.matches[:1]
        for match in targets:
            self.store.record_retrieval_feedback(
                run_id=run.run_id,
                session_id=run.session_id,
                prior_ir_id=match.prior_ir_id,
                case_id=match.case_id,
                action=action,
            )

    async def _run_pipeline(
        self,
        run: FourStageRun,
        start_at: FourStageStage | None = None,
    ) -> None:
        for stage in _PIPELINE_ORDER:
            if start_at is not None:
                idx = _PIPELINE_ORDER.index(stage)
                start_idx = _PIPELINE_ORDER.index(start_at)
                if idx < start_idx:
                    continue
            if stage == run.stage:
                continue
            ok = await self._execute_stage(run, stage)
            if not ok:
                return
        self._transition(run, FourStageStage.awaiting_gate)
        self.store.save_run(run)
        await self._emit(
            run,
            "four_stage.awaiting_gate",
            {"decision_id": run.decision.decision_id if run.decision else None},
        )

    async def _execute_stage(self, run: FourStageRun, stage: FourStageStage) -> bool:
        self._transition(run, stage)
        self._mark(run, stage, "started_at")
        self.store.save_run(run)
        try:
            if stage == FourStageStage.encoding:
                result = await self.encoding_service.encode(run)
                run.intent_ir = result
            elif stage == FourStageStage.retrieval:
                result = await self.retrieval_service.retrieve(run, run.intent_ir)
                run.retrieval = result
            elif stage == FourStageStage.re_representation:
                result = await self.decision_service.decide(
                    run, run.intent_ir, run.retrieval
                )
                run.decision = result
                self._set_scope_gate(run)
            else:  # pragma: no cover - guarded by _PIPELINE_ORDER
                raise FourStageError(f"stage not executable in pipeline: {stage}")
        except Exception as exc:
            logger.exception("four-stage stage %s failed run=%s", stage, run.run_id)
            run.error = {
                "code": "stage_failed",
                "message": str(exc),
                "retryable": True,
                "stage": stage.value,
            }
            run.failed_stage = stage
            self._mark(run, stage, "failed_at")
            self._transition(run, FourStageStage.failed)
            self.store.save_run(run)
            await self._emit(
                run,
                "four_stage.failed",
                {"stage": stage.value, "error_code": "stage_failed"},
            )
            return False
        self._mark(run, stage, "completed_at")
        self.store.save_run(run)
        event_name = {
            FourStageStage.encoding: "four_stage.encoding_completed",
            FourStageStage.retrieval: "four_stage.retrieval_completed",
            FourStageStage.re_representation: "four_stage.decision_completed",
        }[stage]
        await self._emit(run, event_name, {"stage": stage.value})
        return True

    def _set_scope_gate(self, run: FourStageRun) -> None:
        """Persist one compressed Gate question; keep hypotheses off the UI."""

        decision = run.decision
        intent = run.intent_ir
        if decision is None or intent is None:
            return
        object_type = intent.target.object_type
        part = intent.target.part_id
        if not is_concrete_object_type(object_type):
            target = "当前对象"
        else:
            target = part or str(object_type)
        question = decision.gate_question or (
            f"你想改变这个 {target} 的整体轮廓吗？"
        )
        run.scope_gate = ScopeGate(
            gate_id=f"gate_{decision.decision_id}",
            target=target,
            scope=decision.recommended_scope or intent.intent.scope,
            question=question,
            status="pending",
        )

    def _transition(self, run: FourStageRun, next_stage: FourStageStage) -> None:
        allowed = _ALLOWED_NEXT.get(run.stage, set())
        if next_stage not in allowed:
            raise FourStageInvalidTransition(
                f"illegal four-stage transition {run.stage} -> {next_stage}"
            )
        run.stage = next_stage

    def _mark(self, run: FourStageRun, stage: FourStageStage, key: str) -> None:
        entry = run.stage_timestamps.setdefault(stage.value, {})
        entry[key] = now_utc().isoformat()

    async def _emit(
        self,
        run: FourStageRun,
        message_type: str,
        payload: dict[str, Any],
    ) -> None:
        if self.websocket_manager is None:
            return
        event_payload = {
            "run_id": run.run_id,
            "session_id": run.session_id,
            "stage": run.stage.value,
            "schema_version": FOUR_STAGE_RUN_SCHEMA_VERSION,
            **payload,
        }
        try:
            await self.websocket_manager.broadcast(
                run.session_id, message_type, event_payload
            )
        except Exception:  # pragma: no cover - ws failures must not break the run
            logger.warning("four-stage ws emit failed type=%s run=%s", message_type, run.run_id)
