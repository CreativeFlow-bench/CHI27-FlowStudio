#!/usr/bin/env bash
set -euo pipefail

# Run this on the GPU server. It starts the shared FlowStudio cloud API gateway
# and the internal remote worker without depending on a developer laptop.

ROOT_DIR="${FLOWSTUDIO_CLOUD_ROOT:-/root/flowstudio_backend}"
BACKEND_DIR="${FLOWSTUDIO_BACKEND_DIR:-$ROOT_DIR/backend}"
WORKER_DIR="${FLOWSTUDIO_WORKER_DIR:-/root/flowstudio_remote_worker}"
VENV_DIR="${FLOWSTUDIO_BACKEND_VENV:-$ROOT_DIR/.venv}"
WORKER_PYTHON="${FLOWSTUDIO_WORKER_PYTHON:-/root/miniconda3/envs/hunyuan3d21/bin/python}"
BACKEND_HOST="${FLOWSTUDIO_CLOUD_BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${FLOWSTUDIO_CLOUD_BACKEND_PORT:-18000}"
WORKER_HOST="${FLOWSTUDIO_REMOTE_WORKER_HOST:-127.0.0.1}"
WORKER_PORT="${FLOWSTUDIO_REMOTE_WORKER_PORT:-18100}"
VLM_DIR="${FLOWSTUDIO_VLM_DIR:-/root/creativeflow_vlm_service}"
VLM_PORT="${FLOWSTUDIO_VLM_PORT:-18081}"
VLM_START_SCRIPT="${FLOWSTUDIO_VLM_START_SCRIPT:-$VLM_DIR/start_qwen25_vl_service.sh}"
START_VLM="${FLOWSTUDIO_START_VLM:-0}"
VLM_URL="${IUL_VLM_INTENT_URL:-http://127.0.0.1:18081/intent/interpret}"
QWEN_IMAGE_URL="${CF_QWEN_IMAGE_URL:-}"
FRONTEND_DIST="${FLOWSTUDIO_FRONTEND_DIST:-$ROOT_DIR/frontend/dist}"
FRONTEND_HOST="${FLOWSTUDIO_FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${FLOWSTUDIO_FRONTEND_PORT:-5173}"
START_FRONTEND="${FLOWSTUDIO_START_FRONTEND:-1}"
PUBLIC_API_BASE="${FLOWSTUDIO_PUBLIC_API_BASE:-}"
PUBLIC_WS_BASE="${FLOWSTUDIO_PUBLIC_WS_BASE:-}"
LOG_DIR="${FLOWSTUDIO_CLOUD_LOG_DIR:-$ROOT_DIR/logs}"
RESTART="${FLOWSTUDIO_RESTART:-1}"
FLOWSTUDIO_DATA_ROOT="${FLOWSTUDIO_DATA_ROOT:-/root/autodl-tmp/data/flowstudio}"

export FLOWSTUDIO_DATA_ROOT
export SAM3D_ROOT="${SAM3D_ROOT:-/root/SAMPart3D}"
export SAM3D_PYTHON="${SAM3D_PYTHON:-$FLOWSTUDIO_DATA_ROOT/envs/sam3d/bin/python}"
export SAM3D_MODEL="${SAM3D_MODEL:-$FLOWSTUDIO_DATA_ROOT/sam3d/checkpoints}"
export HF_HOME="${HF_HOME:-$FLOWSTUDIO_DATA_ROOT/cache/huggingface}"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-$FLOWSTUDIO_DATA_ROOT/cache/pip}"
export CONDA_PKGS_DIRS="${CONDA_PKGS_DIRS:-$FLOWSTUDIO_DATA_ROOT/cache/conda_pkgs}"

mkdir -p "$LOG_DIR"

if [[ -f /root/.oss_env ]]; then
  # shellcheck disable=SC1091
  set -a
  source /root/.oss_env
  set +a
fi

ensure_backend_env() {
  if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    "$WORKER_PYTHON" -m venv "$VENV_DIR"
  fi
  if ! "$VENV_DIR/bin/python" - <<'PY' >/dev/null 2>&1
import fastapi, pydantic_settings, uvicorn, websockets
PY
  then
    "$VENV_DIR/bin/python" -m pip install \
      'fastapi>=0.115.0' \
      'pydantic-settings>=2.6.0' \
      'python-multipart>=0.0.20' \
      'requests>=2.31.0' \
      'uvicorn>=0.30.0' \
      'websockets>=12.0' \
      'httpx>=0.27.0' \
      'pytest>=8.3.0'
  fi
}

kill_port() {
  local port="$1"
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" >/dev/null 2>&1 || true
  elif command -v lsof >/dev/null 2>&1; then
    lsof -tiTCP:"$port" -sTCP:LISTEN | xargs -r kill || true
  else
    "$VENV_DIR/bin/python" - "$port" <<'PY'
import os
import signal
import sys

port = sys.argv[1]
for name in os.listdir("/proc"):
    if not name.isdigit():
        continue
    try:
        raw = open(f"/proc/{name}/cmdline", "rb").read().decode("utf-8", "ignore")
    except OSError:
        continue
    parts = raw.split("\x00")
    command = " ".join(part for part in parts if part).strip()
    is_uvicorn = (
        any(part.endswith("uvicorn") or part == "uvicorn" for part in parts)
        and ("app:app" in parts or "app.main:app" in parts)
        and "--port" in parts
        and parts[parts.index("--port") + 1 : parts.index("--port") + 2] == [port]
    )
    is_static = "http.server" in parts and port in parts
    if not is_uvicorn and not is_static:
        continue
    try:
        os.kill(int(name), signal.SIGTERM)
    except OSError:
        pass
PY
    sleep 1
  fi
}

wait_for_url() {
  local name="$1"
  local url="$2"
  local seconds="${3:-30}"
  local start
  start="$(date +%s)"
  until curl -fsS --max-time 3 "$url" >/dev/null 2>&1; do
    if (( "$(date +%s)" - start >= seconds )); then
      echo "$name did not become healthy: $url" >&2
      return 1
    fi
    sleep 1
  done
}

ensure_backend_env

if [[ "$RESTART" == "1" ]]; then
  kill_port "$BACKEND_PORT"
  kill_port "$WORKER_PORT"
  if [[ "$START_VLM" == "1" ]]; then
    kill_port "$VLM_PORT"
  fi
  if [[ "$START_FRONTEND" == "1" ]]; then
    kill_port "$FRONTEND_PORT"
  fi
fi

if [[ "$START_VLM" == "1" && -x "$VLM_START_SCRIPT" ]]; then
  if ! curl -fsS --max-time 3 "http://127.0.0.1:$VLM_PORT/health" >/dev/null 2>&1; then
    nohup bash -lc "
      cd '$VLM_DIR' &&
      exec '$VLM_START_SCRIPT'
    " >"$LOG_DIR/qwen25-vl.log" 2>&1 &
  fi
  wait_for_url "Qwen2.5-VL planner" "http://127.0.0.1:$VLM_PORT/health" 180 || {
    echo "Qwen2.5-VL planner is unavailable; backend will use intent fallback." >&2
  }
fi

if ! curl -fsS --max-time 3 "http://$WORKER_HOST:$WORKER_PORT/health" >/dev/null 2>&1; then
  nohup bash -lc "
    cd '$WORKER_DIR' &&
    exec env CF_QWEN_IMAGE_URL='$QWEN_IMAGE_URL' \
      CF_WORKER_PYTHON='$WORKER_PYTHON' \
      CF_HY3D_PYTHON='$WORKER_PYTHON' \
      CF_HY3D_SLOTS_PER_GPU='${CF_HY3D_SLOTS_PER_GPU:-2}' \
      HY21_ROOT='${HY21_ROOT:-/root/Hunyuan3D-2.1}' \
      HY21_MODEL_ROOT='${HY21_MODEL_ROOT:-/root/models}' \
      '$WORKER_PYTHON' -m uvicorn app:app \
      --host '$WORKER_HOST' \
      --port '$WORKER_PORT'
  " >"$LOG_DIR/remote-worker.log" 2>&1 &
fi

wait_for_url "remote worker" "http://$WORKER_HOST:$WORKER_PORT/health" 45

if ! curl -fsS --max-time 3 "http://127.0.0.1:$BACKEND_PORT/health" >/dev/null 2>&1; then
  nohup bash -lc "
    cd '$BACKEND_DIR' &&
    exec env PYTHONPATH='$BACKEND_DIR:$ROOT_DIR' \
      REMOTE_CREATIVEFLOW_WORKER_URL='http://$WORKER_HOST:$WORKER_PORT' \
      REMOTE_CREATIVEFLOW_REAL_JOBS='${REMOTE_CREATIVEFLOW_REAL_JOBS:-1}' \
      REMOTE_CREATIVEFLOW_TRANSFER_VARIANT='${REMOTE_CREATIVEFLOW_TRANSFER_VARIANT:-minimal}' \
      REMOTE_CREATIVEFLOW_AUTO_HY3D='${REMOTE_CREATIVEFLOW_AUTO_HY3D:-0}' \
      IUL_VLM_INTENT_URL='$VLM_URL' \
      IUL_VLM_TIMEOUT_SEC='${IUL_VLM_TIMEOUT_SEC:-60}' \
      '$VENV_DIR/bin/python' -m uvicorn app.main:app \
      --host '$BACKEND_HOST' \
      --port '$BACKEND_PORT'
  " >"$LOG_DIR/cloud-backend.log" 2>&1 &
fi

wait_for_url "cloud backend" "http://127.0.0.1:$BACKEND_PORT/health" 120

if [[ "$START_FRONTEND" == "1" && -d "$FRONTEND_DIST" ]]; then
  # Keep endpoint selection outside the compiled bundle. This is safe to
  # rewrite on every cloud boot and supports provider port mappings/proxies.
  cat >"$FRONTEND_DIST/runtime-config.js" <<EOF
window.__FLOWSTUDIO_API_BASE__ = ${PUBLIC_API_BASE@Q};
window.__FLOWSTUDIO_WS_BASE__ = ${PUBLIC_WS_BASE@Q};
EOF
  if ! curl -fsS --max-time 3 "http://127.0.0.1:$FRONTEND_PORT/" >/dev/null 2>&1; then
    nohup bash -lc "
      cd '$FRONTEND_DIST' &&
      exec '$VENV_DIR/bin/python' -m http.server '$FRONTEND_PORT' --bind '$FRONTEND_HOST'
    " >"$LOG_DIR/frontend-static.log" 2>&1 &
  fi
  wait_for_url "frontend static" "http://127.0.0.1:$FRONTEND_PORT/" 20 || {
    echo "Frontend static preview is unavailable." >&2
  }
fi

echo "FlowStudio cloud services are running."
echo "Backend: http://127.0.0.1:$BACKEND_PORT/health"
echo "Worker:  http://$WORKER_HOST:$WORKER_PORT/health"
if [[ "$START_FRONTEND" == "1" && -d "$FRONTEND_DIST" ]]; then
  echo "Frontend: http://127.0.0.1:$FRONTEND_PORT/"
fi
echo "Logs:    $LOG_DIR"
