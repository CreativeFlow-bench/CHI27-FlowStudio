from __future__ import annotations

import json
import urllib.request


API_URL = "http://127.0.0.1:18000"


def post(path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        API_URL + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=75) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    session = post("/api/v1/sessions", {"title": "planner smoke"})
    interpretation = post(
        "/api/v1/interaction/interpret",
        {
            "type": "intent_text_changed",
            "event_id": "evt_planner_smoke",
            "session_id": session["session_id"],
            "timestamp": "2026-07-08T00:00:00Z",
            "payload": {
                "text": "make the form softer and propose candidates",
                "intent_text": "make the form softer and propose candidates",
                "signals": {
                    "interaction": {"mode": "chat"},
                    "semantic": {"prompt": "make the form softer and propose candidates"},
                },
            },
        },
    )
    metadata = interpretation.get("predictor_metadata") or {}
    print(
        json.dumps(
            {
                "predictor": interpretation.get("predictor"),
                "mode": metadata.get("mode"),
                "fallback_used": metadata.get("fallback_used"),
                "primary_intent": interpretation.get("primary_intent"),
                "confidence": interpretation.get("confidence"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
