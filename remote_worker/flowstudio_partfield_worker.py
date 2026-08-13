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


def main() -> None:
    parser = argparse.ArgumentParser(description="FlowStudio PartField worker wrapper")
    parser.add_argument("--mesh", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--granularity", default="medium", choices=["low", "medium", "high"])
    parser.add_argument("--max-parts", type=int, default=16)
    parser.add_argument("--brush-mask", default=None)
    parser.add_argument("--partfield-root", default=os.getenv("PARTFIELD_ROOT", "/root/autodl-tmp/PartField"))
    parser.add_argument(
        "--checkpoint",
        default=os.getenv("PARTFIELD_MODEL", "/root/autodl-tmp/PartField/model/model_objaverse.ckpt"),
    )
    args = parser.parse_args()

    partfield_root = Path(args.partfield_root)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "partfield_manifest.json"

    source_mesh = Path(args.mesh)
    if not source_mesh.exists():
        raise FileNotFoundError(f"Missing mesh: {source_mesh}")
    if not partfield_root.exists():
        raise FileNotFoundError(f"Missing PartField root: {partfield_root}")
    checkpoint = Path(args.checkpoint)
    if not checkpoint.exists():
        raise FileNotFoundError(f"Missing PartField checkpoint: {checkpoint}")

    data_dir = out_dir / "data" / "flowstudio_input"
    data_dir.mkdir(parents=True, exist_ok=True)
    mesh_copy = data_dir / source_mesh.name
    if source_mesh.resolve() != mesh_copy.resolve():
        shutil.copy2(source_mesh, mesh_copy)

    feature_name = f"partfield_features/{out_dir.name}"
    feature_root = out_dir / "exp_results" / "partfield_features" / out_dir.name
    cluster_root = out_dir / "exp_results" / "clustering" / out_dir.name
    feature_root.parent.mkdir(parents=True, exist_ok=True)
    cluster_root.mkdir(parents=True, exist_ok=True)

    inference_cmd = [
        sys.executable,
        str(partfield_root / "partfield_inference.py"),
        "-c",
        str(partfield_root / "configs/final/demo.yaml"),
        "--opts",
        "continue_ckpt",
        str(checkpoint),
        "result_name",
        feature_name,
        "dataset.data_path",
        str(data_dir),
    ]
    clustering_cmd = [
        sys.executable,
        str(partfield_root / "run_part_clustering.py"),
        "--root",
        str(partfield_root / "exp_results" / "partfield_features" / out_dir.name),
        "--dump_dir",
        str(cluster_root),
        "--source_dir",
        str(data_dir),
        "--use_agglo",
        "True",
        "--max_num_clusters",
        str(max(2, args.max_parts)),
        "--option",
        "1",
        "--with_knn",
        "True",
    ]

    env = os.environ.copy()
    worker_root = Path(__file__).resolve().parent
    env["PYTHONPATH"] = f"{worker_root}:{partfield_root}:{env.get('PYTHONPATH', '')}"
    env["FLOWSTUDIO_TORCH_LOAD_WEIGHTS_ONLY_FALSE"] = "1"
    run_inference = _run(inference_cmd, partfield_root, env)

    produced_feature_root = partfield_root / "exp_results" / "partfield_features" / out_dir.name
    if produced_feature_root.exists() and produced_feature_root.resolve() != feature_root.resolve():
        if feature_root.exists():
            shutil.rmtree(feature_root)
        shutil.copytree(produced_feature_root, feature_root)

    clustering_logs: dict[str, Any] = {}
    try:
        run_clustering = _run(clustering_cmd, partfield_root, env)
        clustering_logs["with_knn"] = run_clustering
    except RuntimeError as exc:
        clustering_logs["with_knn_error"] = _clean_log_text(str(exc))[-4000:]
        fallback_clustering_cmd = list(clustering_cmd)
        fallback_clustering_cmd[-1] = "False"
        try:
            run_clustering = _run(fallback_clustering_cmd, partfield_root, env)
            clustering_logs["without_knn"] = run_clustering
            clustering_cmd = fallback_clustering_cmd
        except RuntimeError as fallback_exc:
            clustering_logs["without_knn_error"] = _clean_log_text(str(fallback_exc))[-4000:]
            kmeans_cmd = list(fallback_clustering_cmd)
            use_agglo_index = kmeans_cmd.index("--use_agglo") + 1
            kmeans_cmd[use_agglo_index] = "False"
            run_clustering = _run(kmeans_cmd, partfield_root, env)
            clustering_logs["without_agglo"] = run_clustering
            clustering_cmd = kmeans_cmd

    face_labels_path = _choose_cluster_labels(cluster_root, args.max_parts)
    segmented_mesh_path = _choose_segmented_mesh(cluster_root, args.max_parts)
    parts = _summarize_parts(source_mesh, face_labels_path, args.max_parts)
    manifest = {
        "parts": parts,
        "face_labels_path": str(face_labels_path) if face_labels_path else None,
        "segmented_mesh_path": str(segmented_mesh_path) if segmented_mesh_path else None,
        "feature_root": str(feature_root),
        "cluster_root": str(cluster_root),
        "source_mesh": str(source_mesh),
        "copied_mesh": str(mesh_copy),
        "granularity": args.granularity,
        "max_parts": args.max_parts,
        "brush_mask_path": args.brush_mask,
        "commands": {
            "inference": inference_cmd,
            "clustering": clustering_cmd,
        },
        "logs": {
            "inference": run_inference,
            "clustering": run_clustering,
            "clustering_attempts": clustering_logs,
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _run(cmd: list[str], cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    result = {
        "cmd": cmd,
        "return_code": proc.returncode,
        "stdout_tail": _clean_log_text(proc.stdout)[-4000:],
        "stderr_tail": _clean_log_text(proc.stderr)[-4000:],
    }
    if proc.returncode != 0:
        raise RuntimeError(json.dumps(result, ensure_ascii=False))
    return result


def _clean_log_text(text: str) -> str:
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    return "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)


def _choose_cluster_labels(cluster_root: Path, max_parts: int) -> Path | None:
    cluster_dir = cluster_root / "cluster_out"
    if not cluster_dir.exists():
        return None
    candidates = sorted(cluster_dir.glob("*.npy"))
    if not candidates:
        return None
    target_suffix = f"_{max(2, max_parts):02d}.npy"
    for path in candidates:
        if path.name.endswith(target_suffix):
            return path
    return candidates[-1]


def _choose_segmented_mesh(cluster_root: Path, max_parts: int) -> Path | None:
    ply_dir = cluster_root / "ply"
    if not ply_dir.exists():
        return None
    candidates = sorted(ply_dir.glob("*.ply"))
    if not candidates:
        return None
    target_suffix = f"_{max(2, max_parts):02d}.ply"
    for path in candidates:
        if path.name.endswith(target_suffix):
            return path
    return candidates[-1]


def _summarize_parts(mesh_path: Path, labels_path: Path | None, max_parts: int) -> list[dict[str, Any]]:
    if labels_path is None:
        return []
    import numpy as np
    import trimesh

    labels = np.load(labels_path).reshape(-1).astype(int)
    mesh = trimesh.load(mesh_path, force="mesh")
    vertices = np.asarray(mesh.vertices)
    faces = np.asarray(mesh.faces)
    parts: list[dict[str, Any]] = []
    for label in sorted(np.unique(labels).tolist())[:max_parts]:
        face_indices = np.where(labels == label)[0]
        if len(face_indices) == 0:
            continue
        valid_faces = face_indices[face_indices < len(faces)]
        if len(valid_faces) == 0:
            continue
        part_vertices = vertices[np.unique(faces[valid_faces].reshape(-1))]
        bbox_min = part_vertices.min(axis=0).tolist()
        bbox_max = part_vertices.max(axis=0).tolist()
        parts.append(
            {
                "part_id": f"part_{int(label):02d}",
                "label": f"part {int(label):02d}",
                "face_count": int(len(valid_faces)),
                "bbox": {"min": bbox_min, "max": bbox_max},
                "confidence": 0.7,
                "preview_path": None,
            }
        )
    return parts


if __name__ == "__main__":
    main()
