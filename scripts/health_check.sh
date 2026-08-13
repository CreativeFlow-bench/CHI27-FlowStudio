#!/usr/bin/env bash
set -euo pipefail

API_URL="${FLOWSTUDIO_API_URL:-http://127.0.0.1:8000}"
WEB_URL="${FLOWSTUDIO_WEB_URL:-http://127.0.0.1:5173}"
REMOTE_URL="${REMOTE_CREATIVEFLOW_WORKER_URL:-http://127.0.0.1:18100}"

check_json() {
  local name="$1"
  local url="$2"
  local body
  if ! body="$(curl -fsS --max-time 5 "$url" 2>&1)"; then
    echo "$name: FAIL $body"
    return 1
  fi
  echo "$name: OK $body"
}

check_remote_worker() {
  local body
  if ! body="$(curl -fsS --max-time 5 "$REMOTE_URL/health" 2>&1)"; then
    echo "remote-worker: FAIL $body"
    return 1
  fi
  python3 - "$body" <<'PY'
import json
import sys

data = json.loads(sys.argv[1])
pipeline = data.get("creativeflow_pipeline") or {}
summary = {
    "ok": data.get("ok"),
    "legacy_pipeline": pipeline.get("legacy_pipeline_ready", data.get("original_pipeline_exists")),
    "transfer_full": pipeline.get("structured_transfer_ready", data.get("transfer_script_exists")),
    "transfer_minimal": pipeline.get("minimal_transfer_ready", data.get("transfer_minimal_script_exists")),
    "hy3d": pipeline.get("hy3d_ready", data.get("hy3d_script_exists")),
    "segmentation_adapter": data.get("segmentation_adapter"),
    "segmentation_ready": data.get("segmentation_worker_ready") or data.get("sam3d_ready"),
    "sam3d_root": data.get("sam3d_root_exists"),
    "sam3d_python": data.get("sam3d_python_exists"),
    "geometry": data.get("geometry_worker_ready"),
    "render": data.get("render_preview_ready"),
    "legacy_autopartgen_dit": data.get("autopartgen_dit_checkpoint_exists"),
    "legacy_autopartgen_vae": data.get("autopartgen_vae_checkpoint_exists"),
    "jobs": data.get("jobs"),
}
print("remote-worker: OK " + json.dumps(summary, separators=(",", ":")))
PY
}

check_remote_preflight() {
  local body
  if ! body="$(curl -fsS --max-time 12 "$REMOTE_URL/preflight/creativeflow" 2>&1)"; then
    echo "remote-preflight: FAIL $body"
    return 1
  fi
  python3 - "$body" <<'PY'
import json
import sys

data = json.loads(sys.argv[1])
qwen = ((data.get("qwen_image") or {}).get("probe") or {})
kb = data.get("kb_network") or {}
oss = ((data.get("oss") or {}).get("configured_keys") or {})
summary = {
    "ok": data.get("ok"),
    "core_ready": data.get("core_ready"),
    "long_run_ready": data.get("long_run_ready"),
    "qwen": qwen.get("reachable"),
    "qwen_status": qwen.get("status"),
    "kb": {name: probe.get("reachable") for name, probe in kb.items()},
    "oss_keys": f"{sum(1 for value in oss.values() if value)}/{len(oss)}",
    "warnings": len(data.get("warnings") or []),
}
print("remote-preflight: OK " + json.dumps(summary, separators=(",", ":")))
PY
}

check_http() {
  local name="$1"
  local url="$2"
  local code
  code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "$url" || true)"
  if [[ "$code" == "200" ]]; then
    echo "$name: OK HTTP 200"
    return 0
  fi
  echo "$name: FAIL HTTP $code"
  return 1
}

status=0
check_json "backend" "$API_URL/health" || status=1
check_http "frontend" "$WEB_URL" || status=1
check_remote_worker || status=1
check_remote_preflight || status=1

if command -v lsof >/dev/null 2>&1; then
  echo
  echo "Listening ports:"
  lsof -nP -iTCP -sTCP:LISTEN | grep -E '(:8000|:5173|:18100|:18101)' || true
fi

exit "$status"
