"""Four-stage pipeline data contracts (FlowStudio intent encoding -> generation).

These models are the only boundary objects allowed to flow between pipeline
stages. Nothing outside this module may pass an unvalidated dict as a stage
output (strategy doc section 4 / 5).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.base import now_utc
from app.models.semantic_divergence import SemanticDivergenceParams, SemanticDivergenceResponse
from app.models.store import UserEvent

INTENT_IR_SCHEMA_VERSION = "flowstudio.intent-ir.v1"
RETRIEVAL_SCHEMA_VERSION = "flowstudio.retrieval.v1"
DECISION_IR_SCHEMA_VERSION = "flowstudio.decision-ir.v1"
GENERATION_SPEC_SCHEMA_VERSION = "flowstudio.generation-spec.v2"
FOUR_STAGE_RUN_SCHEMA_VERSION = "flowstudio.four-stage-run.v1"

_GENERIC_OBJECT_TYPES = frozenset({"", "object", "unknown", "item", "thing", "model", "asset"})


def is_concrete_object_type(value: str | None) -> bool:
    """Return whether an object type is specific enough for generation.

    The legacy API still accepts ``object`` for old uploads, but the four-stage
    generation path must never use that placeholder as source identity.
    """

    normalized = str(value or "").strip().lower().replace("_", " ")
    return bool(normalized) and normalized not in _GENERIC_OBJECT_TYPES


class FourStageStage(StrEnum):
    raw_events = "raw_events"
    encoding = "encoding"
    retrieval = "retrieval"
    re_representation = "re_representation"
    awaiting_gate = "awaiting_gate"
    generation = "generation"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class GateAction(StrEnum):
    accept_option = "accept_option"
    reject_all = "reject_all"
    request_revision = "request_revision"
    clarify = "clarify"


class IntentTarget(BaseModel):
    asset_id: str | None = None
    object_type: str | None = None
    part_id: str | None = None
    region: dict[str, Any] | None = None


class SourceContext(BaseModel):
    """Concrete source identity carried through every generation request."""

    asset_id: str
    object_type: str
    version_id: str | None = None
    source_image_ref: str | None = None
    source_model_ref: str | None = None
    target_part_id: str | None = None
    target_mask_ref: str | None = None
    camera_ref: str | None = None

    @field_validator("asset_id", "object_type")
    @classmethod
    def _required_text(cls, value: str) -> str:
        value = str(value or "").strip()
        if not value:
            raise ValueError("source context requires concrete asset identity")
        return value

    @field_validator("object_type")
    @classmethod
    def _concrete_object_type(cls, value: str) -> str:
        if not is_concrete_object_type(value):
            raise ValueError("source context object_type must be concrete, not object/unknown")
        return value


class ScopeGate(BaseModel):
    """The only user-facing question before More Creative opens."""

    gate_id: str
    target: str
    scope: str = "whole"
    question: str
    status: str = "pending"
    user_action: str | None = None


class DivergenceSelection(BaseModel):
    """Human-selected divergence direction; never converted to an ActionAtom."""

    scope: str = "whole"
    target_part_id: str | None = None
    selected_candidate_ids: list[str] = Field(default_factory=list, max_length=12)
    selected_keywords: list[str] = Field(default_factory=list, max_length=12)
    resolved_prompt_phrases: list[str] = Field(default_factory=list, max_length=12)
    user_text: str | None = None
    dimensions: dict[str, list[str]] = Field(default_factory=dict)
    system_keywords: list[str] = Field(default_factory=list, max_length=12)
    command_id: str | None = None
    idempotency_key: str | None = None
    expected_version: int | None = Field(default=None, ge=1)
    expected_selection_version: int | None = Field(default=None, ge=0)

    @field_validator("selected_keywords", "system_keywords")
    @classmethod
    def _dedupe_keywords(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if text and text not in result:
                result.append(text[:80])
        return result


class IntentObservations(BaseModel):
    viewport: dict[str, Any] = Field(default_factory=dict)
    interaction_summary: dict[str, Any] = Field(default_factory=dict)
    text: str | None = None
    image_refs: list[str] = Field(default_factory=list)
    model_refs: list[str] = Field(default_factory=list)


class IntentCore(BaseModel):
    operation: str = "observe"
    scope: str = "whole"
    goal: str | None = None
    constraints: list[str] = Field(default_factory=list)
    preferred_axes: list[str] = Field(default_factory=list)


class IntentProvenance(BaseModel):
    encoder: str = "qwen3-8b"
    encoder_version: str = "qwen3-planner"
    prompt_version: str = "intent-ir-v1"
    fallback_used: bool = False


class IntentIRHypothesis(BaseModel):
    hypothesis_id: str
    text: str
    confidence: float = Field(default=0.5, ge=0, le=1)
    evidence_refs: list[str] = Field(default_factory=list)


class IntentIR(BaseModel):
    schema_version: str = INTENT_IR_SCHEMA_VERSION
    ir_id: str
    run_id: str
    session_id: str
    episode_id: str | None = None
    source_event_ids: list[str] = Field(default_factory=list)
    target: IntentTarget = Field(default_factory=IntentTarget)
    observations: IntentObservations = Field(default_factory=IntentObservations)
    intent: IntentCore = Field(default_factory=IntentCore)
    hypotheses: list[IntentIRHypothesis] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0, le=1)
    ambiguity: float = Field(default=0.5, ge=0, le=1)
    provenance: IntentProvenance = Field(default_factory=IntentProvenance)
    created_at: datetime = Field(default_factory=now_utc)
    # LLM-generated natural-language description of the current design phenomenon
    phenomenon: str | None = None


class RetrievalMatch(BaseModel):
    prior_ir_id: str
    case_id: str | None = None
    sparse_score: float = 0.0
    metadata_score: float = 0.0
    outcome_score: float = 0.0
    final_score: float = 0.0
    prior_judgement: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    outcome: dict[str, Any] = Field(default_factory=dict)


class RetrievalBundle(BaseModel):
    schema_version: str = RETRIEVAL_SCHEMA_VERSION
    retrieval_id: str
    run_id: str
    query_ir_id: str
    data_version: str = "design-state-ir-2026-08-v1"
    retriever: str = "design-state-ir-sparse-v1"
    matches: list[RetrievalMatch] = Field(default_factory=list)
    abstained: bool = False
    abstain_reason: str | None = None
    created_at: datetime = Field(default_factory=now_utc)


class DecisionOption(BaseModel):
    option_id: str
    label: str
    rationale: str | None = None
    confidence: float = Field(default=0.5, ge=0, le=1)
    evidence_refs: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    divergence_seeds: list[str] = Field(default_factory=list)


class DecisionIR(BaseModel):
    schema_version: str = DECISION_IR_SCHEMA_VERSION
    decision_id: str
    run_id: str
    intent_ir_id: str
    retrieval_id: str | None = None
    summary: str | None = None
    recommended_scope: str | None = None
    semantic_target: str | None = None
    gate_question: str | None = None
    options: list[DecisionOption] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str | None = None
    confidence: float = Field(default=0.5, ge=0, le=1)
    model: str = "gemini-3.5-flash"
    prompt_version: str = "re-representation-v1"
    created_at: datetime = Field(default_factory=now_utc)


class GenerationTarget(BaseModel):
    scope: str = "whole"
    part_id: str | None = None


class GenerationSpec(BaseModel):
    schema_version: str = GENERATION_SPEC_SCHEMA_VERSION
    generation_id: str
    run_id: str
    decision_id: str
    selected_option_id: str
    source: SourceContext | None = None
    asset_id: str | None = None
    object_type: str | None = None
    target: GenerationTarget = Field(default_factory=GenerationTarget)
    keywords: list[str] = Field(default_factory=list)
    selected_keywords: list[str] = Field(default_factory=list)
    dimensions: dict[str, list[str]] = Field(default_factory=dict)
    prompt_candidates: list[str] = Field(default_factory=list)
    preserved_constraints: list[str] = Field(default_factory=list)
    candidate_count: int = Field(default=8, ge=1, le=8)
    model: str = "Qwen-Image-2512"
    seeds: list[int] = Field(default_factory=list)
    run_hy3d: bool = False
    require_white_background: bool = True
    require_single_object: bool = True
    require_full_object: bool = True
    created_at: datetime = Field(default_factory=now_utc)


class GateDecision(BaseModel):
    decision_id: str
    run_id: str
    action: GateAction
    selected_option_id: str | None = None
    user_revision: str | None = None
    reason: str | None = None
    created_at: datetime = Field(default_factory=now_utc)


class FourStageRun(BaseModel):
    schema_version: str = FOUR_STAGE_RUN_SCHEMA_VERSION
    run_id: str
    session_id: str
    idempotency_key: str | None = None
    episode_id: str | None = None
    stage: FourStageStage = FourStageStage.raw_events
    run_hy3d: bool = False
    events: list[UserEvent] = Field(default_factory=list)
    source_event_ids: list[str] = Field(default_factory=list)
    source_context: SourceContext | None = None
    intent_ir: IntentIR | None = None
    retrieval: RetrievalBundle | None = None
    decision: DecisionIR | None = None
    scope_gate: ScopeGate | None = None
    semantic_divergence: SemanticDivergenceResponse | None = None
    divergence_selection: DivergenceSelection | None = None
    gate_decision: GateDecision | None = None
    generation_spec: GenerationSpec | None = None
    generation_artifacts: list[dict[str, Any]] = Field(default_factory=list)
    error: dict[str, Any] | None = None
    failed_stage: FourStageStage | None = None
    retry_count: int = 0
    stage_timestamps: dict[str, dict[str, str]] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)
    completed_at: datetime | None = None
    # LLM-generated natural-language description of current design phenomenon
    phenomenon: str | None = None


class FourStageRunCreateRequest(BaseModel):
    session_id: str
    idempotency_key: str | None = None
    episode_id: str | None = None
    run_hy3d: bool = False
    auto_advance: bool = True
    events: list[UserEvent] = Field(default_factory=list)
    source_context: SourceContext | None = None

    @field_validator("events")
    @classmethod
    def _bound_events(cls, events: list[UserEvent]) -> list[UserEvent]:
        if len(events) > 128:
            raise ValueError("events exceeds the 128-event bound")
        return events


class GateRequest(BaseModel):
    run_id: str | None = None
    action: GateAction
    selected_option_id: str | None = None
    user_revision: str | None = None
    reason: str | None = None
    divergence_params: SemanticDivergenceParams | None = None
    # Kept true for legacy API clients. The product UI sends false so the
    # accepted scope Gate opens More Creative and waits for an explicit
    # keyword selection + Generate click.
    auto_generate: bool = True


__all__ = [
    "INTENT_IR_SCHEMA_VERSION",
    "RETRIEVAL_SCHEMA_VERSION",
    "DECISION_IR_SCHEMA_VERSION",
    "GENERATION_SPEC_SCHEMA_VERSION",
    "FOUR_STAGE_RUN_SCHEMA_VERSION",
    "is_concrete_object_type",
    "FourStageStage",
    "GateAction",
    "IntentTarget",
    "SourceContext",
    "ScopeGate",
    "DivergenceSelection",
    "IntentObservations",
    "IntentCore",
    "IntentProvenance",
    "IntentIRHypothesis",
    "IntentIR",
    "RetrievalMatch",
    "RetrievalBundle",
    "DecisionOption",
    "DecisionIR",
    "GenerationTarget",
    "GenerationSpec",
    "GateDecision",
    "FourStageRun",
    "FourStageRunCreateRequest",
    "GateRequest",
]
