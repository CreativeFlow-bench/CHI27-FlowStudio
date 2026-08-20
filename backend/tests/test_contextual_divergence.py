"""Unit tests for the contextual divergence fragment pipeline (incremental spec)."""

from __future__ import annotations

import json

import pytest

from app.services.divergence import contextual_graph_policy as policy
from app.services.divergence import fragment_decoder as decoder
from app.services.intent.design_state_ir import DesignStateIRRetriever


def _source() -> dict:
    return {"graph": "wikidata", "id": "Q483985", "label": "snowman"}


def _first_hop() -> dict:
    return {"id": "Q734898", "label": "snowball", "relation": "P527", "relation_family": "part_of_has_part"}


def _second_hop() -> dict:
    return {"graph": "asknature", "id": "https://asknature.org/strategy/x", "label": "Optimally Packing Spheres"}


def test_operation_scope_matrix() -> None:
    assert policy.operation_allowed("deform", "whole")
    assert not policy.operation_allowed("replace", "whole")
    assert policy.operation_allowed("replace", "selected_part")
    assert policy.operation_allowed("finish", "material_region")


def test_relation_whitelist_per_scope() -> None:
    whole_relations = set(policy.allowed_relations("whole"))
    part_relations = set(policy.allowed_relations("selected_part"))
    assert {"P31", "P279", "P527", "P366"} <= whole_relations
    assert "P186" in part_relations


def test_fragment_decode_passes_and_grounds_phrase() -> None:
    fragment = decoder.decode_fragment(
        asset_id="asset_1",
        scope="whole",
        target_label_zh="雪人",
        target_id=None,
        operation="deform",
        constraints=["preserve snowman identity"],
        source_entity=_source(),
        first_hop=_first_hop(),
        second_hop=_second_hop(),
        relation_family="part_of_has_part",
    )
    assert fragment is not None
    assert fragment["hard_gates"]["passed"] is True
    assert fragment["attribute_delta"]["attribute"] == "roundness"
    assert fragment["display_label_zh"] == "更圆润"
    assert "雪人" in fragment["full_phrase_zh"]


def test_fragment_decode_rejects_unmapped_donor() -> None:
    fragment = decoder.decode_fragment(
        asset_id="asset_1",
        scope="whole",
        target_label_zh="雪人",
        target_id=None,
        operation="deform",
        constraints=[],
        source_entity=_source(),
        first_hop=_first_hop(),
        second_hop={"graph": "asknature", "id": "x", "label": "Unrelated Narrative Metaphor Only"},
        relation_family="part_of_has_part",
    )
    assert fragment is None


def test_fragment_decode_rejects_wrong_scope_operation() -> None:
    fragment = decoder.decode_fragment(
        asset_id="asset_1",
        scope="whole",
        target_label_zh="雪人",
        target_id=None,
        operation="replace",
        constraints=[],
        source_entity=_source(),
        first_hop=_first_hop(),
        second_hop=_second_hop(),
        relation_family="part_of_has_part",
    )
    assert fragment is None


def test_groups_are_dynamic_per_scope() -> None:
    part_groups = [group["key"] for group in policy.groups_for_scope("selected_part")]
    assert "shape" in part_groups and "connection" in part_groups
    whole_groups = [group["key"] for group in policy.groups_for_scope("whole")]
    assert "global_form" in whole_groups


def test_ir_retrieval_matches_labels_not_intent_text(tmp_path) -> None:
    payload = {
        "episodes": [
            {
                "episode_id": "text_hit",
                "text": "让鼻子更弯曲",
                "gt_state": "Refinement",
                "gt_hierarchy": "Part",
                "signal_vector": [0, 1, 1, 0, 0, 0],
                "signal_codes": ["undo_redo_loop", "select_part"],
            },
            {
                "episode_id": "ir_hit",
                "text": "无关文本",
                "gt_state": "Exploration",
                "gt_hierarchy": "Silhouette",
                "signal_vector": [1, 0, 0, 1, 0, 1],
                "signal_codes": ["long_compare", "zoom_out", "match_reference"],
            },
        ]
    }
    path = tmp_path / "episodes.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    retriever = DesignStateIRRetriever(path=path, limit=10)
    matches = retriever.retrieve(
        {
            "intent_text": "让鼻子更弯曲",
            "signal_codes": ["long_compare", "zoom_out", "match_reference"],
            "signal_vector": [1, 0, 0, 1, 0, 1],
            "gt_state": "Exploration",
            "gt_hierarchy": "Silhouette",
        },
        top_k=2,
    )
    assert matches[0].case_id == "ir_hit"


def test_split_retrieve_uses_text_only_for_content_not_state(tmp_path) -> None:
    payload = {
        "episodes": [
            {
                "episode_id": "text_hit",
                "text": "让鼻子更弯曲",
                "gt_state": "Refinement",
                "gt_hierarchy": "Part",
                "signal_vector": [1, 0, 0, 1, 0, 0],
                "signal_codes": ["long_compare", "zoom_out"],
            },
            {
                "episode_id": "ir_hit",
                "text": "无关文本",
                "gt_state": "Exploration",
                "gt_hierarchy": "Silhouette",
                "signal_vector": [1, 0, 0, 1, 0, 1],
                "signal_codes": ["long_compare", "zoom_out", "match_reference"],
            },
        ]
    }
    path = tmp_path / "episodes.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    retriever = DesignStateIRRetriever(path=path, limit=10)
    ir_top, content_top, vote = retriever.split_retrieve(
        {
            "intent_text": "让鼻子更弯曲",
            "signal_codes": ["long_compare", "zoom_out", "match_reference"],
            "signal_vector": [1, 0, 0, 1, 0, 1],
        },
        pool_k=2,
        vote_k=1,
    )
    assert ir_top[0].case_id == "ir_hit"
    assert content_top[0].case_id == "text_hit"
    assert vote["predicted_state"] == "Exploration"
    assert vote["predicted_hierarchy"] == "Part"
