"""Target fusion: merge ②③ target votes + IR prior, modulated by ① cognition.

Produces the planner's SemanticTarget[] output (with semantics), or marks
requires_clarification when conflicts / hesitation require a user decision.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4
import re

from app.models import CognitionOutput, SupervisorVote
from app.models.semantic import SemanticTarget, SemanticTargetSemantic


LEVELS = ["whole", "silhouette", "part", "material_region"]


def _best_part(part_candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    rows = [item for item in part_candidates if isinstance(item, dict)]
    if not rows:
        return None
    return max(rows, key=lambda item: float(item.get("score") or 0))


def _best_material(material_candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    rows = [item for item in material_candidates if isinstance(item, dict)]
    if not rows:
        return None
    return max(rows, key=lambda item: float(item.get("score") or 0))


def fuse_targets(
    *,
    gui: SupervisorVote,
    semantic: SupervisorVote,
    cognition: CognitionOutput,
    ir_prior: dict[str, Any],
    asset_id: str,
    features: dict[str, Any],
) -> list[SemanticTarget]:
    ir_levels = ir_prior.get("level_scores") if isinstance(ir_prior.get("level_scores"), dict) else {}
    level_scores: dict[str, float] = {}
    for level in LEVELS:
        raw = 0.6 * float(gui.level_scores.get(level) or 0) + 0.4 * float(semantic.level_scores.get(level) or 0)
        ir_bonus = float(ir_levels.get(level) or 0) * 0.25
        level_scores[level] = (raw + ir_bonus) * cognition.confidence_modifier

    # Conflict: GUI interacts with part A, language names part B.
    gui_part = _best_part(gui.part_candidates)
    sem_part = _best_part(semantic.part_candidates)
    conflict = None
    if gui_part and sem_part:
        gui_key = str(gui_part.get("part_id") or gui_part.get("label_en") or gui_part.get("label_zh") or "")
        sem_key = str(sem_part.get("part_id") or sem_part.get("label_en") or sem_part.get("label_zh") or "")
        if gui_key and sem_key and gui_key != sem_key:
            conflict = f"gui_target:{gui_key} vs semantic_target:{sem_key}"

    require_clarification = bool(conflict) or cognition.require_clarification
    ranked_levels = sorted(level_scores.items(), key=lambda item: item[1], reverse=True)
    targets: list[SemanticTarget] = []
    seen_levels: set[str] = set()

    # Merge part candidates by identity.
    part_rows: dict[str, dict[str, Any]] = {}
    for item in [*(gui.part_candidates or []), *(semantic.part_candidates or [])]:
        if not isinstance(item, dict):
            continue
        part_id = str(item.get("part_id") or "")
        label_en = str(item.get("label_en") or "")
        label_zh = str(item.get("label_zh") or "")
        canonical = re.sub(r"^part_", "", (label_en or part_id)).strip().lower()
        key = canonical or label_zh
        if not key:
            continue
        existing = part_rows.get(key)
        if existing is None:
            part_rows[key] = dict(item)
        else:
            existing["score"] = float(existing.get("score") or 0) + float(item.get("score") or 0) * 0.4
            existing["evidence"] = [
                *existing.get("evidence", []),
                *(item.get("evidence", []) if isinstance(item.get("evidence"), list) else []),
            ]
            if not existing.get("label_zh") and label_zh:
                existing["label_zh"] = label_zh
            if not existing.get("label_en") and label_en:
                existing["label_en"] = label_en
            if not existing.get("part_id") and part_id:
                existing["part_id"] = part_id
    merged_parts = list(part_rows.values())

    for level, score in ranked_levels:
        if score <= 0.2 or level in seen_levels:
            continue
        seen_levels.add(level)
        semantic_block = SemanticTargetSemantic()
        operation_hint = semantic.operation_hint
        evidence: list[str] = []
        supervision_sources = {
            "gui_interaction": round(float(gui.level_scores.get(level) or 0), 3),
            "semantic_language": round(float(semantic.level_scores.get(level) or 0), 3),
            "cognition_modifier": cognition.confidence_modifier,
            "ir_prior": round(float(ir_levels.get(level) or 0), 3),
        }
        if level == "part":
            part = _best_part(merged_parts)
            gui_best_part = _best_part(gui.part_candidates)
            semantic_best_part = _best_part(semantic.part_candidates)
            if part:
                semantic_block.part_id = (
                    str(part.get("part_id") or gui_best_part.get("part_id") if isinstance(gui_best_part, dict) else "") or None
                )
                semantic_block.label_zh = (
                    str(
                        (semantic_best_part.get("label_zh") if isinstance(semantic_best_part, dict) else None)
                        or part.get("label_zh")
                        or ""
                    )
                    or None
                )
                semantic_block.label_en = (
                    str(
                        (semantic_best_part.get("label_en") if isinstance(semantic_best_part, dict) else None)
                        or part.get("label_en")
                        or ""
                    )
                    or None
                )
                semantic_block.semantic_role = str(part.get("role") or "") or None
                evidence = [str(item) for item in part.get("evidence", []) if isinstance(item, str)]
                operation_hint = operation_hint or (
                    "deform" if "deform" in str(part.get("role") or "") else None
                )
        elif level == "material_region":
            material = _best_material(semantic.material_candidates)
            if material:
                semantic_block.label_zh = str(material.get("label_zh") or "") or None
                semantic_block.semantic_role = str(material.get("role") or "") or None
                evidence = [str(item) for item in material.get("evidence", []) if isinstance(item, str)]
            operation_hint = operation_hint or "finish"
        elif level == "silhouette":
            semantic_block.label_zh = "整体轮廓"
            semantic_block.label_en = "whole silhouette"
            operation_hint = operation_hint or "deform"
            evidence = [*gui.silhouette_evidence, *semantic.silhouette_evidence]
        else:  # whole
            semantic_block.label_zh = "整体"
            semantic_block.label_en = "whole object"
            operation_hint = operation_hint or "deform"
            evidence = []
        evidence = evidence or [f"fused_level:{level}"]
        targets.append(
            SemanticTarget(
                target_id=f"tgt_{uuid4().hex[:8]}",
                level=level,  # type: ignore[arg-type]
                semantic=semantic_block,
                operation_hint=operation_hint,
                confidence=round(max(0.0, min(1.0, score)), 3),
                evidence=evidence[:8],
                supervision_sources=supervision_sources,
                kg_ready=False,
                requires_clarification=require_clarification,
            )
        )
        if len(targets) >= 3:
            break
    return targets
