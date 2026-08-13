#!/usr/bin/env bash
set -euo pipefail

: "${CF_API_KEY:?CF_API_KEY must be set}"
: "${CF_API_CORS_ORIGINS:=http://localhost:3000,http://localhost:5173}"

export CF_API_KEY
export CF_API_CORS_ORIGINS
export FLOWSTUDIO_WORKER_RUN_ROOT="${FLOWSTUDIO_WORKER_RUN_ROOT:-/root/autodl-tmp/flowstudio_worker_runs}"
export FLOWSTUDIO_WORKER_ASSET_ROOT="${FLOWSTUDIO_WORKER_ASSET_ROOT:-/root/autodl-tmp/flowstudio_worker_assets}"
export CF_QWEN_IMAGE_URL="${CF_QWEN_IMAGE_URL:-http://127.0.0.1:18082/generate}"
export CF_QWEN_CONDITIONED_URL="${CF_QWEN_CONDITIONED_URL:-http://127.0.0.1:18082/generate-conditioned}"
export CF_TEXT_LLM_API_BASE="${CF_TEXT_LLM_API_BASE:-http://127.0.0.1:18084/v1}"
export CF_TEXT_LLM_MODEL="${CF_TEXT_LLM_MODEL:-qwen3-planner}"
export CF_VISION_LLM_API_BASE="${CF_VISION_LLM_API_BASE:-http://127.0.0.1:18084/v1}"
export CF_VISION_LLM_MODEL="${CF_VISION_LLM_MODEL:-qwen3-planner}"
export CF_MODEL_PHASE_SCRIPT="${CF_MODEL_PHASE_SCRIPT:-$(cd "$(dirname "$0")" && pwd)/model_phase.sh}"

exec /root/autodl-tmp/venvs/torch5090/bin/python -m uvicorn app:app \
  --host "${CF_API_HOST:-127.0.0.1}" \
  --port "${CF_API_PORT:-18080}" \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips="${CF_FORWARDED_ALLOW_IPS:-127.0.0.1}"
