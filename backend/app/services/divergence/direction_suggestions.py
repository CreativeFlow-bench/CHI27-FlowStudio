"""Canonical direction suggestion builder (refactor plan P1b)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import HTTPException

from app.models import (
    CrossDomainDivergenceRequest,
    CrossDomainDivergenceResponse,
    MemoryRecord,
    SessionRecord,
)
from app.services.divergence import contextual_divergence
from app.services.storage.studio_store import InMemoryStudioStore


def create_direction_suggestion_builder(
    *,
    require_session: Callable[[str], SessionRecord],
    studio_store: InMemoryStudioStore,
    websocket_manager: object,
    build_cross_domain_response: Callable[..., CrossDomainDivergenceResponse],
) -> Callable[..., Awaitable[CrossDomainDivergenceResponse]]:
    """Return the shared builder used by /directions/suggest + deprecated proxy."""

    async def create_direction_suggestions(
        request: CrossDomainDivergenceRequest,
        *,
        endpoint_name: str,
    ) -> CrossDomainDivergenceResponse:
        session = require_session(request.session_id)
        asset = studio_store.get_asset(request.asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {request.asset_id}")
        draft = None
        if request.intent_draft_id:
            draft = studio_store.get_intent_draft(request.intent_draft_id)
            if draft is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Intent draft not found: {request.intent_draft_id}",
                )
            if draft.session_id != request.session_id:
                raise HTTPException(status_code=400, detail="Intent draft belongs to another session")
        if (request.metadata or {}).get("suggestion_mode") == "contextual_fragments_v1":
            response = await asyncio.to_thread(
                contextual_divergence.suggest_contextual_fragments,
                request=request,
                asset=asset,
                draft=draft,
                session=session,
            )
            response.metadata["direction_endpoint"] = endpoint_name
            response.metadata.setdefault("canonical_endpoint", "suggested_analogy_directions")
            response.metadata.setdefault("task", "direction_suggest")
            if request.interpretation_id:
                response.metadata["interpretation_id"] = request.interpretation_id
            for direction in response.directions:
                direction.metadata.setdefault("status", "suggested")
                direction.metadata.setdefault("asset_id", request.asset_id)
                direction.metadata.setdefault("session_id", request.session_id)
                direction.metadata.setdefault("direction_endpoint", endpoint_name)
                studio_store.save_direction(request.session_id, direction)
            studio_store.save_memory(
                MemoryRecord(
                    memory_id=f"mem_{uuid4().hex[:10]}",
                    session_id=request.session_id,
                    category="working",
                    type=endpoint_name,
                    source_id=request.intent_draft_id,
                    asset_id=request.asset_id,
                    confidence=0.78,
                    content=response.model_dump(mode="json"),
                    tags=["cross_domain", "contextual_fragments_v1", endpoint_name],
                )
            )
            await websocket_manager.broadcast(
                request.session_id,
                "cross_domain_directions",
                response.model_dump(mode="json"),
            )
            return response
        response = build_cross_domain_response(request, asset, draft, session)
        response.metadata["direction_endpoint"] = endpoint_name
        response.metadata.setdefault("canonical_endpoint", "suggested_analogy_directions")
        response.metadata.setdefault("task", "direction_suggest")
        if request.interpretation_id:
            response.metadata["interpretation_id"] = request.interpretation_id
        for direction in response.directions:
            direction.metadata.setdefault("status", "suggested")
            direction.metadata.setdefault("asset_id", request.asset_id)
            direction.metadata.setdefault("session_id", request.session_id)
            direction.metadata.setdefault("direction_endpoint", endpoint_name)
            studio_store.save_direction(request.session_id, direction)
        studio_store.save_memory(
            MemoryRecord(
                memory_id=f"mem_{uuid4().hex[:10]}",
                session_id=request.session_id,
                category="working",
                type=endpoint_name,
                source_id=request.intent_draft_id,
                asset_id=request.asset_id,
                confidence=0.78,
                content=response.model_dump(mode="json"),
                tags=["cross_domain", "analogy_direction", endpoint_name],
            )
        )
        await websocket_manager.broadcast(
            request.session_id,
            "cross_domain_directions",
            response.model_dump(mode="json"),
        )
        return response

    return create_direction_suggestions
