#!/usr/bin/env python3
"""Generate a single-view Hunyuan3D 2.1 mesh and PBR texture package."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


HY21_ROOT = Path(os.getenv("HY21_ROOT", "/root/Hunyuan3D-2.1"))
HY21_MODEL_ROOT = Path(os.getenv("HY21_MODEL_ROOT", "/root/models"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--shape-steps", type=int, default=30)
    parser.add_argument("--octree-resolution", type=int, default=256)
    parser.add_argument("--max-views", type=int, default=6)
    parser.add_argument("--texture-resolution", type=int, default=512)
    parser.add_argument("--reuse-mesh", action="store_true")
    args = parser.parse_args()

    sys.path[:0] = [
        str(HY21_ROOT),
        str(HY21_ROOT / "hy3dshape"),
        str(HY21_ROOT / "hy3dpaint"),
    ]
    os.chdir(HY21_ROOT)

    import huggingface_hub
    import torch
    import torchvision.transforms.functional as torchvision_functional
    # BasicSR still imports the removed torchvision compatibility module.
    sys.modules.setdefault("torchvision.transforms.functional_tensor", torchvision_functional)
    from PIL import Image
    from hy3dshape.rembg import BackgroundRemover
    from hy3dshape.pipelines import Hunyuan3DDiTFlowMatchingPipeline
    from textureGenPipeline import Hunyuan3DPaintConfig, Hunyuan3DPaintPipeline

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    source_image = Path(args.image).resolve()
    image = Image.open(source_image).convert("RGBA")
    image = BackgroundRemover()(image)

    mesh_path = out_dir / "mesh_untextured.glb"
    if not (args.reuse_mesh and mesh_path.exists()):
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
        mesh.export(mesh_path)
        del shape
        torch.cuda.empty_cache()

    original_snapshot_download = huggingface_hub.snapshot_download

    def local_snapshot_download(repo_id: str, *positional, **kwargs):
        if repo_id == str(HY21_MODEL_ROOT):
            return str(HY21_MODEL_ROOT)
        return original_snapshot_download(repo_id, *positional, **kwargs)

    huggingface_hub.snapshot_download = local_snapshot_download
    config = Hunyuan3DPaintConfig(args.max_views, args.texture_resolution)
    config.realesrgan_ckpt_path = str(HY21_ROOT / "hy3dpaint/ckpt/RealESRGAN_x4plus.pth")
    config.multiview_cfg_path = str(HY21_ROOT / "hy3dpaint/cfgs/hunyuan-paint-pbr.yaml")
    config.custom_pipeline = str(HY21_ROOT / "hy3dpaint/hunyuanpaintpbr")
    config.multiview_pretrained_path = str(HY21_MODEL_ROOT)
    config.dino_ckpt_path = str(HY21_MODEL_ROOT / "dinov2-giant")
    paint = Hunyuan3DPaintPipeline(config)
    textured_path = out_dir / "mesh_pbr.glb"
    result_path = paint(
        mesh_path=str(mesh_path),
        image_path=image,
        output_mesh_path=str(textured_path),
        save_glb=True,
    )
    result = {
        "schema_version": "creativeflow.hy21-singleview-pbr.v1",
        "source_image": str(source_image),
        "mesh_untextured": str(mesh_path),
        "mesh_pbr": str(result_path or textured_path),
        "shape_steps": args.shape_steps,
        "octree_resolution": args.octree_resolution,
        "texture_resolution": args.texture_resolution,
        "geometry_source": "Hunyuan3D-2.1 single-view",
        "material_source": "Hunyuan3D-2.1 PaintPBR",
    }
    (out_dir / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
