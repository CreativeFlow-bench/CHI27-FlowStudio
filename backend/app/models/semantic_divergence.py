"""Contracts for post-Gate semantic divergence."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


SEMANTIC_DIVERGENCE_SCHEMA_VERSION = "flowstudio.semantic-divergence.v1"


class SemanticDivergenceParams(BaseModel):
    temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    strictness: float = Field(default=0.6, ge=0.0, le=1.0)
    per_group_count: int | None = Field(default=5, ge=5, le=8)
    candidate_count: int | None = Field(default=None, ge=9, le=32)
    inherited_keywords: list[str] = Field(default_factory=list, max_length=24)
    # Preflight: start divergence while Gate is still pending; accept reuses cache.
    preflight: bool = False

    @model_validator(mode="after")
    def derive_candidate_count(self) -> "SemanticDivergenceParams":
        explicit_count = "candidate_count" in self.model_fields_set
        explicit_per_group = "per_group_count" in self.model_fields_set
        if explicit_count and not explicit_per_group:
            # Persisted pre-quota tasks used a 9–15 total without group quotas.
            self.per_group_count = None
        elif self.per_group_count is not None:
            self.candidate_count = self.per_group_count * 4
        elif self.candidate_count is None:
            self.candidate_count = max(9, min(15, round(9 + 6 * self.temperature)))
        return self

    @property
    def model_temperature(self) -> float:
        return round(0.15 + 0.75 * self.temperature, 3)

    @property
    def thresholds(self) -> dict[str, float]:
        return {
            "identity": 0.55 + 0.35 * self.strictness,
            "scope": 0.55 + 0.40 * self.strictness,
            "relevance": 0.45 + 0.40 * self.strictness,
        }


class SemanticTarget(BaseModel):
    level: str
    part_id: str | None = None
    label_zh: str | None = None
    label_en: str | None = None
    wikidata_qid: str | None = None
    mask_ref: str | None = None
    semantic_role: str | None = None


class SemanticDivergenceRequest(BaseModel):
    run_id: str
    decision_id: str
    session_id: str
    asset_id: str
    object_identity: str
    semantic_target: SemanticTarget
    scope: str
    user_semantic_intent: str
    behavior_summary: str
    behavior_window_id: str
    hard_constraints: list[str] = Field(default_factory=list)
    params: SemanticDivergenceParams = Field(default_factory=SemanticDivergenceParams)

    @model_validator(mode="before")
    @classmethod
    def accept_flat_params(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "params" in value:
            return value
        flattened = {
            name: value[name]
            for name in ("temperature", "strictness", "per_group_count", "candidate_count", "inherited_keywords")
            if name in value
        }
        if flattened:
            value = {**value, "params": flattened}
        return value

    @property
    def temperature(self) -> float:
        return self.params.temperature

    @property
    def strictness(self) -> float:
        return self.params.strictness

    @property
    def candidate_count(self) -> int:
        return self.params.candidate_count

    @property
    def inherited_keywords(self) -> list[str]:
        return self.params.inherited_keywords


class KnowledgeRoute(BaseModel):
    mode: Literal["model_only", "knowledge_augmented"] = "model_only"
    use_wikidata: bool = False
    use_getty_aat: bool = False
    use_asknature: bool = False
    reasons: list[str] = Field(default_factory=list)
    source_statuses: dict[str, str] = Field(default_factory=dict)


class KnowledgeEvidence(BaseModel):
    route: KnowledgeRoute = Field(default_factory=KnowledgeRoute)
    wikidata: list[dict[str, Any]] = Field(default_factory=list)
    getty_aat: list[dict[str, Any]] = Field(default_factory=list)
    asknature: list[dict[str, Any]] = Field(default_factory=list)
    partial_sources: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class SemanticTargetRef(BaseModel):
    asset_id: str
    type: Literal["whole", "part", "material_region"]
    id: str | None = None


class SemanticAttributeDelta(BaseModel):
    attribute: str
    change: str


class SemanticScores(BaseModel):
    identity: float = Field(ge=0.0, le=1.0)
    scope: float = Field(ge=0.0, le=1.0)
    relevance: float = Field(ge=0.0, le=1.0)
    specificity: float = Field(ge=0.0, le=1.0)
    novelty: float = Field(ge=0.0, le=1.0)


class SemanticCandidateProvenance(BaseModel):
    generator: str
    mode: str
    wikidata: list[dict[str, Any]] = Field(default_factory=list)
    getty_aat: list[dict[str, Any]] = Field(default_factory=list)
    asknature: list[dict[str, Any]] = Field(default_factory=list)


class SemanticCandidate(BaseModel):
    candidate_id: str
    display_label_zh: str
    label_en: str
    group: Literal["shape", "connection", "surface", "semantic_transfer"]
    target_ref: SemanticTargetRef
    operation: str
    semantic_anchor: str
    prompt_phrase: str
    attribute_delta: SemanticAttributeDelta
    scores: SemanticScores
    provenance: SemanticCandidateProvenance


class SemanticDivergenceResponse(BaseModel):
    schema_version: str = SEMANTIC_DIVERGENCE_SCHEMA_VERSION
    divergence_id: str
    run_id: str
    decision_id: str
    request_key: str
    status: Literal["completed", "failed"] = "completed"
    generator_model: str
    fallback_used: bool = False
    fallback_reason: str | None = None
    knowledge_route: KnowledgeRoute = Field(default_factory=KnowledgeRoute)
    validation_counts: dict[str, int] = Field(default_factory=dict)
    latency_ms: int = Field(default=0, ge=0)
    prompt_version: str = "semantic-divergence-v1"
    candidates: list[SemanticCandidate] = Field(default_factory=list)


__all__ = [
    "SEMANTIC_DIVERGENCE_SCHEMA_VERSION",
    "SemanticDivergenceParams",
    "SemanticTarget",
    "SemanticDivergenceRequest",
    "KnowledgeRoute",
    "KnowledgeEvidence",
    "SemanticTargetRef",
    "SemanticAttributeDelta",
    "SemanticScores",
    "SemanticCandidateProvenance",
    "SemanticCandidate",
    "SemanticDivergenceResponse",
]
