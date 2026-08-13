#!/usr/bin/env bash
set -euo pipefail

AUTOPARTGEN_ROOT="${AUTOPARTGEN_ROOT:-/root/autodl-tmp/AutoPartGen}"
AUTOPARTGEN_PYTHON="${AUTOPARTGEN_PYTHON:-/root/autodl-tmp/venvs/autopartgen/bin/python}"
MODEL_REPO="${AUTOPARTGEN_HF_REPO:-facebook/autopartgen}"
CHECKPOINT_DIR="$AUTOPARTGEN_ROOT/checkpoints"

if [[ -z "${HF_TOKEN:-}" ]]; then
  echo "HF_TOKEN is required. Use a read-only Hugging Face token with access to $MODEL_REPO." >&2
  exit 2
fi

if [[ ! -x "$AUTOPARTGEN_PYTHON" ]]; then
  echo "Missing AutoPartGen Python: $AUTOPARTGEN_PYTHON" >&2
  exit 3
fi

mkdir -p "$CHECKPOINT_DIR"

"$AUTOPARTGEN_PYTHON" -m pip install -q -U "huggingface_hub[cli]"
"$AUTOPARTGEN_PYTHON" -m huggingface_hub.commands.huggingface_cli download \
  "$MODEL_REPO" \
  autopartgen_dit.pth autopartgen_vae.pth \
  --local-dir "$CHECKPOINT_DIR" \
  --token "$HF_TOKEN"

test -s "$CHECKPOINT_DIR/autopartgen_dit.pth"
test -s "$CHECKPOINT_DIR/autopartgen_vae.pth"

echo "AutoPartGen checkpoints are ready in $CHECKPOINT_DIR"
