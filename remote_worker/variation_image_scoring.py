"""Deterministic image-level QA for CreativeFlow variation candidates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageFilter, ImageOps


def _rgb(path: str | Path, size: tuple[int, int] | None = None) -> np.ndarray:
    image = Image.open(path).convert("RGB")
    if size and image.size != size:
        image = image.resize(size, Image.Resampling.LANCZOS)
    return np.asarray(image, dtype=np.float32) / 255.0


def _edge_map(array: np.ndarray) -> np.ndarray:
    gray = Image.fromarray(np.clip(array * 255.0, 0, 255).astype(np.uint8)).convert("RGB")
    edge = ImageOps.grayscale(gray).filter(ImageFilter.FIND_EDGES)
    values = np.asarray(ImageOps.autocontrast(edge), dtype=np.uint8)
    return values >= 52


def _edge_iou(a: np.ndarray, b: np.ndarray) -> float:
    ea, eb = _edge_map(a), _edge_map(b)
    union = np.logical_or(ea, eb).sum()
    if union <= 0:
        return 1.0
    return float(np.logical_and(ea, eb).sum() / union)


def _foreground_mask(array: np.ndarray) -> np.ndarray:
    """Estimate the studio foreground from border colors without segmentation."""
    border = np.concatenate(
        (array[0], array[-1], array[:, 0], array[:, -1]), axis=0
    )
    background = np.median(border, axis=0)
    distance = np.sqrt(np.square(array - background).sum(axis=2))
    return distance >= 0.12


def _chromatic_palette_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Histogram intersection over saturated foreground colors.

    Low Fidelity permits geometry to move, so pixelwise color comparison is
    inappropriate. This metric still rejects cases where a red scarf becomes
    blue or a black accessory becomes brown.
    """

    def histogram(array: np.ndarray) -> np.ndarray:
        image = Image.fromarray(np.clip(array * 255.0, 0, 255).astype(np.uint8))
        hsv = np.asarray(image.convert("HSV"), dtype=np.uint8)
        foreground = _foreground_mask(array)
        chromatic = foreground & (hsv[:, :, 1] >= 55) & (hsv[:, :, 2] >= 28)
        if not np.any(chromatic):
            return np.zeros(32, dtype=np.float64)
        hue_bins = np.minimum(hsv[:, :, 0] // 8, 31)
        values = hue_bins[chromatic]
        hist = np.bincount(values, minlength=32).astype(np.float64)
        return hist / max(1.0, hist.sum())

    left, right = histogram(a), histogram(b)
    if left.sum() == 0 and right.sum() == 0:
        return 1.0
    return float(np.minimum(left, right).sum())


def score_candidate_image(
    *,
    stage: str,
    source_image_path: str | Path,
    candidate_image_path: str | Path,
) -> dict[str, Any]:
    source_image = Image.open(source_image_path).convert("RGB")
    size = source_image.size
    source = np.asarray(source_image, dtype=np.float32) / 255.0
    candidate = _rgb(candidate_image_path, size=size)
    global_mae = float(np.abs(source - candidate).mean())
    edge_iou = _edge_iou(source, candidate)
    palette_similarity = _chromatic_palette_similarity(source, candidate)

    reasons: list[str] = []
    if stage == "low_fidelity":
        if global_mae < 0.035:
            reasons.append("global_form_change_too_small")
        if edge_iou > 0.94:
            reasons.append("silhouette_too_similar")
        if edge_iou < 0.10:
            reasons.append("source_identity_or_composition_lost")
    elif stage == "part":
        if global_mae < 0.025:
            reasons.append("selected_part_change_too_small")
        if edge_iou < 0.22:
            reasons.append("source_identity_or_composition_lost")
    elif stage == "texture":
        if global_mae < 0.025:
            reasons.append("material_change_too_small")
        if edge_iou < 0.42:
            reasons.append("geometry_edge_lock_failed")
    else:
        reasons.append(f"unsupported_stage:{stage}")

    return {
        "schema_version": "creativeflow.image-score.v1",
        "stage": stage,
        "mode": "advisory",
        "image_qa_passed": not reasons,
        "reasons": reasons,
        "metrics": {
            "global_mae": round(global_mae, 6),
            "edge_iou": round(edge_iou, 6),
            "chromatic_palette_similarity": round(palette_similarity, 6),
        },
    }


def pairwise_diversity(
    candidate_paths: list[str | Path],
    *,
    min_pair_mae: float = 0.018,
) -> dict[str, Any]:
    pairs: list[dict[str, Any]] = []
    passed = True
    arrays: list[np.ndarray] = []
    size: tuple[int, int] | None = None
    for path in candidate_paths:
        image = Image.open(path).convert("RGB")
        size = size or image.size
        arrays.append(_rgb(path, size=size))
    for left in range(len(arrays)):
        for right in range(left + 1, len(arrays)):
            mae = float(np.abs(arrays[left] - arrays[right]).mean())
            pair_passed = mae >= min_pair_mae
            passed = passed and pair_passed
            pairs.append(
                {"left": left, "right": right, "mae": round(mae, 6), "passed": pair_passed}
            )
    return {
        "schema_version": "creativeflow.pairwise-diversity.v1",
        "passed": passed,
        "threshold": min_pair_mae,
        "region": "full_image",
        "pairs": pairs,
    }
