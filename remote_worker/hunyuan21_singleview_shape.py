#!/usr/bin/env python3
"""Generate single-view Hunyuan3D 2.1 geometry without PaintPBR/bpy."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


HY21_ROOT = Path(os.getenv("HY21_ROOT", "/root/Hunyuan3D-2.1"))
HY21_MODEL_ROOT = Path(os.getenv("HY21_MODEL_ROOT", "/root/models"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--shape-steps", type=int, default=int(os.getenv("CF_HY3D_STEPS", "30")))
    parser.add_argument("--octree-resolution", type=int, default=int(os.getenv("CF_HY3D_OCTREE_RESOLUTION", "384")))
    args = parser.parse_args()

    sys.path[:0] = [
        str(HY21_ROOT),
        str(HY21_ROOT / "hy3dshape"),
    ]
    os.chdir(HY21_ROOT)

    import torch
    from PIL import Image
    from hy3dshape.rembg import BackgroundRemover
    from hy3dshape.pipelines import Hunyuan3DDiTFlowMatchingPipeline

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    source_image = Path(args.image).resolve()
    image = Image.open(source_image).convert("RGBA")
    image = BackgroundRemover()(image)

    shape = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
        str(HY21_MODEL_ROOT),
        subfolder="hunyuan3d-dit-v2-1",
        device="cuda",
        dtype=torch.float16,
    )
    mesh = shape(
        image=image,
        num_inference_steps=args.shape_steps,
        octree_resolution=args.octree_resolution,
    )[0]
    glb_path = out_dir / "mesh.glb"
    obj_path = out_dir / "mesh.obj"
    mesh.export(glb_path)
    mesh.export(obj_path)
    result = {
        "schema_version": "creativeflow.hy21-singleview-shape.v1",
        "source_image": str(source_image),
        "mesh_glb": str(glb_path),
        "mesh_obj": str(obj_path),
        "shape_steps": args.shape_steps,
        "octree_resolution": args.octree_resolution,
        "geometry_source": "Hunyuan3D-2.1 single-view shape",
        "pbr_textured": False,
    }
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
