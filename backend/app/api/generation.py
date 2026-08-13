"""Generation / jobs / deprecated candidates routers (Phase D + E)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.models import (
    Candidate,
    GenerationMode,
    GenerationRequest,
    JobCreateResponse,
    JobStatus,
    SessionRecord,
)
from app.services.generation.generation_orchestrator import GenerationOrchestrator
from app.services.storage.job_store import InMemoryJobStore
from app.services.storage.studio_store import InMemoryStudioStore
from app.services.storage.websocket_manager import WebSocketManager


def create_generation_router(
    *,
    require_session: Callable[[str], SessionRecord],
    studio_store: InMemoryStudioStore,
    legacy_job_store: InMemoryJobStore,
    generation_orchestrator: GenerationOrchestrator,
    websocket_manager: WebSocketManager,
    log_deprecated_api: Callable[[str, str | None], None],
    cancel_remote_worker_jobs: Callable[..., Awaitable[dict]],
) -> APIRouter:
    router = APIRouter(tags=["generation"])

    async def _create_generation(request: GenerationRequest) -> JobCreateResponse:
        require_session(request.session_id)
        if studio_store.get_asset(request.asset_id) is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {request.asset_id}")
        job = await generation_orchestrator.create_generation_job(request)
        return JobCreateResponse(
            job_id=job.job_id,
            session_id=job.session_id,
            status=job.status,
            stage=job.stage,
            created_at=job.created_at,
        )

    @router.post("/api/v1/generation/replace")
    async def generate_replace(request: GenerationRequest) -> JobCreateResponse:
        if request.intent.mode != GenerationMode.replace:
            request.intent.mode = GenerationMode.replace
        return await _create_generation(request)

    @router.post("/api/v1/generation/drag")
    async def generate_drag(request: GenerationRequest) -> JobCreateResponse:
        if request.intent.mode != GenerationMode.drag_regenerate:
            request.intent.mode = GenerationMode.drag_regenerate
        return await _create_generation(request)

    @router.post("/api/v1/generation/diverge")
    async def generate_diverge(request: GenerationRequest) -> JobCreateResponse:
        if request.intent.mode != GenerationMode.diverge:
            request.intent.mode = GenerationMode.diverge
        return await _create_generation(request)

    @router.get("/api/v1/jobs/{job_id}")
    async def get_job(job_id: str):
        job = studio_store.get_job(job_id)
        if job is None:
            try:
                legacy = legacy_job_store.get(UUID(job_id))
            except ValueError:
                legacy = None
            if legacy is not None:
                return legacy
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
        return job

    @router.get("/api/v1/jobs/{job_id}/candidates")
    async def get_job_candidates(job_id: str) -> list[Candidate]:
        job = studio_store.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
        candidates: list[Candidate] = []
        for candidate_id in job.candidate_ids:
            candidate = studio_store.get_candidate(candidate_id)
            if candidate is not None:
                candidates.append(candidate)
        return candidates

    @router.post("/api/v1/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str):
        job = studio_store.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
        job.status = JobStatus.cancelled
        job.message = "Job cancelled"
        job.metadata["remote_cancel"] = await cancel_remote_worker_jobs(job)
        studio_store.save_job(job)
        await websocket_manager.broadcast(
            job.session_id,
            "job_update",
            {
                "job_id": job.job_id,
                "status": job.status,
                "stage": job.stage,
                "progress": job.progress,
                "message": job.message,
            },
        )
        return job

    @router.post("/api/v1/candidates")
    async def create_candidates_gone() -> JSONResponse:
        """Removed stub path (Phase E). Use POST /api/v1/generation/*."""
        log_deprecated_api("/api/v1/candidates", None)
        return JSONResponse(
            status_code=410,
            content={
                "error": {
                    "code": "CANDIDATES_ENDPOINT_GONE",
                    "message": (
                        "POST /api/v1/candidates has been removed. "
                        "Use POST /api/v1/generation/replace|drag|diverge."
                    ),
                    "retryable": False,
                    "details": {
                        "deprecated": True,
                        "deprecated_endpoint": "/api/v1/candidates",
                        "canonical_endpoint": "/api/v1/generation/replace",
                    },
                }
            },
        )

    return router
