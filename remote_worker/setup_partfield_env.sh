#!/usr/bin/env bash
set -euo pipefail

PARTFIELD_ROOT="${PARTFIELD_ROOT:-/root/autodl-tmp/PartField}"
PARTFIELD_ENV="${PARTFIELD_ENV:-/root/autodl-tmp/venvs/partfield}"
PARTFIELD_MODEL="${PARTFIELD_MODEL:-$PARTFIELD_ROOT/model/model_objaverse.ckpt}"
PARTFIELD_REPO="${PARTFIELD_REPO:-https://github.com/nv-tlabs/PartField.git}"
PARTFIELD_TARBALL_URL="${PARTFIELD_TARBALL_URL:-https://codeload.github.com/nv-tlabs/PartField/tar.gz/refs/heads/main}"
PARTFIELD_TARBALL="${PARTFIELD_TARBALL:-/root/autodl-tmp/partfield-main.tgz}"
PARTFIELD_MODEL_URL="${PARTFIELD_MODEL_URL:-https://huggingface.co/mikaelaangel/partfield-ckpt/resolve/main/model_objaverse.ckpt}"
PARTFIELD_MODEL_MIRROR_URL="${PARTFIELD_MODEL_MIRROR_URL:-https://hf-mirror.com/mikaelaangel/partfield-ckpt/resolve/main/model_objaverse.ckpt}"
PARTFIELD_GIT_TIMEOUT_SEC="${PARTFIELD_GIT_TIMEOUT_SEC:-120}"
CONDA_BIN="${CONDA_BIN:-/root/miniconda3/bin/conda}"
PARTFIELD_LOCK_FILE="${PARTFIELD_LOCK_FILE:-$PARTFIELD_ENV.setup.lock}"

mkdir -p "$(dirname "$PARTFIELD_ROOT")" "$(dirname "$PARTFIELD_ENV")"
exec 9>"$PARTFIELD_LOCK_FILE"
if ! flock -n 9; then
  echo "Another PartField setup is already running: $PARTFIELD_LOCK_FILE" >&2
  exit 0
fi

fetch_partfield_source() {
  rm -rf "$PARTFIELD_ROOT"
  if timeout "$PARTFIELD_GIT_TIMEOUT_SEC" git clone "$PARTFIELD_REPO" "$PARTFIELD_ROOT"; then
    return 0
  fi
  echo "git clone failed; falling back to codeload tarball" >&2
  mkdir -p "$(dirname "$PARTFIELD_TARBALL")"
  if command -v wget >/dev/null 2>&1; then
    wget -c -O "$PARTFIELD_TARBALL" "$PARTFIELD_TARBALL_URL"
  else
    curl -L -C - -o "$PARTFIELD_TARBALL" "$PARTFIELD_TARBALL_URL"
  fi
  rm -rf "$(dirname "$PARTFIELD_ROOT")/PartField-main"
  tar -xzf "$PARTFIELD_TARBALL" -C "$(dirname "$PARTFIELD_ROOT")"
  mv "$(dirname "$PARTFIELD_ROOT")/PartField-main" "$PARTFIELD_ROOT"
}

ensure_partfield_source() {
  if [ -f "$PARTFIELD_ROOT/partfield_inference.py" ]; then
    echo "Using existing PartField source at $PARTFIELD_ROOT"
    return 0
  fi
  if [ -d "$PARTFIELD_ROOT/.git" ]; then
    timeout "$PARTFIELD_GIT_TIMEOUT_SEC" git -C "$PARTFIELD_ROOT" pull --ff-only || echo "git pull failed; refetching source" >&2
  fi
  if [ ! -f "$PARTFIELD_ROOT/partfield_inference.py" ]; then
    fetch_partfield_source
  fi
  test -f "$PARTFIELD_ROOT/partfield_inference.py"
}

ensure_partfield_source

ensure_partfield_env() {
  if [ -x "$PARTFIELD_ENV/bin/python" ]; then
    current_version="$("$PARTFIELD_ENV/bin/python" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
    if [ "$current_version" = "3.10" ]; then
      return 0
    fi
    echo "Existing PartField env is Python $current_version; rebuilding with Python 3.10" >&2
    rm -rf "$PARTFIELD_ENV"
  fi
  if [ -x "$CONDA_BIN" ]; then
    "$CONDA_BIN" create -y -p "$PARTFIELD_ENV" python=3.10
  elif command -v python3.10 >/dev/null 2>&1; then
    python3.10 -m venv "$PARTFIELD_ENV"
  else
    echo "Missing Python 3.10 or conda; falling back to python3 venv" >&2
    python3 -m venv "$PARTFIELD_ENV"
  fi
}

ensure_partfield_env

env_version="$("$PARTFIELD_ENV/bin/python" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
if [ "$env_version" != "3.10" ]; then
  echo "Warning: PartField env is Python $env_version, but upstream recommends Python 3.10" >&2
fi

ensure_partfield_source

"$PARTFIELD_ENV/bin/python" -m pip install --upgrade pip setuptools wheel
"$PARTFIELD_ENV/bin/python" -m pip install "setuptools<81"

"$PARTFIELD_ENV/bin/python" -m pip install psutil
"$PARTFIELD_ENV/bin/python" -m pip install \
  torch==2.10.0+cu128 torchvision==0.25.0+cu128 \
  --index-url https://download.pytorch.org/whl/cu128
"$PARTFIELD_ENV/bin/python" -m pip install \
  lightning==2.2 h5py yacs trimesh scikit-image loguru boto3 \
  mesh2sdf tetgen pymeshlab plyfile einops libigl polyscope \
  potpourri3d simple_parsing arrgh open3d vtk scikit-learn matplotlib \
  networkx scipy
# FlowStudio provides a tiny torch_scatter compatibility shim in the worker
# package. Native torch-scatter wheels for the Blackwell/cu128 stack are not
# always available.

mkdir -p "$PARTFIELD_ROOT/model"
if [ ! -s "$PARTFIELD_MODEL" ]; then
  rm -f "$PARTFIELD_MODEL"
  if command -v wget >/dev/null 2>&1; then
    wget -O "$PARTFIELD_MODEL" "$PARTFIELD_MODEL_URL" || {
      rm -f "$PARTFIELD_MODEL"
      wget -O "$PARTFIELD_MODEL" "$PARTFIELD_MODEL_MIRROR_URL"
    }
  else
    curl -L -o "$PARTFIELD_MODEL" "$PARTFIELD_MODEL_URL" || {
      rm -f "$PARTFIELD_MODEL"
      curl -L -o "$PARTFIELD_MODEL" "$PARTFIELD_MODEL_MIRROR_URL"
    }
  fi
fi
test -s "$PARTFIELD_MODEL"

"$PARTFIELD_ENV/bin/python" - <<'PY'
import importlib
for name in ["torch", "lightning", "trimesh", "open3d", "sklearn", "plyfile"]:
    importlib.import_module(name)
print("PARTFIELD_ENV_IMPORT_OK")
PY

echo "PartField ready:"
echo "  root=$PARTFIELD_ROOT"
echo "  python=$PARTFIELD_ENV/bin/python"
echo "  model=$PARTFIELD_MODEL"
