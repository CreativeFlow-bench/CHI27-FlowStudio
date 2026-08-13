"""Unit tests for the three-signal supervision + target fusion redesign."""

from __future__ import annotations

from app.models import CognitionOutput, SupervisorVote
from app.services.signals.cognition_supervisor import supervise_cognition
from app.services.signals.gui_interaction_supervisor import supervise_gui_interaction
from app.services.signals.semantic_language_supervisor import supervise_semantic_language
from app.services.signals.target_fusion import fuse_targets
from app.services.intent.design_state_ir import DesignStateIRRetriever
from app.services.shared.labels import ZH_LABELS, clean_part_label, zh_label


def _features(**overrides):
    features = {
        "event_type": "action_atom_created",
        "selection_type": "none",
        "creative_stage": "global",
        "intent_text": "",
        "part_id": None,
        "asset_id": "asset_1",
        "live_signals": {},
        "signals": {},
        "image_ref_count": 0,
        "semantic_distance": 0.0,
        "recent_undo_count": 0,
        "same_event_type_recent_count": 0,
        "creative_state": "idle",
        "creative_state_confidence": 0.4,
    }
    features.update(overrides)
    return features


def test_gui_brush_on_named_part_votes_part() -> None:
    vote = supervise_gui_interaction(
        _features(
            tool="brush",
            part_id="part_nose",
            signals={"semantic": {"part_id": "part_nose", "part_label": "胡萝卜鼻子"}},
            live_signals={"brush_count": 2, "mask_coverage": 0.6, "hover_count": 3},
        )
    )
    assert vote.level_scores["part"] > 0.5
    assert vote.part_candidates
    assert vote.part_candidates[0]["label_zh"] == "胡萝卜鼻子"


def test_gui_annotation_and_orbit_vote_silhouette() -> None:
    vote = supervise_gui_interaction(
        _features(
            event_type="annotation_stroke_committed",
            live_signals={"annotation_count": 2, "viewport_orbit_count": 3},
        )
    )
    assert vote.silhouette_evidence
    assert vote.level_scores["silhouette"] >= 0.3


def test_semantic_language_names_part_and_operation() -> None:
    vote = supervise_semantic_language(
        _features(intent_text="让鼻子更弯曲", part_id="part_nose")
    )
    assert vote.operation_hint == "deform"
    assert any("鼻子" in str(item.get("label_zh")) for item in vote.part_candidates)


def test_semantic_language_material_keyword() -> None:
    vote = supervise_semantic_language(_features(intent_text="做成哑光材质"))
    assert vote.operation_hint == "finish"
    assert vote.level_scores["material_region"] >= 0.45


def test_cognition_hesitation_requires_clarification() -> None:
    cognition = supervise_cognition(
        _features(
            live_signals={"dwell_ms": 5000, "compare_dwell_ms": 3000},
            recent_undo_count=3,
            creative_state="exploring",
        )
    )
    assert cognition.hesitation >= 0.7
    assert cognition.require_clarification is True
    assert cognition.confidence_modifier < 1.0


def test_cognition_stable_fixation_modulates_up() -> None:
    cognition = supervise_cognition(
        _features(live_signals={"dwell_ms": 1200}, creative_state="ready_for_help", creative_state_confidence=0.8)
    )
    assert cognition.fixation_stable is True
    assert cognition.require_clarification is False
    assert cognition.confidence_modifier >= 0.8


def test_fusion_merges_votes_and_semantics() -> None:
    gui = supervise_gui_interaction(
        _features(tool="brush", part_id="part_nose", signals={"semantic": {"part_label": "胡萝卜鼻子"}}, live_signals={"brush_count": 2})
    )
    semantic = supervise_semantic_language(_features(intent_text="让鼻子更弯曲", part_id="part_nose"))
    cognition = CognitionOutput(hesitation=0.2, fixation_stable=True, creative_state="refining", confidence_modifier=0.95, require_clarification=False, evidence=[])
    targets = fuse_targets(
        gui=gui,
        semantic=semantic,
        cognition=cognition,
        ir_prior={"level_scores": {"part": 0.6}},
        asset_id="asset_1",
        features=_features(part_id="part_nose"),
    )
    assert targets
    top = targets[0]
    assert top.level == "part"
    assert top.semantic.label_zh == "鼻子"
    assert top.operation_hint == "deform"
    assert top.confidence > 0.4


def test_fusion_conflict_requires_clarification() -> None:
    gui = SupervisorVote(
        supervisor="gui_interaction",
        level_scores={"part": 0.8},
        part_candidates=[{"part_id": "part_nose", "label_zh": "鼻子", "score": 0.8, "evidence": ["brush"]}],
    )
    semantic = SupervisorVote(
        supervisor="semantic_language",
        level_scores={"part": 0.7},
        part_candidates=[{"part_id": "part_scarf", "label_zh": "围巾", "score": 0.7, "evidence": ["text"]}],
        operation_hint="deform",
    )
    cognition = CognitionOutput(hesitation=0.1, fixation_stable=True, creative_state="refining", confidence_modifier=0.9, require_clarification=False, evidence=[])
    targets = fuse_targets(
        gui=gui,
        semantic=semantic,
        cognition=cognition,
        ir_prior={"level_scores": {}},
        asset_id="asset_1",
        features=_features(),
    )
    assert targets and targets[0].requires_clarification is True


def test_ir_recommend_target_uses_level_and_negative_supervision(tmp_path) -> None:
    row = {
        "ir_id": "r1",
        "case_id": "c1",
        "design_state": "early_exploration",
        "route": "generate_local_variants",
        "signals": ["select_part"],
        "scope_hint": "part_or_region",
        "target_level": "part",
        "recommended_axes": ["Structural"],
        "evidence_strength": "medium",
        "state_agreement": 1.0,
        "route_agreement": 1.0,
        "signal_agreement": 1.0,
        "text": "Design state: Early exploration\nSignals: select / focus part",
    }
    path = tmp_path / "rows.jsonl"
    path.write_text(__import__("json").dumps(row) + "\n", encoding="utf-8")
    retriever = DesignStateIRRetriever(path=path, limit=1)
    features = _features(part_id="part_x", selection_type="part")
    matches = [match.to_feature() for match in retriever.retrieve(features, top_k=1)]
    prior = retriever.recommend_target(matches, features)
    assert prior["level_scores"]["part"] > 0
    assert prior["negative_supervision"]["do_not_assume_part"] is False


def test_shared_labels_are_the_single_source() -> None:
    assert zh_label("snowman") == "雪人"
    assert zh_label("nose") == "鼻子"
    assert zh_label("top hat") == "高帽"
    assert zh_label("kettle", "水壶") == "水壶"
    assert clean_part_label("part_nose") is None
    assert clean_part_label("nose") == "鼻子"
    assert clean_part_label("handle_01") == "把手"
    assert "snowman" in ZH_LABELS and "handle" in ZH_LABELS
