"""Behavior tests for the append-only experiment project ledger."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from app.models import ProjectCreateRequest, ProjectEventCreate, ProjectUpdateRequest
from app.services.storage.experiment_project_store import (
    ExperimentProjectConflict,
    ExperimentProjectStore,
)


def _project(store: ExperimentProjectStore, *, session_id: str = "sess_recorded"):
    return store.create_project(
        ProjectCreateRequest(
            title="Participant P07",
            participant_code="P07",
            condition_label="A",
            session_id=session_id,
            baseline_mode="blank",
        )
    )


def test_project_events_are_gap_free_idempotent_and_append_only(tmp_path) -> None:
    store = ExperimentProjectStore(tmp_path / "projects.sqlite3")
    project = _project(store)
    run_id = project.active_run.run_id

    first = store.append_event(
        run_id,
        ProjectEventCreate(
            event_type="input.text_snapshot",
            actor="user",
            idempotency_key="text-1",
            payload={"text": "rounder hat"},
        ),
    )
    duplicate = store.append_event(
        run_id,
        ProjectEventCreate(
            event_type="input.text_snapshot",
            actor="user",
            idempotency_key="text-1",
            payload={"text": "rounder hat"},
        ),
    )
    exclusion = store.append_event(
        run_id,
        ProjectEventCreate(
            event_type="event.excluded_from_analysis",
            actor="user",
            idempotency_key="exclude-1",
            parent_event_id=first.event_id,
            payload={"reason": "participant correction"},
        ),
    )

    assert [first.seq, duplicate.seq, exclusion.seq] == [4, 4, 5]
    events = store.list_events(project.project.project_id)
    assert [item.event_type for item in events[:3]] == [
        "project.created",
        "run.started",
        "baseline.captured",
    ]
    assert events[3].payload == {"text": "rounder hat"}
    assert events[4].parent_event_id == first.event_id


def test_concurrent_appends_receive_unique_monotonic_sequences(tmp_path) -> None:
    store = ExperimentProjectStore(tmp_path / "projects.sqlite3")
    project = _project(store)
    run_id = project.active_run.run_id

    def append(index: int):
        return store.append_event(
            run_id,
            ProjectEventCreate(
                event_type="input.selection_changed",
                actor="user",
                idempotency_key=f"selection-{index}",
                payload={"selection": index},
            ),
        )

    with ThreadPoolExecutor(max_workers=6) as executor:
        appended = list(executor.map(append, range(12)))

    assert sorted(item.seq for item in appended) == list(range(4, 16))
    assert [item.seq for item in store.list_events(project.project.project_id)] == list(range(1, 16))


def test_ended_run_rejects_events_and_next_run_rebinds_session(tmp_path) -> None:
    store = ExperimentProjectStore(tmp_path / "projects.sqlite3")
    project = _project(store, session_id="sess_first")
    old_run_id = project.active_run.run_id

    ended = store.end_run(project.project.project_id, old_run_id)
    assert ended.recording_status == "ended"
    with pytest.raises(ExperimentProjectConflict, match="run_ended"):
        store.append_event(
            old_run_id,
            ProjectEventCreate(
                event_type="input.text_snapshot",
                actor="user",
                idempotency_key="late",
                payload={"text": "too late"},
            ),
        )

    next_run = store.start_run(
        project.project.project_id,
        session_id="sess_second",
        baseline_mode="current_state",
        baseline_snapshot={"asset_id": "asset_1"},
    )
    assert next_run.run_number == 2
    assert store.project_for_session("sess_first") is None
    rebound = store.project_for_session("sess_second")
    assert rebound is not None
    assert rebound.project.project_id == project.project.project_id
    assert rebound.active_run.run_id == next_run.run_id


def test_metadata_updates_do_not_rewrite_recorded_events(tmp_path) -> None:
    store = ExperimentProjectStore(tmp_path / "projects.sqlite3")
    project = _project(store)
    before = [item.model_dump(mode="json") for item in store.list_events(project.project.project_id)]

    updated = store.update_project(
        project.project.project_id,
        ProjectUpdateRequest(title="Participant P07 revised", tags=["pilot"]),
    )

    assert updated.title == "Participant P07 revised"
    assert updated.tags == ["pilot"]
    after = [item.model_dump(mode="json") for item in store.list_events(project.project.project_id)]
    assert after[:3] == before
    assert after[-1]["event_type"] == "project.metadata_changed"


def test_store_uses_wal_journal_mode(tmp_path) -> None:
    store = ExperimentProjectStore(tmp_path / "projects.sqlite3")
    assert store.journal_mode() == "wal"
