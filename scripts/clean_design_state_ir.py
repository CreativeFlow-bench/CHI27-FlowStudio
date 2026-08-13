from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "intentdatabase"
OUT_DIR = RAW_DIR / "cleaned"


STATE_EN = {
    "early_exploration": "Early exploration",
    "coarse_forming": "Coarse forming",
    "local_refinement": "Local refinement",
    "relationship_adjustment": "Relationship adjustment",
    "material_refinement": "Material refinement",
    "evaluation": "Evaluation",
}

ROUTE_EN = {
    "no_intervention": "Observe only",
    "generate_contour_variants": "Generate silhouette / contour variants",
    "generate_local_variants": "Generate local part variants",
    "generate_material_variants": "Generate material / surface variants",
    "generate_breakthrough_reference_variants": "Generate cross-domain reference variants",
}

SIGNAL_EN = {
    "pause_hover": ("pause / hover", "temporal_behavior", ["hover_count", "dwell_ms"]),
    "long_compare": ("long comparison", "temporal_behavior", ["compare_dwell_ms", "dwell_ms"]),
    "rapid_tool_switch": ("rapid tool switching", "temporal_behavior", ["tool_switch_count"]),
    "repeated_micro_edit": ("repeated micro-adjustment", "temporal_behavior", ["same_event_type_recent_count", "brush_count", "drag_count"]),
    "undo_redo_loop": ("undo / redo loop", "temporal_behavior", ["recent_undo_count"]),
    "accept_reject": ("accept / reject candidate", "temporal_behavior", ["recent_accept_count", "recent_reject_count"]),
    "global_orbit": ("global orbit", "spatial_viewport", ["viewport_orbit_count"]),
    "multi_view_check": ("multi-view inspection", "spatial_viewport", ["viewport_orbit_count", "viewport_zoom_count"]),
    "zoom_out": ("zoom out for whole object", "spatial_viewport", ["viewport_zoom_count"]),
    "local_zoom": ("local zoom-in", "spatial_viewport", ["local_zoom_count", "viewport_zoom_count"]),
    "select_object": ("select whole object", "spatial_viewport", ["selection_type=object", "active_object_id"]),
    "select_part": ("select / focus part", "spatial_viewport", ["selection_type=part", "part_id", "hovered_part_id"]),
    "small_brush": ("small brush / mask region", "spatial_viewport", ["brush_count", "mask_coverage"]),
    "large_brush": ("large brush / broad mask", "spatial_viewport", ["brush_count", "mask_coverage"]),
    "form_change": ("form / silhouette change", "semantic_cognitive", ["intent_scope=contour", "drawing_content", "drag_count"]),
    "surface_change": ("surface / material change", "semantic_cognitive", ["intent_scope=material", "material_token_count"]),
    "concept_change": ("conceptual direction change", "semantic_cognitive", ["semantic_distance", "intent_text"]),
    "match_reference": ("matching a reference", "semantic_cognitive", ["reference_match_count", "ref_image_id", "ref_model_id"]),
    "preserve_structure": ("preserve existing structure", "semantic_cognitive", ["protected_region_count", "boundary_lock"]),
    "seek_alternative": ("seeking alternatives", "semantic_cognitive", ["new_case_attempt_rate", "recent_reject_count"]),
    "stuck_uncertain": ("hesitation / possible fixation", "semantic_cognitive", ["dwell_ms", "low_activity_ms", "new_case_attempt_rate"]),
}

GROUP_EN = {
    "行为与时间信号": "temporal_behavior",
    "空间与视口信号": "spatial_viewport",
    "语义与认知信号": "semantic_cognitive",
}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_rows = load_rows()
    grouped = group_by_case(raw_rows)
    cases = [build_case_ir(case_id, dedupe_case_rows(rows)) for case_id, rows in sorted(grouped.items())]
    taxonomy = build_taxonomy(raw_rows, cases)
    retrieval_rows = [build_retrieval_row(case) for case in cases]
    graph_edges = build_graph_edges(cases)
    frontend_mapping = build_frontend_mapping()
    report = build_report(raw_rows, grouped, cases, taxonomy)

    write_json(OUT_DIR / "design_state_ir_cases.json", cases)
    write_jsonl(OUT_DIR / "design_state_ir_retrieval.jsonl", retrieval_rows)
    write_jsonl(OUT_DIR / "design_state_ir_graph_edges.jsonl", graph_edges)
    write_json(OUT_DIR / "frontend_signal_mapping.json", frontend_mapping)
    write_json(OUT_DIR / "design_state_ir_taxonomy.json", taxonomy)
    write_json(OUT_DIR / "design_state_ir_quality_report.json", report)
    write_markdown_report(OUT_DIR / "README.md", report)

    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


def load_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(RAW_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            continue
        for index, item in enumerate(data):
            if not isinstance(item, dict):
                continue
            row = dict(item)
            row["_source_file"] = path.name
            row["_source_index"] = index
            rows.append(row)
    return rows


def group_by_case(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        case_id = clean_text(row.get("case_id")) or f"missing_case_{len(grouped):04d}"
        grouped[case_id].append(row)
    return grouped


def dedupe_case_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one annotation per annotator for a case.

    coder_2 / coder_2.1 and the split coder_3 files can both contain the same
    case. Counting those rows twice biases the IR toward repeated files instead
    of human agreement.
    """
    by_annotator: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_annotator[clean_text(row.get("annotator")) or clean_text(row.get("_source_file"))].append(row)
    return [pick_canonical_row(bucket) for _, bucket in sorted(by_annotator.items())]


def build_case_ir(case_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    canonical = pick_canonical_row(rows)
    cognitive_votes = vote_nested(rows, "Cognitive_Status")
    route_votes = vote_nested(rows, "Creativeflow_route")
    signal_votes = vote_signals(rows)
    signal_codes = [item["code"] for item in signal_votes]
    signal_groups = sorted({item["group"] for item in signal_votes if item.get("group")})
    state_code, state_label = top_vote(cognitive_votes)
    route_code, route_label = top_vote(route_votes)
    state_label_en = STATE_EN.get(state_code, state_label)
    route_label_en = ROUTE_EN.get(route_code, route_label)
    raw_signals = merge_list_text(rows, "raw_signals")
    context_features = infer_context_features(canonical, raw_signals)
    retrieval_text = build_case_retrieval_text(
        canonical=canonical,
        state_label=state_label_en,
        route_label=route_label_en,
        signal_votes=signal_votes,
        raw_signals=raw_signals,
        context_features=context_features,
    )
    return {
        "ir_id": f"dsir_{case_id}",
        "case_id": case_id,
        "video_id": clean_text(canonical.get("video_id")),
        "software": clean_text(canonical.get("software")),
        "source_url": clean_text(canonical.get("source_url")),
        "start_time": clean_text(canonical.get("start_time")),
        "end_time": clean_text(canonical.get("end_time")),
        "task_group": clean_text(canonical.get("task_group")),
        "episode_summary": clean_text(canonical.get("episode_summary")),
        "episode_summary_original": clean_text(canonical.get("episode_summary")),
        "raw_signals": raw_signals,
        "design_state": {
            "code": state_code,
            "label": state_label_en,
            "original_label": state_label,
            "votes": cognitive_votes,
            "agreement": agreement_ratio(cognitive_votes),
        },
        "intuitive_signals": signal_votes,
        "signal_codes": signal_codes,
        "signal_groups": signal_groups,
        "creativeflow_route": {
            "code": route_code,
            "label": route_label_en,
            "original_label": route_label,
            "votes": route_votes,
            "agreement": agreement_ratio(route_votes),
        },
        "retrieval_text": retrieval_text,
        "context_features": context_features,
        "planner_features": {
            "scope_hint": infer_scope(signal_codes),
            "intervention_policy": infer_intervention_policy(route_code),
            "recommended_axes": infer_axes(route_code, signal_codes),
            "evidence_strength": evidence_strength(rows, cognitive_votes, route_votes),
        },
        "annotation": {
            "annotators": sorted({clean_text(row.get("annotator")) for row in rows if row.get("annotator")}),
            "source_files": sorted({clean_text(row.get("_source_file")) for row in rows}),
            "source_row_count": len(rows),
            "human_verified_count": sum(1 for row in rows if row.get("human_verified") is True),
            "assignment_types": sorted({clean_text(row.get("assignment_type")) for row in rows if row.get("assignment_type")}),
        },
        "agreement": case_agreement(rows),
    }


def pick_canonical_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def score(row: dict[str, Any]) -> tuple[int, int, int]:
        return (
            int(bool(row.get("human_verified"))),
            len(clean_text(row.get("episode_summary"))),
            len(row.get("raw_signals") or []),
        )

    return sorted(rows, key=score, reverse=True)[0]


def vote_nested(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    counter: Counter[tuple[str, str]] = Counter()
    for row in rows:
        value = row.get(key)
        if isinstance(value, dict):
            code = clean_text(value.get("code"))
            label = clean_text(value.get("label"))
            if code or label:
                counter[(code, label)] += 1
    return [
        {"code": code, "label": STATE_EN.get(code, ROUTE_EN.get(code, label)), "original_label": label, "count": count}
        for (code, label), count in counter.most_common()
    ]


def vote_signals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[tuple[str, str, str]] = Counter()
    annotators_by_signal: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for row in rows:
        annotator = clean_text(row.get("annotator"))
        for signal in row.get("Intuitive_Signals") or []:
            if not isinstance(signal, dict):
                continue
            code = clean_text(signal.get("code"))
            label = clean_text(signal.get("label"))
            group = clean_text(signal.get("group"))
            if not code:
                continue
            key = (code, label, group)
            counter[key] += 1
            if annotator:
                annotators_by_signal[key].add(annotator)
    return [
        {
            "code": code,
            "label": SIGNAL_EN.get(code, (label, "", []))[0],
            "original_label": label,
            "group": SIGNAL_EN.get(code, ("", GROUP_EN.get(group, group), []))[1] or GROUP_EN.get(group, group),
            "frontend_features": SIGNAL_EN.get(code, ("", "", []))[2],
            "count": count,
            "annotator_count": len(annotators_by_signal[(code, label, group)]),
        }
        for (code, label, group), count in counter.most_common()
    ]


def top_vote(votes: list[dict[str, Any]]) -> tuple[str, str]:
    if not votes:
        return "unknown", "Unknown"
    first = votes[0]
    return clean_text(first.get("code")) or "unknown", clean_text(first.get("label")) or "Unknown"


def agreement_ratio(votes: list[dict[str, Any]]) -> float:
    total = sum(int(vote.get("count") or 0) for vote in votes)
    if total <= 0:
        return 0.0
    return round(float(votes[0].get("count") or 0) / total, 3)


def merge_list_text(rows: list[dict[str, Any]], key: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for value in row.get(key) or []:
            text = clean_text(value)
            if text and text not in seen:
                seen.add(text)
                values.append(text)
    return values


def build_case_retrieval_text(
    *,
    canonical: dict[str, Any],
    state_label: str,
    route_label: str,
    signal_votes: list[dict[str, Any]],
    raw_signals: list[str],
    context_features: dict[str, Any],
) -> str:
    signal_labels = [clean_text(item.get("label")) for item in signal_votes[:8] if item.get("label")]
    object_terms = ", ".join(context_features.get("object_terms") or [])
    operation_terms = ", ".join(context_features.get("operation_terms") or [])
    pieces = [
        f"Design state: {state_label}",
        f"Signals: {'; '.join(signal_labels)}",
        f"CreativeFlow route: {route_label}",
        f"3D context object terms: {object_terms}",
        f"Observed operation terms: {operation_terms}",
        f"Task group: {clean_text(canonical.get('task_group'))}",
    ]
    return "\n".join(piece for piece in pieces if piece.split(": ", 1)[-1])


def infer_scope(signal_codes: list[str]) -> str:
    local = {"select_part", "local_zoom", "small_brush", "large_brush", "repeated_micro_edit"}
    global_ = {"select_object", "global_orbit", "zoom_out", "multi_view_check"}
    if any(code in local for code in signal_codes) and not any(code in global_ for code in signal_codes):
        return "part_or_region"
    if any(code in global_ for code in signal_codes) and not any(code in local for code in signal_codes):
        return "whole_object"
    if any(code in local for code in signal_codes) and any(code in global_ for code in signal_codes):
        return "mixed_whole_and_part"
    return "unknown"


def infer_intervention_policy(route_code: str) -> str:
    mapping = {
        "no_intervention": "observe_only",
        "generate_contour_variants": "offer_structural_or_silhouette_directions",
        "generate_local_variants": "offer_local_part_or_boundary_variants",
        "generate_material_variants": "offer_material_surface_variants",
        "generate_breakthrough_reference_variants": "offer_cross_domain_breakthrough_directions",
    }
    return mapping.get(route_code, "ask_clarification")


def infer_context_features(canonical: dict[str, Any], raw_signals: list[str]) -> dict[str, Any]:
    text = " ".join(
        [
            clean_text(canonical.get("episode_summary")),
            clean_text(canonical.get("task_group")),
            " ".join(raw_signals),
        ]
    ).lower()
    object_terms = [
        term
        for term in [
            "character",
            "rock",
            "helmet",
            "robot",
            "product",
            "sword",
            "cup",
            "lamp",
            "chair",
            "bench",
            "snowman",
            "snow globe",
        ]
        if term in text
    ]
    operation_terms = [
        term
        for term in [
            "sphere",
            "cube",
            "cylinder",
            "primitive",
            "brush",
            "move",
            "drag",
            "gizmo",
            "scale",
            "rotate",
            "material",
            "texture",
            "reference",
        ]
        if term in text
    ]
    return {
        "software": clean_text(canonical.get("software")),
        "object_terms": object_terms,
        "operation_terms": operation_terms,
        "task_group": clean_text(canonical.get("task_group")),
    }


def infer_axes(route_code: str, signal_codes: list[str]) -> list[str]:
    axes: list[str] = []
    if route_code == "generate_contour_variants" or "form_change" in signal_codes:
        axes.extend(["Structural", "Aesthetic"])
    if route_code == "generate_local_variants" or "select_part" in signal_codes:
        axes.extend(["Structural", "Functional"])
    if route_code == "generate_material_variants" or "surface_change" in signal_codes:
        axes.extend(["Aesthetic", "Functional"])
    if route_code == "generate_breakthrough_reference_variants" or "concept_change" in signal_codes:
        axes.extend(["Cross-domain", "Aesthetic"])
    if not axes:
        axes.extend(["Structural", "Aesthetic"])
    return list(dict.fromkeys(axes))


def evidence_strength(
    rows: list[dict[str, Any]],
    cognitive_votes: list[dict[str, Any]],
    route_votes: list[dict[str, Any]],
) -> str:
    annotators = {row.get("annotator") for row in rows if row.get("annotator")}
    agreement = min(agreement_ratio(cognitive_votes), agreement_ratio(route_votes))
    if len(annotators) >= 3 and agreement >= 0.6:
        return "high"
    if len(annotators) >= 2 and agreement >= 0.45:
        return "medium"
    return "low"


def build_retrieval_row(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "ir_id": case["ir_id"],
        "case_id": case["case_id"],
        "text": case["retrieval_text"],
        "design_state": case["design_state"]["code"],
        "route": case["creativeflow_route"]["code"],
        "signals": case["signal_codes"],
        "scope_hint": case["planner_features"]["scope_hint"],
        "recommended_axes": case["planner_features"]["recommended_axes"],
        "evidence_strength": case["planner_features"]["evidence_strength"],
        "state_agreement": case["design_state"]["agreement"],
        "route_agreement": case["creativeflow_route"]["agreement"],
        "signal_agreement": case["agreement"]["signal_jaccard_avg"],
        "context_features": case["context_features"],
    }


def build_taxonomy(rows: list[dict[str, Any]], cases: list[dict[str, Any]]) -> dict[str, Any]:
    states = Counter(case["design_state"]["code"] for case in cases)
    routes = Counter(case["creativeflow_route"]["code"] for case in cases)
    signals = Counter()
    signal_labels: dict[str, dict[str, str]] = {}
    for case in cases:
        for signal in case["intuitive_signals"]:
            code = signal["code"]
            signals[code] += 1
            signal_labels[code] = {"label": signal["label"], "group": signal["group"]}
    return {
        "schema_version": "design_state_ir.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "raw_row_count": len(rows),
        "case_count": len(cases),
        "design_states": [{"code": code, "count": count} for code, count in states.most_common()],
        "creativeflow_routes": [{"code": code, "count": count} for code, count in routes.most_common()],
        "intuitive_signals": [
            {"code": code, "count": count, **signal_labels.get(code, {})}
            for code, count in signals.most_common()
        ],
        "frontend_signal_mapping": build_frontend_mapping(),
    }


def build_frontend_mapping() -> dict[str, Any]:
    return {
        "schema_version": "flowstudio_frontend_signal_mapping.v1",
        "signals": {
            code: {"label": label, "group": group, "frontend_features": frontend_features}
            for code, (label, group, frontend_features) in sorted(SIGNAL_EN.items())
        },
        "derived_scope_rules": {
            "contour": ["form_change", "select_object", "global_orbit", "multi_view_check", "zoom_out"],
            "part": ["select_part", "local_zoom", "small_brush", "repeated_micro_edit"],
            "material": ["surface_change", "match_reference"],
        },
        "intervention_timing_rules": {
            "observe_only": "Do not show an intent bubble.",
            "ask_scope": "Ask only whether the user is changing contour, part, or material.",
            "offer_divergence": "Show More Creative directions after typed intent or confirmed scope.",
        },
    }


def build_graph_edges(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for case in cases:
        cid = case["case_id"]
        state = case["design_state"]["code"]
        route = case["creativeflow_route"]["code"]
        edges.append(edge(cid, "HAS_STATE", state, case["design_state"]["agreement"]))
        edges.append(edge(cid, "SUGGESTS_ROUTE", route, case["creativeflow_route"]["agreement"]))
        edges.append(edge(route, "MAPS_TO_SCOPE", case["planner_features"]["scope_hint"], 1.0))
        for axis in case["planner_features"]["recommended_axes"]:
            edges.append(edge(route, "RECOMMENDS_AXIS", axis, 1.0))
        for signal in case["intuitive_signals"]:
            strength = round(float(signal.get("annotator_count") or signal.get("count") or 1) / max(1, len(case["annotation"]["annotators"])), 3)
            edges.append(edge(cid, "HAS_SIGNAL", signal["code"], strength))
            edges.append(edge(signal["code"], "SUPPORTS_ROUTE", route, strength))
            edges.append(edge(signal["code"], "IMPLIES_SCOPE", case["planner_features"]["scope_hint"], strength))
    return edges


def edge(source: str, relation: str, target: str, weight: float) -> dict[str, Any]:
    return {"source": source, "relation": relation, "target": target, "weight": round(weight, 3)}


def build_report(
    raw_rows: list[dict[str, Any]],
    grouped: dict[str, list[dict[str, Any]]],
    cases: list[dict[str, Any]],
    taxonomy: dict[str, Any],
) -> dict[str, Any]:
    duplicate_groups = {case_id: rows for case_id, rows in grouped.items() if len(rows) > 1}
    agreement = corpus_agreement(grouped)
    low_evidence = [
        case["case_id"]
        for case in cases
        if case["planner_features"]["evidence_strength"] == "low"
    ]
    return {
        "summary": {
            "raw_files": len(list(RAW_DIR.glob("*.json"))),
            "raw_rows": len(raw_rows),
            "unique_cases": len(cases),
            "duplicate_case_groups": len(duplicate_groups),
            "design_state_count": len(taxonomy["design_states"]),
            "route_count": len(taxonomy["creativeflow_routes"]),
            "signal_count": len(taxonomy["intuitive_signals"]),
            "low_evidence_cases": len(low_evidence),
            "state_pairwise_agreement": agreement["state_pairwise_agreement"],
            "route_pairwise_agreement": agreement["route_pairwise_agreement"],
            "signal_pairwise_jaccard": agreement["signal_pairwise_jaccard"],
        },
        "outputs": {
            "cases": str(OUT_DIR / "design_state_ir_cases.json"),
            "retrieval": str(OUT_DIR / "design_state_ir_retrieval.jsonl"),
            "taxonomy": str(OUT_DIR / "design_state_ir_taxonomy.json"),
            "graph_edges": str(OUT_DIR / "design_state_ir_graph_edges.jsonl"),
            "frontend_signal_mapping": str(OUT_DIR / "frontend_signal_mapping.json"),
        },
        "agreement": agreement,
        "notes": [
            "Raw coder files are preserved.",
            "Rows with the same case_id are aggregated into one IR case with vote counts.",
            "Planner features are deterministic hints derived from route and signal codes.",
            "The retrieval JSONL is the lightweight file the backend should load at runtime.",
        ],
        "low_evidence_cases": low_evidence[:80],
    }


def case_agreement(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pairs = list(combinations(rows, 2))
    if not pairs:
        return {"state_pairwise": 1.0, "route_pairwise": 1.0, "signal_jaccard_avg": 1.0}
    state = sum(
        (a.get("Cognitive_Status") or {}).get("code") == (b.get("Cognitive_Status") or {}).get("code")
        for a, b in pairs
    ) / len(pairs)
    route = sum(
        (a.get("Creativeflow_route") or {}).get("code") == (b.get("Creativeflow_route") or {}).get("code")
        for a, b in pairs
    ) / len(pairs)
    signal = sum(signal_jaccard(a, b) for a, b in pairs) / len(pairs)
    return {"state_pairwise": round(state, 3), "route_pairwise": round(route, 3), "signal_jaccard_avg": round(signal, 3)}


def corpus_agreement(grouped: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    state_values: list[float] = []
    route_values: list[float] = []
    signal_values: list[float] = []
    overlap_case_count = 0
    for rows in grouped.values():
        deduped = dedupe_case_rows(rows)
        if len(deduped) < 2:
            continue
        overlap_case_count += 1
        agreement = case_agreement(deduped)
        state_values.append(agreement["state_pairwise"])
        route_values.append(agreement["route_pairwise"])
        signal_values.append(agreement["signal_jaccard_avg"])
    return {
        "overlap_case_count": overlap_case_count,
        "state_pairwise_agreement": round(avg(state_values), 3),
        "route_pairwise_agreement": round(avg(route_values), 3),
        "signal_pairwise_jaccard": round(avg(signal_values), 3),
    }


def signal_jaccard(a: dict[str, Any], b: dict[str, Any]) -> float:
    a_codes = {clean_text(signal.get("code")) for signal in a.get("Intuitive_Signals") or [] if isinstance(signal, dict)}
    b_codes = {clean_text(signal.get("code")) for signal in b.get("Intuitive_Signals") or [] if isinstance(signal, dict)}
    union = a_codes | b_codes
    if not union:
        return 1.0
    return len(a_codes & b_codes) / len(union)


def avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    summary = report["summary"]
    lines = [
        "# Cleaned Design-State IR",
        "",
        f"- raw files: {summary['raw_files']}",
        f"- raw rows: {summary['raw_rows']}",
        f"- unique cases: {summary['unique_cases']}",
        f"- duplicate case groups merged: {summary['duplicate_case_groups']}",
        f"- design states: {summary['design_state_count']}",
        f"- CreativeFlow routes: {summary['route_count']}",
        f"- intuitive signals: {summary['signal_count']}",
        f"- low evidence cases: {summary['low_evidence_cases']}",
        f"- state pairwise agreement: {summary['state_pairwise_agreement']}",
        f"- route pairwise agreement: {summary['route_pairwise_agreement']}",
        f"- signal pairwise Jaccard: {summary['signal_pairwise_jaccard']}",
        "",
        "Outputs:",
        "",
        "- `design_state_ir_cases.json`: full aggregated case IR",
        "- `design_state_ir_retrieval.jsonl`: lightweight retrieval rows for backend runtime",
        "- `design_state_ir_taxonomy.json`: state/signal/route taxonomy",
        "- `design_state_ir_quality_report.json`: machine-readable cleaning report",
        "- `design_state_ir_graph_edges.jsonl`: lightweight graph-like edges for future GraphRAG-style reasoning",
        "- `frontend_signal_mapping.json`: mapping from frontend events/features to IR signal codes",
        "",
        "Raw coder files are preserved. The cleaned files are generated by `scripts/clean_design_state_ir.py`.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def clean_text(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


if __name__ == "__main__":
    main()
