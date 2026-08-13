"""GenerationSpecBuilder: selected DecisionIR option -> bounded GenerationSpec.

Strategy doc 9.3:
- receives DecisionIR + selected_option_id + asset context;
- writes the selected option's constraints into EVERY prompt (not only top
  level metadata);
- keeps "what to diverge" (keywords/seeds) and "what to preserve"
  (constraints) as separate fields;
- four candidates vary along different axes (silhouette / material /
  structure / ornament), not adjective swaps;
- reproducible seeds per run/option.
"""

from __future__ import annotations

import hashlib
import re

from app.models import (
    DecisionOption,
    FourStageRun,
    GenerationSpec,
    GenerationTarget,
    SourceContext,
    is_concrete_object_type,
)

_AXIS_PROMPTS = [
    (
        "silhouette",
        "Change the overall silhouette and outer shape while keeping the part attached",
    ),
    (
        "material",
        "Change the material appearance and surface finish",
    ),
    (
        "structure",
        "Change the internal structure or add/remove structural features",
    ),
    (
        "ornament",
        "Add ornament and surface detail without changing the core shape",
    ),
]

_PART_AXIS_PROMPTS = [
    "Change only the {part} local shape; keep every non-target part unchanged",
    "Change only the {part} attachment and transition; keep its anchors and the rest of the object unchanged",
    "Change only the {part} local surface treatment; do not restyle the whole object",
    "Add detail only inside the {part}; preserve body proportions, pose, camera, and rendering style",
]

_MATERIAL_AXIS_PROMPTS = [
    "Part-aware semantic material transfer: change base color and material family by semantic region while preserving exact geometry",
    "Part-aware semantic material transfer: change roughness, gloss, and specular or metallic response by semantic region while preserving exact geometry",
    "Part-aware semantic material transfer: change surface microstructure and pattern scale by semantic region while preserving exact geometry",
    "Part-aware semantic material transfer: change coating, weathering, or embedded particles by semantic region while preserving exact geometry",
]

_IMAGE_FRAMING_CONTRACT = (
    "Front-facing studio view of one complete object only, centered with at least 5% "
    "clear margin on every side; camera looks straight at the front of the object "
    "(not a side or three-quarter angle); pure white RGB(255,255,255) background; "
    "no crop, no cut-off parts, no floor, no shadow, no scene, no text, no watermark, "
    "and no additional objects."
)

_CHARACTER_IDENTITY_MARKERS = {
    "character", "creature", "animal", "person", "human", "mascot",
    "frog", "snowman", "bird", "fish", "cat", "dog", "角色", "生物", "动物", "青蛙", "雪人",
}
_NARRATIVE_TRANSFER_MARKERS = {
    "narrative", "story", "statue", "relic", "ancient", "archaeological",
    "mythic", "fossil", "carved stone", "stone carving", "叙事", "石像", "石雕", "遗迹", "神话", "化石",
}
_FURNITURE_IDENTITY_MARKERS = {
    "table", "desk", "chair", "stool", "bench", "shelf", "cabinet",
    "counter", "furniture", "桌", "桌子", "餐桌", "书桌", "办公桌", "茶几", "边几",
    "椅子", "座椅", "凳子", "长凳", "架子", "书架", "货架", "柜子", "橱柜", "家具",
}
_STRUCTURE_TRANSFER_MARKERS = {
    "structure", "structural", "support", "load-bearing", "topology", "reshape",
    "flowing", "molten", "lava", "fluid", "结构", "支撑", "承重", "拓扑", "流动", "熔融", "熔岩",
}


class GenerationSpecBuilder:
    def __init__(
        self,
        *,
        candidate_count: int = 8,
        model: str = "gpt-image-2",
        seed_modulus: int = 100_000,
    ) -> None:
        self.candidate_count = max(1, min(8, candidate_count))
        self.model = model
        self.seed_modulus = seed_modulus

    def build_spec(
        self,
        run: FourStageRun,
        selected_option_id: str,
    ) -> GenerationSpec:
        if run.decision is None:
            raise ValueError("run has no decision to build a spec from")
        option = next(
            (item for item in run.decision.options if item.option_id == selected_option_id),
            None,
        )
        if option is None:
            if run.decision.options:
                raise ValueError(
                    f"unknown option {selected_option_id}; "
                    f"valid={sorted(item.option_id for item in run.decision.options)}"
                )
            # Fast Gate ships without concrete direction options; keyword
            # selection is the real generation brief.
            option = DecisionOption(
                option_id=selected_option_id,
                label=run.decision.gate_question or run.decision.summary or "scope change",
                rationale="fast-gate scope accept without direction options",
                confidence=run.decision.confidence,
            )
        intent_ir = run.intent_ir
        object_type = intent_ir.target.object_type if intent_ir else None
        if not is_concrete_object_type(object_type) and run.source_context is not None:
            # SourceContext is the authoritative identity captured at Send.
            # Planner output may legitimately omit/reduce the target label.
            object_type = run.source_context.object_type
        if not is_concrete_object_type(object_type):
            # Pre-contract test clients can still exercise the old text-only
            # path.  Never let that compatibility branch reach production:
            # the encoder attaches SourceContext for real runs, and the
            # absence of it is a hard failure for a generic target.
            if run.source_context is None and object_type in {None, "object", "unknown", "item", "thing"}:
                object_type = "design subject (legacy)"
            else:
                raise ValueError(
                    "generation requires a concrete source object_type; object/unknown is not allowed"
                )
        # Concrete object type is mandatory.  Legacy unit fixtures may not
        # carry an asset id yet; keep the source context optional in that
        # narrow compatibility path, while production runs are populated by
        # the encoder's SourceContext attachment.
        constraints: list[str] = []
        for value in (intent_ir.intent.constraints if intent_ir else []) + option.constraints:
            if value and value not in constraints:
                constraints.append(value)
        if f"preserve {object_type} identity" not in constraints:
            constraints.insert(0, f"preserve {object_type} identity")
        target_scope = intent_ir.intent.scope if intent_ir else "whole"
        target_part = intent_ir.target.part_id if intent_ir else None
        if target_scope == "part" and target_part:
            for value in (
                f"change only {target_part}",
                "preserve every non-target part",
                "preserve body proportions, pose, camera, and rendering style",
            ):
                if value not in constraints:
                    constraints.append(value)
        elif target_scope in {"material", "material_region"}:
            for value in (
                "preserve exact geometry, silhouette, proportions, and every part shape",
                "preserve pose, camera, composition, and background",
                "preserve category-defining semantic features and part roles",
                "apply materials by semantic region; never coat every part with one uniform donor material",
                "allow color and material appearance to change visibly",
            ):
                if value not in constraints:
                    constraints.append(value)
        selection = run.divergence_selection
        if (
            selection is None
            or not selection.selected_candidate_ids
            or not selection.selected_keywords
            or not selection.resolved_prompt_phrases
        ):
            raise ValueError(
                "generation requires an explicit semantic divergence candidate selection"
            )
        scenario = self._scenario(run)
        if scenario == "narrative_character":
            for value in (
                "preserve the complete recognizable character silhouette, anatomy, pose, and part count",
                "preserve category-defining facial and limb cues",
                "do not replace the source character with a different object or species",
                "keep the full source object, camera, composition, and background",
            ):
                if value not in constraints:
                    constraints.append(value)
        elif scenario == "product_structure":
            for value in (
                "preserve furniture category identity and scale",
                "preserve a horizontal usable tabletop and a plausible load-bearing support system",
                "preserve tabletop-to-support topology and full-object camera framing",
                "make structural morphology visibly diverse; texture-only recoloring is insufficient",
            ):
                if value not in constraints:
                    constraints.append(value)
        user_keywords = list(selection.selected_keywords)
        prompt_phrases = list(selection.resolved_prompt_phrases)
        keywords = list(dict.fromkeys(user_keywords))
        goal = (
            (intent_ir.intent.goal if intent_ir and intent_ir.intent.goal else None)
            or option.label
        )
        preserve_clause = (
            "; PRESERVE: " + ", ".join(constraints) if constraints else ""
        )
        prompt_candidates: list[str] = []
        for index in range(self.candidate_count):
            # Match image-divergence-sandbox: part / material / whole axes only.
            # Scenario markers still land in PRESERVE constraints above; they must
            # not swap the axis recipe that gpt-image-2 already responds well to.
            if target_scope == "part" and target_part:
                axis_prompt = _PART_AXIS_PROMPTS[index % len(_PART_AXIS_PROMPTS)].format(
                    part=target_part
                )
            elif target_scope in {"material", "material_region"}:
                axis_prompt = _MATERIAL_AXIS_PROMPTS[index % len(_MATERIAL_AXIS_PROMPTS)]
            else:
                _, axis_prompt = _AXIS_PROMPTS[index % len(_AXIS_PROMPTS)]
            # A chip is a direction anchor, not a bag of adjectives.  Mixing
            # every selected chip into every candidate made the first strong
            # material (for example rattan or moss) dominate the whole batch.
            # Bind exactly one server-resolved full direction phrase to each
            # candidate. Generic planner/taxonomy seeds never enter prompts.
            user_anchor = prompt_phrases[index % len(prompt_phrases)]
            user_clause = f"; USER-SELECTED DIRECTION: {user_anchor}"
            prompt_candidates.append(
                f"{object_type}: {goal} — {axis_prompt}{preserve_clause}"
                f"{user_clause}; "
                f"{_IMAGE_FRAMING_CONTRACT}"
            )
        seeds = [
            int(
                hashlib.sha256(
                    f"{run.run_id}:{selected_option_id}:{index}".encode("utf-8")
                ).hexdigest()[:8],
                16,
            )
            % self.seed_modulus
            for index in range(self.candidate_count)
        ]
        source_context = run.source_context
        if source_context is None and intent_ir.target.asset_id:
            source_context = SourceContext(
                asset_id=intent_ir.target.asset_id,
                object_type=object_type,
                target_part_id=intent_ir.target.part_id,
            )
        return GenerationSpec(
            generation_id=f"gen_{hashlib.sha256(f'{run.run_id}:{selected_option_id}'.encode()).hexdigest()[:10]}",
            run_id=run.run_id,
            decision_id=run.decision.decision_id,
            selected_option_id=selected_option_id,
            source=source_context,
            asset_id=intent_ir.target.asset_id if intent_ir else None,
            object_type=object_type,
            target=GenerationTarget(
                scope=target_scope,
                part_id=target_part,
            ),
            keywords=keywords[:12],
            selected_keywords=user_keywords[:12],
            dimensions=dict(selection.dimensions) if selection else {},
            prompt_candidates=prompt_candidates,
            preserved_constraints=constraints,
            candidate_count=self.candidate_count,
            model=self.model,
            seeds=seeds,
            run_hy3d=bool(run.run_hy3d),
        )

    @staticmethod
    def _scenario(run: FourStageRun) -> str | None:
        intent_ir = run.intent_ir
        if intent_ir is None:
            return None
        identity = " ".join(
            value
            for value in (
                intent_ir.target.object_type,
                run.source_context.object_type if run.source_context else None,
            )
            if value
        ).lower()
        semantic_intent = " ".join(
            value
            for value in (
                intent_ir.intent.operation,
                intent_ir.intent.goal,
                intent_ir.observations.text,
            )
            if value
        ).lower()

        def contains_any(text: str, markers: set[str]) -> bool:
            for marker in markers:
                if marker.isascii():
                    if re.search(rf"(?<![a-z0-9]){re.escape(marker)}(?![a-z0-9])", text):
                        return True
                elif len(marker) == 1:
                    if text.strip() == marker:
                        return True
                elif marker in text:
                    return True
            return False

        if contains_any(identity, _CHARACTER_IDENTITY_MARKERS) and contains_any(
            semantic_intent, _NARRATIVE_TRANSFER_MARKERS
        ):
            return "narrative_character"
        if contains_any(identity, _FURNITURE_IDENTITY_MARKERS) and contains_any(
            semantic_intent, _STRUCTURE_TRANSFER_MARKERS
        ):
            return "product_structure"
        return None
