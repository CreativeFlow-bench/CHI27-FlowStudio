from datetime import UTC, datetime

from typing import Any
from pydantic import BaseModel, Field
from app.models.base import now_utc

class CaseCreateRequest(BaseModel):
    session_id: str
    title: str
    asset_id: str
    accepted_candidate_ids: list[str] = Field(default_factory=list)
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseRecord(BaseModel):
    case_id: str
    session_id: str
    title: str
    asset_id: str
    accepted_candidate_ids: list[str] = Field(default_factory=list)
    notes: str | None = None
    report_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=now_utc)


__all__ = [
    "CaseCreateRequest",
    "CaseRecord",
]
