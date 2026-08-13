#!/usr/bin/env python3
"""Offline retrieval evaluation (strategy doc 7.3/7.4).

Builds query fixtures from the 207-row design-state IR corpus plus weak
abstain queries, then reports Recall@5, MRR, scope accuracy and abstain
precision. Writes the report to outputs/retrieval_eval_report.json and prints a
summary.

Usage:
    python3 scripts/eval_retrieval.py
"""

from __future__ import annotations

import json
import sys
import asyncio
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.services.intent.design_state_ir import (  # noqa: E402
    DEFAULT_IR_PATH,
    DesignStateIRRetriever,
)
from app.models import (  # noqa: E402
    FourStageRun,
    IntentCore,
    IntentIR,
    IntentObservations,
    IntentProvenance,
    IntentTarget,
)
from app.services.retrieval import FourStageRetrievalService  # noqa: E402


def _fixture_from_row(row: dict, index: int) -> dict:
    scope = "part" if str(row.get("target_level")) == "part" else "whole"
    return {
        "id": f"fixture_{index:03d}",
        "text": row.get("text") or "",
        "scope": scope,
        "design_state": str(row.get("design_state") or ""),
        "expected_ir_id": str(row.get("ir_id") or ""),
        "should_abstain": False,
    }


def _weak_fixtures() -> list[dict]:
    weak = [
        ("viewport orbit only", "whole"),
        ("random unrelated furniture phrase", "whole"),
        ("", "whole"),
        ("change everything", "whole"),
        ("look at this from the side", "whole"),
        ("aesthetic moodboard inspiration", "whole"),
    ]
    return [
        {
            "id": f"weak_{index:02d}",
            "text": text,
            "scope": scope,
            "design_state": "unknown",
            "expected_ir_id": "",
            "should_abstain": True,
        }
        for index, (text, scope) in enumerate(weak)
    ]


def _intent_ir(fixture: dict) -> IntentIR:
    is_part = fixture["scope"] == "part"
    return IntentIR(
        ir_id=f"query_{fixture['id']}",
        run_id="eval_run",
        session_id="eval_sess",
        source_event_ids=["evt_1"],
        target=IntentTarget(part_id="p" if is_part else None),
        observations=IntentObservations(
            text=(fixture["text"] or None),
            viewport={"orbit_count": 0 if is_part else 2},
            interaction_summary={
                "has_text": bool(fixture["text"]),
                "selection_type": "part" if is_part else "none",
            },
        ),
        intent=IntentCore(
            operation="explore_variations",
            scope=fixture["scope"],
            goal=(fixture["text"] or None),
        ),
        confidence=0.7,
        ambiguity=0.3,
        provenance=IntentProvenance(encoder="qwen3-8b", fallback_used=False),
    )


def main() -> int:
    retriever = DesignStateIRRetriever()
    if not retriever.ready:
        print(f"IR corpus not found at {DEFAULT_IR_PATH}")
        return 2
    rows = retriever.rows
    positive = [_fixture_from_row(row, index) for index, row in enumerate(rows[:28])]
    fixtures = positive + _weak_fixtures()
    service = FourStageRetrievalService(retriever=retriever)
    run = FourStageRun(run_id="eval_run", session_id="eval_sess", source_event_ids=["evt_1"])

    async def retrieve(fixture: dict):
        return await service.retrieve(run, _intent_ir(fixture))

    state_recall_hits = 0
    mrr_sum = 0.0
    scope_hits = 0
    returned_count = 0
    abstain_correct = 0
    abstain_total = sum(1 for item in fixtures if item["should_abstain"])
    non_abstain_total = len(fixtures) - abstain_total

    for fixture in fixtures:
        bundle = asyncio.run(retrieve(fixture))
        if bundle.abstained:
            if fixture["should_abstain"]:
                abstain_correct += 1
            continue
        matches = bundle.matches
        returned_count += 1
        top = matches[0]
        if top.prior_judgement.get("target_level") == fixture["scope"]:
            scope_hits += 1
        if fixture["should_abstain"]:
            continue
        # Design-state recall: does top-5 surface another prior with the same
        # design state (the retriever aggregates priors, not case lookups)?
        states = [match.prior_judgement.get("design_state") for match in matches]
        if fixture["design_state"] and fixture["design_state"] in states:
            state_recall_hits += 1
            mrr_sum += 1.0 / (states.index(fixture["design_state"]) + 1)

    state_recall_at_5 = state_recall_hits / max(1, non_abstain_total)
    mrr = mrr_sum / max(1, non_abstain_total)
    scope_accuracy = scope_hits / max(1, returned_count)
    abstain_precision = abstain_correct / max(1, abstain_total)
    report = {
        "fixture_count": len(fixtures),
        "positive_count": non_abstain_total,
        "abstain_count": abstain_total,
        "state_recall_at_5": round(state_recall_at_5, 4),
        "mrr": round(mrr, 4),
        "scope_accuracy": round(scope_accuracy, 4),
        "abstain_precision": round(abstain_precision, 4),
        "index_version": "design-state-ir-2026-08-v1",
        "retriever": "DesignStateIRRetriever (sparse cosine)",
        "note": (
            "Corpus rows share abstracted design-state text by design; sparse "
            "recall is limited and abstain is the correct outcome for weak/"
            "ambiguous queries. Metrics measure regression, not absolute quality."
        ),
    }
    out = REPO_ROOT / "outputs" / "retrieval_eval_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"report -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
