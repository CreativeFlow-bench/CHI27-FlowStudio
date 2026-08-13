#!/usr/bin/env python3
"""Live four-stage acceptance for the three concrete objects (strategy doc 13).

Drives teapot / snowman / water gun through the full pipeline on a running
backend: events -> IntentIR -> retrieval -> Gemini DecisionIR -> Gate ->
Qwen-Image generation, and reports the traceability chain.

Usage:
    python3 scripts/live_four_stage_acceptance.py [--base-url http://127.0.0.1:18000]
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request


def _opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _post(base: str, path: str, payload: dict, timeout: float = 180) -> dict:
    request = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with _opener().open(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _get(base: str, path: str, timeout: float = 15) -> dict:
    with _opener().open(base + path, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


CASES = [
    (
        "teapot",
        "teapot",
        [
            ("evt_t1", "orbit", {"viewport_orbit_count": 2}),
            ("evt_t2", "part_select", {"part_id": "lid_knob", "label": "lid knob"}),
            ("evt_t3", "text", {"text": "make the lid knob more organic, 保留 socket"}),
        ],
    ),
    (
        "snowman",
        "snowman",
        [
            ("evt_s1", "orbit", {"viewport_orbit_count": 2, "dwell_ms": 1400}),
            (
                "evt_s2",
                "annotation",
                {
                    "part_id": "carrot_nose",
                    "artifact_url": "http://files/nose_ann.png",
                    "bbox": {"x": 1, "y": 1, "w": 2, "h": 3},
                },
            ),
            ("evt_s3", "text", {"text": "make the carrot nose pointier"}),
        ],
    ),
    (
        "water gun",
        "water gun",
        [
            (
                "evt_w1",
                "brush_end",
                {
                    "part_id": "grip",
                    "mask": {"area_ratio": 0.35},
                    "artifact_url": "http://files/grip_mask.png",
                },
            ),
            ("evt_w2", "text", {"text": "more ergonomic grip, 保留扳机结构"}),
        ],
    ),
]


def run_case(base: str, name: str, object_type: str, raw_events) -> int:
    print(f"===== {name} =====")
    session = _post(base, "/api/v1/sessions", {"title": f"four-stage {name}"})
    sid = session["session_id"]
    asset = _post(base, "/api/v1/assets", {"session_id": sid, "object_type": object_type})
    events = [
        {
            "type": etype,
            "event_id": eid,
            "session_id": sid,
            "payload": {**payload, "asset_id": asset["asset_id"]},
        }
        for eid, etype, payload in raw_events
    ]
    started = time.time()
    run = _post(base, "/api/v1/four-stage/runs", {"session_id": sid, "events": events})
    ir, retrieval, decision = run["intent_ir"], run["retrieval"], run["decision"]
    print(
        f"run={run['run_id']} stage={run['stage']} created={round(time.time() - started, 1)}s"
    )
    print(
        f"IR op={ir['intent']['operation']} scope={ir['intent']['scope']} "
        f"object={ir['target'].get('object_type')} encoder={ir['provenance']['encoder']}"
    )
    print(
        f"retrieval matches={len(retrieval['matches'])} "
        f"abstained={retrieval['abstained']}"
    )
    print(
        f"decision model={decision['model']} options={len(decision['options'])} "
        f"clarify={decision['needs_clarification']}"
    )
    if not decision["options"]:
        print("no options -> clarify path; skipping gate")
        return 1
    option = decision["options"][0]
    gated = _post(
        base,
        f"/api/v1/four-stage/decisions/{decision['decision_id']}/gate",
        {
            "run_id": run["run_id"],
            "action": "accept_option",
            "selected_option_id": option["option_id"],
        },
    )
    print(f"after gate stage={gated['stage']}")
    for _ in range(90):
        final = _get(base, f"/api/v1/four-stage/runs/{run['run_id']}")
        if final["stage"] in ("completed", "failed", "cancelled"):
            break
        time.sleep(2)
    artifacts = final.get("generation_artifacts") or []
    print(
        f"final stage={final['stage']} "
        f"error={(final.get('error') or {}).get('code')} "
        f"artifacts={len(artifacts)} total={round(time.time() - started, 1)}s"
    )
    for artifact in artifacts[:4]:
        print(f"  - {artifact.get('url')}")
    return 0 if final["stage"] == "completed" and artifacts else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument("--case", choices=[name for name, _, _ in CASES], default=None)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    cases = [item for item in CASES if args.case is None or item[0] == args.case]
    failed = 0
    for name, object_type, raw_events in cases:
        failed += run_case(base, name, object_type, raw_events)
    print("LIVE_ACCEPTANCE_DONE failures=%d" % failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
