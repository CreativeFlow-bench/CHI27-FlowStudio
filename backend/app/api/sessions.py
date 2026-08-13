"""sessions router (refactor plan P2); mechanical move out of main.py."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.models import (
    ArtifactListResponse,
    ArtifactRecord,
    Candidate,
    CandidateDecision,
    CrossDomainDivergenceRequest,
    DesignPhase,
    CandidateDecisionRequest,
    CandidateDecisionResponse,
    CandidateFitRequest,
    CandidateRequest,
    CandidateResponse,
    CaseCreateRequest,
    CaseRecord,
    DirectionUpdateRequest,
    GeometryWorkerRequest,
    GeometryWorkerResponse,
    IntentDraft,
    InteractionInterpretation,
    JobRecord,
    LegacyCandidate,
    LegacyJobRecord,
    MemoryListResponse,
    MemoryRecord,
    PlannerInterpretationDecisionRequest,
    PlannerInterpretationDecisionResponse,
    PromptComposeRequest,
    PromptComposeResponse,
    RenderPreviewRequest,
    RenderPreviewResponse,
    SessionCreateRequest,
    SessionRecord,
    SessionSnapshotResponse,
    SessionUpdateRequest,
    StageState,
    StoreStateImportRequest,
    StoreStateImportResponse,
    StoreStateSnapshot,
    UserEvent,
    WorkerJobRecord,
    now_utc,
)
from app.api.solution_space import build_solution_space_view
from app.services.storage.studio_store import InMemoryStudioStore


def create_sessions_router(
    *,
    require_session,
    studio_store: InMemoryStudioStore,
    websocket_manager,
    live_signals_payload,
    create_direction_suggestions,
    clear_four_stage_session: Callable[[str], object] | None = None,
) -> APIRouter:
    router = APIRouter(tags=["sessions"])

    @router.post("/api/v1/sessions")
    async def create_session(request: SessionCreateRequest) -> SessionRecord:
        return studio_store.create_session(request)

    @router.get("/api/v1/sessions/{session_id}")
    async def get_session(session_id: str) -> SessionRecord:
        return require_session(session_id)

    @router.get("/api/v1/sessions/{session_id}/memory")
    async def get_session_memory(session_id: str) -> dict[str, object]:
        session = require_session(session_id)
        recent_events = studio_store.recent_events(session_id, limit=12)
        recent_interpretations = studio_store.recent_interpretations(session_id, limit=12)
        return {
            "session_id": session_id,
            "stage": session.stage.model_dump(mode="json"),
            "candidate_memory": session.metadata.get("candidate_memory", {}),
            "structured_memory": {
                category: [item.model_dump(mode="json") for item in rows]
                for category, rows in studio_store.memory_by_category(session_id, limit_per_category=8).items()
            },
            "recent_events": [
                {
                    "event_id": event.event_id,
                    "type": event.type,
                    "timestamp": event.timestamp.isoformat(),
                    "asset_id": event.payload.get("asset_id"),
                    "part_id": event.payload.get("part_id")
                    or (event.payload.get("selection") or {}).get("part_id"),
                    "creative_stage": event.payload.get("creative_stage")
                    or (event.payload.get("generation") or {}).get("metadata", {}).get("stage"),
                    "fidelity": event.payload.get("fidelity")
                    or (event.payload.get("generation") or {}).get("metadata", {}).get("fidelity"),
                    "candidate_id": event.payload.get("candidate_id"),
                }
                for event in recent_events
            ],
            "recent_interpretations": [
                {
                    "interpretation_id": item.interpretation_id,
                    "source_event_id": item.source_event_id,
                    "action_type": item.action_type,
                    "predictor": item.predictor,
                    "predictor_version": item.predictor_version,
                    "primary_intent": item.primary_intent.value,
                    "confidence": item.confidence,
                    "ambiguity": item.ambiguity,
                    "assistance_policy": item.assistance_policy.value,
                    "target": item.target.model_dump(mode="json"),
                }
                for item in recent_interpretations
            ],
        }

    @router.post("/api/v1/sessions/{session_id}/reset")
    async def reset_session_workspace(session_id: str) -> dict[str, object]:
        """清空会话工作区历史（用户不下载即删除）。"""
        require_session(session_id)
        session = studio_store.reset_session_workspace(session_id)
        if clear_four_stage_session is not None:
            clear_four_stage_session(session_id)
        return {"ok": True, "session": session.model_dump(mode="json")}

    @router.get("/api/v1/sessions/{session_id}/snapshot")
    async def get_session_snapshot(session_id: str) -> SessionSnapshotResponse:
        session = require_session(session_id)
        active_asset = studio_store.get_asset(session.stage.active_asset_id) if session.stage.active_asset_id else None
        active_job = studio_store.recent_session_job(session_id)
        visible_candidates: list[Candidate] = []
        if active_job:
            visible_candidates = [
                candidate
                for candidate_id in active_job.candidate_ids[:12]
                if (candidate := studio_store.get_candidate(candidate_id)) is not None
            ]
        artifacts = studio_store.list_artifacts(
            session_id=session_id,
            asset_id=active_asset.asset_id if active_asset else None,
            limit=50,
        )
        if active_job:
            for candidate in visible_candidates:
                artifacts.extend(
                    studio_store.list_artifacts(
                        session_id=session_id,
                        candidate_id=candidate.candidate_id,
                        limit=20,
                    )
                )
        deduped = {artifact.artifact_id: artifact for artifact in artifacts}
        return SessionSnapshotResponse(
            session=session,
            active_asset=active_asset,
            active_parts=active_asset.parts if active_asset else [],
            active_job=active_job,
            live_signals=live_signals_payload(session)["live_signals"],
            visible_candidates=visible_candidates,
            recent_events=studio_store.recent_events(session_id, limit=20),
            recent_interpretations=studio_store.recent_interpretations(session_id, limit=20),
            artifacts=list(deduped.values())[:80],
            intent_drafts=studio_store.list_intent_drafts(session_id, include_archived=True),
            action_atoms=studio_store.list_action_atoms(session_id, limit=100),
            directions=studio_store.list_directions(session_id, limit=100),
            memory=studio_store.memory_by_category(session_id, limit_per_category=12),
            solution_space=build_solution_space_view(studio_store, session, limit=50),
        )

    @router.get("/api/v1/sessions/{session_id}/memories")
    async def list_session_memories(
        session_id: str,
        category: str | None = None,
        asset_id: str | None = None,
        part_id: str | None = None,
        candidate_id: str | None = None,
        limit: int = 100,
    ) -> MemoryListResponse:
        require_session(session_id)
        return MemoryListResponse(
            memories=studio_store.list_memories(
                session_id=session_id,
                category=category,
                asset_id=asset_id,
                part_id=part_id,
                candidate_id=candidate_id,
                limit=limit,
            )
        )

    @router.get("/api/v1/artifacts")
    async def list_artifacts(
        session_id: str | None = None,
        asset_id: str | None = None,
        candidate_id: str | None = None,
        worker: str | None = None,
        type: str | None = None,
        limit: int = 100,
    ) -> ArtifactListResponse:
        return ArtifactListResponse(
            artifacts=studio_store.list_artifacts(
                session_id=session_id,
                asset_id=asset_id,
                candidate_id=candidate_id,
                worker=worker,
                artifact_type=type,
                limit=limit,
            )
        )

    @router.get("/api/v1/artifacts/{artifact_id}")
    async def get_artifact(artifact_id: str) -> ArtifactRecord:
        artifact = studio_store.get_artifact(artifact_id)
        if artifact is None:
            raise HTTPException(status_code=404, detail=f"Artifact not found: {artifact_id}")
        return artifact

    @router.get("/api/v1/admin/state/export")
    async def export_store_state() -> StoreStateSnapshot:
        return studio_store.export_state()

    @router.post("/api/v1/admin/state/import")
    async def import_store_state(request: StoreStateImportRequest) -> StoreStateImportResponse:
        try:
            return studio_store.import_state(request.snapshot, replace=request.replace)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/v1/interpretations/{interpretation_id}/decision")
    async def decide_planner_interpretation(
        interpretation_id: str,
        request: PlannerInterpretationDecisionRequest,
    ) -> PlannerInterpretationDecisionResponse:
        session = require_session(request.session_id)
        interpretation = studio_store.get_interpretation(interpretation_id)
        if interpretation is None:
            raise HTTPException(
                status_code=404,
                detail=f"Interpretation not found: {interpretation_id}",
            )
        if interpretation.session_id != request.session_id:
            raise HTTPException(
                status_code=400,
                detail="Interpretation does not belong to the supplied session",
            )

        event_type = f"planner_interpretation_{request.decision}"
        event = UserEvent(
            type=event_type,
            event_id=f"evt_{uuid4().hex[:10]}",
            session_id=request.session_id,
            payload={
                "interpretation_id": interpretation.interpretation_id,
                "decision": request.decision,
                "reason": request.reason,
                "primary_intent": interpretation.primary_intent.value,
                "confidence": interpretation.confidence,
                "ambiguity": interpretation.ambiguity,
                "assistance_policy": interpretation.assistance_policy.value,
                "target": interpretation.target.model_dump(mode="json"),
                "suggested_assistance": [
                    item.model_dump(mode="json") for item in interpretation.suggested_assistance
                ],
                "metadata": request.metadata,
                "asset_id": interpretation.target.asset_id,
                "part_id": interpretation.target.part_id,
            },
        )
        studio_store.save_event(event)

        memory = MemoryRecord(
            memory_id=f"mem_{uuid4().hex[:10]}",
            session_id=request.session_id,
            category="reflective",
            type=event_type,
            source_id=interpretation.interpretation_id,
            asset_id=interpretation.target.asset_id,
            part_id=interpretation.target.part_id,
            candidate_id=interpretation.features.get("candidate_id")
            if isinstance(interpretation.features, dict)
            else None,
            confidence=interpretation.confidence,
            content={
                "decision": request.decision,
                "reason": request.reason,
                "primary_intent": interpretation.primary_intent.value,
                "assistance_policy": interpretation.assistance_policy.value,
                "suggested_assistance": [
                    item.model_dump(mode="json") for item in interpretation.suggested_assistance
                ],
                "evidence": interpretation.evidence,
                "metadata": request.metadata,
            },
            tags=["planner_control_gate", request.decision, interpretation.primary_intent.value],
        )
        studio_store.save_memory(memory)

        stage = session.stage
        if request.decision == "accepted":
            stage.confidence = interpretation.confidence
            stage.current_goal = f"Accepted planner intent: {interpretation.primary_intent.value}"
            stage.active_asset_id = interpretation.target.asset_id or stage.active_asset_id
            stage.active_part_id = interpretation.target.part_id or stage.active_part_id
            if interpretation.suggested_assistance:
                suggestion = interpretation.suggested_assistance[0]
                stage.suggested_action = str(
                    suggestion.metadata.get("suggested_next_action")
                    or suggestion.label
                    or suggestion.type
                )
            else:
                stage.suggested_action = "continue_with_confirmed_intent"
            if stage.phase == DesignPhase.idle:
                stage.phase = DesignPhase.exploring
            stage.evidence = [
                *stage.evidence[-5:],
                f"planner_interpretation_accepted:{interpretation.interpretation_id}",
            ]
        else:
            stage.confidence = min(stage.confidence, max(0.2, 1.0 - interpretation.ambiguity))
            stage.current_goal = "Planner interpretation rejected; revise intent or continue editing"
            stage.suggested_action = "revise_intent_or_continue_editing"
            stage.evidence = [
                *stage.evidence[-5:],
                f"planner_interpretation_rejected:{interpretation.interpretation_id}",
            ]
        studio_store.save_stage(request.session_id, stage)
        session.metadata.setdefault("planner_control_gate", {})
        if isinstance(session.metadata["planner_control_gate"], dict):
            session.metadata["planner_control_gate"] = {
                **session.metadata["planner_control_gate"],
                "last_interpretation_id": interpretation.interpretation_id,
                "last_decision": request.decision,
                "last_event_id": event.event_id,
                "last_memory_id": memory.memory_id,
            }
            studio_store.update_session(
                request.session_id,
                SessionUpdateRequest(metadata={"planner_control_gate": session.metadata["planner_control_gate"]}),
            )

        await websocket_manager.broadcast(
            request.session_id,
            "planner_interpretation_decision",
            {
                "interpretation_id": interpretation.interpretation_id,
                "decision": request.decision,
                "event_id": event.event_id,
                "memory_id": memory.memory_id,
            },
        )
        await websocket_manager.broadcast(
            request.session_id,
            "stage_update",
            stage.model_dump(mode="json"),
        )
        direction_response: CrossDomainDivergenceResponse | None = None
        if request.decision == "accepted" and request.metadata.get("auto_suggest_directions"):
            asset_id = interpretation.target.asset_id or stage.active_asset_id
            if asset_id and studio_store.get_asset(asset_id):
                direction_response = await create_direction_suggestions(
                    CrossDomainDivergenceRequest(
                        session_id=request.session_id,
                        asset_id=asset_id,
                        interpretation_id=interpretation.interpretation_id,
                        source_summary=str(
                            request.metadata.get("source_summary")
                            or "confirmed planner intent prompt expansion"
                        ),
                        constraints=[
                            str(value)
                            for value in request.metadata.get("preserved_constraints", [])
                            if isinstance(value, str)
                        ],
                        dimensions=request.metadata.get("dimensions", []),
                        candidate_count=int(request.metadata.get("direction_count") or 4),
                        metadata={
                            **request.metadata,
                            "auto_suggest_source": "planner_interpretation_decision",
                            "interpretation_id": interpretation.interpretation_id,
                        },
                    ),
                    endpoint_name="suggested_analogy_directions",
                )
        return PlannerInterpretationDecisionResponse(
            interpretation_id=interpretation.interpretation_id,
            session_id=request.session_id,
            decision=request.decision,
            event_id=event.event_id,
            memory_id=memory.memory_id,
            updated_stage=stage,
            suggested_directions=direction_response.directions if direction_response else [],
            direction_response=direction_response,
        )

    @router.patch("/api/v1/sessions/{session_id}")
    async def update_session(session_id: str, request: SessionUpdateRequest) -> SessionRecord:
        session = studio_store.update_session(session_id, request)
        if session is None:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
        return session

    return router
