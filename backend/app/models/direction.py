from typing import Any
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from app.models.semantic import SemanticTarget

class AnalogyDirection(BaseModel):
    direction_id: str
    label: str
    dimension: Literal["Aesthetic", "Functional", "Structural", "Cross-domain"]
    divergence_mode: Literal["local", "whole_object", "cross_domain"] = "cross_domain"
    source_domain: str
    target_domain: str
    relation: str
    transfer_rationale: str
    constraints: list[str] = Field(default_factory=list)
    score: float | None = Field(default=None, ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TargetRef(BaseModel):
    """Explicit pointer to the object/part/surface a contextual fragment changes."""

    asset_id: str | None = None
    type: Literal["whole", "part", "surface_mask"]
    id: str | None = None
    label_zh: str | None = None
    label_en: str | None = None


class ProvenancePath(BaseModel):
    """Wikidata source -> first-hop neighbor -> Getty AAT / AskNature second-hop."""

    source: dict[str, Any] = Field(default_factory=dict)
    first_hop: dict[str, Any] | None = None
    second_hop: dict[str, Any] | None = None


class HardGates(BaseModel):
    """Boolean hard gates; every gate must pass before a fragment is shown."""

    entity_resolved: bool = False
    first_hop_verified: bool = False
    second_hop_verified: bool = False
    target_exists: bool = False
    scope_match: bool = False
    operation_compatible: bool = False
    locks_preserved: bool = False
    physically_expressible: bool = False
    phrase_grounded: bool = False
    passed: bool = False


class ContextualFragment(BaseModel):
    """Incremental spec: a human-selectable phrase bound to the current 3D target."""

    fragment_id: str
    display_label_zh: str
    full_phrase_zh: str
    label_en: str | None = None
    group: dict[str, str] = Field(default_factory=dict)
    legacy_dimension: str = "Structural"
    scope: str = "selected_part"
    target_ref: TargetRef = Field(default_factory=TargetRef)
    operation: str = "deform"
    attribute_delta: dict[str, str] = Field(default_factory=dict)
    provenance_path: ProvenancePath = Field(default_factory=ProvenancePath)
    hard_gates: HardGates = Field(default_factory=HardGates)
    constraints: list[str] = Field(default_factory=list)
    source_direction_id: str | None = None


class CrossDomainDivergenceRequest(BaseModel):
    session_id: str
    asset_id: str
    intent_draft_id: str | None = None
    interpretation_id: str | None = None
    source_summary: str | None = None
    constraints: list[str] = Field(default_factory=list)
    dimensions: list[Literal["Aesthetic", "Functional", "Structural"]] = Field(default_factory=list)
    candidate_count: int = Field(default=6, ge=1, le=12)
    semantic_target: SemanticTarget | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def accept_spec_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        next_data = dict(data)
        if next_data.get("candidate_count") is None and next_data.get("direction_count") is not None:
            next_data["candidate_count"] = next_data.get("direction_count")
        if not next_data.get("constraints") and next_data.get("preserved_constraints"):
            next_data["constraints"] = next_data.get("preserved_constraints")
        metadata = dict(next_data.get("metadata") or {})
        for key in ("request_id", "scope", "context_snapshot_id", "minimum_semantic_distance"):
            if key in next_data and key not in metadata:
                metadata[key] = next_data[key]
        if next_data.get("semantic_target") is None and metadata.get("semantic_target"):
            next_data["semantic_target"] = metadata.get("semantic_target")
        if next_data.get("interpretation_id") is None and metadata.get("interpretation_id"):
            next_data["interpretation_id"] = metadata.get("interpretation_id")
        if next_data.get("interpretation_id") and "interpretation_id" not in metadata:
            metadata["interpretation_id"] = next_data["interpretation_id"]
        next_data["metadata"] = metadata
        return next_data

    @field_validator("dimensions", mode="before")
    @classmethod
    def normalize_dimensions(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        labels = {
            "aesthetic": "Aesthetic",
            "functional": "Functional",
            "structural": "Structural",
        }
        return [labels.get(str(item).strip().lower(), item) for item in value]


class CrossDomainDivergenceResponse(BaseModel):
    session_id: str
    asset_id: str
    intent_draft_id: str | None = None
    source_summary: str
    directions: list[AnalogyDirection] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DirectionUpdateRequest(BaseModel):
    status: Literal["suggested", "selected", "dismissed", "pinned"] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PromptComposeRequest(BaseModel):
    session_id: str
    asset_id: str | None = None
    base_prompt: str = ""
    selected_prompt_tokens: list[dict[str, Any]] = Field(default_factory=list)
    direction_ids: list[str] = Field(default_factory=list)
    intent_draft_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PromptComposeResponse(BaseModel):
    session_id: str
    asset_id: str | None = None
    final_prompt: str
    analogy_prompt_package: dict[str, Any]
    event_id: str
    memory_id: str


class ViewportSegmentationRequest(BaseModel):
    session_id: str
    asset_id: str | None = None
    part_id: str | None = None
    label: str | None = None
    image_data_url: str
    point: dict[str, float]
    viewport: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ViewportSegmentationResponse(BaseModel):
    session_id: str
    asset_id: str | None = None
    part_id: str | None = None
    status: str
    adapter: str = "viewport_sam"
    mask_url: str | None = None
    overlay_url: str | None = None
    artifact_id: str | None = None
    worker_job_id: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "AnalogyDirection",
    "TargetRef",
    "ProvenancePath",
    "HardGates",
    "ContextualFragment",
    "CrossDomainDivergenceRequest",
    "CrossDomainDivergenceResponse",
    "DirectionUpdateRequest",
    "PromptComposeRequest",
    "PromptComposeResponse",
    "ViewportSegmentationRequest",
    "ViewportSegmentationResponse",
]
