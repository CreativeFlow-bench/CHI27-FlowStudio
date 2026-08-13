"""Contracts and scoring for the three CreativeFlow variation facets.

This module intentionally has no model/runtime dependencies.  The original
CreativeFlow transfer engine remains responsible for graph retrieval, base
ranking and semantic distance.  These functions add the facet-specific hard
gates and score required before a graph node may become a transfer direction.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Iterable


def _tokens(*values: Any) -> set[str]:
    text = " ".join(str(value or "") for value in values)
    return {item for item in re.findall(r"[a-z][a-z0-9-]*", text.lower()) if item}


def _normalise_label(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


ONTOLOGY_NOISE = {
    "addition",
    "document",
    "manifestation",
    "particular anatomical entity",
    "physical attributes facet",
    "probability distribution",
    "qualia",
    "quality",
    "quantity",
    "relation",
    "technical activity",
    "topological manifold",
    "two-dimensional space",
    "value",
}

HIERARCHY_MARKERS = {
    "facet",
    "hierarchy name",
    "perceived attribute",
    "substances",
}

GENERIC_OPEN_DIMENSIONS = {
    "attachment",
    "coating", "contour",
    "color",
    "finish",
    "mass distribution",
    "material",
    "proportion",
    "protrusion",
    "replaceable component",
    "shape",
    "silhouette",
    "surface",
    "surface finish",
    "surface texture",
    "texture",
    "weathering",
}

LOW_NON_3D_REPRESENTATIONS = {
    "contour", "drawing", "illustration", "line art", "outline", "photograph",
    "picture", "sketch", "two-dimensional art",
}

LOW_FIDELITY_TERMS = {
    "amorphous", "asymmetric", "asymmetrical", "biomorphic", "branching",
    "bulbous", "cellular", "compressed", "contour", "curvilinear",
    "elongated", "faceted", "folded", "fragmented", "framework", "geometric",
    "globular", "hourglass", "inflated", "lattice", "layered", "lobed",
    "mass", "membrane", "modular", "organic", "porous", "proportion",
    "ribbed", "sculpture", "segmented", "shell", "silhouette", "skeletal", "spiral",
    "stacked", "tapered", "tectonic", "topology", "twisted", "weightless",
}

PART_TERMS = {
    "antenna", "appendage", "attachment", "beak", "bill", "blade", "branch",
    "button", "cap", "claw", "connector", "ear", "eye", "fin", "fixture",
    "handle", "horn", "joint", "knob", "limb", "nozzle", "nose", "organ",
    "ornament", "peg", "plug", "probe", "proboscis", "receptor", "sensor",
    "snout", "socket", "spout", "stem", "tail", "tube", "tusk", "valve", "wing",
}

TEXTURE_TERMS = {
    "anodized", "brass", "bronze", "brushed", "ceramic", "chrome",
    "clay", "coarse", "coating", "copper", "cracked", "crystalline",
    "diamond", "fabric", "felt", "frosted", "glass", "glaze", "glazed", "glossy", "gossamer", "granular", "ice",
    "iridescent", "lacquer", "leather", "marble", "matte", "metal",
    "metallic", "oxidized", "painted", "patina", "pearlescent", "porcelain",
    "rough", "rubber", "rusted", "satin", "silk", "snow", "stone",
    "textile", "translucent", "velvet", "weathered", "wood", "wooden",
}


@dataclass(frozen=True)
class VariationContract:
    stage: str
    open_facets: tuple[str, ...]
    locked_facets: tuple[str, ...]
    graph_seed_dimensions: tuple[str, ...]
    relevance_terms: frozenset[str]


CONTRACTS: dict[str, VariationContract] = {
    "low_fidelity": VariationContract(
        stage="low_fidelity",
        open_facets=("outer_contour", "proportion", "mass_distribution", "tactile_form"),
        locked_facets=("object_identity", "part_inventory", "accessories", "material", "color", "pose"),
        graph_seed_dimensions=("silhouette", "proportion", "mass distribution", "tactile form"),
        relevance_terms=frozenset(LOW_FIDELITY_TERMS),
    ),
    "part": VariationContract(
        stage="part",
        open_facets=("selected_part_identity", "selected_part_shape", "selected_part_role"),
        locked_facets=("global_silhouette", "unselected_parts", "pose", "composition"),
        graph_seed_dimensions=("replaceable component", "attachment", "socket", "protrusion"),
        relevance_terms=frozenset(PART_TERMS),
    ),
    "texture": VariationContract(
        stage="texture",
        open_facets=("material", "color", "surface_microstructure", "finish", "weathering", "coating"),
        locked_facets=("object_identity", "geometry", "outer_contour", "proportion", "part_layout", "pose"),
        graph_seed_dimensions=("material", "surface finish", "coating", "weathering"),
        relevance_terms=frozenset(TEXTURE_TERMS),
    ),
}


def contract_for(stage: str) -> VariationContract:
    key = str(stage).strip().lower().replace("-", "_")
    if key not in CONTRACTS:
        raise ValueError(f"unsupported CreativeFlow variation: {stage}")
    return CONTRACTS[key]


def dynamic_relevance_terms(
    stage: str,
    source_elements: dict[str, Any] | None,
    part_semantics: dict[str, Any] | None,
    extra_terms: Iterable[str] = (),
) -> set[str]:
    contract = contract_for(stage)
    terms = set(contract.relevance_terms)
    source_elements = source_elements or {}
    part_semantics = part_semantics or {}

    if stage == "low_fidelity":
        fields: Iterable[Any] = (
            source_elements.get("global_form"),
            source_elements.get("silhouette"),
            source_elements.get("mass_distribution"),
            source_elements.get("tactile_form"),
        )
    elif stage == "part":
        fields = (
            part_semantics.get("canonical_name"),
        )
    else:
        fields = (
            source_elements.get("materials"),
            source_elements.get("colors"),
            source_elements.get("surface_features"),
            source_elements.get("finish"),
        )
    stop = {
        "about", "after", "again", "against", "along", "also", "among", "and",
        "body", "complete", "current", "every", "for", "from", "into", "material",
        "object", "only", "other", "part", "preserve", "source", "than", "that",
        "the", "their", "these", "this", "three", "with",
    }
    for value in fields:
        terms.update(token for token in _tokens(value) if len(token) >= 4 and token not in stop)
    # Runtime descriptors are produced by the original CreativeFlow planner for
    # this source.  They expand the admissible vocabulary without turning an
    # example-specific word list into fixed variation prompts.
    for value in extra_terms:
        terms.update(token for token in _tokens(value) if len(token) >= 4 and token not in stop)
    return terms


def candidate_blob(candidate: dict[str, Any]) -> str:
    summary = candidate.get("summary") or {}
    pieces: list[Any] = [candidate.get("label"), summary.get("description")]
    for key in ("aliases", "aat_labels", "aat_broader_labels", "neighbor_labels"):
        value = summary.get(key)
        if isinstance(value, list):
            pieces.extend(value)
    return " ".join(str(piece) for piece in pieces if piece)


def _has_real_graph_provenance(candidate: dict[str, Any]) -> bool:
    provenance = [str(item).lower() for item in candidate.get("provenance", [])]
    return any(
        item.startswith(("concept:", "neighbor:", "aat_", "aat_search:", "second_hop:", "second_hop_", "asknature:"))
        for item in provenance
    )


def _specificity(label: str) -> float:
    words = _tokens(label)
    if label in GENERIC_OPEN_DIMENSIONS:
        return 0.0
    if len(words) >= 2:
        return 1.0
    return 0.65 if len(words) == 1 else 0.0


def score_graph_candidate(
    *,
    stage: str,
    candidate: dict[str, Any],
    graph_origin: str,
    seed_terms: Iterable[str],
    source_elements: dict[str, Any] | None = None,
    part_semantics: dict[str, Any] | None = None,
    extra_relevance_terms: Iterable[str] = (),
) -> dict[str, Any]:
    """Combine original KG score with variation-specific gates and score."""

    label = _normalise_label(candidate.get("label"))
    blob = candidate_blob(candidate).lower()
    blob_tokens = _tokens(blob)
    reasons: list[str] = []
    hard_reject = False

    if not label:
        reasons.append("empty_label")
        hard_reject = True
    if len(_tokens(label)) > 4:
        reasons.append("noisy_long_entity_title")
        hard_reject = True
    if label in ONTOLOGY_NOISE or any(marker in label for marker in HIERARCHY_MARKERS):
        reasons.append("ontology_noise")
        hard_reject = True
    if label == _normalise_label(graph_origin):
        reasons.append("same_as_graph_origin")
        hard_reject = True
    if label in {_normalise_label(item) for item in seed_terms}:
        reasons.append("open_dimension_not_transfer_anchor")
        hard_reject = True
    if label in GENERIC_OPEN_DIMENSIONS:
        reasons.append("generic_open_dimension")
        hard_reject = True
    if stage == "low_fidelity" and label in LOW_NON_3D_REPRESENTATIONS:
        reasons.append("non_3d_representation")
        hard_reject = True
    if not _has_real_graph_provenance(candidate):
        reasons.append("missing_real_graph_provenance")
        hard_reject = True

    relevance_terms = dynamic_relevance_terms(
        stage, source_elements, part_semantics, extra_relevance_terms
    )
    relevance_hits = sorted(blob_tokens & relevance_terms)
    if not relevance_hits:
        reasons.append("facet_irrelevant")
        hard_reject = True

    bucket = str(candidate.get("semantic_distance_bucket") or "unknown").lower()
    if bucket not in {"near", "far"}:
        reasons.append("distance_not_near_or_far")

    original_score = max(0.0, float(candidate.get("score") or 0.0))
    original_component = min(1.0, math.log1p(original_score) / math.log(11.0))
    relevance_component = min(1.0, len(relevance_hits) / 3.0)
    provenance_component = 1.0 if _has_real_graph_provenance(candidate) else 0.0
    distance_component = 1.0 if bucket in {"near", "far"} else 0.0
    specificity_component = _specificity(label)
    selection_priority = specificity_component
    if stage == "texture":
        label_tokens = _tokens(label)
        high_visibility_substrates = {
            "bronze", "ceramic", "fabric", "felt", "leather", "marble",
            "metal", "stone", "textile", "velvet", "wood",
        }
        generic_biological = label in {"anatomical structure", "biological structure"}
        if generic_biological:
            selection_priority = 0.1
        elif label_tokens & high_visibility_substrates:
            selection_priority = 0.9
        elif len(label_tokens) >= 2 and (
            "structure" in label_tokens or bool(label_tokens & TEXTURE_TERMS)
        ):
            selection_priority = 1.0
        elif label_tokens & TEXTURE_TERMS:
            selection_priority = 0.65
        else:
            selection_priority = 0.2
    total = (
        0.34 * original_component
        + 0.28 * relevance_component
        + 0.16 * provenance_component
        + 0.12 * distance_component
        + 0.10 * specificity_component
    )
    passed = not hard_reject and bucket in {"near", "far"} and total >= 0.45
    if not passed and not reasons:
        reasons.append("below_variation_score_threshold")
    return {
        "label": label,
        "passed": passed,
        "hard_reject": hard_reject,
        "reasons": reasons,
        "distance_bucket": bucket,
        "variation_score": round(total, 4),
        "selection_priority": round(selection_priority, 4),
        "score_breakdown": {
            "original_kg_score": round(original_score, 4),
            "original_component": round(original_component, 4),
            "facet_relevance": round(relevance_component, 4),
            "real_graph_provenance": round(provenance_component, 4),
            "known_distance": round(distance_component, 4),
            "specificity": round(specificity_component, 4),
            "relevance_hits": relevance_hits,
        },
    }


def select_balanced_candidates(
    scored_candidates: list[dict[str, Any]],
    *,
    near_count: int = 2,
    far_count: int = 2,
) -> list[dict[str, Any]]:
    """Select exact near/far quotas while discouraging lexical duplicates."""

    selected: list[dict[str, Any]] = []
    selected_tokens: list[set[str]] = []
    for bucket, quota in (("near", near_count), ("far", far_count)):
        pool = [
            item for item in scored_candidates
            if item.get("variation_scoring", {}).get("passed")
            and item.get("variation_scoring", {}).get("distance_bucket") == bucket
        ]
        pool.sort(
            key=lambda item: (
                -float(item.get("variation_scoring", {}).get("selection_priority", 0.0)),
                -float(item.get("variation_scoring", {}).get("variation_score", 0.0)),
                -float(item.get("score", 0.0)),
                str(item.get("label", "")).lower(),
            )
        )
        bucket_selected = 0
        for item in pool:
            tokens = _tokens(item.get("label"))
            # A far transfer must not merely rename a near anchor with one
            # shared content word (for example "ice crystal" -> "ice flower").
            # This operates on runtime KG labels, not a fixed output lexicon.
            if bucket == "far" and any(tokens & prior for prior in selected_tokens):
                continue
            duplicate = any(tokens and prior and len(tokens & prior) / len(tokens | prior) >= 0.8 for prior in selected_tokens)
            if duplicate:
                continue
            selected.append(item)
            selected_tokens.append(tokens)
            bucket_selected += 1
            if bucket_selected >= quota:
                break
    if sum(1 for item in selected if item["variation_scoring"]["distance_bucket"] == "near") < near_count:
        return []
    if sum(1 for item in selected if item["variation_scoring"]["distance_bucket"] == "far") < far_count:
        return []
    return selected


def validate_part_semantics(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    # SAM3D is responsible for locating the part and the VLM only names it.
    # Shape/material/role are mutable and must not constrain graph expansion.
    required = ("part_id", "canonical_name")
    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise ValueError(f"Part variation requires SAM3D semantic fields: {', '.join(missing)}")
    if not payload.get("face_labels_path") and not payload.get("sam3d_manifest_path"):
        raise ValueError("Part variation requires SAM3D face-label or manifest evidence")
    confidence = float(payload.get("confidence") or 0.0)
    if confidence < 0.45:
        raise ValueError(f"SAM3D part semantic confidence is too low: {confidence:.3f}")
    return payload
