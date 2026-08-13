"""FourStageRetrievalService: sparse retrieval -> rerank -> abstain.

Strategy doc 7 (V1.1): no vector library. The existing sparse
``DesignStateIRRetriever`` is the only channel; scoring is

    final = w_sparse * sparse + w_metadata * metadata + w_outcome * outcome

with configurable weights. abstain fires when the top match is too weak or the
top-1/top-2 gap is too small, so weak episodes do not borrow prior cases.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from app.models import (
    FourStageRun,
    IntentIR,
    RetrievalBundle,
    RetrievalMatch,
)
from app.services.intent.design_state_ir import DesignStateIRMatch, DesignStateIRRetriever
from app.services.storage.four_stage_store import FourStageStore

logger = logging.getLogger("flowstudio.retrieval")


class FourStageRetrievalError(Exception):
    pass


class FourStageRetrievalService:
    DATA_VERSION = "design-state-ir-2026-08-v1"
    DEFAULT_WEIGHTS = {"sparse": 1.0, "metadata": 0.8, "outcome": 0.4}
    ABSTAIN_MIN_NORM = 0.28
    ABSTAIN_TOP_GAP = 0.04

    def __init__(
        self,
        retriever: DesignStateIRRetriever | None = None,
        *,
        store: FourStageStore | None = None,
        weights: dict[str, float] | None = None,
        candidate_pool: int = 20,
        top_k: int = 5,
    ) -> None:
        self.retriever = retriever or DesignStateIRRetriever()
        self.store = store
        self.weights = {**self.DEFAULT_WEIGHTS, **(weights or {})}
        self.candidate_pool = candidate_pool
        self.top_k = top_k

    async def retrieve(
        self,
        run: FourStageRun,
        intent_ir: IntentIR,
    ) -> RetrievalBundle:
        if not self.retriever.ready:
            raise FourStageRetrievalError(
                "design-state IR data missing or empty (source of truth unavailable)"
            )
        features = self._ir_to_features(intent_ir)
        pool = self.retriever.retrieve(features, top_k=self.candidate_pool)
        if not pool:
            return self._abstained(run, intent_ir, "no prior matched the query")

        norm_scores = [self._norm(item.score) for item in pool]
        top_norm = norm_scores[0]
        if top_norm < self.ABSTAIN_MIN_NORM:
            return self._abstained(run, intent_ir, "top prior score below abstain threshold")
        same_state_close = False
        if len(pool) > 1:
            gap = top_norm - norm_scores[1]
            same_state = pool[0].design_state == pool[1].design_state
            same_state_close = not same_state and gap < self.ABSTAIN_TOP_GAP
        if same_state_close:
            return self._abstained(
                run,
                intent_ir,
                "top-1/top-2 prior scores from different design states too close to choose",
            )

        matches: list[RetrievalMatch] = []
        for item in pool[: self.candidate_pool]:
            metadata_score = self._metadata_score(item, intent_ir)
            outcome_score = self._outcome_score(item.case_id, run.session_id)
            final_score = self._final_score(
                sparse=item.score,
                metadata=metadata_score,
                outcome=outcome_score,
            )
            matches.append(
                RetrievalMatch(
                    prior_ir_id=item.ir_id,
                    case_id=item.case_id,
                    sparse_score=round(self._norm(item.score), 4),
                    metadata_score=round(metadata_score, 4),
                    outcome_score=round(outcome_score, 4),
                    final_score=round(final_score, 4),
                    prior_judgement={
                        "design_state": item.design_state,
                        "route": item.route,
                        "evidence_strength": item.evidence_strength,
                        "target_level": item.target_level,
                        "recommended_axes": item.recommended_axes,
                    },
                    evidence=[
                        {
                            "signal_overlap": item.signal_overlap[:12],
                            "term_overlap": item.term_overlap[:12],
                            "scope_match": item.scope_match,
                            "vector_score": round(item.vector_score, 4),
                        }
                    ],
                    outcome={"accepted": self._case_accepted(item.case_id)},
                )
            )
        matches.sort(key=lambda item: item.final_score, reverse=True)
        matches = matches[: self.top_k]
        return RetrievalBundle(
            retrieval_id=f"ret_{uuid4().hex[:10]}",
            run_id=run.run_id,
            query_ir_id=intent_ir.ir_id,
            data_version=self.DATA_VERSION,
            retriever="design-state-ir-sparse-v1",
            matches=matches,
            abstained=False,
            abstain_reason=None,
        )

    def _abstained(
        self,
        run: FourStageRun,
        intent_ir: IntentIR,
        reason: str,
    ) -> RetrievalBundle:
        return RetrievalBundle(
            retrieval_id=f"ret_{uuid4().hex[:10]}",
            run_id=run.run_id,
            query_ir_id=intent_ir.ir_id,
            data_version=self.DATA_VERSION,
            retriever="design-state-ir-sparse-v1",
            matches=[],
            abstained=True,
            abstain_reason=reason,
        )

    def _ir_to_features(self, intent_ir: IntentIR) -> dict[str, Any]:
        summary = intent_ir.observations.interaction_summary or {}
        if summary.get("has_brush"):
            event_type = "brush_end"
        elif summary.get("has_drag"):
            event_type = "drag_end"
        elif intent_ir.intent.operation == "observe":
            event_type = "orbit_end"
        else:
            event_type = "text"
        selection_type = str(summary.get("selection_type") or "")
        if not selection_type and intent_ir.target.part_id:
            selection_type = "part"
        viewport = intent_ir.observations.viewport or {}
        live_signals = {
            "viewport_orbit_count": int(viewport.get("orbit_count") or 0),
            "viewport_zoom_count": int(viewport.get("zoom_count") or 0),
            "dwell_ms": int(viewport.get("dwell_ms_max") or 0),
            "mask_coverage": float(summary.get("mask_coverage") or 0),
        }
        return {
            "event_type": event_type,
            "selection_type": selection_type or "none",
            "part_id": intent_ir.target.part_id,
            "intent_text": intent_ir.intent.goal
            or intent_ir.observations.text
            or "",
            "ir_scope_hint": intent_ir.intent.scope,
            "creative_stage": "form"
            if intent_ir.intent.operation != "observe"
            else "",
            "live_signals": live_signals,
            "image_ref_count": len(intent_ir.observations.image_refs or []),
        }

    def _metadata_score(self, match: DesignStateIRMatch, intent_ir: IntentIR) -> float:
        hits = 0.0
        total = 0.0
        if match.scope_match:
            hits += 1.0
        total += 1.0
        if match.target_level == intent_ir.intent.scope:
            hits += 1.0
        total += 1.0
        operation = intent_ir.intent.operation
        if operation != "observe" and operation in str(match.design_state).lower():
            hits += 0.5
        total += 0.5
        query_text = intent_ir.observations.text or intent_ir.intent.goal or ""
        if self._same_language(query_text, match.text):
            hits += 0.5
        total += 0.5
        return hits / total if total else 0.0

    def _outcome_score(self, case_id: str | None, session_id: str) -> float:
        if self.store is None or not case_id:
            return 0.0
        return self.store.retrieval_outcome_score(case_id, session_id)

    def _case_accepted(self, case_id: str | None) -> bool:
        if self.store is None or not case_id:
            return False
        return self.store.retrieval_case_accepted(case_id)

    def _final_score(self, *, sparse: float, metadata: float, outcome: float) -> float:
        sparse_norm = self._norm(sparse)
        weights = self.weights
        total = weights["sparse"] + weights["metadata"] + weights["outcome"]
        return (
            weights["sparse"] * sparse_norm
            + weights["metadata"] * metadata
            + weights["outcome"] * outcome
        ) / total

    @staticmethod
    def _norm(score: float) -> float:
        return 1.0 - 1.0 / (1.0 + max(0.0, score))

    @staticmethod
    def _same_language(a: str, b: str) -> bool:
        def lang(text: str) -> str:
            if not text:
                return "unknown"
            return "zh" if any("\u4e00" <= char <= "\u9fff" for char in text) else "en"

        la, lb = lang(a), lang(b)
        return la == lb and la != "unknown"
