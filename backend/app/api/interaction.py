"""Canonical fast interaction task and recovery endpoints."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, HTTPException

from app.models import (
    DivergenceSelection,
    InteractionCommandMeta,
    InteractionProjection,
    InteractionTask,
    RevisionGateRequest,
    SessionRecord,
)
from app.services.interaction.orchestrator import InteractionOrchestrator
from app.services.pipeline.four_stage_orchestrator import FourStageConflict, FourStageError


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, FourStageConflict):
        return HTTPException(status_code=409, detail=str(exc))
    if "not found" in str(exc).lower():
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


def create_interaction_router(
    *,
    service: InteractionOrchestrator,
    require_session: Callable[[str], SessionRecord],
) -> APIRouter:
    router = APIRouter(tags=["interaction-orchestration"])

    @router.post("/api/v1/intent-revisions/{revision_id}/generation-tasks")
    async def start_generation_task(
        revision_id: str,
        request: InteractionCommandMeta | None = None,
    ) -> dict:
        try:
            revision, task, events = await service.start_generation(revision_id, request)
            return {
                "revision": revision.model_dump(mode="json"),
                "task": task.model_dump(mode="json"),
                "events": [item.model_dump(mode="json") for item in events],
            }
        except (FourStageConflict, FourStageError) as exc:
            raise _error(exc) from exc

    @router.get(
        "/api/v1/interaction-tasks/{task_id}",
        response_model=InteractionTask,
    )
    async def get_task(task_id: str) -> InteractionTask:
        task = service.store.get_interaction_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="interaction task not found")
        return task

    @router.post("/api/v1/interaction-tasks/{task_id}/retry", response_model=InteractionTask)
    async def retry_task(task_id: str) -> InteractionTask:
        try:
            return await service.retry_task(task_id)
        except (FourStageConflict, FourStageError) as exc:
            raise _error(exc) from exc

    @router.post("/api/v1/interaction-tasks/{task_id}/cancel", response_model=InteractionTask)
    async def cancel_task(task_id: str) -> InteractionTask:
        try:
            return service.cancel_task(task_id)
        except (FourStageConflict, FourStageError) as exc:
            raise _error(exc) from exc

    @router.get(
        "/api/v1/sessions/{session_id}/interaction-projection",
        response_model=InteractionProjection,
    )
    async def get_projection(session_id: str) -> InteractionProjection:
        require_session(session_id)
        return service.projection(session_id)

    @router.get("/api/v1/sessions/{session_id}/interaction-events")
    async def get_events(session_id: str, after_cursor: int = 0) -> dict:
        require_session(session_id)
        events = service.events(session_id, after_cursor=max(0, after_cursor))
        return {
            "events": [item.model_dump(mode="json") for item in events],
            "last_event_cursor": events[-1].event_cursor if events else max(0, after_cursor),
        }

    return router


__all__ = ["create_interaction_router"]
