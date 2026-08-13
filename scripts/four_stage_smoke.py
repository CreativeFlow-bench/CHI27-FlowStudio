#!/usr/bin/env python3
"""Live four-stage smoke against a running FlowStudio backend (doc 10.1).

Creates a session, a teapot asset, submits a four-stage run with orbit +
part-select + text events, waits for awaiting_gate, accepts the first option
and prints the full traceability chain. Requires the backend to be running and
Gemini configured (or the backend's rule fallback active).

Usage:
    python3 scripts/four_stage_smoke.py [--base-url http://127.0.0.1:18000]
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request


def _post(url: str, payload: dict, timeout: float = 30) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _get(url: str, timeout: float = 15) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    session = _post(f"{base}/api/v1/sessions", {"title": "four-stage smoke"})
    sid = session["session_id"]
    asset = _post(
        f"{base}/api/v1/assets",
        {"session_id": sid, "object_type": "teapot"},
    )
    events = [
        {
            "type": "orbit",
            "event_id": "smoke_evt_1",
            "session_id": sid,
            "payload": {"asset_id": asset["asset_id"], "viewport_orbit_count": 1},
        },
        {
            "type": "part_select",
            "event_id": "smoke_evt_2",
            "session_id": sid,
            "payload": {"asset_id": asset["asset_id"], "part_id": "lid_knob", "label": "lid knob"},
        },
        {
            "type": "text",
            "event_id": "smoke_evt_3",
            "session_id": sid,
            "payload": {"asset_id": asset["asset_id"], "text": "make the lid knob more organic, 保留 socket"},
        },
    ]
    run = _post(
        f"{base}/api/v1/four-stage/runs",
        {"session_id": sid, "events": events},
        timeout=90,
    )
    print(f"run_id={run['run_id']} stage={run['stage']}")
    ir = run["intent_ir"]
    retrieval = run["retrieval"]
    decision = run["decision"]
    print(
        f"trace ir={ir['ir_id']} operation={ir['intent']['operation']} scope={ir['intent']['scope']}"
    )
    print(
        f"retrieval retriever={retrieval['retriever']} abstained={retrieval['abstained']} "
        f"matches={len(retrieval['matches'])}"
    )
    print(
        f"decision={decision['decision_id']} model={decision['model']} "
        f"options={len(decision['options'])} needs_clarification={decision['needs_clarification']}"
    )
    if not decision["options"]:
        print("no options; backend asked for clarification — smoke ends at gate.")
        return 0
    option_id = decision["options"][0]["option_id"]
    gated = _post(
        f"{base}/api/v1/four-stage/decisions/{decision['decision_id']}/gate",
        {
            "run_id": run["run_id"],
            "action": "accept_option",
            "selected_option_id": option_id,
        },
        timeout=90,
    )
    print(f"after gate stage={gated['stage']}")
    if gated.get("generation_spec"):
        spec = gated["generation_spec"]
        print(
            f"spec generation_id={spec['generation_id']} selected={spec['selected_option_id']} "
            f"candidates={spec['candidate_count']} seeds={spec['seeds']}"
        )
    if gated.get("generation_artifacts"):
        print(f"artifacts={len(gated['generation_artifacts'])}")
    # Wait for the background generation job (real Qwen-Image can take a while).
    current = gated
    for _ in range(120):
        if current["stage"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(5)
        current = _get(f"{base}/api/v1/four-stage/runs/{run['run_id']}")
    artifacts = current.get("generation_artifacts") or []
    print(f"final stage={current['stage']} artifacts={len(artifacts)}")
    for artifact in artifacts[:4]:
        print(f"  - {artifact.get('url')}")
    if current["stage"] == "completed" and artifacts:
        print("FOUR_STAGE_SMOKE_OK")
        return 0
    if current["stage"] == "failed":
        print(f"smoke failed: {(current.get('error') or {}).get('code')}")
        return 1
    print("smoke did not reach completed stage (generation pending/failed).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
