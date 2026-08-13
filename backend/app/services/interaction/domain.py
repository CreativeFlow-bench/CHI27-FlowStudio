"""Pure domain rules for interaction aggregate transitions."""

from __future__ import annotations

from app.models.realtime_observation import IntentRevisionStatus
from app.services.pipeline.four_stage_orchestrator import FourStageConflict


INTENT_TRANSITIONS: dict[IntentRevisionStatus, set[IntentRevisionStatus]] = {
    IntentRevisionStatus.planning: {
        IntentRevisionStatus.awaiting_gate,
        IntentRevisionStatus.failed,
        IntentRevisionStatus.cancelled,
    },
    IntentRevisionStatus.awaiting_gate: {
        IntentRevisionStatus.accepted,
        IntentRevisionStatus.rejected,
        IntentRevisionStatus.failed,
        IntentRevisionStatus.cancelled,
    },
    IntentRevisionStatus.accepted: {
        IntentRevisionStatus.accepted,
        IntentRevisionStatus.generating,
        IntentRevisionStatus.failed,
        IntentRevisionStatus.cancelled,
    },
    IntentRevisionStatus.generating: {
        IntentRevisionStatus.generating,
        IntentRevisionStatus.completed,
        IntentRevisionStatus.failed,
        IntentRevisionStatus.cancelled,
    },
    IntentRevisionStatus.completed: {IntentRevisionStatus.completed},
    IntentRevisionStatus.rejected: {IntentRevisionStatus.rejected},
    IntentRevisionStatus.failed: {IntentRevisionStatus.failed},
    IntentRevisionStatus.cancelled: {IntentRevisionStatus.cancelled},
}


def assert_intent_transition(
    current: IntentRevisionStatus,
    target: IntentRevisionStatus,
) -> None:
    if target not in INTENT_TRANSITIONS.get(current, set()):
        raise FourStageConflict(f"illegal intent revision transition: {current} -> {target}")


def phase_for_revision(status: IntentRevisionStatus, task_status: str | None = None) -> str:
    if status == IntentRevisionStatus.planning:
        return "planning_intent"
    if status == IntentRevisionStatus.awaiting_gate:
        return "awaiting_gate"
    if status == IntentRevisionStatus.accepted:
        return "preparing_keywords" if task_status in {"queued", "running"} else "choosing_keywords"
    if status == IntentRevisionStatus.generating:
        return "generating"
    if status == IntentRevisionStatus.completed:
        return "reviewing_solutions"
    if status == IntentRevisionStatus.failed:
        return "needs_attention"
    return "observing"


__all__ = ["INTENT_TRANSITIONS", "assert_intent_transition", "phase_for_revision"]
