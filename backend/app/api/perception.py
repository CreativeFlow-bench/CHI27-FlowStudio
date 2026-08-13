"""Perception / live-signals / solution-space routers (Phase D extract)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import APIRouter

from app.api.perception_flow import interpret_and_publish
from app.api.solution_space import build_solution_space_view
from app.models import (
    InteractionInterpretation,
    SessionRecord,
    UserEvent,
)
from app.services.intent.interaction_understanding import InteractionUnderstandingService
from app.services.storage.studio_store import InMemoryStudioStore
from app.services.storage.websocket_manager import WebSocketManager


def create_perception_router(
    *,
    require_session: Callable[[str], SessionRecord],
    studio_store: InMemoryStudioStore,
    websocket_manager: WebSocketManager,
    interaction_service: InteractionUnderstandingService,
    publish_perception: Callable[..., Awaitable[None]],
    update_session_live_signals: Callable[..., dict[str, object]],
    live_signals_payload: Callable[[SessionRecord], dict[str, object]],
    perception_payload: Callable[[InteractionInterpretation], dict[str, object]],
    compact_evidence_summary: Callable[[InteractionInterpretation], list[dict[str, object]]],
) -> APIRouter:
    router = APIRouter(tags=["perception"])

    @router.get("/api/v1/sessions/{session_id}/live-signals")
    async def get_live_signals(session_id: str) -> dict[str, object]:
        session = require_session(session_id)
        return live_signals_payload(session)

    @router.put("/api/v1/sessions/{session_id}/live-signals")
    async def put_live_signals(session_id: str, payload: dict[str, object]) -> dict[str, object]:
        require_session(session_id)
        raw_signals = payload.get("live_signals") if "live_signals" in payload else payload
        result = update_session_live_signals(session_id, raw_signals, "live_signals_endpoint")
        await websocket_manager.broadcast(session_id, "live_signals_updated", result)
        return result

    @router.get("/api/v1/sessions/{session_id}/perception/latest")
    async def get_latest_perception(session_id: str) -> dict[str, object]:
        require_session(session_id)
        interpretations = studio_store.recent_interpretations(session_id, limit=1)
        if not interpretations:
            return {
                "session_id": session_id,
                "perception": None,
                "status": "empty",
            }
        interpretation = interpretations[0]
        return {
            "session_id": session_id,
            "status": "ready",
            "perception": perception_payload(interpretation),
            "interpretation": interpretation.model_dump(mode="json"),
            "evidence_summary": compact_evidence_summary(interpretation),
        }

    @router.get("/api/v1/sessions/{session_id}/solution-space")
    async def get_solution_space(session_id: str, limit: int = 50) -> dict[str, object]:
        session = require_session(session_id)
        return build_solution_space_view(studio_store, session, limit=limit)

    @router.post("/api/v1/interaction/interpret")
    async def interpret_interaction_event(event: UserEvent) -> InteractionInterpretation:
        require_session(event.session_id)
        live_signals_update = update_session_live_signals(
            event.session_id,
            event.payload.get("live_signals"),
            f"event:{event.type}",
        )
        studio_store.save_event(event)
        if live_signals_update.get("live_signals"):
            await websocket_manager.broadcast(
                event.session_id,
                "live_signals_updated",
                live_signals_update,
            )
        return await interpret_and_publish(
            session_id=event.session_id,
            event=event,
            interaction_service=interaction_service,
            publish_perception=publish_perception,
            defer_vlm=True,
        )

    return router
