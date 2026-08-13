"""HTTP acceptance tests for experiment project lifecycle and export."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.projects import create_projects_router
from app.models import SessionCreateRequest
from app.services.storage.experiment_project_store import ExperimentProjectStore
from app.services.storage.studio_store import InMemoryStudioStore


@pytest.fixture
def project_api(tmp_path: Path):
    studio = InMemoryStudioStore()
    store = ExperimentProjectStore(tmp_path / "projects.sqlite3")
    files_root = tmp_path / "files"
    files_root.mkdir()

    def require_session(session_id: str):
        session = studio.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
        return session

    app = FastAPI()
    app.include_router(
        create_projects_router(
            store=store,
            require_session=require_session,
            files_root=files_root,
        )
    )
    return TestClient(app), studio, store, files_root


def _session(studio: InMemoryStudioStore, title: str = "Temporary") -> str:
    return studio.create_session(SessionCreateRequest(title=title)).session_id


def _create_project(client: TestClient, studio: InMemoryStudioStore) -> dict:
    session_id = _session(studio)
    response = client.post(
        "/api/v1/projects",
        json={
            "title": "Participant P07",
            "participant_code": "P07",
            "condition_label": "A",
            "session_id": session_id,
            "baseline_mode": "current_state",
            "baseline_snapshot": {
                "active_asset_id": None,
                "version_graph": {"active_node_id": None, "nodes": []},
            },
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_temporary_session_can_become_a_recorded_project(project_api) -> None:
    client, studio, _, _ = project_api
    created = _create_project(client, studio)
    project_id = created["project"]["project_id"]

    events = client.get(f"/api/v1/projects/{project_id}/events")

    assert events.status_code == 200
    assert [item["event_type"] for item in events.json()["items"]] == [
        "project.created",
        "run.started",
        "baseline.captured",
    ]
    assert events.json()["items"][2]["payload"]["version_graph"]["nodes"] == []


def test_browser_event_batch_is_whitelisted_idempotent_and_sanitized(project_api) -> None:
    client, studio, _, _ = project_api
    created = _create_project(client, studio)
    project_id = created["project"]["project_id"]
    run_id = created["active_run"]["run_id"]
    payload = {
        "events": [
            {
                "event_type": "input.asset_uploaded",
                "actor": "user",
                "idempotency_key": "asset-1",
                "payload": {
                    "asset_id": "asset_1",
                    "url": "https://oss.example/model.glb?signature=secret",
                },
                "asset_refs": [
                    {
                        "asset_id": "asset_1",
                        "role": "source_model",
                        "storage_key": "projects/source/model.glb",
                        "sha256": "a" * 64,
                    }
                ],
            }
        ]
    }

    first = client.post(f"/api/v1/projects/{project_id}/runs/{run_id}/events:batch", json=payload)
    duplicate = client.post(f"/api/v1/projects/{project_id}/runs/{run_id}/events:batch", json=payload)
    forbidden = client.post(
        f"/api/v1/projects/{project_id}/runs/{run_id}/events:batch",
        json={
            "events": [
                {
                    "event_type": "model.raw_output_recorded",
                    "actor": "model",
                    "idempotency_key": "spoofed-model",
                    "payload": {"authorization": "Bearer secret"},
                }
            ]
        },
    )

    assert first.status_code == 200
    assert duplicate.status_code == 200
    assert first.json()[0]["event_id"] == duplicate.json()[0]["event_id"]
    assert first.json()[0]["payload"]["url"] == "https://oss.example/model.glb"
    assert forbidden.status_code == 422


def test_exclusion_appends_and_ended_run_rejects_new_events(project_api) -> None:
    client, studio, _, _ = project_api
    created = _create_project(client, studio)
    project_id = created["project"]["project_id"]
    run_id = created["active_run"]["run_id"]
    recorded = client.post(
        f"/api/v1/projects/{project_id}/runs/{run_id}/events:batch",
        json={
            "events": [
                {
                    "event_type": "input.text_snapshot",
                    "actor": "user",
                    "idempotency_key": "text-1",
                    "payload": {"text": "wrong prompt"},
                }
            ]
        },
    ).json()[0]

    excluded = client.post(
        f"/api/v1/projects/{project_id}/events/{recorded['event_id']}/exclude",
        json={"reason": "participant correction"},
    )
    ended = client.post(f"/api/v1/projects/{project_id}/runs/{run_id}/end")
    late = client.post(
        f"/api/v1/projects/{project_id}/runs/{run_id}/events:batch",
        json={
            "events": [
                {
                    "event_type": "input.text_snapshot",
                    "actor": "user",
                    "idempotency_key": "late",
                    "payload": {"text": "too late"},
                }
            ]
        },
    )

    assert excluded.status_code == 200
    assert excluded.json()["parent_event_id"] == recorded["event_id"]
    assert ended.status_code == 200
    assert ended.json()["recording_status"] == "ended"
    assert late.status_code == 409
    assert late.json()["detail"] == "run_ended"


def test_session_reset_does_not_remove_project_events(project_api) -> None:
    client, studio, store, _ = project_api
    created = _create_project(client, studio)
    project_id = created["project"]["project_id"]
    session_id = created["active_run"]["session_id"]

    studio.reset_session_workspace(session_id)

    assert len(store.list_events(project_id)) == 3


def test_export_contains_manifest_events_projection_checksums_and_assets(project_api) -> None:
    client, studio, _, files_root = project_api
    created = _create_project(client, studio)
    project_id = created["project"]["project_id"]
    run_id = created["active_run"]["run_id"]
    source = files_root / "source.glb"
    source.write_bytes(b"glTF-test")
    event = client.post(
        f"/api/v1/projects/{project_id}/runs/{run_id}/events:batch",
        json={
            "events": [
                {
                    "event_type": "input.asset_uploaded",
                    "actor": "user",
                    "idempotency_key": "asset-export-1",
                    "payload": {"asset_id": "asset_export"},
                    "asset_refs": [
                        {
                            "asset_id": "asset_export",
                            "role": "source_model",
                            "storage_key": "source.glb",
                        }
                    ],
                }
            ]
        },
    )
    assert event.status_code == 200, event.text

    exported = client.post(f"/api/v1/projects/{project_id}/export")

    assert exported.status_code == 200, exported.text
    assert exported.json()["status"] == "completed"
    archive = Path(exported.json()["file_path"])
    assert archive.exists()
    with zipfile.ZipFile(archive) as bundle:
        assert set(bundle.namelist()) == {
            "manifest.json",
            "events.jsonl",
            "projection.json",
            "checksums.json",
            "assets/source.glb",
        }
        manifest = json.loads(bundle.read("manifest.json"))
        checksums = json.loads(bundle.read("checksums.json"))
        assert manifest["complete"] is True
        assert checksums["assets/source.glb"]
