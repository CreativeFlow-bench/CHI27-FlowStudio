#!/usr/bin/env bash
set -euo pipefail

WORKER_DIR="${CF_WORKER_DIR:-/root/autodl-tmp/data/flowstudio/opt-flowstudio/app/remote_worker}"
IMAGE_DIR="${CF_IMAGE_SERVICE_DIR:-/root/autodl-tmp/flowstudio_restore/20260715_source18119/services/creativeflow_image_service}"
PYTHON_BIN="${CF_SERVICE_PYTHON:-/root/miniconda3/envs/hunyuan3d21/bin/python}"
API_KEY_FILE="${CF_API_KEY_FILE:-/root/.creativeflow_api_v1.key}"
LOG_ROOT="${CF_SERVICE_LOG_ROOT:-/root/autodl-tmp}"

if [[ ! -s "$API_KEY_FILE" ]]; then
  umask 077
  openssl rand -hex 32 > "$API_KEY_FILE"
fi
chmod 600 "$API_KEY_FILE"

start_screen() {
  local name="$1"
  local command="$2"
  screen -S "$name" -X quit >/dev/null 2>&1 || true
  screen -dmS "$name" bash -lc "$command"
}

if [[ -d "$IMAGE_DIR" && -x "$PYTHON_BIN" && -f "$IMAGE_DIR/app_qwen_image.py" ]]; then
  start_screen creativeflow-qwen-image \
    "cd '$IMAGE_DIR'; export CUDA_VISIBLE_DEVICES=0; export QWEN_IMAGE_UNLOAD_AFTER_GENERATE='${QWEN_IMAGE_UNLOAD_AFTER_GENERATE:-1}'; export PYTORCH_CUDA_ALLOC_CONF='${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}'; exec '$PYTHON_BIN' -m uvicorn app_qwen_image:app --host 127.0.0.1 --port 18082 >> '$LOG_ROOT/qwen_image_api_v1.log' 2>&1"
else
  echo "skip Qwen-Image (retired local service)"
fi

start_screen creativeflow-api-v1 \
  "cd '$WORKER_DIR'; export CF_API_KEY=\$(cat '$API_KEY_FILE'); export CF_API_CORS_ORIGINS=http://localhost:3000,http://localhost:5173; exec ./run_api_v1.sh >> '$LOG_ROOT/creativeflow_api_v1.log' 2>&1"

start_screen creativeflow-api-tunnel \
  "cd '$WORKER_DIR'; exec ./run_api_reverse_tunnel.sh >> '$LOG_ROOT/creativeflow_api_tunnel.log' 2>&1"

echo "CreativeFlow collaboration stack started."
echo "Run: $WORKER_DIR/status_collaboration_stack.sh"
