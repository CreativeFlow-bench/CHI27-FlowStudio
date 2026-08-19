#!/usr/bin/env python3
"""Generate Hunyuan3D 2.1 PaintPBR OBJ textures without importing bpy in Python.

The upstream PaintPBR package imports ``bpy`` at module import time only for
OBJ->GLB conversion. On the Blackwell worker the usable torch environment is
Python 3.12/CUDA 12.8, while the available bpy wheel is in a separate Python
3.10 env. This runner injects the mesh IO helpers needed by PaintPBR so it can
write OBJ + PBR texture maps first. GLB conversion can then be done separately
with Blender's own Python.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import types
from io import StringIO
from pathlib import Path
from typing import Any


HY21_ROOT = Path(os.getenv("HY21_ROOT", "/root/Hunyuan3D-2.1"))
HY21_MODEL_ROOT = Path(os.getenv("HY21_MODEL_ROOT", "/root/models"))


def _install_no_bpy_mesh_utils() -> None:
    import cv2
    import numpy as np

    mesh_utils = types.ModuleType("DifferentiableRenderer.mesh_utils")

    def _safe_extract_attribute(obj: Any, attr_path: str, default: Any = None) -> Any:
        try:
            for attr in attr_path.split("."):
                obj = getattr(obj, attr)
            return obj
        except AttributeError:
            return default

    def _convert_to_numpy(data: Any, dtype: np.dtype):
        if data is None:
            return None
        return np.asarray(data, dtype=dtype)

    def load_mesh(mesh):
        vtx_pos = _convert_to_numpy(_safe_extract_attribute(mesh, "vertices"), np.float32)
        pos_idx = _convert_to_numpy(_safe_extract_attribute(mesh, "faces"), np.int32)
        vtx_uv = _convert_to_numpy(_safe_extract_attribute(mesh, "visual.uv"), np.float32)
        uv_idx = pos_idx
        texture_data = None
        return vtx_pos, pos_idx, vtx_uv, uv_idx, texture_data

    def _base(mesh_path: str):
        base_path = os.path.splitext(mesh_path)[0]
        return base_path, os.path.basename(base_path)

    def _save_texture_map(texture, base_path: str, suffix: str = "", image_format: str = ".jpg", color_convert=None):
        path = f"{base_path}{suffix}{image_format}"
        processed = (texture * 255).astype(np.uint8)
        if color_convert is not None:
            processed = cv2.cvtColor(processed, color_convert)
            cv2.imwrite(path, processed)
        else:
            cv2.imwrite(path, processed[..., ::-1])
        return os.path.basename(path)

    def _write_props(f, properties):
        for key, value in properties.items():
            if isinstance(value, (list, tuple)):
                f.write(f"{key} {' '.join(map(str, value))}\n")
            else:
                f.write(f"{key} {value}\n")

    def _create_obj_content(vtx_pos, vtx_uv, pos_idx, uv_idx, name: str) -> str:
        buffer = StringIO()
        buffer.write(f"mtllib {name}.mtl\no {name}\n")
        np.savetxt(buffer, vtx_pos, fmt="v %.6f %.6f %.6f")
        np.savetxt(buffer, vtx_uv, fmt="vt %.6f %.6f")
        buffer.write("s 0\nusemtl Material\n")
        pos_idx_plus1 = pos_idx + 1
        uv_idx_plus1 = uv_idx + 1
        face_format = np.frompyfunc(lambda *x: f"{int(x[0])}/{int(x[1])}", 2, 1)
        faces = face_format(pos_idx_plus1, uv_idx_plus1)
        buffer.write("\n".join([f"f {' '.join(face)}" for face in faces]) + "\n")
        return buffer.getvalue()

    def _create_mtl_file(base_path: str, texture_maps: dict[str, str], is_pbr: bool):
        with open(f"{base_path}.mtl", "w", encoding="utf-8") as f:
            f.write("newmtl Material\n")
            props = {
                "Kd": [0.800, 0.800, 0.800],
                "Ke": [0.000, 0.000, 0.000],
                "Ni": 1.500,
                "d": 1.0,
                "illum": 2 if is_pbr else 3,
                "map_Kd": texture_maps["diffuse"],
            }
            if not is_pbr:
                props.update({"Ns": 250.0, "Ka": [0.2, 0.2, 0.2], "Ks": [0.5, 0.5, 0.5]})
            _write_props(f, props)
            if is_pbr:
                if "metallic" in texture_maps:
                    f.write(f"map_Pm {texture_maps['metallic']}\n")
                if "roughness" in texture_maps:
                    f.write(f"map_Pr {texture_maps['roughness']}\n")
                if "normal" in texture_maps:
                    f.write(f"map_Bump -bm 1.0 {texture_maps['normal']}\n")

    def save_obj_mesh(mesh_path, vtx_pos, pos_idx, vtx_uv, uv_idx, texture, metallic=None, roughness=None, normal=None):
        vtx_pos = _convert_to_numpy(vtx_pos, np.float32)
        vtx_uv = _convert_to_numpy(vtx_uv, np.float32)
        pos_idx = _convert_to_numpy(pos_idx, np.int32)
        uv_idx = _convert_to_numpy(uv_idx, np.int32)
        base_path, name = _base(mesh_path)
        with open(mesh_path, "w", encoding="utf-8") as obj_file:
            obj_file.write(_create_obj_content(vtx_pos, vtx_uv, pos_idx, uv_idx, name))
        texture_maps = {"diffuse": _save_texture_map(texture, base_path)}
        if metallic is not None:
            texture_maps["metallic"] = _save_texture_map(metallic, base_path, "_metallic", color_convert=cv2.COLOR_RGB2GRAY)
        if roughness is not None:
            texture_maps["roughness"] = _save_texture_map(roughness, base_path, "_roughness", color_convert=cv2.COLOR_RGB2GRAY)
        if normal is not None:
            texture_maps["normal"] = _save_texture_map(normal, base_path, "_normal")
        _create_mtl_file(base_path, texture_maps, metallic is not None or roughness is not None)

    def save_mesh(mesh_path, vtx_pos, pos_idx, vtx_uv, uv_idx, texture, metallic=None, roughness=None, normal=None):
        save_obj_mesh(mesh_path, vtx_pos, pos_idx, vtx_uv, uv_idx, texture, metallic=metallic, roughness=roughness, normal=normal)

    def convert_obj_to_glb(*_args, **_kwargs):
        raise RuntimeError("GLB conversion is intentionally disabled in no-bpy runner")

    mesh_utils.load_mesh = load_mesh
    mesh_utils.save_mesh = save_mesh
    mesh_utils.convert_obj_to_glb = convert_obj_to_glb
    sys.modules["DifferentiableRenderer.mesh_utils"] = mesh_utils


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--mesh", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--max-views", type=int, default=6)
    parser.add_argument("--texture-resolution", type=int, default=1024)
    args = parser.parse_args()

    sys.path[:0] = [
        str(HY21_ROOT),
        str(HY21_ROOT / "hy3dshape"),
        str(HY21_ROOT / "hy3dpaint"),
        str(HY21_ROOT / "hy3dpaint" / "custom_rasterizer"),
    ]
    os.chdir(HY21_ROOT)

    import huggingface_hub
    import torch
    import torchvision.transforms.functional as torchvision_functional
    from PIL import Image
    from hy3dshape.rembg import BackgroundRemover

    sys.modules.setdefault("torchvision.transforms.functional_tensor", torchvision_functional)
    _install_no_bpy_mesh_utils()
    import textureGenPipeline
    from utils.pipeline_utils import ViewProcessor
    from textureGenPipeline import Hunyuan3DPaintConfig, Hunyuan3DPaintPipeline

    class _IdentityImageSuperNet:
        """Smoke-test fallback when RealESRGAN is unavailable in the active env."""

        def __init__(self, _config) -> None:
            pass

        def __call__(self, image):
            return image

    if os.getenv("CF_PBR_DISABLE_REALESRGAN", "1") == "1":
        textureGenPipeline.imageSuperNet = _IdentityImageSuperNet
    if os.getenv("CF_PBR_DISABLE_UV_INPAINT", "1") == "1":
        ViewProcessor.texture_inpaint = lambda self, texture, _mask: texture

    original_snapshot_download = huggingface_hub.snapshot_download

    def local_snapshot_download(repo_id: str, *positional, **kwargs):
        if repo_id == str(HY21_MODEL_ROOT):
            return str(HY21_MODEL_ROOT)
        return original_snapshot_download(repo_id, *positional, **kwargs)

    huggingface_hub.snapshot_download = local_snapshot_download

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    source_image = Path(args.image).resolve()
    source_mesh = Path(args.mesh).resolve()

    image = Image.open(source_image).convert("RGBA")
    image = BackgroundRemover()(image)

    config = Hunyuan3DPaintConfig(args.max_views, args.texture_resolution)
    config.realesrgan_ckpt_path = str(HY21_ROOT / "hy3dpaint/ckpt/RealESRGAN_x4plus.pth")
    config.multiview_cfg_path = str(HY21_ROOT / "hy3dpaint/cfgs/hunyuan-paint-pbr.yaml")
    config.custom_pipeline = str(HY21_ROOT / "hy3dpaint/hunyuanpaintpbr")
    config.multiview_pretrained_path = str(HY21_MODEL_ROOT)
    config.dino_ckpt_path = str(HY21_MODEL_ROOT / "dinov2-giant")

    paint = Hunyuan3DPaintPipeline(config)
    output_obj = out_dir / "mesh_pbr.obj"
    result_path = paint(
        mesh_path=str(source_mesh),
        image_path=image,
        output_mesh_path=str(output_obj),
        use_remesh=False,
        save_glb=False,
    )
    torch.cuda.empty_cache()

    result = {
        "schema_version": "creativeflow.hy21-singleview-pbr-obj.v1",
        "source_image": str(source_image),
        "source_mesh": str(source_mesh),
        "mesh_obj": str(result_path or output_obj),
        "mesh_mtl": str(output_obj.with_suffix(".mtl")),
        "texture_diffuse": str(output_obj.with_suffix(".jpg")),
        "texture_metallic": str(out_dir / "mesh_pbr_metallic.jpg"),
        "texture_roughness": str(out_dir / "mesh_pbr_roughness.jpg"),
        "max_views": args.max_views,
        "texture_resolution": args.texture_resolution,
        "material_source": "Hunyuan3D-2.1 PaintPBR no-bpy OBJ path",
    }
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
