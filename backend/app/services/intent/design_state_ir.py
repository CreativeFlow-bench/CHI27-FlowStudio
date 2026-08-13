from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_IR_PATH = (
    Path(__file__).resolve().parents[4]
    / "intentdatabase"
    / "cleaned"
    / "design_state_ir_retrieval.jsonl"
)


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
        }


class DesignStateIRRetriever:
    def __init__(self, path: Path | None = None, limit: int = 207) -> None:
        self.path = path or DEFAULT_IR_PATH
        self.rows = self._load_rows(limit)

    @property
    def ready(self) -> bool:
        return bool(self.rows)

    def retrieve(self, features: dict[str, object], top_k: int = 5) -> list[DesignStateIRMatch]:
        query_signals = set(self._feature_signal_codes(features))
        query_terms = self._feature_terms(features)
        query_vector = self._feature_vector(features, query_signals, query_terms)
        query_scope = str(features.get("ir_scope_hint") or "")
        scored: list[DesignStateIRMatch] = []
        for row in self.rows:
            row_signals = set(row.get("signals") or [])
            signal_overlap = sorted(query_signals & row_signals)
            term_overlap = sorted(query_terms & row["_tokens"])
            vector_score = self._cosine(query_vector, row["_vector"])
            scope_match = bool(query_scope and query_scope == row.get("scope_hint"))
            scope_bonus = 1 if scope_match else 0
            evidence_bonus = {"high": 0.35, "medium": 0.18}.get(str(row.get("evidence_strength")), 0.0)
            agreement = self._row_agreement(row)
            score = (
                len(signal_overlap) * 2.0
                + len(term_overlap) * 0.18
                + vector_score * 3.0
                + scope_bonus * 0.75
                + evidence_bonus
            ) * (0.72 + agreement * 0.28)
            if score <= 0:
                continue
            confidence = min(0.97, max(0.05, score / (score + 4.5)))
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
                    term_overlap=term_overlap,
                    scope_match=scope_match,
                )
            )
        return sorted(scored, key=lambda item: item.score, reverse=True)[: max(1, top_k)]

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
            level = str(match.get("target_level") or "unknown")
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
        query_signals = self._feature_signal_codes(features)
        query_terms = sorted(self._feature_terms(features))[:24]
        return {
            "query_signals": query_signals,
            "query_terms": query_terms,
            "scope_hint": str(features.get("ir_scope_hint") or ""),
            "retrieval_mode": "hybrid_signal_vector",
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
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            # Runtime retrieval text may only carry abstracted design-state
            # fields; strip hard case identity lines (software/task group/
            # object terms) before tokenizing (main spec §1.2).
            row["_tokens"] = self._tokens(self._abstracted_text(row))
            row["_vector"] = self._row_vector(row)
            rows.append(row)
            if len(rows) >= limit:
                break
        return rows

    def _abstracted_text(self, row: dict[str, Any]) -> str:
        raw = str(row.get("text") or "")
        lines: list[str] = []
        for line in raw.splitlines():
            stripped = line.strip()
            lowered = stripped.lower()
            if lowered.startswith("task group") or lowered.startswith("software"):
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

    def _feature_terms(self, features: dict[str, object]) -> set[str]:
        signals = features.get("signals")
        chunks = [
            str(features.get("event_type") or ""),
            str(features.get("intent_text") or ""),
            str(features.get("creative_stage") or ""),
            str(features.get("selection_type") or ""),
        ]
        if isinstance(signals, dict):
            chunks.append(json.dumps(signals, ensure_ascii=False, sort_keys=True))
        return self._tokens("\n".join(chunks))

    def _tokens(self, text: str) -> set[str]:
        return {
            token.lower()
            for token in re.findall(r"[\w\u4e00-\u9fff]+", text)
            if len(token) >= 2
        }

    def _row_vector(self, row: dict[str, Any]) -> Counter[str]:
        vector: Counter[str] = Counter()
        for token in row.get("_tokens") or []:
            vector[f"t:{token}"] += 1.0
        for signal in row.get("signals") or []:
            vector[f"s:{signal}"] += 2.5
        for axis in row.get("recommended_axes") or []:
            vector[f"a:{axis}"] += 0.8
        if row.get("design_state"):
            vector[f"state:{row.get('design_state')}"] += 1.5
        if row.get("route"):
            vector[f"route:{row.get('route')}"] += 1.2
        if row.get("scope_hint"):
            vector[f"scope:{row.get('scope_hint')}"] += 1.0
        return vector

    def _feature_vector(
        self,
        features: dict[str, object],
        query_signals: set[str],
        query_terms: set[str],
    ) -> Counter[str]:
        vector: Counter[str] = Counter()
        for token in query_terms:
            vector[f"t:{token}"] += 1.0
        for signal in query_signals:
            vector[f"s:{signal}"] += 2.5
        scope = str(features.get("ir_scope_hint") or "")
        if scope:
            vector[f"scope:{scope}"] += 1.0
        return vector

    def _cosine(self, a: Counter[str], b: Counter[str]) -> float:
        if not a or not b:
            return 0.0
        dot = sum(value * b.get(key, 0.0) for key, value in a.items())
        norm_a = math.sqrt(sum(value * value for value in a.values()))
        norm_b = math.sqrt(sum(value * value for value in b.values()))
        if norm_a <= 0 or norm_b <= 0:
            return 0.0
        return dot / (norm_a * norm_b)

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
        intent_text = str(features.get("intent_text") or "").lower()
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
        if any(term in intent_text for term in ["preserve", "boundary", "edge", "keep", "保留", "边界"]):
            codes.append("preserve_structure")
        if any(term in intent_text for term in ["cute", "creative", "different", "breakthrough", "可爱", "创意", "发散"]):
            codes.append("concept_change")
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
            if str(live.get("drawing_content") or "").strip():
                codes.append("form_change")
        return list(dict.fromkeys(codes))
