from datetime import UTC, datetime

from typing import Any
from typing import Literal
from pydantic import BaseModel, Field, computed_field, model_validator
from app.models.base import now_utc
from app.models.planner import InteractionInterpretation
from app.models.base import GenerationMode, SelectionType

class Selection(BaseModel):
    type: SelectionType = SelectionType.none
    part_id: str | None = None
    label: str | None = None
    mask_url: str | None = None
    bbox: list[float] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DragSignal(BaseModel):
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    space: str = "world"
    influence_radius: float = Field(default=0.25, gt=0)


class Intent(BaseModel):
    mode: GenerationMode
    text: str | None = None
    drag: DragSignal | None = None
    constraints: list[str] = Field(default_factory=list)
    style_refs: list[str] = Field(default_factory=list)
    axes: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenerationOptions(BaseModel):
    candidate_count: int = Field(default=6, ge=1, le=24)
    diversity: float = Field(default=0.7, ge=0, le=1)
    output_format: str = "glb"
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenerationRequest(BaseModel):
    session_id: str
    asset_id: str
    selection: Selection = Field(default_factory=Selection)
    intent: Intent
    generation: GenerationOptions = Field(default_factory=GenerationOptions)


class ActionAtom(BaseModel):
    atom_id: str
    tool: Literal["hover", "brush", "annotation", "drag", "smooth", "add", "text", "image", "model"]
    target: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    order: int = 0
    created_at: datetime = Field(default_factory=now_utc)

    @computed_field
    @property
    def action_id(self) -> str:
        return self.atom_id


class ActionAtomCreateRequest(BaseModel):
    atom_id: str | None = None
    tool: Literal["hover", "brush", "annotation", "drag", "smooth", "add", "text", "image", "model"]
    target: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    order: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def accept_spec_action_id(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("atom_id") is None and data.get("action_id"):
            data = {**data, "atom_id": data.get("action_id")}
        return data


class AnnotationArtifactCreateRequest(BaseModel):
    session_id: str
    asset_id: str | None = None
    part_id: str | None = None
    text: str | None = None
    strokes: list[dict[str, Any]] = Field(default_factory=list)
    projection: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BrushMaskArtifactCreateRequest(BaseModel):
    session_id: str
    asset_id: str | None = None
    part_id: str | None = None
    label: str | None = None
    mask: dict[str, Any] = Field(default_factory=dict)
    projection: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SmoothOperationArtifactCreateRequest(BaseModel):
    session_id: str
    asset_id: str | None = None
    part_id: str | None = None
    label: str | None = None
    region: dict[str, Any] = Field(default_factory=dict)
    brush: dict[str, Any] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    preview: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PrimitiveAdditionArtifactCreateRequest(BaseModel):
    session_id: str
    asset_id: str | None = None
    part_id: str | None = None
    primitive: str
    transform: dict[str, Any] = Field(default_factory=dict)
    relation: dict[str, Any] = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)
    preview: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DragOperationArtifactCreateRequest(BaseModel):
    session_id: str
    asset_id: str | None = None
    part_id: str | None = None
    label: str | None = None
    drag: dict[str, Any] = Field(default_factory=dict)
    region: dict[str, Any] = Field(default_factory=dict)
    preview: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FocusObservationArtifactCreateRequest(BaseModel):
    session_id: str
    asset_id: str | None = None
    part_id: str | None = None
    label: str | None = None
    observation: dict[str, Any] = Field(default_factory=dict)
    viewport: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntentDraftCreateRequest(BaseModel):
    session_id: str
    asset_id: str | None = None
    title: str | None = None
    text: str | None = None
    behavior_atoms: list[ActionAtom] = Field(default_factory=list)
    image_refs: list[str] = Field(default_factory=list)
    model_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntentDraftUpdateRequest(BaseModel):
    title: str | None = None
    text: str | None = None
    behavior_atoms: list[ActionAtom] | None = None
    image_refs: list[str] | None = None
    model_refs: list[str] | None = None
    status: Literal["draft", "sent", "archived"] | None = None
    metadata: dict[str, Any] | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_spec_status(cls, data: Any) -> Any:
        if isinstance(data, dict):
            status = data.get("status")
            if status == "saved":
                data = {**data, "status": "draft"}
            elif status == "submitted":
                data = {**data, "status": "sent"}
        return data


class IntentDraft(BaseModel):
    draft_id: str
    session_id: str
    asset_id: str | None = None
    title: str
    text: str | None = None
    behavior_atoms: list[ActionAtom] = Field(default_factory=list)
    image_refs: list[str] = Field(default_factory=list)
    model_refs: list[str] = Field(default_factory=list)
    status: Literal["draft", "sent", "archived"] = "draft"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)

    @computed_field
    @property
    def intent_draft_id(self) -> str:
        return self.draft_id

    @computed_field
    @property
    def action_ids(self) -> list[str]:
        return [atom.atom_id for atom in self.behavior_atoms]


class IntentDraftListResponse(BaseModel):
    drafts: list[IntentDraft] = Field(default_factory=list)


class IntentEpisodeCreateRequest(BaseModel):
    intent_draft_id: str | None = None
    action_atom_ids: list[str] = Field(default_factory=list)
    behavior_atoms: list[ActionAtom] = Field(default_factory=list)
    text: str | None = None
    image_refs: list[str] = Field(default_factory=list)
    model_refs: list[str] = Field(default_factory=list)
    context_snapshot_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntentEpisodeResponse(BaseModel):
    episode_id: str
    session_id: str
    asset_id: str | None = None
    intent_draft_id: str | None = None
    behavior_atoms: list[ActionAtom] = Field(default_factory=list)
    text: str | None = None
    image_refs: list[str] = Field(default_factory=list)
    model_refs: list[str] = Field(default_factory=list)
    context_snapshot_id: str | None = None
    status: Literal["submitted"] = "submitted"
    planner_interpretation: InteractionInterpretation | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=now_utc)


__all__ = [
    "Selection",
    "DragSignal",
    "Intent",
    "GenerationOptions",
    "GenerationRequest",
    "ActionAtom",
    "ActionAtomCreateRequest",
    "AnnotationArtifactCreateRequest",
    "BrushMaskArtifactCreateRequest",
    "SmoothOperationArtifactCreateRequest",
    "PrimitiveAdditionArtifactCreateRequest",
    "DragOperationArtifactCreateRequest",
    "FocusObservationArtifactCreateRequest",
    "IntentDraftCreateRequest",
    "IntentDraftUpdateRequest",
    "IntentDraft",
    "IntentDraftListResponse",
    "IntentEpisodeCreateRequest",
    "IntentEpisodeResponse",
]
