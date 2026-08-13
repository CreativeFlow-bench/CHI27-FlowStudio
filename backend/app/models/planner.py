from datetime import UTC, datetime

from typing import Any
from typing import Literal
from pydantic import BaseModel, Field
from app.models.base import now_utc
from app.models.direction import AnalogyDirection
from app.models.direction import CrossDomainDivergenceResponse
from app.models.semantic import SemanticTarget
from app.models.session import StageState
from app.models.base import AssistancePolicy, GenerationMode, IntentLabel

class IntentHypothesis(BaseModel):
    intent: IntentLabel
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)


class AssistanceSuggestion(BaseModel):
    type: Literal["generate", "ask", "notify", "highlight"] = "notify"
    mode: GenerationMode | None = None
    label: str | None = None
    question: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InterpretationTarget(BaseModel):
    asset_id: str | None = None
    part_id: str | None = None
    region: dict[str, Any] | None = None


class SupervisorVote(BaseModel):
    supervisor: str
    level_scores: dict[str, float] = Field(default_factory=dict)
    part_candidates: list[dict[str, Any]] = Field(default_factory=list)
    material_candidates: list[dict[str, Any]] = Field(default_factory=list)
    silhouette_evidence: list[str] = Field(default_factory=list)
    operation_hint: str | None = None
    conflict: str | None = None
    evidence: list[str] = Field(default_factory=list)


class CognitionOutput(BaseModel):
    supervisor: str = "cognition"
    hesitation: float = Field(default=0.0, ge=0, le=1)
    fixation_stable: bool = False
    creative_state: str = "idle"
    confidence_modifier: float = Field(default=1.0, ge=0, le=1)
    require_clarification: bool = False
    evidence: list[str] = Field(default_factory=list)


class InteractionInterpretation(BaseModel):
    interpretation_id: str
    session_id: str
    source_event_id: str
    action_type: str
    predictor: str = "rule_based_multisignal"
    predictor_version: str = "v0"
    predictor_metadata: dict[str, Any] = Field(default_factory=dict)
    primary_intent: IntentLabel
    confidence: float = Field(ge=0, le=1)
    ambiguity: float = Field(ge=0, le=1)
    target: InterpretationTarget = Field(default_factory=InterpretationTarget)
    hypotheses: list[IntentHypothesis] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    assistance_policy: AssistancePolicy = AssistancePolicy.observe
    suggested_assistance: list[AssistanceSuggestion] = Field(default_factory=list)
    semantic_targets: list[SemanticTarget] = Field(default_factory=list)
    supervision_votes: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=now_utc)
    features: dict[str, Any] = Field(default_factory=dict)


class PlannerInterpretationDecisionRequest(BaseModel):
    session_id: str
    decision: Literal["accepted", "rejected"]
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlannerInterpretationDecisionResponse(BaseModel):
    interpretation_id: str
    session_id: str
    decision: Literal["accepted", "rejected"]
    event_id: str
    memory_id: str
    updated_stage: StageState
    suggested_directions: list[AnalogyDirection] = Field(default_factory=list)
    direction_response: CrossDomainDivergenceResponse | None = None


__all__ = [
    "IntentHypothesis",
    "AssistanceSuggestion",
    "InterpretationTarget",
    "SupervisorVote",
    "CognitionOutput",
    "InteractionInterpretation",
    "PlannerInterpretationDecisionRequest",
    "PlannerInterpretationDecisionResponse",
]
