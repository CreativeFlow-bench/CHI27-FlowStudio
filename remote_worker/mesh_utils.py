from __future__ import annotations

import math
import re
import struct
from pathlib import Path
from typing import Any


def files_root() -> Path:
    root = Path(__file__).resolve().parents[2] / "storage" / "files"
    root.mkdir(parents=True, exist_ok=True)
    return root


def parse_obj_vertices(text: str) -> list[list[float]]:
    vertices: list[list[float]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("v "):
            continue
        fields = line.split()
        if len(fields) < 4:
            continue
        try:
            vertices.append([float(fields[1]), float(fields[2]), float(fields[3])])
        except ValueError:
            continue
    return vertices


def parse_obj_faces(text: str) -> list[list[int]]:
    faces: list[list[int]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("f "):
            continue
        face = face_vertex_indices(line)
        if len(face) >= 3:
            faces.append(face)
    return faces


def obj_bbox(data: bytes) -> dict[str, list[float]]:
    vertices = parse_obj_vertices(data.decode("utf-8", errors="ignore"))
    if not vertices:
        raise ValueError("OBJ has no readable vertices")
    return {
        "min": [min(point[axis] for point in vertices) for axis in range(3)],
        "max": [max(point[axis] for point in vertices) for axis in range(3)],
    }


def bbox_metrics(data: bytes) -> dict[str, Any]:
    text = data.decode("utf-8", errors="ignore")
    bbox = obj_bbox(data)
    extent = [bbox["max"][axis] - bbox["min"][axis] for axis in range(3)]
    center = [(bbox["min"][axis] + bbox["max"][axis]) / 2 for axis in range(3)]
    return {
        "bbox3d": bbox,
        "extent": extent,
        "center": center,
        "vertex_count": len(parse_obj_vertices(text)),
        "face_count": len(parse_obj_faces(text)),
    }


def normalize_obj(data: bytes) -> tuple[str, dict[str, Any]]:
    metrics = bbox_metrics(data)
    center = metrics["center"]
    max_extent = max(metrics["extent"] or [1.0]) or 1.0
    transform = {
        "scale": 1.0 / max_extent,
        "translation": [-(center[axis] / max_extent) for axis in range(3)],
    }
    return transform_obj(data, transform), {**metrics, "normalization_transform": transform}


def build_bbox_fit_result(
    source_bbox: dict[str, list[float]],
    target_bbox: dict[str, list[float]],
    policy: str,
    target_part_id: str | None = None,
) -> dict[str, Any]:
    source_min = source_bbox["min"]
    source_max = source_bbox["max"]
    target_min = target_bbox["min"]
    target_max = target_bbox["max"]
    source_extent = [max(1e-6, source_max[i] - source_min[i]) for i in range(3)]
    target_extent = [max(1e-6, target_max[i] - target_min[i]) for i in range(3)]
    if policy == "bbox_axis_aligned":
        scale: float | list[float] = [target_extent[i] / source_extent[i] for i in range(3)]
        scaled_extent = target_extent
    else:
        uniform = min(target_extent[i] / source_extent[i] for i in range(3))
        scale = uniform
        scaled_extent = [source_extent[i] * uniform for i in range(3)]
    source_center = [(source_min[i] + source_max[i]) / 2 for i in range(3)]
    target_center = [(target_min[i] + target_max[i]) / 2 for i in range(3)]
    scaled_center = [
        source_center[i] * (scale[i] if isinstance(scale, list) else scale)
        for i in range(3)
    ]
    translation = [target_center[i] - scaled_center[i] for i in range(3)]
    extent_similarity = extent_similarity_score(scaled_extent, target_extent)
    return {
        "status": "transform_ready",
        "policy": policy,
        "target_part_id": target_part_id,
        "source_bbox": source_bbox,
        "target_bbox": target_bbox,
        "transform": {"scale": scale, "translation": translation},
        "quality": {
            "bbox_extent_similarity": extent_similarity,
            "normalized_center_error": 0.0,
            "volume_ratio": volume_ratio(scaled_extent, target_extent),
        },
    }


def transform_obj(data: bytes, transform: dict[str, Any]) -> str:
    scale = transform.get("scale", 1.0)
    translation = transform.get("translation", [0.0, 0.0, 0.0])
    if not isinstance(translation, list) or len(translation) != 3:
        raise ValueError("Transform translation must be a 3D vector")
    output: list[str] = []
    for raw_line in data.decode("utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line.startswith("v "):
            output.append(raw_line)
            continue
        fields = line.split()
        if len(fields) < 4:
            output.append(raw_line)
            continue
        try:
            coords = [float(fields[1]), float(fields[2]), float(fields[3])]
        except ValueError:
            output.append(raw_line)
            continue
        if isinstance(scale, list):
            scaled = [coords[i] * float(scale[i]) for i in range(3)]
        else:
            scaled = [coords[i] * float(scale) for i in range(3)]
        moved = [scaled[i] + float(translation[i]) for i in range(3)]
        suffix = " ".join(fields[4:])
        vertex = f"v {format_obj_float(moved[0])} {format_obj_float(moved[1])} {format_obj_float(moved[2])}"
        output.append(f"{vertex} {suffix}".rstrip())
    return "\n".join(output) + "\n"


def extract_faces_obj(data: bytes, face_indices: set[int]) -> tuple[str, dict[str, Any]]:
    text = data.decode("utf-8", errors="ignore")
    vertices = parse_obj_vertices(text)
    selected_faces: list[list[int]] = []
    face_index = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("f "):
            continue
        if face_index in face_indices:
            face = face_vertex_indices(line)
            if len(face) >= 3:
                selected_faces.append(face)
        face_index += 1
    return build_obj_from_faces(vertices, selected_faces), {
        "selected_face_count": len(selected_faces),
        "source_face_count": face_index,
        "selected_vertex_count": len({idx for face in selected_faces for idx in face}),
    }


def extract_labeled_region_obj(
    data: bytes,
    labels: list[int],
    cluster_id: int,
) -> tuple[str, dict[str, Any]]:
    selected = {index for index, label in enumerate(labels) if label == cluster_id}
    obj_text, metrics = extract_faces_obj(data, selected)
    boundary = boundary_metrics_for_cluster(data.decode("utf-8", errors="ignore"), labels, cluster_id)
    return obj_text, {
        **metrics,
        "cluster_id": cluster_id,
        "labeled_face_count": len(labels),
        "boundary_edge_count": boundary["boundary_edge_count"],
        "boundary_centroid": boundary["boundary_centroid"],
    }


def build_obj_from_faces(vertices: list[list[float]], faces: list[list[int]]) -> str:
    used = sorted({idx for face in faces for idx in face if idx > 0})
    remap = {old: new for new, old in enumerate(used, start=1)}
    output = ["# FlowStudio extracted OBJ region"]
    for old in used:
        point = vertices[old - 1]
        output.append(f"v {format_obj_float(point[0])} {format_obj_float(point[1])} {format_obj_float(point[2])}")
    for face in faces:
        remapped = [str(remap[idx]) for idx in face if idx in remap]
        if len(remapped) >= 3:
            output.append("f " + " ".join(remapped))
    return "\n".join(output) + "\n"


def remove_labeled_faces(data: bytes, labels: list[int], cluster_id: int) -> tuple[bytes, dict[str, Any]]:
    output: list[str] = []
    face_index = 0
    removed = 0
    text = data.decode("utf-8", errors="ignore")
    boundary = boundary_metrics_for_cluster(text, labels, cluster_id)
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("f "):
            label = labels[face_index] if face_index < len(labels) else None
            face_index += 1
            if label == cluster_id:
                removed += 1
                continue
        output.append(raw_line)
    return ("\n".join(output) + "\n").encode("utf-8"), {
        "removed_source_face_count": removed,
        "source_face_count": face_index,
        "boundary_edge_count": boundary["boundary_edge_count"],
        "source_boundary_centroid": boundary["boundary_centroid"],
    }


def merge_obj_pair(source_obj: bytes, fitted_obj: bytes, note: str) -> str:
    source_text = source_obj.decode("utf-8", errors="ignore")
    fitted_text = fitted_obj.decode("utf-8", errors="ignore")
    offset = sum(1 for line in source_text.splitlines() if line.strip().startswith("v "))
    return "\n".join(
        [
            "# FlowStudio assembly preview.",
            f"# {note}",
            source_text.rstrip(),
            "o flowstudio_fitted_candidate",
            offset_obj_faces(fitted_text, offset).rstrip(),
            "",
        ]
    )


def boundary_metrics_for_cluster(text: str, labels: list[int], cluster_id: int) -> dict[str, Any]:
    vertices_by_index = obj_vertices_by_index(text)
    edge_labels: dict[tuple[int, int], set[int]] = {}
    face_index = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("f "):
            continue
        label = labels[face_index] if face_index < len(labels) else None
        face_index += 1
        vertices = face_vertex_indices(line)
        if label is None or len(vertices) < 2:
            continue
        for index, start in enumerate(vertices):
            end = vertices[(index + 1) % len(vertices)]
            if start == end:
                continue
            edge = tuple(sorted((start, end)))
            edge_labels.setdefault(edge, set()).add(label)
    boundary_edges = [
        edge
        for edge, labels_for_edge in edge_labels.items()
        if cluster_id in labels_for_edge and any(label != cluster_id for label in labels_for_edge)
    ]
    return {
        "boundary_edge_count": len(boundary_edges),
        "boundary_centroid": edge_vertex_centroid(boundary_edges, vertices_by_index),
    }


def open_boundary_metrics(text: str) -> dict[str, Any]:
    vertices_by_index = obj_vertices_by_index(text)
    edge_counts: dict[tuple[int, int], int] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("f "):
            continue
        vertices = face_vertex_indices(line)
        for index, start in enumerate(vertices):
            end = vertices[(index + 1) % len(vertices)]
            if start == end:
                continue
            edge = tuple(sorted((start, end)))
            edge_counts[edge] = edge_counts.get(edge, 0) + 1
    edges = [edge for edge, count in edge_counts.items() if count == 1]
    return {
        "boundary_edge_count": len(edges),
        "boundary_centroid": edge_vertex_centroid(edges, vertices_by_index),
    }


def parse_npy_ints(data: bytes) -> list[int]:
    if not data.startswith(b"\x93NUMPY"):
        raise ValueError("Not a numpy .npy file")
    major = data[6]
    if major == 1:
        header_len = struct.unpack("<H", data[8:10])[0]
        header_start = 10
    elif major in {2, 3}:
        header_len = struct.unpack("<I", data[8:12])[0]
        header_start = 12
    else:
        raise ValueError(f"Unsupported .npy version: {major}")
    header = data[header_start : header_start + header_len].decode("latin1")
    descr_match = re.search(r"'descr': '([^']+)'", header)
    shape_match = re.search(r"'shape': \(([^)]*)\)", header)
    fortran_match = re.search(r"'fortran_order': (False|True)", header)
    if not descr_match or not shape_match or not fortran_match:
        raise ValueError("Unsupported .npy header")
    if fortran_match.group(1) != "False":
        raise ValueError("Fortran-order .npy labels are not supported")
    descr = descr_match.group(1)
    dtype_map = {
        "<i1": ("b", 1),
        "|i1": ("b", 1),
        "<u1": ("B", 1),
        "|u1": ("B", 1),
        "<i2": ("h", 2),
        "<u2": ("H", 2),
        "<i4": ("i", 4),
        "<u4": ("I", 4),
        "<i8": ("q", 8),
        "<u8": ("Q", 8),
    }
    if descr not in dtype_map:
        raise ValueError(f"Unsupported .npy dtype: {descr}")
    fmt, item_size = dtype_map[descr]
    dims = [int(item.strip()) for item in shape_match.group(1).split(",") if item.strip()]
    count = math.prod(dims) if dims else 1
    payload = data[header_start + header_len :]
    if len(payload) < count * item_size:
        raise ValueError("Truncated .npy payload")
    return [
        int(struct.unpack_from(f"<{fmt}", payload, offset)[0])
        for offset in range(0, count * item_size, item_size)
    ]


def cluster_id_from_part(part: dict[str, Any] | None) -> int | None:
    if not isinstance(part, dict):
        return None
    metadata = part.get("metadata") if isinstance(part.get("metadata"), dict) else part
    raw = metadata.get("source_part_id") or metadata.get("raw_cluster_id") or metadata.get("cluster_id")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        match = re.search(r"(-?\d+)$", raw)
        if match:
            return int(match.group(1))
    return None


def face_labels_path_from_part(part: dict[str, Any] | None) -> str | None:
    if not isinstance(part, dict):
        return None
    metadata = part.get("metadata") if isinstance(part.get("metadata"), dict) else part
    value = metadata.get("face_labels_path")
    return str(value) if value else None


def bbox_from_part(part: dict[str, Any] | None) -> dict[str, list[float]] | None:
    if not isinstance(part, dict):
        return None
    metadata = part.get("metadata") if isinstance(part.get("metadata"), dict) else part
    value = metadata.get("bbox3d") or part.get("bbox3d")
    if isinstance(value, dict):
        mins = value.get("min") or value.get("mins")
        maxs = value.get("max") or value.get("maxs")
        if isinstance(mins, list) and isinstance(maxs, list) and len(mins) == 3 and len(maxs) == 3:
            return {"min": [float(item) for item in mins], "max": [float(item) for item in maxs]}
    return None


def face_vertex_indices(face_line: str) -> list[int]:
    vertices = []
    for token in face_line.split()[1:]:
        head = token.split("/")[0]
        try:
            value = int(head)
        except ValueError:
            continue
        if value > 0:
            vertices.append(value)
    return vertices


def obj_vertices_by_index(text: str) -> dict[int, list[float]]:
    return {index: point for index, point in enumerate(parse_obj_vertices(text), start=1)}


def edge_vertex_centroid(
    edges: list[tuple[int, int]],
    vertices_by_index: dict[int, list[float]],
) -> list[float] | None:
    vertex_ids = sorted({vertex for edge in edges for vertex in edge})
    points = [vertices_by_index[vertex] for vertex in vertex_ids if vertex in vertices_by_index]
    if not points:
        return None
    return [round(sum(point[axis] for point in points) / len(points), 6) for axis in range(3)]


def offset_obj_faces(text: str, vertex_offset: int) -> str:
    output: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("f "):
            output.append(raw_line)
            continue
        tokens = line.split()
        output.append(" ".join([tokens[0], *[offset_face_token(token, vertex_offset) for token in tokens[1:]]]))
    return "\n".join(output) + "\n"


def offset_face_token(token: str, vertex_offset: int) -> str:
    parts = token.split("/")
    if not parts or not parts[0]:
        return token
    try:
        index = int(parts[0])
    except ValueError:
        return token
    if index > 0:
        parts[0] = str(index + vertex_offset)
    return "/".join(parts)


def extent_similarity_score(source: list[float], target: list[float]) -> float:
    scores = [
        min(max(source[i], 1e-6), max(target[i], 1e-6)) / max(max(source[i], 1e-6), max(target[i], 1e-6))
        for i in range(3)
    ]
    return round(sum(scores) / 3, 4)


def volume_ratio(source: list[float], target: list[float]) -> float:
    source_volume = max(1e-9, source[0] * source[1] * source[2])
    target_volume = max(1e-9, target[0] * target[1] * target[2])
    return round(source_volume / target_volume, 4)


def format_obj_float(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")
