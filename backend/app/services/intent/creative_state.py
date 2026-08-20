"""Creative state observer for interpret metadata (refactor plan P2)."""

from __future__ import annotations

from app.models import UserEvent


def attach_creative_state(features: dict[str, object], event: UserEvent) -> None:
        """Lightweight Creative State Observer for interpret metadata (Phase flow-spec)."""
        live = features.get("live_signals") if isinstance(features.get("live_signals"), dict) else {}
        dwell_ms = float(live.get("dwell_ms") or 0)
        compare_dwell = float(live.get("compare_dwell_ms") or 0)
        attempt_rate = float(live.get("new_case_attempt_rate") or 0)
        semantic_distance = float(live.get("semantic_distance") or 0)
        hover_count = int(live.get("hover_count") or 0)
        brush_count = int(live.get("brush_count") or 0)
        annotation_count = int(live.get("annotation_count") or 0)
        orbit = int(live.get("viewport_orbit_count") or 0)
        zoom = int(live.get("viewport_zoom_count") or 0)
        has_part = bool(features.get("part_id"))
        has_asset = bool(features.get("asset_id"))
        event_type = str(event.type or "")

        state = "idle"
        confidence = 0.4
        if compare_dwell >= 2500 or event_type == "candidate_compared":
            state, confidence = "comparing", 0.82
        elif brush_count >= 2 and dwell_ms >= 1200 and attempt_rate < 0.35:
            state, confidence = "refining", 0.7
        elif has_part and (hover_count > 0 or brush_count > 0 or annotation_count > 0):
            if dwell_ms >= 2000 and attempt_rate < 0.3 and (hover_count > 0 or orbit + zoom >= 2):
                state, confidence = "possible_fixation", 0.74
            else:
                state, confidence = "focused_editing", 0.68
        elif attempt_rate >= 0.45 or semantic_distance >= 0.55:
            state, confidence = "exploring", 0.66
        elif has_asset or orbit > 0 or zoom > 0:
            state, confidence = "exploring", 0.45

        # Promote possible fixation when IR also hints stagnation-like routes.
        ir = features.get("design_state_ir") if isinstance(features.get("design_state_ir"), dict) else {}
        predicted = str(ir.get("predicted_state") or "")
        mapped = {
            "Exploration": "exploring",
            "Formation": "focused_editing",
            "Refinement": "refining",
            "Evaluation": "comparing",
        }.get(predicted)
        if mapped and state not in {"possible_fixation", "ready_for_help", "comparing"}:
            state, confidence = mapped, max(confidence, 0.64)
        top = (ir.get("matches") or [None])[0] if isinstance(ir.get("matches"), list) else None
        route = str((top or {}).get("route") or "").lower() if isinstance(top, dict) else ""
        if state == "possible_fixation" and ("fix" in route or "help" in route or "stuck" in route):
            state, confidence = "ready_for_help", max(confidence, 0.78)
        elif state == "possible_fixation" and dwell_ms >= 4000:
            state, confidence = "ready_for_help", max(confidence, 0.72)

        scope_from_ir = {
            "Silhouette": "whole_object",
            "Part": "part_or_region",
            "Material": "material_surface",
        }.get(str(ir.get("predicted_hierarchy") or ""))
        scope_hint = scope_from_ir or features.get("ir_scope_hint") or (
            "part" if has_part else "contour"
        )
        features["creative_state"] = state
        features["creative_state_confidence"] = round(confidence, 3)
        features["change_scope_hint"] = scope_hint
        recommended = ir.get("recommended_axes") if isinstance(ir, dict) else None
        if isinstance(recommended, list):
            features["recommended_axes"] = recommended[:4]

