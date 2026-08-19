#!/usr/bin/env bash
set -euo pipefail

PHASE="${1:-status}"
IMAGE_DIR="${CF_IMAGE_SERVICE_DIR:-/root/creativeflow_image_service}"
IMAGE_PYTHON="${CF_IMAGE_PYTHON:-}"
LOG_ROOT="${CF_SERVICE_LOG_ROOT:-/root/autodl-tmp/flowstudio_logs}"
PLANNER_HEALTH="${CF_PLANNER_HEALTH_URL:-}"
IMAGE_HEALTH="${CF_IMAGE_HEALTH_URL:-}"
IMAGE_UNLOAD="${CF_QWEN_IMAGE_UNLOAD_URL:-}"

mkdir -p "$LOG_ROOT"

http_ok() {
  [[ -n "$1" ]] || return 1
  curl -fsS --max-time 3 "$1" >/dev/null 2>&1
}

planner_pids() {
  pgrep -f "VLLM::EngineCore|start_.*vllm|large.*planner" 2>/dev/null || true
}

image_ready() {
  local body
  body="$(curl -fsS --max-time 3 "$IMAGE_HEALTH" 2>/dev/null)" || return 1
  "$IMAGE_PYTHON" -c \
    'import json,sys; raise SystemExit(0 if json.load(sys.stdin).get("ok") else 1)' \
    <<<"$body"
}

start_image_api() {
  if [[ -z "$IMAGE_PYTHON" || ! -x "$IMAGE_PYTHON" ]]; then
    echo "local Qwen-Image retired; skipped"
    return 0
  fi
  if image_ready; then
    return
  fi
  screen -S creativeflow-qwen-image -X quit >/dev/null 2>&1 || true
  screen -dmS creativeflow-qwen-image bash -lc \
    "cd '$IMAGE_DIR'; export QWEN_IMAGE_UNLOAD_AFTER_GENERATE='${QWEN_IMAGE_UNLOAD_AFTER_GENERATE:-1}'; export PYTORCH_CUDA_ALLOC_CONF='${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}'; exec '$IMAGE_PYTHON' -m uvicorn app_qwen_image:app \
      --host 127.0.0.1 --port 18082 >> '$LOG_ROOT/qwen-image.log' 2>&1"
  for _ in $(seq 1 60); do
    image_ready && return
    sleep 1
  done
  echo "Qwen-Image API did not become healthy" >&2
  return 1
}

unload_image() {
  if ! http_ok "$IMAGE_HEALTH"; then
    return
  fi
  curl -fsS --max-time 60 -X POST "$IMAGE_UNLOAD" >/dev/null
}

stop_planner() {
  local pids
  pids="$(planner_pids)"
  if [ -n "$pids" ]; then
    echo "Force stopping local planner pids: $pids" >&2
    pkill -TERM -f "VLLM::EngineCore|start_.*vllm|large.*planner" >/dev/null 2>&1 || true
    for _ in $(seq 1 30); do
      if [ -z "$(planner_pids)" ]; then
        return
      fi
      sleep 1
    done
    pkill -KILL -f "VLLM::EngineCore|start_.*vllm|large.*planner" >/dev/null 2>&1 || true
  fi
}

start_planner() {
  if [[ -z "$PLANNER_HEALTH" ]]; then
    echo "local planner retired; skipped"
    return 0
  fi
  http_ok "$PLANNER_HEALTH" && return 0
  echo "local planner retired; skipped"
  return 0
}

show_status() {
  if http_ok "$PLANNER_HEALTH"; then
    echo "planner=remote_ready"
    curl -fsS "$PLANNER_HEALTH"
    echo
  else
    echo "planner=remote_unreachable"
  fi
  if http_ok "$IMAGE_HEALTH"; then
    curl -fsS "$IMAGE_HEALTH"
    echo
  else
    echo "image_api=stopped"
  fi
  nvidia-smi --query-compute-apps=pid,process_name,used_memory \
    --format=csv,noheader || true
}

case "$PHASE" in
  planner)
    start_image_api
    unload_image
    start_planner
    ;;
  image)
    stop_planner
    start_image_api
    ;;
  3d)
    stop_planner
    start_image_api
    unload_image
    ;;
  status)
    ;;
  *)
    echo "Usage: $0 {planner|image|3d|status}" >&2
    exit 2
    ;;
esac

show_status
