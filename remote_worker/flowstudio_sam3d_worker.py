from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


REQUIRED_IMPORTS = [
    "torch",
    "numpy",
    "trimesh",
    "open3d",
    "pointcept",
    "pointops",
    "spconv",
    "torch_scatter",
    "tinycudann",
    "tensorboardX",
    "segment_anything",
    "OpenEXR",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="FlowStudio SAMPart3D worker wrapper")
    parser.add_argument("--health", action="store_true")
    parser.add_argument("--mesh")
    parser.add_argument("--out-dir")
    parser.add_argument("--granularity", default="medium")
    parser.add_argument("--max-parts", type=int, default=16)
    parser.add_argument("--brush-mask")
    parser.add_argument("--sam3d-root", default=os.environ.get("SAM3D_ROOT", "/root/SAMPart3D"))
    parser.add_argument("--model-root", default=os.environ.get("SAM3D_MODEL", ""))
    parser.add_argument("--blender-bin", default=os.environ.get("BLENDER_BIN", ""))
    parser.add_argument("--manifest", default="sam3d_manifest.json")
    parser.add_argument("--epochs", type=int, default=int(os.environ.get("SAM3D_EPOCHS", "50")))
    parser.add_argument("--sample-num", type=int, default=int(os.environ.get("SAM3D_SAMPLE_NUM", "15000")))
    parser.add_argument("--pixels-per-image", type=int, default=int(os.environ.get("SAM3D_PIXELS_PER_IMAGE", "256")))
    parser.add_argument("--mask-batch-size", type=int, default=int(os.environ.get("SAM3D_MASK_BATCH_SIZE", "90")))
    args = parser.parse_args()

    status = preflight(args)
    if args.health:
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0 if status["ready"] else 2

    out_dir = Path(args.out_dir or ".").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / args.manifest

    if not status["ready"]:
        manifest = {
            "adapter": "sam3d",
            "status": "failed",
            "error": "SAMPart3D is not ready",
            "preflight": status,
            "parts": [],
            "face_labels_path": None,
            "segmented_mesh_path": None,
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 2

    mesh = Path(str(args.mesh or "")).resolve()
    if not mesh.exists():
        manifest = {
            "adapter": "sam3d",
            "status": "failed",
            "error": f"Missing mesh: {mesh}",
            "parts": [],
            "face_labels_path": None,
            "segmented_mesh_path": None,
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 2

    layout = prepare_sam3d_layout(args, mesh, out_dir, status)
    render_dir = Path(layout["data_dir"])
    render = render_16_views(args, mesh, render_dir)
    if not render["ok"]:
        manifest = {
            "adapter": "sam3d",
            "status": "failed",
            "error": render["error"],
            "preflight": status,
            "render": render,
            "parts": [],
            "face_labels_path": None,
            "segmented_mesh_path": None,
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 2

    train = run_sam3d_train(args, out_dir, layout, status)
    if not train["ok"]:
        manifest = {
            "adapter": "sam3d",
            "status": "failed",
            "error": train["error"],
            "granularity": args.granularity,
            "max_parts": args.max_parts,
            "preflight": status,
            "layout": layout,
            "render": render,
            "train": train,
            "parts": [],
            "face_labels_path": None,
            "segmented_mesh_path": None,
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 2

    labels_path = choose_result_file(Path(train["results_dir"]), args.granularity)
    segmented_mesh_path = choose_result_file(Path(train["vis_dir"]), args.granularity, suffix=".ply")
    parts = summarize_parts(Path(layout["mesh_glb"]), labels_path, args.max_parts)
    projection_manifest = render_part_projection_masks(
        Path(layout["mesh_glb"]), labels_path, parts, out_dir / "part_projection_masks"
    )
    if labels_path is None or segmented_mesh_path is None:
        manifest = {
            "adapter": "sam3d",
            "status": "failed",
            "error": "SAMPart3D finished but did not produce mesh labels and segmented mesh",
            "granularity": args.granularity,
            "max_parts": args.max_parts,
            "preflight": status,
            "layout": layout,
            "render": render,
            "train": train,
            "parts": parts,
            "part_projection_masks": projection_manifest,
            "face_labels_path": str(labels_path) if labels_path else None,
            "segmented_mesh_path": str(segmented_mesh_path) if segmented_mesh_path else None,
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 2

    manifest = {
        "adapter": "sam3d",
        "status": "completed",
        "granularity": args.granularity,
        "max_parts": args.max_parts,
        "preflight": status,
        "layout": layout,
        "render": render,
        "train": train,
        "parts": parts,
        "part_projection_masks": projection_manifest,
        "face_labels_path": str(labels_path),
        "segmented_mesh_path": str(segmented_mesh_path),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


def preflight(args: argparse.Namespace) -> dict[str, Any]:
    sam3d_root = Path(args.sam3d_root).resolve()
    model_root = Path(args.model_root).resolve() if args.model_root else sam3d_root / "ckpt"
    blender_bin = Path(args.blender_bin).resolve() if args.blender_bin else None
    ensure_sam3d_paths(sam3d_root)
    imports = {name: import_available(name) for name in REQUIRED_IMPORTS}
    torch_info = get_torch_info(imports.get("torch", False))
    checkpoint = find_checkpoint(sam3d_root, model_root)
    paths = {
        "sam3d_root": str(sam3d_root),
        "sam3d_root_exists": sam3d_root.exists(),
        "train_script_exists": (sam3d_root / "scripts" / "train.sh").exists(),
        "eval_script_exists": (sam3d_root / "scripts" / "eval.sh").exists(),
        "render_script_exists": (sam3d_root / "tools" / "blender_render_16views.py").exists(),
        "config_exists": (
            sam3d_root / "configs" / "sampart3d" / "sampart3d-trainmlp-render16views.py"
        ).exists(),
        "model_root": str(model_root),
        "model_root_exists": model_root.exists(),
        "checkpoint": str(checkpoint) if checkpoint else None,
        "checkpoint_exists": bool(checkpoint),
        "blender_bin": str(blender_bin) if blender_bin else None,
        "blender_exists": bool(blender_bin and blender_bin.exists()),
    }
    required_paths = [
        paths["sam3d_root_exists"],
        paths["train_script_exists"],
        paths["eval_script_exists"],
        paths["render_script_exists"],
        paths["config_exists"],
        paths["checkpoint_exists"],
    ]
    required_imports_ok = all(imports.get(name, False) for name in REQUIRED_IMPORTS)
    return {
        "ready": all(required_paths) and required_imports_ok,
        "python": sys.executable,
        "paths": paths,
        "imports": imports,
        "torch": torch_info,
        "missing_imports": [name for name, ok in imports.items() if not ok],
    }


def ensure_sam3d_paths(sam3d_root: Path) -> None:
    for path in (sam3d_root, sam3d_root / "libs" / "pointops"):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)


def import_available(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def get_torch_info(has_torch: bool) -> dict[str, Any]:
    if not has_torch:
        return {}
    import torch

    return {
        "version": torch.__version__,
        "cuda": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(),
        "device_count": torch.cuda.device_count(),
    }


def find_checkpoint(sam3d_root: Path, model_root: Path) -> Path | None:
    candidates = [
        model_root / "ptv3-object.pth",
        sam3d_root / "ckpt" / "ptv3-object.pth",
    ]
    candidates.extend(model_root.glob("*.pth") if model_root.is_dir() else [])
    for path in candidates:
        if path.exists() and path.is_file() and path.stat().st_size > 0:
            return path
    return None


def render_16_views(args: argparse.Namespace, mesh: Path, render_dir: Path) -> dict[str, Any]:
    sam3d_root = Path(args.sam3d_root).resolve()
    blender_bin = Path(args.blender_bin).resolve() if args.blender_bin else None
    render_script = sam3d_root / "tools" / "blender_render_16views.py"
    if not blender_bin or not blender_bin.exists():
        return {"ok": False, "error": f"Missing Blender binary: {blender_bin}"}
    if not render_script.exists():
        return {"ok": False, "error": f"Missing SAMPart3D render script: {render_script}"}
    mesh_type = mesh.suffix.lower().lstrip(".")
    if mesh_type not in {"glb", "gltf", "obj"}:
        return {"ok": False, "error": f"Unsupported mesh type for SAMPart3D render: {mesh.suffix}"}
    render_dir.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [str(blender_bin), "-b", "-P", str(render_script), str(mesh), mesh_type, str(render_dir)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=600,
        check=False,
    )
    files = sorted(str(path) for path in render_dir.iterdir() if path.is_file())
    render_files = [path for path in files if Path(path).name.startswith("render_") and Path(path).suffix == ".webp"]
    depth_files = [path for path in files if Path(path).name.startswith("depth_") and Path(path).suffix == ".exr"]
    meta_path = render_dir / "meta.json"
    if completed.returncode != 0:
        return {
            "ok": False,
            "error": "Blender 16-view render failed",
            "stderr_tail": completed.stderr[-2000:],
            "stdout_tail": completed.stdout[-2000:],
        }
    if len(render_files) < 16 or len(depth_files) < 16 or not meta_path.exists():
        return {
            "ok": False,
            "error": "Blender render did not produce the full SAMPart3D RGB/depth/meta set",
            "returncode": completed.returncode,
            "render_dir": str(render_dir),
            "file_count": len(files),
            "render_file_count": len(render_files),
            "depth_file_count": len(depth_files),
            "meta_path": str(meta_path) if meta_path.exists() else None,
            "files": files[:64],
            "stderr_tail": completed.stderr[-2000:],
            "stdout_tail": completed.stdout[-2000:],
        }
    return {
        "ok": True,
        "render_dir": str(render_dir),
        "file_count": len(files),
        "render_file_count": len(render_files),
        "depth_file_count": len(depth_files),
        "meta_path": str(meta_path) if meta_path.exists() else None,
        "files": files[:64],
    }


def prepare_sam3d_layout(
    args: argparse.Namespace, mesh: Path, out_dir: Path, status: dict[str, Any]
) -> dict[str, Any]:
    oid = sanitize_oid(out_dir.name or mesh.stem)
    data_root = out_dir / "data_root"
    data_dir = data_root / oid
    mesh_root = out_dir / "mesh_root"
    exp_dir = out_dir / "exp"
    config_dir = Path(args.sam3d_root).resolve() / "configs" / "sampart3d"
    runtime_config = config_dir / f"flowstudio_{oid}.py"
    data_dir.mkdir(parents=True, exist_ok=True)
    mesh_root.mkdir(parents=True, exist_ok=True)
    exp_dir.mkdir(parents=True, exist_ok=True)
    mesh_glb = mesh_root / f"{oid}.glb"
    materialize_glb(mesh, mesh_glb)
    checkpoint = status["paths"].get("checkpoint")
    write_runtime_config(
        Path(args.sam3d_root).resolve(),
        runtime_config,
        data_root,
        mesh_root,
        checkpoint,
        epochs=max(1, args.epochs),
        sample_num=max(512, args.sample_num),
        pixels_per_image=max(16, args.pixels_per_image),
        mask_batch_size=max(1, args.mask_batch_size),
    )
    return {
        "oid": oid,
        "data_root": str(data_root),
        "data_dir": str(data_dir),
        "mesh_root": str(mesh_root),
        "mesh_glb": str(mesh_glb),
        "exp_dir": str(exp_dir),
        "runtime_config": str(runtime_config),
        "epochs": max(1, args.epochs),
        "sample_num": max(512, args.sample_num),
        "pixels_per_image": max(16, args.pixels_per_image),
        "mask_batch_size": max(1, args.mask_batch_size),
    }


def sanitize_oid(value: str) -> str:
    oid = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
    return oid or "flowstudio_mesh"


def materialize_glb(source: Path, target: Path) -> None:
    if source.resolve() == target.resolve():
        return
    if source.suffix.lower() in {".glb", ".gltf"}:
        shutil.copy2(source, target)
        return
    import trimesh

    loaded = trimesh.load(source, force="scene")
    loaded.export(target)


def write_runtime_config(
    sam3d_root: Path,
    runtime_config: Path,
    data_root: Path,
    mesh_root: Path,
    checkpoint: str | None,
    *,
    epochs: int,
    sample_num: int,
    pixels_per_image: int,
    mask_batch_size: int,
) -> None:
    source = sam3d_root / "configs" / "sampart3d" / "sampart3d-trainmlp-render16views.py"
    text = source.read_text(encoding="utf-8")
    override = f"""

# FlowStudio runtime overrides.
data_root = r"{data_root}"
mesh_root = r"{mesh_root}"
backbone_weight_path = r"{checkpoint or ''}"
epoch = {epochs}
eval_epoch = {epochs}
enable_amp = False
model["backbone"]["enable_flash"] = False
data["train"]["data_root"] = data_root
data["train"]["mesh_root"] = mesh_root
data["train"]["sample_num"] = {sample_num}
data["train"]["pixels_per_image"] = {pixels_per_image}
data["train"]["batch_size"] = {mask_batch_size}
"""
    runtime_config.write_text(text + override, encoding="utf-8")


def run_sam3d_train(
    args: argparse.Namespace, out_dir: Path, layout: dict[str, Any], status: dict[str, Any]
) -> dict[str, Any]:
    sam3d_root = Path(args.sam3d_root).resolve()
    exp_dir = Path(layout["exp_dir"])
    cmd = [
        sys.executable,
        str(sam3d_root / "launch" / "train.py"),
        "--config-file",
        str(layout["runtime_config"]),
        "--num-gpus",
        "1",
        "--options",
        f"save_path={exp_dir}",
        f"oid={layout['oid']}",
        f"label={args.granularity}",
    ]
    env = os.environ.copy()
    worker_root = Path(__file__).resolve().parent
    env["PYTHONPATH"] = (
        f"{worker_root}:{sam3d_root}:{sam3d_root / 'libs' / 'pointops'}:"
        f"{env.get('PYTHONPATH', '')}"
    )
    env["OPENCV_IO_ENABLE_OPENEXR"] = "1"
    env.setdefault("SAM3D_FORCE_LOCAL_SAM", "1")
    env.setdefault("HF_HOME", str(out_dir / "hf_cache"))
    env.setdefault("TRANSFORMERS_CACHE", str(out_dir / "hf_cache" / "transformers"))
    timeout = int(os.environ.get("SAM3D_TRAIN_TIMEOUT", "7200"))
    completed = subprocess.run(
        cmd,
        cwd=str(sam3d_root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )
    results_dir = exp_dir / "results" / "last"
    vis_dir = exp_dir / "vis_pcd" / "last"
    result = {
        "ok": completed.returncode == 0,
        "cmd": cmd,
        "returncode": completed.returncode,
        "exp_dir": str(exp_dir),
        "results_dir": str(results_dir),
        "vis_dir": str(vis_dir),
        "stdout_tail": clean_log_text(completed.stdout)[-6000:],
        "stderr_tail": clean_log_text(completed.stderr)[-6000:],
        "epochs": layout["epochs"],
    }
    if completed.returncode != 0:
        result["error"] = "SAMPart3D train/eval failed"
    return result


def choose_result_file(root: Path, granularity: str, suffix: str = ".npy") -> Path | None:
    if not root.exists():
        return None
    candidates = sorted(root.glob(f"mesh_*{suffix}"))
    if not candidates:
        return None
    preferred = {
        "low": "mesh_2.0",
        "medium": "mesh_1.0",
        "high": "mesh_0.5",
    }.get(str(granularity).lower(), "mesh_1.0")
    for path in candidates:
        if path.stem == preferred:
            return path
    return candidates[len(candidates) // 2]


def summarize_parts(mesh_path: Path, labels_path: Path | None, max_parts: int) -> list[dict[str, Any]]:
    if labels_path is None or not labels_path.exists():
        return []
    import numpy as np
    import trimesh

    labels = np.load(labels_path).reshape(-1).astype(int)
    loaded = trimesh.load(mesh_path)
    mesh = loaded.dump(concatenate=True) if isinstance(loaded, trimesh.Scene) else loaded
    vertices = mesh.vertices
    faces = mesh.faces
    parts: list[dict[str, Any]] = []
    for label in sorted(np.unique(labels).tolist())[: max(1, max_parts)]:
        face_indices = np.where(labels == label)[0]
        valid_faces = face_indices[face_indices < len(faces)]
        if len(valid_faces) == 0:
            continue
        part_vertices = vertices[np.unique(faces[valid_faces].reshape(-1))]
        bbox_min = part_vertices.min(axis=0).tolist()
        bbox_max = part_vertices.max(axis=0).tolist()
        parts.append(
            {
                "part_id": f"sam3d_{int(label)}",
                "label": f"part {int(label)}",
                "source_part_id": int(label),
                "cluster_id": int(label),
                "face_count": int(len(valid_faces)),
                "bbox3d": {"min": bbox_min, "max": bbox_max},
                "metadata": {
                    "source": "sam3d",
                    "labels_path": str(labels_path),
                },
            }
        )
    return parts


def render_part_projection_masks(
    mesh_path: Path,
    labels_path: Path | None,
    parts: list[dict[str, Any]],
    out_root: Path,
    *,
    view_count: int = 16,
    image_size: int = 512,
) -> dict[str, Any]:
    """Project SAM3D face clusters into deterministic orbit-view masks.

    The masks are generated from the actual SAM3D face labels, not a 2D
    detector.  A downstream resolver matches the user's brush to the most
    compatible view/cluster and then performs semantic naming with the VLM.
    """

    if labels_path is None or not labels_path.is_file() or not parts:
        return {"status": "unavailable", "views": [], "parts": {}}
    import math
    import numpy as np
    import trimesh
    from PIL import Image, ImageDraw

    labels = np.load(labels_path).reshape(-1).astype(int)
    loaded = trimesh.load(mesh_path)
    mesh = loaded.dump(concatenate=True) if isinstance(loaded, trimesh.Scene) else loaded
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    if not len(vertices) or not len(faces):
        return {"status": "failed", "error": "empty mesh", "views": [], "parts": {}}
    out_root.mkdir(parents=True, exist_ok=True)
    center = (vertices.min(axis=0) + vertices.max(axis=0)) / 2.0
    extent = float(np.max(vertices.max(axis=0) - vertices.min(axis=0))) or 1.0
    world_up = np.array([0.0, 0.0, 1.0], dtype=np.float64)
    views: list[dict[str, Any]] = []
    projected: dict[str, list[str]] = {str(part["part_id"]): [] for part in parts}
    valid_label_count = min(len(labels), len(faces))

    for view_index in range(max(1, view_count)):
        azimuth = 2.0 * math.pi * view_index / max(1, view_count)
        elevation = math.radians(8.0)
        camera = center + extent * 2.5 * np.array(
            [math.sin(azimuth) * math.cos(elevation), -math.cos(azimuth) * math.cos(elevation), math.sin(elevation)]
        )
        forward = center - camera
        forward /= np.linalg.norm(forward) + 1e-12
        right = np.cross(forward, world_up)
        if np.linalg.norm(right) < 1e-8:
            right = np.array([1.0, 0.0, 0.0])
        right /= np.linalg.norm(right) + 1e-12
        up = np.cross(right, forward)
        relative = vertices - center
        px = relative @ right
        py = relative @ up
        scale = (image_size * 0.82) / max(1e-8, 2.0 * max(np.max(np.abs(px)), np.max(np.abs(py))))
        screen = np.stack(
            [image_size / 2.0 + px * scale, image_size / 2.0 - py * scale], axis=1
        )
        views.append(
            {
                "view_index": view_index,
                "azimuth_deg": round(math.degrees(azimuth), 3),
                "elevation_deg": 8.0,
            }
        )
        for part in parts:
            cluster_id = int(part["cluster_id"])
            face_ids = np.where(labels[:valid_label_count] == cluster_id)[0]
            part_dir = out_root / str(part["part_id"])
            part_dir.mkdir(parents=True, exist_ok=True)
            mask = Image.new("L", (image_size, image_size), 0)
            draw = ImageDraw.Draw(mask)
            for face_id in face_ids:
                polygon = [tuple(screen[int(vertex_id)]) for vertex_id in faces[int(face_id)]]
                draw.polygon(polygon, fill=255)
            path = part_dir / f"view_{view_index:02d}.png"
            mask.save(path)
            projected[str(part["part_id"])].append(str(path))

    by_id = {str(part["part_id"]): part for part in parts}
    for part_id, paths in projected.items():
        by_id[part_id]["projection_masks"] = paths
        by_id[part_id]["metadata"]["projection_view_count"] = len(paths)
    return {
        "status": "completed",
        "image_size": image_size,
        "view_count": view_count,
        "views": views,
        "parts": projected,
    }


def clean_log_text(text: str) -> str:
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    return "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)


if __name__ == "__main__":
    raise SystemExit(main())
