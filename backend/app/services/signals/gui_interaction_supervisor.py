"""② GUI interaction supervisor: all spatial manipulation + viewport.

Drag / Brush / Smooth / Add / click selection / viewport zoom-rotate all live
here. Outputs a target vote: which level (whole/silhouette/part/material) and
which part/region the GUI interaction points at, with spatial evidence.
"""

from __future__ import annotations

from typing import Any

from app.models import SupervisorVote
from app.services.shared.labels import clean_part_label


def _part_label(features: dict[str, Any]) -> str | None:
    signals = features.get("signals") if isinstance(features.get("signals"), dict) else {}
    semantic = signals.get("semantic") if isinstance(signals.get("semantic"), dict) else {}
    label = str(semantic.get("part_label") or "").strip()
    return label or None


def supervise_gui_interaction(features: dict[str, Any]) -> SupervisorVote:
    event_type = str(features.get("event_type") or "")
    part_id = features.get("part_id") or (features.get("signals") or {}).get("semantic", {}).get("part_id")
    part_label = _part_label(features)
    live = features.get("live_signals") if isinstance(features.get("live_signals"), dict) else {}
    brush = int(live.get("brush_count") or 0)
    hover = int(live.get("hover_count") or 0)
    annotation = int(live.get("annotation_count") or 0)
    orbit = int(live.get("viewport_orbit_count") or 0)
    zoom = int(live.get("viewport_zoom_count") or 0)
    mask_coverage = float(live.get("mask_coverage") or 0)
    atom_tools = features.get("behavior_atom_tools")
    if not isinstance(atom_tools, list):
        atom_tools = []
    geometry_edit_atoms = [tool for tool in atom_tools if tool in {"brush", "drag", "smooth", "draw", "grab", "move", "deform"}]
    edit_atom_count = len(geometry_edit_atoms)

    level_scores = {"whole": 0.05, "silhouette": 0.1, "part": 0.1, "material_region": 0.05}
    part_candidates: list[dict[str, Any]] = []
    material_candidates: list[dict[str, Any]] = []
    silhouette_evidence: list[str] = []
    evidence: list[str] = []

    tool = str(features.get("tool") or "")
    if not tool:
        payload_signals = features.get("signals") if isinstance(features.get("signals"), dict) else {}
        interaction = payload_signals.get("interaction") if isinstance(payload_signals.get("interaction"), dict) else {}
        tool = str(interaction.get("tool") or "")

    part_actions = {"brush", "drag", "smooth", "draw", "grab", "move", "deform"}
    editing_part = bool(part_id) and (
        tool in part_actions
        or brush > 0
        or hover > 0
        or edit_atom_count > 0
        or event_type in {"part_brush_end", "drag_end", "smooth_end", "semantic_hover_ended"}
    )
    if editing_part:
        level_scores["part"] = min(1.0, 0.45 + brush * 0.12 + hover * 0.08 + mask_coverage * 0.1)
        evidence.append(f"gui_part_tool:{tool or 'interaction'}")
        if mask_coverage > 0:
            evidence.append(f"brush_mask:{mask_coverage:.2f}")
            if not part_label:
                level_scores["material_region"] = min(1.0, 0.3 + mask_coverage * 0.2)
                material_candidates.append(
                    {"label_zh": None, "role": "unnamed_surface", "score": 0.3 + mask_coverage * 0.2,
                     "evidence": [f"brush_mask:{mask_coverage:.2f}"]}
                )
        part_candidates.append(
            {
                "part_id": str(part_id) if part_id else None,
                "label_zh": clean_part_label(part_label),
                "label_en": part_label or (str(part_id) if part_id else None),
                "role": "gui_target",
                "score": level_scores["part"],
                "evidence": [f"gui:{tool or event_type}", f"hover:{hover}", f"brush:{brush}"],
            }
        )
    elif tool == "add" or event_type == "primitive_added":
        level_scores["whole"] = min(1.0, 0.5 + brush * 0.05)
        evidence.append("gui_add_primitive")
    else:
        if edit_atom_count > 0 and not part_id:
            # Composed geometry edits without a registered part: the user is
            # reshaping the whole silhouette / surface region.
            level_scores["silhouette"] = min(1.0, level_scores["silhouette"] + 0.35 + 0.08 * edit_atom_count)
            level_scores["whole"] = min(1.0, level_scores["whole"] + 0.15)
            silhouette_evidence.append(f"geometry_edit_atoms:{edit_atom_count}")
            evidence.append(f"gui_geometry_edit:{edit_atom_count}")
        if orbit >= 2 or zoom >= 2:
            level_scores["whole"] = min(1.0, 0.35 + orbit * 0.06 + zoom * 0.05)
            level_scores["silhouette"] = min(1.0, 0.2 + orbit * 0.05)
            silhouette_evidence.append(f"orbit:{orbit}")
            evidence.append(f"viewport_orbit:{orbit}")
        if annotation > 0:
            level_scores["silhouette"] = min(1.0, 0.3 + annotation * 0.1)
            silhouette_evidence.append(f"annotation:{annotation}")
            evidence.append("gui_annotation_outline")

    return SupervisorVote(
        supervisor="gui_interaction",
        level_scores={key: round(value, 3) for key, value in level_scores.items()},
        part_candidates=part_candidates,
        material_candidates=material_candidates,
        silhouette_evidence=silhouette_evidence,
        conflict=None,
        evidence=evidence or ["no_gui_signal"],
    )
