from __future__ import annotations

from math import sqrt
from uuid import uuid4

from app.models import (
    AssistancePolicy,
    AssistanceSuggestion,
    DesignPhase,
    GenerationMode,
    IntentHypothesis,
    IntentLabel,
    InteractionInterpretation,
    InterpretationTarget,
    StageState,
    UserEvent,
)
from app.models.semantic import SemanticTarget
from app.services.intent.multimodal_intent_predictor import (
    RuleBasedMultimodalIntentPredictor,
)
from app.services.intent.design_state_ir import DesignStateIRRetriever
from app.services.shared.labels import zh_label
from app.services.signals.cognition_supervisor import supervise_cognition
from app.services.signals.gui_interaction_supervisor import supervise_gui_interaction
from app.services.signals.semantic_language_supervisor import supervise_semantic_language
from app.services.signals.target_fusion import fuse_targets
from app.services.storage.studio_store import InMemoryStudioStore
from app.services.intent.creative_state import attach_creative_state
from app.services.intent.interaction_features import extract_interaction_features



class InteractionUnderstandingService:
    """Rule-based MVP preserving the future multimodal predictor boundary."""

    def __init__(
        self,
        store: InMemoryStudioStore,
        predictor: RuleBasedMultimodalIntentPredictor | None = None,
        ir_retriever: DesignStateIRRetriever | None = None,
    ) -> None:
        self.store = store
        self.predictor = predictor or RuleBasedMultimodalIntentPredictor()
        self.ir_retriever = ir_retriever or DesignStateIRRetriever()

    def interpret_event(
        self,
        event: UserEvent,
        *,
        defer_vlm: bool = False,
        interpretation_id: str | None = None,
    ) -> InteractionInterpretation:
        features = self._extract_features(event)
        self._attach_part_context(features)
        self._attach_design_state_ir(features)
        self._attach_creative_state(features, event)
        self._attach_semantic_targets(features)
        use_rule_first = (
            defer_vlm
            and self.vlm_configured()
            and hasattr(self.predictor, "predict_rules_only")
        )
        if use_rule_first:
            prediction = self.predictor.predict_rules_only(event, features)
        else:
            prediction = self.predictor.predict(event, features)
        return self._build_interpretation(
            event,
            features,
            prediction,
            interpretation_id=interpretation_id,
        )

    def _attach_part_context(self, features: dict[str, object]) -> None:
        """Make the asset's registered part labels visible to the semantic
        supervisor so text like "把帽子改成皇冠" can be grounded to a part."""
        asset_id = features.get("asset_id")
        if not asset_id:
            features["part_labels"] = []
            return
        asset = self.store.get_asset(str(asset_id))
        parts = list(getattr(asset, "parts", None) or []) if asset is not None else []
        if asset is not None:
            object_label = str(getattr(asset, "object_type", None) or getattr(asset, "label", None) or "").strip()
            if object_label:
                features["object_label"] = object_label
                features["object_label_zh"] = zh_label(object_label)
        entries: list[dict[str, object]] = []
        for part in parts:
            label = str(getattr(part, "label", None) or getattr(part, "part_id", "") or "")
            part_id = str(getattr(part, "part_id", "") or "")
            if label:
                entries.append({"label": label, "part_id": part_id})
        features["part_labels"] = entries
        if entries and not features.get("part_id"):
            intent_text = str(features.get("intent_text") or "").lower()
            if intent_text:
                for entry in entries:
                    label = str(entry.get("label") or "")
                    if label.lower() in intent_text:
                        features["part_id"] = entry.get("part_id") or None
                        if not features.get("part_label"):
                            features["part_label"] = label
                        break

    def refine_with_vlm(
        self,
        event: UserEvent,
        base: InteractionInterpretation,
    ) -> InteractionInterpretation:
        """Second-pass VLM refine; reuses IR already attached on base.features."""
        features = dict(base.features or {})
        if "design_state_ir" not in features:
            self._attach_design_state_ir(features)
        else:
            # Count as reused; do not retrieve again.
            ir = features.get("design_state_ir")
            if isinstance(ir, dict):
                features["design_state_ir"] = {**ir, "ir_reused_for_vlm_refine": True}
        prediction = self.predictor.predict(event, features)
        refined = self._build_interpretation(
            event,
            features,
            prediction,
            interpretation_id=base.interpretation_id,
        )
        refined.predictor_metadata = {
            **refined.predictor_metadata,
            "refined_from": base.interpretation_id,
            "vlm_refined": True,
            "vlm_pending": False,
            "task": "intent_predict",
        }
        self.store.save_interpretation(refined)
        self._update_stage(refined)
        return refined

    def vlm_configured(self) -> bool:
        endpoint = getattr(self.predictor, "endpoint_url", None)
        if isinstance(endpoint, str) and endpoint.strip():
            return True
        gateway = getattr(self.predictor, "gateway", None)
        profile = getattr(gateway, "profile", None) if gateway is not None else None
        api_key = getattr(profile, "api_key", None) if profile is not None else None
        return bool(api_key)

    def build_sandbox_prompt_bundle(
        self,
        event: UserEvent,
        *,
        system_prompt: str | None = None,
    ) -> dict[str, object]:
        features = self._extract_features(event)
        self._attach_part_context(features)
        self._attach_design_state_ir(features)
        self._attach_creative_state(features, event)
        self._attach_semantic_targets(features)
        builder = getattr(self.predictor, "build_prompt_bundle", None)
        if callable(builder):
            return builder(event, features, system_prompt=system_prompt)
        prior = self.predictor.predict(event, features) if not self.vlm_configured() else None
        if prior is None and hasattr(self.predictor, "fallback"):
            prior = self.predictor.fallback.predict(event, features)  # type: ignore[attr-defined]
        return {
            "system": system_prompt
            or "Rule-based predictor only — no planner system prompt is sent.",
            "user": "",
            "user_payload": {
                "event": event.model_dump(mode="json"),
                "features": features,
            },
            "model": None,
            "messages": [],
            "rule_based_prior": {
                "hypotheses": [
                    item.model_dump(mode="json")
                    for item in (getattr(prior, "hypotheses", []) or [])
                ]
            }
            if prior is not None
            else {},
            "mode": "rule_only_no_prompt",
        }

    def interpret_sandbox(
        self,
        event: UserEvent,
        *,
        system_prompt: str | None = None,
        sync_vlm: bool = True,
        preview_only: bool = False,
    ) -> dict[str, object]:
        """Run interpret for the IR sandbox and expose the planner prompts."""
        prompts = self.build_sandbox_prompt_bundle(event, system_prompt=system_prompt)
        if preview_only:
            return {
                "preview_only": True,
                "vlm_configured": self.vlm_configured(),
                "prompts": prompts,
                "interpretation": None,
            }

        predictor = self.predictor
        previous_override = getattr(predictor, "system_prompt_override", None)
        if system_prompt is not None and hasattr(predictor, "system_prompt_override"):
            predictor.system_prompt_override = system_prompt
        try:
            if sync_vlm and self.vlm_configured():
                interpretation = self.interpret_event(event, defer_vlm=False)
            else:
                interpretation = self.interpret_event(event, defer_vlm=True)
        finally:
            if hasattr(predictor, "system_prompt_override"):
                predictor.system_prompt_override = previous_override

        return {
            "preview_only": False,
            "vlm_configured": self.vlm_configured(),
            "sync_vlm": bool(sync_vlm and self.vlm_configured()),
            "prompts": prompts,
            "interpretation": interpretation.model_dump(mode="json"),
        }

    def _build_interpretation(
        self,
        event: UserEvent,
        features: dict[str, object],
        prediction: object,
        *,
        interpretation_id: str | None = None,
    ) -> InteractionInterpretation:
        hypotheses = list(getattr(prediction, "hypotheses", []) or [])
        hypotheses.sort(key=lambda item: item.confidence, reverse=True)

        primary = hypotheses[0] if hypotheses else IntentHypothesis(
            intent=IntentLabel.unknown,
            confidence=0.2,
            evidence=["No rule matched this event."],
        )
        second = hypotheses[1].confidence if len(hypotheses) > 1 else 0
        ambiguity = max(0.0, min(1.0, 1.0 - (primary.confidence - second)))
        policy, suggestions = self._assistance(event, primary, ambiguity, features)
        metadata = dict(getattr(prediction, "metadata", {}) or {})
        metadata.setdefault("task", "intent_predict")

        interpretation = InteractionInterpretation(
            interpretation_id=interpretation_id or f"interp_{uuid4().hex[:10]}",
            session_id=event.session_id,
            source_event_id=event.event_id,
            action_type=event.type,
            predictor=getattr(prediction, "predictor", "rule_based_multisignal"),
            predictor_version=getattr(prediction, "predictor_version", "v0"),
            predictor_metadata=metadata,
            primary_intent=primary.intent,
            confidence=primary.confidence,
            ambiguity=round(ambiguity, 3),
            target=InterpretationTarget(
                asset_id=features.get("asset_id"),
                part_id=features.get("part_id"),
                region=features.get("region"),
            ),
            hypotheses=hypotheses,
            evidence=self._evidence_with_ir(primary.evidence, features),
            assistance_policy=policy,
            suggested_assistance=suggestions,
            semantic_targets=[
                SemanticTarget.model_validate(item)
                for item in features.get("semantic_targets") or []
                if isinstance(item, dict)
            ],
            supervision_votes=dict(features.get("supervision_votes") or {}),
            features=features,
        )
        self.store.save_interpretation(interpretation)
        self._update_stage(interpretation)
        return interpretation

    def _attach_design_state_ir(self, features: dict[str, object]) -> None:
        if isinstance(features.get("design_state_ir"), dict) and features["design_state_ir"].get("matches"):
            # Already attached (e.g. reused for refine) — do not retrieve again.
            features["design_state_ir"] = {
                **features["design_state_ir"],
                "retrieve_skipped": True,
            }
            return
        if not self.ir_retriever.ready:
            features["design_state_ir"] = {
                "ready": False,
                "matches": [],
            }
            return
        features["ir_scope_hint"] = self._scope_hint_from_features(features)
        matches = self.ir_retriever.retrieve(features, top_k=5)
        axis_recommendation = self.ir_retriever.recommend_axes(matches, features)
        features["design_state_ir"] = {
            "ready": True,
            "matches": [match.to_feature() for match in matches],
            "source": str(self.ir_retriever.path),
            "retrieve_count": 1,
            **self.ir_retriever.query_profile(features),
            **axis_recommendation,
        }

    def _attach_creative_state(self, features: dict[str, object], event: UserEvent) -> None:
        attach_creative_state(features, event)
    def _attach_semantic_targets(self, features: dict[str, object]) -> None:
        """Redesign: three supervisors (cognition/gui/semantic-language) produce
        votes; fusion + IR target prior produce SemanticTarget[] for the planner."""
        ir = features.get("design_state_ir") if isinstance(features.get("design_state_ir"), dict) else {}
        matches = ir.get("matches") if isinstance(ir.get("matches"), list) else []
        ir_prior = (
            self.ir_retriever.recommend_target(matches, features)
            if matches
            else {"level_scores": {}}
        )
        features["ir_target_prior"] = ir_prior
        gui_vote = supervise_gui_interaction(features)
        semantic_vote = supervise_semantic_language(features)
        cognition = supervise_cognition(features)
        targets = fuse_targets(
            gui=gui_vote,
            semantic=semantic_vote,
            cognition=cognition,
            ir_prior=ir_prior,
            asset_id=str(features.get("asset_id") or ""),
            features=features,
        )
        features["semantic_targets"] = [target.model_dump(mode="json") for target in targets]
        features["supervision_votes"] = {
            "gui_interaction": gui_vote.model_dump(mode="json"),
            "semantic_language": semantic_vote.model_dump(mode="json"),
            "cognition": cognition.model_dump(mode="json"),
            "ir_target_prior": ir_prior,
        }

    def _evidence_with_ir(
        self,
        evidence: list[str],
        features: dict[str, object],
    ) -> list[str]:
        ir = features.get("design_state_ir")
        if not isinstance(ir, dict):
            return evidence
        matches = ir.get("matches")
        if not isinstance(matches, list) or not matches:
            return evidence
        top = matches[0]
        if not isinstance(top, dict):
            return evidence
        case_id = top.get("case_id")
        design_state = top.get("design_state")
        route = top.get("route")
        strength = top.get("evidence_strength")
        return [
            *evidence,
            f"Design-state IR matched {case_id}: state={design_state}, route={route}, evidence={strength}.",
        ]

    def _scope_hint_from_features(self, features: dict[str, object]) -> str:
        text_scope = self._scope_hint_from_text(str(features.get("intent_text") or ""))
        if text_scope:
            return text_scope
        selection_type = str(features.get("selection_type") or "")
        live = features.get("live_signals")
        if isinstance(live, dict) and int(live.get("local_zoom_count") or 0) >= 1:
            return "part_or_region"
        if selection_type in {"part", "brush", "mesh_region"} or features.get("part_id"):
            return "part_or_region"
        if isinstance(live, dict) and (
            int(live.get("viewport_orbit_count") or 0) >= 2
            or int(live.get("viewport_zoom_count") or 0) >= 1
        ):
            return "whole_object"
        creative_stage = str(features.get("creative_stage") or "")
        if creative_stage in {"silhouette", "global", "rough_form"}:
            return "whole_object"
        return "mixed_whole_and_part"

    def _scope_hint_from_text(self, text: str) -> str | None:
        normalized = text.lower()
        if not normalized.strip():
            return None
        if any(term in normalized for term in ["material", "texture", "surface", "color", "fabric", "finish", "材质", "纹理", "颜色", "表面"]):
            return "material_surface"
        if any(term in normalized for term in ["part", "component", "local", "brush", "部件", "组件", "局部", "某个部分", "当前部分"]):
            return "part_or_region"
        return "whole_object"

    def _extract_features(self, event: UserEvent) -> dict[str, object]:
        return extract_interaction_features(
            event,
            store=self.store,
            socket_score=self._socket_score,
            axis_alignment=self._axis_alignment,
        )
    def _socket_score(self, scores: object, evidence: object) -> float | None:
        if isinstance(scores, dict):
            value = scores.get("socket_compatibility")
            if isinstance(value, int | float):
                return round(float(value), 4)
        if isinstance(evidence, dict):
            value = evidence.get("socket_compatibility_score")
            if isinstance(value, int | float):
                return round(float(value), 4)
            seam = evidence.get("seam_validation")
            if isinstance(seam, dict):
                value = seam.get("socket_compatibility_score")
                if isinstance(value, int | float):
                    return round(float(value), 4)
        return None

    def _generate_hypotheses(
        self, event: UserEvent, features: dict[str, object]
    ) -> list[IntentHypothesis]:
        event_type = event.type
        hypotheses: list[IntentHypothesis] = []
        has_text = bool(features.get("intent_text"))
        same_part_edits = int(features.get("same_part_recent_edits") or 0)

        if event_type in {"part_select", "part_hover", "hover_focus", "semantic_hover_ended"}:
            hypotheses.append(
                IntentHypothesis(
                    intent=IntentLabel.target_part,
                    confidence=0.62,
                    evidence=["User focused a specific part."],
                )
            )

        if event_type == "brush_end":
            if has_text:
                hypotheses.append(
                    IntentHypothesis(
                        intent=IntentLabel.replace_region,
                        confidence=0.84,
                        evidence=[
                            "Brush selection ended on a region.",
                            "User provided text intent for the selected region.",
                        ],
                    )
                )
            hypotheses.append(
                IntentHypothesis(
                    intent=IntentLabel.semantic_focus,
                    confidence=0.58,
                    evidence=["Brush selection indicates a semantically important region."],
                )
            )
            if same_part_edits >= 3:
                hypotheses.append(
                    IntentHypothesis(
                        intent=IntentLabel.refine_boundary,
                        confidence=0.67,
                        evidence=["The same part or region has been edited repeatedly."],
                    )
                )

        if event_type == "drag_end":
            drag_length = float(features.get("drag_length") or 0)
            if drag_length > 0.05:
                hypotheses.append(
                    IntentHypothesis(
                        intent=IntentLabel.extend_part,
                        confidence=0.71,
                        evidence=[
                            "Drag has meaningful distance.",
                            "Drag direction is interpreted as outward from the selected part.",
                        ],
                    )
                )
                hypotheses.append(
                    IntentHypothesis(
                        intent=IntentLabel.change_proportion,
                        confidence=0.47,
                        evidence=["Dragging a part may express proportion adjustment."],
                    )
                )
            hypotheses.append(
                IntentHypothesis(
                    intent=IntentLabel.explore_shape,
                    confidence=0.39 if not has_text else 0.28,
                    evidence=["No precise semantic replacement request is required for drag."],
                )
            )

        if event_type == "smooth_end":
            strength = float(features.get("smooth_strength") or 0)
            preserve_boundary = bool(features.get("smooth_preserve_boundary"))
            hypotheses.append(
                IntentHypothesis(
                    intent=IntentLabel.deform_surface,
                    confidence=0.8 if strength > 0 else 0.72,
                    evidence=[
                        "Smooth tool ended on a local 3D surface region.",
                        "Smoothing brush parameters indicate surface refinement rather than replacement.",
                    ],
                )
            )
            if preserve_boundary:
                hypotheses.append(
                    IntentHypothesis(
                        intent=IntentLabel.refine_boundary,
                        confidence=0.64,
                        evidence=[
                            "Smooth operation requests boundary preservation.",
                            "Local geometry refinement should avoid changing adjacent regions.",
                        ],
                    )
                )

        if event_type in {"primitive_add_intent", "primitive_added"}:
            hypotheses.append(
                IntentHypothesis(
                    intent=IntentLabel.deform_surface,
                    confidence=0.76,
                    evidence=[
                        "User expressed an intent to add a 3D primitive.",
                        "Primitive type, transform, and relation provide structural edit evidence.",
                    ],
                )
            )
            hypotheses.append(
                IntentHypothesis(
                    intent=IntentLabel.explore_shape,
                    confidence=0.52,
                    evidence=["Adding a primitive may also be an exploratory rough-form move."],
                )
            )

        if event_type == "candidate_compared":
            hypotheses.append(
                IntentHypothesis(
                    intent=IntentLabel.compare_candidates,
                    confidence=0.76,
                    evidence=["User is inspecting generated alternatives."],
                )
            )
        if event_type == "candidate_accepted":
            hypotheses.append(
                IntentHypothesis(
                    intent=IntentLabel.accept_direction,
                    confidence=0.88,
                    evidence=["User accepted a candidate direction."],
                )
            )
        if event_type == "candidate_rejected":
            hypotheses.append(
                IntentHypothesis(
                    intent=IntentLabel.reject_direction,
                    confidence=0.83,
                    evidence=["User rejected a candidate direction."],
                )
            )
        if event_type == "generation_requested":
            mode = event.payload.get("mode") or event.payload.get("intent", {}).get("mode")
            creative_stage = str(features.get("creative_stage") or "")
            if creative_stage == "part" or mode == GenerationMode.replace:
                label = IntentLabel.replace_region
            elif creative_stage == "texture":
                label = IntentLabel.deform_surface
            else:
                label = IntentLabel.explore_shape
            hypotheses.append(
                IntentHypothesis(
                    intent=label,
                    confidence=0.8,
                    evidence=[
                        "User explicitly requested generation.",
                        f"Creative stage: {creative_stage or 'unspecified'}.",
                    ],
                )
            )
        if event_type == "undo":
            hypotheses.append(
                IntentHypothesis(
                    intent=IntentLabel.reject_direction,
                    confidence=0.64,
                    evidence=["Undo indicates the previous operation was not satisfactory."],
                )
            )

        return hypotheses or [
            IntentHypothesis(
                intent=IntentLabel.unknown,
                confidence=0.2,
                evidence=["Event is recorded for memory but not interpreted in v0."],
            )
        ]

    def _assistance(
        self,
        event: UserEvent,
        primary: IntentHypothesis,
        ambiguity: float,
        features: dict[str, object],
    ) -> tuple[AssistancePolicy, list[AssistanceSuggestion]]:
        if event.type in {"part_hover", "drag_update", "brush_update"}:
            return AssistancePolicy.observe, []

        if primary.intent == IntentLabel.replace_region:
            return AssistancePolicy.proactive_candidate, [
                AssistanceSuggestion(
                    type="generate",
                    mode=GenerationMode.replace,
                    label="Generate replacement candidates for this region",
                )
            ]
        if primary.intent == IntentLabel.refine_boundary:
            return AssistancePolicy.soft_suggestion, [
                AssistanceSuggestion(
                    type="generate",
                    mode=GenerationMode.replace,
                    label="Generate boundary-preserving part refinements",
                    metadata={
                        "suggested_next_action": "generate_boundary_refinements",
                        "preserve_boundary": True,
                    },
                )
            ]
        if primary.intent in {IntentLabel.extend_part, IntentLabel.change_proportion}:
            return AssistancePolicy.soft_suggestion, [
                AssistanceSuggestion(
                    type="generate",
                    mode=GenerationMode.drag_regenerate,
                    label="Generate drag-aware shape variations",
                )
            ]
        if primary.intent == IntentLabel.deform_surface:
            return AssistancePolicy.soft_suggestion, [
                AssistanceSuggestion(
                    type="generate",
                    mode=GenerationMode.replace,
                    label="Generate smooth local surface refinements",
                    metadata={
                        "suggested_next_action": "generate_boundary_refinements",
                        "preserve_boundary": features.get("smooth_preserve_boundary") is not False,
                        "smooth_operation_artifact_id": features.get("smooth_operation_artifact_id"),
                    },
                )
            ]

        if ambiguity > 0.68 and primary.confidence < 0.75:
            return AssistancePolicy.ask_clarification, [
                AssistanceSuggestion(
                    type="ask",
                    question="Should the system preserve the original part boundary?",
                    metadata={"suggested_next_action": "generate_drag_candidates"},
                )
            ]
        if primary.intent == IntentLabel.compare_candidates:
            socket_score = features.get("socket_compatibility_score")
            if isinstance(socket_score, int | float) and float(socket_score) >= 0.65:
                return AssistancePolicy.soft_suggestion, [
                    AssistanceSuggestion(
                        type="notify",
                        label="Socket fit is strong enough to preview or accept",
                        metadata={
                            "candidate_id": features.get("candidate_id"),
                            "socket_compatibility_score": round(float(socket_score), 4),
                            "suggested_next_action": "preview_or_accept_candidate",
                        },
                    )
                ]
            if isinstance(socket_score, int | float) and float(socket_score) > 0:
                return AssistancePolicy.soft_suggestion, [
                    AssistanceSuggestion(
                        type="notify",
                        label="Socket fit may need another variant",
                        metadata={
                            "candidate_id": features.get("candidate_id"),
                            "socket_compatibility_score": round(float(socket_score), 4),
                            "suggested_next_action": "compare_more_candidates",
                        },
                    )
                ]
        if primary.intent in {IntentLabel.accept_direction, IntentLabel.reject_direction}:
            return AssistancePolicy.interpret_silently, []

        return AssistancePolicy.soft_suggestion, [
            AssistanceSuggestion(
                type="notify",
                label=f"Interpreted as {primary.intent.value}",
                metadata={"features": features},
            )
        ]

    def _update_stage(self, interpretation: InteractionInterpretation) -> None:
        session = self.store.get_session(interpretation.session_id)
        if session is None:
            return
        phase = session.stage.phase
        suggested_action = session.stage.suggested_action
        goal = session.stage.current_goal

        if interpretation.primary_intent == IntentLabel.replace_region:
            phase = DesignPhase.local_replacement
            suggested_action = "generate_replace_candidates"
            goal = self._goal_text(interpretation, "replace selected region")
        elif interpretation.primary_intent in {
            IntentLabel.extend_part,
            IntentLabel.change_proportion,
            IntentLabel.bend_or_curve,
        }:
            phase = DesignPhase.drag_modification
            suggested_action = "generate_drag_candidates"
            goal = self._goal_text(interpretation, "modify selected part through drag")
        elif interpretation.primary_intent == IntentLabel.compare_candidates:
            phase = DesignPhase.candidate_comparison
            suggested_action = None
        elif interpretation.primary_intent == IntentLabel.accept_direction:
            payload_suggested_action = interpretation.features.get("payload_suggested_action")
            commit_policy = str(interpretation.features.get("commit_policy") or "")
            creative_stage = str(interpretation.features.get("creative_stage") or "")
            if isinstance(payload_suggested_action, str) and payload_suggested_action:
                phase = DesignPhase.exploring
                suggested_action = payload_suggested_action
            elif commit_policy == "direction_memory" and creative_stage in {
                "silhouette",
                "global",
            }:
                phase = DesignPhase.exploring
                suggested_action = "continue_rough_form_exploration"
            else:
                phase = DesignPhase.refinement
                suggested_action = None
        elif interpretation.primary_intent == IntentLabel.reject_direction:
            phase = DesignPhase.candidate_comparison
            payload_suggested_action = interpretation.features.get("payload_suggested_action")
            suggested_action = (
                payload_suggested_action
                if isinstance(payload_suggested_action, str) and payload_suggested_action
                else "revise_candidate_direction"
            )
        elif interpretation.primary_intent == IntentLabel.target_part:
            phase = DesignPhase.part_selection
        elif interpretation.primary_intent == IntentLabel.explore_shape:
            phase = DesignPhase.exploring
            suggested_action = "generate_divergent_candidates"
            goal = self._goal_text(interpretation, "explore shape directions")

        stage = StageState(
            phase=phase,
            confidence=interpretation.confidence,
            current_goal=goal,
            active_asset_id=interpretation.target.asset_id or session.stage.active_asset_id,
            active_part_id=interpretation.target.part_id or session.stage.active_part_id,
            suggested_action=suggested_action,
            evidence=interpretation.evidence,
        )
        self.store.save_stage(interpretation.session_id, stage)

    def _goal_text(self, interpretation: InteractionInterpretation, fallback: str) -> str:
        part = interpretation.target.part_id
        if part:
            return f"{fallback}: {part}"
        return fallback

    def _axis_alignment(self, vector: tuple[float, float, float]) -> dict[str, object]:
        axes = ["x", "y", "z"]
        magnitudes = [abs(item) for item in vector]
        total = sum(magnitudes) or 1.0
        index = magnitudes.index(max(magnitudes))
        return {"axis": axes[index], "score": round(magnitudes[index] / total, 3)}
