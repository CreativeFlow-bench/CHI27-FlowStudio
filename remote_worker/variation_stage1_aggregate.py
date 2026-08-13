#!/usr/bin/env python3
"""Aggregate independent real-KG audits, then rescore and compile four directions."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, os.getenv("CF_TRANSFER_PIPELINE_ROOT", "/root/creativeflow_pipeline"))

from pipeline_transfer_engine import SourceSpec
from variation_contracts import contract_for, score_graph_candidate, select_balanced_candidates
from variation_graph_directions import compile_transfer_spec, validate_transfer_spec


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", action="append", required=True)
    parser.add_argument("--source-image", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    audits = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.audit]
    base = next((item for item in audits if item.get("source_elements")), None)
    if not base:
        raise RuntimeError("no source-grounded KG audit supplied")
    stage = str(base["stage"])
    contract = contract_for(stage)
    object_type = str((base.get("source_elements") or {}).get("object_identity") or "").lower()
    if not object_type or object_type == "object":
        raise RuntimeError("aggregate requires a concrete source identity")
    graph_origin = str(base["graph_origin"])
    source_elements = base["source_elements"]
    part_semantics = base.get("part_semantics") or {}
    abstract: list[str] = []
    for audit in audits:
        for item in audit.get("abstract_descriptors", []):
            value = str(item).strip()
            if value and value not in abstract:
                abstract.append(value)

    merged: dict[str, dict[str, Any]] = {}
    for audit in audits:
        if audit.get("stage") != stage or audit.get("graph_origin") != graph_origin:
            raise RuntimeError("cannot aggregate audits from different variation contracts")
        for candidate in audit.get("graph_candidates", []):
            label = re.sub(r"\s+", " ", str(candidate.get("label") or "").strip().lower())
            if not label or candidate.get("semantic_distance_bucket") not in {"near", "far"}:
                continue
            current = merged.get(label)
            if current is None or float(candidate.get("score") or 0) > float(current.get("score") or 0):
                merged[label] = candidate

    candidates = list(merged.values())
    for candidate in candidates:
        candidate["variation_scoring"] = score_graph_candidate(
            stage=stage,
            candidate=candidate,
            graph_origin=graph_origin,
            seed_terms=contract.graph_seed_dimensions,
            source_elements=source_elements,
            part_semantics=part_semantics,
            extra_relevance_terms=abstract,
        )
    selected = select_balanced_candidates(candidates, near_count=2, far_count=2)
    if len(selected) != 4:
        raise RuntimeError("aggregated real-KG pool still lacks exact 2 near + 2 far")

    source = SourceSpec(
        source_id=f"{object_type}_{stage}_aggregate",
        object_type=object_type,
        image_paths=[args.source_image],
        identity_constraints=[f"lock {item}" for item in contract.locked_facets],
    )
    directions: list[dict[str, Any]] = []
    for index, candidate in enumerate(selected, start=1):
        spec = compile_transfer_spec(
            stage=stage,
            object_type=object_type,
            candidate=candidate,
            source=source,
            source_elements=source_elements,
            part_semantics=part_semantics,
        )
        validate_transfer_spec(stage, spec, part_semantics)
        anchor_slug = re.sub(r"[^a-z0-9]+", "_", str(candidate["label"]).lower()).strip("_")
        directions.append({
            "direction_id": f"{stage}_{index:02d}_{anchor_slug[:40]}",
            "anchor": candidate["label"],
            "distance_bucket": candidate["semantic_distance_bucket"],
            "semantic_distance": candidate.get("semantic_distance") or {},
            "semantic_bridging": candidate.get("semantic_bridging") or {},
            "graph_provenance": candidate.get("provenance") or [],
            "original_kg_score": candidate.get("score"),
            "variation_scoring": candidate["variation_scoring"],
            "transfer_spec": spec,
            "open_facets": list(contract.open_facets),
            "locked_facets": list(contract.locked_facets),
        })
    result = {
        "schema_version": "creativeflow.variation-stage1.v1",
        "status": "completed",
        "stage": stage,
        "graph_origin": graph_origin,
        "source_elements": source_elements,
        "part_semantics": part_semantics,
        "abstract_descriptors": abstract,
        "graph_candidates": candidates,
        "directions": directions,
        "selection_policy": {"near": 2, "far": 2, "fail_closed": True, "multi_audit_aggregation": True},
        "input_audits": args.audit,
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"directions": [(item["distance_bucket"], item["anchor"]) for item in directions]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
