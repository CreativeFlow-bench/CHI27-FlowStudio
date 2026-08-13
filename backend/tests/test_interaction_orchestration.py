from __future__ import annotations

from app.models import (
    IntentRevision,
    IntentRevisionStatus,
    InteractionAggregateType,
    InteractionAuditEvent,
    InteractionDomainEvent,
    InteractionTask,
    InteractionTaskType,
    SourceContext,
)
from app.services.interaction.domain import assert_intent_transition
from app.services.pipeline.four_stage_orchestrator import FourStageConflict
from app.services.storage.four_stage_store import FourStageStore


def _revision() -> IntentRevision:
    return IntentRevision(
        revision_id="rev_a",
        session_id="session_a",
        intent_seq=1,
        window_start_seq=1,
        cutoff_seq=1,
        source_context=SourceContext(asset_id="asset_a", object_type="snowman"),
        status=IntentRevisionStatus.awaiting_gate,
    )


def test_interaction_command_is_idempotent_and_outbox_is_ordered() -> None:
    store = FourStageStore()
    revision = _revision()
    audit = InteractionAuditEvent(
        audit_id="audit_a",
        command_id="cmd_a",
        command_type="AcceptGate",
        idempotency_key="idem_a",
        session_id=revision.session_id,
        revision_id=revision.revision_id,
    )
    event = InteractionDomainEvent(
        event_id="event_a",
        event_type="GateAccepted",
        session_id=revision.session_id,
        revision_id=revision.revision_id,
        intent_seq=revision.intent_seq,
        aggregate_type=InteractionAggregateType.intent_revision,
        aggregate_id=revision.revision_id,
        aggregate_version=2,
    )
    task = InteractionTask(
        task_id="task_a",
        task_type=InteractionTaskType.semantic_divergence,
        session_id=revision.session_id,
        revision_id=revision.revision_id,
        idempotency_key="task:idem_a",
    )
    revision.status = IntentRevisionStatus.accepted
    revision.version = 2
    saved_task, events = store.commit_interaction_command(
        revision=revision, audit=audit, events=[event], task=task
    )
    assert saved_task is not None
    assert events[0].event_cursor == 1
    replay_task, replay_events = store.commit_interaction_command(
        revision=revision, audit=audit, events=[event], task=task
    )
    assert replay_task is not None
    assert replay_task.task_id == task.task_id
    assert len(replay_events) == 1
    assert store.list_interaction_events("session_a")[0].event_id == "event_a"
    pending = store.list_pending_interaction_outbox()
    assert [item.event_id for item in pending] == ["event_a"]
    store.mark_interaction_outbox_published("event_a")
    assert store.list_pending_interaction_outbox() == []


def test_task_lease_can_be_reclaimed_after_expiry() -> None:
    store = FourStageStore()
    task = InteractionTask(
        task_id="task_lease",
        task_type=InteractionTaskType.solution_generation,
        session_id="session_a",
        idempotency_key="lease-a",
    )
    store.commit_interaction_command(
        revision=None,
        audit=InteractionAuditEvent(
            audit_id="audit_lease",
            command_id="cmd_lease",
            command_type="StartGeneration",
            idempotency_key="idem_lease",
            session_id="session_a",
        ),
        events=[],
        task=task,
    )
    claimed = store.claim_interaction_task(lease_owner="worker_a", lease_seconds=0, task_id=task.task_id)
    assert claimed is not None
    reclaimed = store.claim_interaction_task(lease_owner="worker_b", lease_seconds=30, task_id=task.task_id)
    assert reclaimed is not None
    assert reclaimed.lease_owner == "worker_b"
    assert reclaimed.attempt == 2


def test_terminal_intent_revision_cannot_roll_back() -> None:
    assert_intent_transition(IntentRevisionStatus.awaiting_gate, IntentRevisionStatus.accepted)
    assert_intent_transition(IntentRevisionStatus.accepted, IntentRevisionStatus.accepted)
    try:
        assert_intent_transition(IntentRevisionStatus.completed, IntentRevisionStatus.awaiting_gate)
    except FourStageConflict:
        pass
    else:
        raise AssertionError("terminal revision unexpectedly rolled back")
