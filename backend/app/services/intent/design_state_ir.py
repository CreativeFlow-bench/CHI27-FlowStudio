from __future__ import annotations

import json
import math
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_IR_PATH = REPO_ROOT / "intentdatabase" / "cleaned" / "dsir_eval_episodes.json"
LEGACY_IR_PATH = REPO_ROOT / "intentdatabase" / "cleaned" / "design_state_ir_retrieval.jsonl"

STATE_4 = {
    "early_exploration": "Exploration",
    "coarse_forming": "Formation",
    "local_refinement": "Refinement",
    "relationship_adjustment": "Refinement",
    "material_refinement": "Refinement",
    "evaluation": "Evaluation",
}
HIERARCHY_3 = {
    "generate_contour_variants": "Silhouette",
    "generate_local_variants": "Part",
    "generate_material_variants": "Material",
}
CODING_STATE_TO_HIERARCHY = {
    "early_exploration": "Silhouette",
    "coarse_forming": "Silhouette",
    "local_refinement": "Part",
    "relationship_adjustment": "Part",
    "material_refinement": "Material",
}
DIM1_DWELL = {"pause_hover", "long_compare"}
DIM2_HESITATION = {"undo_redo_loop", "stuck_uncertain"}
DIM3_SPATIAL = {"select_part", "select_object", "small_brush", "large_brush", "form_change"}
DIM4_VIEWPORT = {"global_orbit", "multi_view_check", "local_zoom", "zoom_out"}
DIM6_SKETCH = {"match_reference"}
SIGNAL_WEIGHTS = (1.4, 1.4, 1.5, 1.5, 0.0, 1.0)
HYBRID_ALPHA = 0.5
SCORE_SCALE = 4.0
IR_POOL_K = 20
VOTE_K = 3
HIERARCHY_TO_LEVEL = {"Silhouette": "silhouette", "Part": "part", "Material": "material_region"}
HIERARCHY_TO_SCOPE = {"Silhouette": "whole_object", "Part": "part_or_region", "Material": "material_surface"}
HIERARCHY_TO_AXES = {
    "Silhouette": ["Structural", "Aesthetic"],
    "Part": ["Structural", "Functional"],
    "Material": ["Aesthetic", "Functional"],
}


@dataclass(frozen=True)
class DesignStateIRMatch:
    ir_id: str
    case_id: str
    score: float
    design_state: str
    route: str
    signals: list[str]
    scope_hint: str
    target_level: str
    recommended_axes: list[str]
    evidence_strength: str
    text: str
    confidence: float
    vector_score: float
    signal_overlap: list[str]
    term_overlap: list[str]
    scope_match: bool
    hierarchy: str = ""
    content_score: float = 0.0

    def to_feature(self) -> dict[str, Any]:
        return {
            "ir_id": self.ir_id,
            "case_id": self.case_id,
            "score": round(self.score, 4),
            "design_state": self.design_state,
            "route": self.route,
            "signals": self.signals,
            "scope_hint": self.scope_hint,
            "target_level": self.target_level,
            "recommended_axes": self.recommended_axes,
            "evidence_strength": self.evidence_strength,
            "text": self.text,
            "confidence": round(self.confidence, 4),
            "vector_score": round(self.vector_score, 4),
            "signal_overlap": self.signal_overlap,
            "term_overlap": self.term_overlap[:12],
            "scope_match": self.scope_match,
            "hierarchy": self.hierarchy,
            "content_score": round(self.content_score, 4),
        }


class DesignStateIRRetriever:
    def __init__(self, path: Path | None = None, limit: int = 250) -> None:
        self.path = path or (DEFAULT_IR_PATH if DEFAULT_IR_PATH.exists() else LEGACY_IR_PATH)
        self.rows = self._load_rows(limit)

    @property
    def ready(self) -> bool:
        return bool(self.rows)

    def retrieve(self, features: dict[str, object], top_k: int = 3) -> list[DesignStateIRMatch]:
        query = self._query_ir(features)
        query_signals = set(query["signal_codes"])
        query_signal = query["signal_vector"]
        query_scope = query["scope_hint"]
        scored: list[DesignStateIRMatch] = []
        for row in self.rows:
            row_signals = set(row.get("signals") or [])
            signal_overlap = sorted(query_signals & row_signals)
            label_overlap = self._label_overlap(query, row)
            signal_score = self._vector_cosine(query_signal, row["_signal_vector"])
            code_score = self._jaccard(query_signals, row_signals)
            wanted = sum(1 for key in ("gt_state", "gt_hierarchy", "route") if query.get(key))
            label_score = len(label_overlap) / wanted if wanted else 0.0
            vector_score = signal_score + HYBRID_ALPHA * code_score + HYBRID_ALPHA * label_score
            scope_match = bool(query_scope and query_scope == row.get("scope_hint"))
            if vector_score <= 0 and not signal_overlap and not label_overlap:
                continue
            score = vector_score * SCORE_SCALE
            if scope_match:
                score += 0.15
            confidence = min(0.97, max(0.05, vector_score / (vector_score + 1.0)))
            scored.append(
                DesignStateIRMatch(
                    ir_id=str(row.get("ir_id") or ""),
                    case_id=str(row.get("case_id") or ""),
                    score=score,
                    design_state=str(row.get("design_state") or "unknown"),
                    route=str(row.get("route") or "unknown"),
                    signals=[str(value) for value in row.get("signals") or []],
                    scope_hint=str(row.get("scope_hint") or "unknown"),
                    target_level=str(row.get("target_level") or "unknown"),
                    recommended_axes=[str(value) for value in row.get("recommended_axes") or []],
                    evidence_strength=str(row.get("evidence_strength") or "low"),
                    text=str(row.get("text") or ""),
                    confidence=confidence,
                    vector_score=vector_score,
                    signal_overlap=signal_overlap,
                    term_overlap=label_overlap,
                    scope_match=scope_match,
                    hierarchy=str(row.get("hierarchy") or ""),
                )
            )
        return sorted(scored, key=lambda item: item.score, reverse=True)[: max(1, top_k)]

    def annotate_content(
        self,
        matches: list[DesignStateIRMatch],
        features: dict[str, object],
    ) -> list[DesignStateIRMatch]:
        query = str(features.get("intent_text") or features.get("text") or "")
        query_grams = self._char_ngrams(query)
        return [
            replace(
                match,
                content_score=self._set_cosine(query_grams, self._char_ngrams(match.text)),
            )
            for match in matches
        ]

    def split_retrieve(
        self,
        features: dict[str, object],
        pool_k: int = IR_POOL_K,
        vote_k: int = VOTE_K,
    ) -> tuple[list[DesignStateIRMatch], list[DesignStateIRMatch], dict[str, Any]]:
        pool = self.annotate_content(self.retrieve(features, top_k=pool_k), features)
        ir_top = pool[:vote_k]
        content_top = sorted(pool, key=lambda item: item.content_score, reverse=True)[:vote_k]
        has_content = any(item.content_score > 0 for item in content_top)
        vote = self.vote(ir_top, hierarchy_matches=content_top if has_content else None)
        return ir_top, content_top, vote

    def vote(
        self,
        matches: list[DesignStateIRMatch],
        *,
        hierarchy_matches: list[DesignStateIRMatch] | None = None,
    ) -> dict[str, Any]:
        state = self._weighted_vote(matches, lambda item: item.design_state)
        hier_src = hierarchy_matches or matches
        score_of = (
            (lambda item: item.content_score)
            if hierarchy_matches is not None
            else (lambda item: item.score)
        )
        hierarchy = self._weighted_vote(
            hier_src,
            lambda item: item.hierarchy or item.target_level,
            score_of=score_of,
        )
        return {
            "predicted_hierarchy": self._canonical_hierarchy(hierarchy),
            "predicted_state": STATE_4.get(state, state) if state else None,
            "signal_weights": list(SIGNAL_WEIGHTS),
            "alpha": HYBRID_ALPHA,
        }

    def recommend_target(
        self,
        matches: list[dict[str, Any]],
        features: dict[str, object],
    ) -> dict[str, Any]:
        """Supervise which target level (whole/silhouette/part/material) the
        planner should expand, based on design-state cases + live signals.
        IR stays a context prior: it does not rank fragments or tokens."""
        level_scores: dict[str, float] = {}
        for match in matches:
            strength = {"high": 1.0, "medium": 0.75, "low": 0.45}.get(
                str(match.get("evidence_strength") or "low"), 0.45
            )
            level = str(match.get("hierarchy") or match.get("target_level") or "unknown")
            level = HIERARCHY_TO_LEVEL.get(level, level)
            if level == "material":
                level = "material_region"
            if level == "whole":
                level = "silhouette"
            if level in {"whole", "silhouette", "part", "material_region"}:
                level_scores[level] = level_scores.get(level, 0.0) + float(match.get("score") or 0) * strength

        event_type = str(features.get("event_type") or "")
        selection_type = str(features.get("selection_type") or "")
        intent_text = str(features.get("intent_text") or "").lower()
        if features.get("part_id") or selection_type in {"part", "brush", "mesh_region"}:
            level_scores["part"] = level_scores.get("part", 0.0) + 1.2
        if event_type.startswith("brush") or "surface" in intent_text or "材质" in intent_text:
            level_scores["material_region"] = level_scores.get("material_region", 0.0) + 0.8
        if event_type.startswith("annotation") or "轮廓" in intent_text or "silhouette" in intent_text:
            level_scores["silhouette"] = level_scores.get("silhouette", 0.0) + 1.0
        if event_type.startswith("orbit") or selection_type == "none" or "整体" in intent_text:
            level_scores["whole"] = level_scores.get("whole", 0.0) + 0.7

        total = sum(level_scores.values()) or 1.0
        normalized = {
            level: round(score / total, 4)
            for level, score in level_scores.items()
            if level in {"whole", "silhouette", "part", "material_region"}
        }
        return {
            "level_scores": normalized,
            "policy": "design_state_target_supervision",
            "evidence": [
                f"ir_targets={','.join(sorted(normalized, key=normalized.get, reverse=True)[:2])}",
            ],
            "negative_supervision": {
                "do_not_assume_part": bool(
                    not features.get("part_id")
                    and not selection_type
                    and "part" in normalized
                    and normalized["part"] < 0.2
                )
            },
        }

    def query_profile(self, features: dict[str, object]) -> dict[str, Any]:
        query = self._query_ir(features)
        labels = [
            *query["signal_codes"],
            *(value for value in (query["gt_state"], query["gt_hierarchy"], query["route"]) if value),
        ]
        return {
            "query_signals": query["signal_codes"],
            "query_terms": labels[:24],
            "scope_hint": query["scope_hint"],
            "retrieval_mode": "ir_then_content",
            "signal_vector": query["signal_vector"],
            "query_state": query["gt_state"],
            "query_hierarchy": query["gt_hierarchy"],
            "query_route": query["route"],
            "alpha": HYBRID_ALPHA,
            "signal_weights": list(SIGNAL_WEIGHTS),
        }

    def recommend_axes(
        self,
        matches: list[DesignStateIRMatch],
        features: dict[str, object],
    ) -> dict[str, Any]:
        """Aggregate matched design-state cases into next-step divergence axes.

        The IR is used as an interaction-state prior, not as an object/case lookup.
        Source case ids stay available for audit, but the runtime conclusion is the
        axis distribution that should guide More Creative prompt expansion.
        """
        axis_scores: dict[str, float] = {}
        for match in matches:
            strength = {"high": 1.0, "medium": 0.75, "low": 0.45}.get(match.evidence_strength, 0.45)
            for rank, axis in enumerate(match.recommended_axes):
                weight = max(0.35, 1.0 - rank * 0.18)
                axis_scores[axis] = axis_scores.get(axis, 0.0) + match.score * strength * weight

        # Direct UI signals can override noisy historical cases. These are still
        # interpreted as axis priors, not final generation decisions.
        event_type = str(features.get("event_type") or "")
        selection_type = str(features.get("selection_type") or "")
        creative_stage = str(features.get("creative_stage") or "")
        intent_text = str(features.get("intent_text") or "").lower()
        if event_type.startswith("hover") or selection_type in {"part", "brush", "mesh_region"} or features.get("part_id"):
            axis_scores["Structural"] = axis_scores.get("Structural", 0.0) + 1.4
            axis_scores["Functional"] = axis_scores.get("Functional", 0.0) + 0.9
        if event_type.startswith("brush") or creative_stage == "texture":
            axis_scores["Aesthetic"] = axis_scores.get("Aesthetic", 0.0) + 1.0
        if event_type.startswith("drag") or event_type.startswith("smooth") or event_type.startswith("primitive"):
            axis_scores["Structural"] = axis_scores.get("Structural", 0.0) + 1.4
        if any(term in intent_text for term in ["cute", "style", "mood", "可爱", "风格", "气质"]):
            axis_scores["Aesthetic"] = axis_scores.get("Aesthetic", 0.0) + 1.2
        if any(term in intent_text for term in ["function", "use", "afford", "功能", "用途"]):
            axis_scores["Functional"] = axis_scores.get("Functional", 0.0) + 1.2
        if any(term in intent_text for term in ["creative", "different", "breakthrough", "发散", "创意", "跨领域"]):
            axis_scores["Aesthetic"] = axis_scores.get("Aesthetic", 0.0) + 0.8
            axis_scores["Structural"] = axis_scores.get("Structural", 0.0) + 0.6

        concrete_axis_scores = {
            axis: score
            for axis, score in axis_scores.items()
            if axis in {"Aesthetic", "Functional", "Structural"}
        }
        ranked_axes = sorted(concrete_axis_scores.items(), key=lambda item: item[1], reverse=True)
        total = sum(score for _, score in ranked_axes) or 1.0
        return {
            "recommended_axes": [axis for axis, _ in ranked_axes[:3]],
            "axis_scores": [
                {"axis": axis, "score": round(score / total, 4)}
                for axis, score in ranked_axes
            ],
            "policy": "infer_next_divergence_dimension_from_ui_actions",
        }

    def _load_rows(self, limit: int) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        raw_rows = self._read_payload(self.path)
        rows: list[dict[str, Any]] = []
        for raw in raw_rows:
            if not isinstance(raw, dict):
                continue
            row = self._normalize_row(raw)
            row["_signal_vector"] = [float(value) for value in row["signal_vector"]]
            rows.append(row)
            if len(rows) >= limit:
                break
        return rows

    def _read_payload(self, path: Path) -> list[dict[str, Any]]:
        if path.suffix == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("episodes"), list):
                return payload["episodes"]
            if isinstance(payload, list):
                return payload
            return []
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
        return rows

    def _normalize_row(self, raw: dict[str, Any]) -> dict[str, Any]:
        codes = [str(code) for code in (raw.get("signal_codes") or raw.get("signals") or [])]
        coding_state = str(raw.get("coding_state") or raw.get("design_state") or "")
        route = str(raw.get("route") or "")
        hierarchy = str(raw.get("gt_hierarchy") or raw.get("hierarchy") or "")
        if hierarchy not in HIERARCHY_TO_LEVEL:
            hierarchy = HIERARCHY_3.get(route) or CODING_STATE_TO_HIERARCHY.get(coding_state, "")
        state = str(raw.get("gt_state") or STATE_4.get(coding_state, coding_state) or "")
        signal_vector = raw.get("signal_vector")
        if not isinstance(signal_vector, list) or len(signal_vector) != 6:
            signal_vector = self._signal_vector(set(codes), {})
        text = str(raw.get("text") or raw.get("episode_summary") or "")
        if "gt_state" not in raw:
            text = self._abstracted_text(raw)
        target_level = HIERARCHY_TO_LEVEL.get(hierarchy) or str(raw.get("target_level") or "unknown")
        scope_hint = HIERARCHY_TO_SCOPE.get(hierarchy) or str(raw.get("scope_hint") or "unknown")
        axes = raw.get("recommended_axes") or HIERARCHY_TO_AXES.get(hierarchy, ["Structural", "Aesthetic"])
        return {
            "ir_id": raw.get("ir_id") or f"dsir_{raw.get('episode_id') or raw.get('case_id') or ''}",
            "case_id": raw.get("episode_id") or raw.get("case_id") or "",
            "text": text,
            "design_state": state,
            "hierarchy": hierarchy,
            "route": route,
            "signals": codes,
            "signal_vector": [float(value) for value in signal_vector[:6]],
            "scope_hint": scope_hint,
            "target_level": target_level,
            "recommended_axes": [str(value) for value in axes],
            "evidence_strength": raw.get("evidence_strength") or "low",
            "state_agreement": raw.get("state_agreement") or 1.0,
            "route_agreement": raw.get("route_agreement") or 1.0,
            "signal_agreement": raw.get("signal_agreement") or 1.0,
        }

    def _abstracted_text(self, row: dict[str, Any]) -> str:
        raw = str(row.get("text") or "")
        lines: list[str] = []
        for line in raw.splitlines():
            stripped = line.strip()
            lowered = stripped.lower()
            if lowered.startswith("task group") or lowered.startswith("software"):
                continue
            if lowered.startswith("design state") or lowered.startswith("signals:"):
                continue
            if lowered.startswith("creativeflow route"):
                continue
            if "3d context object terms" in lowered:
                continue
            lines.append(stripped)
        if lines:
            return "\n".join(lines)
        return " ".join(
            [
                str(row.get("design_state") or ""),
                " ".join(str(value) for value in row.get("signals") or []),
                str(row.get("route") or ""),
                str(row.get("scope_hint") or ""),
                " ".join(str(value) for value in row.get("recommended_axes") or []),
            ]
        )

    def _query_ir(self, features: dict[str, object]) -> dict[str, Any]:
        packed = features.get("query_ir") if isinstance(features.get("query_ir"), dict) else {}
        src = {**features, **packed}
        codes = self._explicit_signal_codes(src) or self._feature_signal_codes(src)
        raw_vec = src.get("signal_vector")
        if isinstance(raw_vec, list) and len(raw_vec) >= 6:
            signal_vector = [float(value) for value in raw_vec[:6]]
        else:
            signal_vector = self._signal_vector(set(codes), src)
        hierarchy = self._canonical_hierarchy(
            str(src.get("gt_hierarchy") or packed.get("hierarchy") or src.get("query_hierarchy") or "")
        ) or ""
        state = str(src.get("gt_state") or packed.get("design_state") or src.get("query_state") or "")
        state = STATE_4.get(state, state)
        return {
            "signal_codes": codes,
            "signal_vector": signal_vector,
            "gt_state": state if state not in {"", "unknown"} else "",
            "gt_hierarchy": hierarchy,
            "route": str(src.get("route") or ""),
            "scope_hint": str(src.get("ir_scope_hint") or src.get("scope_hint") or ""),
        }

    def _explicit_signal_codes(self, features: dict[str, object]) -> list[str] | None:
        for key in ("signal_codes", "query_signals"):
            value = features.get(key)
            if isinstance(value, list) and value:
                return [str(item) for item in value]
        return None

    def _label_overlap(self, query: dict[str, Any], row: dict[str, Any]) -> list[str]:
        overlap: list[str] = []
        row_state = STATE_4.get(str(row.get("design_state") or ""), str(row.get("design_state") or ""))
        if query["gt_state"] and query["gt_state"] == row_state:
            overlap.append(query["gt_state"])
        if query["gt_hierarchy"] and query["gt_hierarchy"] == str(row.get("hierarchy") or ""):
            overlap.append(query["gt_hierarchy"])
        if query["route"] and query["route"] == str(row.get("route") or ""):
            overlap.append(query["route"])
        return overlap

    def _jaccard(self, left: set[str], right: set[str]) -> float:
        if not left and not right:
            return 0.0
        union = left | right
        return len(left & right) / len(union) if union else 0.0

    def _char_ngrams(self, text: str) -> set[str]:
        lowered = str(text or "").lower()
        grams: set[str] = set()
        for size in (2, 3, 4):
            grams.update(lowered[i : i + size] for i in range(max(0, len(lowered) - size + 1)))
        return grams

    def _set_cosine(self, left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        return len(left & right) / math.sqrt(len(left) * len(right))

    def _signal_vector(self, codes: set[str], features: dict[str, object]) -> list[float]:
        live = features.get("live_signals") if isinstance(features.get("live_signals"), dict) else {}
        semantic = float(live.get("semantic_distance") or features.get("semantic_distance") or 0.0)
        return [
            1.0 if codes & DIM1_DWELL else 0.0,
            1.0 if codes & DIM2_HESITATION else 0.0,
            1.0 if codes & DIM3_SPATIAL else 0.0,
            1.0 if codes & DIM4_VIEWPORT else 0.0,
            max(0.0, min(1.0, semantic)),
            1.0 if codes & DIM6_SKETCH else 0.0,
        ]

    def _vector_cosine(self, left: list[float], right: list[float]) -> float:
        a = [value * weight for value, weight in zip(left, SIGNAL_WEIGHTS)]
        b = [value * weight for value, weight in zip(right, SIGNAL_WEIGHTS)]
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a <= 0 or norm_b <= 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _weighted_vote(
        self,
        matches: list[DesignStateIRMatch],
        getter,
        score_of: Callable[[DesignStateIRMatch], float] | None = None,
    ) -> str:
        score_of = score_of or (lambda item: item.score)
        weights: dict[str, float] = {}
        for match in matches:
            label = str(getter(match) or "").strip()
            if not label or label == "unknown":
                continue
            weights[label] = weights.get(label, 0.0) + max(float(score_of(match)), 0.0)
        if not weights:
            return ""
        return max(weights, key=weights.get)

    def _canonical_hierarchy(self, value: str) -> str | None:
        if value in HIERARCHY_TO_LEVEL:
            return value
        lowered = value.lower()
        if lowered in {"silhouette", "whole", "contour", "whole_object"}:
            return "Silhouette"
        if lowered in {"part", "part_or_region"}:
            return "Part"
        if lowered in {"material", "material_region", "material_surface"}:
            return "Material"
        return value or None

    def _row_agreement(self, row: dict[str, Any]) -> float:
        values = [
            float(row.get("state_agreement") or 0.0),
            float(row.get("route_agreement") or 0.0),
            float(row.get("signal_agreement") or 0.0),
        ]
        values = [value for value in values if value > 0]
        return sum(values) / len(values) if values else 0.45

    def _feature_signal_codes(self, features: dict[str, object]) -> list[str]:
        event_type = str(features.get("event_type") or "")
        selection_type = str(features.get("selection_type") or "")
        creative_stage = str(features.get("creative_stage") or "")
        codes: list[str] = []
        if event_type.endswith("hover"):
            codes.append("pause_hover")
        if event_type.startswith("brush"):
            codes.append("small_brush")
        if event_type.startswith("drag"):
            codes.extend(["form_change", "repeated_micro_edit"])
        if event_type in {"hover_focus", "object_select"} or selection_type == "none":
            codes.append("select_object")
        if selection_type in {"part", "brush", "mesh_region"} or features.get("part_id"):
            codes.extend(["select_part", "local_zoom"])
        if creative_stage in {"silhouette", "rough_form", "global", "form"}:
            codes.extend(["form_change", "multi_view_check"])
        if creative_stage == "texture":
            codes.append("surface_change")
        if features.get("recent_undo_count"):
            codes.append("undo_redo_loop")
        if int(features.get("same_event_type_recent_count") or 0) >= 3:
            codes.append("repeated_micro_edit")
        if int(features.get("recent_reject_count") or 0) or int(features.get("recent_accept_count") or 0):
            codes.append("accept_reject")
        live = features.get("live_signals")
        if isinstance(live, dict):
            if int(live.get("dwell_ms") or 0) >= 1200:
                codes.append("pause_hover")
            if int(live.get("tool_switch_count") or 0) >= 3:
                codes.append("rapid_tool_switch")
            if int(live.get("compare_dwell_ms") or 0) >= 1800:
                codes.append("long_compare")
            if int(live.get("viewport_orbit_count") or 0) >= 2:
                codes.append("global_orbit")
                codes.append("multi_view_check")
            if int(live.get("viewport_zoom_count") or 0) >= 1:
                codes.append("zoom_out")
            if int(live.get("local_zoom_count") or 0) >= 1:
                codes.append("local_zoom")
            if float(live.get("mask_coverage") or 0.0) > 0:
                codes.append("small_brush")
            if float(live.get("semantic_distance") or 0.0) >= 0.45:
                codes.append("seek_alternative")
                codes.append("concept_change")
            if int(live.get("new_case_attempt_rate") or 0) >= 2:
                codes.append("seek_alternative")
            if int(live.get("reference_match_count") or 0) >= 1:
                codes.append("match_reference")
            if str(live.get("drawing_content") or "").strip() or int(features.get("image_ref_count") or 0) >= 1:
                codes.append("match_reference")
                codes.append("form_change")
        return list(dict.fromkeys(codes))


_DEFAULT_RETRIEVER: DesignStateIRRetriever | None = None


def default_retriever() -> DesignStateIRRetriever:
    global _DEFAULT_RETRIEVER
    if _DEFAULT_RETRIEVER is None:
        _DEFAULT_RETRIEVER = DesignStateIRRetriever()
    return _DEFAULT_RETRIEVER


def silent_ir_prior(
    live_signals: dict[str, object] | None,
    *,
    part_id: str | None = None,
) -> dict[str, Any]:
    """Process-state prior from GUI/live signals only — no intent text."""
    retriever = default_retriever()
    live = live_signals if isinstance(live_signals, dict) else {}
    if not retriever.ready:
        return {"ready": False, "matches": [], "recommended_axes": []}
    if int(live.get("brush_count") or 0) or float(live.get("mask_coverage") or 0):
        event_type = "brush_end"
    elif int(live.get("hover_count") or 0) or int(live.get("dwell_ms") or 0) >= 1200:
        event_type = "hover_end"
    elif int(live.get("viewport_orbit_count") or 0) >= 2 or int(live.get("viewport_zoom_count") or 0) >= 1:
        event_type = "orbit_end"
    else:
        event_type = "hover_end"
    features: dict[str, object] = {
        "event_type": event_type,
        "selection_type": "part" if part_id else "none",
        "part_id": part_id or "",
        "live_signals": live,
        "intent_text": "",
        "ir_scope_hint": "part_or_region" if part_id else "whole_object",
        "image_ref_count": int(live.get("reference_match_count") or 0),
    }
    ir_top, _content_top, vote = retriever.split_retrieve(features)
    axes = retriever.recommend_axes(ir_top, features)
    return {
        "ready": True,
        "matches": [match.to_feature() for match in ir_top],
        **retriever.query_profile(features),
        **axes,
        **vote,
    }
