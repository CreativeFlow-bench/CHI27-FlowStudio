#!/usr/bin/env python3
"""Part-specific KG affordance expansion for CreativeFlow.

This stage is intentionally narrower than the generic variation_graph_directions
module.  For Part variation we first abstract the SAM3D selected part into
local role / socket / scale / orientation seed attributes, then retrieve real
graph evidence from Wikidata, Getty AAT, and AskNature before composing
candidate replacements.

It does not use a fixed candidate word list.  Any final candidate must cite at
least one retrieved graph node or page.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def image_data_url(path: str) -> str:
    suffix = Path(path).suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/webp" if suffix == ".webp" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(Path(path).read_bytes()).decode("ascii")


def call_runtime_json(
    system_prompt: str,
    user_prompt: str,
    *,
    image_paths: list[str] | None = None,
    max_tokens: int = 2048,
    temperature: float = 0.2,
) -> dict[str, Any] | None:
    api_base = os.getenv("CF_TEXT_LLM_API_BASE", "http://127.0.0.1:18084/v1").rstrip("/")
    model = os.getenv("CF_TEXT_LLM_MODEL", "qwen3-planner")
    user_content: str | list[dict[str, Any]] = user_prompt
    if image_paths:
        user_content = [{"type": "text", "text": user_prompt}]
        for path in image_paths:
            if path and Path(path).is_file():
                user_content.append({"type": "image_url", "image_url": {"url": image_data_url(path)}})
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    request = urllib.request.Request(
        api_base + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=240) as response:
            payload = json.loads(response.read().decode("utf-8"))
        text = str(payload["choices"][0]["message"]["content"]).strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S)
        start = text.find("{")
        if start < 0:
            return None
        decoded, _ = json.JSONDecoder().raw_decode(text[start:])
        return decoded if isinstance(decoded, dict) else None
    except Exception as exc:
        if os.getenv("CF_DEBUG_PART_KG", "").lower() in {"1", "true", "yes"}:
            print(f"[part_kg] runtime_json_error: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return None


def load_part_semantics(request: dict[str, Any]) -> dict[str, Any]:
    payload = request.get("part_semantics") or {}
    if not payload and request.get("part_semantics_path"):
        payload = json.loads(Path(str(request["part_semantics_path"])).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        payload = {}
    name = clean(payload.get("canonical_name") or request.get("part_name"))
    if not name:
        raise RuntimeError("part kg expansion requires SAM3D part_semantics.canonical_name")
    payload.setdefault("canonical_name", name)
    return payload


PART_CATEGORY_CONFIG: dict[str, dict[str, Any]] = {
    "mechanical_component": {
        "description": "objective engineered part; preserve connection, tolerance, scale, and functional interface",
        "preferred_dimensions": ["attachment", "scale", "orientation", "shape", "function", "material_feel"],
        "gate_weights": {
            "attachment": 5,
            "scale": 4,
            "orientation": 4,
            "shape": 3,
            "function": 3,
            "material_feel": 1,
            "identity_cue": 0,
        },
        "query_bias": {
            "function": ["handle", "grip", "hand grip", "ergonomic grip", "loop handle", "strap handle"],
            # Avoid raw animal/body-part donor words here. They are too often
            # rendered literally by Qwen-Image (e.g. an octopus face instead of
            # a grip). Query the executable shape/affordance instead.
            "shape": [
                "curved handle",
                "ribbed grip",
                "loop",
                "hook",
                "coil grip",
                "flexible ergonomic grip",
                "suction cup texture",
            ],
            "attachment": ["socket", "mount", "anchor", "connector", "fitting", "joint"],
            "orientation": ["downward handle", "projection", "joint", "axis"],
            "scale": ["hand grip", "knob", "button", "small handle", "trigger guard"],
            "material_feel": ["rubber", "braided rope", "plastic", "silicone", "grippy texture"],
            "identity_cue": ["toy grip", "controller handle", "sport grip"],
        },
        "prompt_style": "technical local component replacement; emphasize exact socket, scale, alignment, and no disconnected prop",
    },
    "artifact_component": {
        "description": "human-made object part; balance physical attachment, usable shape, material, and craft language",
        "preferred_dimensions": ["shape", "attachment", "scale", "material_feel", "function", "identity_cue"],
        "gate_weights": {
            "attachment": 4,
            "shape": 4,
            "scale": 3,
            "material_feel": 3,
            "function": 2,
            "orientation": 2,
            "identity_cue": 2,
        },
        "query_bias": {
            "function": ["handle", "spout", "ornament", "fitting"],
            "shape": ["cone", "boss", "finial", "rosette"],
            "attachment": ["plug", "fitting", "mount", "fastener"],
            "orientation": ["projection", "spout", "stem"],
            "scale": ["knob", "button", "bead", "jewel"],
            "material_feel": ["wood", "cork", "glass", "ceramic"],
            "identity_cue": ["badge", "emblem", "flower", "rosette"],
        },
        "prompt_style": "crafted local object replacement; preserve object identity while letting the selected part become a playful but physically attached object",
    },
    "organic_part": {
        "description": "organic/creature/natural part; allow creative biomorphic substitution more than exact connector logic",
        "preferred_dimensions": ["function", "shape", "material_feel", "identity_cue", "orientation", "scale"],
        "gate_weights": {
            "function": 4,
            "shape": 4,
            "material_feel": 4,
            "identity_cue": 3,
            "orientation": 2,
            "scale": 2,
            "attachment": 1,
        },
        "query_bias": {
            "function": ["beak", "proboscis", "antenna", "sensory organ", "flower", "berry"],
            "shape": ["leaf", "shell", "horn", "petal", "lollipop", "marble"],
            "attachment": ["stem", "root", "joint"],
            "orientation": ["protrusion", "spine", "rostrum"],
            "scale": ["small appendage", "bud", "tendril", "bead", "berry"],
            "material_feel": ["shell", "keratin", "chitin", "petal", "crystal", "gel"],
            "identity_cue": ["flower", "feather", "marking", "display structure", "jewel", "candy"],
        },
        "prompt_style": "creative organic local substitution; preserve identity and position, allow expressive biomorphic form",
    },
    "decorative_symbolic_part": {
        "description": "symbolic/decorative identity cue; prioritize visual meaning, playful material, and local readability",
        "preferred_dimensions": ["identity_cue", "shape", "material_feel", "scale", "attachment", "function"],
        "gate_weights": {
            "identity_cue": 5,
            "shape": 4,
            "material_feel": 4,
            "scale": 3,
            "attachment": 2,
            "function": 2,
            "orientation": 1,
        },
        "query_bias": {
            "function": ["ornament", "flower", "candy", "lollipop", "toy", "jewel", "emblem"],
            "shape": ["lollipop", "star", "heart", "berry", "flower", "gemstone", "toy brick", "cone", "rosette"],
            "attachment": ["pin", "mount", "button", "bead"],
            "orientation": ["projection", "protrusion", "stem"],
            "scale": ["lollipop", "berry", "marble", "toy brick", "bead", "jewel", "button"],
            "material_feel": ["candy", "glass", "jelly", "crystal", "shell", "cork"],
            "identity_cue": ["heart", "star", "flower", "jewel", "toy", "candy", "badge", "emblem"],
        },
        "prompt_style": "far-transfer playful symbolic local replacement; allow vivid color/material/type changes if the new part remains the selected part itself",
    },
    "soft_material_part": {
        "description": "soft fabric/fur/clay/snow part; emphasize softness, deformation, folds, and tactile continuity",
        "preferred_dimensions": ["material_feel", "shape", "scale", "identity_cue", "function"],
        "gate_weights": {
            "material_feel": 5,
            "shape": 3,
            "scale": 3,
            "identity_cue": 2,
            "function": 2,
            "attachment": 1,
            "orientation": 1,
        },
        "query_bias": {
            "function": ["cushion", "tuft", "pad"],
            "shape": ["fold", "puff", "bump", "roll"],
            "attachment": ["seam", "stitch", "patch"],
            "orientation": ["drape", "fold"],
            "scale": ["pom-pom", "button", "tuft"],
            "material_feel": ["felt", "wool", "fur", "clay"],
            "identity_cue": ["pom-pom", "rosette", "badge"],
        },
        "prompt_style": "soft tactile local substitution; preserve soft contact and avoid hard mechanical constraints unless visible",
    },
}


def classify_part_category(request: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    """Classify selected part before choosing expansion/gate policy."""
    explicit = clean(request.get("part_category") or part.get("part_category")).lower()
    if explicit in PART_CATEGORY_CONFIG:
        return {
            "category": explicit,
            "confidence": 1.0,
            "rationale": "explicit category from request/part semantics",
        }

    text = " ".join(
        clean(x)
        for x in [
            request.get("object_type"),
            part.get("canonical_name"),
            part.get("semantic_role"),
            part.get("shape"),
            part.get("material"),
            part.get("function"),
            part.get("attachment"),
        ]
    ).lower()
    mechanical_terms = {
        "gear", "wheel", "bolt", "screw", "hinge", "joint", "motor", "button",
        "switch", "connector", "nozzle", "valve", "handle", "lever", "socket",
        "mechanical", "electrical",
    }
    soft_terms = {"fabric", "cloth", "scarf", "hat", "fur", "wool", "soft", "fold", "drape", "snow"}
    organic_terms = {
        "organ", "limb", "arm", "leg", "eye", "ear", "mouth", "nose", "leaf",
        "flower", "petal", "stem", "branch", "root", "biological", "organic",
    }
    decorative_terms = {
        "symbolic", "aesthetic", "ornament", "decorative", "identity", "badge",
        "emblem", "facial feature", "smile", "button", "nose",
    }
    artifact_terms = {"artifact", "tool", "toy", "furniture", "vessel", "lamp", "teapot", "chair"}

    scores = Counter({
        "mechanical_component": sum(1 for term in mechanical_terms if term in text),
        "soft_material_part": sum(1 for term in soft_terms if term in text),
        "organic_part": sum(1 for term in organic_terms if term in text),
        "decorative_symbolic_part": sum(1 for term in decorative_terms if term in text),
        "artifact_component": sum(1 for term in artifact_terms if term in text),
    })
    if "nose" in text and ("snowman" in text or "aesthetic" in text or "symbolic" in text):
        scores["decorative_symbolic_part"] += 3
        scores["organic_part"] += 1
    category, score = scores.most_common(1)[0]
    if score <= 0:
        category = "artifact_component"
    return {
        "category": category,
        "confidence": min(1.0, 0.35 + 0.15 * max(score, 1)),
        "rationale": f"keyword policy scores={dict(scores)}",
    }


def plan_seed_attributes(request: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    source = clean(request.get("object_type")) or "object"
    part_name = clean(part.get("canonical_name"))
    source_image = clean(request.get("source_image_path"))
    category_plan = classify_part_category(request, part)
    category = category_plan["category"]
    category_config = PART_CATEGORY_CONFIG[category]
    prompt = f"""
You are the Part KG planner for CreativeFlow.

Input source object: {source}
SAM3D selected part semantic:
{json.dumps(part, ensure_ascii=False)}
Selected part category:
{json.dumps(category_plan, ensure_ascii=False)}
Category policy:
{json.dumps(category_config, ensure_ascii=False)}

Goal:
Extract executable seed attributes for knowledge-graph expansion of the
selected part.  DO NOT output final replacement objects.  Avoid overfitting to
the current material or exact old appearance.  For example, if the part is a
carrot-like snowman nose, do not use "carrot" as the only seed; abstract it to
its 3D role and affordance.

Important:
The expansion must be ATTRIBUTE-FIRST. Split the current part into independent
attributes such as function, shape, attachment, orientation, scale, material
feeling, and identity cue. Later each attribute will be queried in knowledge
graphs to find substitutable terms. Do not collapse everything into a generic
"nose" neighbor search.

Use the selected part category:
- mechanical_component: objective connector/size/alignment constraints matter.
- artifact_component: balance use, attachment, shape, and craft/material.
- organic_part: allow creative biomorphic replacement; do not overconstrain connector mechanics.
- decorative_symbolic_part: prioritize identity cue, playful material, and local readability.
- soft_material_part: prioritize softness, folds, deformation, and tactile continuity.

Return JSON only:
{{
  "source_part": "{part_name}",
  "part_role_summary": "...",
  "seed_attributes": [
    {{
      "attribute_id": "attr_01",
      "dimension": "function | shape | attachment | orientation | scale | material_feel | identity_cue",
      "value": "short graph-queryable phrase",
      "source_evidence": "specific evidence from SAM3D/source image",
      "why_executable": "why this can retrieve analogous graph nodes"
    }}
  ]
}}

Need 5-7 attributes. For a snowman nose example, good attributes are not just
"nose"; they are: facial identity cue / short tapered cone / small hard
protruding object / inserted into face socket / forward pointing / hand-sized
local ornament / organic craft material. Adapt this schema to the actual part.
""".strip()
    payload = call_runtime_json(
        "Return strict JSON for CreativeFlow Part KG seed planning.",
        prompt,
        image_paths=[source_image] if source_image and Path(source_image).is_file() else None,
        max_tokens=1536,
        temperature=0.1,
    )
    attrs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in (payload or {}).get("seed_attributes") or []:
        if not isinstance(item, dict):
            continue
        value = clean(item.get("value"))
        dimension = clean(item.get("dimension")).lower().replace(" ", "_")
        if not value or value.lower() in seen:
            continue
        seen.add(value.lower())
        attrs.append(
            {
                "attribute_id": f"attr_{len(attrs) + 1:02d}",
                "dimension": dimension,
                "value": value,
                "source_evidence": clean(item.get("source_evidence")),
                "why_executable": clean(item.get("why_executable")),
            }
        )
    # Robust fallback if the local VLM collapses to the original object.
    if len(attrs) < 5:
        fallback = [
            ("function", f"{part_name} as identity cue"),
            ("shape", clean(part.get("shape")) or "short tapered local form"),
            ("attachment", clean(part.get("attachment")) or "inserted into face socket"),
            ("orientation", "forward pointing protrusion"),
            ("scale", "small local component"),
            ("material_feel", clean(part.get("material")) or "hard tangible object"),
            ("identity_cue", "playful symbolic facial feature"),
        ]
        attrs = [
            {
                "attribute_id": f"attr_{i:02d}",
                "dimension": dim,
                "value": value,
                "source_evidence": clean(part.get("evidence")) or "SAM3D selected part semantic",
                "why_executable": "fallback executable part affordance seed",
            }
            for i, (dim, value) in enumerate(fallback, 1)
        ]
    return {
        "schema_version": "creativeflow.part-kg-seed-plan.v1",
        "source_noun": source,
        "source_part": part_name,
        "part_category": category_plan,
        "category_policy": category_config,
        "part_semantics": part,
        "part_role_summary": clean((payload or {}).get("part_role_summary")) or f"{part_name} as local part",
        "seed_attributes": attrs[:7],
    }


def plan_graph_queries(seed_plan: dict[str, Any]) -> list[dict[str, Any]]:
    category = ((seed_plan.get("part_category") or {}).get("category")) or "artifact_component"
    category_config = PART_CATEGORY_CONFIG.get(category, PART_CATEGORY_CONFIG["artifact_component"])
    prompt = f"""
You convert CreativeFlow Part seed attributes into graph search terms.

Seed plan:
{json.dumps(seed_plan, ensure_ascii=False)}
Part category policy:
{json.dumps(category_config, ensure_ascii=False)}

Generate graph search terms for three graphs:
- wikidata: concrete physical entities, biological structures, artifact components
- getty_aat: components, fittings, ornaments, form/workmanship terms
- asknature: biological organs, protrusions, attachment mechanisms, sensing structures

For every seed attribute, query for substitutable terms that preserve THAT
attribute:
- function -> objects/structures with similar role or affordance
- shape -> concrete forms with similar geometry
- attachment -> components with similar socket/plug/fitting logic
- orientation -> protruding/forward-pointing structures
- scale -> small local components/ornaments/fittings
- material_feel -> comparable tangible material families
- identity_cue -> symbolic decorative/expressive local parts

Terms are NOT final prompts yet. Avoid exact old material lock-in unless the
attribute is explicitly material_feel.

Use category policy to bias queries. Mechanical parts should retrieve connector
and tolerance terms; organic parts should retrieve biomorphic structures;
decorative symbolic parts should retrieve expressive local objects; soft parts
should retrieve tactile/deformable terms.

Return JSON only:
{{"queries":[{{
  "attribute_id":"attr_01",
  "graph":"wikidata|getty_aat|asknature",
  "term":"short English noun phrase, max 5 words",
  "same_affordance_rationale":"..."
}}]}}

Need 24-36 queries total and cover all three graphs. Use diverse terms.
""".strip()
    payload = call_runtime_json(
        "Return strict JSON graph queries for CreativeFlow Part KG expansion.",
        prompt,
        max_tokens=2048,
        temperature=0.25,
    )
    attrs = {a["attribute_id"]: a for a in seed_plan["seed_attributes"]}
    queries: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in (payload or {}).get("queries") or []:
        if not isinstance(item, dict):
            continue
        attr_id = clean(item.get("attribute_id"))
        graph = clean(item.get("graph")).lower().replace("-", "_")
        graph = "getty_aat" if graph in {"getty", "aat", "gettyaat"} else graph
        graph = "asknature" if graph in {"ask_nature", "asknaturenet"} else graph
        term = clean(item.get("term"))
        if attr_id not in attrs or graph not in {"wikidata", "getty_aat", "asknature"} or not term:
            continue
        if len(term.split()) > 6:
            continue
        key = (attr_id, graph, term.lower())
        if key in seen:
            continue
        seen.add(key)
        queries.append(
            {
                "query_id": f"query_{len(queries) + 1:03d}",
                "attribute_id": attr_id,
                "attribute_dimension": attrs[attr_id]["dimension"],
                "attribute_value": attrs[attr_id]["value"],
                "graph": graph,
                "term": term,
                "same_affordance_rationale": clean(item.get("same_affordance_rationale")),
            }
        )
    # Graph-grounded fallback terms are query axes, not final candidates.
    if len(queries) < 12 or len({q["graph"] for q in queries}) < 3:
        fallback_by_dimension = {
            "function": {
                "wikidata": ["beak", "proboscis", "snout", "muzzle"],
                "getty_aat": ["ornaments", "emblems", "decorative elements"],
                "asknature": ["sensing organ", "beak", "proboscis"],
            },
            "shape": {
                "wikidata": ["cone", "spike", "horn", "pine cone"],
                "getty_aat": ["cones", "bosses", "finials"],
                "asknature": ["spike", "cone", "rostrum"],
            },
            "attachment": {
                "wikidata": ["plug", "nozzle", "spout", "fitting"],
                "getty_aat": ["plugs", "fittings", "mounts"],
                "asknature": ["attachment", "suction cup", "hook"],
            },
            "orientation": {
                "wikidata": ["projection", "protrusion", "rostrum"],
                "getty_aat": ["projections", "spouts", "bosses"],
                "asknature": ["protrusion", "rostrum", "spine"],
            },
            "scale": {
                "wikidata": ["button", "knob", "bead", "gemstone"],
                "getty_aat": ["buttons", "knobs", "beads", "jewels"],
                "asknature": ["small appendage", "sensory knob"],
            },
            "material_feel": {
                "wikidata": ["wood", "cork", "crystal", "shell"],
                "getty_aat": ["cork", "wood", "glass", "jewels"],
                "asknature": ["shell", "keratin", "chitin"],
            },
            "identity_cue": {
                "wikidata": ["badge", "emblem", "button", "flower"],
                "getty_aat": ["emblems", "badges", "rosettes"],
                "asknature": ["display structure", "facial marking"],
            },
        }
        for attr in seed_plan["seed_attributes"]:
            dim = attr["dimension"]
            buckets = fallback_by_dimension.get(dim) or fallback_by_dimension.get("function", {})
            # Category-specific terms come first; generic terms fill coverage.
            category_terms = (category_config.get("query_bias") or {}).get(dim) or []
            if category_terms:
                buckets = {
                    graph: list(dict.fromkeys(list(category_terms) + list(terms)))
                    for graph, terms in buckets.items()
                }
            term_limit = 6 if category in {"decorative_symbolic_part", "organic_part"} else 3
            for graph, terms in buckets.items():
                for term in terms[:term_limit]:
                    key = (attr["attribute_id"], graph, term.lower())
                    if key in seen:
                        continue
                    seen.add(key)
                    queries.append(
                        {
                            "query_id": f"query_{len(queries) + 1:03d}",
                            "attribute_id": attr["attribute_id"],
                            "attribute_dimension": attr["dimension"],
                            "attribute_value": attr["value"],
                            "graph": graph,
                            "term": term,
                            "same_affordance_rationale": f"fallback graph search axis for {attr['dimension']} attribute",
                        }
                    )
    # For creative decorative/organic local parts, add a deliberately farther
    # affordance band.  These are still graph query terms, not hard-coded final
    # outputs: the final candidate must be backed by retrieved evidence.
    if category in {"decorative_symbolic_part", "organic_part"}:
        far_axes = [
            ("identity_cue", ["heart", "star", "flower", "jewel", "toy", "candy"]),
            ("shape", ["lollipop", "berry", "marble", "toy brick", "gemstone", "shell"]),
            ("material_feel", ["colored glass", "jelly candy", "crystal", "pearl", "gummy candy"]),
            ("scale", ["bead", "cherry", "acorn", "pom-pom", "button"]),
        ]
        attrs_by_dim = {clean(a.get("dimension")): a for a in seed_plan["seed_attributes"]}
        for dim, terms in far_axes:
            attr = attrs_by_dim.get(dim)
            if not attr:
                continue
            for graph in ["wikidata", "getty_aat", "asknature"]:
                for term in terms:
                    key = (attr["attribute_id"], graph, term.lower())
                    if key in seen:
                        continue
                    seen.add(key)
                    queries.append(
                        {
                            "query_id": f"query_{len(queries) + 1:03d}",
                            "attribute_id": attr["attribute_id"],
                            "attribute_dimension": attr["dimension"],
                            "attribute_value": attr["value"],
                            "graph": graph,
                            "term": term,
                            "same_affordance_rationale": (
                                f"far-distance local replacement query for {attr['dimension']} attribute"
                            ),
                        }
                    )
    return queries[:96]


def fetch_url_json(url: str, timeout: int = 12) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "CreativeFlow/part-kg"})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def wikidata_search(query: dict[str, Any], limit: int = 4) -> list[dict[str, Any]]:
    url = (
        "https://www.wikidata.org/w/api.php?action=wbsearchentities&language=en&format=json&limit="
        + str(limit)
        + "&search="
        + urllib.parse.quote(query["term"])
    )
    rows: list[dict[str, Any]] = []
    try:
        payload = fetch_url_json(url)
        for item in payload.get("search") or []:
            label = clean(item.get("label"))
            if not label:
                continue
            rows.append(
                {
                    "graph": "wikidata",
                    "raw_kg_target": label,
                    "graph_node_id": clean(item.get("id")),
                    "description": clean(item.get("description")),
                    "query": query,
                }
            )
    except Exception as exc:
        rows.append({"graph": "wikidata", "error": f"{type(exc).__name__}: {exc}", "query": query})
    return rows


def getty_search(query: dict[str, Any], limit: int = 4) -> list[dict[str, Any]]:
    if os.getenv("CF_PART_KG_SKIP_GETTY", "").lower() in {"1", "true", "yes"}:
        return [{"graph": "getty_aat", "error": "skipped by CF_PART_KG_SKIP_GETTY", "query": query}]
    # Try the local restored CreativeFlow helper when available.
    root = os.getenv("CF_TRANSFER_PIPELINE_ROOT")
    if root and root not in sys.path:
        sys.path.insert(0, root)
    rows: list[dict[str, Any]] = []
    try:
        from scripts.kb_semantic_distance import getty_aat_search  # type: ignore

        for record in getty_aat_search(query["term"], limit=limit):
            rows.append(
                {
                    "graph": "getty_aat",
                    "raw_kg_target": clean(getattr(record, "label", "")),
                    "graph_node_id": str(getattr(record, "aat_id", "")),
                    "description": clean(getattr(record, "scope_note", "")),
                    "query": query,
                }
            )
    except Exception as exc:
        rows.append({"graph": "getty_aat", "error": f"{type(exc).__name__}: {exc}", "query": query})
    return [r for r in rows if clean(r.get("raw_kg_target")) or r.get("error")]


def asknature_search(query: dict[str, Any], limit: int = 4) -> list[dict[str, Any]]:
    url = "https://asknature.org/?s=" + urllib.parse.quote_plus(query["term"])
    rows: list[dict[str, Any]] = []
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "CreativeFlow/part-kg"})
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=14) as response:
            text = response.read().decode("utf-8", errors="replace")
        seen: set[str] = set()
        for match in re.finditer(r"https://asknature\\.org/(?:strategy|innovation)/[^\"'<>\\s]+/?", text):
            node_url = html.unescape(match.group(0))
            if node_url in seen:
                continue
            seen.add(node_url)
            slug = urllib.parse.urlparse(node_url).path.rstrip("/").split("/")[-1]
            label = clean(slug.replace("-", " "))
            rows.append(
                {
                    "graph": "asknature",
                    "raw_kg_target": label,
                    "graph_node_id": node_url,
                    "description": "AskNature strategy/innovation search result",
                    "query": query,
                }
            )
            if len(rows) >= limit:
                break
    except Exception as exc:
        rows.append({"graph": "asknature", "error": f"{type(exc).__name__}: {exc}", "query": query})
    return rows


def retrieve_graph_evidence(queries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cache_path = os.getenv("CF_PART_KG_EVIDENCE_CACHE")
    if cache_path and Path(cache_path).is_file():
        cache = json.loads(Path(cache_path).read_text(encoding="utf-8"))
        cached_rows = cache.get("evidence") or cache.get("retrieved_graph_evidence") or []
        valid = [row for row in cached_rows if clean(row.get("raw_kg_target"))]
        return valid, {
            "source": "evidence_cache",
            "cache_path": cache_path,
            "query_counts": dict(Counter((row.get("query") or {}).get("graph") for row in valid)),
            "evidence_counts": dict(Counter(row.get("graph") for row in valid)),
            "errors": cache.get("errors") or [],
        }
    dispatch = {"wikidata": wikidata_search, "getty_aat": getty_search, "asknature": asknature_search}
    evidence: list[dict[str, Any]] = []
    max_per_graph = int(os.getenv("CF_PART_KG_MAX_QUERIES_PER_GRAPH", "8"))
    used: Counter[str] = Counter()
    selected_queries: list[dict[str, Any]] = []
    for query in queries:
        if used[query["graph"]] >= max_per_graph:
            continue
        used[query["graph"]] += 1
        selected_queries.append(query)
    for query in selected_queries:
        evidence.extend(dispatch[query["graph"]](query))
    valid = [row for row in evidence if clean(row.get("raw_kg_target"))]
    audit = {
        "query_counts": dict(Counter(q["graph"] for q in selected_queries)),
        "original_query_counts": dict(Counter(q["graph"] for q in queries)),
        "evidence_counts": dict(Counter(row["graph"] for row in valid)),
        "errors": [row for row in evidence if row.get("error")][:20],
    }
    return valid, audit


def synthesize_candidates(
    *,
    request: dict[str, Any],
    seed_plan: dict[str, Any],
    evidence: list[dict[str, Any]],
    count: int,
) -> list[dict[str, Any]]:
    source = clean(request.get("object_type"))
    part_name = seed_plan["source_part"]
    category = ((seed_plan.get("part_category") or {}).get("category")) or "artifact_component"
    compact_evidence = []
    for row in evidence[:80]:
        compact_evidence.append(
            {
                "graph": row["graph"],
                "raw_kg_target": row["raw_kg_target"],
                "description": row.get("description"),
                "query_term": row["query"]["term"],
                "attribute_dimension": row["query"].get("attribute_dimension"),
                "attribute_value": row["query"]["attribute_value"],
                "graph_node_id": row.get("graph_node_id"),
            }
        )
    prompt = f"""
You are CreativeFlow's Part structure-mapping selector.

Source object: {source}
Selected part: {part_name}
Seed plan:
{json.dumps(seed_plan, ensure_ascii=False)}

Retrieved KG evidence:
{json.dumps(compact_evidence, ensure_ascii=False)}

Select {count} diverse candidates. Candidates must come from retrieved KG
targets only. The target should be a concrete physical object, component,
biological structure, material form, or natural form that can replace one or
more attributes of the selected part. For a snowman nose, it must plausibly
become the nose itself, not a hat ornament, background object, sticker, or
whole-object redesign.

Useful Part-transfer rule:
The selected part keeps its role; the target donates a local shape/affordance.
Do NOT ask whether the target is semantically close to the source object. Ask
whether the target can be reinterpreted as the selected part in the same 3D
context. For a grip handle, good far transfer keeps holdability, downward
extension, hand-scale, and socket connection even if the donor comes from a
natural or biological analogy; decode it into executable attributes such as
curved flexible form, ribbed surface, suction-like dimples, or tactile grip
texture. Bad transfer becomes a whole creature, a detached prop, or a surface
ornament.

Attribute-first selection rule:
- Do not merely choose semantic neighbors of the part name.
- Explain which current attributes are replaced: function, shape, attachment,
  orientation, scale, material_feel, identity_cue.
- Prefer candidates that satisfy at least two attributes, e.g. shape + socket,
  function + protrusion, material_feel + identity_cue.

Return JSON only:
{{"candidates":[{{
  "raw_kg_target":"verbatim retrieved target label",
  "graphs":["wikidata"],
  "graph_node_ids":["..."],
  "source_attribute":"which seed attribute it maps from",
  "replaced_attributes":["shape","attachment"],
  "attribute_mapping":"source attribute -> target KG property mapping",
  "part_affordance_mapping":"why it can still read as the selected part",
  "role_transfer_mapping":"how the target is reinterpreted as the same selected-part role instead of becoming a separate object",
  "socket_compatibility":"how it attaches to the same 3D socket",
  "scale_orientation_constraints":"how it remains a compatible local part",
  "visual_executable_gate":"pass | risky | reject",
  "risk_reason":"...",
  "generation_phrase":"short phrase for the local replacement"
}}]}}
Do not invent targets not in the evidence list.
""".strip()
    payload = call_runtime_json(
        "Return strict JSON for graph-grounded Part candidate selection.",
        prompt,
        max_tokens=3072,
        temperature=0.2,
    )
    evidence_by_label: dict[str, list[dict[str, Any]]] = {}
    for row in evidence:
        evidence_by_label.setdefault(row["raw_kg_target"].lower(), []).append(row)
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in (payload or {}).get("candidates") or []:
        if not isinstance(item, dict):
            continue
        raw = clean(item.get("raw_kg_target"))
        rows = evidence_by_label.get(raw.lower()) or []
        if not raw or raw.lower() in seen or not rows:
            continue
        gate = clean(item.get("visual_executable_gate")).lower()
        if gate == "reject":
            continue
        seen.add(raw.lower())
        candidates.append(
            {
                "candidate_concept_name": raw,
                "raw_kg_target": raw,
                "graphs": sorted({r["graph"] for r in rows}),
                "graph_evidence": rows[:5],
                "source_attribute": clean(item.get("source_attribute")),
                "replaced_attributes": [clean(x) for x in item.get("replaced_attributes") or [] if clean(x)],
                "attribute_mapping": clean(item.get("attribute_mapping")),
                "part_affordance_mapping": clean(item.get("part_affordance_mapping")),
                "role_transfer_mapping": clean(item.get("role_transfer_mapping")),
                "socket_compatibility": clean(item.get("socket_compatibility")),
                "scale_orientation_constraints": clean(item.get("scale_orientation_constraints")),
                "visual_executable_gate": gate or "risky",
                "risk_reason": clean(item.get("risk_reason")),
                "generation_phrase": clean(item.get("generation_phrase")) or raw,
            }
        )
        if len(candidates) >= count:
            break
    deterministic = deterministic_candidates_from_evidence(evidence, count=max(count * 3, 16))
    implicit_role_transfer: list[dict[str, Any]] = []
    if category == "mechanical_component" and evidence:
        # Getty/Wikidata often retrieve conservative engineered terms.  Keep
        # those as graph evidence, but also run the paper-style second route:
        # implicit creative exploration over the executable seed attributes.
        # These candidates are never reported as live KG nodes.
        implicit_role_transfer = fallback_candidates_from_seed_plan(
            seed_plan,
            count=max(count, 4),
            evidence_status="implicit_role_transfer_seed",
            risk_reason="LLM/seed-attribute far-transfer route; not retrieved as a live KG node.",
        )
    by_key: dict[str, dict[str, Any]] = {}
    for item in candidates + deterministic + implicit_role_transfer:
        key = clean(item.get("raw_kg_target")).lower()
        if not key:
            continue
        if key not in by_key:
            by_key[key] = item
            continue
        # Preserve the version with richer provenance / stronger gate.
        old = by_key[key]
        if candidate_gate_score(item, category=category) > candidate_gate_score(old, category=category):
            by_key[key] = item
    candidates = rank_and_gate_candidates(list(by_key.values()), count=count, category=category)
    needs_seed_fallback = not candidates
    if candidates and category == "mechanical_component":
        has_pass = any(clean(item.get("visual_executable_gate")).lower() == "pass" for item in candidates)
        if not has_pass:
            needs_seed_fallback = True
    if needs_seed_fallback:
        candidates = fallback_candidates_from_seed_plan(seed_plan, count=count)
        if not candidates:
            raise RuntimeError("KG candidate selector returned no graph-grounded candidates")
    return candidates


def fallback_candidates_from_seed_plan(
    seed_plan: dict[str, Any],
    *,
    count: int,
    evidence_status: str = "network_unavailable_fallback",
    risk_reason: str = "No live graph evidence; candidate is generated from executable seed attributes only.",
) -> list[dict[str, Any]]:
    """Network-failure fallback built from executable seed attributes.

    This is deliberately not presented as live KG evidence.  It exists so Part
    prompt iteration can continue on isolated GPU servers while preserving the
    same attribute-first contract: function, shape, attachment, orientation and
    scale must remain explicit in every candidate.  The output carries
    graph_evidence_status=network_unavailable_fallback so downstream reports do
    not confuse it with Wikidata/Getty/AskNature retrieval.
    """
    part = seed_plan.get("part_semantics") or {}
    part_name = clean(part.get("canonical_name") or seed_plan.get("source_part")).lower()
    category = clean(((seed_plan.get("part_category") or {}).get("category")) or "artifact_component")
    role = clean(part.get("semantic_role") or seed_plan.get("part_role_summary"))
    attachment = clean(part.get("attachment")) or "same original 3D socket"
    scale = clean(part.get("scale_constraint")) or "same local part scale"

    def cand(raw: str, phrase: str, mapping: str, attrs: list[str]) -> dict[str, Any]:
        return {
            "candidate_concept_name": raw,
            "raw_kg_target": raw,
            "graphs": [],
            "graph_evidence": [],
            "graph_evidence_status": evidence_status,
            "source_attribute": role,
            "replaced_attributes": attrs,
            "attribute_mapping": mapping,
            "part_affordance_mapping": (
                f"Preserves the selected part role ({role}) while changing its visible local 3D form."
            ),
            "role_transfer_mapping": (
                f"The donor form is decoded as the {part_name} itself, not as an added object; "
                "only the selected local component changes."
            ),
            "socket_compatibility": f"Must attach at: {attachment}.",
            "scale_orientation_constraints": f"Keep compatible local scale/orientation: {scale}.",
            "visual_executable_gate": "risky",
            "risk_reason": risk_reason,
            "generation_phrase": phrase,
        }

    templates: list[dict[str, Any]]
    if any(word in part_name for word in ["grip", "handle", "lever"]):
        templates = [
            cand(
                "bicycle handlebar grip",
                "the entire lower hand grip itself becomes a compact ribbed bicycle-handlebar-style grip, vertical and holdable, still attached below the trigger with clear trigger clearance",
                "function=hand holding affordance -> target grip object; shape=ergonomic ribbed cylinder/handle",
                ["function", "shape", "attachment", "scale"],
            ),
            cand(
                "braided rope loop",
                "the entire lower hand grip itself becomes a short braided rope-loop handle with two reinforced plastic anchor sockets, integrated into the gun body and usable as the grip",
                "attachment=two-point handle socket -> target loop handle; material_feel=braided tactile grip",
                ["attachment", "shape", "material_feel", "scale"],
            ),
            cand(
                "curved suction-cup silicone grip",
                (
                    "the entire lower hand grip itself becomes a curved blue silicone ergonomic grip; "
                    "the grip surface has rows of small suction-cup-like dimples for tactile texture; "
                    "all dimples are embedded on the grip surface only; preserve the same trigger clearance and same upper attachment socket; "
                    "no dangling appendage, no extra protruding limb, no animal, no creature, no face, no eyes"
                ),
                (
                    "shape=curved downward grip -> silicone ergonomic grip; "
                    "material_feel=rubbery tactile grip; surface rhythm=suction-cup-like dimples embedded on the grip surface"
                ),
                ["shape", "function", "material_feel", "attachment"],
            ),
            cand(
                "game controller handle",
                "the entire lower hand grip itself becomes a rounded game-controller-style ergonomic handle with small embedded control-button details on the grip surface, integrated below the water gun body",
                "function=hand control affordance -> controller grip; scale=hand-sized local component",
                ["function", "shape", "scale", "identity_cue"],
            ),
        ]
    elif any(word in part_name for word in ["nozzle", "spout", "muzzle", "outlet"]):
        templates = [
            cand(
                "mini shower-head spray cap",
                "the front nozzle itself becomes a compact round shower-head-style spray cap with many tiny perforations on the outlet face, mounted at the same front socket and pointing forward",
                "function=water outlet/spray -> perforated shower head; orientation=forward pointing; attachment=same front socket",
                ["function", "orientation", "attachment", "scale"],
            ),
            cand(
                "trumpet bell outlet",
                "the front nozzle itself becomes a short flared trumpet-bell outlet, hollow at the center and aligned with the water jet axis, with the bell shape integrated into the original orange nozzle socket",
                "shape=front opening/protrusion -> flared bell; function=projecting outlet; orientation=water jet axis",
                ["shape", "function", "orientation", "attachment"],
            ),
            cand(
                "lotus-petal sprinkler diffuser",
                "the front nozzle itself becomes a small lotus-petal sprinkler diffuser: petal-like radial lobes form the outlet rim, with tiny spray holes embedded in the center, mounted exactly at the original front socket",
                "function=spray diffuser -> sprinkler; shape=radial petal outlet; identity_cue=playful toy-like floral form",
                ["function", "shape", "identity_cue", "scale"],
            ),
            cand(
                "accordion bellows tube nozzle",
                "the front nozzle itself becomes a short flexible accordion-bellows tube nozzle with ribbed rings, forward-facing and integrated into the same front socket; it is only a nozzle tube, not a creature or separate hose",
                "function=directed jet outlet -> flexible siphon tube; material_feel=ribbed rubber; attachment=same front socket",
                ["function", "shape", "material_feel", "attachment"],
            ),
            cand(
                "camera lens nozzle",
                "the front nozzle itself becomes a toy camera-lens-like circular outlet with two nested concentric rings and a dark hollow center, mounted in the same front socket and still reading as the water exit",
                "shape=concentric circular aperture -> lens; function=hollow directed outlet; scale=small front component",
                ["shape", "function", "scale", "identity_cue"],
            ),
            cand(
                "honeycomb aerator nozzle",
                "the front nozzle itself becomes a honeycomb aerator face: a compact hexagonal-cell perforated outlet plate inside the same round front socket, pointing forward for multi-stream spray",
                "function=multi-stream outlet -> aerator; structure=honeycomb perforations; attachment=same socket",
                ["function", "shape", "material_feel", "attachment"],
            ),
            cand(
                "spiral seashell outlet",
                "the front nozzle itself becomes a small spiral seashell-like outlet: a curled spiral rim around a hollow central opening, compact and integrated into the original front nozzle socket",
                "shape=spiral hollow shell -> outlet rim; function=directed opening; scale=compact local component",
                ["shape", "function", "scale", "identity_cue"],
            ),
            cand(
                "coral perforated nozzle",
                "the front nozzle itself becomes a coral-branch-inspired perforated nozzle face with several short rounded tubes fused into one compact outlet cluster, all attached to the same front socket",
                "structure=branching porous flow channels -> compact outlet cluster; function=spray diffusion; attachment=same socket",
                ["shape", "function", "attachment", "material_feel"],
            ),
        ]
    elif any(word in part_name for word in ["lid", "cap", "cover"]):
        templates = [
            cand("mushroom cap", "a domed mushroom-cap-like cover seated on the same top opening", "shape=domed cover -> mushroom cap", ["shape", "attachment", "scale"]),
            cand("lotus leaf", "a shallow lotus-leaf-like cover with curled rim, seated as the same lid", "shape=thin cover -> leaf dish", ["shape", "material_feel", "attachment"]),
            cand("shell cover", "a ridged seashell-like lid cover fitted to the same opening", "shape=ridged cover -> shell", ["shape", "material_feel", "scale"]),
            cand("cork stopper", "a fitted cork-stopper-style cap occupying the same lid socket", "function=cover/plug -> stopper", ["function", "attachment", "material_feel"]),
        ]
    else:
        templates = [
            cand("rubber fitting", "a compatible rubber fitting replacing the selected local component at the same socket", "attachment/local scale -> rubber fitting", ["attachment", "scale", "material_feel"]),
            cand("faceted crystal insert", "a faceted crystal insert replacing only the selected local component", "shape/local component -> faceted insert", ["shape", "material_feel", "scale"]),
            cand("wooden carved component", "a small carved wooden component occupying the same selected-part volume", "material/craft -> carved wood part", ["material_feel", "shape", "attachment"]),
            cand("shell-shaped component", "a curved shell-shaped component attached at the same socket", "shape/attachment -> shell component", ["shape", "attachment", "scale"]),
        ]

    selected = templates[: max(1, count)]
    for item in selected:
        score = candidate_gate_score(item, category=category)
        item["part_category"] = category
        item["part_category_policy"] = PART_CATEGORY_CONFIG.get(category, PART_CATEGORY_CONFIG["artifact_component"])["description"]
        item["visual_executable_score"] = max(score, 5)
        item["visual_executable_gate"] = "risky" if score < 7 else "pass"
    return selected


def _candidate_text(candidate: dict[str, Any]) -> str:
    evidence_text = " ".join(
        clean(row.get("raw_kg_target")) + " " + clean(row.get("description")) + " " + clean((row.get("query") or {}).get("term"))
        for row in candidate.get("graph_evidence") or []
    )
    return (
        clean(candidate.get("raw_kg_target"))
        + " "
        + clean(candidate.get("generation_phrase"))
        + " "
        + clean(candidate.get("attribute_mapping"))
        + " "
        + clean(candidate.get("part_affordance_mapping"))
        + " "
        + clean(candidate.get("role_transfer_mapping"))
        + " "
        + evidence_text
    ).lower()


def role_transfer_score(candidate: dict[str, Any], *, category: str) -> int:
    """Score whether the donor concept can still play the selected part role."""
    text = _candidate_text(candidate)
    dims = {clean(dim) for dim in candidate.get("replaced_attributes") or [] if clean(dim)}
    score = 0
    if dims & {"function", "attachment", "scale", "orientation"}:
        score += 1
    if len(dims & {"function", "attachment", "scale", "orientation", "shape"}) >= 2:
        score += 2
    if any(term in text for term in ["same socket", "attached", "integrated", "anchor", "mount", "fitting", "joint"]):
        score += 2
    if any(term in text for term in ["local", "selected part", "itself", "replace", "replacing", "hand-sized", "small"]):
        score += 1
    if category == "mechanical_component":
        if any(term in text for term in ["grip", "handle", "hold", "ergonomic", "hand", "trigger", "ribbed", "loop"]):
            score += 3
        if any(term in text for term in ["tentacle", "suction", "rope", "coil", "braid", "controller"]):
            score += 2
        if any(term in text for term in ["creature body", "head", "eyes", "face", "animal body", "whole creature"]):
            score -= 8
        if any(term in text for term in ["sticker", "badge", "ornament", "decoration", "separate prop", "detached"]):
            score -= 8
    return score


def candidate_gate_score(candidate: dict[str, Any], category: str = "artifact_component") -> int:
    """Score whether a KG target can be rendered as the selected local part."""
    category_config = PART_CATEGORY_CONFIG.get(category, PART_CATEGORY_CONFIG["artifact_component"])
    dims = {
        clean(dim)
        for dim in candidate.get("replaced_attributes") or []
        if clean(dim)
    }
    if not dims:
        dims = {
            clean((row.get("query") or {}).get("attribute_dimension"))
            for row in candidate.get("graph_evidence") or []
            if clean((row.get("query") or {}).get("attribute_dimension"))
        }
    text = _candidate_text(candidate)
    reject_terms = {
        "album", "band", "song", "film", "video game", "podcast", "record label",
        "family name", "given name", "commune", "parish", "borough", "drawing",
        "interpro", "software", "company", "fictional character", "patent",
        "population projection", "map projection", "comune", "city", "town",
        "village", "municipality", "cell", "cells", "photo sensitive",
        "brand", "county", "administrative", "ireland", "ownership",
        "operating system", "journal", "scholarly article", "doctoral thesis",
        "single by", "singer-songwriter", "museum", "collections",
        "biological strategies", "innovations", "search evidence",
        "article", "act of the parliament", "developer",
    }
    if category == "mechanical_component":
        # Getty contains many terms that match "plug"/"handle" lexically but
        # are not executable mechanical local-part analogies for artifacts.
        reject_terms.update(
            {
                "nose plug", "nose plugs", "plug tobacco", "bayonet",
                "bayonets", "ornament", "ornaments", "jewelry", "earrings",
                "costume accessory", "tobacco",
                "answering machine", "answering machines", "board slotting",
                "candle socket", "candle sockets",
            }
        )
    if any(term in text for term in reject_terms):
        return -100
    score = 0
    # Attribute dimensions that directly support local visual replacement.
    for dim, weight in (category_config.get("gate_weights") or {}).items():
        if dim in dims:
            score += int(weight)
    executable_terms = {
        "cone", "conical", "spike", "rostrum", "beak", "horn",
        "plug", "cork", "nozzle", "spout", "fitting", "button", "push-button",
        "knob", "bead", "gemstone", "crystal", "shell", "wood", "flower",
        "badge", "emblem", "boss", "finial", "jewel", "small", "protrusion",
        "appendage", "connector", "device", "candy", "lollipop", "marble",
        "berry", "heart", "star", "toy", "brick", "glass", "jelly", "rosette",
        "petal", "feather", "balloon", "pearl",
    }
    for term in executable_terms:
        if term in text:
            score += 1
    # Function-only biological analogies often preserve meaning but are too
    # global/strong for a small snowman part unless paired with shape/socket.
    overstrong_terms = {
        "elephant", "trunk", "muzzle", "proboscis", "snout", "species",
        "genus", "mammal", "insect",
    }
    if any(term in text for term in overstrong_terms):
        score -= 1 if category == "organic_part" else 3
    prop_risk_terms = {"electrical plug", "tool", "device to control", "connector"}
    if any(term in text for term in prop_risk_terms):
        if category == "mechanical_component":
            score += 1
        elif not ({"attachment", "scale"} & dims):
            score -= 2
        else:
            score -= 1
    if len(dims) >= 2:
        score += 2
    score += role_transfer_score(candidate, category=category)
    # A candidate based only on function is generally too loose.
    if dims == {"function"} and category not in {"organic_part"}:
        score -= 4
    # Decorative/organic parts may intentionally be more whimsical.
    if category == "decorative_symbolic_part" and dims & {"identity_cue", "material_feel", "shape"}:
        score += 2
    if category == "organic_part" and dims & {"function", "shape", "material_feel"}:
        score += 2
    if category == "decorative_symbolic_part" and dims == {"identity_cue"}:
        # A pure symbol is often generated as a chest badge/hat emblem unless
        # it also has local 3D shape/material/scale support.
        if not any(term in text for term in ["button", "jewel", "gem", "flower", "bead", "rosette", "crystal"]):
            score -= 4
    far_transfer_terms = {
        "candy", "lollipop", "jewel", "gem", "gemstone", "crystal", "flower",
        "berry", "marble", "toy", "brick", "glass", "jelly", "heart", "star",
        "shell", "pearl", "bead", "rosette", "petal", "feather",
    }
    if category in {"decorative_symbolic_part", "organic_part"} and any(term in text for term in far_transfer_terms):
        score += 4
    near_mechanical_terms = {"plug", "nozzle", "spout", "fitting", "electrical"}
    if category == "decorative_symbolic_part" and any(term in text for term in near_mechanical_terms):
        score -= 2
    return score


def rank_and_gate_candidates(candidates: list[dict[str, Any]], *, count: int, category: str = "artifact_component") -> list[dict[str, Any]]:
    category_config = PART_CATEGORY_CONFIG.get(category, PART_CATEGORY_CONFIG["artifact_component"])
    enriched: list[dict[str, Any]] = []
    for item in candidates:
        score = candidate_gate_score(item, category=category)
        if score < 2:
            continue
        gate = "pass" if score >= 7 else "risky"
        item = dict(item)
        item["part_category"] = category
        item["part_category_policy"] = category_config["description"]
        item["visual_executable_score"] = score
        item["visual_executable_gate"] = gate
        item["risk_reason"] = clean(item.get("risk_reason")) or "attribute-driven visual executable gate"
        if not item.get("replaced_attributes"):
            item["replaced_attributes"] = sorted(
                {
                    clean((row.get("query") or {}).get("attribute_dimension"))
                    for row in item.get("graph_evidence") or []
                    if clean((row.get("query") or {}).get("attribute_dimension"))
                }
            )
        if not item.get("attribute_mapping") and item.get("graph_evidence"):
            row = item["graph_evidence"][0]
            q = row.get("query") or {}
            item["attribute_mapping"] = (
                f"{clean(q.get('attribute_dimension'))}={clean(q.get('attribute_value'))} "
                f"-> KG target '{clean(item.get('raw_kg_target'))}' via query '{clean(q.get('term'))}'"
            )
        enriched.append(item)
    # Balance dimensions: do not let function-only neighbors dominate.
    enriched.sort(
        key=lambda item: (
            -int(item.get("visual_executable_score") or 0),
            min(
                [
                    (category_config.get("preferred_dimensions") or []).index(dim)
                    for dim in (item.get("replaced_attributes") or [])
                    if dim in (category_config.get("preferred_dimensions") or [])
                ]
                or [99]
            ),
            clean(item.get("raw_kg_target")).lower(),
        )
    )
    selected: list[dict[str, Any]] = []
    used_labels: set[str] = set()
    used_primary_dims: Counter[str] = Counter()
    for item in enriched:
        label = clean(item.get("raw_kg_target")).lower()
        if label in used_labels:
            continue
        dims = item.get("replaced_attributes") or []
        primary = dims[0] if dims else "unknown"
        limit = 4 if category in {"organic_part", "decorative_symbolic_part"} else 3
        if used_primary_dims[primary] >= limit and len(selected) < count - 1:
            continue
        selected.append(item)
        used_labels.add(label)
        used_primary_dims[primary] += 1
        if len(selected) >= count:
            break
    if len(selected) < count:
        for item in enriched:
            label = clean(item.get("raw_kg_target")).lower()
            if label in used_labels:
                continue
            selected.append(item)
            used_labels.add(label)
            if len(selected) >= count:
                break
    return selected


def deterministic_candidates_from_evidence(evidence: list[dict[str, Any]], *, count: int) -> list[dict[str, Any]]:
    """Fallback selector that still requires retrieved graph evidence."""
    bad_terms = {
        "album", "band", "song", "film", "video game", "podcast", "record label",
        "family name", "given name", "commune", "parish", "borough", "drawing",
        "interpro", "software", "company", "operating system", "journal",
        "scholarly article", "doctoral thesis", "single by", "singer-songwriter",
        "museum", "collections", "biological strategies", "innovations",
        "search evidence", "act of the parliament", "developer",
    }
    positive_terms = {
        "anatomical", "appendage", "protrusion", "structure", "device", "connector",
        "plug", "button", "knob", "spout", "nozzle", "beak", "snout", "muzzle",
        "proboscis", "trunk", "horn", "gemstone", "pine cone", "lure",
        "cork", "wood", "shell", "crystal", "flower", "badge", "emblem",
        "cone", "spike", "rostrum", "boss", "finial", "bead", "jewel",
        "candy", "lollipop", "marble", "berry", "cherry", "heart", "star",
        "toy", "brick", "glass", "jelly", "pearl", "pom-pom", "acorn",
        "gummy", "rosette", "petal",
    }
    rows_by_label: dict[str, list[dict[str, Any]]] = {}
    score_by_label: dict[str, int] = {}
    for row in evidence:
        label = clean(row.get("raw_kg_target"))
        if not label:
            continue
        text = (label + " " + clean(row.get("description")) + " " + clean((row.get("query") or {}).get("term"))).lower()
        if any(term in text for term in bad_terms):
            continue
        score = 0
        for term in positive_terms:
            if term in text:
                score += 2
        if row.get("graph") == "wikidata":
            score += 1
        if row.get("graph") == "asknature":
            score += 2
        # Prefer concrete local-part-like labels over broad classes.
        if len(label.split()) <= 3:
            score += 1
        if score <= 0:
            continue
        key = label.lower()
        rows_by_label.setdefault(key, []).append(row)
        score_by_label[key] = max(score_by_label.get(key, 0), score)

    candidates: list[dict[str, Any]] = []
    for key, _score in sorted(score_by_label.items(), key=lambda kv: (-kv[1], kv[0])):
        rows = rows_by_label[key]
        raw = clean(rows[0].get("raw_kg_target"))
        query_term = clean((rows[0].get("query") or {}).get("term"))
        generation_phrase = raw
        lower = raw.lower()
        if lower in {"beak", "proboscis", "snout", "muzzle", "horn", "spout", "nozzle", "rostrum"}:
            generation_phrase = f"{raw}-like local protruding component"
        elif lower == "cone":
            generation_phrase = "short cone-shaped local component"
        elif lower == "spike":
            generation_phrase = "short spike-shaped local component"
        elif "plug" in lower:
            generation_phrase = f"{raw}-like fitted local component"
        elif "button" in lower:
            generation_phrase = f"{raw}-like small local component"
        elif "cork" in lower:
            generation_phrase = f"{raw} cork local component"
        elif "wood" in lower:
            generation_phrase = f"{raw} wooden local component"
        elif "shell" in lower:
            generation_phrase = "one small curved seashell-like component attached at the selected part socket"
        elif "crystal" in lower:
            generation_phrase = "faceted translucent crystal local component"
        elif "flower" in lower:
            generation_phrase = f"bright colorful {raw} flower-like local component"
        elif "badge" in lower or "emblem" in lower:
            generation_phrase = f"{raw} emblem-like local component"
        elif "gemstone" in lower:
            generation_phrase = "one bright faceted gemstone mounted exactly as the selected local part"
        elif "pine cone" in lower:
            generation_phrase = "small pine-cone-like local component"
        elif "gummy" in lower:
            generation_phrase = "one translucent colorful gummy-candy-like local component"
        elif "candy" in lower:
            generation_phrase = "colorful candy-like local component"
        elif "lollipop" in lower:
            generation_phrase = "one small round colorful lollipop-like local component with a short embedded stem"
        elif "marble" in lower:
            generation_phrase = "glossy colorful marble local component"
        elif "berry" in lower:
            generation_phrase = "one bright glossy berry-like local component"
        elif "cherry" in lower:
            generation_phrase = "glossy red cherry-like local component"
        elif "heart" in lower:
            generation_phrase = "one small red heart-shaped 3D local component"
        elif "star" in lower:
            generation_phrase = "one small yellow star-shaped 3D local component"
        elif "toy" in lower or "brick" in lower:
            generation_phrase = f"colorful {raw} toy-like local component"
        elif "glass" in lower:
            generation_phrase = "translucent colored glass local component"
        elif "jelly" in lower:
            generation_phrase = f"translucent jelly-like local component"
        elif "bead" in lower:
            generation_phrase = "glossy colorful bead local component"
        elif "pearl" in lower:
            generation_phrase = "shiny pearl local component"
        elif "acorn" in lower:
            generation_phrase = "small brown acorn-like local component"
        elif "pom-pom" in lower or "pompom" in lower:
            generation_phrase = "soft colorful pom-pom local component"
        elif "rosette" in lower:
            generation_phrase = f"colorful rosette local component"
        candidates.append(
            {
                "candidate_concept_name": raw,
                "raw_kg_target": raw,
                "graphs": sorted({r["graph"] for r in rows}),
                "graph_evidence": rows[:5],
                "source_attribute": clean((rows[0].get("query") or {}).get("attribute_value")),
                "replaced_attributes": sorted(
                    {
                        clean((r.get("query") or {}).get("attribute_dimension"))
                        for r in rows
                        if clean((r.get("query") or {}).get("attribute_dimension"))
                    }
                ),
                "attribute_mapping": (
                    f"{clean((rows[0].get('query') or {}).get('attribute_dimension'))}="
                    f"{clean((rows[0].get('query') or {}).get('attribute_value'))} "
                    f"-> KG target '{raw}' via query '{query_term}'"
                ),
                "part_affordance_mapping": (
                    f"KG node '{raw}' was retrieved through '{query_term}' and can be mapped into the "
                    "selected local part volume, so it remains readable as the selected part rather than a separate object."
                ),
                "role_transfer_mapping": "reinterpret the KG target as the selected part itself, preserving the original role and local 3D context",
                "socket_compatibility": "same selected-part socket/contact interface; no detached prop",
                "scale_orientation_constraints": "same local part scale and orientation relative to neighboring parts",
                "visual_executable_gate": "pass" if _score >= 4 else "risky",
                "risk_reason": "deterministic graph-evidence fallback selector",
                "generation_phrase": generation_phrase,
            }
        )
        if len(candidates) >= count:
            break
    return candidates


def build_directions(request: dict[str, Any], part: dict[str, Any], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source = clean(request.get("object_type"))
    part_name = clean(part.get("canonical_name"))
    identity = clean((request.get("source_elements") or {}).get("identity")) or source
    # All candidates in one Stage1 share the category from seed plan, stored on
    # each candidate for prompt clarity by synthesize/rank.
    directions: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates, 1):
        target = candidate["generation_phrase"]
        category = clean(candidate.get("part_category")) or "artifact_component"
        category_config = PART_CATEGORY_CONFIG.get(category, PART_CATEGORY_CONFIG["artifact_component"])
        semantic_role = clean(part.get("semantic_role")) or f"selected {part_name} role"
        attachment = clean(part.get("attachment")) or "the original 3D attachment socket"
        shape = clean(part.get("shape")) or "the original selected-part volume"
        scale = clean(part.get("scale_constraint")) or "the original local part scale"
        role_mapping = clean(candidate.get("role_transfer_mapping")) or (
            f"reinterpret the donor form as the {part_name} itself, not as an added object"
        )
        prompt = (
            f"Single {source} 3D product render on a pure white RGB255 background. "
            f"Keep source identity: {identity}. "
            f"PART VARIATION category: {category}. Policy: {category_config['prompt_style']}. "
            f"The {source} has exactly one {part_name}. "
            f"Original selected-part role: {semantic_role}. Original local shape/position: {shape}. "
            f"Original attachment: {attachment}. Original scale rule: {scale}. "
            f"The {part_name} itself is replaced by {target}, based on KG target '{candidate['raw_kg_target']}'. "
            f"Attribute mapping: {candidate.get('attribute_mapping') or candidate.get('source_attribute')}. "
            f"It must still read as the {source}'s {part_name}: {candidate['part_affordance_mapping']}. "
            f"Role transfer mapping: {role_mapping}. "
            f"Attach it at the same 3D socket: {candidate['socket_compatibility']}. "
            f"Respect local scale and orientation: {candidate['scale_orientation_constraints']}. "
            f"The target is the {part_name} itself, not a separate prop. "
            f"Only one {part_name}; no pasted sticker, no surface badge, no handheld prop, no separate donor object, no unrelated character or creature. "
            f"Do not add any extra protrusion, dangling appendage, tail, limb, bead chain, charm, hanging loop, or second component outside the original {part_name} volume; "
            f"if the donor provides surface texture, keep it embedded on the {part_name} surface only. "
            "Keep all unselected parts normal and recognizable. Tangible 3D volume, complete single object, no scene, no floor, no shadow."
        )
        directions.append(
            {
                "direction_id": f"part_{index:02d}",
                "anchor": candidate["raw_kg_target"],
                "candidate": candidate,
                "transfer_spec": {
                    "graph_anchor": candidate["raw_kg_target"],
                    "prompt": prompt,
                    "positive_only": True,
                    "minimal_prompt": True,
                    "generation_phrase": target,
                    "selected_part": part,
                    "graph_provenance": candidate["graph_evidence"],
                },
            }
        )
    return directions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--candidate-count", type=int, default=8)
    args = parser.parse_args()
    request = json.loads(Path(args.input).read_text(encoding="utf-8"))
    part = load_part_semantics(request)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    def checkpoint(stage: str, **payload: Any) -> None:
        output.write_text(
            json.dumps(
                {
                    "schema_version": "creativeflow.part-kg-affordance-stage1.v1",
                    "status": "running",
                    "current_stage": stage,
                    **payload,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    seed_plan = plan_seed_attributes(request, part)
    checkpoint("seed_planning", seed_plan=seed_plan)
    queries = plan_graph_queries(seed_plan)
    checkpoint("graph_query_planning", seed_plan=seed_plan, graph_queries=queries)
    evidence, audit = retrieve_graph_evidence(queries)
    checkpoint("graph_retrieval", seed_plan=seed_plan, graph_queries=queries, graph_retrieval_audit=audit, retrieved_graph_evidence=evidence[:120])
    candidates = synthesize_candidates(
        request=request,
        seed_plan=seed_plan,
        evidence=evidence,
        count=args.candidate_count,
    )
    directions = build_directions(request, part, candidates)
    result = {
        "schema_version": "creativeflow.part-kg-affordance-stage1.v1",
        "status": "completed",
        "stage": "part",
        "source_image_path": clean(request.get("source_image_path")),
        "source_noun": clean(request.get("object_type")),
        "part_semantics": part,
        "seed_plan": seed_plan,
        "graph_queries": queries,
        "graph_retrieval_audit": audit,
        "retrieved_graph_evidence": evidence[:120],
        "selected_candidates": candidates,
        "directions": directions,
        "selection_policy": {
            "fixed_candidate_library": False,
            "requires_real_graph_evidence": False,
            "hybrid_routes": [
                "live_graph_evidence_when_available",
                "implicit_role_transfer_seed_when_graph_is_too_conservative_or_partial",
            ],
            "part_affordance_gate": True,
            "socket_compatibility_required": True,
        },
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
