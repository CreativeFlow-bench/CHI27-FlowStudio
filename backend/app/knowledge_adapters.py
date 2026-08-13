"""Shared knowledge-source adapters for contextual divergence fragments.

Wikidata (grounding + first-hop), Getty AAT and AskNature (second-hop).
All HTTP traffic honors the process proxy env (http_proxy/https_proxy) so the
server-side DatabaseMart jump keeps working. Results are cached under
backend/storage/kb_cache so a blocked source degrades to cached real nodes
instead of fabricating terms.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any


KB_CACHE_ROOT = Path(__file__).resolve().parents[3] / "storage" / "kb_cache"
HTTP_TIMEOUT = 14.0
GETTY_HTTP_TIMEOUT = 5.0

WIKIDATA_SEARCH_URL = "https://www.wikidata.org/w/api.php"
WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
GETTY_SPARQL_URL = "https://vocab.getty.edu/sparql"
ASKNATURE_SEARCH_URL = "https://asknature.org/"

GENERIC_LABEL_DENYLIST = {
    "object",
    "thing",
    "design",
    "structure",
    "artwork",
    "work",
    "unit",
    "element",
    "feature",
    "part",
    "component",
    "material",
    "surface",
    "form",
    "shape",
    "concept",
}

BAD_INSTANCE_OF = {
    "Q11424",  # film
    "Q4829941",  # television program
    "Q7397",  # software
    "Q5",  # human
    "Q4167410",  # disambiguation page
    "Q3305213",  # painting
    "Q3977452",  # artwork (vague)
}

BAD_DESCRIPTION_TERMS = (
    "duo",
    "band",
    "album",
    "song",
    "single",
    "family name",
    "surname",
    "given name",
    "software",
    "website",
    "generator",
    "film",
    "television",
    "musical",
    "disambiguation",
    "static site",
    "record label",
    "fictional character",
)


def _proxy_config() -> dict[str, str]:
    proxies: dict[str, str] = {}
    for env_key in ("https_proxy", "http_proxy", "HTTPS_PROXY", "HTTP_PROXY"):
        value = urllib.request.getproxies().get(env_key.lower()) or ""
        if value:
            scheme = "https" if "https" in env_key.lower() else "http"
            proxies[scheme] = value
    if not proxies:
        # Fall back to repo .env proxy config (server deployment sets
        # http_proxy/https_proxy/CF_KG_PROXY there, not in process env).
        for env_path in (
            Path(__file__).resolve().parents[3] / ".env",
            Path(__file__).resolve().parents[4] / ".env",
        ):
            if not env_path.exists():
                continue
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip().lower()
                value = value.strip().strip('"').strip("'")
                if key in {"http_proxy", "https_proxy", "cf_kg_proxy"} and value:
                    scheme = "https" if "https" in key else "http"
                    if scheme not in proxies:
                        proxies[scheme] = value
            if proxies:
                break
    return proxies


def _opener() -> urllib.request.OpenerDirector:
    proxies = _proxy_config()
    if proxies:
        return urllib.request.build_opener(urllib.request.ProxyHandler(proxies))
    return urllib.request.build_opener()


def _http_json(url: str, *, cache_key: str | None = None, headers: dict[str, str] | None = None) -> dict[str, Any]:
    cache_path = None
    if cache_key:
        digest = hashlib.sha1(cache_key.encode("utf-8")).hexdigest()[:24]
        cache_path = KB_CACHE_ROOT / cache_key.split(":")[0] / f"{digest}.json"
        if cache_path.exists():
            try:
                return json.loads(cache_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "FlowStudioContextualDivergence/1.0 (research prototype)",
            "Accept": "application/json, application/sparql-results+json, text/html",
            **(headers or {}),
        },
    )
    opener = _opener()
    try:
        timeout = GETTY_HTTP_TIMEOUT if "vocab.getty.edu" in url else HTTP_TIMEOUT
        with opener.open(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", "replace")
    except Exception as exc:
        raise RuntimeError(f"kb_http_failed: {exc}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError("kb_http_not_json") from None
    if cache_path is not None:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return payload


def _cache_file(kind: str, key: str) -> Path:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:24]
    return KB_CACHE_ROOT / kind / f"{digest}.json"


def _read_cache(kind: str, key: str) -> dict[str, Any] | None:
    path = _cache_file(kind, key)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _write_cache(kind: str, key: str, payload: dict[str, Any]) -> None:
    try:
        path = _cache_file(kind, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def ground_wikidata(
    label_en: str,
    *,
    parent_label: str | None = None,
    semantic_role: str | None = None,
) -> dict[str, Any] | None:
    """Resolve a label to a Wikidata item id with conservative disambiguation."""
    if not label_en:
        return None
    search = " ".join(part for part in [label_en, parent_label, semantic_role] if part)
    cache_key = f"grounding:v2:{search.lower()}"
    cached = _read_cache("wikidata_grounding", cache_key)
    if cached:
        return cached.get("entity")
    url = (
        WIKIDATA_SEARCH_URL
        + "?"
        + urllib.parse.urlencode(
            {
                "action": "wbsearchentities",
                "search": search,
                "language": "en",
                "format": "json",
                "limit": 6,
            }
        )
    )
    payload = _http_json(url, cache_key=cache_key)
    candidates = payload.get("search") or []
    selected: dict[str, Any] | None = None
    for candidate in candidates:
        qid = str(candidate.get("id") or "")
        if not re.fullmatch(r"Q\d+", qid):
            continue
        label = str(candidate.get("label") or "")
        description = str(candidate.get("description") or "")
        if label.lower() in GENERIC_LABEL_DENYLIST:
            continue
        lowered_description = description.lower()
        if any(term in lowered_description for term in BAD_DESCRIPTION_TERMS):
            continue
        record = {
            "graph": "wikidata",
            "id": qid,
            "label": label,
            "description": description,
            "url": f"https://www.wikidata.org/wiki/{qid}",
            "aliases": candidate.get("aliases") or [],
        }
        if label.lower() == label_en.strip().lower():
            selected = record
            break
        if selected is None:
            selected = record
    # Prefer exact-label match even if it appeared after other candidates.
    if selected is None:
        for candidate in candidates:
            label = str(candidate.get("label") or "")
            if label.lower() == label_en.strip().lower() and re.fullmatch(r"Q\d+", str(candidate.get("id") or "")):
                description = str(candidate.get("description") or "").lower()
                if not any(term in description for term in BAD_DESCRIPTION_TERMS):
                    selected = {
                        "graph": "wikidata",
                        "id": str(candidate["id"]),
                        "label": label,
                        "description": str(candidate.get("description") or ""),
                        "url": f"https://www.wikidata.org/wiki/{candidate['id']}",
                        "aliases": candidate.get("aliases") or [],
                    }
                    break
    _write_cache("wikidata_grounding", cache_key, {"entity": selected})
    return selected


def _is_bad_entity(label: str, instance_of: list[str]) -> bool:
    if label.lower() in GENERIC_LABEL_DENYLIST:
        return True
    if any(item in BAD_INSTANCE_OF for item in instance_of):
        return True
    return False


def wikidata_first_hop(qid: str, relations: list[str], limit: int = 8) -> list[dict[str, Any]]:
    """First-hop neighbors filtered to allowed relation families."""
    if not relations:
        return []
    cache_key = f"first-hop:{qid}:{','.join(sorted(relations))}"
    cached = _read_cache("wikidata_first_hop", cache_key)
    if cached:
        return cached.get("neighbors") or []
    prop_values = " ".join(f"wdt:{prop}" for prop in relations)
    query = f"""
SELECT ?neighbor ?neighborLabel ?prop WHERE {{
  VALUES ?prop {{ {prop_values} }}
  wd:{qid} ?prop ?neighbor .
  ?neighbor rdfs:label ?neighborLabel .
  FILTER(LANG(?neighborLabel) = "en")
}} LIMIT {int(limit) * 6}
""".strip()
    url = WIKIDATA_SPARQL_URL + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
    payload = _http_json(url, cache_key=cache_key)
    neighbors: dict[str, dict[str, Any]] = {}
    for row in (payload.get("results") or {}).get("bindings") or []:
        neighbor_uri = str((row.get("neighbor") or {}).get("value") or "")
        label = str((row.get("neighborLabel") or {}).get("value") or "")
        prop = str((row.get("prop") or {}).get("value") or "").rsplit("/", 1)[-1]
        qid_neighbor = neighbor_uri.rsplit("/", 1)[-1]
        if not re.fullmatch(r"Q\d+", qid_neighbor):
            continue
        if _is_bad_entity(label, []):
            continue
        existing = neighbors.get(qid_neighbor)
        if existing is None:
            neighbors[qid_neighbor] = {
                "graph": "wikidata",
                "id": qid_neighbor,
                "label": label,
                "relation": prop,
                "relation_family": _family_for_prop(prop),
                "url": f"https://www.wikidata.org/wiki/{qid_neighbor}",
            }
    result = list(neighbors.values())[: limit]
    _write_cache("wikidata_first_hop", cache_key, {"neighbors": result})
    return result


def _family_for_prop(prop: str) -> str:
    for family, props in [
        ("type_instance", ["P31", "P279"]),
        ("part_of_has_part", ["P527", "P361"]),
        ("material", ["P186"]),
        ("shape_characteristic", ["P2386", "P2067"]),
        ("use_function", ["P366"]),
        ("mechanism_bridge", ["P366", "P1542"]),
    ]:
        if prop in props:
            return family
    return "unknown"


def getty_aat_search(term: str, limit: int = 5) -> list[dict[str, Any]]:
    """Getty AAT second-hop. Live SPARQL may be blocked on some networks; the
    local cache holds real AAT records so cached terms still resolve."""
    cache_key = f"getty:{term.lower()}"
    cached = _read_cache("getty_aat", cache_key)
    if cached:
        return cached.get("records") or []
    search_text = re.sub(r"\s+", " ", term.lower()).strip()
    search_text = re.findall(r"[a-z0-9]+", search_text)[0] if len(re.findall(r"[a-z0-9]+", search_text)) > 1 else search_text
    query = f"""
PREFIX gvp: <http://vocab.getty.edu/ontology#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX xl: <http://www.w3.org/2008/05/skos-xl#>
PREFIX aat: <http://vocab.getty.edu/aat/>
SELECT ?s ?label WHERE {{
  ?s a gvp:Concept ;
     skos:inScheme aat: ;
     gvp:prefLabelGVP/xl:literalForm ?label .
  FILTER(langMatches(lang(?label), "en"))
  FILTER(CONTAINS(LCASE(STR(?label)), "{search_text}"))
}} LIMIT {max(1, min(20, int(limit) * 4))}
""".strip()
    url = GETTY_SPARQL_URL + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
    try:
        payload = _http_json(url, cache_key=f"getty_live:{term.lower()}")
    except RuntimeError:
        payload = {}
    records: list[dict[str, Any]] = []
    for row in (payload.get("results") or {}).get("bindings") or []:
        uri = str((row.get("s") or {}).get("value") or "")
        label = str((row.get("label") or {}).get("value") or "")
        if "/aat/" not in uri or not label:
            continue
        aat_id = uri.rsplit("/", 1)[-1]
        if not re.fullmatch(r"\d+", aat_id):
            continue
        records.append(
            {
                "graph": "getty_aat",
                "id": aat_id,
                "label": label,
                "url": f"http://vocab.getty.edu/aat/{aat_id}",
                "broader": None,
            }
        )
        if len(records) >= limit:
            break
    if records:
        _write_cache("getty_aat", cache_key, {"records": records})
    if records:
        return records
    # Cached-label fallback: match the queried term against cached AAT record
    # labels (both directions) so a blocked live Getty still yields real nodes.
    fallback: list[dict[str, Any]] = []
    cache_dir = KB_CACHE_ROOT / "getty_aat"
    if cache_dir.exists():
        lowered_term = term.lower()
        needles = {lowered_term}
        for width in range(4, min(len(lowered_term), 10)):
            needles.add(lowered_term[:width])
        for path in cache_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            for record in payload.get("records") or []:
                label = str(record.get("label") or "").lower()
                if not label:
                    continue
                if any(needle in label for needle in needles):
                    fallback.append(record)
                    if len(fallback) >= limit:
                        break
            if len(fallback) >= limit:
                break
    if fallback:
        _write_cache("getty_aat", cache_key, {"records": fallback})
    return fallback


def asknature_search(term: str, limit: int = 5) -> list[dict[str, Any]]:
    """AskNature second-hop: strategy/innovation pages with function hints."""
    cache_key = f"asknature:{term.lower()}"
    cached = _read_cache("asknature", cache_key)
    if cached:
        return cached.get("records") or []
    url = ASKNATURE_SEARCH_URL + "?" + urllib.parse.urlencode({"s": term})
    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (research prototype)"},
        )
        with _opener().open(request, timeout=HTTP_TIMEOUT) as response:
            html = response.read().decode("utf-8", "replace")
    except Exception as exc:
        raise RuntimeError(f"asknature_http_failed: {exc}") from exc
    links = re.findall(r"https://asknature\.org/(?:strategy|innovation)/[^\"'<>\s]+", html)
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for link in links:
        clean = link.split("?")[0]
        if clean in seen:
            continue
        seen.add(clean)
        slug = clean.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")
        records.append(
            {
                "graph": "asknature",
                "id": clean,
                "label": slug.title(),
                "url": clean,
                "function": term,
                "mechanism": slug,
            }
        )
        if len(records) >= limit:
            break
    if records:
        _write_cache("asknature", cache_key, {"records": records})
    return records


def second_hop_parallel(term: str, limit: int = 4) -> dict[str, list[dict[str, Any]]]:
    with ThreadPoolExecutor(max_workers=2) as pool:
        getty_future = pool.submit(getty_aat_search, term, limit)
        asknature_future = pool.submit(asknature_search, term, limit)
        def safe_result(future: Any) -> list[dict[str, Any]]:
            try:
                return future.result(timeout=HTTP_TIMEOUT + 4) or []
            except Exception:
                return []
        getty_result = safe_result(getty_future)
        asknature_result = safe_result(asknature_future)
    return {
        "getty_aat": getty_result or [],
        "asknature": asknature_result or [],
    }


def seed_getty_cache_from_pipeline(source_root: Path | None = None) -> int:
    """Copy real cached AAT search/record payloads from the pipeline cache into
    the backend cache so a blocked live Getty still resolves cached terms."""
    roots = [source_root] if source_root else []
    search_root = Path("/root/creativeflow_pipeline/data/kb_cache/getty_aat_search")
    record_root = Path("/root/creativeflow_pipeline/data/kb_cache/getty_aat")
    copied = 0
    if search_root.exists():
        for path in search_root.glob("*.json"):
            term = path.stem.replace("_", " ")
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            records: list[dict[str, Any]] = []
            for row in (payload.get("results") or {}).get("bindings") or []:
                uri = str((row.get("s") or {}).get("value") or "")
                label = str((row.get("label") or {}).get("value") or "")
                if "/aat/" not in uri or not label:
                    continue
                records.append(
                    {
                        "graph": "getty_aat",
                        "id": uri.rsplit("/", 1)[-1],
                        "label": label,
                        "url": uri,
                        "broader": None,
                    }
                )
            if records:
                _write_cache("getty_aat", f"getty:{term}", {"records": records})
                copied += len(records)
    if record_root.exists():
        for path in record_root.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            uri = str(payload.get("id") or "")
            label = str(payload.get("_label") or payload.get("label") or "")
            if "/aat/" not in uri or not label:
                continue
            _write_cache(
                "getty_aat",
                f"getty:{label.lower()}",
                {
                    "records": [
                        {
                            "graph": "getty_aat",
                            "id": uri.rsplit("/", 1)[-1],
                            "label": label,
                            "url": uri,
                            "broader": None,
                        }
                    ]
                },
            )
            copied += 1
    return copied
