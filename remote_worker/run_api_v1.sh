#!/usr/bin/env bash
set -euo pipefail

: "${CF_API_KEY:?CF_API_KEY must be set}"
: "${CF_API_CORS_ORIGINS:=http://localhost:3000,http://localhost:5173}"

export CF_API_KEY
export CF_API_CORS_ORIGINS
export FLOWSTUDIO_WORKER_RUN_ROOT="${FLOWSTUDIO_WORKER_RUN_ROOT:-/root/autodl-tmp/flowstudio_worker_runs}"
export FLOWSTUDIO_WORKER_ASSET_ROOT="${FLOWSTUDIO_WORKER_ASSET_ROOT:-/root/autodl-tmp/flowstudio_worker_assets}"
export CF_MODEL_PHASE_SCRIPT="${CF_MODEL_PHASE_SCRIPT:-$(cd "$(dirname "$0")" && pwd)/model_phase.sh}"

PYTHON_BIN="${CF_WORKER_PYTHON:-${CF_HY3D_PYTHON:-/root/miniconda3/envs/hunyuan3d21/bin/python}}"
exec "$PYTHON_BIN" -m uvicorn app:app \
  --host "${CF_API_HOST:-127.0.0.1}" \
  --port "${CF_API_PORT:-18080}" \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips="${CF_FORWARDED_ALLOW_IPS:-127.0.0.1}"
