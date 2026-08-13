from typing import Literal
from pydantic import BaseModel, Field

class SemanticTargetSemantic(BaseModel):
    """Semantic description of the expansion target (contour/part/material)."""

    label_zh: str | None = None
    label_en: str | None = None
    semantic_role: str | None = None
    wikidata_qid: str | None = None
    part_id: str | None = None
    mask_ref: str | None = None
    surface_ref: str | None = None


class SemanticTarget(BaseModel):
    """A semantically grounded expansion target: whole / silhouette / part / material."""

    target_id: str
    level: Literal["whole", "silhouette", "part", "material_region"] = "whole"
    semantic: SemanticTargetSemantic = Field(default_factory=SemanticTargetSemantic)
    operation_hint: str | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)
    supervision_sources: dict[str, float] = Field(default_factory=dict)
    kg_ready: bool = False
    requires_clarification: bool = False


__all__ = [
    "SemanticTargetSemantic",
    "SemanticTarget",
]
