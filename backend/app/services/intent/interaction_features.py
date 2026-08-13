"""Interaction feature extraction (refactor plan P2).

Pure extraction of raw interaction payloads into the feature dict consumed by
interpretation, supervision and planner assembly.
"""

from __future__ import annotations

from collections.abc import Callable
from math import sqrt

from app.models import UserEvent


def unique_ref_count(raw_refs: list[object], structured_refs: list[object]) -> int:
    keys: set[str] = set()
    for item in raw_refs:
        if isinstance(item, str) and item:
            keys.add(item)
    for item in structured_refs:
        if isinstance(item, dict):
            value = item.get("url") or item.get("artifact_id")
            if isinstance(value, str) and value:
                keys.add(value)
        elif isinstance(item, str) and item:
            keys.add(item)
    return len(keys)


def unique_image_ref_count(image_refs: list[object], reference_images: list[object]) -> int:
    return unique_ref_count(image_refs, reference_images)


def extract_interaction_features(
    event: UserEvent,
    *,
    store: object,
    socket_score: Callable[[object, object], float | None],
    axis_alignment: Callable[[tuple[float, float, float]], dict[str, object]],
) -> dict[str, object]:
        payload = event.payload
        selection = payload.get("selection") or {}
        signals = payload.get("signals") or {}
        semantic_signals = signals.get("semantic") if isinstance(signals, dict) else {}
        if not isinstance(semantic_signals, dict):
            semantic_signals = {}
        drag = payload.get("drag") or payload.get("intent", {}).get("drag") or {}
        part_id = payload.get("part_id") or selection.get("part_id") or semantic_signals.get("part_id")
        asset_id = payload.get("active_asset_id") or payload.get("asset_id") or selection.get("asset_id")
        behavior_atoms = payload.get("behavior_atoms")
        if not isinstance(behavior_atoms, list):
            behavior_atoms = []
        atom_tools = [
            str(item.get("tool") or "")
            for item in behavior_atoms
            if isinstance(item, dict)
        ]
        # Composed multi-intent: drag/brush/smooth/hover/annotation atoms each
        # count as one behavior; merge them into the live signal counters so
        # the supervisors can judge the perception content even when the event
        # itself carries no live_signals.
        live_signals = payload.get("live_signals")
        if not isinstance(live_signals, dict):
            live_signals = {}
        if behavior_atoms:
            merged_live = dict(live_signals)
            atom_brush = sum(1 for tool in atom_tools if tool in {"brush", "draw", "grab", "deform"})
            atom_annotation = sum(1 for tool in atom_tools if tool in {"annotation", "sketch", "add"})
            atom_hover = sum(1 for tool in atom_tools if tool == "hover")
            merged_live["brush_count"] = int(merged_live.get("brush_count") or 0) + atom_brush
            merged_live["annotation_count"] = int(merged_live.get("annotation_count") or 0) + atom_annotation
            merged_live["hover_count"] = int(merged_live.get("hover_count") or 0) + atom_hover
            live_signals = merged_live
            if not part_id:
                for item in behavior_atoms:
                    target = item.get("target") if isinstance(item, dict) else None
                    if isinstance(target, dict) and target.get("part_id"):
                        part_id = str(target["part_id"])
                        break
        atom_part_label = None
        if behavior_atoms:
            for item in behavior_atoms:
                target = item.get("target") if isinstance(item, dict) else None
                if isinstance(target, dict) and (target.get("label") or target.get("part_label")):
                    atom_part_label = str(target.get("label") or target.get("part_label") or "")
                    break
        image_refs = payload.get("image_refs")
        if not isinstance(image_refs, list):
            image_refs = []
        reference_images = payload.get("reference_images")
        if not isinstance(reference_images, list):
            reference_images = []
        image_ref_count = unique_image_ref_count(image_refs, reference_images)
        model_refs = payload.get("model_refs")
        if not isinstance(model_refs, list):
            model_refs = []
        reference_models = payload.get("reference_models")
        if not isinstance(reference_models, list):
            reference_models = []
        model_ref_count = unique_ref_count(model_refs, reference_models)

        features: dict[str, object] = {
            "event_type": event.type,
            "asset_id": asset_id,
            "part_id": part_id,
            "part_label": payload.get("selected_part_label")
            or payload.get("part_label")
            or semantic_signals.get("part_label")
            or atom_part_label,
            "selection_type": selection.get("type"),
            "intent_text": payload.get("intent_text")
            or payload.get("text")
            or payload.get("intent", {}).get("text"),
            "mask_url": selection.get("mask_url") or payload.get("mask_url"),
            "bbox": selection.get("bbox") or payload.get("bbox"),
            "candidate_id": payload.get("candidate_id"),
            "commit_policy": payload.get("commit_policy"),
            "make_active_asset": payload.get("make_active_asset"),
            "creative_stage": payload.get("creative_stage")
            or payload.get("stage")
            or (payload.get("generation") or {}).get("metadata", {}).get("stage"),
            "fidelity": payload.get("fidelity")
            or (payload.get("generation") or {}).get("metadata", {}).get("fidelity"),
            "divergence_axes": payload.get("divergence_axes")
            or (payload.get("generation") or {}).get("metadata", {}).get("divergence_axes"),
            "payload_suggested_action": payload.get("suggested_action"),
            "candidate_scores": payload.get("scores") or {},
            "pipeline_evidence": payload.get("pipeline_evidence") or {},
            "live_signals": live_signals,
            "behavior_atoms": behavior_atoms,
            "behavior_atom_tools": atom_tools,
            "behavior_atom_count": len(behavior_atoms),
            "image_refs": image_refs,
            "reference_images": reference_images,
            "image_ref_count": image_ref_count,
            "model_refs": model_refs,
            "reference_models": reference_models,
            "model_ref_count": model_ref_count,
            "annotation_artifact_id": payload.get("annotation_artifact_id") or payload.get("artifact_id"),
            "annotation_stroke_url": payload.get("stroke_url"),
            "annotation_shape": payload.get("annotation_shape"),
            "annotation_projection": payload.get("projection"),
            "brush_mask_artifact_id": payload.get("brush_mask_artifact_id")
            or selection.get("brush_mask_artifact_id")
            or (
                payload.get("artifact_id")
                if event.type.startswith("brush") or selection.get("type") in {"brush", "mesh_region"}
                else None
            ),
            "brush_mask_url": payload.get("brush_mask_url")
            or selection.get("brush_mask_url")
            or selection.get("mask_url")
            or payload.get("mask_url"),
            "brush_coverage": payload.get("brush_coverage")
            or payload.get("coverage")
            or selection.get("coverage")
            or (selection.get("metrics") or {}).get("coverage"),
            "brush_projection": payload.get("brush_projection")
            or selection.get("projection")
            or payload.get("projection"),
            "smooth_operation_artifact_id": payload.get("smooth_operation_artifact_id")
            or (
                payload.get("artifact_id")
                if event.type.startswith("smooth")
                else None
            ),
            "smooth_operation_url": payload.get("smooth_operation_url") or payload.get("operation_url"),
            "smooth_region": payload.get("smooth_region")
            or payload.get("region")
            or selection.get("region"),
            "smooth_strength": payload.get("smooth_strength")
            or payload.get("strength")
            or (payload.get("parameters") or {}).get("strength"),
            "smooth_brush_radius": payload.get("smooth_brush_radius")
            or (payload.get("brush") or {}).get("radius"),
            "smooth_preserve_boundary": payload.get("smooth_preserve_boundary")
            or payload.get("preserve_boundary")
            or (payload.get("parameters") or {}).get("preserve_boundary"),
            "smooth_preview_mesh_url": payload.get("smooth_preview_mesh_url")
            or payload.get("preview_mesh_url")
            or (payload.get("preview") or {}).get("preview_mesh_url"),
            "smooth_geometry_job_id": payload.get("smooth_geometry_job_id")
            or payload.get("geometry_job_id")
            or (payload.get("preview") or {}).get("geometry_job_id"),
            "primitive_addition_artifact_id": payload.get("primitive_addition_artifact_id")
            or (
                payload.get("artifact_id")
                if event.type.startswith("primitive")
                else None
            ),
            "primitive_addition_url": payload.get("primitive_addition_url")
            or payload.get("primitive_url"),
            "primitive": payload.get("primitive"),
            "primitive_transform": payload.get("primitive_transform")
            or payload.get("transform"),
            "primitive_relation": payload.get("primitive_relation")
            or payload.get("relation"),
            "primitive_constraints": payload.get("primitive_constraints")
            or payload.get("constraints"),
            "drag_operation_artifact_id": payload.get("drag_operation_artifact_id")
            or (
                payload.get("artifact_id")
                if event.type.startswith("drag")
                else None
            ),
            "drag_operation_url": payload.get("drag_operation_url"),
            "drag_preview_mesh_url": payload.get("drag_preview_mesh_url")
            or payload.get("preview_mesh_url")
            or (payload.get("preview") or {}).get("preview_mesh_url"),
            "drag_geometry_job_id": payload.get("drag_geometry_job_id")
            or payload.get("geometry_job_id")
            or (payload.get("preview") or {}).get("geometry_job_id"),
            "focus_observation_artifact_id": payload.get("focus_observation_artifact_id")
            or (
                payload.get("artifact_id")
                if event.type in {"hover_focus", "semantic_hover_ended", "camera_observation_ended"}
                else None
            ),
            "focus_observation_url": payload.get("focus_observation_url"),
            "focus_source": payload.get("focus_source")
            or (payload.get("observation") or {}).get("focus_source"),
            "dwell_ms": payload.get("dwell_ms")
            or (payload.get("metrics") or {}).get("dwell_ms"),
        }
        socket_score = socket_score(features["candidate_scores"], features["pipeline_evidence"])
        if socket_score is not None:
            features["socket_compatibility_score"] = socket_score

        recent_events = store.recent_events(event.session_id, limit=30)
        features["same_part_recent_edits"] = sum(
            1
            for recent in recent_events
            if (
                recent.payload.get("part_id")
                or (recent.payload.get("selection") or {}).get("part_id")
            )
            == part_id
        )
        features["recent_undo_count"] = sum(1 for recent in recent_events if recent.type == "undo")
        features["recent_event_count"] = len(recent_events)
        features["same_event_type_recent_count"] = sum(
            1 for recent in recent_events if recent.type == event.type
        )
        features["recent_accept_count"] = sum(
            1 for recent in recent_events if recent.type == "candidate_accepted"
        )
        features["recent_reject_count"] = sum(
            1 for recent in recent_events if recent.type == "candidate_rejected"
        )

        if drag and drag.get("start") and drag.get("end"):
            start = tuple(float(x) for x in drag["start"])
            end = tuple(float(x) for x in drag["end"])
            vector = tuple(round(end[i] - start[i], 4) for i in range(3))
            length = sqrt(sum(item * item for item in vector))
            features.update(
                {
                    "drag_vector": vector,
                    "drag_length": round(length, 4),
                    "influence_radius": drag.get("influence_radius", 0.25),
                    "space": drag.get("space", "world"),
                    "direction_relation": "outward_from_part_center" if length > 0.05 else "small_adjustment",
                    "axis_alignment": axis_alignment(vector),
                }
            )

        if selection.get("bbox"):
            bbox = selection["bbox"]
            if len(bbox) == 4:
                features["region"] = {
                    "bbox": bbox,
                    "area": max(0, float(bbox[2] - bbox[0])) * max(0, float(bbox[3] - bbox[1])),
                }
        asset = store.get_asset(str(asset_id)) if asset_id else None
        features["signals"] = {
            "geometric": {
                "drag_vector": features.get("drag_vector"),
                "drag_length": features.get("drag_length"),
                "influence_radius": features.get("influence_radius"),
                "axis_alignment": features.get("axis_alignment"),
                "direction_relation": features.get("direction_relation"),
                "drag_operation_artifact_id": features.get("drag_operation_artifact_id"),
                "drag_operation_url": features.get("drag_operation_url"),
                "drag_preview_mesh_url": features.get("drag_preview_mesh_url"),
                "drag_geometry_job_id": features.get("drag_geometry_job_id"),
                "focus_observation_artifact_id": features.get("focus_observation_artifact_id"),
                "focus_source": features.get("focus_source"),
                "dwell_ms": features.get("dwell_ms"),
                "bbox": features.get("bbox"),
                "region": features.get("region"),
                "brush_coverage": features.get("brush_coverage"),
                "brush_projection": features.get("brush_projection"),
                "smooth_region": features.get("smooth_region"),
                "smooth_strength": features.get("smooth_strength"),
                "smooth_brush_radius": features.get("smooth_brush_radius"),
                "smooth_preserve_boundary": features.get("smooth_preserve_boundary"),
                "primitive_transform": features.get("primitive_transform"),
                "primitive_relation": features.get("primitive_relation"),
            },
            "semantic": {
                "part_id": part_id,
                "part_label": selection.get("label") or payload.get("part_label"),
                "object_type": asset.object_type if asset else payload.get("object_type"),
                "intent_text": features.get("intent_text"),
                "creativeflow_relation": payload.get("relation")
                or payload.get("creativeflow_relation"),
                "creative_stage": features.get("creative_stage"),
                "fidelity": features.get("fidelity"),
                "divergence_axes": features.get("divergence_axes"),
                "image_ref_count": features.get("image_ref_count"),
                "model_ref_count": features.get("model_ref_count"),
                "annotation_shape": features.get("annotation_shape"),
                "brush_mask_artifact_id": features.get("brush_mask_artifact_id"),
                "smooth_operation_artifact_id": features.get("smooth_operation_artifact_id"),
                "primitive_addition_artifact_id": features.get("primitive_addition_artifact_id"),
                "primitive": features.get("primitive"),
                "primitive_constraints": features.get("primitive_constraints"),
                "drag_operation_artifact_id": features.get("drag_operation_artifact_id"),
                "focus_observation_artifact_id": features.get("focus_observation_artifact_id"),
            },
            "temporal": {
                "recent_event_count": features.get("recent_event_count"),
                "same_event_type_recent_count": features.get("same_event_type_recent_count"),
                "same_part_recent_edits": features.get("same_part_recent_edits"),
                "recent_undo_count": features.get("recent_undo_count"),
            },
            "visual_context": {
                "viewport": payload.get("viewport"),
                "visible_region": payload.get("visible_region"),
                "mask_url": features.get("mask_url"),
                "candidate_thumbnail_url": payload.get("candidate_thumbnail_url"),
                "mesh_url": payload.get("mesh_url"),
                "obj_url": payload.get("obj_url"),
                "image_refs": image_refs,
                "reference_images": reference_images,
                "image_ref_count": features.get("image_ref_count"),
                "model_refs": model_refs,
                "reference_models": reference_models,
                "model_ref_count": features.get("model_ref_count"),
                "annotation_artifact_id": features.get("annotation_artifact_id"),
                "annotation_stroke_url": features.get("annotation_stroke_url"),
                "annotation_projection": features.get("annotation_projection"),
                "brush_mask_artifact_id": features.get("brush_mask_artifact_id"),
                "brush_mask_url": features.get("brush_mask_url"),
                "brush_coverage": features.get("brush_coverage"),
                "smooth_operation_artifact_id": features.get("smooth_operation_artifact_id"),
                "smooth_operation_url": features.get("smooth_operation_url"),
                "smooth_preview_mesh_url": features.get("smooth_preview_mesh_url"),
                "smooth_geometry_job_id": features.get("smooth_geometry_job_id"),
                "primitive_addition_artifact_id": features.get("primitive_addition_artifact_id"),
                "primitive_addition_url": features.get("primitive_addition_url"),
                "drag_operation_artifact_id": features.get("drag_operation_artifact_id"),
                "drag_operation_url": features.get("drag_operation_url"),
                "drag_preview_mesh_url": features.get("drag_preview_mesh_url"),
                "drag_geometry_job_id": features.get("drag_geometry_job_id"),
                "focus_observation_artifact_id": features.get("focus_observation_artifact_id"),
                "focus_observation_url": features.get("focus_observation_url"),
            },
            "interaction": {
                "event_type": event.type,
                "selection_type": features.get("selection_type"),
                "is_hover": event.type.endswith("hover"),
                "is_select": event.type in {"part_select", "object_select"},
                "is_brush": event.type.startswith("brush"),
                "is_drag": event.type.startswith("drag"),
                "is_compare": event.type == "candidate_compared",
                "is_accept": event.type == "candidate_accepted",
                "is_reject": event.type == "candidate_rejected",
            },
            "history": {
                "recent_accept_count": features.get("recent_accept_count"),
                "recent_reject_count": features.get("recent_reject_count"),
                "same_part_recent_edits": features.get("same_part_recent_edits"),
                "candidate_id": features.get("candidate_id"),
                "commit_policy": features.get("commit_policy"),
                "make_active_asset": features.get("make_active_asset"),
                "creative_stage": features.get("creative_stage"),
                "fidelity": features.get("fidelity"),
                "socket_compatibility_score": features.get("socket_compatibility_score"),
            },
        }
        return features
