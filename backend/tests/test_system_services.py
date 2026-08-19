"""Unit tests for the runtime service inventory."""

from __future__ import annotations

import asyncio
import os
import signal
import socket
import sys
import tempfile
from pathlib import Path

from app.services import system_services


def test_definitions_cover_expected_services() -> None:
    system_services.configure_runtime(enable_legacy_models=False, enable_3d=False)
    definitions = system_services._definitions()
    ids = {item["id"] for item in definitions}
    assert {"backend", "frontend"}.issubset(ids)
    assert {
        "remote_worker",
        "creativeflow_api",
        "qwen_image",
        "planner_llm",
        "intent_vlm",
    }.isdisjoint(ids)
    by_id = {item["id"]: item for item in definitions}
    # The backend is never self-startable.
    assert by_id["backend"]["startable"] is False


def test_rollback_inventory_requires_explicit_runtime_flags() -> None:
    system_services.configure_runtime(enable_legacy_models=True, enable_3d=True)
    try:
        ids = {item["id"] for item in system_services._definitions()}
        assert "qwen_image" in ids
        assert {"planner_llm", "intent_vlm"}.isdisjoint(ids)
        assert {"remote_worker", "creativeflow_api"}.issubset(ids)
    finally:
        system_services.configure_runtime(enable_legacy_models=False, enable_3d=False)


def test_probe_all_returns_statuses() -> None:
    results = asyncio.run(system_services.probe_all())
    assert len(results) == len(system_services._definitions())
    for item in results:
        assert item["state"] in {"up", "down", "starting", "unknown"}
        assert "detail" in item
        assert "startable" in item


def test_start_unknown_service_returns_error() -> None:
    result = asyncio.run(system_services.start_service("does_not_exist"))
    assert result["ok"] is False
    assert "unknown service" in result["error"]


def test_start_service_brings_local_http_server_up() -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    fake_id = "fake_local_http"
    definition = {
        "id": fake_id,
        "name": "Fake HTTP",
        "name_zh": "测试服务",
        "port": port,
        "group": "core",
        "required": False,
        "description": "local start flow test",
        "health_url": f"http://127.0.0.1:{port}/",
        "start": {
            "cwd": tempfile.gettempdir(),
            "cmd": [
                sys.executable,
                "-m",
                "http.server",
                str(port),
                "--bind",
                "127.0.0.1",
            ],
        },
        "start_timeout_sec": 20,
    }
    system_services._SERVICE_DEFS.append(definition)
    try:
        result = asyncio.run(system_services.start_service(fake_id))
        assert result["ok"] is True
        assert result.get("state") == "up"
        status = asyncio.run(system_services.probe_one(fake_id))
        assert status["state"] == "up"
    finally:
        pid = (system_services._START_RESULTS.get(fake_id) or {}).get("pid")
        if pid:
            try:
                os.kill(int(pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
        system_services._SERVICE_DEFS.remove(definition)
        system_services._START_RESULTS.pop(fake_id, None)
