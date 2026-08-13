#!/usr/bin/env python3
"""Material variation probe: keep source geometry, migrate PBR material only."""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REMOTE_WORKER = Path(__file__).resolve().parent
PYTHON = os.getenv("CF_PYTHON", "/root/autodl-tmp/venvs/torch5090/bin/python")
QWEN_BASE_URL = os.getenv("CF_QWEN_IMAGE_URL", "http://127.0.0.1:18082").rstrip("/")
BLENDER = os.getenv(
    "CF_BLENDER",
    "/root/autodl-tmp/data/flowstudio/blender/blender-5.0.0-linux-x64/blender",
)

SOURCE_IMAGE = os.getenv("CF_MATERIAL_SOURCE_IMAGE", "/root/autodl-tmp/flowstudio_worker_runs/snowman_inputs/source.png")
SOURCE_MESH = os.getenv(
    "CF_MATERIAL_SOURCE_MESH",
    "/root/autodl-tmp/creativeflow_variations_20260716/hunyuan3d/source/snowman_source/mesh.glb",
)
SOURCE_OBJECT = os.getenv("CF_MATERIAL_SOURCE_OBJECT", "snowman")

MATERIALS: list[dict[str, Any]] = [
    {
        "id": "translucent_blue_ice",
        "target": "translucent blue ice",
        "prompt": "保留这张图中的snowman结构、轮廓、部件、姿态、相机角度和元素不变，只把整体表面材质迁移为半透明蓝色冰晶材质；可见冰内部折射、微小气泡、霜纹和冷色高光。纯白背景、无地面、无投影、单体、完整三维产品渲染。",
    },
    {
        "id": "glazed_porcelain",
        "target": "glazed porcelain",
        "prompt": "保留这张图中的snowman结构、轮廓、部件、姿态、相机角度和元素不变，只把整体表面材质迁移为高光釉面瓷器材质；白瓷底、细腻釉裂纹、局部蓝色釉彩、光滑反射。纯白背景、无地面、无投影、单体、完整三维产品渲染。",
    },
    {
        "id": "carved_pale_wood",
        "target": "carved pale wood",
        "prompt": "保留这张图中的snowman结构、轮廓、部件、姿态、相机角度和元素不变，只把整体表面材质迁移为浅色雕刻木材；可见连续木纹、雕刻刀痕、哑光清漆、温暖木色。纯白背景、无地面、无投影、单体、完整三维产品渲染。",
    },
    {
        "id": "iridescent_opal_glass",
        "target": "iridescent opal glass",
        "prompt": "保留这张图中的snowman结构、轮廓、部件、姿态、相机角度和元素不变，只把整体表面材质迁移为虹彩蛋白石玻璃；乳白半透明基底、粉蓝紫虹彩、玻璃厚度感、柔和折射。纯白背景、无地面、无投影、单体、完整三维产品渲染。",
    },
]


def run(cmd: list[str], *, log_path: Path, env: dict[str, str] | None = None, timeout: int | None = None) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    with log_path.open("w", encoding="utf-8") as log:
        log.write("$ " + " ".join(cmd) + "\n")
        log.flush()
        completed = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, text=True, env=merged_env, timeout=timeout)
    if completed.returncode != 0:
        raise RuntimeError(f"command failed ({completed.returncode}); see {log_path}")


def generate_conditioned(prompt: str, output: Path, *, seed: int) -> None:
    payload = {
        "prompt": prompt,
        "negative_prompt": (
            "different shape, changed silhouette, changed pose, missing hat, missing scarf, missing arms, extra object, "
            "scene, floor, shadow, blue background, gray background, gradient background, text, watermark, cropped, flat illustration"
        ),
        "source_image_path": SOURCE_IMAGE,
        "mode": "img2img",
        "strength": 0.62,
        "width": 768,
        "height": 768,
        "num_inference_steps": 24,
        "true_cfg_scale": 4.0,
        "max_sequence_length": 384,
        "seed": seed,
    }
    req = urllib.request.Request(
        QWEN_BASE_URL + "/generate-conditioned",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=1200) as resp:
            output.write_bytes(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Qwen HTTP {exc.code}: {body}") from exc


def main() -> int:
    out_root = Path(os.getenv("CF_MATERIAL_OUT", "/root/autodl-tmp/creativeflow_material_snowman_pbr_20260722"))
    out_root.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {
        "schema_version": "creativeflow.material-pbr-probe.v1",
        "status": "running",
        "source_object": SOURCE_OBJECT,
        "source_image": SOURCE_IMAGE,
        "source_mesh_fixed_geometry": SOURCE_MESH,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "items": [],
    }
    summary_path = out_root / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    for idx, spec in enumerate(MATERIALS):
        item_dir = out_root / spec["id"]
        item_dir.mkdir(parents=True, exist_ok=True)
        image_path = item_dir / "qwen_material_reference.png"
        generate_conditioned(spec["prompt"], image_path, seed=12200 + idx * 101)
        item = {
            **spec,
            "status": "qwen_completed",
            "material_reference_image": str(image_path),
        }
        summary["items"].append(item)
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    subprocess.run(["pkill", "-f", "uvicorn app_qwen_image:app"], check=False)
    time.sleep(3)

    hy_env = {
        "HY21_ROOT": "/root/autodl-tmp/data/flowstudio/root/Hunyuan3D-2.1",
        "HY21_MODEL_ROOT": "/root/autodl-tmp/data/flowstudio/root/models",
        "CF_PBR_DISABLE_REALESRGAN": "1",
        "CF_PBR_DISABLE_UV_INPAINT": "1",
    }
    for item in summary["items"]:
        item_dir = out_root / item["id"]
        pbr_dir = item_dir / "paint_pbr_fixed_mesh"
        render_dir = item_dir / "renders_pbr"
        item["status"] = "paint_pbr_running"
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        run(
            [
                PYTHON,
                str(REMOTE_WORKER / "hunyuan21_singleview_pbr_obj.py"),
                "--image",
                item["material_reference_image"],
                "--mesh",
                SOURCE_MESH,
                "--out-dir",
                str(pbr_dir),
                "--max-views",
                "4",
                "--texture-resolution",
                "512",
            ],
            log_path=item_dir / "logs" / "paint_pbr.log",
            env=hy_env,
            timeout=2400,
        )
        item["status"] = "rendering"
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        run(
            [
                PYTHON,
                str(REMOTE_WORKER / "render_glb_three_views.py"),
                "--mesh",
                str(pbr_dir / "mesh_pbr.obj"),
                "--out-dir",
                str(render_dir),
                "--blender",
                BLENDER,
            ],
            log_path=item_dir / "logs" / "render.log",
            timeout=900,
        )
        item.update(
            {
                "status": "completed",
                "pbr_obj": str(pbr_dir / "mesh_pbr.obj"),
                "pbr_mtl": str(pbr_dir / "mesh_pbr.mtl"),
                "pbr_diffuse": str(pbr_dir / "mesh_pbr.jpg"),
                "pbr_metallic": str(pbr_dir / "mesh_pbr_metallic.jpg"),
                "pbr_roughness": str(pbr_dir / "mesh_pbr_roughness.jpg"),
                "renders": str(render_dir / "renders.json"),
            }
        )
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    summary["status"] = "completed"
    summary["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
