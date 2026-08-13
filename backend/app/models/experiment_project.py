"""Contracts for durable, append-only experiment project recording."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.base import now_utc


class ProjectStatus(StrEnum):
    active = "active"
    completed = "completed"
    archived = "archived"


class RecordingStatus(StrEnum):
    healthy = "healthy"
    degraded = "degraded"
    paused = "paused"
    ended = "ended"


class BaselineMode(StrEnum):
    blank = "blank"
    current_state = "current_state"


class ProjectFile(BaseModel):
    project_id: str
    title: str
    participant_code: str | None = None
    condition_label: str | None = None
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    status: ProjectStatus = ProjectStatus.active
    active_run_id: str | None = None
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class ExperimentRun(BaseModel):
    run_id: str
    project_id: str
    session_id: str
    run_number: int = Field(ge=1)
    baseline_mode: BaselineMode = BaselineMode.blank
    started_at: datetime = Field(default_factory=now_utc)
    ended_at: datetime | None = None
    next_event_seq: int = Field(default=1, ge=1)
    recording_status: RecordingStatus = RecordingStatus.healthy


class ProjectAssetReference(BaseModel):
    ref_id: str
    project_id: str
    run_id: str
    asset_id: str | None = None
    artifact_id: str | None = None
    role: str
    sha256: str | None = None
    byte_size: int | None = Field(default=None, ge=0)
    mime_type: str | None = None
    storage_key: str | None = None
    source_event_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=now_utc)


class ExperimentEvent(BaseModel):
    event_id: str
    project_id: str
    run_id: str
    session_id: str
    seq: int = Field(ge=1)
    event_type: str
    actor: Literal["user", "model", "system", "worker"]
    occurred_at: datetime | None = None
    recorded_at: datetime = Field(default_factory=now_utc)
    correlation_id: str | None = None
    parent_event_id: str | None = None
    idempotency_key: str
    payload: dict[str, Any] = Field(default_factory=dict)
    asset_refs: list[dict[str, Any]] = Field(default_factory=list)
    schema_version: str = "flowstudio.experiment-event.v1"


class ProjectCreateRequest(BaseModel):
    title: str = "Untitled experiment"
    participant_code: str | None = None
    condition_label: str | None = None
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    session_id: str
    baseline_mode: BaselineMode = BaselineMode.blank
    baseline_snapshot: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdateRequest(BaseModel):
    title: str | None = None
    participant_code: str | None = None
    condition_label: str | None = None
    notes: str | None = None
    tags: list[str] | None = None
    status: ProjectStatus | None = None


class ProjectEventCreate(BaseModel):
    event_type: str
    actor: Literal["user", "model", "system", "worker"] = "user"
    idempotency_key: str
    occurred_at: datetime | None = None
    correlation_id: str | None = None
    parent_event_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    asset_refs: list[dict[str, Any]] = Field(default_factory=list)
    schema_version: str = "flowstudio.experiment-event.v1"


class ProjectEventBatchRequest(BaseModel):
    events: list[ProjectEventCreate] = Field(min_length=1, max_length=100)


class ProjectRunCreateRequest(BaseModel):
    session_id: str
    baseline_mode: BaselineMode = BaselineMode.blank
    baseline_snapshot: dict[str, Any] = Field(default_factory=dict)


class ProjectEventExclusionRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class ProjectDetail(BaseModel):
    project: ProjectFile
    active_run: ExperimentRun | None = None
    asset_refs: list[ProjectAssetReference] = Field(default_factory=list)


class ProjectEventPage(BaseModel):
    items: list[ExperimentEvent] = Field(default_factory=list)
    next_cursor: int | None = None


class ProjectExportRecord(BaseModel):
    export_id: str
    project_id: str
    status: Literal["queued", "completed", "failed"] = "queued"
    file_url: str | None = None
    file_path: str | None = None
    missing_asset_refs: list[str] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class UiBrief(BaseModel):
    phenomenon: str
    next_question: str = ""
    requires_response: bool = False
    question_id: str | None = None
    status: str = "idle"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    details_ref: str | None = None
    pending_decision_count: int = Field(default=0, ge=0)


__all__ = [
    "BaselineMode",
    "ExperimentEvent",
    "ExperimentRun",
    "ProjectAssetReference",
    "ProjectCreateRequest",
    "ProjectDetail",
    "ProjectEventBatchRequest",
    "ProjectEventCreate",
    "ProjectEventExclusionRequest",
    "ProjectEventPage",
    "ProjectExportRecord",
    "ProjectFile",
    "ProjectRunCreateRequest",
    "ProjectStatus",
    "ProjectUpdateRequest",
    "RecordingStatus",
    "UiBrief",
]
