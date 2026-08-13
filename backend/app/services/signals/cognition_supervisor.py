"""① Cognition supervisor: thinking behaviour (pauses, hesitation).

Paper-aligned role: this class does NOT vote for a target; it modulates
confidence and decides whether the planner must clarify before expanding.
It reuses the creative-state observer already computed in
interaction_understanding and adds hesitation metrics from raw signals.
"""

from __future__ import annotations

from typing import Any

from app.models import CognitionOutput


STABLE_STATES = {"refining", "possible_fixation", "ready_for_help", "focused_editing"}


def supervise_cognition(features: dict[str, Any]) -> CognitionOutput:
    live = features.get("live_signals") if isinstance(features.get("live_signals"), dict) else {}
    creative_state = str(features.get("creative_state") or "idle")
    confidence = float(features.get("creative_state_confidence") or 0.4)

    dwell_ms = float(live.get("dwell_ms") or 0)
    compare_ms = float(live.get("compare_dwell_ms") or 0)
    undo_count = int(features.get("recent_undo_count") or 0)
    same_event_count = int(features.get("same_event_type_recent_count") or 0)
    hover_count = int(live.get("hover_count") or 0)
    orbit = int(live.get("viewport_orbit_count") or 0)
    zoom = int(live.get("viewport_zoom_count") or 0)

    evidence: list[str] = []
    hesitation = 0.0
    if dwell_ms >= 4000:
        hesitation += 0.3
        evidence.append(f"long_dwell:{dwell_ms:.0f}ms")
    elif dwell_ms >= 2000:
        hesitation += 0.2
    if compare_ms >= 2500:
        hesitation += 0.3
        evidence.append(f"compare:{compare_ms:.0f}ms")
    if undo_count >= 2:
        hesitation += 0.3
        evidence.append(f"undo_redo:{undo_count}")
    if same_event_count >= 3:
        hesitation += 0.2
        evidence.append(f"repeated_micro_edit:{same_event_count}")
    if hover_count >= 3 and orbit + zoom >= 2:
        hesitation += 0.1
        evidence.append("hover_oscillation")
    hesitation = min(1.0, round(hesitation, 3))

    fixation_stable = creative_state in STABLE_STATES
    require_clarification = hesitation >= 0.7 and not fixation_stable
    base_modifier = 1.0 if fixation_stable else max(0.4, 0.75 - hesitation * 0.45)
    confidence_modifier = round(min(1.0, base_modifier * (0.7 + 0.3 * confidence)), 3)

    if creative_state in {"ready_for_help", "possible_fixation"}:
        evidence.append(f"creative_state:{creative_state}")
    if not evidence:
        evidence.append("no_cognitive_signal")

    return CognitionOutput(
        hesitation=hesitation,
        fixation_stable=fixation_stable,
        creative_state=creative_state,
        confidence_modifier=confidence_modifier,
        require_clarification=require_clarification,
        evidence=evidence,
    )
