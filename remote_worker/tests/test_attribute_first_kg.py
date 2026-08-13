from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from variation_graph_directions import select_top_diverse  # noqa: E402


def _candidate(label: str, score: float, graph: str, attribute: str, passed: bool = True) -> dict:
    return {
        "raw_kg_target": label,
        "attribute_id": attribute,
        "graph_evidence": [{"graph": graph}],
        "paper_scoring": {"passed": passed, "total_score": score},
    }


def test_selects_four_feasible_candidates_without_distance_buckets() -> None:
    candidates = [
        _candidate("form a", 0.92, "wikidata", "attr_01"),
        _candidate("form b", 0.89, "getty_aat", "attr_02"),
        _candidate("form c", 0.88, "asknature", "attr_03"),
        _candidate("form d", 0.86, "wikidata", "attr_04"),
        _candidate("form e", 0.84, "getty_aat", "attr_01"),
        _candidate("rejected", 0.99, "asknature", "attr_02", passed=False),
    ]
    selected = select_top_diverse(candidates)
    assert len(selected) == 4
    assert all("semantic_distance" not in item for item in selected)
    assert len({item["attribute_id"] for item in selected}) >= 3
    assert len({e["graph"] for item in selected for e in item["graph_evidence"]}) == 3

