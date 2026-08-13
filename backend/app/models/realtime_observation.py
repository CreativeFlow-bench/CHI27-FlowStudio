"""Contracts for always-on observation and multi-intent revisions."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.base import now_utc
from app.models.experiment_project import UiBrief
from app.models.four_stage import DivergenceSelection, SourceContext
from app.models.semantic_divergence import SemanticDivergenceParams


class BehaviorStatus(StrEnum):
    active = "active"
    committed = "committed"


class IntentRevisionStatus(StrEnum):
    planning = "planning"
    awaiting_gate = "awaiting_gate"
    accepted = "accepted"
    rejected = "rejected"
    generating = "generating"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class VersionNodeStatus(StrEnum):
    image_ready = "image_ready"
    generating_3d = "generating_3d"
    mesh_ready = "mesh_ready"
    mesh_failed = "mesh_failed"


class BehaviorViewSet(BaseModel):
    front: str | None = None
    side: str | None = None
    top: str | None = None


class BehaviorSession(BaseModel):
    behavior_id: str
    session_id: str
    behavior_seq: int = Field(ge=1)
    tool: str
    target: dict[str, Any] = Field(default_factory=dict)
    status: BehaviorStatus = BehaviorStatus.active
    started_at: datetime = Field(default_factory=now_utc)
    ended_at: datetime | None = None
    stroke_count: int = Field(default=0, ge=0)
    operation_summary: dict[str, Any] = Field(default_factory=dict)
    start_views: BehaviorViewSet = Field(default_factory=BehaviorViewSet)
    end_views: BehaviorViewSet = Field(default_factory=BehaviorViewSet)
    evidence_refs: list[str] = Field(default_factory=list)


class BehaviorCommitRequest(BaseModel):
    behavior_id: str | None = None
    tool: str
    target: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    stroke_count: int = Field(default=1, ge=0)
    operation_summary: dict[str, Any] = Field(default_factory=dict)
    start_views: BehaviorViewSet = Field(default_factory=BehaviorViewSet)
    end_views: BehaviorViewSet = Field(default_factory=BehaviorViewSet)
    evidence_refs: list[str] = Field(default_factory=list)


class BehaviorStartRequest(BaseModel):
    behavior_id: str | None = None
    tool: str
    target: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None


class BehaviorPatchRequest(BaseModel):
    """Merge evidence onto an already-committed / active behavior (e.g. screenshot)."""

    operation_summary: dict[str, Any] | None = None
    evidence_refs: list[str] | None = None
    stroke_count: int | None = Field(default=None, ge=0)


class LiveObservationState(BaseModel):
    """Descriptive snapshot of what the 3D workspace currently shows.

    This is intentionally *not* an intent/phase inference. It reports the
    observable context (which operation the user just committed, at which
    scope, on which target) so downstream consumers can describe the live
    model. Design-state inference for retrieval is handled separately by the
    ``DesignStateIRRetriever`` over the feature stream.
    """

    session_id: str
    latest_behavior_seq: int = 0
    encoded_through_seq: int = 0
    operation: str = "observe"
    scope: str = "whole"
    target: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.0, ge=0, le=1)
    intent_confidence: float = Field(default=0.0, ge=0, le=1)
    behavior_count: int = 0
    retrieval_query: list[str] = Field(default_factory=list)
    retrieval_fingerprint: str | None = None
    intent_summary: str | None = None
    updated_at: datetime = Field(default_factory=now_utc)


class IntentRevisionCreateRequest(BaseModel):
    user_text: str = ""
    source_context: SourceContext
    run_hy3d: bool = False
    cutoff_seq: int | None = Field(default=None, ge=0)


class IntentRevisionSourceImageRequest(BaseModel):
    source_image_ref: str


class IntentRevision(BaseModel):
    revision_id: str
    session_id: str
    intent_seq: int = Field(ge=1)
    parent_revision_id: str | None = None
    window_start_seq: int = Field(ge=1)
    cutoff_seq: int = Field(ge=0)
    behavior_ids: list[str] = Field(default_factory=list)
    user_text: str = ""
    source_context: SourceContext
    status: IntentRevisionStatus = IntentRevisionStatus.planning
    version: int = Field(default=1, ge=1)
    selection_version: int = Field(default=0, ge=0)
    run_id: str | None = None
    gate_id: str | None = None
    gate_question: str | None = None
    gate_target: str | None = None
    gate_scope: str | None = None
    gate_provisional: bool = False
    base_keywords: list[str] = Field(default_factory=list)
    delta_keywords: list[str] = Field(default_factory=list)
    effective_keywords: list[str] = Field(default_factory=list)
    divergence_selection: DivergenceSelection | None = None
    semantic_divergence_status: str | None = None
    semantic_divergence_error: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)
    # LLM-generated natural-language description of current design phenomenon
    phenomenon: str | None = None

    @field_validator("base_keywords", "delta_keywords", "effective_keywords")
    @classmethod
    def _dedupe_keywords(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if text and text not in result:
                result.append(text[:80])
        return result


class RevisionGateRequest(BaseModel):
    accepted: bool
    divergence_params: SemanticDivergenceParams | None = None
    selected_option_id: str | None = None
    reason: str | None = None
    command_id: str | None = None
    idempotency_key: str | None = None
    expected_version: int | None = Field(default=None, ge=1)


class SolutionBatch(BaseModel):
    batch_id: str
    session_id: str
    revision_id: str
    intent_seq: int
    run_id: str
    append_index: int = Field(default=1, ge=1)
    parent_batch_id: str | None = None
    keyword_mode: str = "append"
    base_keywords: list[str] = Field(default_factory=list)
    delta_keywords: list[str] = Field(default_factory=list)
    cumulative_keywords: list[str] = Field(default_factory=list)
    source_context: SourceContext | None = None
    gate_id: str | None = None
    status: str = "queued"
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class VersionGraphNodeCreateRequest(BaseModel):
    parent_node_id: str | None = None
    candidate_id: str | None = None
    label: str
    preview_url: str | None = None
    status: VersionNodeStatus = VersionNodeStatus.generating_3d


class VersionGraphNodeUpdateRequest(BaseModel):
    status: VersionNodeStatus | None = None
    preview_url: str | None = None
    mesh_url: str | None = None
    obj_url: str | None = None
    hy3d_job_id: str | None = None
    error: str | None = None


class VersionGraphNode(BaseModel):
    node_id: str
    session_id: str
    version_number: int = Field(ge=1)
    parent_node_id: str | None = None
    candidate_id: str | None = None
    label: str
    preview_url: str | None = None
    mesh_url: str | None = None
    obj_url: str | None = None
    status: VersionNodeStatus = VersionNodeStatus.image_ready
    hy3d_job_id: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class VersionGraphState(BaseModel):
    active_node_id: str | None = None
    nodes: list[VersionGraphNode] = Field(default_factory=list)


class RealtimeObservationSnapshot(BaseModel):
    observation: LiveObservationState
    behaviors: list[BehaviorSession] = Field(default_factory=list)
    revisions: list[IntentRevision] = Field(default_factory=list)
    solution_batches: list[SolutionBatch] = Field(default_factory=list)
    version_graph: VersionGraphState = Field(default_factory=VersionGraphState)
    ui_brief: UiBrief


__all__ = [
    "BehaviorCommitRequest",
    "BehaviorPatchRequest",
    "BehaviorSession",
    "BehaviorStartRequest",
    "BehaviorStatus",
    "BehaviorViewSet",
    "IntentRevision",
    "IntentRevisionCreateRequest",
    "IntentRevisionSourceImageRequest",
    "IntentRevisionStatus",
    "LiveObservationState",
    "RealtimeObservationSnapshot",
    "RevisionGateRequest",
    "SolutionBatch",
    "VersionGraphNode",
    "VersionGraphNodeCreateRequest",
    "VersionGraphNodeUpdateRequest",
    "VersionGraphState",
    "VersionNodeStatus",
]
