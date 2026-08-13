#!/usr/bin/env bash
set -euo pipefail

DATA_ROOT="${FLOWSTUDIO_DATA_ROOT:-/root/autodl-tmp/data/flowstudio}"
SAM3D_ROOT="${SAM3D_ROOT:-/root/SAMPart3D}"
SAM3D_ENV="${SAM3D_ENV:-$DATA_ROOT/envs/sam3d}"
SAM3D_CACHE="${SAM3D_CACHE:-$DATA_ROOT/cache/sam3d}"
SAM3D_MODEL="${SAM3D_MODEL:-$DATA_ROOT/sam3d/checkpoints}"
SAM3D_READY_SENTINEL="${SAM3D_READY_SENTINEL:-$SAM3D_MODEL/.flowstudio_ready}"
CONDA_BIN="${CONDA_BIN:-/root/miniconda3/bin/conda}"
PYTHON_VERSION="${PYTHON_VERSION:-3.10}"
INSTALL_HEAVY="${FLOWSTUDIO_SAM3D_INSTALL_HEAVY:-0}"
DOWNLOAD_SAM="${FLOWSTUDIO_SAM3D_DOWNLOAD_SAM:-0}"
SAM_CHECKPOINT="$SAM3D_MODEL/sam_vit_h_4b8939.pth"

mkdir -p "$DATA_ROOT/envs" "$SAM3D_CACHE/pip" "$SAM3D_CACHE/conda_pkgs" "$SAM3D_MODEL"

export CONDA_PKGS_DIRS="$SAM3D_CACHE/conda_pkgs"
export PIP_CACHE_DIR="$SAM3D_CACHE/pip"
export HF_HOME="${HF_HOME:-$SAM3D_CACHE/huggingface}"
export TORCH_HOME="${TORCH_HOME:-$SAM3D_CACHE/torch}"

if [[ ! -x "$SAM3D_ENV/bin/python" ]]; then
  "$CONDA_BIN" create -y -p "$SAM3D_ENV" "python=$PYTHON_VERSION" pip
fi

"$SAM3D_ENV/bin/python" -m pip install --upgrade pip wheel setuptools

if [[ "$INSTALL_HEAVY" == "1" ]]; then
  "$SAM3D_ENV/bin/python" -m pip install \
    torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cu128
  "$SAM3D_ENV/bin/python" -m pip install -r "$SAM3D_ROOT/requirements.txt"
  "$SAM3D_ENV/bin/python" -m pip install spconv-cu120
  "$SAM3D_ENV/bin/python" -m pip install ninja cmake tensorboardX segment-anything OpenEXR
else
  "$SAM3D_ENV/bin/python" -m pip install Pillow numpy scipy trimesh open3d opencv-python segment-anything OpenEXR
fi

if [[ "$DOWNLOAD_SAM" == "1" && ! -s "$SAM_CHECKPOINT" ]]; then
  curl -L --fail --retry 3 --connect-timeout 20 \
    https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth \
    -o "$SAM_CHECKPOINT.tmp"
  mv "$SAM_CHECKPOINT.tmp" "$SAM_CHECKPOINT"
fi

if [[ ! -e "$SAM3D_ROOT/checkpoints" ]]; then
  ln -s "$SAM3D_MODEL" "$SAM3D_ROOT/checkpoints"
fi

cat <<EOF
SAM3D data env prepared.
DATA_ROOT=$DATA_ROOT
SAM3D_ENV=$SAM3D_ENV
SAM3D_MODEL=$SAM3D_MODEL
SAM_CHECKPOINT=$SAM_CHECKPOINT
INSTALL_HEAVY=$INSTALL_HEAVY
DOWNLOAD_SAM=$DOWNLOAD_SAM

Heavy CUDA dependencies are skipped unless FLOWSTUDIO_SAM3D_INSTALL_HEAVY=1.
Place/download ptv3-object.pth under \$SAM3D_MODEL before enabling real segmentation.
Set FLOWSTUDIO_SAM3D_DOWNLOAD_SAM=1 to download the local Segment Anything
checkpoint used by SAMPart3D when HuggingFace is unreachable.
Only create $SAM3D_READY_SENTINEL after flowstudio_sam3d_worker.py --health exits 0.
EOF
