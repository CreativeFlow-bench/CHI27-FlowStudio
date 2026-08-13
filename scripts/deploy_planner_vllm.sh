#!/usr/bin/env bash
# Deploy the Qwen3 planner as an OpenAI-compatible vLLM service on port 18084.
#
# Strategy doc: the planner must run on the new GPU instance at
# 127.0.0.1:18084 (qwen3.5-27b per backend/.env). vLLM is NOT installed yet and
# CUDA 13.0 / Blackwell (RTX PRO 6000) compatibility must be verified first.
#
# Usage (run ON the server):
#   PLANNER_MODEL=Qwen/Qwen3-8B bash scripts/deploy_planner_vllm.sh
#   PLANNER_MODEL=<your-model-id> bash scripts/deploy_planner_vllm.sh
set -euo pipefail

MODEL="${PLANNER_MODEL:-Qwen/Qwen3-8B}"
PORT="${PLANNER_PORT:-18084}"
VENV_DIR="${PLANNER_VENV:-/root/autodl-tmp/venvs/planner}"
MODEL_DIR="/root/autodl-tmp/data/flowstudio/models"
LOG_DIR="${LOG_DIR:-/root/flowstudio_app/logs}"

echo "== planner deploy =="
echo "model=$MODEL port=$PORT venv=$VENV_DIR"
mkdir -p "$VENV_DIR" "$MODEL_DIR" "$LOG_DIR"

if [ ! -x "$VENV_DIR/bin/python" ]; then
  python3 -m venv "$VENV_DIR"
fi

# Blackwell (sm_120) + CUDA 13.0: pin a recent vLLM; verify it imports first.
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install "vllm>=0.8" "modelscope"

# Download weights (Modelscope mirror preferred on AutoDL).
if [ ! -d "$MODEL_DIR/$(basename "$MODEL")" ]; then
  "$VENV_DIR/bin/modelscope" download --model "$MODEL" --local_dir "$MODEL_DIR/$(basename "$MODEL")"
fi

# Import sanity check (CUDA/Blackwell compatibility gate).
"$VENV_DIR/bin/python" -c "import vllm; print('vllm', vllm.__version__)"

nohup "$VENV_DIR/bin/python" -m vllm.entrypoints.openai.api_server \
  --model "$MODEL_DIR/$(basename "$MODEL")" \
  --served-model-name qwen3-planner \
  --port "$PORT" \
  --host 127.0.0.1 \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.35 \
  > "$LOG_DIR/planner-vllm.log" 2>&1 &
disown

echo "planner starting; log=$LOG_DIR/planner-vllm.log"
echo "verify: curl http://127.0.0.1:$PORT/v1/models"
