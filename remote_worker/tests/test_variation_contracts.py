from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from variation_contracts import (  # noqa: E402
    score_graph_candidate,
    select_balanced_candidates,
    validate_part_semantics,
)


def candidate(label: str, bucket: str, score: float = 4.0) -> dict:
    return {
        "label": label,
        "score": score,
        "semantic_distance_bucket": bucket,
        "provenance": ["second_hop:source"],
        "summary": {"description": label},
    }


def test_ontology_noise_is_rejected() -> None:
    item = candidate("probability distribution", "far")
    result = score_graph_candidate(
        stage="low_fidelity",
        candidate=item,
        graph_origin="snowman",
        seed_terms=["silhouette"],
    )
    assert not result["passed"]
    assert "ontology_noise" in result["reasons"]


def test_part_requires_sam3d_semantic_evidence() -> None:
    payload = {
        "part_id": "cluster_7",
        "canonical_name": "nose",
        "semantic_role": "facial protrusion",
        "shape": "tapered cone",
        "attachment": "embedded at front of head",
        "confidence": 0.91,
        "face_labels_path": "/tmp/labels.npy",
    }
    assert validate_part_semantics(payload) == payload


def test_exact_two_near_two_far_selection() -> None:
    items = [
        candidate("segmented shell", "near", 8.0),
        candidate("branching framework", "near", 7.0),
        candidate("spiral lattice", "far", 8.0),
        candidate("porous membrane", "far", 7.0),
    ]
    for item in items:
        item["variation_scoring"] = score_graph_candidate(
            stage="low_fidelity",
            candidate=item,
            graph_origin="snowman",
            seed_terms=["silhouette", "proportion"],
        )
    selected = select_balanced_candidates(items)
    assert len(selected) == 4
    assert [item["variation_scoring"]["distance_bucket"] for item in selected].count("near") == 2
    assert [item["variation_scoring"]["distance_bucket"] for item in selected].count("far") == 2


def test_generic_open_dimension_is_not_a_direction() -> None:
    result = score_graph_candidate(
        stage="texture",
        candidate=candidate("material", "near"),
        graph_origin="snow",
        seed_terms=["surface finish"],
    )
    assert not result["passed"]
    assert "generic_open_dimension" in result["reasons"]

