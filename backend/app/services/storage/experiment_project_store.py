"""SQLite/WAL persistence for durable experiment projects and events."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.models import (
    BaselineMode,
    ExperimentEvent,
    ExperimentRun,
    ProjectAssetReference,
    ProjectCreateRequest,
    ProjectDetail,
    ProjectEventCreate,
    ProjectExportRecord,
    ProjectFile,
    ProjectUpdateRequest,
    RecordingStatus,
    now_utc,
)


class ExperimentProjectError(RuntimeError):
    """Base error for project recording."""


class ExperimentProjectNotFound(ExperimentProjectError):
    """Requested project or run does not exist."""


class ExperimentProjectConflict(ExperimentProjectError):
    """Requested lifecycle transition conflicts with persisted state."""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


class ExperimentProjectStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self._path: str | Path = path or ":memory:"
        self._lock = threading.RLock()
        self._conn = self._connect()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        path = str(self._path)
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        if path != ":memory:":
            conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def reopen(self, path: str | Path) -> None:
        with self._lock:
            self._conn.close()
            self._path = path
            self._conn = self._connect()
            self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    participant_code TEXT,
                    condition_label TEXT,
                    notes TEXT,
                    tags_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    active_run_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS experiment_runs (
                    run_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    run_number INTEGER NOT NULL,
                    baseline_mode TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    next_event_seq INTEGER NOT NULL,
                    recording_status TEXT NOT NULL,
                    UNIQUE(project_id, run_number),
                    FOREIGN KEY(project_id) REFERENCES projects(project_id)
                );
                CREATE INDEX IF NOT EXISTS idx_experiment_runs_session
                    ON experiment_runs(session_id, recording_status);
                CREATE TABLE IF NOT EXISTS experiment_events (
                    event_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    occurred_at TEXT,
                    recorded_at TEXT NOT NULL,
                    correlation_id TEXT,
                    parent_event_id TEXT,
                    idempotency_key TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    asset_refs_json TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    UNIQUE(run_id, seq),
                    UNIQUE(run_id, idempotency_key),
                    FOREIGN KEY(project_id) REFERENCES projects(project_id),
                    FOREIGN KEY(run_id) REFERENCES experiment_runs(run_id)
                );
                CREATE INDEX IF NOT EXISTS idx_experiment_events_project
                    ON experiment_events(project_id, run_id, seq);
                CREATE TABLE IF NOT EXISTS project_asset_refs (
                    ref_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    asset_id TEXT,
                    artifact_id TEXT,
                    role TEXT NOT NULL,
                    sha256 TEXT,
                    byte_size INTEGER,
                    mime_type TEXT,
                    storage_key TEXT,
                    source_event_id TEXT,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(project_id),
                    FOREIGN KEY(run_id) REFERENCES experiment_runs(run_id)
                );
                CREATE TABLE IF NOT EXISTS project_exports (
                    export_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    file_url TEXT,
                    file_path TEXT,
                    missing_asset_refs_json TEXT NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(project_id)
                );
                """
            )

    def journal_mode(self) -> str:
        with self._lock:
            return str(self._conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()

    def create_project(self, request: ProjectCreateRequest) -> ProjectDetail:
        project_id = f"proj_{uuid4().hex[:12]}"
        run_id = f"exprun_{uuid4().hex[:12]}"
        timestamp = now_utc()
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._conn.execute(
                    """
                    INSERT INTO projects (
                        project_id, title, participant_code, condition_label, notes,
                        tags_json, status, active_run_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
                    """,
                    (
                        project_id,
                        request.title,
                        request.participant_code,
                        request.condition_label,
                        request.notes,
                        _json(request.tags),
                        run_id,
                        timestamp.isoformat(),
                        timestamp.isoformat(),
                    ),
                )
                self._conn.execute(
                    """
                    INSERT INTO experiment_runs (
                        run_id, project_id, session_id, run_number, baseline_mode,
                        started_at, next_event_seq, recording_status
                    ) VALUES (?, ?, ?, 1, ?, ?, 1, 'healthy')
                    """,
                    (run_id, project_id, request.session_id, request.baseline_mode.value, timestamp.isoformat()),
                )
                bootstrap = [
                    ("project.created", {"title": request.title}),
                    ("run.started", {"run_number": 1, "baseline_mode": request.baseline_mode.value}),
                    ("baseline.captured", request.baseline_snapshot),
                ]
                for index, (event_type, payload) in enumerate(bootstrap, 1):
                    self._insert_event(
                        project_id=project_id,
                        run_id=run_id,
                        session_id=request.session_id,
                        seq=index,
                        event=ProjectEventCreate(
                            event_type=event_type,
                            actor="system",
                            idempotency_key=f"bootstrap:{event_type}",
                            payload=payload,
                        ),
                    )
                self._conn.execute(
                    "UPDATE experiment_runs SET next_event_seq = 4 WHERE run_id = ?", (run_id,)
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        return self.get_project(project_id)

    def append_event(self, run_id: str, event: ProjectEventCreate) -> ExperimentEvent:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                duplicate = self._conn.execute(
                    "SELECT * FROM experiment_events WHERE run_id = ? AND idempotency_key = ?",
                    (run_id, event.idempotency_key),
                ).fetchone()
                if duplicate is not None:
                    self._conn.execute("COMMIT")
                    return self._event_from_row(duplicate)
                run = self._conn.execute(
                    "SELECT * FROM experiment_runs WHERE run_id = ?", (run_id,)
                ).fetchone()
                if run is None:
                    raise ExperimentProjectNotFound(f"run_not_found:{run_id}")
                if run["recording_status"] == RecordingStatus.ended.value:
                    raise ExperimentProjectConflict("run_ended")
                seq = int(run["next_event_seq"])
                created = self._insert_event(
                    project_id=run["project_id"],
                    run_id=run_id,
                    session_id=run["session_id"],
                    seq=seq,
                    event=event,
                )
                self._persist_asset_refs(created)
                self._conn.execute(
                    "UPDATE experiment_runs SET next_event_seq = ? WHERE run_id = ?",
                    (seq + 1, run_id),
                )
                self._conn.execute(
                    "UPDATE projects SET updated_at = ? WHERE project_id = ?",
                    (created.recorded_at.isoformat(), run["project_id"]),
                )
                self._conn.execute("COMMIT")
                return created
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def append_events(self, run_id: str, events: list[ProjectEventCreate]) -> list[ExperimentEvent]:
        return [self.append_event(run_id, event) for event in events]

    def _insert_event(
        self,
        *,
        project_id: str,
        run_id: str,
        session_id: str,
        seq: int,
        event: ProjectEventCreate,
    ) -> ExperimentEvent:
        created = ExperimentEvent(
            event_id=f"expev_{uuid4().hex[:14]}",
            project_id=project_id,
            run_id=run_id,
            session_id=session_id,
            seq=seq,
            event_type=event.event_type,
            actor=event.actor,
            occurred_at=event.occurred_at,
            correlation_id=event.correlation_id,
            parent_event_id=event.parent_event_id,
            idempotency_key=event.idempotency_key,
            payload=event.payload,
            asset_refs=event.asset_refs,
            schema_version=event.schema_version,
        )
        self._conn.execute(
            """
            INSERT INTO experiment_events (
                event_id, project_id, run_id, session_id, seq, event_type, actor,
                occurred_at, recorded_at, correlation_id, parent_event_id,
                idempotency_key, payload_json, asset_refs_json, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created.event_id,
                created.project_id,
                created.run_id,
                created.session_id,
                created.seq,
                created.event_type,
                created.actor,
                created.occurred_at.isoformat() if created.occurred_at else None,
                created.recorded_at.isoformat(),
                created.correlation_id,
                created.parent_event_id,
                created.idempotency_key,
                _json(created.payload),
                _json(created.asset_refs),
                created.schema_version,
            ),
        )
        return created

    def _persist_asset_refs(self, event: ExperimentEvent) -> None:
        for raw in event.asset_refs:
            ref = ProjectAssetReference(
                ref_id=str(raw.get("ref_id") or f"assetref_{uuid4().hex[:14]}"),
                project_id=event.project_id,
                run_id=event.run_id,
                asset_id=raw.get("asset_id"),
                artifact_id=raw.get("artifact_id"),
                role=str(raw.get("role") or "attachment"),
                sha256=raw.get("sha256"),
                byte_size=raw.get("byte_size"),
                mime_type=raw.get("mime_type"),
                storage_key=raw.get("storage_key"),
                source_event_id=event.event_id,
                metadata=raw.get("metadata") or {},
            )
            self._conn.execute(
                """
                INSERT OR IGNORE INTO project_asset_refs (
                    ref_id, project_id, run_id, asset_id, artifact_id, role,
                    sha256, byte_size, mime_type, storage_key, source_event_id,
                    metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ref.ref_id,
                    ref.project_id,
                    ref.run_id,
                    ref.asset_id,
                    ref.artifact_id,
                    ref.role,
                    ref.sha256,
                    ref.byte_size,
                    ref.mime_type,
                    ref.storage_key,
                    ref.source_event_id,
                    _json(ref.metadata),
                    ref.created_at.isoformat(),
                ),
            )

    def list_events(
        self,
        project_id: str,
        *,
        cursor: int = 0,
        limit: int = 500,
    ) -> list[ExperimentEvent]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT e.* FROM experiment_events e
                JOIN experiment_runs r ON r.run_id = e.run_id
                WHERE e.project_id = ?
                ORDER BY r.run_number, e.seq
                LIMIT ? OFFSET ?
                """,
                (project_id, limit, cursor),
            ).fetchall()
        return [self._event_from_row(row) for row in rows]

    def get_project(self, project_id: str) -> ProjectDetail:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM projects WHERE project_id = ?", (project_id,)
            ).fetchone()
            if row is None:
                raise ExperimentProjectNotFound(f"project_not_found:{project_id}")
            run = None
            if row["active_run_id"]:
                run_row = self._conn.execute(
                    "SELECT * FROM experiment_runs WHERE run_id = ?", (row["active_run_id"],)
                ).fetchone()
                run = self._run_from_row(run_row) if run_row else None
            refs = self._conn.execute(
                "SELECT * FROM project_asset_refs WHERE project_id = ? ORDER BY created_at",
                (project_id,),
            ).fetchall()
        return ProjectDetail(
            project=self._project_from_row(row),
            active_run=run,
            asset_refs=[self._asset_ref_from_row(item) for item in refs],
        )

    def list_projects(self, *, include_archived: bool = False) -> list[ProjectDetail]:
        clause = "" if include_archived else "WHERE status != 'archived'"
        with self._lock:
            rows = self._conn.execute(
                f"SELECT project_id FROM projects {clause} ORDER BY updated_at DESC"
            ).fetchall()
        return [self.get_project(row["project_id"]) for row in rows]

    def project_for_session(self, session_id: str) -> ProjectDetail | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT project_id FROM experiment_runs
                WHERE session_id = ? AND recording_status != 'ended'
                ORDER BY started_at DESC LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        return self.get_project(row["project_id"]) if row else None

    def append_system_event(
        self,
        session_id: str,
        event_type: str,
        *,
        actor: str = "system",
        payload: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> ExperimentEvent | None:
        detail = self.project_for_session(session_id)
        if detail is None or detail.active_run is None:
            return None
        return self.append_event(
            detail.active_run.run_id,
            ProjectEventCreate(
                event_type=event_type,
                actor=actor,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key or f"{event_type}:{uuid4().hex}",
                payload=payload or {},
            ),
        )

    def update_project(self, project_id: str, request: ProjectUpdateRequest) -> ProjectFile:
        detail = self.get_project(project_id)
        changes = request.model_dump(exclude_none=True, mode="json")
        if not changes:
            return detail.project
        timestamp = now_utc()
        allowed = {
            "title": "title",
            "participant_code": "participant_code",
            "condition_label": "condition_label",
            "notes": "notes",
            "tags": "tags_json",
            "status": "status",
        }
        assignments: list[str] = []
        values: list[Any] = []
        for key, value in changes.items():
            assignments.append(f"{allowed[key]} = ?")
            values.append(_json(value) if key == "tags" else value)
        assignments.append("updated_at = ?")
        values.extend([timestamp.isoformat(), project_id])
        with self._lock:
            self._conn.execute(
                f"UPDATE projects SET {', '.join(assignments)} WHERE project_id = ?", values
            )
        if detail.active_run is not None:
            self.append_event(
                detail.active_run.run_id,
                ProjectEventCreate(
                    event_type="project.metadata_changed",
                    actor="user",
                    idempotency_key=f"project-metadata:{uuid4().hex}",
                    payload=changes,
                ),
            )
        return self.get_project(project_id).project

    def end_run(self, project_id: str, run_id: str) -> ExperimentRun:
        detail = self.get_project(project_id)
        if detail.active_run is None or detail.active_run.run_id != run_id:
            raise ExperimentProjectConflict("run_not_active")
        self.append_event(
            run_id,
            ProjectEventCreate(
                event_type="run.ended",
                actor="user",
                idempotency_key=f"run-ended:{run_id}",
                payload={"run_number": detail.active_run.run_number},
            ),
        )
        timestamp = now_utc()
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._conn.execute(
                    """
                    UPDATE experiment_runs
                    SET ended_at = ?, recording_status = 'ended'
                    WHERE run_id = ?
                    """,
                    (timestamp.isoformat(), run_id),
                )
                self._conn.execute(
                    "UPDATE projects SET active_run_id = NULL, updated_at = ? WHERE project_id = ?",
                    (timestamp.isoformat(), project_id),
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        return self._run_by_id(run_id)

    def start_run(
        self,
        project_id: str,
        *,
        session_id: str,
        baseline_mode: BaselineMode | str,
        baseline_snapshot: dict[str, Any] | None = None,
    ) -> ExperimentRun:
        detail = self.get_project(project_id)
        if detail.active_run is not None and detail.active_run.recording_status != RecordingStatus.ended:
            raise ExperimentProjectConflict("run_already_active")
        mode = BaselineMode(baseline_mode)
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(MAX(run_number), 0) + 1 FROM experiment_runs WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            run_number = int(row[0])
            run_id = f"exprun_{uuid4().hex[:12]}"
            timestamp = now_utc()
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._conn.execute(
                    """
                    INSERT INTO experiment_runs (
                        run_id, project_id, session_id, run_number, baseline_mode,
                        started_at, next_event_seq, recording_status
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, 'healthy')
                    """,
                    (run_id, project_id, session_id, run_number, mode.value, timestamp.isoformat()),
                )
                self._conn.execute(
                    "UPDATE projects SET active_run_id = ?, updated_at = ? WHERE project_id = ?",
                    (run_id, timestamp.isoformat(), project_id),
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        self.append_event(
            run_id,
            ProjectEventCreate(
                event_type="run.started",
                actor="system",
                idempotency_key="bootstrap:run.started",
                payload={"run_number": run_number, "baseline_mode": mode.value},
            ),
        )
        self.append_event(
            run_id,
            ProjectEventCreate(
                event_type="baseline.captured",
                actor="system",
                idempotency_key="bootstrap:baseline.captured",
                payload=baseline_snapshot or {},
            ),
        )
        return self._run_by_id(run_id)

    def set_recording_status(self, run_id: str, status: RecordingStatus | str) -> ExperimentRun:
        value = RecordingStatus(status).value
        with self._lock:
            result = self._conn.execute(
                "UPDATE experiment_runs SET recording_status = ? WHERE run_id = ?",
                (value, run_id),
            )
            if result.rowcount == 0:
                raise ExperimentProjectNotFound(f"run_not_found:{run_id}")
        return self._run_by_id(run_id)

    def create_export_record(self, record: ProjectExportRecord) -> ProjectExportRecord:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO project_exports (
                    export_id, project_id, status, file_url, file_path,
                    missing_asset_refs_json, error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.export_id,
                    record.project_id,
                    record.status,
                    record.file_url,
                    record.file_path,
                    _json(record.missing_asset_refs),
                    record.error,
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                ),
            )
        return record

    def get_event(self, project_id: str, event_id: str) -> ExperimentEvent:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM experiment_events WHERE project_id = ? AND event_id = ?",
                (project_id, event_id),
            ).fetchone()
        if row is None:
            raise ExperimentProjectNotFound(f"event_not_found:{event_id}")
        return self._event_from_row(row)

    def get_run(self, project_id: str, run_id: str) -> ExperimentRun:
        run = self._run_by_id(run_id)
        if run.project_id != project_id:
            raise ExperimentProjectNotFound(f"run_not_found:{run_id}")
        return run

    def get_export(self, project_id: str, export_id: str) -> ProjectExportRecord:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM project_exports WHERE project_id = ? AND export_id = ?",
                (project_id, export_id),
            ).fetchone()
        if row is None:
            raise ExperimentProjectNotFound(f"export_not_found:{export_id}")
        return self._export_from_row(row)

    def update_export(self, record: ProjectExportRecord) -> ProjectExportRecord:
        record.updated_at = now_utc()
        with self._lock:
            result = self._conn.execute(
                """
                UPDATE project_exports
                SET status = ?, file_url = ?, file_path = ?,
                    missing_asset_refs_json = ?, error = ?, updated_at = ?
                WHERE export_id = ? AND project_id = ?
                """,
                (
                    record.status,
                    record.file_url,
                    record.file_path,
                    _json(record.missing_asset_refs),
                    record.error,
                    record.updated_at.isoformat(),
                    record.export_id,
                    record.project_id,
                ),
            )
        if result.rowcount == 0:
            raise ExperimentProjectNotFound(f"export_not_found:{record.export_id}")
        return record

    def _run_by_id(self, run_id: str) -> ExperimentRun:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM experiment_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise ExperimentProjectNotFound(f"run_not_found:{run_id}")
        return self._run_from_row(row)

    @staticmethod
    def _project_from_row(row: sqlite3.Row) -> ProjectFile:
        return ProjectFile(
            project_id=row["project_id"],
            title=row["title"],
            participant_code=row["participant_code"],
            condition_label=row["condition_label"],
            notes=row["notes"],
            tags=_loads(row["tags_json"], []),
            status=row["status"],
            active_run_id=row["active_run_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _run_from_row(row: sqlite3.Row) -> ExperimentRun:
        return ExperimentRun(
            run_id=row["run_id"],
            project_id=row["project_id"],
            session_id=row["session_id"],
            run_number=row["run_number"],
            baseline_mode=row["baseline_mode"],
            started_at=datetime.fromisoformat(row["started_at"]),
            ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None,
            next_event_seq=row["next_event_seq"],
            recording_status=row["recording_status"],
        )

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> ExperimentEvent:
        return ExperimentEvent(
            event_id=row["event_id"],
            project_id=row["project_id"],
            run_id=row["run_id"],
            session_id=row["session_id"],
            seq=row["seq"],
            event_type=row["event_type"],
            actor=row["actor"],
            occurred_at=datetime.fromisoformat(row["occurred_at"]) if row["occurred_at"] else None,
            recorded_at=datetime.fromisoformat(row["recorded_at"]),
            correlation_id=row["correlation_id"],
            parent_event_id=row["parent_event_id"],
            idempotency_key=row["idempotency_key"],
            payload=_loads(row["payload_json"], {}),
            asset_refs=_loads(row["asset_refs_json"], []),
            schema_version=row["schema_version"],
        )

    @staticmethod
    def _asset_ref_from_row(row: sqlite3.Row) -> ProjectAssetReference:
        return ProjectAssetReference(
            ref_id=row["ref_id"],
            project_id=row["project_id"],
            run_id=row["run_id"],
            asset_id=row["asset_id"],
            artifact_id=row["artifact_id"],
            role=row["role"],
            sha256=row["sha256"],
            byte_size=row["byte_size"],
            mime_type=row["mime_type"],
            storage_key=row["storage_key"],
            source_event_id=row["source_event_id"],
            metadata=_loads(row["metadata_json"], {}),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _export_from_row(row: sqlite3.Row) -> ProjectExportRecord:
        return ProjectExportRecord(
            export_id=row["export_id"],
            project_id=row["project_id"],
            status=row["status"],
            file_url=row["file_url"],
            file_path=row["file_path"],
            missing_asset_refs=_loads(row["missing_asset_refs_json"], []),
            error=row["error"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


__all__ = [
    "ExperimentProjectConflict",
    "ExperimentProjectError",
    "ExperimentProjectNotFound",
    "ExperimentProjectStore",
]
