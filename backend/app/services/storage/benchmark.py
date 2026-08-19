"""Benchmark/white-model discovery (refactor plan P2).

Moved out of main.py; the FastAPI layer only wires the discovery callable.
"""

from __future__ import annotations

import json
import re
import ssl
from pathlib import Path
from urllib.parse import quote, unquote, urlparse
from urllib.request import Request as UrlRequest, urlopen

from app.models import BenchmarkAssetRecord


_DISCOVERY_CACHE: dict[str, tuple[float, list[BenchmarkAssetRecord]]] = {}
_DISCOVERY_TTL_SECONDS = 300.0


def discover_benchmark_assets(files_root: Path) -> list[BenchmarkAssetRecord]:
    """Discover benchmark/white-model assets with a short TTL cache.

    The listing endpoint and every asset-load call used to rescan the whole
    white-model manifest + OSS manifest on disk (~2.6s with 335 records).
    Caching for 30s makes the menu open instantly while still picking up
    newly uploaded models after a short delay.
    """
    import os
    import time

    # Tests and small deployments may opt out of the discovery cache entirely.
    if os.environ.get("FLOWSTUDIO_DISABLE_BENCHMARK_CACHE") == "1":
        return _discover_benchmark_assets_uncached(files_root)

    # Invalidate the cache whenever a manifest changes so tests that swap
    # manifests (and live deployments that add models) see fresh data.
    manifest_stamp = _discovery_manifest_stamp(files_root)
    key = f"{files_root}:{manifest_stamp}"
    now = time.monotonic()
    cached = _DISCOVERY_CACHE.get(key)
    if cached is not None and (now - cached[0]) < _DISCOVERY_TTL_SECONDS:
        return cached[1]
    records = _discover_benchmark_assets_uncached(files_root)
    _DISCOVERY_CACHE[key] = (now, records)
    return records


def _discovery_manifest_stamp(files_root: Path) -> str:
    stamps: list[str] = []
    for candidate in (
        files_root / "white-models" / "manifest.json",
        files_root.parent / "benchmark" / "creativeflow_oss_manifest.json",
    ):
        try:
            stat = candidate.stat()
        except OSError:
            continue
        stamps.append(f"{candidate.name}:{stat.st_mtime_ns}:{stat.st_size}")
    return "|".join(stamps)


def _discover_benchmark_assets_uncached(files_root: Path) -> list[BenchmarkAssetRecord]:
    local_white_records = _discover_local_white_model_assets(files_root)
    picked_records = _discover_creativeflow_picked_assets(files_root)
    if picked_records:
        return [*local_white_records, *picked_records]
    pinpoint_records = _discover_pinpoint_benchmark_assets(files_root)
    if pinpoint_records:
        return [*local_white_records, *pinpoint_records]
    manifest = _read_benchmark_oss_manifest(files_root)
    native_sources = manifest.get("native_sources") if isinstance(manifest, dict) else None
    selected_cases = manifest.get("selected20_cases") if isinstance(manifest, dict) else None
    if not isinstance(native_sources, list) and not isinstance(selected_cases, list):
        return local_white_records
    records: list[BenchmarkAssetRecord] = []
    oss_host = str(manifest.get("oss_host") or "")

    if isinstance(native_sources, list):
        for item in native_sources:
            if not isinstance(item, dict):
                continue
            first_target = next(
                (
                    target
                    for target in item.get("targets", [])
                    if isinstance(target, dict) and target.get("mesh_glb_key")
                ),
                None,
            )
            if not isinstance(first_target, dict):
                continue
            object_type = str(item.get("object_type") or "benchmark_object")
            source_id = str(item.get("source_id") or "")
            candidate_id = str(first_target.get("candidate_id") or "candidate")
            rationale_id = str(first_target.get("rationale_id") or "relation")
            benchmark_id = f"native15-target:{source_id}:{candidate_id}"
            records.append(
                BenchmarkAssetRecord(
                    benchmark_id=benchmark_id,
                    label=f"CreativeFlow {object_type}",
                    object_type=object_type,
                    relation_text=None,
                    target_text=None,
                    mesh_url=None,
                    obj_url=None,
                    file_size_bytes=0,
                    reference_status="OSS_GENERATED_GLB",
                    model_available=True,
                    metadata={
                        "source": "creativeflow_benchmark_oss_manifest",
                        "asset_kind": "native_generated_target",
                        "case_index": item.get("case_index"),
                        "source_id": item.get("source_id"),
                        "candidate_id": first_target.get("candidate_id"),
                        "rationale_id": first_target.get("rationale_id"),
                        "creativeflow_tree": _creativeflow_tree_metadata(
                            source_id=source_id,
                            object_type=object_type,
                            source_image_key=item.get("source_image_key"),
                            source_mesh_obj_key=item.get("source_mesh_obj_key"),
                            relation_id=rationale_id,
                            relation_key=rationale_id,
                            relation_text=None,
                            target_id=candidate_id,
                            target_key=candidate_id,
                            target_text=None,
                            target=first_target,
                        ),
                        "mesh_glb_key": first_target.get("mesh_glb_key"),
                        "mesh_obj_key": first_target.get("mesh_obj_key"),
                        "canonical_image_key": first_target.get("canonical_image_key"),
                        "creative_image_key": first_target.get("creative_image_key"),
                        "multiview_grid_key": first_target.get("multiview_grid_key"),
                        "source_image_key": item.get("source_image_key"),
                        "oss_host": oss_host,
                        "native_case_id": manifest.get("native_case_id"),
                        "selected20_run_id": manifest.get("selected20_run_id"),
                        "texture_index_rule": _benchmark_texture_index_rule("generated_glb"),
                    },
                )
            )

    if isinstance(selected_cases, list):
        selected20_references = _read_creativeflow_selected20_references(files_root)
        for item in selected_cases:
            if not isinstance(item, dict):
                continue
            first_target = next(
                (
                    target
                    for target in item.get("targets", [])
                    if isinstance(target, dict) and target.get("mesh_glb_key")
                ),
                None,
            )
            if not isinstance(first_target, dict):
                continue
            object_type = str(item.get("object_type") or "benchmark_object")
            benchmark_id = str(item.get("benchmark_id") or f"selected20:{item.get('source_id')}")
            source_id = str(item.get("source_id") or "")
            relation_key, target_key = _parse_creativeflow_relation_target_keys(first_target)
            reference = selected20_references.get((source_id, relation_key, target_key), {})
            relation_text = str(reference.get("relation_text") or "") or None
            target_text = str(reference.get("target_text") or "") or None
            records.append(
                BenchmarkAssetRecord(
                    benchmark_id=benchmark_id,
                    label=f"CreativeFlow dataset {object_type}",
                    object_type=object_type,
                    relation_text=relation_text,
                    target_text=target_text,
                    mesh_url=None,
                    obj_url=None,
                    file_size_bytes=0,
                    reference_status="OSS_SELECTED20_GLB",
                    model_available=True,
                    metadata={
                        "source": "creativeflow_benchmark_oss_manifest",
                        "asset_kind": "selected20_generated_target",
                        "case_index": item.get("case_index"),
                        "source_id": item.get("source_id"),
                        "relation_key": relation_key,
                        "target_key": target_key,
                        "relation_text": relation_text,
                        "target_text": target_text,
                        "candidate_id": first_target.get("candidate_id"),
                        "rationale_id": first_target.get("rationale_id"),
                        "creativeflow_tree": _creativeflow_tree_metadata(
                            source_id=source_id,
                            object_type=object_type,
                            source_image_key=item.get("source_image_key"),
                            source_mesh_obj_key=item.get("source_mesh_obj_key"),
                            relation_id=relation_key or str(first_target.get("rationale_id") or ""),
                            relation_key=relation_key,
                            relation_text=relation_text,
                            target_id=target_key or str(first_target.get("candidate_id") or ""),
                            target_key=target_key,
                            target_text=target_text,
                            target=first_target,
                            reference=reference,
                        ),
                        "mesh_glb_key": first_target.get("mesh_glb_key"),
                        "mesh_obj_key": first_target.get("mesh_obj_key"),
                        "canonical_image_key": first_target.get("canonical_image_key"),
                        "creative_image_key": first_target.get("creative_image_key"),
                        "multiview_grid_key": first_target.get("multiview_grid_key"),
                        "source_image_key": item.get("source_image_key"),
                        "oss_host": oss_host,
                        "native_case_id": manifest.get("native_case_id"),
                        "selected20_run_id": manifest.get("selected20_run_id"),
                        "texture_index_rule": _benchmark_texture_index_rule("generated_glb"),
                    },
                )
            )

    if not isinstance(native_sources, list):
        return [*local_white_records, *records]
    for item in native_sources:
        if not isinstance(item, dict):
            continue
        benchmark_id = str(item.get("benchmark_id") or item.get("source_id") or "")
        source_mesh_path = str(item.get("local_source_mesh_path") or "")
        source_glb_path = source_mesh_path.rsplit(".", 1)[0] + ".glb" if source_mesh_path.endswith(".obj") else ""
        object_type = str(item.get("object_type") or "benchmark_object")
        if not benchmark_id:
            continue
        mesh_url = (
            f"/api/v1/remote-worker/artifact-file?path={quote(source_glb_path, safe='')}"
            if item.get("local_source_mesh_exists") and source_glb_path
            else None
        )
        obj_url = (
            f"/api/v1/remote-worker/artifact-file?path={quote(source_mesh_path, safe='')}"
            if item.get("local_source_mesh_exists") and source_mesh_path
            else None
        )
        records.append(
            BenchmarkAssetRecord(
                benchmark_id=benchmark_id,
                label=f"Benchmark {object_type} source",
                object_type=object_type,
                mesh_url=mesh_url,
                obj_url=obj_url,
                file_size_bytes=0,
                reference_status="OSS_MANIFEST",
                model_available=bool(obj_url),
                metadata={
                    "source": "creativeflow_benchmark_oss_manifest",
                    "case_index": item.get("case_index"),
                    "source_id": item.get("source_id"),
                    "creativeflow_tree": _creativeflow_tree_metadata(
                        source_id=str(item.get("source_id") or ""),
                        object_type=object_type,
                        source_image_key=item.get("source_image_key"),
                        source_mesh_obj_key=item.get("source_mesh_obj_key"),
                        relation_id=None,
                        relation_key=None,
                        relation_text=None,
                        target_id=None,
                        target_key=None,
                        target_text=None,
                        target=None,
                    ),
                    "remote_source_mesh_path": source_mesh_path,
                    "remote_source_glb_path": source_glb_path,
                    "source_mesh_obj_key": item.get("source_mesh_obj_key"),
                    "source_material_mtl_key": item.get("source_material_mtl_key")
                    or item.get("material_mtl_key")
                    or item.get("mtl_key"),
                    "source_texture_key": item.get("source_texture_key")
                    or item.get("texture_key")
                    or item.get("albedo_key")
                    or item.get("diffuse_key")
                    or item.get("basecolor_key"),
                    "source_image_key": item.get("source_image_key"),
                    "mesh_obj_key": item.get("source_mesh_obj_key"),
                    "target_count": item.get("target_count"),
                    "targets": item.get("targets") or [],
                    "oss_host": oss_host,
                    "native_case_id": manifest.get("native_case_id"),
                    "selected20_run_id": manifest.get("selected20_run_id"),
                    "texture_index_rule": _benchmark_texture_index_rule("source_obj"),
                },
            )
        )
    return [*local_white_records, *records]


def _discover_local_white_model_assets(files_root: Path) -> list[BenchmarkAssetRecord]:
    manifest_path = files_root / "white-models" / "manifest.json"
    if not manifest_path.exists():
        return []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    assets = manifest.get("assets") if isinstance(manifest, dict) else None
    if not isinstance(assets, list):
        return []
    records: list[BenchmarkAssetRecord] = []
    for item in assets:
        if not isinstance(item, dict):
            continue
        obj_url = str(item.get("obj_url") or "")
        rel_path = unquote(obj_url.removeprefix("/files/")) if obj_url.startswith("/files/") else ""
        storage_path = str((files_root / rel_path).resolve()) if rel_path else ""
        if not obj_url or (storage_path and not Path(storage_path).exists()):
            continue
        label = str(item.get("label") or Path(obj_url).stem)
        category = str(item.get("category") or "white_models")
        preview_url = _clean_url_value(item.get("thumbnail_url"))
        if not preview_url and obj_url.lower().endswith(".obj"):
            preview_url = _clean_url_value(obj_url.replace(".obj", ".preview.png").replace(".OBJ", ".preview.png"))
        records.append(
            BenchmarkAssetRecord(
                benchmark_id=str(item.get("benchmark_id") or f"white:{category}:{Path(obj_url).stem}"),
                label=f"{category.replace('_', ' ').title()} · {label}",
                object_type=str(item.get("object_type") or category),
                obj_url=obj_url,
                thumbnail_url=preview_url,
                file_size_bytes=int(item.get("file_size_bytes") or 0),
                reference_status="LOCAL_WHITE_MODEL",
                model_available=True,
                metadata={
                    "source": "local_white_model",
                    "asset_kind": "white_model_source",
                    "category": category,
                    "collection": item.get("collection"),
                    "source_zip": item.get("source_zip"),
                    "image": preview_url,
                    "storage_path": storage_path,
                    "texture_index_rule": _benchmark_texture_index_rule("source_obj"),
                },
            )
        )
    # Keep quarantined collections visible in the benchmark browser so the
    # category remains discoverable, while explicitly marking the model as
    # unavailable. The load endpoint rejects these records instead of
    # pretending a high-poly source is runnable in the browser.
    quarantined = manifest.get("quarantined_assets") if isinstance(manifest, dict) else None
    if isinstance(quarantined, list):
        for item in quarantined:
            if not isinstance(item, dict):
                continue
            benchmark_id = str(item.get("benchmark_id") or "")
            parts = benchmark_id.split(":")
            if len(parts) < 3 or not benchmark_id:
                continue
            category = parts[1]
            label = parts[-1].replace("-", " ").replace("_", " ").title()
            records.append(
                BenchmarkAssetRecord(
                    benchmark_id=benchmark_id,
                    label=f"{category.replace('_', ' ').title()} · {label}",
                    object_type=label.lower().replace(" ", "_"),
                    reference_status="QUARANTINED_HIGH_POLY",
                    model_available=False,
                    metadata={
                        "source": "local_white_model",
                        "asset_kind": "white_model_source",
                        "category": category,
                        "availability": "quarantined",
                        "quarantine_reason": item.get("reason"),
                        "quarantine_path": item.get("quarantine_path"),
                    },
                )
            )
    return records


def _discover_creativeflow_picked_assets(files_root: Path) -> list[BenchmarkAssetRecord]:
    payload = _read_creativeflow_picked_dataset(files_root)
    sources = payload.get("sources") if isinstance(payload, dict) else None
    if not isinstance(sources, list):
        return []
    records: list[BenchmarkAssetRecord] = []
    for source_index, source in enumerate(sources):
        if not isinstance(source, dict):
            continue
        source = _clean_creativeflow_payload(source)
        source_id = str(source.get("id") or source.get("source_id") or "")
        if not source_id:
            continue
        noun_text = str(source.get("noun") or source.get("noun_text") or source.get("object_type") or "source")
        if "[DELETE]" in noun_text or source.get("deleted") is True:
            continue
        project_id = str(source.get("project") or source.get("project_id") or "")
        source_image_url = _clean_url_value(source.get("image") or source.get("source_image_url"))
        source_mesh_glb_url = _clean_url_value(
            source.get("mesh_glb") or source.get("source_mesh_glb_url") or source.get("source_mesh_url")
        )
        source_mesh_obj_url = _clean_url_value(
            source.get("mesh_obj") or source.get("source_mesh_obj_url")
        )
        source_multiview_url = _clean_url_value(
            source.get("multiview") or source.get("source_multiview_url")
        )
        source_image_key = _oss_key_from_url(source_image_url)
        source_mesh_glb_key = _oss_key_from_url(source_mesh_glb_url)
        source_mesh_obj_key = _oss_key_from_url(source_mesh_obj_url)
        source_multiview_key = _oss_key_from_url(source_multiview_url)
        relations = source.get("relations")
        relations_payload = relations if isinstance(relations, list) else []
        target_records = [
            target
            for relation in relations_payload
            if isinstance(relation, dict)
            for target in relation.get("targets", [])
            if isinstance(target, dict)
        ]
        first_mesh_target = next(
            (
                target
                for target in target_records
                if target.get("mesh_ready") and (target.get("mesh_glb") or target.get("mesh_obj"))
            ),
            None,
        )
        target_payload: dict[str, object] | None = None
        relation_payload: dict[str, object] | None = None
        if isinstance(first_mesh_target, dict):
            for relation in relations_payload:
                if isinstance(relation, dict) and first_mesh_target in relation.get("targets", []):
                    relation_payload = relation
                    break
            target_mesh_glb_key = _oss_key_from_url(first_mesh_target.get("mesh_glb"))
            target_payload = {
                "mesh_glb_key": target_mesh_glb_key,
                "mesh_obj_key": _oss_key_from_url(first_mesh_target.get("mesh_obj"))
                or _mesh_obj_key_from_glb_key(target_mesh_glb_key),
                "canonical_image_key": _oss_key_from_url(first_mesh_target.get("image")),
                "creative_image_key": _oss_key_from_url(first_mesh_target.get("image")),
                "multiview_grid_key": _oss_key_from_url(first_mesh_target.get("multiview"))
                or _multiview_grid_key_from_mesh_key(target_mesh_glb_key),
            }
        relation_id = str((relation_payload or {}).get("id") or "")
        relation_text = str((relation_payload or {}).get("label") or "")
        target_id = str((first_mesh_target or {}).get("id") or "")
        relation_key, target_key = _relation_target_from_target_key(
            str(target_payload.get("mesh_glb_key") if target_payload else "")
        )
        records.append(
            BenchmarkAssetRecord(
                benchmark_id=source_id,
                label=noun_text,
                object_type=noun_text,
                noun_text=noun_text,
                relation_text=relation_text or None,
                target_text=str((first_mesh_target or {}).get("text") or "") or None,
                mesh_url=source_mesh_glb_url or None,
                obj_url=source_mesh_obj_url or None,
                file_size_bytes=0,
                reference_status="GITHUB_PAGES_PICKED",
                model_available=bool(source_mesh_glb_url or source_mesh_obj_url),
                metadata={
                    "source": "creativeflow_github_pages_picked",
                    "asset_kind": "github_picked_source",
                    "project_id": project_id,
                    "source_id": source_id,
                    "source_index": source_index,
                    "category_id": source.get("category_id"),
                    "category_label": source.get("category") or source.get("category_label"),
                    "image": source_image_url,
                    "mesh_glb": source_mesh_glb_url,
                    "mesh_obj": source_mesh_obj_url,
                    "multiview": source_multiview_url,
                    "source_image_key": source_image_key,
                    "source_mesh_glb_key": source_mesh_glb_key,
                    "source_mesh_obj_key": source_mesh_obj_key,
                    "source_multiview_key": source_multiview_key,
                    "relation_count": source.get("relation_count"),
                    "target_count": source.get("target_count"),
                    "target_image_count": source.get("target_image_count"),
                    "target_mesh_count": source.get("target_mesh_count"),
                    "summary": {
                        "relation_count": source.get("relation_count"),
                        "target_count": source.get("target_count"),
                        "target_image_count": source.get("target_image_count"),
                        "target_mesh_count": source.get("target_mesh_count"),
                    },
                    "relations": relations_payload,
                    "targets": target_records,
                    "relation_id": relation_id,
                    "relation_key": relation_key,
                    "relation_text": relation_text,
                    "target_id": target_id,
                    "target_key": target_key,
                    "target_text": (first_mesh_target or {}).get("text"),
                    "mesh_glb_key": source_mesh_glb_key,
                    "mesh_obj_key": source_mesh_obj_key,
                    "picked_dataset_url": "https://creativeflow-bench.github.io/Creativeflow-Dataset/data/creativeflow-picked.json",
                    "creativeflow_tree": _creativeflow_tree_metadata(
                        source_id=source_id,
                        object_type=noun_text,
                        source_image_key=source_image_key,
                        source_mesh_obj_key=source_mesh_obj_key,
                        source_mesh_glb_key=source_mesh_glb_key,
                        relation_id=relation_id or None,
                        relation_key=relation_key or relation_id or None,
                        relation_text=relation_text or None,
                        target_id=target_id or None,
                        target_key=target_key or target_id or None,
                        target_text=str((first_mesh_target or {}).get("text") or "") or None,
                        target=target_payload,
                    ),
                    "oss_host": "creativeflow.oss-cn-beijing.aliyuncs.com",
                    "texture_index_rule": _benchmark_texture_index_rule("source_glb"),
                },
            )
        )
    records.sort(
        key=lambda item: (
            int(item.metadata.get("source_index") or 0),
            str(item.metadata.get("source_id") or ""),
        )
    )
    return records


def _picked_benchmark_label(
    noun_text: str, relation_key: str, target_key: str, relation_text: str
) -> str:
    if relation_key and target_key:
        return f"CreativeFlow picked {noun_text} · {relation_key}/{target_key}"
    if relation_text:
        return f"CreativeFlow picked {noun_text} · {relation_text[:42]}"
    return f"CreativeFlow picked {noun_text}"


def _read_creativeflow_picked_dataset(files_root: Path) -> dict[str, object]:
    cache_path = files_root.parent / "benchmark" / "creativeflow-picked.json"
    request = UrlRequest(
        "https://creativeflow-bench.github.io/Creativeflow-Dataset/data/creativeflow-picked.json",
        headers={
            "Accept": "application/json",
            "User-Agent": "FlowStudio/0.1 creativeflow-picked-loader",
        },
    )
    try:
        payload = json.loads(
            urlopen(request, timeout=4, context=ssl._create_unverified_context())
            .read()
            .decode("utf-8")
        )
        if isinstance(payload, dict) and isinstance(payload.get("sources"), list):
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return payload
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        pass
    candidates = [
        cache_path,
        files_root.parent / "benchmark" / "creativeflow_picked.json",
        Path("/benchmark/creativeflow-picked.json"),
        Path("/benchmark/creativeflow_picked.json"),
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(payload, dict) and isinstance(payload.get("sources"), list):
            return payload
    return {}


def _discover_pinpoint_benchmark_assets(files_root: Path) -> list[BenchmarkAssetRecord]:
    index = _read_pinpoint_benchmark_index(files_root)
    sources = index.get("sources") if isinstance(index, dict) else None
    if not isinstance(sources, list):
        return []
    records: list[BenchmarkAssetRecord] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("source_id") or "")
        noun_text = str(source.get("noun_text") or source.get("classification", {}).get("matched") or "benchmark_object")
        project_id = str(source.get("project_id") or "")
        if not source_id or not project_id:
            continue
        if "[DELETE]" in noun_text or source.get("deleted") is True:
            continue
        source_image_key = _oss_key_from_url(source.get("source_image_url"))
        source_mesh_glb_key = _oss_key_from_url(source.get("source_mesh_url"))
        preview_key = _oss_key_from_url(source.get("preview_image_url"))
        target_mesh_glb_key = _target_mesh_glb_key_from_preview_key(preview_key)
        relation_key, target_key = _relation_target_from_target_key(target_mesh_glb_key or preview_key)
        mesh_glb_key = target_mesh_glb_key or source_mesh_glb_key
        if not mesh_glb_key:
            continue
        target: dict[str, object] | None = None
        if target_mesh_glb_key:
            target = {
                "mesh_glb_key": target_mesh_glb_key,
                "mesh_obj_key": target_mesh_glb_key.rsplit(".", 1)[0] + ".obj",
                "canonical_image_key": preview_key,
                "creative_image_key": preview_key,
                "multiview_grid_key": target_mesh_glb_key.rsplit("/", 1)[0] + "/multiview/grid.png",
            }
        benchmark_id = (
            f"pinpoint:{source_id}:{relation_key}:{target_key}"
            if target_mesh_glb_key
            else f"pinpoint-source:{source_id}"
        )
        records.append(
            BenchmarkAssetRecord(
                benchmark_id=benchmark_id,
                label=_pinpoint_benchmark_label(noun_text, relation_key, target_key, bool(target_mesh_glb_key)),
                object_type=noun_text,
                noun_text=noun_text,
                relation_text=str(source.get("preview_relation_text") or "") or None,
                target_text=None,
                mesh_url=None,
                obj_url=None,
                file_size_bytes=0,
                reference_status="PINPOINT_BENCHMARK_TREE",
                model_available=True,
                metadata={
                    "source": "pinpoint_benchmark",
                    "asset_kind": "pinpoint_target" if target_mesh_glb_key else "pinpoint_source",
                    "project_id": project_id,
                    "source_id": source_id,
                    "category_id": source.get("category_id"),
                    "category_label": source.get("category_label"),
                    "benchmark_status": source.get("benchmark_status"),
                    "source_status": source.get("source_status"),
                    "quality_status": source.get("quality_status"),
                    "target_count": source.get("target_count"),
                    "target_mesh_ready_count": source.get("target_mesh_ready_count"),
                    "relation_count": source.get("relation_count"),
                    "relation_key": relation_key,
                    "target_key": target_key,
                    "mesh_glb_key": mesh_glb_key,
                    "mesh_obj_key": mesh_glb_key.rsplit(".", 1)[0] + ".obj",
                    "source_image_key": source_image_key,
                    "source_mesh_glb_key": source_mesh_glb_key,
                    "source_mesh_obj_key": source_mesh_glb_key.rsplit(".", 1)[0] + ".obj" if source_mesh_glb_key else "",
                    "preview_image_key": preview_key,
                    "detail_url": source.get("detail_url"),
                    "pinpoint_api": {
                        "relations_url": f"https://pinpoint.asia/api/v2/sources/{source_id}/relations",
                        "targets_url_template": "https://pinpoint.asia/api/v2/relations/{relation_id}/targets",
                    },
                    "creativeflow_tree": _creativeflow_tree_metadata(
                        source_id=source_id,
                        object_type=noun_text,
                        source_image_key=source_image_key,
                        source_mesh_obj_key=source_mesh_glb_key.rsplit(".", 1)[0] + ".obj" if source_mesh_glb_key else "",
                        source_mesh_glb_key=source_mesh_glb_key,
                        relation_id=relation_key,
                        relation_key=relation_key,
                        relation_text=None,
                        target_id=target_key,
                        target_key=target_key,
                        target_text=None,
                        target=target,
                    ),
                    "oss_host": "creativeflow.oss-cn-beijing.aliyuncs.com",
                    "texture_index_rule": _benchmark_texture_index_rule(
                        "generated_glb" if target_mesh_glb_key else "source_glb"
                    ),
                },
            )
        )
    records.sort(
        key=lambda item: (
            0 if item.metadata.get("asset_kind") == "pinpoint_target" else 1,
            str(item.object_type),
            str(item.metadata.get("source_id") or ""),
        )
    )
    return records


def _pinpoint_benchmark_label(noun_text: str, relation_key: str, target_key: str, has_target: bool) -> str:
    if has_target and relation_key and target_key:
        return f"CreativeFlow {noun_text} · {relation_key}/{target_key}"
    return f"CreativeFlow source {noun_text}"


def _target_mesh_glb_key_from_preview_key(preview_key: str) -> str:
    if "/targets/" not in preview_key or not preview_key.endswith("/image.png"):
        return ""
    return preview_key[: -len("/image.png")] + "/mesh.glb"


def _mesh_obj_key_from_glb_key(mesh_glb_key: str) -> str:
    return mesh_glb_key.rsplit(".", 1)[0] + ".obj" if mesh_glb_key else ""


def _multiview_grid_key_from_mesh_key(mesh_glb_key: str) -> str:
    return mesh_glb_key.rsplit("/", 1)[0] + "/multiview/grid.png" if mesh_glb_key else ""


def _relation_target_from_target_key(key: str) -> tuple[str, str]:
    if "/targets/" not in key:
        return "", ""
    tail = key.split("/targets/", 1)[1].split("/")
    if len(tail) < 2:
        return "", ""
    return tail[0], tail[1]


def _oss_key_from_url(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    if value.strip().lower() in {"none", "null", "undefined", "nan"}:
        return ""
    parsed = urlparse(value.strip())
    path = parsed.path if parsed.scheme else value.strip()
    path = unquote(path).lstrip("/")
    if path.startswith("creativeflow/"):
        return path
    return ""


def _clean_url_value(value: object) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = value.strip()
    if not cleaned or cleaned.lower() in {"none", "null", "undefined", "nan"}:
        return ""
    parsed = urlparse(cleaned)
    if (
        parsed.netloc == "creativeflow.oss-cn-beijing.aliyuncs.com"
        and "OSSAccessKeyId=" in parsed.query
        and "Signature=" in parsed.query
    ):
        return parsed._replace(query="", fragment="").geturl()
    return cleaned


def _clean_creativeflow_payload(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _clean_creativeflow_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean_creativeflow_payload(item) for item in value]
    if isinstance(value, str):
        return _clean_url_value(value)
    return value


def _read_pinpoint_benchmark_index(files_root: Path) -> dict[str, object]:
    candidates = [
        files_root.parent / "benchmark" / "benchmark_index.json",
        files_root.parent / "benchmark" / "benchmark_index_lite.json",
        Path("/benchmark/benchmark_index.json"),
        Path("/benchmark/benchmark_index_lite.json"),
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(payload, dict) and isinstance(payload.get("sources"), list):
            return payload
    for url in (
        "https://pinpoint.asia/benchmark/benchmark_index.json",
        "https://pinpoint.asia/benchmark/benchmark_index_lite.json",
    ):
        try:
            request = UrlRequest(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "FlowStudio/0.1 benchmark-index-loader",
                },
            )
            payload = json.loads(
                urlopen(request, timeout=4, context=ssl._create_unverified_context())
                .read()
                .decode("utf-8")
            )
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(payload, dict) and isinstance(payload.get("sources"), list):
            return payload
    return {}


def _benchmark_texture_index_rule(asset_kind: str) -> dict[str, object]:
    if asset_kind == "generated_glb":
        return {
            "version": "creativeflow_benchmark_texture_tree.v1",
            "tree": "source -> relation -> target",
            "priority": [
                "target.mesh_glb_key: load GLB directly; CreativeFlow/Hunyuan GLB embeds baseColorTexture",
                "target.mesh_obj_key + explicit material/texture keys",
                "target.mesh_obj_key + target.canonical_image_key only as an OBJ preview fallback",
            ],
            "missing_texture_policy": "do_not_synthesize_texture; render material-only/white-shell regions",
        }
    if asset_kind == "source_glb":
        return {
            "version": "creativeflow_benchmark_texture_tree.v1",
            "tree": "source -> relation -> target",
            "priority": [
                "source.source_mesh_glb_key: load GLB directly; Hunyuan GLB embeds baseColorTexture when present",
                "source.source_mesh_obj_key + source.source_image_key fallback",
            ],
            "missing_texture_policy": "do_not_synthesize_texture; render material-only/white-shell regions",
        }
    return {
        "version": "creativeflow_benchmark_texture_tree.v1",
        "tree": "source -> relation -> target",
        "priority": [
            "source.source_material_mtl_key + source.source_texture_key",
            "source.source_texture_key",
            "source.source_image_key from the same source/ tree",
            "source sibling source.png/texture.png if explicitly indexed later",
        ],
        "missing_texture_policy": "do_not_synthesize_texture; render material-only/white-shell regions",
    }


def _creativeflow_tree_metadata(
    *,
    source_id: str,
    object_type: str,
    source_image_key: object,
    source_mesh_obj_key: object,
    relation_id: str | None,
    relation_key: str | None,
    relation_text: str | None,
    target_id: str | None,
    target_key: str | None,
    target_text: str | None,
    target: dict | None,
    reference: dict | None = None,
    source_mesh_glb_key: object | None = None,
) -> dict[str, object]:
    target = target if isinstance(target, dict) else {}
    reference = reference if isinstance(reference, dict) else {}
    return {
        "source": {
            "id": source_id,
            "object_type": object_type,
            "image_key": source_image_key,
            "mesh_glb_key": source_mesh_glb_key,
            "mesh_obj_key": source_mesh_obj_key,
            "reference_image_path": reference.get("source_image_path"),
            "reference_mesh_path": reference.get("source_mesh_path"),
            "texture_rule": "source.image_key is the source texture preview when OBJ has no explicit MTL sidecar",
        },
        "relation": {
            "id": relation_id,
            "key": relation_key,
            "text": relation_text,
        },
        "target": {
            "id": target_id,
            "key": target_key,
            "text": target_text,
            "mesh_glb_key": target.get("mesh_glb_key"),
            "mesh_obj_key": target.get("mesh_obj_key"),
            "canonical_image_key": target.get("canonical_image_key"),
            "creative_image_key": target.get("creative_image_key"),
            "multiview_grid_key": target.get("multiview_grid_key"),
            "reference_image_path": reference.get("target_image_path"),
            "reference_mesh_path": reference.get("target_mesh_path"),
            "texture_rule": "target.mesh_glb_key is authoritative when available because it embeds baseColorTexture",
        },
    }


def _parse_creativeflow_relation_target_keys(target: dict[str, object]) -> tuple[str, str]:
    haystack = " ".join(
        str(target.get(key) or "")
        for key in ("mesh_glb_key", "mesh_obj_key", "canonical_image_key", "creative_image_key")
    )
    match = re.search(r"__(g\d+_r\d+)__(e\d+_t\d+)", haystack)
    if not match:
        return "", ""
    return match.group(1).replace("_", "-"), match.group(2).replace("_", "-")


def _read_creativeflow_selected20_references(files_root: Path) -> dict[tuple[str, str, str], dict[str, object]]:
    selected_path = files_root.parent / "benchmark" / "creativeflow_selected20.json"
    if not selected_path.exists():
        return {}
    try:
        payload = json.loads(selected_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(payload, list):
        return {}
    references: dict[tuple[str, str, str], dict[str, object]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("source_id") or "")
        relation_key = str(item.get("relation_key") or "")
        target_key = str(item.get("target_key") or "")
        reference = item.get("creativeflow_reference")
        if not source_id or not relation_key or not target_key or not isinstance(reference, dict):
            continue
        references[(source_id, relation_key, target_key)] = {
            **reference,
            "relation_text": item.get("relation_text"),
            "target_text": item.get("target_text"),
            "noun_text": item.get("noun_text"),
            "source_prompt": item.get("source_prompt"),
            "analogy_prompt": item.get("analogy_prompt"),
        }
    return references


def _resolve_benchmark_texture_key(metadata: dict[str, object]) -> str:
    for key in (
        "source_texture_key",
        "texture_key",
        "albedo_key",
        "diffuse_key",
        "basecolor_key",
        "texture_image_key",
        "source_image_key",
        "canonical_image_key",
        "creative_image_key",
    ):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _benchmark_tree_material(texture_name: str) -> bytes:
    return (
        "newmtl material_0\n"
        "Ka 1.000000 1.000000 1.000000\n"
        "Kd 1.000000 1.000000 1.000000\n"
        "Ks 0.000000 0.000000 0.000000\n"
        f"map_Kd {texture_name}\n"
    ).encode("utf-8")


def _download_oss_object(oss_host: str, object_key: str) -> bytes:
    oss_url = f"https://{oss_host.rstrip('/')}/{object_key.lstrip('/')}"
    with urlopen(oss_url, timeout=30, context=ssl._create_unverified_context()) as response:
        return response.read()


def _read_benchmark_oss_manifest(files_root: Path) -> dict[str, object]:
    manifest_path = files_root.parent / "benchmark" / "creativeflow_oss_manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}
