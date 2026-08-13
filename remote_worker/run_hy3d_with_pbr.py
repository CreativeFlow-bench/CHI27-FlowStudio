#!/usr/bin/env python3
"""Hy3D staged runner with PaintPBR texturing.

Runs the canonical ``pipeline_hunyuan3d_post.py`` (same args), then textures
each generated mesh with Hunyuan3D-2.1 PaintPBR (OBJ path) and converts the
textured OBJ to GLB with Blender. Writes the same
``hunyuan3d_post_summary.json`` contract back; ``mesh_glb``/``mesh_obj`` are
upgraded to the PBR outputs and extra ``mesh_pbr_*`` fields are added. PBR is
best-effort: if it fails for an item, the original mesh stays in the summary.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


PYTHON_BIN = Path(os.getenv("CF_WORKER_PYTHON", "/root/autodl-tmp/venvs/torch5090/bin/python"))
PBR_SCRIPT = Path(
    os.getenv(
        "CF_PBR_SCRIPT",
        "/root/flowstudio_app/remote_worker/hunyuan21_singleview_pbr_obj.py",
    )
)
CONVERT_SCRIPT = Path(
    os.getenv(
        "CF_PBR_CONVERT",
        "/root/flowstudio_app/remote_worker/convert_obj_to_glb_blender.py",
    )
)
BLENDER = Path(
    os.getenv(
        "CF_PBR_BLENDER",
        "/root/autodl-tmp/blender/blender-5.0.0-linux-x64/blender",
    )
)


def _run(cmd: list[str], timeout: int = 1800) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(part) for part in cmd],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
    )


def _texture_item(item: dict, out_dir: Path) -> dict:
    mesh_glb = item.get("mesh_glb")
    input_image = item.get("input_image")
    if not mesh_glb or not input_image:
        return item
    candidate_id = str(item.get("candidate_id") or item.get("rationale_id") or "candidate")
    pbr_dir = out_dir / "pbr" / candidate_id
    pbr_dir.mkdir(parents=True, exist_ok=True)
    pbr_cmd = [
        PYTHON_BIN,
        PBR_SCRIPT,
        "--image",
        str(input_image),
        "--mesh",
        str(mesh_glb),
        "--out-dir",
        str(pbr_dir),
    ]
    pbr = _run(pbr_cmd, timeout=1800)
    pbr_obj = pbr_dir / "mesh_pbr.obj"
    if pbr.returncode != 0 or not pbr_obj.exists():
        print(f"PBR skipped for {candidate_id}: rc={pbr.returncode}", flush=True)
        print((pbr.stdout or "")[-1200:], flush=True)
        return item
    pbr_glb = pbr_dir / "mesh_pbr.glb"
    convert = _run(
        [
            PYTHON_BIN,
            CONVERT_SCRIPT,
            "--obj",
            str(pbr_obj),
            "--glb",
            str(pbr_glb),
            "--blender",
            str(BLENDER),
        ],
        timeout=600,
    )
    if convert.returncode != 0 or not pbr_glb.exists():
        print(f"PBR GLB convert skipped for {candidate_id}: rc={convert.returncode}", flush=True)
        print((convert.stdout or "")[-1200:], flush=True)
        return item
    item["mesh_glb"] = str(pbr_glb)
    item["mesh_obj"] = str(pbr_obj)
    item["mesh_pbr_glb"] = str(pbr_glb)
    item["mesh_pbr_obj"] = str(pbr_obj)
    item["mesh_pbr_mtl"] = str(pbr_dir / "mesh_pbr.mtl")
    item["texture_diffuse"] = str(pbr_dir / "mesh_pbr.jpg")
    item["texture_metallic"] = str(pbr_dir / "mesh_pbr_metallic.jpg")
    item["texture_roughness"] = str(pbr_dir / "mesh_pbr_roughness.jpg")
    item["pbr"] = True
    print(f"PBR OK for {candidate_id}: {pbr_glb}", flush=True)
    return item


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hy3d-script", required=True)
    parser.add_argument("--transfer-result", required=True)
    parser.add_argument("--worker-script", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--oss-prefix-root", required=True)
    parser.add_argument("--max-candidates", type=int, default=1)
    parser.add_argument("--pbr", action="store_true", default=True)
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    hy3d_cmd = [
        PYTHON_BIN,
        args.hy3d_script,
        "--transfer-result",
        args.transfer_result,
        "--worker-script",
        args.worker_script,
        "--out-dir",
        str(out_dir),
        "--oss-prefix-root",
        args.oss_prefix_root,
        "--max-candidates",
        str(args.max_candidates),
    ]
    hy3d = _run(hy3d_cmd, timeout=2400)
    summary_path = out_dir / "hunyuan3d_post_summary.json"
    if hy3d.returncode != 0:
        print("Hy3D failed:", (hy3d.stdout or "")[-3000:], flush=True)
        return hy3d.returncode
    if not summary_path.exists():
        print(f"Hy3D summary missing: {summary_path}", flush=True)
        print((hy3d.stdout or "")[-3000:], flush=True)
        return 1
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if args.pbr:
        items = summary.get("items") or []
        textured = [_texture_item(item, out_dir) for item in items]
        summary["items"] = textured
        summary["pbr_enabled"] = True
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"ok": True, "items": len(summary.get("items") or [])}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
