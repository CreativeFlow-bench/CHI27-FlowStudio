from datetime import UTC, datetime

from typing import Any
from typing import Literal
from pydantic import BaseModel, Field, model_validator
from app.models.base import now_utc
from app.models.base import JobStatus

class PartRecord(BaseModel):
    part_id: str
    label: str
    type: str = "semantic"
    lifecycle: Literal[
        "tentative_raycast",
        "obj_group_fallback",
        "viewport_2d_mask",
        "segmented_3d",
    ] | None = None
    bbox: list[float] | None = None
    mask_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def sync_lifecycle_metadata(self) -> "PartRecord":
        meta = dict(self.metadata or {})
        source = str(meta.get("lifecycle") or meta.get("source") or self.type or "")
        inferred = self.lifecycle
        if inferred is None:
            if source.startswith("obj_group") or self.type == "obj_group":
                inferred = "obj_group_fallback"
            elif source in {"sam3d", "sampart3d", "partfield"} or meta.get("segmented_mesh_path"):
                inferred = "segmented_3d"
            elif meta.get("has_viewport_2d_mask") or meta.get("viewport_mask_artifact_id"):
                inferred = "viewport_2d_mask"
            else:
                inferred = "tentative_raycast"
        self.lifecycle = inferred
        meta["lifecycle"] = inferred
        self.metadata = meta
        return self


class AssetRecord(BaseModel):
    asset_id: str
    session_id: str
    object_type: str
    label: str
    mesh_url: str | None = None
    obj_url: str | None = None
    thumbnail_url: str | None = None
    parts: list[PartRecord] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=now_utc)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssetCreateRequest(BaseModel):
    session_id: str
    object_type: str = "object"
    label: str | None = None
    mesh_url: str | None = None
    obj_url: str | None = None
    thumbnail_url: str | None = None
    parts: list[PartRecord] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BenchmarkAssetRecord(BaseModel):
    benchmark_id: str
    label: str
    object_type: str
    mesh_url: str | None = None
    obj_url: str | None = None
    thumbnail_url: str | None = None
    file_size_bytes: int = 0
    vertex_count: int | None = None
    face_count: int | None = None
    noun_text: str | None = None
    relation_text: str | None = None
    target_text: str | None = None
    reference_status: str | None = None
    model_available: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class BenchmarkAssetListResponse(BaseModel):
    assets: list[BenchmarkAssetRecord] = Field(default_factory=list)


class BenchmarkAssetLoadRequest(BaseModel):
    session_id: str


class AssetPartsResponse(BaseModel):
    asset_id: str
    parts: list[PartRecord]


class AssetVersionRecord(BaseModel):
    version_id: str
    asset_id: str
    parent_version_id: str | None = None
    mesh_url: str | None = None
    obj_url: str | None = None
    thumbnail_url: str | None = None
    edit_ops: list[dict[str, Any]] = Field(default_factory=list)
    source: str = "sculpt_commit"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=now_utc)


class AssetVersionCreateRequest(BaseModel):
    session_id: str
    parent_version_id: str | None = None
    edit_ops: list[dict[str, Any]] = Field(default_factory=list)
    source: str = "sculpt_commit"
    metadata: dict[str, Any] = Field(default_factory=dict)


class PartUpdateRequest(BaseModel):
    label: str | None = None
    type: str | None = None
    lifecycle: Literal[
        "tentative_raycast",
        "obj_group_fallback",
        "viewport_2d_mask",
        "segmented_3d",
    ] | None = None
    metadata: dict[str, Any] | None = None


class PartDiscoveryRequest(BaseModel):
    session_id: str
    asset_id: str
    mode: Literal["mesh", "image", "image_mask"] = "mesh"
    image_url: str | None = None
    mask_url: str | None = None
    prompt: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PartDiscoveryResponse(BaseModel):
    job_id: str | None = None
    session_id: str
    asset_id: str
    status: JobStatus
    parts: list[PartRecord] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WebReferenceAttachRequest(BaseModel):
    session_id: str
    asset_id: str | None = None
    url: str
    thumbnail: str | None = None
    title: str | None = None
    role: str = "shape_reference"


__all__ = [
    "PartRecord",
    "AssetRecord",
    "AssetCreateRequest",
    "BenchmarkAssetRecord",
    "BenchmarkAssetListResponse",
    "BenchmarkAssetLoadRequest",
    "AssetPartsResponse",
    "AssetVersionRecord",
    "AssetVersionCreateRequest",
    "PartUpdateRequest",
    "PartDiscoveryRequest",
    "PartDiscoveryResponse",
    "WebReferenceAttachRequest",
]
