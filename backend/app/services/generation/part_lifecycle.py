"""Part lifecycle state machine for FlowStudio Phase B.

Layers (never pretend a lower layer is a stable 3D part):

- tentative_raycast: frontend raycast hit (may not be persisted)
- obj_group_fallback: OBJ o/g groups used as editable proxies
- viewport_2d_mask: 2D SAM evidence attached; not mesh-stable
- segmented_3d: real SAMPart3D / PartField / SAM3D parts
"""

from __future__ import annotations

from typing import Any, Literal

from app.models import PartRecord

PartLifecycle = Literal[
    "tentative_raycast",
    "obj_group_fallback",
    "viewport_2d_mask",
    "segmented_3d",
]

PART_LIFECYCLES: tuple[PartLifecycle, ...] = (
    "tentative_raycast",
    "obj_group_fallback",
    "viewport_2d_mask",
    "segmented_3d",
)

_LIFECYCLE_RANK = {
    "tentative_raycast": 0,
    "obj_group_fallback": 1,
    "viewport_2d_mask": 2,
    "segmented_3d": 3,
}


def normalize_lifecycle(value: object, default: PartLifecycle = "tentative_raycast") -> PartLifecycle:
    text = str(value or "").strip().lower()
    aliases = {
        "tentative": "tentative_raycast",
        "raycast": "tentative_raycast",
        "obj_group": "obj_group_fallback",
        "obj-group": "obj_group_fallback",
        "fallback": "obj_group_fallback",
        "viewport_sam": "viewport_2d_mask",
        "viewport_2d": "viewport_2d_mask",
        "sam_2d": "viewport_2d_mask",
        "sam3d": "segmented_3d",
        "sampart3d": "segmented_3d",
        "partfield": "segmented_3d",
        "segmented": "segmented_3d",
        "real_3d": "segmented_3d",
    }
    if text in PART_LIFECYCLES:
        return text  # type: ignore[return-value]
    mapped = aliases.get(text)
    if mapped in PART_LIFECYCLES:
        return mapped  # type: ignore[return-value]
    return default


def read_lifecycle(part: PartRecord | dict[str, Any] | None) -> PartLifecycle:
    if part is None:
        return "tentative_raycast"
    if isinstance(part, PartRecord):
        if part.lifecycle:
            return normalize_lifecycle(part.lifecycle)
        meta = part.metadata or {}
        source = meta.get("lifecycle") or meta.get("source") or part.type
        if str(source).startswith("obj_group") or part.type == "obj_group":
            return "obj_group_fallback"
        if str(source) in {"sam3d", "sampart3d", "partfield"} or "segmented_mesh" in meta:
            return "segmented_3d"
        if meta.get("viewport_mask_artifact_id") or meta.get("has_viewport_2d_mask"):
            return "viewport_2d_mask"
        return normalize_lifecycle(source)
    meta = part.get("metadata") if isinstance(part.get("metadata"), dict) else {}
    return normalize_lifecycle(
        part.get("lifecycle") or meta.get("lifecycle") or meta.get("source") or part.get("type")
    )


def apply_lifecycle(part: PartRecord, lifecycle: PartLifecycle) -> PartRecord:
    lifecycle = normalize_lifecycle(lifecycle)
    part.lifecycle = lifecycle
    metadata = dict(part.metadata or {})
    metadata["lifecycle"] = lifecycle
    part.metadata = metadata
    return part


def annotate_obj_group_part(part: PartRecord) -> PartRecord:
    return apply_lifecycle(part, "obj_group_fallback")


def annotate_segmented_3d_part(part: PartRecord) -> PartRecord:
    return apply_lifecycle(part, "segmented_3d")


def attach_viewport_2d_evidence(
    part: PartRecord,
    *,
    artifact_id: str,
    mask_url: str | None,
    overlay_url: str | None = None,
    mask_coverage: float | None = None,
    note: str | None = None,
) -> PartRecord:
    """Attach 2D SAM evidence without promoting the part to segmented_3d."""
    previous = read_lifecycle(part)
    evidence = dict(part.metadata.get("evidence") or {})
    evidence["viewport_mask_artifact_id"] = artifact_id
    evidence["viewport_mask_url"] = mask_url
    if overlay_url:
        evidence["viewport_overlay_url"] = overlay_url
    if mask_coverage is not None:
        evidence["viewport_mask_coverage"] = mask_coverage
    evidence["viewport_mask_note"] = note or (
        "2D viewport mask only; not a stable 3D part until projected to mesh."
    )

    metadata = dict(part.metadata or {})
    metadata["evidence"] = evidence
    metadata["has_viewport_2d_mask"] = True
    metadata["viewport_mask_artifact_id"] = artifact_id
    metadata["mesh_source_lifecycle"] = previous
    part.metadata = metadata

    if previous == "segmented_3d":
        # Keep true 3D identity; only enrich evidence.
        return apply_lifecycle(part, "segmented_3d")

    # Promote observation layer to viewport_2d_mask, never to segmented_3d.
    return apply_lifecycle(part, "viewport_2d_mask")


def lifecycle_summary(parts: list[PartRecord]) -> dict[str, Any]:
    counts: dict[str, int] = {key: 0 for key in PART_LIFECYCLES}
    for part in parts:
        counts[read_lifecycle(part)] = counts.get(read_lifecycle(part), 0) + 1
    return {
        "counts": counts,
        "has_segmented_3d": counts.get("segmented_3d", 0) > 0,
        "has_obj_group_fallback": counts.get("obj_group_fallback", 0) > 0,
        "has_viewport_2d_mask": counts.get("viewport_2d_mask", 0) > 0,
    }


def find_part(asset_parts: list[PartRecord], part_id: str | None) -> PartRecord | None:
    if not part_id:
        return None
    for part in asset_parts:
        if part.part_id == part_id:
            return part
        source_part_id = str((part.metadata or {}).get("source_part_id") or "")
        if source_part_id and source_part_id == part_id:
            return part
        if part.label == part_id:
            return part
    return None


def can_upgrade(from_lifecycle: PartLifecycle, to_lifecycle: PartLifecycle) -> bool:
    return _LIFECYCLE_RANK[normalize_lifecycle(to_lifecycle)] >= _LIFECYCLE_RANK[
        normalize_lifecycle(from_lifecycle)
    ]
