#!/usr/bin/env python3
"""Run a small real Part-flow probe on three sources.

Pipeline:
1. Attribute-grounded analogical candidate prompt for the selected part.
2. Qwen-Image text-to-image for a standalone replacement part.
3. Hunyuan3D-2.1 single-view shape.
4. PaintPBR OBJ texture.
5. SAM3D-label 3D socket fitting back into the original source mesh.
6. Blender three-view renders for replacement PBR and merged preview.

This is intentionally not a prompt-only edit of the full source image.
"""

from __future__ import annotations

import json
import os
import signal
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


CASES: list[dict[str, Any]] = [
    {
        "case_id": "snowman_nose_icicle_horn",
        "source_object": "snowman",
        "part_name": "nose",
        "part_labels": "0",
        "source_mesh": "/root/autodl-tmp/creativeflow_variations_20260716/sam3d_source/mesh_root/sam3d_source.glb",
        "face_labels": "/root/autodl-tmp/creativeflow_variations_20260716/sam3d_source/exp/results/last/mesh_1.0.npy",
        "candidate": {
            "name": "translucent icicle-horn carrot nose",
            "source_part_attributes": [
                "small protruding facial landmark",
                "tapered cone",
                "warm color identity cue",
                "socketed into snow face",
            ],
            "analogy_relation": "nose as a forward-pointing protrusion; icicle/horn preserves taper and socket while adding material/shape novelty",
            "target_traits": [
                "clear icy translucency",
                "spiral ridge taper",
                "carrot-like orange core",
                "small plug base",
            ],
        },
        "prompt": (
            "A single standalone replacement part for a snowman's nose: a translucent icicle-horn carrot nose, "
            "small plug-in socket base, tapered conical form, subtle spiral ridges, orange carrot core fading into clear ice, "
            "frosty PBR material, designed to be embedded in a snowman face. Pure white RGB(255,255,255) background, "
            "no snowman body, no scene, no floor, no shadow, centered 3D product render."
        ),
    },
    {
        "case_id": "teapot_lid_knob_acorn_metal_ceramic",
        "source_object": "teapot",
        "part_name": "lid knob",
        "part_labels": "3",
        "source_mesh": "/root/autodl-tmp/creativeflow_variations_20260718/teapot_source_sam3d/mesh_root/teapot_source_sam3d.glb",
        "face_labels": "/root/autodl-tmp/creativeflow_variations_20260718/teapot_source_sam3d/exp/results/last/mesh_1.0.npy",
        "candidate": {
            "name": "ridged acorn pull knob",
            "source_part_attributes": [
                "small top grasping part",
                "rounded cap",
                "vertical pull affordance",
                "mounted on lid center",
            ],
            "analogy_relation": "lid knob as graspable cap; acorn and knurled hardware preserve pull affordance while changing silhouette/material",
            "target_traits": [
                "acorn dome",
                "knurled dark metal rim",
                "warm ceramic base",
                "grip ridges",
            ],
        },
        "prompt": (
            "A single standalone replacement teapot lid knob: an acorn-shaped pull knob with a rounded ceramic dome, "
            "dark knurled metal grip ring, small circular mounting base, tactile ridges for finger grip, elegant PBR ceramic and metal materials. "
            "Pure white RGB(255,255,255) background, no teapot body, no scene, no floor, no shadow, centered 3D product render."
        ),
    },
    {
        "case_id": "watergun_grip_braided_rubber_handle",
        "source_object": "toy water gun",
        "part_name": "handle grip",
        "part_labels": "13,16",
        "source_mesh": "/root/autodl-tmp/creativeflow_part_real_sam3d_20260718/watergun_sam3d/mesh_root/watergun_sam3d.glb",
        "face_labels": "/root/autodl-tmp/creativeflow_part_real_sam3d_20260718/watergun_sam3d/exp/results/last/mesh_0.5.npy",
        "candidate": {
            "name": "braided rubber ergonomic handle",
            "source_part_attributes": [
                "hand-contact affordance",
                "downward pistol-grip silhouette",
                "socketed below toy body",
                "needs comfortable tactile surface",
            ],
            "analogy_relation": "handle as grasping interface; braided rope and soft rubber preserve hand affordance while adding tactile/material novelty",
            "target_traits": [
                "curved ergonomic pistol grip",
                "braided side wrapping",
                "soft rubber ribs",
                "toy-safe rounded edges",
            ],
        },
        "prompt": (
            "A single standalone replacement handle grip for a toy water gun: curved ergonomic pistol-grip shape, "
            "soft blue rubber body with tan braided rope wrap along the sides, rounded toy-safe edges, ribbed finger grooves, "
            "small upper socket surface for attaching under a toy water gun body, colorful PBR toy material. "
            "Pure white RGB(255,255,255) background, no full gun, no scene, no floor, no shadow, centered 3D product render."
        ),
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
        completed = subprocess.run(
            cmd,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            env=merged_env,
            timeout=timeout,
        )
    if completed.returncode != 0:
        raise RuntimeError(f"command failed ({completed.returncode}); see {log_path}")


def qwen_health() -> dict[str, Any]:
    request = urllib.request.Request(QWEN_BASE_URL + "/health", method="GET")
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        return {"ok": False, "error": repr(exc)}


def generate_qwen_image(prompt: str, output: Path, *, seed: int) -> None:
    payload = {
        "prompt": prompt,
        "negative_prompt": (
            "full object, complete source object, scene, scenery, floor, shadow, cast shadow, table, hand, "
            "text, label, watermark, duplicate, multiple objects, diagram, line art, flat 2d illustration, "
            "colored background, blue background, gray background, gradient background"
        ),
        "width": 768,
        "height": 768,
        "num_inference_steps": 24,
        "true_cfg_scale": 4.0,
        "max_sequence_length": 384,
        "seed": seed,
    }
    request = urllib.request.Request(
        QWEN_BASE_URL + "/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=1200) as response:
            output.write_bytes(response.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Qwen-Image HTTP {exc.code}: {body}") from exc


def stop_qwen_to_free_vram() -> None:
    subprocess.run(["pkill", "-f", "uvicorn app_qwen_image:app"], check=False)
    time.sleep(3)


def main() -> int:
    out_root = Path(os.getenv("CF_PART_FULL_OUT", "/root/autodl-tmp/creativeflow_part_full_three_sources_20260721"))
    out_root.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {
        "schema_version": "creativeflow.part-full-flow-probe.v1",
        "status": "running",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "qwen_base_url": QWEN_BASE_URL,
        "cases": [],
    }
    summary_path = out_root / "run_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    health = qwen_health()
    summary["qwen_health"] = health
    if not health.get("ok") and health.get("status") not in {"ok", "healthy"}:
        raise RuntimeError(f"Qwen service is not healthy: {health}")

    # Generate all replacement images first while Qwen is resident.
    for idx, case in enumerate(CASES):
        case_dir = out_root / case["case_id"]
        case_dir.mkdir(parents=True, exist_ok=True)
        image_path = case_dir / "replacement_qwen.png"
        generate_qwen_image(case["prompt"], image_path, seed=9300 + idx * 97)
        case_record = {
            **case,
            "replacement_image": str(image_path),
            "status": "qwen_image_completed",
        }
        (case_dir / "candidate.json").write_text(json.dumps(case_record, ensure_ascii=False, indent=2), encoding="utf-8")
        summary["cases"].append(case_record)
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    stop_qwen_to_free_vram()

    hy_env = {
        "HY21_ROOT": "/root/autodl-tmp/data/flowstudio/root/Hunyuan3D-2.1",
        "HY21_MODEL_ROOT": "/root/autodl-tmp/data/flowstudio/root/models",
        "CF_PBR_DISABLE_REALESRGAN": "1",
        "CF_PBR_DISABLE_UV_INPAINT": "1",
    }

    for case_record in summary["cases"]:
        case_dir = out_root / case_record["case_id"]
        shape_dir = case_dir / "hunyuan_shape"
        pbr_dir = case_dir / "hunyuan_pbr_obj"
        socket_dir = case_dir / "socket_fit"
        repl_render_dir = case_dir / "renders_replacement_pbr"
        merged_render_dir = case_dir / "renders_merged_preview"

        case_record["status"] = "hunyuan_shape_running"
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        run(
            [
                PYTHON,
                str(REMOTE_WORKER / "hunyuan21_singleview_shape.py"),
                "--image",
                case_record["replacement_image"],
                "--out-dir",
                str(shape_dir),
                "--shape-steps",
                "20",
                "--octree-resolution",
                "256",
            ],
            log_path=case_dir / "logs" / "hunyuan_shape.log",
            env=hy_env,
            timeout=1800,
        )

        case_record["status"] = "paint_pbr_running"
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        run(
            [
                PYTHON,
                str(REMOTE_WORKER / "hunyuan21_singleview_pbr_obj.py"),
                "--image",
                case_record["replacement_image"],
                "--mesh",
                str(shape_dir / "mesh.glb"),
                "--out-dir",
                str(pbr_dir),
                "--max-views",
                "4",
                "--texture-resolution",
                "512",
            ],
            log_path=case_dir / "logs" / "paint_pbr.log",
            env=hy_env,
            timeout=2400,
        )

        case_record["status"] = "socket_fit_running"
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        run(
            [
                PYTHON,
                str(REMOTE_WORKER / "part_socket_replace_mesh.py"),
                "--source-mesh",
                case_record["source_mesh"],
                "--face-labels",
                case_record["face_labels"],
                "--part-labels",
                case_record["part_labels"],
                "--variant",
                "gel",
                "--replacement-mesh",
                str(pbr_dir / "mesh_pbr.obj"),
                "--out-dir",
                str(socket_dir),
            ],
            log_path=case_dir / "logs" / "socket_fit.log",
            timeout=900,
        )

        case_record["status"] = "rendering"
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        run(
            [
                PYTHON,
                str(REMOTE_WORKER / "render_glb_three_views.py"),
                "--mesh",
                str(pbr_dir / "mesh_pbr.obj"),
                "--out-dir",
                str(repl_render_dir),
                "--blender",
                BLENDER,
            ],
            log_path=case_dir / "logs" / "render_replacement.log",
            timeout=900,
        )
        run(
            [
                PYTHON,
                str(REMOTE_WORKER / "render_glb_three_views.py"),
                "--mesh",
                str(socket_dir / "part_replaced_gel_debug_colors.glb"),
                "--out-dir",
                str(merged_render_dir),
                "--blender",
                BLENDER,
            ],
            log_path=case_dir / "logs" / "render_merged.log",
            timeout=900,
        )

        case_record.update(
            {
                "status": "completed",
                "hunyuan_shape_glb": str(shape_dir / "mesh.glb"),
                "hunyuan_shape_obj": str(shape_dir / "mesh.obj"),
                "pbr_obj": str(pbr_dir / "mesh_pbr.obj"),
                "pbr_mtl": str(pbr_dir / "mesh_pbr.mtl"),
                "pbr_diffuse": str(pbr_dir / "mesh_pbr.jpg"),
                "socket_report": str(socket_dir / "part_socket_replace_report.json"),
                "merged_preview_glb": str(socket_dir / "part_replaced_gel_debug_colors.glb"),
                "replacement_renders": str(repl_render_dir / "renders.json"),
                "merged_renders": str(merged_render_dir / "renders.json"),
            }
        )
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    summary["status"] = "completed"
    summary["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(summary_path)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
