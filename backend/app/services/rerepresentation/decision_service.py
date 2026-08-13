"""FourStageDecisionService: Gemini DecisionIR with explicit rule fallback.

Rule fallback is always visible in ``DecisionIR.model`` / provenance and must
never be presented as a Gemini judgement.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from app.models import (
    DecisionIR,
    DecisionOption,
    FourStageRun,
    IntentIR,
    RetrievalBundle,
    is_concrete_object_type,
)
from app.services.rerepresentation.evidence_assembler import EvidenceAssembler
from app.services.rerepresentation.gemini_client import (
    GeminiClient,
    GeminiDecisionError,
    GeminiUnavailable,
)

logger = logging.getLogger("flowstudio.rerepresentation")

_AXIS_SEEDS = {
    "Aesthetic": ["soft silhouette", "surface ornament", "material contrast"],
    "Structural": ["additive geometry", "thinner profile", "reinforced rim"],
    "Functional": ["repositioned handle", "improved grip", "modular joint"],
}


class RuleDecisionService:
    async def decide(
        self,
        run: FourStageRun,
        intent_ir: IntentIR,
        retrieval: RetrievalBundle,
    ) -> DecisionIR:
        goal = intent_ir.intent.goal or intent_ir.observations.text or ""
        constraints = list(intent_ir.intent.constraints)
        axes = list(intent_ir.intent.preferred_axes) or ["Aesthetic", "Structural"]
        prior_axes: list[str] = []
        for match in (retrieval.matches or [])[:3]:
            judgement = match.prior_judgement or {}
            for axis in judgement.get("recommended_axes") or []:
                if axis not in prior_axes:
                    prior_axes.append(axis)
        axes = list(dict.fromkeys(axes + prior_axes))[:3] or ["Aesthetic"]

        if not goal:
            return DecisionIR(
                decision_id=f"decision_{uuid4().hex[:10]}",
                run_id=run.run_id,
                intent_ir_id=intent_ir.ir_id,
                retrieval_id=retrieval.retrieval_id,
                summary="User intent is too weak to recommend a concrete direction.",
                recommended_scope=intent_ir.intent.scope,
                semantic_target=intent_ir.target.part_id or intent_ir.target.object_type,
                gate_question=_gate_question(intent_ir),
                options=[],
                needs_clarification=True,
                clarification_question="你更想改变形状、材质还是整体风格？",
                confidence=0.25,
                model="rule-fallback",
                prompt_version="re-representation-rule-v1",
            )

        options: list[DecisionOption] = []
        for index, axis in enumerate(axes[:4]):
            seeds = _AXIS_SEEDS.get(axis, ["silhouette", "material", "ornament"])
            options.append(
                DecisionOption(
                    option_id=f"opt_{index + 1}",
                    label=f"{goal} — {axis.lower()} direction",
                    rationale=(
                        f"Rule fallback direction along the {axis} axis"
                        + (f"; prior case {retrieval.matches[0].case_id}" if retrieval.matches else "")
                    ),
                    confidence=0.5,
                    evidence_refs=[
                        match.prior_ir_id for match in (retrieval.matches or [])[:2]
                    ],
                    constraints=constraints,
                    divergence_seeds=seeds,
                )
            )
        return DecisionIR(
            decision_id=f"decision_{uuid4().hex[:10]}",
            run_id=run.run_id,
            intent_ir_id=intent_ir.ir_id,
            retrieval_id=retrieval.retrieval_id,
            summary=f"Rule fallback re-representation for: {goal}",
            recommended_scope=intent_ir.intent.scope,
            semantic_target=intent_ir.target.part_id or intent_ir.target.object_type,
            gate_question=_gate_question(intent_ir),
            options=options,
            needs_clarification=False,
            confidence=0.5,
            model="rule-fallback",
            prompt_version="re-representation-rule-v1",
        )


class FourStageDecisionService:
    def __init__(
        self,
        *,
        assembler: EvidenceAssembler,
        gemini_client: GeminiClient,
        rule_decision: RuleDecisionService,
        enabled: bool = False,
        feedback_lookup=None,
    ) -> None:
        self.assembler = assembler
        self.gemini_client = gemini_client
        self.rule_decision = rule_decision
        self.enabled = enabled
        self.feedback_lookup = feedback_lookup

    async def decide(
        self,
        run: FourStageRun,
        intent_ir: IntentIR,
        retrieval: RetrievalBundle,
    ) -> DecisionIR:
        if not self.enabled or not self.gemini_client.configured:
            return await self.rule_decision.decide(run, intent_ir, retrieval)
        evidence = self.assembler.assemble(
            run=run,
            intent_ir=intent_ir,
            retrieval=retrieval,
            feedback_lookup=(
                (lambda case_id: self.feedback_lookup(case_id, run.session_id))
                if self.feedback_lookup is not None
                else None
            ),
        )
        try:
            decision = await self.gemini_client.decide(evidence, run_id=run.run_id)
            self._inject_hard_constraints(decision, intent_ir)
            self._inject_divergence_seeds(decision, intent_ir, retrieval)
            self._inject_gate_question(decision, intent_ir)
            if self._should_fallback_from_clarify(decision, intent_ir, retrieval):
                logger.warning(
                    "gemini clarified despite usable evidence; rule fallback run=%s",
                    run.run_id,
                )
                return await self.rule_decision.decide(run, intent_ir, retrieval)
            return decision
        except GeminiUnavailable as exc:
            logger.warning(
                "gemini unavailable; rule fallback run=%s: %s", run.run_id, exc
            )
            return await self.rule_decision.decide(run, intent_ir, retrieval)
        except GeminiDecisionError:
            raise

    @staticmethod
    def _inject_gate_question(decision: DecisionIR, intent_ir: IntentIR) -> None:
        decision.semantic_target = intent_ir.target.part_id or intent_ir.target.object_type
        decision.gate_question = _gate_question(intent_ir)

    @staticmethod
    def _should_fallback_from_clarify(
        decision: DecisionIR,
        intent_ir: IntentIR,
        retrieval: RetrievalBundle,
    ) -> bool:
        if not (decision.needs_clarification and not decision.options):
            return False
        has_goal = bool(
            (intent_ir.intent.goal or intent_ir.observations.text or "").strip()
        )
        return has_goal or bool(retrieval.matches)

    @staticmethod
    def _inject_hard_constraints(
        decision: DecisionIR,
        intent_ir: IntentIR,
    ) -> None:
        constraints = list(intent_ir.intent.constraints)
        if not constraints:
            return
        for option in decision.options:
            merged = list(constraints)
            for value in option.constraints:
                if value not in merged:
                    merged.append(value)
            option.constraints = merged

    @staticmethod
    def _inject_divergence_seeds(
        decision: DecisionIR,
        intent_ir: IntentIR,
        retrieval: RetrievalBundle,
    ) -> None:
        fallback: list[str] = []
        for value in (intent_ir.intent.preferred_axes or []) + [
            axis
            for match in (retrieval.matches or [])[:3]
            for axis in ((match.prior_judgement or {}).get("recommended_axes") or [])
        ]:
            if value and value not in fallback:
                fallback.append(value)
        if not fallback:
            fallback = ["silhouette", "material", "ornament"]
        for option in decision.options:
            if not option.divergence_seeds:
                option.divergence_seeds = list(fallback)


def _gate_question(intent_ir: IntentIR) -> str:
    """Compress backend hypotheses into exactly one user-facing question."""

    object_type = intent_ir.target.object_type
    part = intent_ir.target.part_id
    scope = intent_ir.intent.scope
    if not is_concrete_object_type(object_type):
        return "请先确认当前具体对象和目标部件，再开始发散，可以吗？"
    if scope in {"material", "material_region"}:
        return f"你想改变这个 {object_type} 的表面材质吗？"
    if part or scope == "part":
        raw = str(part or "").strip()
        lower = raw.lower()
        if (
            not raw
            or lower in {"object", "unknown", "item", "thing", "model", "asset", "当前部件"}
            or lower.startswith("obj_group")
            or lower.startswith("cube_")
        ):
            target = "部件"
        else:
            target = raw
        return f"你想改变这个 {target} 的形状或连接吗？"
    return f"你想改变这个 {object_type} 的整体轮廓吗？"
