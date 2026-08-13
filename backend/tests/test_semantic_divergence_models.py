"""Semantic divergence contract and persistence boundaries."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models import (
    FourStageRun,
    SemanticCandidate,
    SemanticDivergenceParams,
    SemanticDivergenceResponse,
)
from app.services.storage.four_stage_store import FourStageStore


def _candidate() -> SemanticCandidate:
    return SemanticCandidate(
        candidate_id="kw_1",
        display_label_zh="熔岩流线",
        label_en="lava flow lines",
        group="semantic_transfer",
        target_ref={"asset_id": "asset_1", "type": "part", "id": "support"},
        operation="deform",
        semantic_anchor="cooling lava",
        prompt_phrase="reshape only the support with solidified lava-flow contours",
        attribute_delta={"attribute": "contour", "change": "solidified flow ridges"},
        scores={"identity": 0.9, "scope": 0.9, "relevance": 0.9, "specificity": 0.9, "novelty": 0.8},
        provenance={"generator": "gemini", "mode": "model_only"},
    )


def _response() -> SemanticDivergenceResponse:
    return SemanticDivergenceResponse(
        divergence_id="div_1",
        run_id="run_1",
        decision_id="decision_1",
        request_key="request_1",
        generator_model="gemini-3.5-flash",
        knowledge_route={"mode": "model_only"},
        validation_counts={"accepted": 1},
        latency_ms=123,
        candidates=[_candidate()],
    )


def test_semantic_divergence_params_are_bounded() -> None:
    """Removing parameter bounds or the shared count mapping breaks this contract."""
    params = SemanticDivergenceParams(temperature=0.6, strictness=0.8)
    assert params.per_group_count == 5
    assert params.candidate_count == 20
    assert SemanticDivergenceParams(per_group_count=8).candidate_count == 32
    with pytest.raises(ValidationError):
        SemanticDivergenceParams(per_group_count=4)
    with pytest.raises(ValidationError):
        SemanticDivergenceParams(temperature=1.1, strictness=0.8)


def test_legacy_explicit_candidate_count_remains_readable() -> None:
    """Removing legacy count compatibility would break persisted 9-candidate tasks."""
    params = SemanticDivergenceParams(candidate_count=9)

    assert params.candidate_count == 9
    assert params.per_group_count is None


def test_candidate_keeps_short_label_and_full_prompt_separate() -> None:
    """Replacing the UI label with a generation phrase breaks the display contract."""
    candidate = _candidate()
    assert candidate.display_label_zh == "熔岩流线"
    assert "support" in candidate.prompt_phrase


def test_store_round_trips_semantic_divergence_and_legacy_null() -> None:
    """Dropping the JSON column or treating old NULL rows as payloads breaks reloads."""
    store = FourStageStore()
    run = FourStageRun(run_id="run_1", session_id="session_1", semantic_divergence=_response())
    store.save_run(run)
    restored = store.get_run(run.run_id)
    assert restored is not None
    assert restored.semantic_divergence is not None
    assert restored.semantic_divergence.candidates[0].prompt_phrase == _candidate().prompt_phrase

    legacy = FourStageRun(run_id="run_2", session_id="session_1")
    store.save_run(legacy)
    restored_legacy = store.get_run(legacy.run_id)
    assert restored_legacy is not None
    assert restored_legacy.semantic_divergence is None
