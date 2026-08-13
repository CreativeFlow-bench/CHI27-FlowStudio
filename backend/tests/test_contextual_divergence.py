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


def test_ir_retrieval_text_strips_hard_case_identity(tmp_path) -> None:
    row = {
        "ir_id": "r1",
        "case_id": "c1",
        "design_state": "early_exploration",
        "route": "generate_local_variants",
        "signals": ["select_part"],
        "scope_hint": "part_or_region",
        "recommended_axes": ["Structural"],
        "evidence_strength": "low",
        "state_agreement": 1.0,
        "route_agreement": 1.0,
        "signal_agreement": 1.0,
        "text": (
            "Design state: Early exploration\n"
            "Signals: select / focus part\n"
            "CreativeFlow route: Generate local part variants\n"
            "Task group: Task 1 · Character / Organic Modeling\n"
        ),
    }
    path = tmp_path / "rows.jsonl"
    path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    retriever = DesignStateIRRetriever(path=path, limit=1)
    tokens = retriever.rows[0]["_tokens"]
    assert "task" not in tokens
    assert "organic" not in tokens
    assert "modeling" not in tokens
