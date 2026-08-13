"""Directions routers (Phase D extract)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import APIRouter

from app.models import (
    AnalogyDirection,
    CrossDomainDivergenceRequest,
    CrossDomainDivergenceResponse,
    SessionRecord,
)
from app.services.storage.studio_store import InMemoryStudioStore


def create_directions_router(
    *,
    require_session: Callable[[str], SessionRecord],
    studio_store: InMemoryStudioStore,
    log_deprecated_api: Callable[[str, str | None], None],
    create_direction_suggestions: Callable[..., Awaitable[CrossDomainDivergenceResponse]],
) -> APIRouter:
    router = APIRouter(tags=["directions"])

    @router.post("/api/v1/directions/cross-domain")
    async def create_cross_domain_directions(
        request: CrossDomainDivergenceRequest,
    ) -> CrossDomainDivergenceResponse:
        """Deprecated thin proxy → /directions/suggest. Do not use in new code."""
        log_deprecated_api("/api/v1/directions/cross-domain", request.session_id)
        response = await create_direction_suggestions(
            request,
            endpoint_name="suggested_analogy_directions",
        )
        response.metadata = {
            **response.metadata,
            "deprecated": True,
            "deprecated_endpoint": "/api/v1/directions/cross-domain",
            "canonical_endpoint": "/api/v1/directions/suggest",
            "direction_endpoint": "cross_domain_directions_proxy",
            "task": "direction_suggest",
        }
        return response

    @router.post("/api/v1/directions/suggest")
    async def suggest_analogy_directions(
        request: CrossDomainDivergenceRequest,
    ) -> CrossDomainDivergenceResponse:
        """Canonical More Creative direction endpoint."""
        response = await create_direction_suggestions(
            request,
            endpoint_name="suggested_analogy_directions",
        )
        response.metadata.setdefault("task", "direction_suggest")
        return response

    @router.get("/api/v1/sessions/{session_id}/directions")
    async def list_session_directions(
        session_id: str,
        limit: int = 100,
    ) -> dict[str, list[AnalogyDirection]]:
        require_session(session_id)
        return {"directions": studio_store.list_directions(session_id, limit=limit)}

    return router
