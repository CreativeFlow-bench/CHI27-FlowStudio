#!/usr/bin/env python3
"""Run the real Hunyuan3D shape + paint worker for scored variation images."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import struct
import subprocess
from pathlib import Path
from typing import Any


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")[:80]


def read_stage2(path: str) -> tuple[str, list[dict[str, Any]]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("status") != "completed" or not payload.get("items"):
        raise RuntimeError(f"Stage 2 is not a completed non-empty batch: {path}")
    return str(payload.get("stage") or Path(path).parent.name), payload["items"]


def inspect_glb_pbr(path: Path) -> dict[str, Any]:
    """Validate actual glTF material bindings instead of trusting metadata."""
    raw = path.read_bytes()
    if len(raw) < 20:
        raise RuntimeError(f"GLB is truncated: {path}")
    magic, version, total_length = struct.unpack_from("<4sII", raw, 0)
    if magic != b"glTF" or version != 2 or total_length != len(raw):
        raise RuntimeError(f"invalid GLB header: {path}")
    json_length, json_type = struct.unpack_from("<I4s", raw, 12)
    if json_type != b"JSON":
        raise RuntimeError(f"GLB first chunk is not JSON: {path}")
    document = json.loads(raw[20 : 20 + json_length].decode("utf-8").rstrip("\x00 "))
    materials = document.get("materials") or []
    images = document.get("images") or []
    textures = document.get("textures") or []
    base_color_bound = False
    metallic_roughness_bound = False
    for material in materials:
        pbr = material.get("pbrMetallicRoughness") or {}
        base_color_bound = base_color_bound or isinstance(pbr.get("baseColorTexture"), dict)
        metallic_roughness_bound = metallic_roughness_bound or isinstance(
            pbr.get("metallicRoughnessTexture"), dict
        )
    passed = bool(materials and images and textures and base_color_bound and metallic_roughness_bound)
    return {
        "passed": passed,
        "material_count": len(materials),
        "image_count": len(images),
        "texture_count": len(textures),
        "base_color_texture_bound": base_color_bound,
        "metallic_roughness_texture_bound": metallic_roughness_bound,
    }


def export_textured_obj(*, blender: str, exporter: str, glb: Path, obj: Path) -> None:
    completed = subprocess.run(
        [blender, "--background", "--python", exporter, "--", str(glb), str(obj)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=360,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Blender OBJ export failed: {completed.stdout[-1600:]}")
    if not obj.is_file() or obj.stat().st_size <= 1024:
        raise RuntimeError(f"missing exported OBJ: {obj}")


def bind_obj_pbr_material(work_dir: Path) -> dict[str, Any]:
    """Bind PaintPBR's external maps to the Blender-exported UV OBJ."""
    obj = work_dir / "mesh.obj"
    exported_mtl = work_dir / "mesh.mtl"
    paint_mtl = work_dir / "mesh_pbr.mtl"
    obj_text = obj.read_text(encoding="utf-8", errors="replace")
    material_match = re.search(r"^usemtl\s+(.+)$", obj_text, flags=re.MULTILINE)
    if not material_match or "\nvt " not in obj_text or "mtllib mesh.mtl" not in obj_text:
        raise RuntimeError(f"OBJ lacks UV/material declarations: {obj}")
    material_name = material_match.group(1).strip()
    if not paint_mtl.is_file():
        raise RuntimeError(f"PaintPBR MTL is missing: {paint_mtl}")
    paint_text = paint_mtl.read_text(encoding="utf-8", errors="replace")
    paint_text = re.sub(
        r"^newmtl\s+.+$", f"newmtl {material_name}", paint_text, count=1, flags=re.MULTILINE
    )
    map_names = re.findall(r"^map_(?:Kd|Pm|Pr)\s+(.+)$", paint_text, flags=re.MULTILINE)
    required_maps = {"mesh_pbr.jpg", "mesh_pbr_metallic.jpg", "mesh_pbr_roughness.jpg"}
    if not required_maps.issubset(set(map_names)):
        raise RuntimeError(f"PaintPBR MTL does not declare all maps: {map_names}")
    for name in required_maps:
        path = work_dir / name
        if not path.is_file() or path.stat().st_size <= 1024:
            raise RuntimeError(f"PBR map missing or empty: {path}")
    exported_mtl.write_text(paint_text, encoding="utf-8")
    return {
        "passed": True,
        "material_name": material_name,
        "mtl_path": str(exported_mtl),
        "maps": sorted(required_maps),
        "uv_coordinates_present": True,
    }


def final_package_files(work_dir: Path, meta_path: Path) -> list[Path]:
    files = [work_dir / "mesh.glb", work_dir / "mesh.obj", meta_path]
    files.extend(sorted(work_dir.glob("*.mtl")))
    files.extend(sorted(work_dir.glob("mesh_pbr*.jpg")))
    files.extend(sorted(work_dir.glob("mesh_pbr*.png")))
    out: list[Path] = []
    seen: set[str] = set()
    for path in files:
        if path.is_file() and path.name not in seen:
            seen.add(path.name)
            out.append(path)
    return out


def upload_final_package(work_dir: Path, key_prefix: str, meta_path: Path) -> list[str]:
    import oss2

    required = ("OSS_ACCESS_KEY_ID", "OSS_ACCESS_KEY_SECRET", "OSS_ENDPOINT", "OSS_BUCKET")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(f"OSS environment is missing: {', '.join(missing)}")
    bucket = oss2.Bucket(
        oss2.Auth(os.environ["OSS_ACCESS_KEY_ID"], os.environ["OSS_ACCESS_KEY_SECRET"]),
        os.environ["OSS_ENDPOINT"],
        os.environ["OSS_BUCKET"],
    )
    uploaded: list[str] = []
    for path in final_package_files(work_dir, meta_path):
        object_key = f"{key_prefix}/{path.name}"
        bucket.put_object_from_file(object_key, str(path))
        uploaded.append(object_key)
    return uploaded


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage2-result", action="append", default=[])
    parser.add_argument("--source-image")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--worker", default="/root/creativeflow_pipeline/step4_mesh_worker_mv.py")
    parser.add_argument("--python", default="/root/autodl-tmp/venvs/torch5090/bin/python")
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--hy21-worker", default="/root/autodl-tmp/data/flowstudio/opt-flowstudio/app/remote_worker/hunyuan21_singleview_pbr.py")
    parser.add_argument("--hy21-python", default="/root/autodl-tmp/venvs/torch5090/bin/python")
    parser.add_argument("--texture-resolution", type=int, default=512)
    parser.add_argument("--blender", default="/root/autodl-tmp/blender/blender-5.0.0-linux-x64/blender")
    parser.add_argument("--obj-exporter", default="/root/autodl-tmp/data/flowstudio/opt-flowstudio/app/remote_worker/export_glb_obj.py")
    parser.add_argument("--skip-pbr-enrichment", action="store_true")
    parser.add_argument("--skip-final-upload", action="store_true")
    parser.add_argument("--oss-prefix", default="creativeflow/variation-cases/20260716")
    args = parser.parse_args()

    jobs: list[dict[str, Any]] = []
    if args.source_image:
        jobs.append({
            "stage": "source",
            "direction_id": "snowman_source",
            "anchor": "original source",
            "image_path": args.source_image,
        })
    for result_path in args.stage2_result:
        stage, stage_items = read_stage2(result_path)
        for item in stage_items:
            jobs.append({"stage": stage, **item})
    if not jobs:
        raise RuntimeError("no source or Stage 2 jobs supplied")

    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["CF_ENABLE_MULTIVIEW"] = "0"
    env["CF_HY3D_STEPS"] = str(args.steps)
    manifest: list[dict[str, Any]] = []

    for index, job in enumerate(jobs, start=1):
        job_id = slug(str(job["direction_id"]))
        stage = slug(str(job["stage"]))
        work_dir = output_root / stage / job_id
        work_dir.mkdir(parents=True, exist_ok=True)
        meta_path = work_dir / "mesh_meta.json"
        if meta_path.is_file():
            existing = json.loads(meta_path.read_text(encoding="utf-8"))
            existing_validation = existing.get("pbr_validation") or {}
            if (
                existing.get("textured")
                and existing_validation.get("passed")
                and (work_dir / "mesh.glb").is_file()
                and (work_dir / "mesh.obj").is_file()
            ):
                manifest.append({"status": "reused", "work_dir": str(work_dir), "job": job, "meta": existing})
                print(f"[{index}/{len(jobs)}] reuse {stage}/{job_id}", flush=True)
                continue
        key = f"{args.oss_prefix}/{stage}/{job_id}"
        command = [
            args.python,
            args.worker,
            "--input-image", str(job["image_path"]),
            "--work-dir", str(work_dir),
            "--target-id", job_id,
            "--source-id", "snowman_shared_source_v1",
            "--relation-id", stage,
            "--prompt-text", str(job.get("anchor") or job_id),
            "--glb-key", f"{key}/mesh.glb",
            "--obj-key", f"{key}/mesh.obj",
            "--meta-key", f"{key}/mesh_meta.json",
        ]
        print(f"[{index}/{len(jobs)}] run {stage}/{job_id}", flush=True)
        log_path = work_dir / "hunyuan3d.log"
        with log_path.open("w", encoding="utf-8") as log:
            completed = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, text=True)
        if completed.returncode != 0:
            raise RuntimeError(f"Hunyuan3D failed for {stage}/{job_id}; see {log_path}")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if not meta.get("textured"):
            raise RuntimeError(f"PBR paint failed for {stage}/{job_id}: {meta.get('texture_error')}")
        if not (work_dir / "mesh.glb").is_file() or not (work_dir / "mesh.obj").is_file():
            raise RuntimeError(f"missing GLB/OBJ for {stage}/{job_id}")
        base_mesh = work_dir / "mesh.glb"
        if not args.skip_pbr_enrichment:
            shutil.copy2(base_mesh, work_dir / "mesh_basecolor.glb")
            shutil.copy2(base_mesh, work_dir / "mesh_untextured.glb")
            pbr_log = work_dir / "hunyuan21_pbr.log"
            pbr_command = [
                args.hy21_python,
                args.hy21_worker,
                "--image", str(job["image_path"]),
                "--out-dir", str(work_dir),
                "--shape-steps", str(args.steps),
                "--texture-resolution", str(args.texture_resolution),
                "--reuse-mesh",
            ]
            with pbr_log.open("w", encoding="utf-8") as log:
                pbr_completed = subprocess.run(
                    pbr_command, env=env, stdout=log, stderr=subprocess.STDOUT, text=True
                )
            pbr_mesh = work_dir / "mesh_pbr.glb"
            if pbr_completed.returncode != 0 or not pbr_mesh.is_file():
                raise RuntimeError(f"Hunyuan3D 2.1 PaintPBR failed for {stage}/{job_id}; see {pbr_log}")
            shutil.copy2(pbr_mesh, base_mesh)
        pbr_validation = inspect_glb_pbr(base_mesh)
        if not pbr_validation["passed"]:
            raise RuntimeError(f"PBR material binding validation failed for {stage}/{job_id}: {pbr_validation}")
        export_textured_obj(
            blender=args.blender,
            exporter=args.obj_exporter,
            glb=base_mesh,
            obj=work_dir / "mesh.obj",
        )
        obj_pbr_validation = bind_obj_pbr_material(work_dir)
        meta["textured"] = True
        meta["pbr_enriched"] = not args.skip_pbr_enrichment
        meta["pbr_validation"] = pbr_validation
        meta["obj_pbr_validation"] = obj_pbr_validation
        meta["pbr_worker"] = "Hunyuan3D-2.1 PaintPBR"
        if not args.skip_final_upload:
            # Include the final package manifest in metadata before the single
            # upload pass. PBR output replaces the base-color-only GLB under
            # the same canonical object key.
            meta["final_oss_keys"] = [
                f"{key}/{path.name}" for path in final_package_files(work_dir, meta_path)
            ]
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        if not args.skip_final_upload:
            uploaded = upload_final_package(work_dir, key, meta_path)
            meta["final_oss_keys"] = uploaded
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            # Only metadata changed after upload; update that small object.
            import oss2

            bucket = oss2.Bucket(
                oss2.Auth(os.environ["OSS_ACCESS_KEY_ID"], os.environ["OSS_ACCESS_KEY_SECRET"]),
                os.environ["OSS_ENDPOINT"],
                os.environ["OSS_BUCKET"],
            )
            bucket.put_object_from_file(f"{key}/{meta_path.name}", str(meta_path))
        manifest.append({"status": "completed", "work_dir": str(work_dir), "job": job, "meta": meta})
        (output_root / "batch_manifest.json").write_text(
            json.dumps({"status": "running", "completed": len(manifest), "total": len(jobs), "items": manifest}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    (output_root / "batch_manifest.json").write_text(
        json.dumps({"status": "completed", "completed": len(manifest), "total": len(jobs), "items": manifest}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
