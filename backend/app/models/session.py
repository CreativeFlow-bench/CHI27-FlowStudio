from datetime import UTC, datetime

from typing import Any
from pydantic import BaseModel, Field
from app.models.base import now_utc
from app.models.base import DesignPhase, SessionStatus

class StageState(BaseModel):
    phase: DesignPhase = DesignPhase.idle
    confidence: float = Field(default=1.0, ge=0, le=1)
    current_goal: str | None = None
    active_asset_id: str | None = None
    active_part_id: str | None = None
    suggested_action: str | None = None
    evidence: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=now_utc)


class SessionCreateRequest(BaseModel):
    title: str = "Untitled FlowStudio session"
    user_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionUpdateRequest(BaseModel):
    title: str | None = None
    status: SessionStatus | None = None
    metadata: dict[str, Any] | None = None


class SessionRecord(BaseModel):
    session_id: str
    title: str
    user_id: str | None = None
    status: SessionStatus = SessionStatus.active
    stage: StageState = Field(default_factory=StageState)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


__all__ = [
    "StageState",
    "SessionCreateRequest",
    "SessionUpdateRequest",
    "SessionRecord",
]
