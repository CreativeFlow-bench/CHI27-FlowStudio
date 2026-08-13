from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from typing import Any


def now_utc() -> datetime:
    return datetime.now(UTC)
class SessionStatus(StrEnum):
    active = "active"
    paused = "paused"
    completed = "completed"
    archived = "archived"


class DesignPhase(StrEnum):
    idle = "idle"
    exploring = "exploring"
    part_selection = "part_selection"
    local_replacement = "local_replacement"
    drag_modification = "drag_modification"
    candidate_comparison = "candidate_comparison"
    refinement = "refinement"
    finalizing = "finalizing"


class GenerationMode(StrEnum):
    replace = "replace"
    drag_regenerate = "drag_regenerate"
    diverge = "diverge"
    refine = "refine"


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class JobStage(StrEnum):
    queued = "queued"
    transfer = "transfer"
    graph_expansion = "graph_expansion"
    relation_generation = "relation_generation"
    image_generation = "image_generation"
    postprocess_3d = "postprocess_3d"
    mesh_generation = "mesh_generation"
    asset_normalization = "asset_normalization"
    asset_upload = "asset_upload"
    completed = "completed"
    failed = "failed"


class SelectionType(StrEnum):
    part = "part"
    brush = "brush"
    bbox = "bbox"
    mesh_region = "mesh_region"
    none = "none"


class CandidateDecision(StrEnum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    saved = "saved"


class AssistancePolicy(StrEnum):
    observe = "observe"
    interpret_silently = "interpret_silently"
    soft_suggestion = "soft_suggestion"
    proactive_candidate = "proactive_candidate"
    ask_clarification = "ask_clarification"


class IntentLabel(StrEnum):
    target_part = "target_part"
    semantic_focus = "semantic_focus"
    replace_region = "replace_region"
    refine_boundary = "refine_boundary"
    protect_region = "protect_region"
    compare_region = "compare_region"
    extend_part = "extend_part"
    shrink_part = "shrink_part"
    bend_or_curve = "bend_or_curve"
    reposition_part = "reposition_part"
    change_proportion = "change_proportion"
    open_space = "open_space"
    emphasize_feature = "emphasize_feature"
    deform_surface = "deform_surface"
    explore_shape = "explore_shape"
    compare_candidates = "compare_candidates"
    accept_direction = "accept_direction"
    reject_direction = "reject_direction"
    refine_candidate = "refine_candidate"
    finalize_design = "finalize_design"
    unknown = "unknown"


class ApiErrorBody(BaseModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class ApiError(BaseModel):
    error: ApiErrorBody


__all__ = [
    "now_utc",
    "SessionStatus",
    "DesignPhase",
    "GenerationMode",
    "JobStatus",
    "JobStage",
    "SelectionType",
    "CandidateDecision",
    "AssistancePolicy",
    "IntentLabel",
    "ApiErrorBody",
    "ApiError",
]
