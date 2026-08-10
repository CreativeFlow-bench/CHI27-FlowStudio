"""candidates router (refactor plan P2); mechanical move out of main.py."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.models import (
    ArtifactListResponse,
    ArtifactRecord,
    AnalogyDirection,
    Candidate,
    CandidateDecision,
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
from app.services.storage.studio_store import InMemoryStudioStore
from app.services.generation.generation_orchestrator import ThreeDGenerationDisabled


def create_candidates_router(
    *,
    require_session,
    studio_store: InMemoryStudioStore,
    websocket_manager,
    generation_orchestrator,
    publish_perception,
    interaction_service,
    record_candidate_memory,
    legacy_job_store,
    files_root,
    validate_optional_session,
    record_candidate_rejection,
    build_prompt_chip_package,
    hydrate_geometry_request,
    hydrate_render_request,
    next_action_after_accept,
    next_action_after_reject,
    geometry_worker,
    render_preview_worker,
    interpret_and_publish,
    create_direction_suggestions,
    register_worker_artifacts,
    save_worker_job,
) -> APIRouter:
    router = APIRouter(tags=["candidates"])

    @router.post("/api/v1/geometry/{operation}")
    async def run_geometry_operation(
        operation: str,
        request: GeometryWorkerRequest,
    ) -> GeometryWorkerResponse:
        validate_optional_session(request.session_id)
        hydrate_geometry_request(request)
        response = await geometry_worker.run(operation, request)
        artifacts = register_worker_artifacts(worker="geometry", response=response, request=request)
        if artifacts:
            response.artifacts = {
                **response.artifacts,
                "artifact_ids": [artifact.artifact_id for artifact in artifacts],
            }
        save_worker_job(worker="geometry", request=request, response=response, artifacts=artifacts)
        return response

    @router.get("/api/v1/geometry/jobs/{job_id}")
    async def get_geometry_job(job_id: str) -> GeometryWorkerResponse:
        job = studio_store.get_worker_job(job_id)
        if job is None or job.worker != "geometry":
            raise HTTPException(status_code=404, detail=f"Geometry worker job not found: {job_id}")
        return GeometryWorkerResponse(**job.response)

    @router.post("/api/v1/geometry/jobs/{job_id}/cancel")
    async def cancel_geometry_job(job_id: str) -> GeometryWorkerResponse:
        job = studio_store.get_worker_job(job_id)
        if job is None or job.worker != "geometry":
            raise HTTPException(status_code=404, detail=f"Geometry worker job not found: {job_id}")
        if job.status in {JobStatus.queued, JobStatus.running}:
            job.status = JobStatus.cancelled
            job.ok = False
            job.error = ApiErrorBody(code="GEOMETRY_JOB_CANCELLED", message="Geometry job cancelled.", retryable=False)
            job.response = {
                **job.response,
                "ok": False,
                "status": JobStatus.cancelled.value,
                "error": job.error.model_dump(mode="json"),
            }
            studio_store.save_worker_job(job)
        return GeometryWorkerResponse(**job.response)

    @router.post("/api/v1/render/{operation}")
    async def run_render_operation(
        operation: str,
        request: RenderPreviewRequest,
    ) -> RenderPreviewResponse:
        validate_optional_session(request.session_id)
        hydrate_render_request(request)
        response = await render_preview_worker.run(operation, request)
        artifacts = register_worker_artifacts(worker="render", response=response, request=request)
        if artifacts:
            response.artifacts = {
                **response.artifacts,
                "artifact_ids": [artifact.artifact_id for artifact in artifacts],
            }
        save_worker_job(worker="render", request=request, response=response, artifacts=artifacts)
        return response

    @router.get("/api/v1/render/jobs/{job_id}")
    async def get_render_job(job_id: str) -> RenderPreviewResponse:
        job = studio_store.get_worker_job(job_id)
        if job is None or job.worker != "render":
            raise HTTPException(status_code=404, detail=f"Render worker job not found: {job_id}")
        return RenderPreviewResponse(**job.response)

    @router.post("/api/v1/render/jobs/{job_id}/cancel")
    async def cancel_render_job(job_id: str) -> RenderPreviewResponse:
        job = studio_store.get_worker_job(job_id)
        if job is None or job.worker != "render":
            raise HTTPException(status_code=404, detail=f"Render worker job not found: {job_id}")
        if job.status in {JobStatus.queued, JobStatus.running}:
            job.status = JobStatus.cancelled
            job.ok = False
            job.error = ApiErrorBody(code="RENDER_JOB_CANCELLED", message="Render job cancelled.", retryable=False)
            job.response = {
                **job.response,
                "ok": False,
                "status": JobStatus.cancelled.value,
                "error": job.error.model_dump(mode="json"),
            }
            studio_store.save_worker_job(job)
        return RenderPreviewResponse(**job.response)

    @router.patch("/api/v1/directions/{direction_id}")
    async def update_direction(
        direction_id: str,
        request: DirectionUpdateRequest,
    ) -> AnalogyDirection:
        direction = studio_store.get_direction(direction_id)
        if direction is None:
            raise HTTPException(status_code=404, detail=f"Direction not found: {direction_id}")
        if request.status is not None:
            direction.metadata["status"] = request.status
            direction.metadata["selected"] = request.status in {"selected", "pinned"}
        direction.metadata.update(request.metadata)
        session_id = str(direction.metadata.get("session_id") or "")
        if not session_id:
            session_id = _session_id_for_direction(direction_id)
        studio_store.save_direction(session_id, direction)
        await websocket_manager.broadcast(
            session_id,
            "directions_updated",
            {"directions": [direction.model_dump(mode="json")]},
        )
        return direction

    @router.post("/api/v1/prompt/compose")
    async def compose_prompt_tokens(request: PromptComposeRequest) -> PromptComposeResponse:
        require_session(request.session_id)
        if request.asset_id and studio_store.get_asset(request.asset_id) is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {request.asset_id}")
        package = build_prompt_chip_package(request)
        event = UserEvent(
            type="prompt_tokens_composed",
            event_id=f"evt_{uuid4().hex[:10]}",
            session_id=request.session_id,
            payload={
                "asset_id": request.asset_id,
                "intent_draft_id": request.intent_draft_id,
                "analogy_prompt_package": package,
                "final_prompt": package["final_prompt"],
                "selected_prompt_tokens": package["selected_prompt_tokens"],
                "direction_ids": package["direction_ids"],
                "metadata": request.metadata,
            },
        )
        studio_store.save_event(event)
        memory = studio_store.save_memory(
            MemoryRecord(
                memory_id=f"mem_{uuid4().hex[:10]}",
                session_id=request.session_id,
                category="working",
                type="prompt_chip_composition",
                source_id=event.event_id,
                asset_id=request.asset_id,
                confidence=0.86,
                content=event.payload,
                tags=["prompt_chip_composition", "more_creative", "human_selectable_chips"],
            )
        )
        await websocket_manager.broadcast(
            request.session_id,
            "prompt_tokens_composed",
            {
                "event_id": event.event_id,
                "memory_id": memory.memory_id,
                "analogy_prompt_package": package,
            },
        )
        return PromptComposeResponse(
            session_id=request.session_id,
            asset_id=request.asset_id,
            final_prompt=package["final_prompt"],
            analogy_prompt_package=package,
            event_id=event.event_id,
            memory_id=memory.memory_id,
        )

    @router.get("/api/v1/candidates/{candidate_id}")
    async def get_candidate(candidate_id: str):
        candidate = studio_store.get_candidate(candidate_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail=f"Candidate not found: {candidate_id}")
        return candidate

    @router.post("/api/v1/candidates/{candidate_id}/accept")
    async def accept_candidate(
        candidate_id: str, request: CandidateDecisionRequest
    ) -> CandidateDecisionResponse:
        return await _decide_candidate(candidate_id, request, CandidateDecision.accepted)

    @router.post("/api/v1/candidates/{candidate_id}/reject")
    async def reject_candidate(
        candidate_id: str, request: CandidateDecisionRequest
    ) -> CandidateDecisionResponse:
        return await _decide_candidate(candidate_id, request, CandidateDecision.rejected)

    @router.post("/api/v1/candidates/{candidate_id}/preview")
    async def preview_candidate(candidate_id: str, request: CandidateDecisionRequest) -> Candidate:
        require_session(request.session_id)
        candidate = studio_store.get_candidate(candidate_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail=f"Candidate not found: {candidate_id}")
        if candidate.session_id != request.session_id:
            raise HTTPException(status_code=400, detail="Candidate belongs to another session")
        candidate.metadata["last_previewed_at"] = now_utc().isoformat()
        candidate.metadata["preview_reason"] = request.reason
        studio_store.save_candidate(candidate)
        event = UserEvent(
            type="candidate_compared",
            event_id=f"evt_{uuid4().hex[:10]}",
            session_id=request.session_id,
            payload={
                "candidate_id": candidate_id,
                "reason": request.reason,
                "asset_id": candidate.source_asset_id,
                "part_id": candidate.source_part_id,
                "artifact_level": "mesh" if candidate.mesh_url or candidate.obj_url else "image",
            },
        )
        studio_store.save_event(event)
        await websocket_manager.broadcast(
            request.session_id,
            "candidate_previewed",
            candidate.model_dump(mode="json"),
        )
        return candidate

    @router.post("/api/v1/candidates/{candidate_id}/commit")
    async def commit_candidate(
        candidate_id: str,
        request: CandidateDecisionRequest,
    ) -> CandidateDecisionResponse:
        request.make_active_asset = True
        return await _decide_candidate(candidate_id, request, CandidateDecision.accepted)

    @router.post("/api/v1/candidates/{candidate_id}/hy3d")
    async def generate_candidate_hy3d(candidate_id: str, request: CandidateDecisionRequest) -> Candidate:
        require_session(request.session_id)
        try:
            return await generation_orchestrator.generate_candidate_hy3d(
                candidate_id,
                request.session_id,
            )
        except ThreeDGenerationDisabled as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": exc.code, "message": str(exc)},
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.post("/api/v1/candidates/{candidate_id}/fit")
    async def fit_candidate(candidate_id: str, request: CandidateFitRequest) -> Candidate:
        require_session(request.session_id)
        try:
            return await generation_orchestrator.fit_candidate_to_part(candidate_id, request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    async def _decide_candidate(
        candidate_id: str,
        request: CandidateDecisionRequest,
        decision: CandidateDecision,
    ) -> CandidateDecisionResponse:
        session = require_session(request.session_id)
        candidate = studio_store.get_candidate(candidate_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail=f"Candidate not found: {candidate_id}")
        candidate.decision = decision
        studio_store.save_candidate(candidate)

        candidate_stage = str(candidate.metadata.get("stage") or "").strip()
        candidate_fidelity = str(candidate.metadata.get("fidelity") or "").strip()
        is_direction_candidate = candidate_stage in {"silhouette", "rough_form", "global", "form"}
        has_asset_output = bool(candidate.mesh_url or candidate.obj_url)
        commit_policy = "active_asset" if request.make_active_asset and has_asset_output else "direction_memory"

        active_asset_id = None
        if (
            decision == CandidateDecision.accepted
            and request.make_active_asset
            and has_asset_output
        ):
            active_asset = studio_store.create_asset(
                AssetCreateRequest(
                    session_id=request.session_id,
                    object_type=studio_store.get_asset(candidate.source_asset_id).object_type
                    if studio_store.get_asset(candidate.source_asset_id)
                    else "object",
                    label=candidate.label,
                    mesh_url=candidate.mesh_url,
                    obj_url=candidate.obj_url,
                    thumbnail_url=candidate.thumbnail_url,
                    metadata={"source_candidate_id": candidate.candidate_id},
                )
            )
            active_asset_id = active_asset.asset_id

        if decision == CandidateDecision.accepted:
            record_candidate_memory(
                session,
                candidate,
                commit_policy,
                candidate_stage,
                candidate_fidelity,
            )
        else:
            record_candidate_rejection(session, candidate, candidate_stage, candidate_fidelity)

        phase = (
            DesignPhase.exploring
            if decision == CandidateDecision.accepted
            and is_direction_candidate
            and commit_policy == "direction_memory"
            else DesignPhase.refinement
            if decision == CandidateDecision.accepted
            else DesignPhase.candidate_comparison
        )
        goal = request.reason
        if decision == CandidateDecision.accepted and not goal:
            if commit_policy == "direction_memory":
                goal = f"Accepted direction: {candidate.label}"
            else:
                goal = f"Accepted asset candidate: {candidate.label}"
        stage = StageState(
            phase=phase,
            confidence=0.86 if decision == CandidateDecision.accepted else 0.78,
            current_goal=goal,
            active_asset_id=active_asset_id or session.stage.active_asset_id,
            active_part_id=candidate.source_part_id or session.stage.active_part_id,
            suggested_action=next_action_after_accept(candidate_stage, commit_policy)
            if decision == CandidateDecision.accepted
            else next_action_after_reject(session, candidate_stage),
            evidence=[
                f"Candidate {decision.value}: {candidate_id}",
                f"commit_policy={commit_policy}",
                f"stage={candidate_stage or 'unspecified'}",
                f"fidelity={candidate_fidelity or 'unspecified'}",
            ],
        )
        studio_store.save_stage(request.session_id, stage)

        event = UserEvent(
            type=f"candidate_{decision.value}",
            event_id=f"evt_{uuid4().hex[:10]}",
            session_id=request.session_id,
            payload={
                "candidate_id": candidate_id,
                "reason": request.reason,
                "asset_id": candidate.source_asset_id,
                "part_id": candidate.source_part_id,
                "creative_stage": candidate_stage or None,
                "fidelity": candidate_fidelity or None,
                "commit_policy": commit_policy,
                "make_active_asset": bool(active_asset_id),
                "active_asset_id": active_asset_id,
                "suggested_action": stage.suggested_action,
            },
        )
        studio_store.save_event(event)
        await interpret_and_publish(
            session_id=request.session_id,
            event=event,
            interaction_service=interaction_service,
            publish_perception=publish_perception,
            defer_vlm=True,
        )

        return CandidateDecisionResponse(
            candidate_id=candidate_id,
            decision=decision,
            active_asset_id=active_asset_id,
            updated_stage=studio_store.get_session(request.session_id).stage,
        )

    return router
