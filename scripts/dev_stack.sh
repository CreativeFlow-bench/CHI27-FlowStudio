#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_HOST="${FLOWSTUDIO_API_HOST:-127.0.0.1}"
API_PORT="${FLOWSTUDIO_API_PORT:-18001}"
WEB_HOST="${FLOWSTUDIO_WEB_HOST:-127.0.0.1}"
WEB_PORT="${FLOWSTUDIO_WEB_PORT:-5184}"
REMOTE_URL="${REMOTE_CREATIVEFLOW_WORKER_URL:-}"
REMOTE_REAL_JOBS="${REMOTE_CREATIVEFLOW_REAL_JOBS:-false}"
REMOTE_TRANSFER_VARIANT="${REMOTE_CREATIVEFLOW_TRANSFER_VARIANT:-minimal}"
REMOTE_AUTO_HY3D="false"
IUL_VLM_URL="${IUL_VLM_INTENT_URL:-}"
IUL_VLM_TIMEOUT="${IUL_VLM_TIMEOUT_SEC:-60}"
ENABLE_LEGACY_MODELS="${ENABLE_LEGACY_LOCAL_MODELS:-false}"
ENABLE_3D="${ENABLE_3D_GENERATION:-false}"
PYTHON_BIN="${FLOWSTUDIO_PYTHON_BIN:-$ROOT_DIR/backend/.venv/bin/python}"

if [[ ! -x "$PYTHON_BIN" && -x "$ROOT_DIR/.flowstudio-run/py312-test-venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.flowstudio-run/py312-test-venv/bin/python"
fi

if [[ "${FLOWSTUDIO_PRINT_CONFIG:-0}" == "1" ]]; then
  echo "backend=http://$API_HOST:$API_PORT"
  echo "frontend=http://$WEB_HOST:$WEB_PORT"
  echo "remote_worker=$REMOTE_URL"
  echo "legacy_models=$ENABLE_LEGACY_MODELS"
  echo "3d_generation=$ENABLE_3D"
  exit 0
fi

cd "$ROOT_DIR"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing a FlowStudio Python environment. Set FLOWSTUDIO_PYTHON_BIN." >&2
  exit 1
fi

if [[ ! -d "frontend/node_modules" ]]; then
  echo "Missing frontend/node_modules. Run npm install in frontend/ first." >&2
  exit 1
fi

mkdir -p .flowstudio-run
API_LOG="$ROOT_DIR/.flowstudio-run/backend.log"
WEB_LOG="$ROOT_DIR/.flowstudio-run/frontend.log"
TUNNEL_LOG="$ROOT_DIR/.flowstudio-run/tunnel.log"
API_PID_FILE="$ROOT_DIR/.flowstudio-run/backend.pid"
WEB_PID_FILE="$ROOT_DIR/.flowstudio-run/frontend.pid"
TUNNEL_PID_FILE="$ROOT_DIR/.flowstudio-run/tunnel.pid"

# Bootstrap white models for local development
if [[ -f "$ROOT_DIR/scripts/fix_white_models.py" ]]; then
  echo "Bootstrapping white models..."
  "$PYTHON_BIN" "$ROOT_DIR/scripts/fix_white_models.py"
fi

cleanup() {
  if [[ "${FLOWSTUDIO_KEEP_RUNNING:-0}" != "1" ]]; then
    [[ -f "$WEB_PID_FILE" ]] && kill "$(cat "$WEB_PID_FILE")" >/dev/null 2>&1 || true
    [[ -f "$API_PID_FILE" ]] && kill "$(cat "$API_PID_FILE")" >/dev/null 2>&1 || true
    [[ -f "$TUNNEL_PID_FILE" ]] && kill "$(cat "$TUNNEL_PID_FILE")" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if [[ "${FLOWSTUDIO_START_TUNNEL:-0}" == "1" ]]; then
  if [[ -z "${FLOWSTUDIO_REMOTE_PASSWORD:-}" ]]; then
    echo "FLOWSTUDIO_START_TUNNEL=1 requires FLOWSTUDIO_REMOTE_PASSWORD." >&2
    exit 1
  fi
  REMOTE_URL="${REMOTE_CREATIVEFLOW_WORKER_URL:-http://127.0.0.1:18101}"
  echo "Starting remote tunnel on http://127.0.0.1:18101"
  FLOWSTUDIO_REMOTE_PASSWORD="$FLOWSTUDIO_REMOTE_PASSWORD" \
    scripts/start_remote_tunnel.expect >"$TUNNEL_LOG" 2>&1 &
  echo "$!" >"$TUNNEL_PID_FILE"
fi

echo "Starting FlowStudio backend on http://$API_HOST:$API_PORT"
REMOTE_CREATIVEFLOW_WORKER_URL="$REMOTE_URL" \
REMOTE_CREATIVEFLOW_REAL_JOBS="$REMOTE_REAL_JOBS" \
REMOTE_CREATIVEFLOW_TRANSFER_VARIANT="$REMOTE_TRANSFER_VARIANT" \
REMOTE_CREATIVEFLOW_AUTO_HY3D="$REMOTE_AUTO_HY3D" \
IUL_VLM_INTENT_URL="$IUL_VLM_URL" \
IUL_VLM_TIMEOUT_SEC="$IUL_VLM_TIMEOUT" \
ENABLE_LEGACY_LOCAL_MODELS="$ENABLE_LEGACY_MODELS" \
ENABLE_3D_GENERATION="$ENABLE_3D" \
SYSTEM_SERVICES_AUTO_BOOTSTRAP=0 \
FLOWSTUDIO_SERVICE_BACKEND_URL="http://$API_HOST:$API_PORT/health" \
PYTHONPATH="$ROOT_DIR/backend" \
  "$PYTHON_BIN" -m uvicorn app.main:app \
  --host "$API_HOST" --port "$API_PORT" >"$API_LOG" 2>&1 &
echo "$!" >"$API_PID_FILE"

echo "Starting FlowStudio frontend on http://$WEB_HOST:$WEB_PORT"
(
  cd frontend
  VITE_API_BASE="http://$API_HOST:$API_PORT" \
  VITE_WS_BASE="ws://$API_HOST:$API_PORT" \
  npm run dev -- --host "$WEB_HOST" --port "$WEB_PORT"
) >"$WEB_LOG" 2>&1 &
echo "$!" >"$WEB_PID_FILE"

echo "Backend log: $API_LOG"
echo "Frontend log: $WEB_LOG"
if [[ "${FLOWSTUDIO_START_TUNNEL:-0}" == "1" ]]; then
  echo "Tunnel log: $TUNNEL_LOG"
fi
echo "Remote worker URL: $REMOTE_URL"
echo "Real CreativeFlow jobs: $REMOTE_REAL_JOBS"
echo "Auto Hy3D: $REMOTE_AUTO_HY3D"
echo "IUL VLM URL: $IUL_VLM_URL"
echo "Legacy local models: $ENABLE_LEGACY_MODELS"
echo "3D generation: $ENABLE_3D"
echo
echo "Open: http://$WEB_HOST:$WEB_PORT"
echo "Press Ctrl-C to stop, or run with FLOWSTUDIO_KEEP_RUNNING=1 to leave processes running."

wait
