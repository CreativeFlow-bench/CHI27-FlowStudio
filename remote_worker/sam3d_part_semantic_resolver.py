#!/usr/bin/env python3
"""Resolve a user-selected SAM3D cluster into source-grounded part semantics."""

from __future__ import annotations

import argparse
import base64
import io
import json
import math
import os
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


def _binary(path: str | Path, size: tuple[int, int]) -> np.ndarray:
    image = Image.open(path).convert("L").resize(size, Image.Resampling.NEAREST)
    return np.asarray(image, dtype=np.uint8) >= 128


def _bbox(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)


def _bbox_iou(left: tuple[int, int, int, int] | None, right: tuple[int, int, int, int] | None) -> float:
    if not left or not right:
        return 0.0
    x1, y1 = max(left[0], right[0]), max(left[1], right[1])
    x2, y2 = min(left[2], right[2]), min(left[3], right[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    a = max(0, left[2] - left[0]) * max(0, left[3] - left[1])
    b = max(0, right[2] - right[0]) * max(0, right[3] - right[1])
    return float(inter / max(1, a + b - inter))


def _centroid(mask: np.ndarray) -> tuple[float, float]:
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return 0.5, 0.5
    return float(xs.mean() / mask.shape[1]), float(ys.mean() / mask.shape[0])


def match_cluster(
    manifest: dict[str, Any], brush_mask_path: str, image_size: tuple[int, int]
) -> tuple[dict[str, Any], str, dict[str, float]]:
    brush = _binary(brush_mask_path, image_size)
    brush_bbox = _bbox(brush)
    brush_center = _centroid(brush)
    ranked: list[tuple[float, dict[str, Any], str, dict[str, float]]] = []
    for part in manifest.get("parts", []):
        for projection_path in part.get("projection_masks", []):
            path = Path(str(projection_path))
            if not path.is_file():
                continue
            projection = _binary(path, image_size)
            union = np.logical_or(brush, projection).sum()
            pixel_iou = float(np.logical_and(brush, projection).sum() / max(1, union))
            bbox_iou = _bbox_iou(brush_bbox, _bbox(projection))
            center = _centroid(projection)
            center_distance = math.dist(brush_center, center)
            center_score = max(0.0, 1.0 - center_distance / 0.45)
            area_ratio = min(brush.sum(), projection.sum()) / max(1, max(brush.sum(), projection.sum()))
            score = 0.35 * pixel_iou + 0.30 * bbox_iou + 0.25 * center_score + 0.10 * area_ratio
            metrics = {
                "pixel_iou": round(pixel_iou, 6),
                "bbox_iou": round(bbox_iou, 6),
                "center_score": round(center_score, 6),
                "area_ratio": round(float(area_ratio), 6),
                "match_score": round(float(score), 6),
            }
            ranked.append((score, part, str(path), metrics))
    if not ranked:
        raise RuntimeError("SAM3D manifest contains no usable cluster projection masks")
    ranked.sort(key=lambda item: (-item[0], -int(item[1].get("face_count") or 0)))
    _, part, path, metrics = ranked[0]
    return part, path, metrics


def _data_url(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _semantic_overlay(source_path: str, brush_path: str, *, draw_box: bool = True) -> Image.Image:
    source = Image.open(source_path).convert("RGB")
    if not draw_box:
        return source
    mask = Image.open(brush_path).convert("L").resize(source.size, Image.Resampling.NEAREST)
    # Never tint the selected pixels: the VLM must read their actual source
    # color and material.  A tinted semantic overlay was previously mistaken
    # for red plastic.  The contour is sufficient to communicate selection.
    overlay = source.copy()
    draw = ImageDraw.Draw(overlay)
    bbox = mask.point(lambda value: 255 if value >= 128 else 0).getbbox()
    if bbox:
        draw.rectangle(bbox, outline=(0, 255, 255), width=max(3, source.width // 120))
    return overlay


def resolve_semantics(
    *,
    source_image_path: str,
    brush_mask_path: str,
    part: dict[str, Any],
    projection_mask_path: str,
    match_metrics: dict[str, float],
    api_base: str,
    model: str,
    draw_overlay_box: bool = True,
) -> dict[str, Any]:
    overlay = _semantic_overlay(source_image_path, brush_mask_path, draw_box=draw_overlay_box)
    projection = Image.open(projection_mask_path).convert("RGB")
    first_image_description = (
        "The first image is the unmodified complete source object; a cyan rectangle marks the user-selected region."
        if draw_overlay_box
        else "The first image is the unmodified complete source object, with no annotation overlay."
    )
    prompt = f"""
{first_image_description}
The second image is the matched SAM3D face-cluster projection mask.
SAM3D cluster metadata: {json.dumps(part, ensure_ascii=False)}
projection matching metrics: {json.dumps(match_metrics)}

Name and describe only the selected physical part. Return strict JSON:
{{
  "canonical_name": "concrete singular part noun",
  "semantic_role": "role relative to the whole object",
  "shape": "short 3D shape description",
  "visible_color": "literal color observed in the complete source image",
  "material": "visible current material",
  "attachment": "how it connects to its parent/socket",
  "function": "visual or functional role",
  "confidence": 0.0,
  "evidence": ["visible evidence"]
}}
Do not use labels such as part N, region, component, or object.
Use the complete source image as the authority for color and material; the
binary SAM3D projection conveys geometry only and must not be interpreted as
surface appearance. Do not infer the overlay highlight color as the material.
If the source object is an untextured white/gray mesh render, report the visible
material as untextured clay/ceramic-like geometry rather than inventing color.
""".strip()
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You resolve SAM3D face clusters into concrete part semantics. Return strict JSON only.",
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": _data_url(overlay)}},
                    {"type": "image_url", "image_url": {"url": _data_url(projection)}},
                ],
            },
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        api_base.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=120) as response:
        response_payload = json.loads(response.read().decode("utf-8"))
    result = json.loads(response_payload["choices"][0]["message"]["content"])
    required = ("canonical_name", "semantic_role", "shape", "attachment", "confidence")
    missing = [key for key in required if not result.get(key)]
    if missing:
        raise RuntimeError(f"part semantic resolver missing: {', '.join(missing)}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--source-image", required=True)
    parser.add_argument("--brush-mask", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--no-overlay-box",
        action="store_true",
        help="Use an unannotated source image; useful when selecting an existing SAM3D cluster directly.",
    )
    parser.add_argument(
        "--api-base",
        default=os.getenv("CF_VISION_LLM_API_BASE", "http://127.0.0.1:18084/v1"),
    )
    parser.add_argument(
        "--model", default=os.getenv("CF_VISION_LLM_MODEL", "qwen3-planner")
    )
    args = parser.parse_args()
    manifest_path = Path(args.manifest).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_size = Image.open(args.source_image).size
    part, projection_path, match_metrics = match_cluster(
        manifest, args.brush_mask, source_size
    )
    semantics = resolve_semantics(
        source_image_path=args.source_image,
        brush_mask_path=args.brush_mask,
        part=part,
        projection_mask_path=projection_path,
        match_metrics=match_metrics,
        api_base=args.api_base,
        model=args.model,
        draw_overlay_box=not args.no_overlay_box,
    )
    vlm_confidence = max(0.0, min(1.0, float(semantics.get("confidence") or 0.0)))
    # Cluster matching and semantic naming are separate evidence channels.
    combined_confidence = 0.55 * vlm_confidence + 0.45 * min(
        1.0, float(match_metrics["match_score"]) / 0.35
    )
    result = {
        "schema_version": "creativeflow.sam3d-part-semantics.v1",
        "part_id": part["part_id"],
        "cluster_id": part["cluster_id"],
        "source_part_id": part.get("source_part_id"),
        "canonical_name": semantics["canonical_name"],
        "semantic_role": semantics["semantic_role"],
        "shape": semantics["shape"],
        "visible_color": semantics.get("visible_color", ""),
        "material": semantics.get("material", ""),
        "attachment": semantics["attachment"],
        "function": semantics.get("function", ""),
        "confidence": round(combined_confidence, 6),
        "vlm_confidence": vlm_confidence,
        "match_metrics": match_metrics,
        "bbox3d": part.get("bbox3d"),
        "face_count": part.get("face_count"),
        "projection_mask_path": projection_path,
        "face_labels_path": manifest.get("face_labels_path"),
        "sam3d_manifest_path": str(manifest_path),
        "evidence_views": [projection_path, args.source_image],
        "evidence": semantics.get("evidence") or [],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
