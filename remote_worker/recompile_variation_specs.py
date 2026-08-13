#!/usr/bin/env python3
"""Recompile visual transfer specs without repeating KG retrieval."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from variation_graph_directions import (
    SourceSpec,
    compile_transfer_spec,
    validate_transfer_spec,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage1", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    result = json.loads(Path(args.stage1).read_text(encoding="utf-8"))
    request = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if result.get("status") != "completed":
        raise RuntimeError("transfer-spec recompilation requires a completed Stage 1 result")

    stage = str(result["stage"])
    object_type = str(request["object_type"])
    source = SourceSpec(
        source_id=str(request.get("source_id") or "variation_recompile"),
        object_type=object_type,
        mesh_path=str(request.get("source_mesh_path") or ""),
        image_paths=[str(request["source_image_path"])] if request.get("source_image_path") else [],
        render_paths=[str(item) for item in request.get("source_multiview_paths") or []],
    )
    candidates = {
        str(item.get("label") or "").strip().lower(): item
        for item in result.get("graph_candidates") or []
    }
    for direction in result.get("directions") or []:
        anchor = str(direction.get("anchor") or "").strip().lower()
        candidate = candidates.get(anchor)
        relation = direction.get("candidate_relation") or {}
        if not candidate or not relation:
            raise RuntimeError(f"direction lacks relation/target evidence: {direction.get('direction_id')}")
        spec = compile_transfer_spec(
            stage=stage,
            object_type=object_type,
            relation=relation,
            candidate=candidate,
            source=source,
            source_elements=result.get("source_elements") or {},
            part_semantics=result.get("part_semantics") or {},
        )
        validate_transfer_spec(stage, spec, result.get("part_semantics") or {})
        direction["transfer_spec"] = spec

    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
