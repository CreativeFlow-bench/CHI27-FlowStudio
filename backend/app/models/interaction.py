"""Authoritative interaction-orchestration contracts.

These records deliberately sit beside the legacy four-stage contracts.  The
four-stage pipeline remains a model-processing implementation detail; these
contracts describe the durable user-facing command lifecycle.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.base import now_utc


class InteractionTaskType(StrEnum):
    intent_planning = "intent_planning"
    semantic_divergence = "semantic_divergence"
    solution_generation = "solution_generation"


class InteractionTaskStatus(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"
    superseded = "superseded"


class InteractionAggregateType(StrEnum):
    intent_revision = "intent_revision"
    divergence_selection = "divergence_selection"
    generation_task = "generation_task"


class InteractionTask(BaseModel):
    task_id: str
    task_type: InteractionTaskType
    project_id: str | None = None
    session_id: str
    revision_id: str | None = None
    status: InteractionTaskStatus = InteractionTaskStatus.queued
    input_json: dict[str, Any] = Field(default_factory=dict)
    result_ref: str | None = None
    progress: float = Field(default=0.0, ge=0, le=1)
    attempt: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1, le=10)
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    idempotency_key: str
    created_at: datetime = Field(default_factory=now_utc)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    cancel_requested: bool = False
    updated_at: datetime = Field(default_factory=now_utc)

    @field_validator("idempotency_key")
    @classmethod
    def _idempotency_key_required(cls, value: str) -> str:
        value = str(value or "").strip()
        if not value:
            raise ValueError("idempotency_key is required")
        return value[:240]


class InteractionAuditEvent(BaseModel):
    audit_id: str
    command_id: str
    command_type: str
    idempotency_key: str
    project_id: str | None = None
    session_id: str
    revision_id: str | None = None
    actor: str = "user"
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=now_utc)
    correlation_id: str | None = None
    causation_id: str | None = None


class InteractionDomainEvent(BaseModel):
    event_id: str
    event_type: str
    project_id: str | None = None
    session_id: str
    revision_id: str | None = None
    intent_seq: int | None = None
    aggregate_type: InteractionAggregateType
    aggregate_id: str
    aggregate_version: int = Field(default=1, ge=1)
    correlation_id: str | None = None
    causation_id: str | None = None
    occurred_at: datetime = Field(default_factory=now_utc)
    payload: dict[str, Any] = Field(default_factory=dict)
    event_cursor: int = Field(default=0, ge=0)


class InteractionOutboxRecord(BaseModel):
    outbox_id: str
    event: InteractionDomainEvent
    published_at: datetime | None = None
    attempts: int = Field(default=0, ge=0)
    last_error: str | None = None


class InteractionProjection(BaseModel):
    revisions: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[InteractionTask] = Field(default_factory=list)
    solution_batches: list[dict[str, Any]] = Field(default_factory=list)
    last_event_cursor: int = 0


class InteractionCommandMeta(BaseModel):
    command_id: str
    idempotency_key: str
    expected_version: int | None = Field(default=None, ge=1)
    actor: str = "user"
    requested_at: datetime = Field(default_factory=now_utc)


__all__ = [
    "InteractionTaskType",
    "InteractionTaskStatus",
    "InteractionAggregateType",
    "InteractionTask",
    "InteractionAuditEvent",
    "InteractionDomainEvent",
    "InteractionOutboxRecord",
    "InteractionProjection",
    "InteractionCommandMeta",
]
