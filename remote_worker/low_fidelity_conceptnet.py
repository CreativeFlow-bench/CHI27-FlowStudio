#!/usr/bin/env python3
"""Runtime ConceptNet evidence for Low Fidelity silhouette transfer.

This module keeps the low-fidelity path intentionally simple:

source image + source noun -> VLM contour seed terms -> ConceptNet neighbors ->
short graph evidence labels for the two-stage prompt planner.

It does not score, validate, mask, composite, or generate images.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import base64
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import quote


CONTOUR_SEED_SYSTEM = """
You are the first planner in a CreativeFlow low-fidelity silhouette transfer
pipeline. Your only job is to describe the source object's identity cues and
extract generic silhouette seed attributes that can be expanded through a
ConceptNet-style graph.

The generation goal downstream is: keep the source object recognizable, but
change only the overall outer contour, massing, proportion, and shape rhythm.
Do not propose final target objects. Return JSON only.
""".strip()


CONTOUR_SEED_PROMPT = """
Source object:
{source}

Optional source description:
{description}

Look at the attached image if available. Return:
1. source_identity: the concrete object noun.
2. identity_cues_to_preserve: category-defining visible elements that should
   remain recognizable after silhouette transfer.
3. current_contour_description: one concise description of the current outer
   silhouette, massing, proportion, and rhythm.
4. contour_seed_terms: 5 to 8 short English graph query terms that describe
   the source object's CURRENT visible silhouette attributes. These are source
   evidence terms, not desired target axes and not final target objects.
   Use only attributes that are actually supported by the source description
   or image, such as squat, rounded, broad, compact, elongated, blocky,
   segmented, domed, tapered, cylindrical, etc. Do not include "columnar",
   "conical", "crescent", "disciform", or other target-like words unless the
   source itself is already visibly close to that attribute.
   Do not include the source noun or source accessories.

Return JSON only:
{{
  "source_identity": "...",
  "identity_cues_to_preserve": ["..."],
  "current_contour_description": "...",
  "contour_seed_terms": ["..."]
}}
""".strip()


USEFUL_RELATIONS = {
    "RelatedTo",
    "SimilarTo",
    "IsA",
    "HasProperty",
    "FormOf",
    "DerivedFrom",
    "Synonym",
    "MannerOf",
}

BLOCKED_LABEL_BITS = {
    "background",
    "cartoon",
    "christmas",
    "color",
    "film",
    "game",
    "altitude",
    "another word",
    "bass",
    "car",
    "hearted",
    "key",
    "level",
    "music",
    "person",
    "piano",
    "pitched",
    "scene",
    "sir david",
    "snow",
    "snowman",
    "song",
    "texture",
    "winter",
    "breast",
}

BLOCKED_SEED_TERMS = {
    "contour",
    "form",
    "identity",
    "massing",
    "object",
    "outline",
    "rhythm",
    "shape",
    "silhouette",
}

SHAPE_SEED_HINTS = {
    "angular",
    "asymmetric",
    "barrel",
    "block",
    "blocky",
    "broad",
    "bulb",
    "bulbous",
    "column",
    "columnar",
    "compact",
    "conic",
    "conical",
    "cube",
    "cubic",
    "cylinder",
    "cylindrical",
    "dome",
    "dome-like",
    "elongated",
    "flat",
    "lobed",
    "narrow",
    "oval",
    "pillar",
    "pyramid",
    "pyramidal",
    "rectangle",
    "rectangular",
    "round",
    "rounded",
    "spherical",
    "squat",
    "stacked",
    "segmented",
    "tall",
    "tapered",
    "upright",
    "vertical",
    "wide",
}

SHAPE_LABEL_HINTS = SHAPE_SEED_HINTS | {
    "almond",
    "aspherical",
    "bean",
    "bowfront",
    "crescent",
    "cycloidal",
    "cylindric",
    "disciform",
    "doughnut",
    "ellipsoid",
    "ellipsoidal",
    "hyperboloid",
    "hyperboloidal",
    "olive",
    "oval",
    "parabolic",
    "paraboloid",
    "paraboloidal",
}


def _image_data_url(path: str) -> str:
    suffix = Path(path).suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/webp" if suffix == ".webp" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(Path(path).read_bytes()).decode("ascii")


def call_runtime_json(
    system_prompt: str,
    user_prompt: str,
    *,
    image_paths: list[str] | None = None,
    max_tokens: int = 1536,
) -> dict[str, Any] | None:
    api_base = os.getenv("CF_TEXT_LLM_API_BASE", "http://127.0.0.1:18084/v1").rstrip("/")
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
        start = text.find("{")
        if start < 0:
            raise ValueError("runtime response contains no JSON object")
        decoded, _ = json.JSONDecoder().raw_decode(text[start:])
        return decoded if isinstance(decoded, dict) else None
    except urllib.error.HTTPError as exc:
        if os.getenv("CF_DEBUG_LOW_FIDELITY", "").lower() in {"1", "true", "yes"}:
            detail = exc.read().decode("utf-8", errors="replace")
            print(f"[low_fidelity] runtime_json_http_error: {exc.code} {detail}")
        return None
    except Exception as exc:
        if os.getenv("CF_DEBUG_LOW_FIDELITY", "").lower() in {"1", "true", "yes"}:
            print(f"[low_fidelity] runtime_json_error: {exc}")
        return None


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.lower().replace("-", "_")).strip("_")


def _term_tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z][a-z0-9-]*", value.lower()))


def _is_shape_seed(term: str, source: str) -> bool:
    low = term.lower().strip()
    if not low or low == source.lower():
        return False
    tokens = _term_tokens(low)
    source_tokens = _term_tokens(source)
    if tokens & source_tokens:
        return False
    if low in BLOCKED_SEED_TERMS or tokens <= BLOCKED_SEED_TERMS:
        return False
    if len(tokens) > 2:
        return False
    return bool(tokens & SHAPE_SEED_HINTS or low.endswith(("shaped", "form", "like")))


def _is_english_node(node: dict[str, Any]) -> bool:
    language = node.get("language")
    term = str(node.get("@id") or "")
    return language == "en" or term.startswith("/c/en/")


def _label_from_node(node: dict[str, Any]) -> str:
    label = _clean(node.get("label"))
    if label:
        return label
    term = str(node.get("term") or node.get("@id") or "")
    if term.startswith("/c/en/"):
        return term.split("/")[3].replace("_", " ")
    return ""


def _looks_useful(label: str, source: str) -> bool:
    low = label.lower()
    if not low or low == source.lower():
        return False
    if len(low) < 3 or len(low) > 42:
        return False
    if any(bit in low for bit in BLOCKED_LABEL_BITS):
        return False
    if re.search(r"\b(to|be|do|have|make|use)\b", low):
        return False
    return bool(re.search(r"[a-z]", low))


def _has_shape_label_value(label: str) -> bool:
    low = label.lower()
    tokens = _term_tokens(low)
    return (
        low.endswith(("shaped", "like", "form"))
        or bool(tokens & SHAPE_LABEL_HINTS)
        or any(hint in low for hint in ("shaped", "spherical", "cylind", "conic", "dome", "disc", "oval"))
    )


def _fetch_url(url: str, *, proxy: str, timeout: int) -> bytes:
    cmd = ["curl", "-L", "-sS", "--max-time", str(timeout)]
    if proxy:
        if proxy.startswith("socks5://") or proxy.startswith("socks5h://"):
            cmd += ["--socks5-hostname", proxy.split("://", 1)[1]]
        else:
            cmd += ["--proxy", proxy]
    cmd.append(url)
    with tempfile.NamedTemporaryFile("w+b", delete=False) as handle:
        tmp_path = Path(handle.name)
    try:
        result = subprocess.run(cmd, stdout=tmp_path.open("wb"), stderr=subprocess.PIPE, check=False)
        if result.returncode != 0:
            return b""
        return tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)


def extract_contour_seed_terms(
    *,
    source: str,
    source_description: str,
    source_image_path: str,
) -> dict[str, Any]:
    payload = call_runtime_json(
        CONTOUR_SEED_SYSTEM,
        CONTOUR_SEED_PROMPT.format(source=source, description=source_description or "None supplied"),
        image_paths=[source_image_path] if source_image_path else None,
        max_tokens=1536,
    )
    if not isinstance(payload, dict):
        payload = {}
    terms = [_clean(item).lower() for item in payload.get("contour_seed_terms") or []]
    terms = [item for item in terms if _is_shape_seed(item, source)]
    description_terms = [
        token
        for token in re.findall(r"[a-z][a-z0-9-]*", source_description.lower())
        if token in SHAPE_SEED_HINTS and token not in terms
    ]
    terms.extend(description_terms)
    text = f"{source} {source_description}".lower()
    if any(word in text for word in ["armchair", "chair", "seat", "backrest"]):
        terms.extend(["broad", "squat", "rounded", "blocky"])
    if any(word in text for word in ["sneaker", "shoe", "sole", "toe", "heel"]):
        terms.extend(["elongated", "rounded", "tapered", "compact"])
    if any(word in text for word in ["robot", "toy", "torso", "limbs"]):
        terms.extend(["compact", "blocky", "segmented", "rounded"])
    if not terms:
        terms = ["rounded", "compact", "stacked", "bulbous", "upright", "tapered"]
    payload["contour_seed_terms"] = list(dict.fromkeys(terms))[:10]
    return payload


def fetch_conceptnet_neighbors(
    term: str,
    *,
    source: str,
    proxy: str = "",
    limit: int = 20,
    timeout: int = 20,
) -> list[dict[str, str]]:
    url = f"https://api.conceptnet.io/c/en/{quote(_slug(term))}?offset=0&limit={limit}"
    body = _fetch_url(url, proxy=proxy, timeout=timeout)
    rows: list[dict[str, str]] = []
    seen_labels: set[str] = set()
    try:
        data = json.loads(body.decode("utf-8"))
    except Exception:
        data = None

    if isinstance(data, dict):
        for edge in data.get("edges") or []:
            if not isinstance(edge, dict):
                continue
            rel = _clean((edge.get("rel") or {}).get("label"))
            if rel and rel not in USEFUL_RELATIONS:
                continue
            start = edge.get("start") or {}
            end = edge.get("end") or {}
            if not _is_english_node(start) or not _is_english_node(end):
                continue
            labels = [_label_from_node(start), _label_from_node(end)]
            for label in labels:
                label = _clean(label)
                if label.lower() == term.lower():
                    continue
                if not _looks_useful(label, source):
                    continue
                if not _has_shape_label_value(label):
                    continue
                if label.lower() in seen_labels:
                    continue
                seen_labels.add(label.lower())
                rows.append({"seed": term, "relation": rel or "RelatedTo", "label": label})
    if rows:
        return rows

    # ConceptNet's JSON API is sometimes unavailable while the public concept
    # pages still render. Use linked English nodes as a graph-neighborhood
    # fallback, preserving the seed that produced each neighbor.
    html_url = f"https://conceptnet.io/c/en/{quote(_slug(term))}"
    html = _fetch_url(html_url, proxy=proxy, timeout=timeout).decode("utf-8", errors="ignore")
    for path in re.findall(r"/c/en/[A-Za-z0-9_/-]+", html):
        bits = [bit for bit in path.split("/") if bit]
        if len(bits) < 3 or bits[0] != "c" or bits[1] != "en":
            continue
        label = bits[2].replace("_", " ")
        if label.lower() == term.lower():
            continue
        if not _looks_useful(label, source):
            continue
        if not _has_shape_label_value(label):
            continue
        if label.lower() in seen_labels:
            continue
        seen_labels.add(label.lower())
        rows.append({"seed": term, "relation": "ConceptNetPageLink", "label": label})
    return rows


def conceptnet_silhouette_evidence(
    *,
    source: str,
    source_description: str,
    source_image_path: str,
    count: int = 12,
) -> dict[str, Any]:
    seed_payload = extract_contour_seed_terms(
        source=source,
        source_description=source_description,
        source_image_path=source_image_path,
    )
    proxy = os.getenv("CF_CONCEPTNET_PROXY", "").strip()
    seen: set[str] = set()
    evidence: list[str] = []
    rows: list[dict[str, str]] = []
    rows_by_seed: list[list[dict[str, str]]] = []
    for term in seed_payload.get("contour_seed_terms") or []:
        seed_rows = fetch_conceptnet_neighbors(term, source=source, proxy=proxy)
        if seed_rows:
            rows_by_seed.append(seed_rows)

    cursor = 0
    while len(evidence) < count and rows_by_seed:
        progressed = False
        for seed_rows in rows_by_seed:
            if cursor >= len(seed_rows):
                continue
            progressed = True
            row = seed_rows[cursor]
            key = row["label"].lower()
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
            evidence.append(row["label"])
            if len(evidence) >= count:
                break
        if not progressed:
            break
        cursor += 1
    return {
        "seed_planner": seed_payload,
        "conceptnet_proxy": proxy or None,
        "conceptnet_rows": rows,
        "conceptnet_silhouette_evidence": evidence[:count],
    }
