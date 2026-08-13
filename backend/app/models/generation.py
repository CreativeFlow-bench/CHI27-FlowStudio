from datetime import UTC, datetime

from typing import Any
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field
from app.models.base import now_utc
from app.models.intent import GenerationRequest
from app.models.session import StageState
from app.models.base import ApiErrorBody, CandidateDecision, JobStage, JobStatus

class JobCreateResponse(BaseModel):
    job_id: str
    session_id: str
    status: JobStatus
    stage: JobStage
    created_at: datetime


class Candidate(BaseModel):
    candidate_id: str
    job_id: str
    session_id: str
    source_asset_id: str
    source_part_id: str | None = None
    label: str
    decision: CandidateDecision = CandidateDecision.pending
    thumbnail_url: str | None = None
    mesh_url: str | None = None
    obj_url: str | None = None
    scores: dict[str, float] = Field(default_factory=dict)
    solution_space: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobRecord(BaseModel):
    job_id: str
    session_id: str
    status: JobStatus = JobStatus.queued
    stage: JobStage = JobStage.queued
    progress: float = Field(default=0, ge=0, le=1)
    message: str | None = None
    candidate_ids: list[str] = Field(default_factory=list)
    error: ApiErrorBody | None = None
    request: GenerationRequest | None = None
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CandidateDecisionRequest(BaseModel):
    session_id: str
    reason: str | None = None
    make_active_asset: bool = False


class CandidateFitRequest(BaseModel):
    session_id: str
    target_part_id: str | None = None
    policy: Literal["bbox_uniform", "bbox_axis_aligned"] = "bbox_uniform"


class CandidateDecisionResponse(BaseModel):
    candidate_id: str
    decision: CandidateDecision
    active_asset_id: str | None = None
    updated_stage: StageState


class GeometryWorkerRequest(BaseModel):
    session_id: str | None = None
    asset_id: str | None = None
    candidate_id: str | None = None
    source_mesh_url: str | None = None
    source_mesh_path: str | None = None
    candidate_mesh_url: str | None = None
    candidate_mesh_path: str | None = None
    part: dict[str, Any] | None = None
    face_indices: list[int] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)


class GeometryWorkerResponse(BaseModel):
    ok: bool
    job_id: str
    status: JobStatus
    operation: str
    result_mesh_url: str | None = None
    preview_mesh_url: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    error: ApiErrorBody | None = None


class RenderPreviewRequest(BaseModel):
    session_id: str | None = None
    asset_id: str | None = None
    candidate_id: str | None = None
    source_mesh_url: str | None = None
    source_mesh_path: str | None = None
    candidate_mesh_url: str | None = None
    candidate_mesh_path: str | None = None
    part: dict[str, Any] | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class RenderPreviewResponse(BaseModel):
    ok: bool
    job_id: str
    status: JobStatus
    operation: str
    thumbnail_url: str | None = None
    views: dict[str, str] = Field(default_factory=dict)
    turntable_video_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    error: ApiErrorBody | None = None


class RemoteTransferJobRequest(BaseModel):
    request: GenerationRequest
    flowstudio_job_id: str


class RemoteHy3DJobRequest(BaseModel):
    transfer_job_id: str
    candidate_ids: list[str] = Field(default_factory=list)
    output_format: str = "glb"


# Backward-compatible minimal candidate API used by the original prototype tests.


class DragIntent(BaseModel):
    part_id: str
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    influence_radius: float = Field(default=0.2, gt=0)


class CandidateRequest(BaseModel):
    asset_id: str
    source_part_id: str
    relation_prompt: str | None = None
    drag_intent: DragIntent | None = None
    candidate_count: int = Field(default=6, ge=1, le=24)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LegacyCandidate(BaseModel):
    id: str
    label: str
    relation: str
    mesh_url: str | None = None
    thumbnail_url: str | None = None
    scores: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CandidateResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    candidates: list[LegacyCandidate]


class LegacyJobRecord(BaseModel):
    job_id: UUID
    status: JobStatus
    request: CandidateRequest
    candidates: list[LegacyCandidate] = Field(default_factory=list)
    error: str | None = None


class WorkerJobRecord(BaseModel):
    job_id: str
    worker: Literal["geometry", "render"]
    operation: str
    status: JobStatus
    ok: bool
    session_id: str | None = None
    asset_id: str | None = None
    candidate_id: str | None = None
    request: dict[str, Any] = Field(default_factory=dict)
    response: dict[str, Any] = Field(default_factory=dict)
    artifact_ids: list[str] = Field(default_factory=list)
    error: ApiErrorBody | None = None
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


__all__ = [
    "JobCreateResponse",
    "Candidate",
    "JobRecord",
    "CandidateDecisionRequest",
    "CandidateFitRequest",
    "CandidateDecisionResponse",
    "GeometryWorkerRequest",
    "GeometryWorkerResponse",
    "RenderPreviewRequest",
    "RenderPreviewResponse",
    "RemoteTransferJobRequest",
    "RemoteHy3DJobRequest",
    "DragIntent",
    "CandidateRequest",
    "LegacyCandidate",
    "CandidateResponse",
    "LegacyJobRecord",
    "WorkerJobRecord",
]
