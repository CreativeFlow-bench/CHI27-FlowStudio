"""Experiment project lifecycle, append-only events, and portable exports."""

from __future__ import annotations

import hashlib
import json
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query

from app.models import (
    ExperimentEvent,
    ExperimentRun,
    ProjectCreateRequest,
    ProjectDetail,
    ProjectEventBatchRequest,
    ProjectEventCreate,
    ProjectEventExclusionRequest,
    ProjectEventPage,
    ProjectExportRecord,
    ProjectFile,
    ProjectRunCreateRequest,
    ProjectUpdateRequest,
)
from app.services.storage.experiment_project_store import (
    ExperimentProjectConflict,
    ExperimentProjectNotFound,
    ExperimentProjectStore,
)

BROWSER_EVENT_TYPES = {
    "input.text_snapshot",
    "input.asset_uploaded",
    "input.reference_added",
    "input.selection_changed",
    "behavior.undo",
    "behavior.redo",
    "gate.answered",
    "divergence.parameters_changed",
    "divergence.selection_changed",
    "generation.requested",
    "candidate.selected",
    "candidate.accepted",
    "candidate.rejected",
    "candidate.added_to_canvas",
    "version.retry_requested",
}
SECRET_KEYS = {"authorization", "cookie", "api_key", "apikey", "token", "password"}


def _clean_client_value(value: Any) -> Any:
    if isinstance(value, dict):
        for key in value:
            if key.lower() in SECRET_KEYS:
                raise HTTPException(status_code=422, detail=f"secret_field_forbidden:{key}")
        return {key: _clean_client_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean_client_value(item) for item in value]
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        parts = urlsplit(value)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    return value


def _translate_error(error: Exception) -> HTTPException:
    if isinstance(error, ExperimentProjectNotFound):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, ExperimentProjectConflict):
        return HTTPException(status_code=409, detail=str(error))
    raise error


def _safe_asset_path(files_root: Path, storage_key: str) -> Path | None:
    root = files_root.resolve()
    candidate = (root / storage_key).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str).encode("utf-8")


def create_projects_router(
    *,
    store: ExperimentProjectStore,
    require_session: Callable[[str], Any],
    files_root: str | Path,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/projects", tags=["experiment-projects"])
    root = Path(files_root)

    @router.post("", response_model=ProjectDetail)
    def create_project(request: ProjectCreateRequest) -> ProjectDetail:
        require_session(request.session_id)
        return store.create_project(request)

    @router.get("", response_model=list[ProjectDetail])
    def list_projects(include_archived: bool = False) -> list[ProjectDetail]:
        return store.list_projects(include_archived=include_archived)

    @router.get("/{project_id}", response_model=ProjectDetail)
    def get_project(project_id: str) -> ProjectDetail:
        try:
            return store.get_project(project_id)
        except (ExperimentProjectNotFound, ExperimentProjectConflict) as error:
            raise _translate_error(error) from error

    @router.patch("/{project_id}", response_model=ProjectFile)
    def update_project(project_id: str, request: ProjectUpdateRequest) -> ProjectFile:
        try:
            return store.update_project(project_id, request)
        except (ExperimentProjectNotFound, ExperimentProjectConflict) as error:
            raise _translate_error(error) from error

    @router.post("/{project_id}/runs", response_model=ExperimentRun)
    def start_run(project_id: str, request: ProjectRunCreateRequest) -> ExperimentRun:
        require_session(request.session_id)
        try:
            return store.start_run(
                project_id,
                session_id=request.session_id,
                baseline_mode=request.baseline_mode,
                baseline_snapshot=request.baseline_snapshot,
            )
        except (ExperimentProjectNotFound, ExperimentProjectConflict) as error:
            raise _translate_error(error) from error

    @router.post("/{project_id}/runs/{run_id}/end", response_model=ExperimentRun)
    def end_run(project_id: str, run_id: str) -> ExperimentRun:
        try:
            return store.end_run(project_id, run_id)
        except (ExperimentProjectNotFound, ExperimentProjectConflict) as error:
            raise _translate_error(error) from error

    @router.get("/{project_id}/events", response_model=ProjectEventPage)
    def list_events(
        project_id: str,
        cursor: int = Query(default=0, ge=0),
        limit: int = Query(default=500, ge=1, le=500),
    ) -> ProjectEventPage:
        try:
            store.get_project(project_id)
            items = store.list_events(project_id, cursor=cursor, limit=limit + 1)
        except (ExperimentProjectNotFound, ExperimentProjectConflict) as error:
            raise _translate_error(error) from error
        has_more = len(items) > limit
        return ProjectEventPage(
            items=items[:limit],
            next_cursor=cursor + limit if has_more else None,
        )

    @router.post("/{project_id}/runs/{run_id}/events:batch", response_model=list[ExperimentEvent])
    def append_browser_events(
        project_id: str,
        run_id: str,
        request: ProjectEventBatchRequest,
    ) -> list[ExperimentEvent]:
        try:
            run = store.get_run(project_id, run_id)
            if run.recording_status.value == "ended":
                raise ExperimentProjectConflict("run_ended")
            detail = store.get_project(project_id)
            if detail.active_run is None or detail.active_run.run_id != run_id:
                raise ExperimentProjectConflict("run_not_active")
            cleaned: list[ProjectEventCreate] = []
            for event in request.events:
                if event.event_type not in BROWSER_EVENT_TYPES or event.actor != "user":
                    raise HTTPException(status_code=422, detail="browser_event_not_allowed")
                cleaned.append(
                    event.model_copy(
                        update={
                            "payload": _clean_client_value(event.payload),
                            "asset_refs": _clean_client_value(event.asset_refs),
                        }
                    )
                )
            return store.append_events(run_id, cleaned)
        except (ExperimentProjectNotFound, ExperimentProjectConflict) as error:
            raise _translate_error(error) from error

    @router.post("/{project_id}/events/{event_id}/exclude", response_model=ExperimentEvent)
    def exclude_event(
        project_id: str,
        event_id: str,
        request: ProjectEventExclusionRequest,
    ) -> ExperimentEvent:
        try:
            source = store.get_event(project_id, event_id)
            return store.append_event(
                source.run_id,
                ProjectEventCreate(
                    event_type="event.excluded",
                    actor="user",
                    parent_event_id=source.event_id,
                    idempotency_key=f"exclude:{source.event_id}:{uuid4().hex}",
                    payload={"reason": request.reason, "excluded_event_id": source.event_id},
                ),
            )
        except (ExperimentProjectNotFound, ExperimentProjectConflict) as error:
            raise _translate_error(error) from error

    @router.post("/{project_id}/export", response_model=ProjectExportRecord)
    def export_project(project_id: str) -> ProjectExportRecord:
        try:
            detail = store.get_project(project_id)
            events = store.list_events(project_id, limit=1_000_000)
        except (ExperimentProjectNotFound, ExperimentProjectConflict) as error:
            raise _translate_error(error) from error

        export_id = f"export_{uuid4().hex[:12]}"
        record = store.create_export_record(
            ProjectExportRecord(export_id=export_id, project_id=project_id)
        )
        export_dir = root / "project_exports" / project_id
        export_dir.mkdir(parents=True, exist_ok=True)
        archive = export_dir / f"{export_id}.zip"
        missing: list[str] = []
        asset_entries: list[tuple[str, Path]] = []
        checksums: dict[str, str] = {}
        used_names: set[str] = set()
        for ref in detail.asset_refs:
            if not ref.storage_key:
                missing.append(ref.ref_id)
                continue
            source = _safe_asset_path(root, ref.storage_key)
            if source is None or not source.is_file():
                missing.append(ref.ref_id)
                continue
            name = source.name
            if name in used_names:
                name = f"{ref.ref_id}-{name}"
            used_names.add(name)
            arcname = f"assets/{name}"
            asset_entries.append((arcname, source))
            checksums[arcname] = hashlib.sha256(source.read_bytes()).hexdigest()

        manifest = {
            "schema_version": "flowstudio.experiment-export.v1",
            "project_id": project_id,
            "export_id": export_id,
            "complete": not missing,
            "missing_asset_refs": missing,
            "assets": [name for name, _ in asset_entries],
        }
        projection = detail.model_dump(mode="json")
        event_lines = b"\n".join(_json_bytes(event.model_dump(mode="json")) for event in events) + b"\n"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr("manifest.json", _json_bytes(manifest))
            bundle.writestr("events.jsonl", event_lines)
            bundle.writestr("projection.json", _json_bytes(projection))
            bundle.writestr("checksums.json", _json_bytes(checksums))
            for arcname, source in asset_entries:
                bundle.write(source, arcname)

        record.status = "completed"
        record.file_path = str(archive)
        record.file_url = f"/files/project_exports/{project_id}/{archive.name}"
        record.missing_asset_refs = missing
        return store.update_export(record)

    @router.get("/{project_id}/exports/{export_id}", response_model=ProjectExportRecord)
    def get_export(project_id: str, export_id: str) -> ProjectExportRecord:
        try:
            return store.get_export(project_id, export_id)
        except (ExperimentProjectNotFound, ExperimentProjectConflict) as error:
            raise _translate_error(error) from error

    return router


__all__ = ["BROWSER_EVENT_TYPES", "create_projects_router"]
