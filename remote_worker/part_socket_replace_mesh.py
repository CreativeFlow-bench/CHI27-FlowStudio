#!/usr/bin/env python3
"""3D-first Part replacement prototype.

This script does not use a 2D mask. It removes a selected SAM3D face cluster
from a source mesh, estimates the selected part's local socket/bbox frame, and
inserts a replacement mesh back into that same 3D region.

It can either create a procedural placeholder replacement for smoke testing, or
fit an externally generated replacement mesh (for example a Hunyuan3D part mesh)
back into the selected SAM3D socket.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import trimesh


def load_mesh(path: Path) -> trimesh.Trimesh:
    loaded = trimesh.load(path, force="scene", process=False)
    if isinstance(loaded, trimesh.Scene):
        meshes = [m for m in loaded.geometry.values() if isinstance(m, trimesh.Trimesh)]
        if not meshes:
            raise RuntimeError(f"no mesh geometry found in {path}")
        return trimesh.util.concatenate(meshes)
    if not isinstance(loaded, trimesh.Trimesh):
        raise RuntimeError(f"unsupported mesh type for {path}: {type(loaded)!r}")
    return loaded


def face_indices_for_labels(labels_path: Path, labels_to_select: list[int], face_count: int) -> np.ndarray:
    labels = np.load(labels_path).reshape(-1).astype(int)
    if labels.shape[0] != face_count:
        raise RuntimeError(
            f"face label count mismatch: labels={labels.shape[0]} mesh_faces={face_count}"
        )
    indices = np.flatnonzero(np.isin(labels, np.asarray(labels_to_select, dtype=int)))
    if indices.size == 0:
        raise RuntimeError(f"SAM3D labels {labels_to_select} have no faces")
    return indices


def submesh_from_mask(mesh: trimesh.Trimesh, mask: np.ndarray) -> trimesh.Trimesh:
    face_ids = np.flatnonzero(mask)
    if face_ids.size == 0:
        raise RuntimeError("empty submesh mask")
    sub = mesh.submesh([face_ids], append=True, repair=False)
    if not isinstance(sub, trimesh.Trimesh):
        raise RuntimeError("submesh extraction failed")
    return sub


def pca_frame(points: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    center = points.mean(axis=0)
    centered = points - center
    cov = np.cov(centered.T)
    values, vectors = np.linalg.eigh(cov)
    order = np.argsort(values)[::-1]
    axes = vectors[:, order]
    if np.linalg.det(axes) < 0:
        axes[:, -1] *= -1
    local = centered @ axes
    return center, axes, local


def make_ergonomic_grip(
    *,
    selected: trimesh.Trimesh,
    variant: str,
    color: tuple[int, int, int, int],
) -> trimesh.Trimesh:
    """Create a compact grip-like replacement fitted to the selected bbox."""

    points = selected.vertices
    center, axes, local_points = pca_frame(points)
    local_min = local_points.min(axis=0)
    local_max = local_points.max(axis=0)
    extents = np.maximum(local_max - local_min, 1e-4)
    local_center = (local_min + local_max) * 0.5

    length = float(extents[0] * 0.96)
    radius_a = float(extents[1] * 0.48)
    radius_b = float(extents[2] * 0.48)
    if length < max(radius_a, radius_b):
        order = np.argsort(extents)[::-1]
        # Keep PCA axes but use the largest extent as length by permuting local generation axes.
        length = float(extents[order[0]] * 0.96)
        radius_a = float(extents[order[1]] * 0.48)
        radius_b = float(extents[order[2]] * 0.48)

    rings = 38
    segments = 32
    vertices: list[list[float]] = []
    faces: list[list[int]] = []

    for i in range(rings):
        t = i / (rings - 1)
        x = -length / 2 + t * length
        cap_taper = np.sin(np.pi * t) ** 0.32
        if variant == "gel":
            groove = 0.92 + 0.08 * np.sin(2 * np.pi * 5 * t)
        elif variant == "knurled":
            groove = 0.86 + 0.12 * np.sin(2 * np.pi * 7 * t)
        elif variant == "wood":
            groove = 0.94 + 0.05 * np.sin(2 * np.pi * 3 * t + 0.6)
        else:
            groove = 0.88 + 0.10 * np.sin(2 * np.pi * 4 * t)
        ra = radius_a * cap_taper * groove
        rb = radius_b * cap_taper * groove
        bend = 0.10 * extents[1] * np.sin(np.pi * (t - 0.15))
        for j in range(segments):
            a = 2 * np.pi * j / segments
            y = bend + ra * np.cos(a)
            z = rb * np.sin(a)
            vertices.append([x, y, z])

    for i in range(rings - 1):
        for j in range(segments):
            a = i * segments + j
            b = i * segments + (j + 1) % segments
            c = (i + 1) * segments + (j + 1) % segments
            d = (i + 1) * segments + j
            faces.append([a, b, c])
            faces.append([a, c, d])

    left_center = len(vertices)
    vertices.append([-length / 2, 0.0, 0.0])
    right_center = len(vertices)
    vertices.append([length / 2, 0.0, 0.0])
    for j in range(segments):
        faces.append([left_center, (j + 1) % segments, j])
        a = (rings - 1) * segments + j
        b = (rings - 1) * segments + (j + 1) % segments
        faces.append([right_center, a, b])

    verts = np.asarray(vertices, dtype=np.float64)
    # Place procedural local mesh into the selected part PCA frame.
    verts += local_center
    world = center + verts @ axes.T
    mesh = trimesh.Trimesh(vertices=world, faces=np.asarray(faces), process=False)
    mesh.visual.vertex_colors = np.tile(np.asarray(color, dtype=np.uint8), (len(mesh.vertices), 1))
    return mesh


def fit_external_replacement_to_selected(
    *,
    selected: trimesh.Trimesh,
    replacement: trimesh.Trimesh,
) -> trimesh.Trimesh:
    """PCA-fit an arbitrary replacement mesh into the selected part's socket.

    This intentionally operates in 3D, not by a 2D image mask: selected SAM3D
    faces define the target socket volume, then the generated candidate part is
    normalized and inserted into that local frame.
    """

    selected_center, selected_axes, selected_local = pca_frame(selected.vertices)
    selected_min = selected_local.min(axis=0)
    selected_max = selected_local.max(axis=0)
    selected_extents = np.maximum(selected_max - selected_min, 1e-4)
    selected_local_center = (selected_min + selected_max) * 0.5

    replacement_center, replacement_axes, replacement_local = pca_frame(replacement.vertices)
    del replacement_center  # coordinates are already centered in replacement_local
    del replacement_axes
    repl_min = replacement_local.min(axis=0)
    repl_max = replacement_local.max(axis=0)
    repl_extents = np.maximum(repl_max - repl_min, 1e-4)
    repl_local_center = (repl_min + repl_max) * 0.5

    # Non-uniform scaling is acceptable here because this is the socket-fit
    # stage. The generated standalone PBR mesh is also exported separately.
    scale = selected_extents / repl_extents * 0.92
    fitted_local = (replacement_local - repl_local_center) * scale + selected_local_center
    fitted_vertices = selected_center + fitted_local @ selected_axes.T

    fitted = replacement.copy()
    fitted.vertices = fitted_vertices
    return fitted


def color_for_variant(variant: str) -> tuple[int, int, int, int]:
    if variant == "gel":
        return (45, 145, 255, 210)
    if variant == "leather":
        return (116, 70, 38, 255)
    if variant == "wood":
        return (156, 92, 42, 255)
    if variant == "knurled":
        return (28, 30, 34, 255)
    return (50, 120, 220, 255)


def export_mesh(mesh: trimesh.Trimesh, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(path)


def with_vertex_color(mesh: trimesh.Trimesh, color: tuple[int, int, int, int]) -> trimesh.Trimesh:
    copy = mesh.copy()
    copy.visual.vertex_colors = np.tile(np.asarray(color, dtype=np.uint8), (len(copy.vertices), 1))
    return copy


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-mesh", required=True)
    parser.add_argument("--face-labels", required=True)
    parser.add_argument("--part-label", type=int, default=None)
    parser.add_argument(
        "--part-labels",
        default="",
        help="Comma-separated SAM3D labels to union into one semantic part, e.g. 13,16.",
    )
    parser.add_argument("--variant", choices=["gel", "leather", "wood", "knurled"], default="gel")
    parser.add_argument(
        "--replacement-mesh",
        default="",
        help="Optional generated replacement mesh to fit into the selected SAM3D part socket.",
    )
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    source_path = Path(args.source_mesh)
    labels_path = Path(args.face_labels)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    source = load_mesh(source_path)
    labels_to_select: list[int] = []
    if args.part_labels.strip():
        labels_to_select = [int(x.strip()) for x in args.part_labels.split(",") if x.strip()]
    elif args.part_label is not None:
        labels_to_select = [int(args.part_label)]
    else:
        raise RuntimeError("Either --part-label or --part-labels is required")

    selected_face_ids = face_indices_for_labels(labels_path, labels_to_select, len(source.faces))
    selected_mask = np.zeros(len(source.faces), dtype=bool)
    selected_mask[selected_face_ids] = True
    body_mask = ~selected_mask

    selected = submesh_from_mask(source, selected_mask)
    body = submesh_from_mask(source, body_mask)
    replacement_source = "procedural_smoke"
    if args.replacement_mesh.strip():
        replacement_source = str(Path(args.replacement_mesh))
        replacement_input = load_mesh(Path(args.replacement_mesh))
        replacement = fit_external_replacement_to_selected(
            selected=selected,
            replacement=replacement_input,
        )
    else:
        replacement = make_ergonomic_grip(
            selected=selected,
            variant=args.variant,
            color=color_for_variant(args.variant),
        )
    merged = trimesh.util.concatenate([body, replacement])
    preview_body = with_vertex_color(body, (55, 170, 245, 255))
    preview_replacement = with_vertex_color(replacement, color_for_variant(args.variant))
    preview_scene = trimesh.Scene()
    preview_scene.add_geometry(preview_body, geom_name="source_body_preserved_debug_blue")
    preview_scene.add_geometry(preview_replacement, geom_name=f"replacement_{args.variant}")

    selected_path = out_dir / "selected_original_part.glb"
    body_path = out_dir / "source_without_selected_part.glb"
    repl_path = out_dir / f"replacement_{args.variant}.glb"
    repl_fitted_obj = out_dir / f"replacement_{args.variant}_fitted.obj"
    merged_glb = out_dir / f"part_replaced_{args.variant}.glb"
    merged_obj = out_dir / f"part_replaced_{args.variant}.obj"
    preview_glb = out_dir / f"part_replaced_{args.variant}_debug_colors.glb"
    export_mesh(selected, selected_path)
    export_mesh(body, body_path)
    export_mesh(replacement, repl_path)
    export_mesh(replacement, repl_fitted_obj)
    export_mesh(merged, merged_glb)
    export_mesh(merged, merged_obj)
    preview_scene.export(preview_glb)

    selected_bounds = selected.bounds.tolist()
    replacement_bounds = replacement.bounds.tolist()
    report: dict[str, Any] = {
        "status": "completed",
        "method": (
            "3d_first_sam3d_cluster_socket_replacement_external_mesh"
            if args.replacement_mesh.strip()
            else "3d_first_sam3d_cluster_socket_replacement_procedural_smoke"
        ),
        "replacement_source": replacement_source,
        "source_mesh": str(source_path),
        "face_labels": str(labels_path),
        "part_labels": labels_to_select,
        "variant": args.variant,
        "source_faces": int(len(source.faces)),
        "selected_faces_removed": int(selected_face_ids.size),
        "body_faces_preserved": int(len(body.faces)),
        "replacement_faces": int(len(replacement.faces)),
        "merged_faces": int(len(merged.faces)),
        "selected_bounds": selected_bounds,
        "replacement_bounds": replacement_bounds,
        "outputs": {
            "selected_original_part_glb": str(selected_path),
            "source_without_selected_part_glb": str(body_path),
            "replacement_part_glb": str(repl_path),
            "replacement_part_fitted_obj": str(repl_fitted_obj),
            "merged_glb": str(merged_glb),
            "merged_obj": str(merged_obj),
            "debug_colored_preview_glb": str(preview_glb),
        },
        "guarantee": "Unselected source faces are copied from the original mesh; only faces with the selected SAM3D label are removed before inserting the replacement.",
    }
    (out_dir / "part_socket_replace_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(out_dir / "part_socket_replace_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
