from datetime import UTC, datetime

from typing import Any
from typing import Literal
from pydantic import BaseModel, Field
from app.models.base import now_utc
from app.models.intent import ActionAtom
from app.models.direction import AnalogyDirection
from app.models.asset import AssetRecord
from app.models.asset import AssetVersionRecord
from app.models.generation import Candidate
from app.models.case import CaseRecord
from app.models.intent import IntentDraft
from app.models.planner import InteractionInterpretation
from app.models.generation import JobRecord
from app.models.asset import PartRecord
from app.models.session import SessionRecord
from app.models.generation import WorkerJobRecord

class ArtifactRecord(BaseModel):
    artifact_id: str
    type: str
    url: str
    session_id: str | None = None
    asset_id: str | None = None
    candidate_id: str | None = None
    part_id: str | None = None
    worker: Literal["geometry", "render", "remote", "manual"] = "manual"
    job_id: str | None = None
    operation: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=now_utc)


class MemoryRecord(BaseModel):
    memory_id: str
    session_id: str
    category: Literal["working", "episodic", "semantic", "procedural", "reflective"]
    type: str
    content: dict[str, Any] = Field(default_factory=dict)
    source_id: str | None = None
    asset_id: str | None = None
    part_id: str | None = None
    candidate_id: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class MemoryListResponse(BaseModel):
    memories: list[MemoryRecord] = Field(default_factory=list)


class UserEvent(BaseModel):
    type: str
    event_id: str
    session_id: str
    timestamp: datetime = Field(default_factory=now_utc)
    payload: dict[str, Any] = Field(default_factory=dict)


class WebSocketMessage(BaseModel):
    type: str
    event_id: str
    session_id: str
    timestamp: datetime = Field(default_factory=now_utc)
    payload: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "ArtifactRecord",
    "MemoryRecord",
    "MemoryListResponse",
    "StoreStateSnapshot",
    "StoreStateImportRequest",
    "StoreStateImportResponse",
    "ArtifactListResponse",
    "SessionSnapshotResponse",
    "UserEvent",
    "WebSocketMessage",
]


class StoreStateSnapshot(BaseModel):
    version: int = 1
    exported_at: datetime = Field(default_factory=now_utc)
    sessions: list[SessionRecord] = Field(default_factory=list)
    assets: list[AssetRecord] = Field(default_factory=list)
    jobs: list[JobRecord] = Field(default_factory=list)
    candidates: list[Candidate] = Field(default_factory=list)
    cases: list[CaseRecord] = Field(default_factory=list)
    asset_versions: list["AssetVersionRecord"] = Field(default_factory=list)
    artifacts: list[ArtifactRecord] = Field(default_factory=list)
    worker_jobs: list[WorkerJobRecord] = Field(default_factory=list)
    memories: list[MemoryRecord] = Field(default_factory=list)
    intent_drafts: list[IntentDraft] = Field(default_factory=list)
    action_atoms: list[ActionAtom] = Field(default_factory=list)
    directions: list[AnalogyDirection] = Field(default_factory=list)
    events: list["UserEvent"] = Field(default_factory=list)
    interpretations: list["InteractionInterpretation"] = Field(default_factory=list)
    session_action_atoms: dict[str, list[str]] = Field(default_factory=dict)
    session_directions: dict[str, list[str]] = Field(default_factory=dict)
    session_events: dict[str, list[str]] = Field(default_factory=dict)
    session_interpretations: dict[str, list[str]] = Field(default_factory=dict)


class StoreStateImportRequest(BaseModel):
    snapshot: StoreStateSnapshot
    replace: bool = False


class StoreStateImportResponse(BaseModel):
    imported: dict[str, int]
    replaced: bool = False


class ArtifactListResponse(BaseModel):
    artifacts: list[ArtifactRecord] = Field(default_factory=list)


class SessionSnapshotResponse(BaseModel):
    session: SessionRecord
    active_asset: AssetRecord | None = None
    active_parts: list[PartRecord] = Field(default_factory=list)
    active_job: JobRecord | None = None
    live_signals: dict[str, Any] = Field(default_factory=dict)
    visible_candidates: list[Candidate] = Field(default_factory=list)
    recent_events: list[UserEvent] = Field(default_factory=list)
    recent_interpretations: list[InteractionInterpretation] = Field(default_factory=list)
    artifacts: list[ArtifactRecord] = Field(default_factory=list)
    intent_drafts: list[IntentDraft] = Field(default_factory=list)
    action_atoms: list[ActionAtom] = Field(default_factory=list)
    directions: list[AnalogyDirection] = Field(default_factory=list)
    memory: dict[str, list[MemoryRecord]] = Field(default_factory=dict)
    solution_space: dict[str, Any] = Field(default_factory=dict)


