"""Assets, versions, parts, uploads and benchmark-model routers (refactor plan P1b)."""

from __future__ import annotations

import json
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.models import (
    ArtifactRecord,
    AssetCreateRequest,
    AssetPartsResponse,
    AssetVersionRecord,
    BenchmarkAssetListResponse,
    BenchmarkAssetLoadRequest,
    BenchmarkAssetRecord,
    MemoryRecord,
    PartDiscoveryRequest,
    PartDiscoveryResponse,
    PartRecord,
    PartUpdateRequest,
    SessionRecord,
    UserEvent,
    WebReferenceAttachRequest,
)
from app.services.storage.studio_store import InMemoryStudioStore


def create_assets_router(
    *,
    require_session: Callable[[str], SessionRecord],
    studio_store: InMemoryStudioStore,
    files_root: Path,
    websocket_manager: Any,
    remote_worker_adapter: Any,
    autopartgen_adapter: Any,
    discover_benchmark_assets: Callable[[Path], list[BenchmarkAssetRecord]],
    download_oss_object: Callable[[str, str], bytes],
    resolve_benchmark_texture_key: Callable[[dict[str, object]], str],
    benchmark_tree_material: Callable[[str], bytes],
    export_url_for_format: Callable[[str | None, str | None, str], str | None],
    read_export_artifact: Callable[[str], Awaitable[tuple[bytes, str]]],
    export_filename: Callable[[str, str], str],
) -> APIRouter:
    router = APIRouter(tags=["assets"])

    @router.post("/api/v1/assets")
    async def create_asset(request: AssetCreateRequest) -> object:
        require_session(request.session_id)
        return studio_store.create_asset(request)

    @router.get("/api/v1/benchmark-assets")
    async def list_benchmark_assets() -> BenchmarkAssetListResponse:
        # 列表只给菜单分组所需的轻量字段；完整 metadata（storage_path、
        # texture 规则、OSS key 等）体积大，经隧道传输会显著拖慢初始化。
        trimmed = []
        keep_metadata_keys = ("source", "category", "collection", "asset_kind", "image")
        for record in discover_benchmark_assets(files_root):
            metadata = record.metadata or {}
            trimmed_metadata = {
                key: metadata.get(key)
                for key in keep_metadata_keys
                if metadata.get(key) is not None
            }
            # Prefer explicit preview image; fall back to multiview still for CF assets.
            if "image" not in trimmed_metadata:
                for key in ("multiview", "preview_image_key"):
                    value = metadata.get(key)
                    if isinstance(value, str) and value.strip():
                        trimmed_metadata["image"] = value.strip()
                        break
            preview_url = record.thumbnail_url or trimmed_metadata.get("image")
            if isinstance(preview_url, str):
                preview_url = preview_url.strip() or None
            else:
                preview_url = None
            trimmed.append(
                record.model_copy(
                    update={
                        "metadata": trimmed_metadata,
                        "thumbnail_url": preview_url,
                    }
                )
            )
        # CreativeFlow picked dataset repeats the same noun across batches
        # (e.g. armchair ×4). Keep one card per label for the menu; prefer a
        # mesh-ready entry when available. Local white models are left intact.
        deduped: list[BenchmarkAssetRecord] = []
        cf_best: dict[str, BenchmarkAssetRecord] = {}
        cf_order: list[str] = []
        for record in trimmed:
            source = str((record.metadata or {}).get("source") or "")
            if source != "creativeflow_github_pages_picked":
                deduped.append(record)
                continue
            key = " ".join(str(record.label or record.object_type or "").lower().split())
            if not key:
                deduped.append(record)
                continue
            previous = cf_best.get(key)
            if previous is None:
                cf_best[key] = record
                cf_order.append(key)
                continue
            prev_score = (
                1 if previous.model_available else 0,
                1 if (previous.mesh_url or previous.obj_url) else 0,
            )
            next_score = (
                1 if record.model_available else 0,
                1 if (record.mesh_url or record.obj_url) else 0,
            )
            if next_score > prev_score:
                cf_best[key] = record
        deduped.extend(cf_best[key] for key in cf_order)
        return BenchmarkAssetListResponse(assets=deduped)

    @router.post("/api/v1/benchmark-assets/{benchmark_id}/load")
    async def load_benchmark_asset(
        benchmark_id: str,
        request: BenchmarkAssetLoadRequest,
    ) -> object:
        require_session(request.session_id)
        benchmarks = {item.benchmark_id: item for item in discover_benchmark_assets(files_root)}
        benchmark = benchmarks.get(benchmark_id)
        if benchmark is None:
            raise HTTPException(status_code=404, detail=f"Benchmark asset not found: {benchmark_id}")
        if not benchmark.model_available:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Benchmark asset is currently unavailable: "
                    f"{benchmark.reference_status or 'not runnable'}"
                ),
            )
        if benchmark.metadata.get("source") in {"creativeflow_github_pages_picked", "local_white_model"}:
            source_kind = str(benchmark.metadata.get("source") or "benchmark")
            asset = studio_store.create_asset(
                AssetCreateRequest(
                    session_id=request.session_id,
                    object_type=benchmark.object_type,
                    label=benchmark.label,
                    mesh_url=benchmark.mesh_url,
                    obj_url=benchmark.obj_url,
                    thumbnail_url=str(benchmark.metadata.get("image") or ""),
                    metadata={
                        "source": "benchmark",
                        "benchmark_id": benchmark.benchmark_id,
                        "benchmark_metadata": benchmark.metadata,
                        "remote_asset": {
                            "source": source_kind,
                            "mesh_url": benchmark.mesh_url,
                            "obj_url": benchmark.obj_url,
                        },
                        "storage_path": benchmark.metadata.get("storage_path"),
                        "white_model_category": benchmark.metadata.get("category"),
                        "white_model_collection": benchmark.metadata.get("collection"),
                        "texture_index_rule": benchmark.metadata.get("texture_index_rule"),
                    },
                )
            )
            session = require_session(request.session_id)
            session.stage.active_asset_id = asset.asset_id
            studio_store.save_stage(session.session_id, session.stage)
            return asset
        remote_source_mesh_path = benchmark.metadata.get("remote_source_mesh_path")
        remote_source_glb_path = benchmark.metadata.get("remote_source_glb_path")
        oss_host = str(benchmark.metadata.get("oss_host") or "").strip()
        mesh_glb_key = str(benchmark.metadata.get("mesh_glb_key") or "").strip()
        mesh_obj_key = str(
            benchmark.metadata.get("mesh_obj_key")
            or benchmark.metadata.get("source_mesh_obj_key")
            or ""
        ).strip()
        materialized_mesh: tuple[bytes, str] | None = None
        materialized_source: str | None = None
        sidecar_files: dict[str, bytes] = {}
        if oss_host and mesh_glb_key:
            try:
                materialized_mesh = (download_oss_object(oss_host, mesh_glb_key), ".glb")
                materialized_source = "oss_glb"
            except OSError as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"Benchmark GLB could not be loaded from OSS: {exc}",
                ) from exc
        if materialized_mesh is None and isinstance(remote_source_glb_path, str) and remote_source_glb_path:
            try:
                content, _content_type = await remote_worker_adapter.get_artifact_file(remote_source_glb_path)
                materialized_mesh = (content, ".glb")
                materialized_source = "remote_worker_glb"
            except RuntimeError:
                materialized_mesh = None
        if materialized_mesh is None and isinstance(remote_source_mesh_path, str) and remote_source_mesh_path:
            try:
                content, _content_type = await remote_worker_adapter.get_artifact_file(remote_source_mesh_path)
                materialized_mesh = (content, ".obj")
                materialized_source = "remote_worker_obj"
            except RuntimeError as exc:
                if not oss_host or not mesh_obj_key:
                    raise HTTPException(
                        status_code=502,
                        detail=(
                            "Benchmark source mesh is registered, but the remote worker "
                            f"could not provide it: {exc}"
                        ),
                    ) from exc
                try:
                    materialized_mesh = (download_oss_object(oss_host, mesh_obj_key), ".obj")
                    materialized_source = "oss_obj"
                except OSError as oss_exc:
                    raise HTTPException(
                        status_code=502,
                        detail=(
                            "Benchmark source mesh could not be loaded from remote worker "
                            f"or OSS: remote={exc}; oss={oss_exc}"
                        ),
                    ) from oss_exc
        if materialized_mesh is None and oss_host and mesh_obj_key:
            try:
                materialized_mesh = (download_oss_object(oss_host, mesh_obj_key), ".obj")
                materialized_source = "oss_obj"
            except OSError as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"Benchmark OBJ could not be loaded from OSS: {exc}",
                ) from exc
        if materialized_mesh is not None and materialized_mesh[1] == ".obj":
            material_key = str(benchmark.metadata.get("source_material_mtl_key") or "").strip()
            texture_key = resolve_benchmark_texture_key(benchmark.metadata)
            if oss_host and material_key:
                try:
                    sidecar_files["material.mtl"] = download_oss_object(oss_host, material_key)
                    if texture_key:
                        sidecar_files[Path(texture_key).name] = download_oss_object(oss_host, texture_key)
                except OSError:
                    sidecar_files = {}
            elif oss_host and texture_key:
                try:
                    texture_name = Path(texture_key).name
                    sidecar_files["material.mtl"] = benchmark_tree_material(texture_name)
                    sidecar_files[texture_name] = download_oss_object(oss_host, texture_key)
                except OSError:
                    sidecar_files = {}
        remote_asset = (
            {
                "path": remote_source_mesh_path,
                "glb_path": remote_source_glb_path,
                "source": "creativeflow_benchmark_oss_manifest",
                "asset_id": benchmark.benchmark_id,
            }
            if isinstance(remote_source_mesh_path, str) and remote_source_mesh_path
            else None
        )
        asset = studio_store.create_asset(
            AssetCreateRequest(
                session_id=request.session_id,
                object_type=benchmark.object_type,
                label=benchmark.label,
                mesh_url=benchmark.mesh_url if materialized_mesh is None else None,
                obj_url=benchmark.obj_url if materialized_mesh is None else None,
                thumbnail_url=str(benchmark.metadata.get("image") or "") or None,
                metadata={
                    "source": "benchmark",
                    "benchmark_id": benchmark.benchmark_id,
                    "remote_asset": remote_asset,
                    "remote_source_mesh_path": remote_source_mesh_path,
                    "benchmark_metadata": benchmark.metadata,
                    "texture_index_rule": benchmark.metadata.get("texture_index_rule"),
                },
            )
        )
        if materialized_mesh is not None:
            content, suffix = materialized_mesh
            asset_dir = files_root / "assets" / asset.asset_id
            asset_dir.mkdir(parents=True, exist_ok=True)
            target = asset_dir / f"source{suffix}"
            target.write_bytes(content)
            for name, data in sidecar_files.items():
                (asset_dir / name).write_bytes(data)
            if suffix == ".glb":
                asset.mesh_url = f"/files/assets/{asset.asset_id}/source{suffix}"
                asset.obj_url = None
            else:
                asset.mesh_url = None
                asset.obj_url = f"/files/assets/{asset.asset_id}/source{suffix}"
            asset.metadata["storage_path"] = str(target)
            asset.metadata["materialized_from_remote"] = True
            asset.metadata["materialized_source"] = materialized_source or "unknown"
            if sidecar_files:
                asset.metadata["material_sidecars"] = sorted(sidecar_files)
                asset.metadata["material_sidecars_generated_by_rule"] = "material.mtl" in sidecar_files and not benchmark.metadata.get(
                    "source_material_mtl_key"
                )
        session = require_session(request.session_id)
        session.stage.active_asset_id = asset.asset_id
        studio_store.save_stage(session.session_id, session.stage)
        return asset

    @router.post("/api/v1/assets/upload")
    async def upload_asset(
        session_id: str = Form(...),
        object_type: str = Form("object"),
        label: str | None = Form(None),
        metadata: str | None = Form(None),
        file: UploadFile = File(...),
    ) -> object:
        require_session(session_id)
        suffix = Path(file.filename or "source.glb").suffix.lower()
        if suffix not in {".glb", ".obj", ".zip"}:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")
        asset_id = f"asset_{uuid4().hex[:10]}"
        asset_dir = files_root / "assets" / asset_id
        asset_dir.mkdir(parents=True, exist_ok=True)
        target = asset_dir / f"source{suffix}"
        with target.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        parsed_metadata = {}
        if metadata:
            try:
                parsed_metadata = json.loads(metadata)
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=400, detail="metadata must be JSON") from exc
        asset = studio_store.create_asset(
            AssetCreateRequest(
                session_id=session_id,
                object_type=object_type,
                label=label or file.filename or f"{object_type} source model",
                mesh_url=f"/files/assets/{asset_id}/source{suffix}" if suffix in {".glb", ".zip"} else None,
                obj_url=f"/files/assets/{asset_id}/source{suffix}" if suffix == ".obj" else None,
                thumbnail_url=None,
                metadata={
                    **parsed_metadata,
                    "uploaded_filename": file.filename,
                    "storage_path": str(target),
                },
            )
        )
        old_asset_id = asset.asset_id
        asset.asset_id = asset_id
        if old_asset_id in studio_store.assets:
            del studio_store.assets[old_asset_id]
        studio_store.assets[asset_id] = asset
        session = require_session(session_id)
        session.stage.active_asset_id = asset_id
        studio_store.save_stage(session_id, session.stage)
        return asset

    @router.post("/api/v1/reference-images/upload")
    async def upload_reference_image(
        session_id: str = Form(...),
        asset_id: str | None = Form(None),
        role: str = Form("shape_reference"),
        metadata: str | None = Form(None),
        file: UploadFile = File(...),
    ) -> ArtifactRecord:
        require_session(session_id)
        if asset_id and studio_store.get_asset(asset_id) is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {asset_id}")
        suffix = Path(file.filename or "reference.png").suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise HTTPException(status_code=400, detail=f"Unsupported reference image type: {suffix}")
        artifact_id = f"art_{uuid4().hex[:10]}"
        ref_dir = files_root / "references" / artifact_id
        ref_dir.mkdir(parents=True, exist_ok=True)
        target = ref_dir / f"source{suffix}"
        with target.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        parsed_metadata: dict[str, object] = {}
        if metadata:
            try:
                raw_metadata = json.loads(metadata)
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=400, detail="metadata must be JSON") from exc
            if isinstance(raw_metadata, dict):
                parsed_metadata = raw_metadata
        artifact = studio_store.save_artifact(
            ArtifactRecord(
                artifact_id=artifact_id,
                type="reference_image",
                url=f"/files/references/{artifact_id}/source{suffix}",
                session_id=session_id,
                asset_id=asset_id,
                worker="manual",
                operation="reference_image_upload",
                metadata={
                    **parsed_metadata,
                    "role": role,
                    "uploaded_filename": file.filename,
                    "storage_path": str(target),
                },
            )
        )
        event = UserEvent(
            type="reference_image_attached",
            event_id=f"evt_{uuid4().hex[:10]}",
            session_id=session_id,
            payload={
                "artifact_id": artifact.artifact_id,
                "artifact_url": artifact.url,
                "asset_id": asset_id,
                "role": role,
                "filename": file.filename,
                "metadata": parsed_metadata,
            },
        )
        studio_store.save_event(event)
        studio_store.save_memory(
            MemoryRecord(
                memory_id=f"mem_{uuid4().hex[:10]}",
                session_id=session_id,
                category="working",
                type="reference_image",
                source_id=artifact.artifact_id,
                asset_id=asset_id,
                content={
                    "artifact": artifact.model_dump(mode="json"),
                    "event_id": event.event_id,
                    "role": role,
                },
                tags=["reference_image", role],
            )
        )
        await websocket_manager.broadcast(
            session_id,
            "reference_image_attached",
            {
                "artifact": artifact.model_dump(mode="json"),
                "event_id": event.event_id,
            },
        )
        return artifact

    @router.post("/api/v1/reference-models/upload")
    async def upload_reference_model(
        session_id: str = Form(...),
        asset_id: str | None = Form(None),
        role: str = Form("model_reference"),
        metadata: str | None = Form(None),
        file: UploadFile = File(...),
    ) -> ArtifactRecord:
        require_session(session_id)
        if asset_id and studio_store.get_asset(asset_id) is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {asset_id}")
        suffix = Path(file.filename or "reference.glb").suffix.lower()
        if suffix not in {".glb", ".obj", ".zip"}:
            raise HTTPException(status_code=400, detail=f"Unsupported reference model type: {suffix}")
        artifact_id = f"art_{uuid4().hex[:10]}"
        ref_dir = files_root / "reference-models" / artifact_id
        ref_dir.mkdir(parents=True, exist_ok=True)
        target = ref_dir / f"source{suffix}"
        with target.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        parsed_metadata: dict[str, object] = {}
        if metadata:
            try:
                raw_metadata = json.loads(metadata)
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=400, detail="metadata must be JSON") from exc
            if isinstance(raw_metadata, dict):
                parsed_metadata = raw_metadata
        artifact = studio_store.save_artifact(
            ArtifactRecord(
                artifact_id=artifact_id,
                type="reference_model",
                url=f"/files/reference-models/{artifact_id}/source{suffix}",
                session_id=session_id,
                asset_id=asset_id,
                worker="manual",
                operation="reference_model_upload",
                metadata={
                    **parsed_metadata,
                    "role": role,
                    "uploaded_filename": file.filename,
                    "storage_path": str(target),
                    "model_ref_kind": "intent_reference_not_active_asset",
                },
            )
        )
        event = UserEvent(
            type="reference_model_attached",
            event_id=f"evt_{uuid4().hex[:10]}",
            session_id=session_id,
            payload={
                "artifact_id": artifact.artifact_id,
                "artifact_url": artifact.url,
                "asset_id": asset_id,
                "role": role,
                "filename": file.filename,
                "metadata": parsed_metadata,
            },
        )
        studio_store.save_event(event)
        studio_store.save_memory(
            MemoryRecord(
                memory_id=f"mem_{uuid4().hex[:10]}",
                session_id=session_id,
                category="working",
                type="reference_model",
                source_id=artifact.artifact_id,
                asset_id=asset_id,
                content={
                    "artifact": artifact.model_dump(mode="json"),
                    "event_id": event.event_id,
                    "role": role,
                },
                tags=["reference_model", role],
            )
        )
        await websocket_manager.broadcast(
            session_id,
            "reference_model_attached",
            {"artifact": artifact.model_dump(mode="json"), "event_id": event.event_id},
        )
        return artifact

    @router.post("/api/v1/reference-images/attach")
    async def attach_web_reference_image(
        request: WebReferenceAttachRequest,
    ) -> ArtifactRecord:
        require_session(request.session_id)
        if not request.url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="url must be an absolute http(s) URL")
        if request.asset_id and studio_store.get_asset(request.asset_id) is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {request.asset_id}")
        artifact_id = f"art_{uuid4().hex[:10]}"
        artifact = studio_store.save_artifact(
            ArtifactRecord(
                artifact_id=artifact_id,
                type="reference_image",
                url=request.url,
                session_id=request.session_id,
                asset_id=request.asset_id,
                worker="manual",
                operation="reference_image_web_attach",
                metadata={
                    "role": request.role,
                    "source": "web_search",
                    "remote_url": True,
                    "thumbnail_url": request.thumbnail,
                    "search_title": request.title,
                    "uploaded_filename": None,
                },
            )
        )
        event = UserEvent(
            type="reference_image_attached",
            event_id=f"evt_{uuid4().hex[:10]}",
            session_id=request.session_id,
            payload={
                "artifact_id": artifact.artifact_id,
                "artifact_url": artifact.url,
                "asset_id": request.asset_id,
                "role": request.role,
                "filename": request.title,
                "metadata": {"source": "web_search", "remote_url": True},
            },
        )
        studio_store.save_event(event)
        studio_store.save_memory(
            MemoryRecord(
                memory_id=f"mem_{uuid4().hex[:10]}",
                session_id=request.session_id,
                category="working",
                type="reference_image",
                source_id=artifact.artifact_id,
                asset_id=request.asset_id,
                content={
                    "artifact": artifact.model_dump(mode="json"),
                    "event_id": event.event_id,
                    "role": request.role,
                },
                tags=["reference_image", "web_search", request.role],
            )
        )
        await websocket_manager.broadcast(
            request.session_id,
            "reference_image_attached",
            {
                "artifact": artifact.model_dump(mode="json"),
                "event_id": event.event_id,
            },
        )
        return artifact

    @router.get("/api/v1/assets/{asset_id}")
    async def get_asset(asset_id: str) -> object:
        asset = studio_store.get_asset(asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {asset_id}")
        return asset

    @router.get("/api/v1/assets/{asset_id}/export")
    async def export_asset_mesh(asset_id: str, format: str = "glb") -> Response:
        asset = studio_store.get_asset(asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {asset_id}")
        url = export_url_for_format(asset.mesh_url, asset.obj_url, format)
        if not url:
            raise HTTPException(
                status_code=404,
                detail=f"Asset has no exportable {format.upper()} mesh",
            )
        content, content_type = await read_export_artifact(url)
        filename = export_filename(asset.label or asset.asset_id, format)
        return Response(
            content=content,
            media_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.post("/api/v1/assets/{asset_id}/versions")
    async def create_asset_version(
        asset_id: str,
        session_id: str = Form(...),
        parent_version_id: str | None = Form(None),
        edit_ops: str | None = Form(None),
        source: str = Form("sculpt_commit"),
        metadata: str | None = Form(None),
        file: UploadFile | None = File(None),
    ) -> AssetVersionRecord:
        require_session(session_id)
        asset = studio_store.get_asset(asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {asset_id}")
        parsed_edit_ops: list[dict[str, Any]] = []
        if edit_ops:
            try:
                parsed_edit_ops = json.loads(edit_ops)
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=400, detail="edit_ops must be a JSON array") from exc
        parsed_metadata: dict[str, Any] = {}
        if metadata:
            try:
                parsed_metadata = json.loads(metadata)
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=400, detail="metadata must be JSON") from exc
        mesh_url: str | None = None
        obj_url: str | None = None
        thumbnail_url: str | None = None
        version_id = f"ver_{uuid4().hex[:10]}"
        if file is not None:
            suffix = Path(file.filename or "sculpted.obj").suffix.lower()
            if suffix not in {".obj", ".glb"}:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported version file type: {suffix}",
                )
            version_dir = files_root / "assets" / asset_id / "versions"
            version_dir.mkdir(parents=True, exist_ok=True)
            target = version_dir / f"{version_id}{suffix}"
            with target.open("wb") as out:
                shutil.copyfileobj(file.file, out)
            url = f"/files/assets/{asset_id}/versions/{version_id}{suffix}"
            if suffix == ".glb":
                mesh_url = url
            else:
                obj_url = url
        version = studio_store.create_asset_version(
            asset_id,
            version_id=version_id,
            mesh_url=mesh_url,
            obj_url=obj_url,
            thumbnail_url=thumbnail_url,
            edit_ops=parsed_edit_ops,
            parent_version_id=parent_version_id,
            source=source,
            metadata=parsed_metadata,
        )
        await websocket_manager.broadcast(
            session_id,
            "asset_version_created",
            version.model_dump(mode="json"),
        )
        return version

    @router.get("/api/v1/assets/{asset_id}/versions")
    async def list_asset_versions(asset_id: str, limit: int = 50) -> dict[str, list[AssetVersionRecord]]:
        if studio_store.get_asset(asset_id) is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {asset_id}")
        return {"versions": studio_store.list_asset_versions(asset_id, limit=limit)}

    @router.get("/api/v1/assets/{asset_id}/parts")
    async def get_asset_parts(asset_id: str) -> AssetPartsResponse:
        asset = studio_store.get_asset(asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {asset_id}")
        return AssetPartsResponse(asset_id=asset_id, parts=asset.parts)

    @router.patch("/api/v1/assets/{asset_id}/parts/{part_id}")
    async def update_asset_part(
        asset_id: str,
        part_id: str,
        request: PartUpdateRequest,
    ) -> PartRecord:
        asset = studio_store.get_asset(asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {asset_id}")
        for index, part in enumerate(asset.parts):
            if part.part_id != part_id:
                continue
            if request.label is not None:
                part.label = request.label.strip() or part.label
            if request.type is not None:
                part.type = request.type.strip() or part.type
            if request.lifecycle is not None:
                part.lifecycle = request.lifecycle
                part.metadata = {**part.metadata, "lifecycle": request.lifecycle}
            if request.metadata:
                part.metadata = {**part.metadata, **request.metadata}
                if "lifecycle" in request.metadata:
                    part.lifecycle = request.metadata["lifecycle"]
            asset.parts[index] = part
            studio_store.assets[asset_id] = asset
            return part
        raise HTTPException(status_code=404, detail=f"Part not found: {part_id}")

    @router.post("/api/v1/parts/discover")
    async def discover_parts(request: PartDiscoveryRequest) -> PartDiscoveryResponse:
        require_session(request.session_id)
        if studio_store.get_asset(request.asset_id) is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {request.asset_id}")
        try:
            return await autopartgen_adapter.discover_parts(request)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/api/v1/parts/from-mask")
    async def discover_parts_from_mask(request: PartDiscoveryRequest) -> PartDiscoveryResponse:
        request.mode = "image_mask"
        require_session(request.session_id)
        if studio_store.get_asset(request.asset_id) is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {request.asset_id}")
        return await autopartgen_adapter.discover_parts(request)

    return router
