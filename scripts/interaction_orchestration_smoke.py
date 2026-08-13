#!/usr/bin/env python3
"""Bounded smoke test for the durable interaction command boundary.

The check intentionally stops after Gate acknowledgement and projection/event
visibility. It proves that the UI command is fast and durable without waiting
for a remote VLM or GPU generation job.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any
from uuid import uuid4


def request_json(base_url: str, path: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc


def run(base_url: str) -> dict[str, Any]:
    suffix = uuid4().hex[:10]
    _, session = request_json(
        base_url,
        "/api/v1/sessions",
        method="POST",
        payload={"title": f"interaction smoke {suffix}"},
    )
    session_id = str(session["session_id"])
    _, created = request_json(
        base_url,
        f"/api/v1/sessions/{session_id}/intent-revisions",
        method="POST",
        payload={
            "user_text": "make the snowman hat more playful",
            "source_context": {
                "asset_id": f"asset_smoke_{suffix}",
                "object_type": "snowman",
                "source_image_ref": "/files/source.png",
            },
        },
    )
    revision_id = str(created["revision_id"])
    _, snapshot = request_json(
        base_url,
        f"/api/v1/sessions/{session_id}/realtime-observation",
    )
    revision = next(
        item for item in snapshot.get("revisions", []) if item.get("revision_id") == revision_id
    )
    command_id = f"cmd_smoke_{suffix}"
    _, acknowledged = request_json(
        base_url,
        f"/api/v1/intent-revisions/{revision_id}/gate",
        method="POST",
        payload={
            "accepted": True,
            "command_id": command_id,
            "idempotency_key": command_id,
            "expected_version": revision.get("version", 1),
        },
    )
    _, projection = request_json(
        base_url,
        f"/api/v1/sessions/{session_id}/interaction-projection",
    )
    _, events = request_json(
        base_url,
        f"/api/v1/sessions/{session_id}/interaction-events",
    )
    task_types = [item.get("task_type") for item in projection.get("tasks", [])]
    event_types = [item.get("event_type") for item in events.get("events", [])]
    if acknowledged.get("status") != "accepted":
        raise RuntimeError(f"Gate acknowledgement did not accept revision: {acknowledged}")
    if "semantic_divergence" not in task_types:
        raise RuntimeError(f"No durable divergence task in projection: {projection}")
    if not {"GateAccepted", "DivergenceQueued"}.issubset(event_types):
        raise RuntimeError(f"Durable Gate events missing: {event_types}")
    return {
        "session_id": session_id,
        "revision_id": revision_id,
        "ack_status": acknowledged.get("status"),
        "task_types": task_types,
        "event_types": event_types,
        "last_event_cursor": projection.get("last_event_cursor"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="FlowStudio API base URL (default: http://127.0.0.1:8000)",
    )
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.base_url), ensure_ascii=False, indent=2))
    except Exception as exc:  # noqa: BLE001
        print(f"interaction-smoke: FAIL {exc}", file=sys.stderr)
        return 1
    print("interaction-smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
