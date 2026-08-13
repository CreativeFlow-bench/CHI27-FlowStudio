#!/usr/bin/env python3
"""Attribute-first CreativeFlow KG expansion for three variation facets.

Paper-aligned order:
source + variation facet -> executable seed attributes -> graph-specific query
expansion -> Wikidata / Getty AAT / AskNatureNet retrieval -> 3D feasibility,
structural-transferability and Gaussian novelty scoring -> structure mapping.

No image prompt is produced until the selected raw KG nodes have passed every
preceding stage.  The raw graph label is preserved verbatim for Stage 2.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error
from urllib.parse import quote_plus, urlparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

import requests


PLANNER_API_BASE = os.getenv(
    "CF_PLANNER_API_BASE", "http://127.0.0.1:18085/v1"
).rstrip("/")
LOCAL_PIPELINE = Path(__file__).resolve().parents[1] / "handoff" / "creativeflow_pipeline"
PIPELINE_ROOT = Path(
    os.getenv(
        "CF_TRANSFER_PIPELINE_ROOT",
        str(LOCAL_PIPELINE if LOCAL_PIPELINE.is_dir() else "/root/creativeflow_pipeline"),
    )
)
sys.path.insert(0, str(PIPELINE_ROOT))

from pipeline_transfer_engine import SourceSpec  # noqa: E402

try:  # noqa: E402
    from pipeline_transfer_engine import call_planning_json  # type: ignore
except Exception:  # pragma: no cover - remote compatibility fallback
    call_planning_json = None  # type: ignore[assignment]

try:  # noqa: E402
    from pipeline_transfer_engine import retrieve_asknature_structure_terms  # type: ignore
except Exception:  # pragma: no cover - remote compatibility fallback
    retrieve_asknature_structure_terms = None  # type: ignore[assignment]
from scripts.kb_semantic_distance import (  # noqa: E402
    build_concept,
    getty_aat_search,
)


PLANNER_SYSTEM = """
You are the multimodal planner of CreativeFlow. Analyze the visible source and
the requested variation facet. Extract morphologically actionable seed
attributes grounded in source evidence. Do not propose target designs, graph
nodes, styles, or replacement objects. Return strict JSON only.
""".strip()

QUERY_SYSTEM = """
You are the query-expansion stage of CreativeFlow's structured KG path. Convert
already-grounded seed attributes into short graph-specific search terms for
Wikidata, Getty AAT, and AskNatureNet. Every term must explore the SAME source
attribute; it must not introduce a different variation facet or directly
declare a final design. Return strict JSON only.
""".strip()

SCORING_SYSTEM = """
You are CreativeFlow's paper-aligned candidate scorer. Score only visible and
physically transferable evidence. Reject broad ontology classes, unrelated
nodes, metaphor-only associations, software/media titles, and candidates that
change a locked variation facet. Return strict JSON only.
""".strip()

MAPPING_SYSTEM = """
You perform Structure Mapping Theory after KG retrieval and scoring. Map the
selected donor's relational property to the source attribute while preserving
the source identity and every locked facet. Do not rename, normalize, or
rewrite the raw KG node. Return strict JSON only.
""".strip()


FACETS: dict[str, dict[str, Any]] = {
    "low_fidelity": {
        "mutable_dimensions": [
            "global_shape", "silhouette", "segment_structure", "proportion",
            "mass_distribution", "global_topology",
        ],
        "locked": ["object_identity", "part_inventory", "material", "color"],
        "target_kind": "a concrete artifact or natural form whose global 3D organization is transferable",
        "graph_focus": {
            "wikidata": "ontological entities exhibiting the same global form attribute",
            "getty_aat": "formal morphology, workmanship, or constructed-form terminology for that attribute",
            "asknature": "organism-scale or natural structural strategies exhibiting that attribute",
        },
    },
    "part": {
        "mutable_dimensions": [
            "selected_part_shape", "selected_part_function", "attachment_logic",
            "orientation", "articulation", "interface",
        ],
        "locked": ["object_identity", "global_shape", "unselected_parts", "material_layout"],
        "target_kind": "a concrete physical component or biological structure that can donate a local part principle",
        "graph_focus": {
            "wikidata": "ontological component entities sharing the selected part attribute",
            "getty_aat": "artifact components, fittings, workmanship, or local-form terminology sharing that attribute",
            "asknature": "biological organs or mechanisms sharing that local function, attachment, or geometry",
        },
    },
    "texture": {
        "mutable_dimensions": [
            "material_family", "surface_microstructure", "roughness", "finish",
            "optical_response", "color_behavior", "weathering",
        ],
        "locked": ["object_identity", "global_shape", "part_inventory", "part_layout"],
        "target_kind": "a concrete material, finish, coating, or physical surface phenomenon",
        "graph_focus": {
            "wikidata": "ontological material or physical surface entities sharing the source material attribute",
            "getty_aat": "material, finish, coating, craft, and workmanship concepts sharing that attribute",
            "asknature": "biological material strategies, microstructures, and optical surface phenomena sharing that attribute",
        },
    },
}

GRAPH_NAMES = ("wikidata", "getty_aat", "asknature")


def _kg_proxy() -> str:
    """Return the live KG proxy, if configured.

    The AutoDL built-in /init/proxy is not an internet HTTP proxy.  Do not
    silently default to a dead 33210 endpoint; graph retrieval should either
    use the explicitly configured jump host proxy or fail visibly.
    """

    return (
        os.getenv("CF_KG_PROXY", "").strip()
        or os.getenv("CF_KB_CURL_PROXY", "").strip()
        or os.getenv("https_proxy", "").strip()
        or os.getenv("http_proxy", "").strip()
    )


def _requests_proxy_env() -> dict[str, str] | None:
    proxy = _kg_proxy()
    if not proxy:
        return None
    return {"http": proxy, "https": proxy}


def _kg_http_text(url: str, *, timeout: int = 30) -> str:
    proxy = _kg_proxy()
    if proxy and proxy.startswith(("socks5h://", "socks5://")):
        cmd = [
            "curl",
            "-fsSL",
            "--max-time",
            str(int(timeout)),
            "-H",
            "User-Agent: CreativeFlow/2.0",
        ]
        if proxy.startswith("socks5h://"):
            cmd.extend(["--socks5-hostname", proxy.removeprefix("socks5h://")])
        else:
            cmd.extend(["--socks5", proxy.removeprefix("socks5://")])
        cmd.append(url)
        completed = subprocess.run(cmd, text=True, capture_output=True)
        if completed.stdout:
            return completed.stdout
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or f"curl exited {completed.returncode}")[:500])
        return completed.stdout
    response = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": "CreativeFlow/2.0"},
        proxies=_requests_proxy_env(),
    )
    response.raise_for_status()
    return response.text
GENERIC_NODES = {
    "attribute", "entity", "facet", "form", "material", "object", "organ",
    "part", "physical entity", "quality", "relation", "shape", "structure",
    "surface", "texture", "thing", "visual work",
}


def _tokens(value: Any) -> set[str]:
    return set(re.findall(r"[a-z][a-z0-9-]*", str(value or "").lower()))


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _read_json(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _image_data_url(path: str) -> str:
    suffix = Path(path).suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/webp" if suffix == ".webp" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(Path(path).read_bytes()).decode("ascii")


def call_runtime_json(
    system_prompt: str,
    user_prompt: str,
    *,
    image_paths: list[str] | None = None,
    max_tokens: int = 4096,
) -> dict[str, Any] | None:
    api_base = os.getenv("CF_TEXT_LLM_API_BASE", PLANNER_API_BASE).rstrip("/")
    model = os.getenv("CF_TEXT_LLM_MODEL", "qwen3-planner")
    user_content: str | list[dict[str, Any]] = user_prompt
    if image_paths:
        user_content = [{"type": "text", "text": user_prompt}]
        for path in image_paths:
            if path and Path(path).is_file():
                user_content.append({"type": "image_url", "image_url": {"url": _image_data_url(path)}})
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.15,
        "max_tokens": max_tokens,
    }
    request = urllib.request.Request(
        api_base + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
            request, timeout=180
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
        text = str(payload["choices"][0]["message"]["content"]).strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S)
        # Locate the first complete JSON object, skipping any prose prefix or
        # trailing commentary. Some endpoints wrap the object in extra text.
        for start in range(len(text)):
            if text[start] != "{":
                continue
            try:
                decoded, end = json.JSONDecoder().raw_decode(text[start:])
            except ValueError:
                continue
            if isinstance(decoded, dict):
                return decoded
            break
        raise ValueError("runtime response contains no complete JSON object")
    except urllib.error.HTTPError as exc:
        if os.getenv("CF_DEBUG_ATTRIBUTE_KG", "").lower() in {"1", "true", "yes"}:
            detail = exc.read().decode("utf-8", errors="replace")
            print(
                f"[attribute_kg] runtime_json_http_error: {exc.code} {detail}",
                file=sys.stderr,
                flush=True,
            )
        return None
    except Exception as exc:
        if os.getenv("CF_DEBUG_ATTRIBUTE_KG", "").lower() in {"1", "true", "yes"}:
            print(f"[attribute_kg] runtime_json_error: {exc}", file=sys.stderr, flush=True)
        return None


def planner_seed_attributes(
    *,
    stage: str,
    source: SourceSpec,
    object_type: str,
    source_elements: dict[str, Any],
    part_semantics: dict[str, Any],
    user_prompt: str,
) -> dict[str, Any]:
    facet = FACETS[stage]
    selected_part = _clean_text(part_semantics.get("canonical_name")) if stage == "part" else ""
    prompt = f"""
source_noun: {object_type}
variation_facet: {stage}
allowed_attribute_dimensions: {json.dumps(facet['mutable_dimensions'])}
locked_facets: {json.dumps(facet['locked'])}
selected_part_noun: {selected_part or 'not applicable'}
available_source_analysis: {json.dumps(source_elements, ensure_ascii=False)}
selected_part_analysis: {json.dumps(part_semantics, ensure_ascii=False)}
user_intent: {user_prompt or 'open-ended variation'}

Inspect the source image and extract 4 to 6 executable seed attributes for
this variation facet. An executable attribute is a visible source property
that can be used unchanged as a query axis across several knowledge graphs.
For Low Fidelity, describe only global form. For Part, describe only the named
selected part. For Texture, describe only the source object's editable body
material and surface appearance, not accessories.

Return exactly:
{{
  "source_anchor": "concrete source concept used for semantic distance",
  "source_noun": "{object_type}",
  "attributes": [
    {{
      "attribute_id": "attr_01",
      "dimension": "one allowed_attribute_dimensions value",
      "value": "short visible attribute phrase",
      "evidence": "specific visible source evidence",
      "transfer_question": "which concrete cross-domain entities exhibit this same relational property?",
      "confidence": 0.0
    }}
  ]
}}
Do not output targets or stylistic ideas. source_anchor must be the object noun
for Low Fidelity, the selected part noun for Part, and the observed editable
body material for Texture.
""".strip()
    if stage == "low_fidelity":
        prompt = f"""
source_noun: {object_type}
variation_facet: low_fidelity
allowed_attribute_dimensions: {json.dumps(facet['mutable_dimensions'])}
available_source_analysis: {json.dumps(source_elements, ensure_ascii=False)}
designer_intent: {user_prompt or 'explore alternative global contours'}

Inspect the attached ORIGINAL SOURCE IMAGE. Do not use, infer, request, or
create a silhouette image. First inventory the visible identity-bearing
content that every generated result must retain: parts, accessories, their
layout, colors, and materials. Then describe the current overall contour using
language only: segment count and rhythm, outer contour, proportions, mass
distribution, posture envelope, and global topology. Finally extract 3 to 5
executable seed attributes for changing ONLY the global contour/shape. Do not
propose target designs or alter the preserved content.

Return exactly:
{{
  "source_anchor":"{object_type}",
  "source_noun":"{object_type}",
  "preserve_elements":["specific visible element with color/material/layout"],
  "current_contour":{{
    "summary":"language-only contour description",
    "segment_structure":"visible organization",
    "proportion":"visible proportions",
    "mass_distribution":"visible mass distribution",
    "posture_envelope":"visible posture"
  }},
  "designer_intent":"concise contour-only intent",
  "attributes":[{{
    "attribute_id":"attr_01",
    "dimension":"one allowed_attribute_dimensions value",
    "value":"short visible contour attribute",
    "evidence":"specific evidence in the original image",
    "transfer_question":"which concrete forms exhibit this same shape property?",
    "confidence":0.0
  }}]
}}
""".strip()
    payload: dict[str, Any] | None = None
    validation_error = "attribute planner returned no structured result"
    base_prompt = prompt
    for attempt in range(6):
        current_prompt = base_prompt
        if attempt > 0:
            current_prompt = base_prompt + (
                f"\n\nYour previous response failed validation: {validation_error}. "
                "Return strict JSON with at least 3 attributes whose dimension is one of "
                f"{json.dumps(facet['mutable_dimensions'])}"
                + (
                    ", plus preserve_elements with at least 4 concrete visible items and a "
                    "current_contour object with a non-empty summary string."
                    if stage == "low_fidelity"
                    else "."
                )
            )
        if stage == "low_fidelity":
            payload = call_runtime_json(
                PLANNER_SYSTEM,
                current_prompt,
                image_paths=list(source.image_paths),
                max_tokens=2048,
            )
        else:
            try:
                payload = (
                    call_planning_json(PLANNER_SYSTEM, current_prompt, source)
                    if callable(call_planning_json)
                    else None
                )
            except Exception as exc:
                validation_error = f"planning provider error: {exc}"
                payload = None
            if not isinstance(payload, dict):
                payload = call_runtime_json(
                    PLANNER_SYSTEM,
                    current_prompt,
                    image_paths=list(source.image_paths),
                    max_tokens=2048,
                )
        if not isinstance(payload, dict):
            validation_error = "attribute planner returned no structured result"
            continue
        try:
            return _build_planner_plan(
                payload,
                stage=stage,
                object_type=object_type,
                selected_part=selected_part,
                facet=facet,
            )
        except RuntimeError as exc:
            validation_error = str(exc)
            continue
    raise RuntimeError(validation_error)


def _build_planner_plan(
    payload: dict[str, Any],
    *,
    stage: str,
    object_type: str,
    selected_part: str,
    facet: dict[str, Any],
) -> dict[str, Any]:
    allowed = set(facet["mutable_dimensions"])
    attributes: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(payload.get("attributes") or [], start=1):
        if not isinstance(item, dict):
            continue
        dimension = _clean_text(item.get("dimension")).lower().replace(" ", "_")
        value = _clean_text(item.get("value"))
        evidence = _clean_text(item.get("evidence"))
        key = (dimension, value.lower())
        if dimension not in allowed or not value or not evidence or key in seen:
            continue
        seen.add(key)
        attributes.append(
            {
                "attribute_id": f"attr_{len(attributes) + 1:02d}",
                "dimension": dimension,
                "value": value,
                "evidence": evidence,
                "transfer_question": _clean_text(item.get("transfer_question")),
                "confidence": max(0.0, min(1.0, float(item.get("confidence") or 0.5))),
            }
        )
    if len(attributes) < 3:
        raise RuntimeError(f"attribute planner produced only {len(attributes)} valid attributes")
    source_anchor = _clean_text(payload.get("source_anchor"))
    if stage == "part":
        source_anchor = selected_part
    elif stage == "low_fidelity":
        source_anchor = object_type
    if not source_anchor:
        raise RuntimeError("attribute planner did not produce a concrete source_anchor")
    result = {
        "schema_version": "creativeflow.attribute-plan.v1",
        "planner_order": "source_plus_variation_facet_before_any_kg_query",
        "source_anchor": source_anchor,
        "source_noun": object_type,
        "selected_part_noun": selected_part or None,
        "attributes": attributes[:6],
        "locked_facets": facet["locked"],
    }
    if stage == "low_fidelity":
        preserve_elements = [
            _clean_text(item) for item in payload.get("preserve_elements") or [] if _clean_text(item)
        ]
        if len(preserve_elements) < 4:
            raise RuntimeError("Low Fidelity planner did not extract enough preserved source elements")
        current_contour = payload.get("current_contour")
        if not isinstance(current_contour, dict) or not _clean_text(current_contour.get("summary")):
            raise RuntimeError("Low Fidelity planner did not describe the current contour")
        result.update(
            {
                "planner_mode": "source_image_language_contour_no_silhouette",
                "preserve_elements": preserve_elements,
                "current_contour": current_contour,
                "designer_intent": _clean_text(payload.get("designer_intent")),
            }
        )
    return result


def expand_attribute_queries(
    *, stage: str, attribute_plan: dict[str, Any]
) -> list[dict[str, Any]]:
    facet = FACETS[stage]
    prompt = f"""
variation_facet: {stage}
source_anchor: {attribute_plan['source_anchor']}
seed_attributes: {json.dumps(attribute_plan['attributes'], ensure_ascii=False)}
locked_facets: {json.dumps(facet['locked'])}
graph_roles: {json.dumps(facet['graph_focus'], ensure_ascii=False)}
eligible_target_kind: {facet['target_kind']}

Create graph-specific expansion query terms. Each query must cite exactly one
attribute_id and search for concrete entities that exhibit that SAME
attribute. Do not jump to a different dimension. Wikidata terms should name
ontological physical entities; Getty AAT terms should address aesthetic/form,
material, craft, or workmanship vocabularies appropriate to the attribute;
AskNatureNet terms should address biological strategies appropriate to the
attribute. Produce both near and cross-domain far probes. Terms must be short
English noun phrases suitable for the graph search endpoint, not sentences.

Every Wikidata term must be the canonical name of a real, concrete physical
entity or natural/artifact category that the Wikidata entity search can
resolve. Never create adjective + source-noun compounds such as "compact
snowman", "stable snowman", or "symmetrical sculpture". Getty terms must be
plausible AAT preferred noun terms, not descriptions. AskNature terms must be
biological organisms, mechanisms, functions, or strategy-search phrases that
AskNature actually indexes. Near probes may remain in the source's physical
domain; far probes must omit the source noun and search another physical
domain that still exhibits the same attribute.

Return exactly:
{{
  "queries": [
    {{
      "attribute_id": "attr_01",
      "attribute_value": "verbatim seed attribute value",
      "graph": "wikidata | getty_aat | asknature",
      "term": "one concrete search term",
      "distance_intent": "near | far",
      "same_attribute_rationale": "how this query preserves the seed attribute"
    }}
  ]
}}
Across the complete response include every graph, every seed attribute, and at
least four near plus four far queries. Return 18 to 24 query items total. Do
not output a final target.
""".strip()
    attributes = {item["attribute_id"]: item for item in attribute_plan["attributes"]}
    last_error = ""

    def attempt(feedback: str | None) -> tuple[list[dict[str, Any]], str]:
        nonlocal last_error
        prompt_text = prompt
        if feedback:
            prompt_text = (
                prompt
                + "\n\nYour previous response was rejected: "
                + feedback
                + " Fix the JSON schema, include every graph and every seed "
                "attribute, and return at least four near plus four far queries."
            )
        payload = call_runtime_json(QUERY_SYSTEM, prompt_text)
        if os.getenv("CF_DEBUG_ATTRIBUTE_KG", "").lower() in {"1", "true", "yes"}:
            print(
                "[attribute_kg] raw_query_payload="
                + json.dumps(payload, ensure_ascii=False),
                file=sys.stderr,
                flush=True,
            )
        if not isinstance(payload, dict):
            last_error = "response was not a JSON object"
            return [], last_error
        queries = _query_items_from_payload(payload, attributes, require_full_coverage=True)
        if queries:
            return queries, ""
        last_error = "query items did not satisfy the schema or coverage requirements"
        return [], last_error

    for _ in range(3):
        queries, error = attempt(last_error)
        if queries:
            return queries
    # Tolerant final pass: accept a valid-format set even if per-bucket quota
    # is short, so one weak attribute cannot discard a full run.
    for _ in range(2):
        payload = call_runtime_json(
            QUERY_SYSTEM,
            prompt
            + "\n\nReturn a compact query set: every graph, at least one near and "
            "one far query, exact JSON schema.",
        )
        if isinstance(payload, dict):
            tolerated = _query_items_from_payload(payload, attributes, require_full_coverage=False)
            if tolerated:
                return tolerated
    raise RuntimeError(last_error or "attribute query expansion returned no structured result")


def _query_items_from_payload(
    payload: dict[str, Any],
    attributes: dict[str, dict[str, Any]],
    *,
    require_full_coverage: bool,
) -> list[dict[str, Any]]:
    if not isinstance(payload.get("queries"), list):
        return []
    queries: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    graph_counts: Counter[str] = Counter()
    bucket_counts: Counter[str] = Counter()
    attribute_counts: Counter[str] = Counter()
    for item in payload["queries"]:
        if not isinstance(item, dict):
            continue
        attr_id = _clean_text(item.get("attribute_id"))
        graph = _clean_text(item.get("graph")).lower().replace("-", "_")
        graph = "getty_aat" if graph in {"getty", "aat", "gettyaat"} else graph
        graph = "asknature" if graph in {"asknaturenet", "ask_nature"} else graph
        term = _clean_text(item.get("term"))
        bucket = _clean_text(item.get("distance_intent")).lower()
        if (
            attr_id not in attributes
            or graph not in GRAPH_NAMES
            or bucket not in {"near", "far"}
            or not term
            or len(term.split()) > 6
        ):
            continue
        key = (attr_id, graph, term.lower())
        if key in seen:
            continue
        seen.add(key)
        attribute = attributes[attr_id]
        queries.append(
            {
                "query_id": f"query_{len(queries) + 1:03d}",
                "attribute_id": attr_id,
                "attribute_dimension": attribute["dimension"],
                "attribute_value": attribute["value"],
                "graph": graph,
                "term": term,
                "distance_intent": bucket,
                "same_attribute_rationale": _clean_text(item.get("same_attribute_rationale")),
            }
        )
        graph_counts[graph] += 1
        bucket_counts[bucket] += 1
        attribute_counts[attr_id] += 1
    missing_graphs = [name for name in GRAPH_NAMES if graph_counts[name] == 0]
    if missing_graphs:
        return []
    if require_full_coverage:
        missing_attributes = [name for name in attributes if attribute_counts[name] == 0]
        if missing_attributes or min(bucket_counts["near"], bucket_counts["far"]) < 4:
            return []
    elif min(bucket_counts["near"], bucket_counts["far"]) < 1:
        return []
    return queries[:48]


def expand_attribute_queries_by_graph(
    *, stage: str, attribute_plan: dict[str, Any]
) -> list[dict[str, Any]]:
    """Create endpoint-specific queries without asking the LLM to emit graph enums."""
    facet = FACETS[stage]
    attributes = {item["attribute_id"]: item for item in attribute_plan["attributes"]}
    constraints = {
        "wikidata": (
            "Use canonical English names of real concrete physical entities, organisms, "
            "natural structures, or artifact categories resolvable by Wikidata entity search. "
            "Never invent adjective+source compounds such as compact snowman, stable snowman, "
            "or symmetrical sculpture."
        ),
        "getty_aat": (
            "Use short plausible Getty AAT preferred noun terms for form, aesthetic type, "
            "material, finish, craft, or workmanship; never descriptive sentences."
        ),
        "asknature": (
            "Use organism, function, mechanism, or biological-strategy phrases likely to occur "
            "in AskNature strategy and innovation pages."
        ),
    }
    queries: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for graph in GRAPH_NAMES:
        prompt = f"""
variation_facet: {stage}
source_anchor: {attribute_plan['source_anchor']}
seed_attributes: {json.dumps(attribute_plan['attributes'], ensure_ascii=False)}
locked_facets: {json.dumps(facet['locked'])}
target_graph: {graph}
target_graph_role: {facet['graph_focus'][graph]}
eligible_target_kind: {facet['target_kind']}
target_graph_constraint: {constraints[graph]}

Generate one near and one far query for EVERY attribute_id, for target_graph
{graph} only. Each query must retrieve a concrete node or indexed strategy
that exhibits the SAME cited attribute. Do not change attribute dimensions and
do not output final design targets. A near query may remain in the source's
physical domain. A far query must omit the source noun and probe another
physical domain while preserving the attribute. Use short English noun phrases
of at most 6 words suitable for this graph's actual search endpoint.

Return exactly:
{{"queries":[{{
  "attribute_id":"attr_01",
  "attribute_value":"verbatim seed attribute value",
  "term":"one graph-specific search term",
  "distance_intent":"near",
  "same_attribute_rationale":"how the term preserves that attribute"
}}]}}
Do not include a graph field; the program fixes it to {graph}.
""".strip()
        accepted: list[dict[str, Any]] = []
        feedback = ""
        for attempt in range(4):
            attempt_prompt = prompt
            if feedback:
                attempt_prompt += (
                    "\nThe previous answer failed coverage validation: "
                    + feedback
                    + ". Return a fresh complete answer."
                )
            payload = call_runtime_json(QUERY_SYSTEM, attempt_prompt)
            if os.getenv("CF_DEBUG_ATTRIBUTE_KG", "").lower() in {"1", "true", "yes"}:
                print(
                    f"[attribute_kg] raw_query_payload graph={graph} attempt={attempt + 1} "
                    + json.dumps(payload, ensure_ascii=False),
                    file=sys.stderr,
                    flush=True,
                )
            parsed: list[dict[str, Any]] = []
            local_seen: set[tuple[str, str]] = set()
            for item in (payload or {}).get("queries") or []:
                if not isinstance(item, dict):
                    continue
                attr_id = _clean_text(item.get("attribute_id"))
                term = _clean_text(item.get("term"))
                bucket = _clean_text(item.get("distance_intent")).lower()
                key = (attr_id, term.lower())
                if (
                    attr_id not in attributes
                    or bucket not in {"near", "far"}
                    or not term
                    or len(term.split()) > 6
                    or key in local_seen
                ):
                    continue
                local_seen.add(key)
                parsed.append(
                    {
                        "attribute_id": attr_id,
                        "term": term,
                        "distance_intent": bucket,
                        "same_attribute_rationale": _clean_text(item.get("same_attribute_rationale")),
                    }
                )
            coverage = {(item["attribute_id"], item["distance_intent"]) for item in parsed}
            required = {(attr_id, bucket) for attr_id in attributes for bucket in ("near", "far")}
            if required.issubset(coverage):
                accepted = parsed
                break
            feedback = f"missing pairs: {sorted(required - coverage)}"
        if not accepted:
            raise RuntimeError(f"{graph} query expansion incomplete after retries: {feedback}")

        for item in accepted:
            key = (item["attribute_id"], graph, item["term"].lower())
            if key in seen:
                continue
            seen.add(key)
            attribute = attributes[item["attribute_id"]]
            queries.append(
                {
                    "query_id": f"query_{len(queries) + 1:03d}",
                    "attribute_id": item["attribute_id"],
                    "attribute_dimension": attribute["dimension"],
                    "attribute_value": attribute["value"],
                    "graph": graph,
                    "term": item["term"],
                    "distance_intent": item["distance_intent"],
                    "same_attribute_rationale": item["same_attribute_rationale"],
                }
            )

    expected_per_graph = len(attributes) * 2
    graph_counts = Counter(item["graph"] for item in queries)
    bucket_counts = Counter(item["distance_intent"] for item in queries)
    if any(graph_counts[name] < expected_per_graph for name in GRAPH_NAMES):
        raise RuntimeError(f"graph-specific query expansion incomplete: {dict(graph_counts)}")
    if bucket_counts["near"] != bucket_counts["far"]:
        raise RuntimeError(f"unbalanced near/far graph queries: {dict(bucket_counts)}")
    return queries


def expand_attribute_queries_unconstrained(
    *, stage: str, attribute_plan: dict[str, Any]
) -> list[dict[str, Any]]:
    """Expand every seed attribute per graph, without semantic-distance buckets."""
    facet = FACETS[stage]
    attributes = {item["attribute_id"]: item for item in attribute_plan["attributes"]}
    constraints = {
        "wikidata": (
            "Use canonical English names of concrete physical entities, organisms, natural "
            "structures, or artifact categories resolvable by Wikidata entity search."
        ),
        "getty_aat": (
            "Use plausible Getty AAT preferred noun terms for form, aesthetic type, material, "
            "finish, craft, or workmanship."
        ),
        "asknature": (
            "Use concrete organisms, physical mechanisms, functions, or biological-strategy "
            "phrases likely to occur on AskNature strategy/innovation pages."
        ),
    }
    queries: list[dict[str, Any]] = []
    graph_filter = {
        item.strip()
        for item in os.getenv("CF_KG_GRAPH_FILTER", "").split(",")
        if item.strip()
    }
    active_graphs = tuple(graph for graph in GRAPH_NAMES if not graph_filter or graph in graph_filter)
    for graph in active_graphs:
        for attr_id, attribute in attributes.items():
            prompt = f"""
variation_facet: {stage}
source_anchor: {attribute_plan['source_anchor']}
single_seed_attribute: {json.dumps(attribute, ensure_ascii=False)}
target_graph: {graph}
target_graph_role: {facet['graph_focus'][graph]}
eligible_target_kind: {facet['target_kind']}
constraint: {constraints[graph]}

Generate exactly ONE new short search term for this one attribute.
The term must name a concrete donor material, coating, natural
structure, craft, or physical phenomenon that visibly exhibits the SAME cited
attribute. For Texture, deliberately cross into different material families;
do not simply repeat the source material. The terms will be sent verbatim to
the real {graph} endpoint. Do not output final object prompts, semantic-distance
labels, or generic classes such as material, surface, object, or thing.
Use canonical English entity labels, preferably one or two words each. Do not
append descriptor words such as texture, surface, structure, formation,
appearance, effect, or pattern. Terms in one response must be distinct from
each other and must not repeat terms already collected.

Return exactly three items:
{{"queries":[
  {{"attribute_id":"{attr_id}","attribute_value":"{attribute['value']}",
    "term":"concrete term 1","same_attribute_rationale":"how the donor exhibits {attribute['value']}"}},
  {{"attribute_id":"{attr_id}","attribute_value":"{attribute['value']}",
    "term":"concrete term 2","same_attribute_rationale":"how the donor exhibits {attribute['value']}"}},
  {{"attribute_id":"{attr_id}","attribute_value":"{attribute['value']}",
    "term":"concrete term 3","same_attribute_rationale":"how the donor exhibits {attribute['value']}"}}
]}}
""".strip()
            accepted: list[dict[str, Any]] = []
            feedback = ""
            accumulated: list[dict[str, Any]] = []
            seen_terms: set[str] = set()
            for attempt in range(6):
                attempt_prompt = prompt
                attempt_prompt += (
                    "\nAlready collected terms that MUST NOT be repeated: "
                    + json.dumps([item["term"] for item in accumulated], ensure_ascii=False)
                )
                if feedback:
                    attempt_prompt += f"\nPrevious response failed: {feedback}. Return one different term."
                payload = call_runtime_json(QUERY_SYSTEM, attempt_prompt, max_tokens=1024)
                if os.getenv("CF_DEBUG_ATTRIBUTE_KG", "").lower() in {"1", "true", "yes"}:
                    print(
                        f"[attribute_kg] raw_query_payload graph={graph} attribute={attr_id} "
                        f"attempt={attempt + 1} " + json.dumps(payload, ensure_ascii=False),
                        file=sys.stderr,
                        flush=True,
                    )
                payload_items = (payload or {}).get("queries") or []
                if not payload_items and isinstance(payload, dict) and payload.get("term"):
                    payload_items = [payload]
                for item in payload_items:
                    if not isinstance(item, dict):
                        continue
                    term = _clean_text(item.get("term"))
                    key = term.lower()
                    if not term or len(term.split()) > 6 or key in seen_terms:
                        continue
                    seen_terms.add(key)
                    accumulated.append(
                        {
                            "attribute_id": attr_id,
                            "term": term,
                            "same_attribute_rationale": _clean_text(
                                item.get("same_attribute_rationale")
                            ),
                        }
                    )
                if len(accumulated) >= 3:
                    accepted = accumulated[:3]
                    break
                feedback = (
                    f"need three unique concrete terms; accumulated={len(accumulated)}"
                )
            if not accepted and len(accumulated) >= 2:
                accepted = accumulated
            if not accepted:
                if stage != "texture":
                    raise RuntimeError(
                        f"{graph}/{attr_id} query expansion incomplete after retries: {feedback}"
                    )
                accepted = _fallback_texture_graph_queries(
                    graph=graph, attributes={attr_id: attribute}
                )

            for item in accepted:
                queries.append(
                    {
                        "query_id": f"query_{len(queries) + 1:03d}",
                        "attribute_id": attr_id,
                        "attribute_dimension": attribute["dimension"],
                        "attribute_value": attribute["value"],
                        "graph": graph,
                        "term": item["term"],
                        "same_attribute_rationale": item["same_attribute_rationale"],
                    }
                )
    expected = len(attributes) * 2
    counts = Counter(item["graph"] for item in queries)
    if any(counts[graph] < expected for graph in active_graphs):
        raise RuntimeError(f"graph query coverage incomplete: {dict(counts)}")
    return queries


def _fallback_texture_graph_queries(
    *, graph: str, attributes: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Deterministic attribute-to-graph query fallback for material transfer.

    This is not a final target list. It only turns already-planned source
    material attributes into real graph search terms when the query LLM returns
    incomplete JSON.
    """

    def terms_for(attribute: dict[str, Any]) -> list[str]:
        dimension = str(attribute.get("dimension") or "").lower()
        value = str(attribute.get("value") or "").lower()
        evidence = str(attribute.get("evidence") or "").lower()
        text = " ".join([dimension, value, evidence])
        if graph == "wikidata":
            if "granular" in text or "particle" in text:
                return ["pumice", "sandstone"]
            if "rough" in text:
                return ["shagreen", "basalt"]
            if "matte" in text or "scattering" in text:
                return ["chalk", "frosted glass"]
            if "snow" in text or "ice" in text or "cold" in text:
                return ["snow", "rime ice"]
            return ["ceramic glaze", "wax"]
        if graph == "getty_aat":
            if "granular" in text or "particle" in text:
                return ["pumice", "granulation"]
            if "rough" in text:
                return ["shagreen", "matte finish"]
            if "matte" in text or "scattering" in text:
                return ["matte", "frosted glass"]
            if "snow" in text or "ice" in text or "cold" in text:
                return ["ice", "crystal"]
            return ["glazes", "coatings"]
        if graph == "asknature":
            if "granular" in text or "particle" in text:
                return ["diatom silica", "cuttlefish bone"]
            if "rough" in text:
                return ["shark skin", "gecko toe"]
            if "matte" in text or "scattering" in text:
                return ["white beetle scales", "moth wing scales"]
            if "snow" in text or "ice" in text or "cold" in text:
                return ["polar bear fur", "ice nucleation"]
            return ["biofilm coating", "waxy leaf"]
        raise ValueError(graph)

    out: list[dict[str, Any]] = []
    for attr_id, attribute in attributes.items():
        chosen = terms_for(attribute)[:2]
        while len(chosen) < 2:
            chosen.append(str(attribute.get("value") or "surface material"))
        for term in chosen:
            out.append(
                {
                    "attribute_id": attr_id,
                    "term": term,
                    "same_attribute_rationale": (
                        f"Searches {graph} for a concrete material/surface entity "
                        f"that exhibits the source attribute: {attribute.get('value')}"
                    ),
                }
            )
    return out


def _wikidata_candidates(query: dict[str, Any]) -> list[dict[str, Any]]:
    record = build_concept(query["term"])
    candidates: list[dict[str, Any]] = []

    def add(label: str, node_id: str, edge: str, description: str = "") -> None:
        label = _clean_text(label)
        if label:
            candidates.append(
                {
                    "raw_kg_target": label,
                    "graph_node_id": node_id,
                    "graph": "wikidata",
                    "edge": edge,
                    "description": description,
                }
            )

    add(record.label or query["term"], record.qid, "matched concept", record.description)
    for label, qid in list(zip(record.parent_labels, record.parent_qids))[:2]:
        add(label, qid, "subclass of")
    for label, qid in list(zip(record.part_of_labels, record.part_of_qids))[:1]:
        add(label, qid, "part of")
    for label, qid in list(zip(record.facet_labels, record.facet_qids))[:1]:
        add(label, qid, "facet of")
    return candidates


def _getty_candidates(query: dict[str, Any]) -> list[dict[str, Any]]:
    records = getty_aat_search(query["term"], limit=3)
    return [
        {
            "raw_kg_target": _clean_text(record.label),
            "graph_node_id": str(record.aat_id),
            "graph": "getty_aat",
            "edge": "AAT search match",
            "description": "Getty Art & Architecture Thesaurus concept",
            "broader_labels": list(record.broader_labels),
        }
        for record in records
        if _clean_text(record.label)
    ]


def _asknature_candidates(query: dict[str, Any]) -> list[dict[str, Any]]:
    """Retrieve actual AskNature strategy/innovation nodes from search HTML.

    The Original helper intentionally keeps only a small keyword whitelist,
    which drops valid attribute-led strategies. Here the node URL is the graph
    identity and the page title is the raw node label.
    """
    search_url = f"https://asknature.org/?s={quote_plus(query['term'])}"
    search_text = _kg_http_text(search_url, timeout=30)
    urls: list[str] = []
    for match in re.findall(
        r"https://asknature\.org/(?:strategy|innovation)/[^\"'<>\\\s]+/?",
        search_text,
        flags=re.I,
    ):
        clean_url = html.unescape(match).rstrip("/.,)") + "/"
        if clean_url not in urls:
            urls.append(clean_url)
        if len(urls) >= 3:
            break
    out: list[dict[str, Any]] = []
    for index, node_url in enumerate(urls, start=1):
        slug = urlparse(node_url).path.rstrip("/").split("/")[-1]
        label = re.sub(r"\s+", " ", slug.replace("-", " ")).strip()
        try:
            page_text = _kg_http_text(node_url, timeout=20)
            title = re.search(
                r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
                page_text,
                flags=re.I,
            ) or re.search(r"<title>(.*?)</title>", page_text, flags=re.I | re.S)
            if title:
                label = _clean_text(html.unescape(re.sub(r"<[^>]+>", " ", title.group(1))))
                label = re.sub(r"\s*[|–-]\s*AskNature\s*$", "", label, flags=re.I)
        except Exception:
            pass
        if label:
            out.append(
                {
                    "raw_kg_target": label,
                    "graph_node_id": node_url,
                    "graph": "asknature",
                    "edge": "AskNature indexed strategy",
                    "description": "AskNature biological strategy or physical mechanism",
                }
            )
    return out


def retrieve_three_graphs(queries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    os.environ["CF_ENABLE_ASKNATURE"] = "true"
    proxy = _kg_proxy()
    if proxy:
        os.environ.setdefault("CF_KB_CURL_PROXY", proxy)
    graph_filter = {
        item.strip()
        for item in os.getenv("CF_KG_GRAPH_FILTER", "").split(",")
        if item.strip()
    }
    if graph_filter:
        queries = [query for query in queries if query.get("graph") in graph_filter]
    dispatch: dict[str, Callable[[dict[str, Any]], list[dict[str, Any]]]] = {
        "wikidata": _wikidata_candidates,
        "getty_aat": _getty_candidates,
        "asknature": _asknature_candidates,
    }
    raw: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(dispatch[q["graph"]], q): q for q in queries}
        for future in as_completed(futures):
            query = futures[future]
            try:
                rows = future.result()
            except Exception as exc:
                errors.append({"query_id": query["query_id"], "graph": query["graph"], "error": str(exc)})
                continue
            for row in rows:
                raw.append({**row, "query": query})

    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for row in raw:
        label = _clean_text(row.get("raw_kg_target"))
        if not label or label.lower() in GENERIC_NODES:
            continue
        key = (str(row["query"]["attribute_id"]), label.lower())
        evidence = {
            "graph": row["graph"],
            "graph_node_id": row.get("graph_node_id"),
            "edge": row.get("edge"),
            "query_id": row["query"]["query_id"],
            "query_term": row["query"]["term"],
        }
        if key not in merged:
            merged[key] = {
                "candidate_id": f"cand_{len(merged) + 1:03d}",
                "raw_kg_target": label,
                "attribute_id": row["query"]["attribute_id"],
                "attribute_dimension": row["query"]["attribute_dimension"],
                "attribute_value": row["query"]["attribute_value"],
                "same_attribute_rationale": row["query"]["same_attribute_rationale"],
                "description": row.get("description") or "",
                "graph_evidence": [evidence],
            }
        else:
            merged[key]["graph_evidence"].append(evidence)
    graph_success = Counter(
        evidence["graph"]
        for candidate in merged.values()
        for evidence in candidate["graph_evidence"]
    )
    audit = {
        "query_counts": dict(Counter(q["graph"] for q in queries)),
        "retrieved_evidence_counts": dict(graph_success),
        "raw_candidate_count": len(raw),
        "merged_candidate_count": len(merged),
        "errors": errors,
    }
    required_graphs = tuple(graph_filter) if graph_filter else GRAPH_NAMES
    missing = [name for name in required_graphs if graph_success[name] == 0]
    if missing:
        audit["missing_graphs"] = missing
        audit["partial_graph_mode"] = os.getenv("CF_KG_ALLOW_PARTIAL", "").lower() in {
            "1",
            "true",
            "yes",
        }
        if not audit["partial_graph_mode"] or not merged:
            raise RuntimeError(f"three-graph retrieval missing evidence from: {missing}; audit={audit}")
    return list(merged.values()), audit


def _score_chunk(
    *, stage: str, attribute_plan: dict[str, Any], candidates: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    facet = FACETS[stage]
    compact = [
        {
            "candidate_id": item["candidate_id"],
            "raw_kg_target": item["raw_kg_target"],
            "attribute_id": item["attribute_id"],
            "attribute_dimension": item["attribute_dimension"],
            "attribute_value": item["attribute_value"],
            "description": item.get("description"),
            "graphs": sorted({x["graph"] for x in item["graph_evidence"]}),
            "query_terms": sorted({x["query_term"] for x in item["graph_evidence"]}),
        }
        for item in candidates
    ]
    prompt = f"""
variation_facet: {stage}
source_anchor: {attribute_plan['source_anchor']}
source_attributes: {json.dumps(attribute_plan['attributes'], ensure_ascii=False)}
locked_facets: {json.dumps(facet['locked'])}
eligible_target_kind: {facet['target_kind']}
candidates: {json.dumps(compact, ensure_ascii=False)}

For every candidate score:
- attribute_alignment: does it exhibit the candidate's cited attribute_dimension and
  attribute_value? Judge ONLY that bound attribute, not every source attribute.
- feasibility_3d: can its visible property be realized in a coherent single 3D object?
- structural_transferability: can the relational property be mapped to the source while preserving locked facets?
- visible_decodeability: will the transfer be visually legible rather than abstract?
Use 0.0 to 1.0. passed must be false for broad classes, unrelated terms,
nonphysical concepts, or targets of the wrong variation facet.
For texture/material variation, a DIFFERENT material family is allowed and often
desirable when it shares the bound physical attribute (for example smoothness,
roughness, gloss, opacity, scattering, porosity, or microstructure). Do not reject
a candidate merely because it is not the source material family. The transfer is
analogical: preserve geometry while borrowing that physical surface property.

Return exactly:
{{"scores":[{{
  "candidate_id":"cand_001",
  "attribute_alignment":0.0,
  "feasibility_3d":0.0,
  "structural_transferability":0.0,
  "visible_decodeability":0.0,
  "passed":false,
  "shared_attribute":"short phrase",
  "transferable_principle":"short physical principle",
  "reason":"evidence-based reason"
}}]}}
""".strip()
    payload: dict[str, Any] | None = None
    for _ in range(3):
        payload = call_runtime_json(SCORING_SYSTEM, prompt)
        if isinstance(payload, dict) and isinstance(payload.get("scores"), list):
            break
        if isinstance(payload, dict) and any(
            name in payload
            for name in (
                "attribute_alignment",
                "feasibility_3d",
                "structural_transferability",
                "visible_decodeability",
            )
        ):
            payload = {"scores": [payload]}
            break
    if not isinstance(payload, dict):
        raise RuntimeError("paper scoring engine returned no structured result")
    out: dict[str, dict[str, Any]] = {}
    response_scores = [item for item in (payload.get("scores") or []) if isinstance(item, dict)]
    if len(candidates) == 1 and response_scores:
        response_scores = response_scores[:1]
    for item in response_scores:
        if not isinstance(item, dict):
            continue
        cid = _clean_text(item.get("candidate_id"))
        if len(candidates) == 1 and len(response_scores) == 1:
            cid = candidates[0]["candidate_id"]
        if cid not in {candidate["candidate_id"] for candidate in candidates}:
            continue
        numeric = {}
        for name in (
            "attribute_alignment", "feasibility_3d", "structural_transferability", "visible_decodeability"
        ):
            numeric[name] = max(0.0, min(1.0, float(item.get(name) or 0.0)))
        threshold_pass = (
            numeric["attribute_alignment"] >= 0.62
            and numeric["feasibility_3d"] >= 0.62
            and numeric["structural_transferability"] >= 0.62
            and numeric["visible_decodeability"] >= 0.55
        )
        out[cid] = {
            **numeric,
            "passed": bool(item.get("passed")) and threshold_pass,
            "shared_attribute": _clean_text(item.get("shared_attribute")),
            "transferable_principle": _clean_text(item.get("transferable_principle")),
            "reason": _clean_text(item.get("reason")),
        }
    if len(candidates) > 1:
        missing = [candidate for candidate in candidates if candidate["candidate_id"] not in out]
        for candidate in missing:
            out.update(
                _score_chunk(
                    stage=stage,
                    attribute_plan=attribute_plan,
                    candidates=[candidate],
                )
            )
    return out


def score_candidates(
    *, stage: str, attribute_plan: dict[str, Any], candidates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    planner_scores: dict[str, dict[str, Any]] = {}
    chunk_size = max(1, int(os.getenv("CF_SCORE_CHUNK_SIZE", "6")))
    for start in range(0, len(candidates), chunk_size):
        planner_scores.update(
            _score_chunk(
                stage=stage,
                attribute_plan=attribute_plan,
                candidates=candidates[start : start + chunk_size],
            )
        )
    scored: list[dict[str, Any]] = []
    for candidate in candidates:
        score = planner_scores.get(candidate["candidate_id"])
        if not score or not score["passed"]:
            candidate["paper_scoring"] = score or {"passed": False, "reason": "missing scorer result"}
            scored.append(candidate)
            continue
        total = (
            0.30 * score["attribute_alignment"]
            + 0.30 * score["feasibility_3d"]
            + 0.30 * score["structural_transferability"]
            + 0.10 * score["visible_decodeability"]
        )
        candidate["paper_scoring"] = {
            **score,
            "total_score": round(total, 6),
            "passed": True,
            "semantic_distance_constraint": "none",
        }
        scored.append(candidate)
    return scored


def select_top_diverse(candidates: list[dict[str, Any]], count: int = 4) -> list[dict[str, Any]]:
    """Select the best feasible transfers without near/far classification."""
    pool = [item for item in candidates if item.get("paper_scoring", {}).get("passed")]
    selected: list[dict[str, Any]] = []
    used_labels: set[str] = set()
    used_attributes: set[str] = set()
    used_graphs: Counter[str] = Counter()
    while len(selected) < count:
        choices = [item for item in pool if item["raw_kg_target"].lower() not in used_labels]
        if not choices:
            break

        def rank(item: dict[str, Any]) -> tuple[float, str]:
            graphs = {e["graph"] for e in item["graph_evidence"]}
            graph_bonus = 0.05 if any(used_graphs[g] == 0 for g in graphs) else 0.0
            attribute_bonus = 0.04 if item["attribute_id"] not in used_attributes else 0.0
            return (
                float(item["paper_scoring"]["total_score"]) + graph_bonus + attribute_bonus,
                item["raw_kg_target"],
            )

        choice = max(choices, key=rank)
        selected.append(choice)
        used_labels.add(choice["raw_kg_target"].lower())
        used_attributes.add(choice["attribute_id"])
        for graph in {e["graph"] for e in choice["graph_evidence"]}:
            used_graphs[graph] += 1
    if len(selected) != count:
        raise RuntimeError(f"only {len(selected)} feasible transferable candidates available; required={count}")
    return selected


def select_material_family_diverse(
    candidates: list[dict[str, Any]], count: int = 4
) -> list[dict[str, Any]]:
    pool = [item for item in candidates if item.get("paper_scoring", {}).get("passed")]
    if len(pool) < count:
        return select_top_diverse(candidates, count=count)
    compact = [
        {
            "candidate_id": item["candidate_id"],
            "target": item["raw_kg_target"],
            "source_attribute": item["attribute_value"],
            "description": item.get("description") or "",
            "score": item["paper_scoring"].get("total_score"),
        }
        for item in pool
    ]
    prompt = f"""
passed_material_candidates: {json.dumps(compact, ensure_ascii=False)}
required_count: {count}

Choose exactly {count} candidate_ids for visibly different material-transfer
directions. Maximize diversity of donor material family and PBR behavior. Do
not choose two members of the same obvious family (for example a substance and
its crystal/particle form, or a material and a form made from that material).
Prefer coverage across distinct behaviors such as mineral/stone, fibrous/soft,
metallic/glassy, porous/granular, organic, translucent, or fluid/solid when
those candidates exist. All chosen candidates must come from the input list.

Return exactly: {{"candidate_ids":["cand_001"]}}
""".strip()
    payload = call_runtime_json(
        "You select a diverse portfolio from already-scored physical material candidates.",
        prompt,
        max_tokens=512,
    )
    requested = [str(item) for item in (payload or {}).get("candidate_ids") or []]
    by_id = {item["candidate_id"]: item for item in pool}
    selected = [by_id[item] for item in requested if item in by_id]
    if len(selected) == count and len({item["candidate_id"] for item in selected}) == count:
        return selected
    return select_top_diverse(candidates, count=count)


def reject_texture_noops(
    *, stage: str, attribute_plan: dict[str, Any], candidates: list[dict[str, Any]]
) -> None:
    if stage != "texture" or os.getenv("CF_DISABLE_TEXTURE_NOOP_GATE", "").lower() in {"1", "true", "yes"}:
        return
    source_text = " ".join(
        f"{item.get('value', '')} {item.get('evidence', '')}"
        for item in attribute_plan.get("attributes") or []
    ).lower()
    source_roots = {
        token[:5]
        for token in re.findall(r"[a-z]+", source_text)
        if len(token) >= 5
    }
    for candidate in candidates:
        score = candidate.get("paper_scoring") or {}
        if not score.get("passed"):
            continue
        target_tokens = [
            token for token in re.findall(r"[a-z]+", candidate.get("raw_kg_target", "").lower())
            if len(token) >= 5
        ]
        if target_tokens and all(token[:5] in source_roots for token in target_tokens):
            score["passed"] = False
            score["no_op_material_target"] = True
            score["reason"] = (
                f"{score.get('reason', '')} Rejected as a material no-op because the target is already "
                "explicitly present in the source material evidence."
            ).strip()


def structure_mapping(
    *, stage: str, object_type: str, attribute_plan: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    attribute = next(
        item for item in attribute_plan["attributes"] if item["attribute_id"] == candidate["attribute_id"]
    )
    prompt = f"""
source_noun: {object_type}
variation_facet: {stage}
source_attribute: {json.dumps(attribute, ensure_ascii=False)}
raw_kg_node_verbatim: {candidate['raw_kg_target']}
shared_attribute: {candidate['paper_scoring']['shared_attribute']}
transferable_principle: {candidate['paper_scoring']['transferable_principle']}
locked_facets: {json.dumps(attribute_plan['locked_facets'])}
graph_evidence: {json.dumps(candidate['graph_evidence'], ensure_ascii=False)}

Map relational structure, not surface word association. Return exactly:
{{
  "raw_kg_target": "verbatim raw_kg_node_verbatim",
  "source_attribute_id": "{candidate['attribute_id']}",
  "source_attribute": "verbatim source attribute value",
  "donor_relational_property": "physical property exhibited by the donor",
  "correspondence": "source attribute ↔ donor property",
  "transfer_operation": "one visible operation limited to the variation facet",
  "preserved_identity": ["all locked facets"],
  "mapping_rationale": "why this is a coherent analogy"
}}
""".strip()
    payload: dict[str, Any] | None = None
    for _ in range(3):
        payload = call_runtime_json(MAPPING_SYSTEM, prompt)
        if isinstance(payload, dict):
            break
    required = (
        "raw_kg_target", "source_attribute_id", "source_attribute",
        "donor_relational_property", "correspondence", "transfer_operation",
        "preserved_identity", "mapping_rationale",
    )
    if not isinstance(payload, dict) or any(not payload.get(name) for name in required):
        raise RuntimeError(f"structure mapping incomplete for {candidate['raw_kg_target']}")
    if _clean_text(payload["raw_kg_target"]) != candidate["raw_kg_target"]:
        raise RuntimeError("structure mapper changed the raw KG target")
    payload["raw_kg_target"] = candidate["raw_kg_target"]
    payload["source_attribute_id"] = candidate["attribute_id"]
    payload["source_attribute"] = attribute["value"]
    payload["preserved_identity"] = list(attribute_plan["locked_facets"])
    return payload


def _direction(
    *, index: int, stage: str, object_type: str, attribute_plan: dict[str, Any],
    candidate: dict[str, Any], mapping: dict[str, Any]
) -> dict[str, Any]:
    raw_target = candidate["raw_kg_target"]
    slug = re.sub(r"[^a-z0-9]+", "_", raw_target.lower()).strip("_")[:40]
    primary = candidate["graph_evidence"][0]
    return {
        "direction_id": f"{stage}_{index:02d}_{slug}",
        "anchor": raw_target,
        "raw_kg_target": raw_target,
        "candidate_relation": {
            "predicate": f"transfers same attribute: {candidate['attribute_dimension']}",
            "source_attribute_id": candidate["attribute_id"],
            "source_attribute_value": candidate["attribute_value"],
            "query_term": primary["query_term"],
            "query_graph": primary["graph"],
            "same_attribute_rationale": candidate["same_attribute_rationale"],
        },
        "graph_provenance": candidate["graph_evidence"],
        "original_kg_score": candidate["paper_scoring"]["total_score"],
        "variation_scoring": candidate["paper_scoring"],
        "structure_mapping": mapping,
        "transfer_spec": {
            "graph_anchor": raw_target,
            "direction_title": raw_target,
            "source_attribute_id": candidate["attribute_id"],
            "source_attribute": candidate["attribute_value"],
            "structure_mapping": mapping,
            "preserve_elements": list(attribute_plan.get("preserve_elements") or []),
            "current_contour": attribute_plan.get("current_contour") or {},
            "designer_intent": attribute_plan.get("designer_intent") or "",
        },
        "open_facets": FACETS[stage]["mutable_dimensions"],
        "locked_facets": FACETS[stage]["locked"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    progress: dict[str, Any] = {
        "schema_version": "creativeflow.attribute-first-stage1.v2",
        "status": "running",
        "current_stage": "input_validation",
    }

    def checkpoint(current_stage: str, *, status: str = "running", **updates: Any) -> None:
        progress.update(updates)
        progress["status"] = status
        progress["current_stage"] = current_stage
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(output)

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    stage = _clean_text(payload.get("stage")).lower().replace("-", "_")
    if stage not in FACETS:
        raise ValueError(f"unsupported variation stage: {stage}")
    object_type = _clean_text(payload.get("object_type")).lower()
    if not object_type or object_type == "object":
        raise ValueError("a concrete object_type is required")
    source_image = _clean_text(payload.get("source_image_path"))
    source = SourceSpec(
        source_id=_clean_text(payload.get("source_id")) or f"variation_{object_type}_{stage}",
        object_type=object_type,
        mesh_path=_clean_text(payload.get("source_mesh_path")),
        image_paths=[source_image] if source_image else [],
        render_paths=[str(x) for x in payload.get("source_multiview_paths") or []],
        identity_constraints=[f"lock {x}" for x in FACETS[stage]["locked"]],
    )
    source_elements = payload.get("source_elements") or _read_json(payload.get("source_elements_path"))
    part_semantics = payload.get("part_semantics") or _read_json(payload.get("part_semantics_path"))
    if stage == "part" and not _clean_text(part_semantics.get("canonical_name")):
        raise RuntimeError("Part requires a concrete SAM3D-resolved canonical_name")

    checkpoint(
        "attribute_planning",
        stage=stage,
        source_elements=source_elements,
        part_semantics=part_semantics,
    )
    try:
        attribute_plan = planner_seed_attributes(
            stage=stage,
            source=source,
            object_type=object_type,
            source_elements=source_elements,
            part_semantics=part_semantics,
            user_prompt=_clean_text(payload.get("user_prompt")),
        )
        checkpoint("graph_query_expansion", attribute_plan=attribute_plan, seed_attributes=attribute_plan["attributes"])

        queries = expand_attribute_queries_unconstrained(stage=stage, attribute_plan=attribute_plan)
        checkpoint("three_graph_retrieval", graph_queries=queries)

        candidates, retrieval_audit = retrieve_three_graphs(queries)
        if os.getenv("CF_KG_DIRECT_MATCH_ONLY", "").lower() in {"1", "true", "yes"}:
            candidates = [
                candidate
                for candidate in candidates
                if any(
                    evidence.get("edge") in {
                        "matched concept",
                        "AAT search match",
                        "AskNature indexed strategy",
                    }
                    for evidence in candidate.get("graph_evidence") or []
                )
            ]
            retrieval_audit["direct_match_candidate_count"] = len(candidates)
        checkpoint(
            "paper_candidate_scoring",
            graph_retrieval_audit=retrieval_audit,
            retrieved_graph_candidates=candidates,
        )

        skip_scoring = os.getenv("CF_SKIP_CANDIDATE_SCORING", "").lower() in {
            "1", "true", "yes"
        }
        if skip_scoring:
            scored = candidates
            for candidate in scored:
                candidate["paper_scoring"] = {
                    "passed": True,
                    "total_score": None,
                    "scoring_skipped": True,
                    "shared_attribute": candidate["attribute_value"],
                    "transferable_principle": candidate["same_attribute_rationale"],
                }
        else:
            scored = score_candidates(
                stage=stage,
                attribute_plan=attribute_plan,
                candidates=candidates,
            )
            reject_texture_noops(stage=stage, attribute_plan=attribute_plan, candidates=scored)
        checkpoint("top_candidate_selection", graph_candidates=scored)
        generate_all = os.getenv("CF_GENERATE_ALL_GRAPH_CANDIDATES", "").lower() in {
            "1", "true", "yes"
        }
        if generate_all:
            selected = list(scored)
            top_k = len(selected)
        else:
            top_k = max(1, int(os.getenv("CF_STAGE1_TOP_K", "4")))
            selected = (
                select_material_family_diverse(scored, count=top_k)
                if stage == "texture" and top_k > 1
                else select_top_diverse(scored, count=top_k)
            )
        checkpoint("structure_mapping", selected_candidates=selected)

        directions: list[dict[str, Any]] = []
        for index, candidate in enumerate(selected, start=1):
            mapping = structure_mapping(
                stage=stage,
                object_type=object_type,
                attribute_plan=attribute_plan,
                candidate=candidate,
            )
            directions.append(
                _direction(
                    index=index,
                    stage=stage,
                    object_type=object_type,
                    attribute_plan=attribute_plan,
                    candidate=candidate,
                    mapping=mapping,
                )
            )
            checkpoint("structure_mapping", mapped_direction_count=len(directions))
    except Exception as exc:
        checkpoint("failed", status="failed", error=f"{type(exc).__name__}: {exc}")
        raise

    result = {
        "schema_version": "creativeflow.attribute-first-stage1.v2",
        "status": "completed",
        "stage": stage,
        "source_elements": source_elements,
        "part_semantics": part_semantics,
        "attribute_plan": attribute_plan,
        "seed_attributes": attribute_plan["attributes"],
        "graph_queries": queries,
        "graph_retrieval_audit": retrieval_audit,
        "graph_candidates": scored,
        "directions": directions,
        "selection_policy": {
            "attribute_first": True,
            "planner_precedes_kg": True,
            "graphs": list(GRAPH_NAMES),
            "same_attribute_required": True,
            "scoring": [
                "attribute_alignment", "feasibility_3d", "structural_transferability",
                "visible_decodeability",
            ],
            "scoring_skipped": skip_scoring,
            "semantic_distance_constraint": "none",
            "structure_mapping_after_scoring": True,
            "top_k": top_k,
            "raw_kg_target_normalization": False,
        },
    }
    checkpoint("completed", **result)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
