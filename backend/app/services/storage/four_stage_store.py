"""Minimal SQLite persistence for the four-stage pipeline.

One file per strategy doc section 11.1:
- ``four_stage_runs`` holds the run row plus every stage output as a JSON
  column. Outputs are always serialized from Pydantic models, never raw dicts.
- ``generation_jobs`` and ``model_call_audits`` are added by later phases.

The store is intentionally small: no migration framework, no ORM. ``:memory:``
is used when no path is given (tests, and app startup under pytest).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from app.models import (
    BehaviorSession,
    FourStageRun,
    IntentRevision,
    LiveObservationState,
    SemanticDivergenceResponse,
    SolutionBatch,
    VersionGraphNode,
    VersionGraphState,
    now_utc,
)
from app.models.interaction import (
    InteractionAuditEvent,
    InteractionDomainEvent,
    InteractionOutboxRecord,
    InteractionTask,
    InteractionTaskStatus,
    InteractionTaskType,
)


def _iso(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


class FourStageStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self._path: str | Path | None = path
        self._lock = threading.Lock()
        self._conn = self._connect()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self._path) if self._path is not None else ":memory:",
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        return conn

    def reopen(self, path: str | Path) -> None:
        """Switch to a file-backed database (used by app startup outside pytest)."""
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass
            self._path = path
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = self._connect()
        # _init_schema takes the (non-reentrant) lock itself; do not call it
        # while holding the lock.
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS four_stage_runs (
                    run_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    idempotency_key TEXT,
                    episode_id TEXT,
                stage TEXT NOT NULL,
                run_hy3d INTEGER NOT NULL DEFAULT 0,
                raw_events TEXT NOT NULL,
                    source_event_ids TEXT NOT NULL,
                    source_context TEXT,
                    intent_ir TEXT,
                    retrieval TEXT,
                    decision TEXT,
                    gate_decision TEXT,
                    scope_gate TEXT,
                    semantic_divergence TEXT,
                    divergence_selection TEXT,
                    generation_spec TEXT,
                    error TEXT,
                    failed_stage TEXT,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    stage_timestamps TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_fs_runs_session ON four_stage_runs(session_id)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_fs_runs_idempotency ON four_stage_runs(idempotency_key)"
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS retrieval_feedback (
                    feedback_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    prior_ir_id TEXT,
                    case_id TEXT,
                    action TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_fb_case ON retrieval_feedback(case_id, created_at)"
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS model_call_audits (
                    audit_id TEXT PRIMARY KEY,
                    run_id TEXT,
                    model TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    request_id TEXT,
                    latency_ms INTEGER,
                    prompt_tokens INTEGER,
                    completion_tokens INTEGER,
                    error_type TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS generation_jobs (
                    job_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    spec TEXT NOT NULL,
                    status TEXT NOT NULL,
                    lease_owner TEXT,
                    lease_expires_at TEXT,
                    remote_job_id TEXT,
                    artifacts TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_gen_jobs_run ON generation_jobs(run_id)"
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS behavior_sessions (
                    behavior_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    behavior_seq INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(session_id, behavior_seq)
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_behaviors_session_seq "
                "ON behavior_sessions(session_id, behavior_seq)"
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS live_observation_states (
                    session_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS intent_revisions (
                    revision_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    intent_seq INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(session_id, intent_seq)
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_revisions_session_seq "
                "ON intent_revisions(session_id, intent_seq)"
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS solution_batches (
                    batch_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    intent_seq INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(session_id, intent_seq)
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_batches_session_seq "
                "ON solution_batches(session_id, intent_seq)"
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS interaction_tasks (
                    task_id TEXT PRIMARY KEY,
                    task_type TEXT NOT NULL,
                    project_id TEXT,
                    session_id TEXT NOT NULL,
                    revision_id TEXT,
                    status TEXT NOT NULL,
                    input_json TEXT NOT NULL,
                    result_ref TEXT,
                    progress REAL NOT NULL DEFAULT 0,
                    attempt INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    lease_owner TEXT,
                    lease_expires_at TEXT,
                    idempotency_key TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    UNIQUE(session_id, idempotency_key)
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_interaction_tasks_claim "
                "ON interaction_tasks(status, lease_expires_at, created_at)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_interaction_tasks_revision "
                "ON interaction_tasks(session_id, revision_id, created_at)"
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS interaction_audit_events (
                    audit_id TEXT PRIMARY KEY,
                    command_id TEXT NOT NULL,
                    command_type TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    project_id TEXT,
                    session_id TEXT NOT NULL,
                    revision_id TEXT,
                    actor TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    correlation_id TEXT,
                    causation_id TEXT,
                    UNIQUE(session_id, idempotency_key)
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS interaction_domain_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    project_id TEXT,
                    session_id TEXT NOT NULL,
                    revision_id TEXT,
                    intent_seq INTEGER,
                    aggregate_type TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    aggregate_version INTEGER NOT NULL,
                    correlation_id TEXT,
                    causation_id TEXT,
                    occurred_at TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    event_cursor INTEGER NOT NULL UNIQUE
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_interaction_events_session_cursor "
                "ON interaction_domain_events(session_id, event_cursor)"
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS interaction_outbox (
                    outbox_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL UNIQUE,
                    event_payload TEXT NOT NULL,
                    published_at TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS version_graph_nodes (
                    node_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    parent_node_id TEXT,
                    candidate_id TEXT,
                    version_number INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_version_nodes_session "
                "ON version_graph_nodes(session_id, version_number)"
            )
            self._conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_version_nodes_parent_candidate "
                "ON version_graph_nodes(session_id, COALESCE(parent_node_id, ''), "
                "COALESCE(candidate_id, ''))"
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS version_graph_states (
                    session_id TEXT PRIMARY KEY,
                    active_node_id TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            try:
                self._conn.execute(
                    "ALTER TABLE four_stage_runs ADD COLUMN generation_artifacts "
                    "TEXT NOT NULL DEFAULT '[]'"
                )
            except sqlite3.OperationalError:
                pass  # column already exists
            try:
                self._conn.execute(
                    "ALTER TABLE four_stage_runs ADD COLUMN run_hy3d "
                    "INTEGER NOT NULL DEFAULT 0"
                )
            except sqlite3.OperationalError:
                pass  # column already exists
            for column in (
                "source_context",
                "scope_gate",
                "semantic_divergence",
                "divergence_selection",
            ):
                try:
                    self._conn.execute(
                        f"ALTER TABLE four_stage_runs ADD COLUMN {column} TEXT"
                    )
                except sqlite3.OperationalError:
                    pass  # column already exists
            self._conn.commit()

    def save_run(self, run: FourStageRun) -> FourStageRun:
        run.updated_at = now_utc()
        row = {
            "run_id": run.run_id,
            "session_id": run.session_id,
            "idempotency_key": run.idempotency_key,
            "episode_id": run.episode_id,
            "stage": run.stage.value,
            "run_hy3d": int(bool(run.run_hy3d)),
            "raw_events": json.dumps(
                [event.model_dump(mode="json") for event in run.events],
                ensure_ascii=False,
            ),
            "source_event_ids": json.dumps(run.source_event_ids, ensure_ascii=False),
            "source_context": self._dumps(run.source_context),
            "intent_ir": self._dumps(run.intent_ir),
            "retrieval": self._dumps(run.retrieval),
            "decision": self._dumps(run.decision),
            "gate_decision": self._dumps(run.gate_decision),
            "scope_gate": self._dumps(run.scope_gate),
            "semantic_divergence": self._dumps(run.semantic_divergence),
            "divergence_selection": self._dumps(run.divergence_selection),
            "generation_spec": self._dumps(run.generation_spec),
            "generation_artifacts": json.dumps(
                run.generation_artifacts, ensure_ascii=False
            ),
            "error": json.dumps(run.error, ensure_ascii=False) if run.error else None,
            "failed_stage": run.failed_stage.value if run.failed_stage else None,
            "retry_count": run.retry_count,
            "stage_timestamps": json.dumps(run.stage_timestamps, ensure_ascii=False),
            "schema_version": run.schema_version,
            "created_at": _iso(run.created_at),
            "updated_at": _iso(run.updated_at),
            "completed_at": _iso(run.completed_at) or None,
        }
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO four_stage_runs (
                    run_id, session_id, idempotency_key, episode_id, stage,
                    run_hy3d,
                    raw_events,
                    source_event_ids, source_context, intent_ir, retrieval, decision,
                    gate_decision, scope_gate, semantic_divergence, divergence_selection, generation_spec,
                    generation_artifacts, error,
                    failed_stage,
                    retry_count, stage_timestamps, schema_version, created_at,
                    updated_at, completed_at
                ) VALUES (
                    :run_id, :session_id, :idempotency_key, :episode_id, :stage,
                    :run_hy3d,
                    :raw_events,
                    :source_event_ids, :source_context, :intent_ir, :retrieval, :decision,
                    :gate_decision, :scope_gate, :semantic_divergence, :divergence_selection, :generation_spec,
                    :generation_artifacts, :error,
                    :failed_stage,
                    :retry_count, :stage_timestamps, :schema_version, :created_at,
                    :updated_at, :completed_at
                )
                ON CONFLICT(run_id) DO UPDATE SET
                    stage = excluded.stage,
                    run_hy3d = excluded.run_hy3d,
                    raw_events = excluded.raw_events,
                    source_event_ids = excluded.source_event_ids,
                    source_context = excluded.source_context,
                    intent_ir = excluded.intent_ir,
                    retrieval = excluded.retrieval,
                    decision = excluded.decision,
                    gate_decision = excluded.gate_decision,
                    scope_gate = excluded.scope_gate,
                    semantic_divergence = excluded.semantic_divergence,
                    divergence_selection = excluded.divergence_selection,
                    generation_spec = excluded.generation_spec,
                    generation_artifacts = excluded.generation_artifacts,
                    error = excluded.error,
                    failed_stage = excluded.failed_stage,
                    retry_count = excluded.retry_count,
                    stage_timestamps = excluded.stage_timestamps,
                    updated_at = excluded.updated_at,
                    completed_at = excluded.completed_at
                """
                , row,
            )
            self._conn.commit()
        return run

    def get_run(self, run_id: str) -> FourStageRun | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM four_stage_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return self._row_to_run(row) if row is not None else None

    def update_semantic_divergence_if_current(
        self,
        run_id: str,
        *,
        expected_decision_id: str,
        response: SemanticDivergenceResponse,
        require_accepted: bool = True,
    ) -> bool:
        """Atomically attach divergence without overwriting newer run state."""
        with self._lock:
            row = self._conn.execute(
                """
                SELECT stage, decision, gate_decision, scope_gate
                FROM four_stage_runs WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            if row is None or row["stage"] != "awaiting_gate":
                return False
            try:
                decision = json.loads(row["decision"] or "null") or {}
                gate_decision = json.loads(row["gate_decision"] or "null") or {}
                scope_gate = json.loads(row["scope_gate"] or "null") or {}
            except (TypeError, json.JSONDecodeError):
                return False
            if decision.get("decision_id") != expected_decision_id:
                return False
            if require_accepted and (
                gate_decision.get("decision_id") != expected_decision_id
                or gate_decision.get("action") != "accept_option"
                or scope_gate.get("status") != "accepted"
            ):
                return False
            if (
                response.run_id != run_id
                or response.decision_id != expected_decision_id
            ):
                return False
            self._conn.execute(
                """
                UPDATE four_stage_runs
                SET semantic_divergence = ?, updated_at = ?
                WHERE run_id = ?
                """,
                (self._dumps(response), _iso(now_utc()), run_id),
            )
            self._conn.commit()
            return True

    def find_by_idempotency(
        self, session_id: str, idempotency_key: str
    ) -> FourStageRun | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT * FROM four_stage_runs
                WHERE session_id = ? AND idempotency_key = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (session_id, idempotency_key),
            ).fetchone()
        return self._row_to_run(row) if row is not None else None

    def list_runs(self, session_id: str | None = None, limit: int = 50) -> list[FourStageRun]:
        with self._lock:
            if session_id:
                rows = self._conn.execute(
                    """
                    SELECT * FROM four_stage_runs WHERE session_id = ?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (session_id, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM four_stage_runs ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._row_to_run(row) for row in rows]

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM four_stage_runs")
            self._conn.execute("DELETE FROM retrieval_feedback")
            self._conn.execute("DELETE FROM model_call_audits")
            self._conn.execute("DELETE FROM generation_jobs")
            self._conn.execute("DELETE FROM behavior_sessions")
            self._conn.execute("DELETE FROM live_observation_states")
            self._conn.execute("DELETE FROM intent_revisions")
            self._conn.execute("DELETE FROM solution_batches")
            self._conn.execute("DELETE FROM version_graph_nodes")
            self._conn.execute("DELETE FROM version_graph_states")
            self._conn.execute("DELETE FROM interaction_tasks")
            self._conn.execute("DELETE FROM interaction_audit_events")
            self._conn.execute("DELETE FROM interaction_domain_events")
            self._conn.execute("DELETE FROM interaction_outbox")
            self._conn.commit()

    def clear_session(self, session_id: str) -> None:
        """Delete every persisted four-stage artifact owned by one session."""
        with self._lock:
            self._conn.execute(
                "DELETE FROM model_call_audits WHERE run_id IN "
                "(SELECT run_id FROM four_stage_runs WHERE session_id = ?)",
                (session_id,),
            )
            for table in (
                "retrieval_feedback",
                "generation_jobs",
                "behavior_sessions",
                "live_observation_states",
                "intent_revisions",
                "solution_batches",
                "version_graph_nodes",
                "version_graph_states",
                "four_stage_runs",
                "interaction_tasks",
                "interaction_audit_events",
                "interaction_domain_events",
            ):
                if table == "interaction_audit_events":
                    clause = "session_id = ?"
                elif table == "interaction_domain_events":
                    clause = "session_id = ?"
                else:
                    clause = "session_id = ?"
                self._conn.execute(f"DELETE FROM {table} WHERE {clause}", (session_id,))
            self._conn.execute(
                "DELETE FROM interaction_outbox WHERE event_id NOT IN "
                "(SELECT event_id FROM interaction_domain_events)"
            )
            self._conn.commit()

    def next_behavior_seq(self, session_id: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(MAX(behavior_seq), 0) + 1 AS seq "
                "FROM behavior_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return int(row["seq"])

    def save_behavior(self, behavior: BehaviorSession) -> BehaviorSession:
        payload = behavior.model_dump_json()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO behavior_sessions (
                    behavior_id, session_id, behavior_seq, payload, created_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(behavior_id) DO UPDATE SET payload = excluded.payload
                """,
                (
                    behavior.behavior_id,
                    behavior.session_id,
                    behavior.behavior_seq,
                    payload,
                    behavior.started_at.isoformat(),
                ),
            )
            self._conn.commit()
        return behavior

    def get_behavior(self, behavior_id: str) -> BehaviorSession | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM behavior_sessions WHERE behavior_id = ?",
                (behavior_id,),
            ).fetchone()
        return BehaviorSession.model_validate_json(row["payload"]) if row else None

    def delete_behavior(self, behavior_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM behavior_sessions WHERE behavior_id = ?", (behavior_id,)
            )
            self._conn.commit()

    def list_behaviors(
        self,
        session_id: str,
        *,
        start_seq: int | None = None,
        end_seq: int | None = None,
    ) -> list[BehaviorSession]:
        clauses = ["session_id = ?"]
        params: list[Any] = [session_id]
        if start_seq is not None:
            clauses.append("behavior_seq >= ?")
            params.append(start_seq)
        if end_seq is not None:
            clauses.append("behavior_seq <= ?")
            params.append(end_seq)
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload FROM behavior_sessions WHERE "
                + " AND ".join(clauses)
                + " ORDER BY behavior_seq",
                params,
            ).fetchall()
        return [BehaviorSession.model_validate_json(row["payload"]) for row in rows]

    def save_live_observation(self, state: LiveObservationState) -> LiveObservationState:
        state.updated_at = now_utc()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO live_observation_states (session_id, payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    payload = excluded.payload, updated_at = excluded.updated_at
                """,
                (state.session_id, state.model_dump_json(), state.updated_at.isoformat()),
            )
            self._conn.commit()
        return state

    def get_live_observation(self, session_id: str) -> LiveObservationState | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM live_observation_states WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return LiveObservationState.model_validate_json(row["payload"]) if row else None

    def next_intent_seq(self, session_id: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(MAX(intent_seq), 0) + 1 AS seq "
                "FROM intent_revisions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return int(row["seq"])

    def save_revision(self, revision: IntentRevision) -> IntentRevision:
        revision.updated_at = now_utc()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO intent_revisions (
                    revision_id, session_id, intent_seq, payload, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(revision_id) DO UPDATE SET
                    payload = excluded.payload, updated_at = excluded.updated_at
                """,
                (
                    revision.revision_id,
                    revision.session_id,
                    revision.intent_seq,
                    revision.model_dump_json(),
                    revision.created_at.isoformat(),
                    revision.updated_at.isoformat(),
                ),
            )
            self._conn.commit()
        return revision

    def get_revision(self, revision_id: str) -> IntentRevision | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM intent_revisions WHERE revision_id = ?",
                (revision_id,),
            ).fetchone()
        return IntentRevision.model_validate_json(row["payload"]) if row else None

    def list_revisions(self, session_id: str) -> list[IntentRevision]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload FROM intent_revisions WHERE session_id = ? ORDER BY intent_seq",
                (session_id,),
            ).fetchall()
        return [IntentRevision.model_validate_json(row["payload"]) for row in rows]

    # ------------------------------------------------------------------
    # Durable interaction orchestration records.  These methods use the same
    # SQLite connection as FourStageRun/IntentRevision so command state,
    # audit events, domain events, and outbox rows can be committed together.

    def commit_interaction_command(
        self,
        *,
        revision: IntentRevision | None,
        audit: InteractionAuditEvent,
        events: list[InteractionDomainEvent],
        task: InteractionTask | None = None,
    ) -> tuple[InteractionTask | None, list[InteractionDomainEvent]]:
        """Persist a command acknowledgement atomically and idempotently."""
        with self._lock:
            existing_audit = self._conn.execute(
                "SELECT audit_id, command_id FROM interaction_audit_events "
                "WHERE session_id = ? AND idempotency_key = ?",
                (audit.session_id, audit.idempotency_key),
            ).fetchone()
            if existing_audit is not None:
                existing_task = self._conn.execute(
                    "SELECT * FROM interaction_tasks "
                    "WHERE session_id = ? AND idempotency_key = ?",
                    (
                        audit.session_id,
                        task.idempotency_key if task is not None else "",
                    ),
                ).fetchone()
                return (
                    self._interaction_task_from_row(existing_task)
                    if existing_task
                    else None,
                    self.list_interaction_events_unlocked(
                        audit.session_id,
                        correlation_id=existing_audit["command_id"],
                    ),
                )

            if revision is not None:
                revision.updated_at = now_utc()
                self._conn.execute(
                    """
                    INSERT INTO intent_revisions (
                        revision_id, session_id, intent_seq, payload, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(revision_id) DO UPDATE SET
                        payload = excluded.payload, updated_at = excluded.updated_at
                    """,
                    (
                        revision.revision_id,
                        revision.session_id,
                        revision.intent_seq,
                        revision.model_dump_json(),
                        revision.created_at.isoformat(),
                        revision.updated_at.isoformat(),
                    ),
                )
            self._conn.execute(
                """
                INSERT INTO interaction_audit_events (
                    audit_id, command_id, command_type, idempotency_key, project_id,
                    session_id, revision_id, actor, payload, occurred_at,
                    correlation_id, causation_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit.audit_id,
                    audit.command_id,
                    audit.command_type,
                    audit.idempotency_key,
                    audit.project_id,
                    audit.session_id,
                    audit.revision_id,
                    audit.actor,
                    json.dumps(audit.payload, ensure_ascii=False),
                    audit.occurred_at.isoformat(),
                    audit.correlation_id,
                    audit.causation_id,
                ),
            )
            persisted_events: list[InteractionDomainEvent] = []
            for event in events:
                event.correlation_id = event.correlation_id or audit.command_id
                event.causation_id = event.causation_id or audit.command_id
                cursor = int(
                    self._conn.execute(
                        "SELECT COALESCE(MAX(event_cursor), 0) + 1 AS cursor "
                        "FROM interaction_domain_events"
                    ).fetchone()["cursor"]
                )
                event.event_cursor = cursor
                self._conn.execute(
                    """
                    INSERT INTO interaction_domain_events (
                        event_id, event_type, project_id, session_id, revision_id,
                        intent_seq, aggregate_type, aggregate_id, aggregate_version,
                        correlation_id, causation_id, occurred_at, payload, event_cursor
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.event_type,
                        event.project_id,
                        event.session_id,
                        event.revision_id,
                        event.intent_seq,
                        event.aggregate_type.value,
                        event.aggregate_id,
                        event.aggregate_version,
                        event.correlation_id,
                        event.causation_id,
                        event.occurred_at.isoformat(),
                        json.dumps(event.payload, ensure_ascii=False),
                        event.event_cursor,
                    ),
                )
                outbox = InteractionOutboxRecord(
                    outbox_id=f"outbox_{event.event_id}",
                    event=event,
                )
                self._conn.execute(
                    "INSERT INTO interaction_outbox "
                    "(outbox_id, event_id, event_payload) VALUES (?, ?, ?)",
                    (
                        outbox.outbox_id,
                        event.event_id,
                        outbox.event.model_dump_json(),
                    ),
                )
                persisted_events.append(event)
            persisted_task = None
            if task is not None:
                task.updated_at = now_utc()
                self._conn.execute(
                    """
                    INSERT INTO interaction_tasks (
                        task_id, task_type, project_id, session_id, revision_id,
                        status, input_json, result_ref, progress, attempt, max_attempts,
                        lease_owner, lease_expires_at, idempotency_key, created_at,
                        started_at, completed_at, error_code, error_message,
                        cancel_requested, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task.task_id,
                        task.task_type.value,
                        task.project_id,
                        task.session_id,
                        task.revision_id,
                        task.status.value,
                        json.dumps(task.input_json, ensure_ascii=False),
                        task.result_ref,
                        task.progress,
                        task.attempt,
                        task.max_attempts,
                        task.lease_owner,
                        _iso(task.lease_expires_at) or None,
                        task.idempotency_key,
                        task.created_at.isoformat(),
                        _iso(task.started_at) or None,
                        _iso(task.completed_at) or None,
                        task.error_code,
                        task.error_message,
                        int(task.cancel_requested),
                        task.updated_at.isoformat(),
                    ),
                )
                persisted_task = task
            self._conn.commit()
            return persisted_task, persisted_events

    def get_interaction_task(self, task_id: str) -> InteractionTask | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM interaction_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        return self._interaction_task_from_row(row) if row else None

    def list_interaction_tasks(
        self,
        session_id: str,
        revision_id: str | None = None,
    ) -> list[InteractionTask]:
        query = "SELECT * FROM interaction_tasks WHERE session_id = ?"
        params: list[Any] = [session_id]
        if revision_id is not None:
            query += " AND revision_id = ?"
            params.append(revision_id)
        query += " ORDER BY created_at"
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [self._interaction_task_from_row(row) for row in rows]

    def find_interaction_task_by_idempotency(
        self, session_id: str, idempotency_key: str
    ) -> InteractionTask | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM interaction_tasks WHERE session_id = ? AND idempotency_key = ?",
                (session_id, idempotency_key),
            ).fetchone()
        return self._interaction_task_from_row(row) if row else None

    def find_interaction_audit_by_idempotency(
        self, session_id: str, idempotency_key: str
    ) -> InteractionAuditEvent | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM interaction_audit_events "
                "WHERE session_id = ? AND idempotency_key = ?",
                (session_id, idempotency_key),
            ).fetchone()
        if row is None:
            return None
        return InteractionAuditEvent.model_validate(
            {
                "audit_id": row["audit_id"],
                "command_id": row["command_id"],
                "command_type": row["command_type"],
                "idempotency_key": row["idempotency_key"],
                "project_id": row["project_id"],
                "session_id": row["session_id"],
                "revision_id": row["revision_id"],
                "actor": row["actor"],
                "payload": json.loads(row["payload"] or "{}"),
                "occurred_at": row["occurred_at"],
                "correlation_id": row["correlation_id"],
                "causation_id": row["causation_id"],
            }
        )

    def claim_interaction_task(
        self,
        *,
        lease_owner: str,
        lease_seconds: int = 60,
        task_type: InteractionTaskType | None = None,
        task_id: str | None = None,
    ) -> InteractionTask | None:
        now = now_utc()
        expires = now_utc().fromtimestamp(now.timestamp() + lease_seconds, tz=now.tzinfo)
        with self._lock:
            clauses = [
                "(status = 'queued' OR (status = 'running' AND lease_expires_at < ?))",
                "cancel_requested = 0",
                "attempt < max_attempts",
            ]
            params: list[Any] = [now.isoformat()]
            if task_type is not None:
                clauses.append("task_type = ?")
                params.append(task_type.value)
            if task_id is not None:
                clauses.append("task_id = ?")
                params.append(task_id)
            row = self._conn.execute(
                "SELECT task_id FROM interaction_tasks WHERE "
                + " AND ".join(clauses)
                + " ORDER BY created_at LIMIT 1",
                params,
            ).fetchone()
            if row is None:
                return None
            updated = self._conn.execute(
                """
                UPDATE interaction_tasks
                SET status = 'running', lease_owner = ?, lease_expires_at = ?,
                    attempt = attempt + 1, started_at = COALESCE(started_at, ?),
                    updated_at = ?
                WHERE task_id = ?
                """,
                (
                    lease_owner,
                    expires.isoformat(),
                    now.isoformat(),
                    now.isoformat(),
                    row["task_id"],
                ),
            )
            if updated.rowcount != 1:
                self._conn.rollback()
                return None
            self._conn.commit()
            saved = self._conn.execute(
                "SELECT * FROM interaction_tasks WHERE task_id = ?", (row["task_id"],)
            ).fetchone()
        return self._interaction_task_from_row(saved) if saved else None

    def update_interaction_task(
        self,
        task: InteractionTask,
        *,
        lease_owner: str | None = None,
    ) -> InteractionTask:
        task.updated_at = now_utc()
        with self._lock:
            clauses = ["task_id = ?"]
            params: list[Any] = [task.task_id]
            if lease_owner is not None:
                clauses.append("lease_owner = ?")
                params.append(lease_owner)
            self._conn.execute(
                """
                UPDATE interaction_tasks
                SET status = ?, input_json = ?, result_ref = ?, progress = ?,
                    attempt = ?, max_attempts = ?,
                    lease_owner = ?, lease_expires_at = ?, completed_at = ?,
                    error_code = ?, error_message = ?, cancel_requested = ?, updated_at = ?
                WHERE """
                + " AND ".join(clauses),
                (
                    task.status.value,
                    json.dumps(task.input_json, ensure_ascii=False),
                    task.result_ref,
                    task.progress,
                    task.attempt,
                    task.max_attempts,
                    task.lease_owner,
                    _iso(task.lease_expires_at) or None,
                    _iso(task.completed_at) or None,
                    task.error_code,
                    task.error_message,
                    int(task.cancel_requested),
                    task.updated_at.isoformat(),
                    *params,
                ),
            )
            self._conn.commit()
        return task

    def renew_interaction_task(
        self,
        task_id: str,
        *,
        lease_owner: str,
        lease_seconds: int = 60,
    ) -> bool:
        now = now_utc()
        expires = now_utc().fromtimestamp(
            now.timestamp() + lease_seconds, tz=now.tzinfo
        )
        with self._lock:
            updated = self._conn.execute(
                "UPDATE interaction_tasks SET lease_expires_at = ?, updated_at = ? "
                "WHERE task_id = ? AND status = 'running' AND lease_owner = ?",
                (expires.isoformat(), now.isoformat(), task_id, lease_owner),
            )
            self._conn.commit()
        return updated.rowcount == 1

    def mark_interaction_outbox_published(self, event_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE interaction_outbox SET published_at = ?, attempts = attempts + 1 "
                "WHERE event_id = ?",
                (_iso(now_utc()), event_id),
            )
            self._conn.commit()

    def cancel_interaction_task(self, task_id: str) -> InteractionTask | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM interaction_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if row is None:
                return None
            status = row["status"]
            if status == InteractionTaskStatus.queued.value:
                self._conn.execute(
                    "UPDATE interaction_tasks SET status='cancelled', completed_at=?, updated_at=? "
                    "WHERE task_id = ?",
                    (_iso(now_utc()), _iso(now_utc()), task_id),
                )
            elif status == InteractionTaskStatus.running.value:
                self._conn.execute(
                    "UPDATE interaction_tasks SET cancel_requested=1, updated_at=? WHERE task_id=?",
                    (_iso(now_utc()), task_id),
                )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT * FROM interaction_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        return self._interaction_task_from_row(row) if row else None

    def list_interaction_events(
        self,
        session_id: str,
        *,
        after_cursor: int = 0,
        limit: int = 200,
        correlation_id: str | None = None,
    ) -> list[InteractionDomainEvent]:
        with self._lock:
            return self.list_interaction_events_unlocked(
                session_id,
                after_cursor=after_cursor,
                limit=limit,
                correlation_id=correlation_id,
            )

    def list_interaction_events_unlocked(
        self,
        session_id: str,
        *,
        after_cursor: int = 0,
        limit: int = 200,
        correlation_id: str | None = None,
    ) -> list[InteractionDomainEvent]:
        query = (
            "SELECT * FROM interaction_domain_events "
            "WHERE session_id = ? AND event_cursor > ?"
        )
        params: list[Any] = [session_id, after_cursor]
        if correlation_id is not None:
            query += " AND correlation_id = ?"
            params.append(correlation_id)
        query += " ORDER BY event_cursor LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(query, params).fetchall()
        return [
            self._interaction_event_from_row(row)
            for row in rows
        ]

    def list_pending_interaction_outbox(
        self,
        *,
        limit: int = 200,
    ) -> list[InteractionDomainEvent]:
        """Return unpublished events in durable event order for dispatch/retry."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT event_payload FROM interaction_outbox "
                "WHERE published_at IS NULL ORDER BY rowid LIMIT ?",
                (limit,),
            ).fetchall()
        events = [
            InteractionDomainEvent.model_validate(json.loads(row["event_payload"]))
            for row in rows
        ]
        return sorted(events, key=lambda event: event.event_cursor)

    def append_interaction_events(
        self, events: list[InteractionDomainEvent]
    ) -> list[InteractionDomainEvent]:
        """Append worker/domain events and their outbox records atomically."""
        if not events:
            return []
        with self._lock:
            for event in events:
                cursor = int(
                    self._conn.execute(
                        "SELECT COALESCE(MAX(event_cursor), 0) + 1 AS cursor "
                        "FROM interaction_domain_events"
                    ).fetchone()["cursor"]
                )
                event.event_cursor = cursor
                self._conn.execute(
                    "INSERT INTO interaction_domain_events ("
                    "event_id, event_type, project_id, session_id, revision_id, "
                    "intent_seq, aggregate_type, aggregate_id, aggregate_version, "
                    "correlation_id, causation_id, occurred_at, payload, event_cursor"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        event.event_id,
                        event.event_type,
                        event.project_id,
                        event.session_id,
                        event.revision_id,
                        event.intent_seq,
                        event.aggregate_type.value,
                        event.aggregate_id,
                        event.aggregate_version,
                        event.correlation_id,
                        event.causation_id,
                        event.occurred_at.isoformat(),
                        json.dumps(event.payload, ensure_ascii=False),
                        event.event_cursor,
                    ),
                )
                outbox = InteractionOutboxRecord(
                    outbox_id=f"outbox_{event.event_id}", event=event
                )
                self._conn.execute(
                    "INSERT INTO interaction_outbox "
                    "(outbox_id, event_id, event_payload) VALUES (?, ?, ?)",
                    (outbox.outbox_id, event.event_id, outbox.event.model_dump_json()),
                )
            self._conn.commit()
        return events

    @staticmethod
    def _interaction_event_from_row(row: sqlite3.Row) -> InteractionDomainEvent:
        return InteractionDomainEvent.model_validate(
            {
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "project_id": row["project_id"],
                "session_id": row["session_id"],
                "revision_id": row["revision_id"],
                "intent_seq": row["intent_seq"],
                "aggregate_type": row["aggregate_type"],
                "aggregate_id": row["aggregate_id"],
                "aggregate_version": row["aggregate_version"],
                "correlation_id": row["correlation_id"],
                "causation_id": row["causation_id"],
                "occurred_at": row["occurred_at"],
                "payload": json.loads(row["payload"] or "{}"),
                "event_cursor": row["event_cursor"],
            }
        )

    def _interaction_task_from_row(self, row: sqlite3.Row) -> InteractionTask:
        return InteractionTask.model_validate(
            {
                "task_id": row["task_id"],
                "task_type": row["task_type"],
                "project_id": row["project_id"],
                "session_id": row["session_id"],
                "revision_id": row["revision_id"],
                "status": row["status"],
                "input_json": json.loads(row["input_json"] or "{}"),
                "result_ref": row["result_ref"],
                "progress": row["progress"],
                "attempt": row["attempt"],
                "max_attempts": row["max_attempts"],
                "lease_owner": row["lease_owner"],
                "lease_expires_at": row["lease_expires_at"],
                "idempotency_key": row["idempotency_key"],
                "created_at": row["created_at"],
                "started_at": row["started_at"],
                "completed_at": row["completed_at"],
                "error_code": row["error_code"],
                "error_message": row["error_message"],
                "cancel_requested": bool(row["cancel_requested"]),
                "updated_at": row["updated_at"],
            }
        )

    def save_solution_batch(self, batch: SolutionBatch) -> SolutionBatch:
        batch.updated_at = now_utc()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO solution_batches (
                    batch_id, session_id, intent_seq, payload, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(batch_id) DO UPDATE SET
                    payload = excluded.payload, updated_at = excluded.updated_at
                """,
                (
                    batch.batch_id,
                    batch.session_id,
                    batch.intent_seq,
                    batch.model_dump_json(),
                    batch.created_at.isoformat(),
                    batch.updated_at.isoformat(),
                ),
            )
            self._conn.commit()
        return batch

    def list_solution_batches(self, session_id: str) -> list[SolutionBatch]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload FROM solution_batches WHERE session_id = ? ORDER BY intent_seq",
                (session_id,),
            ).fetchall()
        return [SolutionBatch.model_validate_json(row["payload"]) for row in rows]

    def next_version_number(self, session_id: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(MAX(version_number), 0) + 1 AS number "
                "FROM version_graph_nodes WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return int(row["number"])

    def save_version_node(self, node: VersionGraphNode) -> VersionGraphNode:
        node.updated_at = now_utc()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO version_graph_nodes (
                    node_id, session_id, parent_node_id, candidate_id,
                    version_number, payload, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (
                    node.node_id,
                    node.session_id,
                    node.parent_node_id,
                    node.candidate_id,
                    node.version_number,
                    node.model_dump_json(),
                    node.created_at.isoformat(),
                    node.updated_at.isoformat(),
                ),
            )
            self._conn.commit()
        return node

    def get_version_node(self, node_id: str) -> VersionGraphNode | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM version_graph_nodes WHERE node_id = ?",
                (node_id,),
            ).fetchone()
        return VersionGraphNode.model_validate_json(row["payload"]) if row else None

    def find_version_node(
        self,
        session_id: str,
        parent_node_id: str | None,
        candidate_id: str | None,
    ) -> VersionGraphNode | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT payload FROM version_graph_nodes
                WHERE session_id = ?
                  AND COALESCE(parent_node_id, '') = COALESCE(?, '')
                  AND COALESCE(candidate_id, '') = COALESCE(?, '')
                LIMIT 1
                """,
                (session_id, parent_node_id, candidate_id),
            ).fetchone()
        return VersionGraphNode.model_validate_json(row["payload"]) if row else None

    def list_version_nodes(self, session_id: str) -> list[VersionGraphNode]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload FROM version_graph_nodes "
                "WHERE session_id = ? ORDER BY version_number",
                (session_id,),
            ).fetchall()
        return [VersionGraphNode.model_validate_json(row["payload"]) for row in rows]

    def delete_version_nodes(self, session_id: str, node_ids: set[str]) -> None:
        if not node_ids:
            return
        with self._lock:
            self._conn.executemany(
                "DELETE FROM version_graph_nodes WHERE session_id = ? AND node_id = ?",
                [(session_id, node_id) for node_id in node_ids],
            )
            self._conn.commit()

    def set_active_version_node(self, session_id: str, node_id: str) -> None:
        timestamp = now_utc().isoformat()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO version_graph_states (session_id, active_node_id, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    active_node_id = excluded.active_node_id,
                    updated_at = excluded.updated_at
                """,
                (session_id, node_id, timestamp),
            )
            self._conn.commit()

    def get_version_graph_state(self, session_id: str) -> VersionGraphState:
        with self._lock:
            row = self._conn.execute(
                "SELECT active_node_id FROM version_graph_states WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return VersionGraphState(
            active_node_id=str(row["active_node_id"]) if row and row["active_node_id"] else None,
            nodes=self.list_version_nodes(session_id),
        )

    def record_model_call(
        self,
        *,
        model: str,
        provider: str,
        run_id: str | None = None,
        request_id: str | None = None,
        latency_ms: int | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        error_type: str | None = None,
        **extra: Any,
    ) -> None:
        from uuid import uuid4

        with self._lock:
            self._conn.execute(
                """
                INSERT INTO model_call_audits (
                    audit_id, run_id, model, provider, request_id, latency_ms,
                    prompt_tokens, completion_tokens, error_type, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"audit_{uuid4().hex[:10]}",
                    run_id,
                    model,
                    provider,
                    request_id,
                    latency_ms,
                    prompt_tokens,
                    completion_tokens,
                    error_type,
                    now_utc().isoformat(),
                ),
            )
            self._conn.commit()

    def recent_model_calls(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM model_call_audits ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_generation_job(self, job: dict[str, Any]) -> dict[str, Any]:
        from datetime import UTC, datetime

        now = datetime.now(UTC).isoformat()
        job.setdefault("created_at", now)
        job["updated_at"] = now
        columns = (
            "job_id, run_id, session_id, spec, status, lease_owner, "
            "lease_expires_at, remote_job_id, artifacts, error, created_at, updated_at"
        )
        placeholders = ", ".join(f":{name}" for name in (
            "job_id", "run_id", "session_id", "spec", "status", "lease_owner",
            "lease_expires_at", "remote_job_id", "artifacts", "error",
            "created_at", "updated_at",
        ))
        values = {
            "job_id": job["job_id"],
            "run_id": job.get("run_id"),
            "session_id": job.get("session_id"),
            "spec": json.dumps(job.get("spec") or {}, ensure_ascii=False),
            "status": job.get("status", "queued"),
            "lease_owner": job.get("lease_owner"),
            "lease_expires_at": job.get("lease_expires_at"),
            "remote_job_id": job.get("remote_job_id"),
            "artifacts": json.dumps(job.get("artifacts") or [], ensure_ascii=False),
            "error": json.dumps(job.get("error"), ensure_ascii=False) if job.get("error") else None,
            "created_at": job.get("created_at", now),
            "updated_at": job["updated_at"],
        }
        with self._lock:
            self._conn.execute(
                f"""
                INSERT INTO generation_jobs ({columns})
                VALUES ({placeholders})
                ON CONFLICT(job_id) DO UPDATE SET
                    status = excluded.status,
                    lease_owner = excluded.lease_owner,
                    lease_expires_at = excluded.lease_expires_at,
                    remote_job_id = excluded.remote_job_id,
                    artifacts = excluded.artifacts,
                    error = excluded.error,
                    updated_at = excluded.updated_at
                """,
                values,
            )
            self._conn.commit()
        return self.get_generation_job(job["job_id"]) or job

    def get_generation_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM generation_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return self._job_row(row) if row is not None else None

    def list_generation_jobs(self, run_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if run_id:
                rows = self._conn.execute(
                    "SELECT * FROM generation_jobs WHERE run_id = ? ORDER BY created_at",
                    (run_id,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM generation_jobs ORDER BY created_at"
                ).fetchall()
        return [self._job_row(row) for row in rows]

    def recover_generation_jobs(self) -> int:
        """Re-queue queued/running jobs whose lease is missing or expired."""
        from datetime import UTC, datetime

        now = datetime.now(UTC).isoformat()
        with self._lock:
            cursor = self._conn.execute(
                """
                UPDATE generation_jobs
                SET status = 'queued', lease_owner = NULL, lease_expires_at = NULL,
                    updated_at = ?
                WHERE status IN ('queued', 'running')
                  AND (lease_expires_at IS NULL OR lease_expires_at < ?)
                """,
                (now, now),
            )
            self._conn.commit()
            return cursor.rowcount

    @staticmethod
    def _job_row(row: sqlite3.Row) -> dict[str, Any]:
        job = dict(row)
        job["spec"] = json.loads(job["spec"] or "{}")
        job["artifacts"] = json.loads(job["artifacts"] or "[]")
        job["error"] = json.loads(job["error"]) if job["error"] else None
        return job

    def record_retrieval_feedback(
        self,
        *,
        run_id: str,
        session_id: str,
        prior_ir_id: str | None,
        case_id: str | None,
        action: str,
    ) -> None:
        if action not in {"accepted", "rejected", "undo"}:
            raise ValueError(f"unsupported retrieval feedback action: {action}")
        from uuid import uuid4

        with self._lock:
            self._conn.execute(
                """
                INSERT INTO retrieval_feedback (
                    feedback_id, run_id, session_id, prior_ir_id, case_id,
                    action, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"fb_{uuid4().hex[:10]}",
                    run_id,
                    session_id,
                    prior_ir_id,
                    case_id,
                    action,
                    now_utc().isoformat(),
                ),
            )
            self._conn.commit()

    def retrieval_outcome_score(self, case_id: str, session_id: str) -> float:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT action FROM retrieval_feedback
                WHERE case_id = ? AND session_id = ?
                ORDER BY created_at DESC LIMIT 20
                """,
                (case_id, session_id),
            ).fetchall()
        score = 0.0
        for row in rows:
            if row["action"] == "accepted":
                score += 0.25
            elif row["action"] == "rejected":
                score -= 0.2
        return max(-0.25, min(0.25, score))

    def retrieval_case_accepted(self, case_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT action FROM retrieval_feedback
                WHERE case_id = ? AND action != 'undo'
                ORDER BY created_at DESC LIMIT 1
                """,
                (case_id,),
            ).fetchone()
        return row is not None and row["action"] == "accepted"

    def _row_to_run(self, row: sqlite3.Row) -> FourStageRun:
        payload: dict[str, Any] = {
            "run_id": row["run_id"],
            "session_id": row["session_id"],
            "idempotency_key": row["idempotency_key"],
            "episode_id": row["episode_id"],
            "stage": row["stage"],
            "run_hy3d": bool(row["run_hy3d"]),
            "events": json.loads(row["raw_events"] or "[]"),
            "source_event_ids": json.loads(row["source_event_ids"] or "[]"),
            "source_context": json.loads(row["source_context"] or "null"),
            "generation_artifacts": json.loads(row["generation_artifacts"] or "[]"),
            "error": json.loads(row["error"]) if row["error"] else None,
            "failed_stage": row["failed_stage"],
            "retry_count": row["retry_count"],
            "stage_timestamps": json.loads(row["stage_timestamps"] or "{}"),
            "schema_version": row["schema_version"],
            "completed_at": row["completed_at"] or None,
        }
        for field, column in (
            ("intent_ir", "intent_ir"),
            ("retrieval", "retrieval"),
            ("decision", "decision"),
            ("gate_decision", "gate_decision"),
            ("scope_gate", "scope_gate"),
            ("semantic_divergence", "semantic_divergence"),
            ("divergence_selection", "divergence_selection"),
            ("generation_spec", "generation_spec"),
        ):
            raw = row[column]
            if raw:
                payload[field] = json.loads(raw)
        return FourStageRun.model_validate(payload)

    @staticmethod
    def _dumps(model: Any) -> str | None:
        if model is None:
            return None
        return model.model_dump_json()

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass
