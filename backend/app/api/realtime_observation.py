"""Always-on observation and multi-intent revision API."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.models import (
    BehaviorCommitRequest,
    BehaviorPatchRequest,
    BehaviorSession,
    BehaviorStartRequest,
    DivergenceSelection,
    IntentRevision,
    IntentRevisionCreateRequest,
    IntentRevisionSourceImageRequest,
    RealtimeObservationSnapshot,
    RevisionGateRequest,
    SessionRecord,
    SolutionBatch,
    VersionGraphNode,
    VersionGraphNodeCreateRequest,
    VersionGraphNodeUpdateRequest,
    VersionGraphState,
    InteractionCommandMeta,
)
from app.services.interaction.orchestrator import InteractionOrchestrator
from app.services.intent.realtime_observation import RealtimeObservationService
from app.services.pipeline.four_stage_orchestrator import FourStageConflict, FourStageError


def _error(exc: FourStageError) -> HTTPException:
    if isinstance(exc, FourStageConflict):
        return HTTPException(status_code=409, detail=str(exc))
    if "not found" in str(exc):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


def create_realtime_observation_router(
    *,
    service: RealtimeObservationService,
    require_session: Callable[[str], SessionRecord],
    interaction_service: InteractionOrchestrator | None = None,
) -> APIRouter:
    router = APIRouter(tags=["realtime-observation"])

    @router.get(
        "/api/v1/sessions/{session_id}/realtime-observation",
        response_model=RealtimeObservationSnapshot,
    )
    async def get_snapshot(session_id: str) -> RealtimeObservationSnapshot:
        require_session(session_id)
        return service.snapshot(session_id)

    @router.post(
        "/api/v1/sessions/{session_id}/behaviors/start",
        response_model=BehaviorSession,
    )
    async def start_behavior(
        session_id: str,
        request: BehaviorStartRequest,
    ) -> BehaviorSession:
        require_session(session_id)
        return await service.start_behavior(session_id, request)

    @router.post(
        "/api/v1/sessions/{session_id}/behaviors",
        response_model=BehaviorSession,
    )
    async def commit_behavior(
        session_id: str,
        request: BehaviorCommitRequest,
        background: BackgroundTasks,
    ) -> BehaviorSession:
        require_session(session_id)
        behavior = await service.commit_behavior(session_id, request)
        background.add_task(service.refine_observation, session_id)
        return behavior

    @router.delete("/api/v1/sessions/{session_id}/behaviors/{behavior_id}", status_code=204)
    async def cancel_behavior(session_id: str, behavior_id: str) -> None:
        require_session(session_id)
        await service.cancel_behavior(session_id, behavior_id)

    @router.patch(
        "/api/v1/sessions/{session_id}/behaviors/{behavior_id}",
        response_model=BehaviorSession,
    )
    async def patch_behavior(
        session_id: str,
        behavior_id: str,
        request: BehaviorPatchRequest,
    ) -> BehaviorSession:
        require_session(session_id)
        try:
            return await service.patch_behavior(session_id, behavior_id, request)
        except FourStageError as exc:
            raise _error(exc) from exc

    @router.post(
        "/api/v1/sessions/{session_id}/intent-revisions",
        response_model=IntentRevision,
        status_code=202,
    )
    async def create_revision(
        session_id: str,
        request: IntentRevisionCreateRequest,
        background: BackgroundTasks,
    ) -> IntentRevision:
        require_session(session_id)
        revision = await service.create_revision(session_id, request)
        background.add_task(
            service.plan_revision,
            revision.revision_id,
            run_hy3d=request.run_hy3d,
        )
        return revision

    @router.post(
        "/api/v1/intent-revisions/{revision_id}/gate",
        response_model=IntentRevision,
    )
    async def resolve_revision_gate(
        revision_id: str,
        request: RevisionGateRequest,
    ) -> IntentRevision:
        try:
            if interaction_service is not None and (
                request.command_id or request.idempotency_key
            ):
                revision, _task, _events = await interaction_service.accept_gate(
                    revision_id, request
                )
                return revision
            return await service.resolve_gate(revision_id, request)
        except FourStageError as exc:
            raise _error(exc) from exc

    @router.put(
        "/api/v1/intent-revisions/{revision_id}/divergence-selection",
        response_model=IntentRevision,
    )
    async def save_revision_selection(
        revision_id: str,
        request: DivergenceSelection,
    ) -> IntentRevision:
        try:
            if interaction_service is not None and (
                request.command_id or request.idempotency_key
            ):
                meta = InteractionCommandMeta(
                    command_id=request.command_id or f"cmd_selection_{revision_id}",
                    idempotency_key=request.idempotency_key or request.command_id or f"selection:{revision_id}",
                    expected_version=request.expected_version,
                )
                revision, _events = await interaction_service.save_selection(
                    revision_id,
                    request,
                    meta,
                )
                return revision
            return await service.save_selection(revision_id, request)
        except FourStageError as exc:
            raise _error(exc) from exc

    @router.post(
        "/api/v1/intent-revisions/{revision_id}/source-image",
        response_model=IntentRevision,
    )
    async def attach_revision_source_image(
        revision_id: str,
        request: IntentRevisionSourceImageRequest,
    ) -> IntentRevision:
        try:
            return service.attach_source_image(revision_id, request.source_image_ref)
        except FourStageError as exc:
            raise _error(exc) from exc

    @router.post(
        "/api/v1/intent-revisions/{revision_id}/generation",
        response_model=SolutionBatch,
    )
    async def start_revision_generation(revision_id: str) -> SolutionBatch:
        try:
            return await service.start_generation(revision_id)
        except FourStageError as exc:
            raise _error(exc) from exc

    @router.post(
        "/api/v1/sessions/{session_id}/version-nodes",
        response_model=VersionGraphNode,
    )
    async def create_version_node(
        session_id: str,
        request: VersionGraphNodeCreateRequest,
    ) -> VersionGraphNode:
        require_session(session_id)
        try:
            return service.create_version_node(session_id, request)
        except FourStageError as exc:
            raise _error(exc) from exc

    @router.patch(
        "/api/v1/sessions/{session_id}/version-nodes/{node_id}",
        response_model=VersionGraphNode,
    )
    async def update_version_node(
        session_id: str,
        node_id: str,
        request: VersionGraphNodeUpdateRequest,
    ) -> VersionGraphNode:
        require_session(session_id)
        try:
            return service.update_version_node(session_id, node_id, request)
        except FourStageError as exc:
            raise _error(exc) from exc

    @router.put(
        "/api/v1/sessions/{session_id}/active-version/{node_id}",
        response_model=VersionGraphState,
    )
    async def activate_version_node(
        session_id: str,
        node_id: str,
    ) -> VersionGraphState:
        require_session(session_id)
        try:
            return service.activate_version_node(session_id, node_id)
        except FourStageError as exc:
            raise _error(exc) from exc

    @router.delete(
        "/api/v1/sessions/{session_id}/version-nodes/{node_id}",
        response_model=VersionGraphState,
    )
    async def delete_version_node(
        session_id: str,
        node_id: str,
    ) -> VersionGraphState:
        require_session(session_id)
        try:
            return service.delete_version_node(session_id, node_id)
        except FourStageError as exc:
            raise _error(exc) from exc

    return router


__all__ = ["create_realtime_observation_router"]
