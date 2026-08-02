from __future__ import annotations

import base64
import asyncio
import json
import logging
import re
import shutil
import ssl
import sys
from html import escape
from pathlib import Path
from urllib.parse import quote, unquote, urlparse
from urllib.request import Request as UrlRequest, urlopen
from uuid import UUID, uuid4

logger = logging.getLogger("flowstudio.api")

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api import (
    create_directions_router,
    create_generation_router,
    create_perception_router,
)
from app.api.perception_flow import interpret_and_publish
from app.api.solution_space import build_solution_space_view
from app.config import Settings, get_settings
from app.models import (
    ApiError,
    ApiErrorBody,
    ActionAtom,
    ActionAtomCreateRequest,
    AnnotationArtifactCreateRequest,
    ArtifactListResponse,
    ArtifactRecord,
    AssetCreateRequest,
    AssetPartsResponse,
    BrushMaskArtifactCreateRequest,
    Candidate,
    CandidateDecision,
    CandidateDecisionRequest,
    CandidateDecisionResponse,
    CandidateFitRequest,
    CandidateRequest,
    CandidateResponse,
    BenchmarkAssetListResponse,
    BenchmarkAssetLoadRequest,
    BenchmarkAssetRecord,
    CaseCreateRequest,
    CaseRecord,
    DesignPhase,
    GenerationMode,
    GenerationRequest,
    GeometryWorkerRequest,
    GeometryWorkerResponse,
    InteractionInterpretation,
    AnalogyDirection,
    CrossDomainDivergenceRequest,
    CrossDomainDivergenceResponse,
    DirectionUpdateRequest,
    DragOperationArtifactCreateRequest,
    FocusObservationArtifactCreateRequest,
    IntentDraft,
    IntentDraftCreateRequest,
    IntentEpisodeCreateRequest,
    IntentEpisodeResponse,
    IntentDraftListResponse,
    IntentDraftUpdateRequest,
    JobCreateResponse,
    JobStage,
    JobStatus,
    LegacyJobRecord,
    MemoryListResponse,
    MemoryRecord,
    PartDiscoveryRequest,
    PartDiscoveryResponse,
    PartRecord,
    PartUpdateRequest,
    PlannerInterpretationDecisionRequest,
    PlannerInterpretationDecisionResponse,
    PrimitiveAdditionArtifactCreateRequest,
    PromptComposeRequest,
    PromptComposeResponse,
    RenderPreviewRequest,
    RenderPreviewResponse,
    SmoothOperationArtifactCreateRequest,
    SessionCreateRequest,
    SessionSnapshotResponse,
    SessionRecord,
    SessionUpdateRequest,
    StageState,
    StoreStateImportRequest,
    StoreStateImportResponse,
    StoreStateSnapshot,
    ViewportSegmentationRequest,
    ViewportSegmentationResponse,
    UserEvent,
    WebSocketMessage,
    WorkerJobRecord,
    now_utc,
)
from app.services.creativeflow_adapter import CreativeFlowAdapter
from app.services.autopartgen_adapter import AutoPartGenAdapter
from app.services.generation_orchestrator import (
    GenerationOrchestrator,
    RemoteCreativeFlowWorkerAdapter,
)
from app.services.geometry_worker import GeometryProcessingWorker
from app.services.interaction_understanding import InteractionUnderstandingService
from app.services.job_store import InMemoryJobStore
from app.services.multimodal_intent_predictor import build_multimodal_intent_predictor
from app.services.part_lifecycle import (
    attach_viewport_2d_evidence,
    find_part,
    read_lifecycle,
)
from app.services.render_preview_worker import RenderPreviewWorker
from app.services.studio_store import InMemoryStudioStore
from app.services.websocket_manager import WebSocketManager

legacy_job_store = InMemoryJobStore()
studio_store = InMemoryStudioStore()
websocket_manager = WebSocketManager()
settings = get_settings()
interaction_service = InteractionUnderstandingService(
    studio_store,
    predictor=build_multimodal_intent_predictor(
        settings.iul_vlm_intent_url,
        timeout_sec=settings.iul_vlm_timeout_sec,
        fallback_to_rules=settings.iul_vlm_fallback_to_rules,
        fallback_endpoint_urls=[
            item.strip()
            for item in (settings.iul_vlm_fallback_urls or "").split(",")
            if item.strip()
        ],
        model_name=settings.iul_vlm_model,
    ),
)
remote_worker_adapter = RemoteCreativeFlowWorkerAdapter(
    settings.remote_creativeflow_worker_url,
    real_jobs=settings.remote_creativeflow_real_jobs,
    transfer_variant=settings.remote_creativeflow_transfer_variant,
)
generation_orchestrator = GenerationOrchestrator(
    studio_store,
    websocket_manager,
    remote_worker_adapter,
    auto_hy3d=settings.remote_creativeflow_auto_hy3d,
    hy3d_max_candidates=settings.remote_creativeflow_hy3d_max_candidates,
)
autopartgen_adapter = AutoPartGenAdapter(
    studio_store,
    remote_worker_url=settings.remote_creativeflow_worker_url,
    segmentation_adapter=settings.remote_segmentation_adapter,
    real_segmentation_default=(
        settings.remote_segmentation_real_default and settings.remote_partfield_real_default
    ),
    wait_timeout_sec=settings.remote_partfield_wait_timeout_sec,
    poll_interval_sec=settings.remote_partfield_poll_interval_sec,
)
geometry_worker = GeometryProcessingWorker(remote_worker_adapter)
render_preview_worker = RenderPreviewWorker(remote_worker_adapter)


def api_error(
    code: str,
    message: str,
    status_code: int,
    retryable: bool = False,
    details: dict | None = None,
) -> JSONResponse:
    body = ApiError(
        error=ApiErrorBody(
            code=code,
            message=message,
            retryable=retryable,
            details=details or {},
        )
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


def _compact_evidence_summary(interpretation: InteractionInterpretation) -> list[dict[str, object]]:
    features = interpretation.features if isinstance(interpretation.features, dict) else {}
    signals = features.get("signals") if isinstance(features.get("signals"), dict) else {}
    geometric = signals.get("geometric") if isinstance(signals.get("geometric"), dict) else {}
    semantic = signals.get("semantic") if isinstance(signals.get("semantic"), dict) else {}
    visual = signals.get("visual_context") if isinstance(signals.get("visual_context"), dict) else {}
    interaction = signals.get("interaction") if isinstance(signals.get("interaction"), dict) else {}
    rows: list[dict[str, object]] = [
        {
            "label": "intent",
            "value": interpretation.primary_intent.value,
            "source": "planner",
            "confidence": interpretation.confidence,
        }
    ]

    event_type = interaction.get("event_type") or features.get("event_type")
    if event_type:
        rows.append({"label": "behavior", "value": event_type, "source": "interaction"})
    part_label = semantic.get("part_label") or semantic.get("part_id")
    if part_label:
        rows.append({"label": "target", "value": part_label, "source": "semantic"})
    object_type = semantic.get("object_type")
    if object_type:
        rows.append({"label": "object", "value": object_type, "source": "semantic"})

    evidence_fields = [
        ("focus", "dwell_ms", geometric.get("dwell_ms"), "attention"),
        ("brush", "coverage", geometric.get("brush_coverage"), "surface mask"),
        ("drag", "length", geometric.get("drag_length"), "3d transform"),
        ("smooth", "strength", geometric.get("smooth_strength"), "local geometry"),
        ("add", "primitive", semantic.get("primitive"), "3d primitive"),
    ]
    for group, label, value, source in evidence_fields:
        if value is not None:
            rows.append({"label": f"{group}_{label}", "value": value, "source": source})

    artifact_fields = [
        ("focus_artifact", visual.get("focus_observation_artifact_id")),
        ("brush_artifact", visual.get("brush_mask_artifact_id")),
        ("drag_artifact", visual.get("drag_operation_artifact_id")),
        ("smooth_artifact", visual.get("smooth_operation_artifact_id")),
        ("add_artifact", visual.get("primitive_addition_artifact_id")),
        ("annotation_artifact", visual.get("annotation_artifact_id")),
    ]
    for label, value in artifact_fields:
        if value:
            rows.append({"label": label, "value": value, "source": "artifact"})
            break

    ir = features.get("design_state_ir") if isinstance(features.get("design_state_ir"), dict) else {}
    matches = ir.get("matches") if isinstance(ir.get("matches"), list) else []
    recommended_axes = ir.get("recommended_axes") if isinstance(ir.get("recommended_axes"), list) else []
    if recommended_axes:
        rows.append(
            {
                "label": "next_axes",
                "value": " / ".join(str(axis) for axis in recommended_axes[:3]),
                "source": "design_state_ir",
            }
        )
    if matches and isinstance(matches[0], dict):
        top = matches[0]
        design_state = top.get("design_state") or "matched_design_state"
        route = top.get("route") or "design_state_ir"
        case_id = top.get("case_id") or top.get("ir_id")
        rows.append(
            {
                "label": "ir_state",
                "value": f"{design_state} → {route}",
                "source": f"design_state_ir:{case_id}" if case_id else "design_state_ir",
                "score": top.get("score"),
            }
        )

    return rows[:8]


def _perception_payload(interpretation: InteractionInterpretation) -> dict[str, object]:
    return {
        "perception_id": interpretation.interpretation_id,
        "summary": interpretation.primary_intent.value,
        "behavior_label": interpretation.action_type,
        "confidence": interpretation.confidence,
        "ambiguity": interpretation.ambiguity,
        "evidence": interpretation.evidence,
        "evidence_summary": _compact_evidence_summary(interpretation),
        "features": interpretation.features,
        "created_at": interpretation.created_at.isoformat(),
    }


async def _publish_perception(
    session_id: str,
    interpretation: InteractionInterpretation,
    *,
    include_stage: bool = True,
) -> None:
    """Single broadcast path for interpretation → perception (+ optional stage)."""
    await websocket_manager.broadcast(
        session_id,
        "interaction_interpretation",
        interpretation.model_dump(mode="json"),
    )
    await websocket_manager.broadcast(
        session_id,
        "perception_updated",
        _perception_payload(interpretation),
    )
    if include_stage:
        session = studio_store.get_session(session_id)
        if session is not None:
            await websocket_manager.broadcast(
                session_id,
                "stage_update",
                session.stage.model_dump(mode="json"),
            )


def _log_deprecated_api(endpoint: str, session_id: str | None = None) -> None:
    logger.warning(
        "DEPRECATED_API_USED endpoint=%s session_id=%s",
        endpoint,
        session_id or "-",
    )


_PROMPT_CHIP_MARKERS = {
    "prompt_chip",
    "analogy_keyword",
    "more_creative_prompt_chip",
    "more_creative_token",
    "front_end_more_creative_prompt_chips",
    "prompt_chip_composition",
}


def _looks_like_prompt_chip_action(request: ActionAtomCreateRequest) -> bool:
    """Prompt chips must use /prompt/compose, never ActionAtom history."""
    bags = [request.metadata or {}, request.evidence or {}]
    for bag in bags:
        source = str(bag.get("source") or bag.get("kind") or "").strip().lower()
        if source in _PROMPT_CHIP_MARKERS:
            return True
        if bag.get("selected_prompt_tokens") or bag.get("prompt_chip") or bag.get("analogy_prompt_package"):
            return True
    if request.tool == "text":
        label = str((request.target or {}).get("label") or "").strip().lower()
        if label in {"whole object", "whole_part", "prompt chip", "analogy"}:
            text = str((request.evidence or {}).get("text") or (request.evidence or {}).get("intent_text") or "")
            if "prompt" in text.lower() or "analogy" in text.lower():
                return True
    return False


def _clean_live_signals(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        return {}
    clean: dict[str, object] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            clean[key] = value
    return clean


def _live_signals_payload(session: SessionRecord) -> dict[str, object]:
    signals = session.metadata.get("live_signals")
    return {
        "session_id": session.session_id,
        "live_signals": signals if isinstance(signals, dict) else {},
        "updated_at": session.metadata.get("live_signals_updated_at"),
        "source": session.metadata.get("live_signals_source"),
    }


def _update_session_live_signals(
    session_id: str,
    raw_signals: object,
    source: str,
) -> dict[str, object]:
    clean = _clean_live_signals(raw_signals)
    if not clean:
        return _live_signals_payload(require_session(session_id))
    session = require_session(session_id)
    current = session.metadata.get("live_signals")
    if not isinstance(current, dict):
        current = {}
    updated = {**current, **clean}
    studio_store.update_session(
        session_id,
        SessionUpdateRequest(
            metadata={
                "live_signals": updated,
                "live_signals_updated_at": now_utc().isoformat(),
                "live_signals_source": source,
            }
        ),
    )
    return _live_signals_payload(require_session(session_id))


def _local_creativeflow_state(root: Path | None) -> dict[str, object]:
    if root is None:
        return {
            "root": None,
            "root_exists": False,
            "scripts": {},
            "structured_transfer_ready": False,
            "minimal_transfer_ready": False,
            "legacy_pipeline_ready": False,
            "hy3d_ready": False,
        }
    scripts = {
        "legacy_pipeline": root / "pipeline.py",
        "structured_transfer": root / "pipeline_transfer_engine.py",
        "minimal_transfer": root / "pipeline_transfer_engine_minimal.py",
        "hunyuan3d_post": root / "pipeline_hunyuan3d_post.py",
        "mesh_worker_mv": root / "step4_mesh_worker_mv.py",
    }
    script_state = {
        name: {
            "path": str(path),
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else 0,
        }
        for name, path in scripts.items()
    }
    return {
        "root": str(root),
        "root_exists": root.exists(),
        "scripts": script_state,
        "structured_transfer_ready": scripts["structured_transfer"].exists(),
        "minimal_transfer_ready": scripts["minimal_transfer"].exists(),
        "legacy_pipeline_ready": scripts["legacy_pipeline"].exists(),
        "hy3d_ready": scripts["hunyuan3d_post"].exists()
        and scripts["mesh_worker_mv"].exists(),
    }


def require_session(session_id: str) -> SessionRecord:
    session = studio_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return session


async def create_direction_suggestions(
    request: CrossDomainDivergenceRequest,
    *,
    endpoint_name: str,
) -> CrossDomainDivergenceResponse:
    """Canonical direction builder shared by suggest + deprecated cross-domain proxy."""
    session = require_session(request.session_id)
    asset = studio_store.get_asset(request.asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Asset not found: {request.asset_id}")
    draft = None
    if request.intent_draft_id:
        draft = studio_store.get_intent_draft(request.intent_draft_id)
        if draft is None:
            raise HTTPException(
                status_code=404,
                detail=f"Intent draft not found: {request.intent_draft_id}",
            )
        if draft.session_id != request.session_id:
            raise HTTPException(status_code=400, detail="Intent draft belongs to another session")
    response = _build_cross_domain_response(request, asset, draft, session)
    response.metadata["direction_endpoint"] = endpoint_name
    response.metadata.setdefault("canonical_endpoint", "suggested_analogy_directions")
    response.metadata.setdefault("task", "direction_suggest")
    if request.interpretation_id:
        response.metadata["interpretation_id"] = request.interpretation_id
    for direction in response.directions:
        direction.metadata.setdefault("status", "suggested")
        direction.metadata.setdefault("asset_id", request.asset_id)
        direction.metadata.setdefault("session_id", request.session_id)
        direction.metadata.setdefault("direction_endpoint", endpoint_name)
        studio_store.save_direction(request.session_id, direction)
    studio_store.save_memory(
        MemoryRecord(
            memory_id=f"mem_{uuid4().hex[:10]}",
            session_id=request.session_id,
            category="working",
            type=endpoint_name,
            source_id=request.intent_draft_id,
            asset_id=request.asset_id,
            confidence=0.78,
            content=response.model_dump(mode="json"),
            tags=["cross_domain", "analogy_direction", endpoint_name],
        )
    )
    await websocket_manager.broadcast(
        request.session_id,
        "cross_domain_directions",
        response.model_dump(mode="json"),
    )
    return response


def _validate_optional_session(session_id: str | None) -> None:
    if session_id:
        require_session(session_id)


def _asset_source_reference(asset_id: str | None) -> str | None:
    if not asset_id:
        return None
    asset = studio_store.get_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Asset not found: {asset_id}")
    storage_path = asset.metadata.get("storage_path")
    if isinstance(storage_path, str) and storage_path:
        return storage_path
    remote_asset = asset.metadata.get("remote_asset")
    if isinstance(remote_asset, dict) and remote_asset.get("path"):
        return str(remote_asset["path"])
    return asset.obj_url or asset.mesh_url


def _candidate_mesh_reference(candidate_id: str | None) -> str | None:
    if not candidate_id:
        return None
    candidate = studio_store.get_candidate(candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail=f"Candidate not found: {candidate_id}")
    return candidate.obj_url or candidate.mesh_url


def _candidate_direction_ids(candidate: Candidate) -> list[str]:
    values: list[str] = []
    direct = candidate.metadata.get("direction_id")
    if isinstance(direct, str) and direct:
        values.append(direct)
    evidence = candidate.metadata.get("pipeline_evidence")
    if isinstance(evidence, dict):
        raw = evidence.get("analogy_direction_ids")
        if isinstance(raw, list):
            values.extend(str(item) for item in raw if item)
        evidence_direction = evidence.get("direction_id")
        if isinstance(evidence_direction, str) and evidence_direction:
            values.append(evidence_direction)
    package = candidate.metadata.get("analogy_prompt_package")
    if isinstance(package, dict) and isinstance(package.get("direction_ids"), list):
        values.extend(str(item) for item in package["direction_ids"] if item)
    return list(dict.fromkeys(values))


def _export_url_for_format(mesh_url: str | None, obj_url: str | None, export_format: str) -> str | None:
    normalized = export_format.strip().lower().lstrip(".")
    if normalized in {"glb", "gltf"}:
        if mesh_url and infer_mesh_extension(mesh_url) in {"glb", "gltf"}:
            return mesh_url
        return None
    if normalized == "obj":
        if obj_url and infer_mesh_extension(obj_url) == "obj":
            return obj_url
        if mesh_url and infer_mesh_extension(mesh_url) == "obj":
            return mesh_url
        return None
    raise HTTPException(status_code=400, detail="format must be glb or obj")


def infer_mesh_extension(url: str) -> str:
    path = urlparse(url).path
    if "path=" in url:
        parsed = urlparse(url)
        query_path = unquote(parsed.query.removeprefix("path="))
        path = query_path or path
    suffix = Path(path).suffix.lower().lstrip(".")
    return suffix


def _export_filename(label: str, export_format: str) -> str:
    normalized = export_format.strip().lower().lstrip(".")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", label).strip("._-") or "flowstudio_export"
    return f"{safe[:80]}.{normalized}"


async def _read_export_artifact(url: str) -> tuple[bytes, str]:
    if url.startswith("/api/v1/remote-worker/artifact-file"):
        parsed = urlparse(url)
        path = ""
        for item in parsed.query.split("&"):
            key, _, value = item.partition("=")
            if key == "path":
                path = unquote(value)
                break
        if not path:
            raise HTTPException(status_code=400, detail="Remote artifact URL is missing path")
        try:
            return await remote_worker_adapter.get_artifact_file(path)
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    if url.startswith("/files/"):
        storage_root = Path(__file__).resolve().parents[1] / "storage"
        files_root = (storage_root / "files").resolve()
        local_path = (files_root / unquote(url.removeprefix("/files/"))).resolve()
        if files_root not in local_path.parents and local_path != files_root:
            raise HTTPException(status_code=400, detail="Invalid local export path")
        if not local_path.exists() or not local_path.is_file():
            raise HTTPException(status_code=404, detail=f"Export file not found: {url}")
        return local_path.read_bytes(), _mesh_content_type(infer_mesh_extension(str(local_path)))
    if url.startswith("http://") or url.startswith("https://"):
        try:
            with urlopen(url, timeout=60) as response:
                content_type = response.headers.get_content_type() or _mesh_content_type(infer_mesh_extension(url))
                return response.read(), content_type
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Could not fetch export URL: {exc}") from exc
    raise HTTPException(status_code=400, detail=f"Unsupported export URL: {url}")


def _mesh_content_type(extension: str) -> str:
    if extension in {"glb", "gltf"}:
        return "model/gltf-binary" if extension == "glb" else "model/gltf+json"
    if extension == "obj":
        return "text/plain"
    return "application/octet-stream"


def _session_id_for_direction(direction_id: str) -> str:
    for session_id, direction_ids in studio_store.session_directions.items():
        if direction_id in direction_ids:
            return session_id
    raise HTTPException(status_code=400, detail="Direction is missing session provenance")


def _build_prompt_chip_package(request: PromptComposeRequest) -> dict[str, object]:
    base_prompt = re.sub(r"\s+", " ", request.base_prompt or "").strip()
    tokens: list[dict[str, object]] = []
    seen_labels: set[str] = set()
    inferred_direction_ids: list[str] = []
    for raw in request.selected_prompt_tokens:
        label = re.sub(
            r"\s+",
            " ",
            str(raw.get("label") or raw.get("text") or raw.get("value") or ""),
        ).strip(" ,.;")
        if not label or label.lower() in seen_labels:
            continue
        seen_labels.add(label.lower())
        source_direction_id = raw.get("source_direction_id") or raw.get("direction_id")
        if isinstance(source_direction_id, str) and source_direction_id:
            inferred_direction_ids.append(source_direction_id)
        weight = raw.get("weight")
        tokens.append(
            {
                "token_id": str(raw.get("token_id") or f"tok_user_{uuid4().hex[:8]}"),
                "label": label[:80],
                "dimension": str(raw.get("dimension") or "Cross-domain")[:40],
                "role": str(raw.get("role") or "keyword")[:40],
                "source_direction_id": source_direction_id if isinstance(source_direction_id, str) else None,
                "weight": float(weight) if isinstance(weight, (int, float)) else None,
            }
        )
    direction_ids = list(dict.fromkeys([*request.direction_ids, *inferred_direction_ids]))
    selected_directions: list[dict[str, object]] = []
    for direction_id in direction_ids:
        direction = studio_store.get_direction(direction_id)
        if direction is None:
            continue
        selected_directions.append(
            {
                "direction_id": direction.direction_id,
                "label": direction.label,
                "dimension": direction.dimension,
                "source_domain": direction.source_domain,
                "target_domain": direction.target_domain,
                "relation": direction.relation,
                "transfer_rationale": direction.transfer_rationale,
                "constraints": direction.constraints,
                "score": direction.score,
            }
        )
    selected_prompt_text = ", ".join(str(token["label"]) for token in tokens)
    final_prompt = base_prompt
    if selected_prompt_text and selected_prompt_text.lower() not in base_prompt.lower():
        final_prompt = f"{base_prompt}\nAnalogy keywords: {selected_prompt_text}".strip()
    return {
        "prompt_token_mode": "human_selectable_chips",
        "source": "backend_prompt_compose",
        "final_prompt": final_prompt,
        "selected_prompt_text": selected_prompt_text,
        "selected_prompt_tokens": tokens,
        "direction_ids": direction_ids,
        "selected_directions": selected_directions,
        "intent_draft_id": request.intent_draft_id,
        "metadata": request.metadata,
    }


def _decode_data_url(value: str) -> bytes:
    if "," in value and value.strip().lower().startswith("data:"):
        value = value.split(",", 1)[1]
    try:
        return base64.b64decode(value, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid image_data_url") from exc


async def _poll_remote_worker_job(job_id: str, timeout_sec: float = 35) -> dict[str, object]:
    if not job_id:
        return {"status": "failed", "error": "Remote worker did not return a job_id"}
    base_url = settings.remote_creativeflow_worker_url.rstrip("/")
    deadline = asyncio.get_running_loop().time() + timeout_sec
    latest: dict[str, object] = {"job_id": job_id, "status": "queued"}
    while asyncio.get_running_loop().time() < deadline:
        latest = await asyncio.to_thread(_get_remote_worker_job_sync, base_url, job_id)
        if latest.get("status") in {"completed", "failed", "cancelled"}:
            return latest
        await asyncio.sleep(1.0)
    latest["timeout"] = True
    return latest


def _get_remote_worker_job_sync(base_url: str, job_id: str) -> dict[str, object]:
    with urlopen(f"{base_url}/jobs/{quote(job_id, safe='')}", timeout=10) as response:
        data = response.read().decode("utf-8")
    value = json.loads(data) if data else {}
    return value if isinstance(value, dict) else {"status": "failed", "error": "Invalid worker job response"}


def _hydrate_geometry_request(request: GeometryWorkerRequest) -> None:
    if not request.source_mesh_path and not request.source_mesh_url:
        source = _asset_source_reference(request.asset_id)
        if source:
            if source.startswith("/files/") or source.startswith("/api/"):
                request.source_mesh_url = source
            else:
                request.source_mesh_path = source
    if not request.candidate_mesh_path and not request.candidate_mesh_url:
        candidate = _candidate_mesh_reference(request.candidate_id)
        if candidate:
            if candidate.startswith("/files/") or candidate.startswith("/api/"):
                request.candidate_mesh_url = candidate
            else:
                request.candidate_mesh_path = candidate


def _hydrate_render_request(request: RenderPreviewRequest) -> None:
    if not request.source_mesh_path and not request.source_mesh_url:
        source = _asset_source_reference(request.asset_id)
        if source:
            if source.startswith("/files/") or source.startswith("/api/"):
                request.source_mesh_url = source
            else:
                request.source_mesh_path = source
    if not request.candidate_mesh_path and not request.candidate_mesh_url:
        candidate = _candidate_mesh_reference(request.candidate_id)
        if candidate:
            if candidate.startswith("/files/") or candidate.startswith("/api/"):
                request.candidate_mesh_url = candidate
            else:
                request.candidate_mesh_path = candidate


def _part_id_from_payload(part: dict | None) -> str | None:
    if isinstance(part, dict) and part.get("part_id"):
        return str(part["part_id"])
    return None


def _register_worker_artifacts(
    *,
    worker: str,
    response: GeometryWorkerResponse | RenderPreviewResponse,
    request: GeometryWorkerRequest | RenderPreviewRequest,
) -> list[ArtifactRecord]:
    if not response.ok:
        return []
    urls: list[tuple[str, str]] = []
    if isinstance(response, GeometryWorkerResponse):
        if response.result_mesh_url:
            urls.append(("result_mesh", response.result_mesh_url))
        if response.preview_mesh_url and response.preview_mesh_url != response.result_mesh_url:
            urls.append(("preview_mesh", response.preview_mesh_url))
        for key, value in response.artifacts.items():
            if isinstance(value, str) and value.startswith("/files/"):
                urls.append((key, value))
            elif isinstance(value, dict) and isinstance(value.get("url"), str):
                urls.append((key, value["url"]))
    else:
        if response.thumbnail_url:
            urls.append(("thumbnail", response.thumbnail_url))
        for key, value in response.views.items():
            if value.startswith("/files/") or value.startswith("/api/v1/remote-worker/artifact-file"):
                urls.append((f"view_{key}", value))
        if response.turntable_video_url:
            urls.append(("turntable", response.turntable_video_url))
        for key, value in response.artifacts.items():
            if isinstance(value, str) and value.startswith("/files/"):
                urls.append((key, value))
            elif isinstance(value, dict) and isinstance(value.get("url"), str):
                urls.append((key, value["url"]))
    deduped: dict[str, str] = {}
    for artifact_type, url in urls:
        deduped.setdefault(url, artifact_type)
    records = [
        studio_store.save_artifact(
            ArtifactRecord(
                artifact_id=f"art_{uuid4().hex[:10]}",
                type=artifact_type,
                url=url,
                session_id=request.session_id,
                asset_id=request.asset_id,
                candidate_id=request.candidate_id,
                part_id=_part_id_from_payload(request.part),
                worker=worker,  # type: ignore[arg-type]
                job_id=response.job_id,
                operation=response.operation,
                metrics=response.metrics if isinstance(response, GeometryWorkerResponse) else {},
                metadata=response.metadata if isinstance(response, RenderPreviewResponse) else {},
            )
        )
        for url, artifact_type in deduped.items()
    ]
    return records


def _save_worker_job(
    *,
    worker: str,
    request: GeometryWorkerRequest | RenderPreviewRequest,
    response: GeometryWorkerResponse | RenderPreviewResponse,
    artifacts: list[ArtifactRecord],
) -> WorkerJobRecord:
    return studio_store.save_worker_job(
        WorkerJobRecord(
            job_id=response.job_id,
            worker=worker,  # type: ignore[arg-type]
            operation=response.operation,
            status=response.status,
            ok=response.ok,
            session_id=request.session_id,
            asset_id=request.asset_id,
            candidate_id=request.candidate_id,
            request=request.model_dump(mode="json"),
            response=response.model_dump(mode="json"),
            artifact_ids=[artifact.artifact_id for artifact in artifacts],
            error=response.error,
        )
    )


async def cancel_remote_worker_jobs(job: object) -> list[dict[str, object]]:
    metadata = getattr(job, "metadata", {})
    if not isinstance(metadata, dict):
        return []
    remote_job_ids: list[str] = []
    for key in ("remote_transfer", "remote_staged_creativeflow", "remote_hy3d"):
        value = metadata.get(key)
        if isinstance(value, dict):
            remote_job_id = value.get("job_id") or value.get("remote_job_id")
            if isinstance(remote_job_id, str) and remote_job_id:
                remote_job_ids.append(remote_job_id)
    results: list[dict[str, object]] = []
    for remote_job_id in dict.fromkeys(remote_job_ids):
        try:
            result = await remote_worker_adapter.cancel_job(remote_job_id)
            results.append(
                {
                    "remote_job_id": remote_job_id,
                    "status": result.get("status"),
                    "stage": result.get("stage"),
                    "ok": True,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "remote_job_id": remote_job_id,
                    "ok": False,
                    "error": str(exc),
                }
            )
    return results


def create_app() -> FastAPI:
    app = FastAPI(title="FlowStudio Backend", version="0.1.0")
    storage_root = Path(__file__).resolve().parents[1] / "storage"
    files_root = storage_root / "files"
    files_root.mkdir(parents=True, exist_ok=True)
    state_root = storage_root / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    state_snapshot_path = state_root / "latest.json"
    if "pytest" not in sys.modules:
        try:
            studio_store.configure_persistence(state_snapshot_path, load_existing=True)
        except Exception:
            broken_path = state_root / f"latest.broken.{uuid4().hex[:8]}.json"
            if state_snapshot_path.exists():
                shutil.move(str(state_snapshot_path), str(broken_path))
            studio_store.configure_persistence(state_snapshot_path, load_existing=False)
    app.mount("/files", StaticFiles(directory=str(files_root)), name="files")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(
        create_perception_router(
            require_session=require_session,
            studio_store=studio_store,
            websocket_manager=websocket_manager,
            interaction_service=interaction_service,
            publish_perception=_publish_perception,
            update_session_live_signals=_update_session_live_signals,
            live_signals_payload=_live_signals_payload,
            perception_payload=_perception_payload,
            compact_evidence_summary=_compact_evidence_summary,
        )
    )
    app.include_router(
        create_directions_router(
            require_session=require_session,
            studio_store=studio_store,
            log_deprecated_api=_log_deprecated_api,
            create_direction_suggestions=create_direction_suggestions,
        )
    )
    app.include_router(
        create_generation_router(
            require_session=require_session,
            studio_store=studio_store,
            legacy_job_store=legacy_job_store,
            generation_orchestrator=generation_orchestrator,
            websocket_manager=websocket_manager,
            log_deprecated_api=_log_deprecated_api,
            cancel_remote_worker_jobs=cancel_remote_worker_jobs,
        )
    )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        code = "NOT_FOUND" if exc.status_code == 404 else "INVALID_REQUEST"
        return api_error(code, detail, exc.status_code)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return """
        <!doctype html>
        <html lang="en">
          <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <title>FlowStudio Backend</title>
            <style>
              body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 48px; line-height: 1.5; color: #172033; }
              main { max-width: 780px; }
              code { background: #eef2f7; border-radius: 6px; padding: 2px 6px; }
              a { color: #1d5fd3; }
            </style>
          </head>
          <body>
            <main>
              <h1>FlowStudio Backend</h1>
              <p>The API server is running.</p>
              <p>Open <a href="/docs"><code>/docs</code></a> or call <a href="/health"><code>/health</code></a>.</p>
              <p>Main endpoints: <code>/api/v1/sessions</code>, <code>/api/v1/generation/replace</code>, <code>/ws/sessions/{session_id}</code>.</p>
            </main>
          </body>
        </html>
        """

    @app.get("/health")
    async def health(settings: Settings = Depends(get_settings)) -> dict[str, object]:
        local_adapter = CreativeFlowAdapter(settings.creativeflow_root)
        remote_health: dict[str, object] | None = None
        if remote_worker_adapter.is_configured:
            try:
                remote_health = await remote_worker_adapter.health()
            except Exception as exc:
                remote_health = {"ok": False, "error": str(exc)}
        remote_ok = bool(remote_health and remote_health.get("ok"))
        # Canonical generation readiness is remote worker, not local CreativeFlow stub.
        creativeflow_ready = remote_ok or local_adapter.is_configured
        return {
            "status": "ok",
            "architecture": {
                "generation_path": "remote_worker",
                "job_store": "studio_store",
                "legacy_job_store": "read_only_fallback",
                "local_creativeflow_adapter": "frozen_legacy",
                "canonical_generation": "/api/v1/generation/*",
                "canonical_directions": "/api/v1/directions/suggest",
            },
            "creativeflow_configured": creativeflow_ready,
            "creativeflow_root": str(settings.creativeflow_root)
            if settings.creativeflow_root
            else None,
            "creativeflow_local": {
                **_local_creativeflow_state(settings.creativeflow_root),
                "legacy_adapter_frozen": True,
                "note": "Local CreativeFlowAdapter is frozen; use REMOTE_CREATIVEFLOW_WORKER_URL.",
            },
            "remote_worker_configured": remote_worker_adapter.is_configured,
            "remote_worker_ok": remote_ok,
            "remote_creativeflow_pipeline": remote_health.get("creativeflow_pipeline")
            if remote_health
            else None,
            "interaction_understanding": {
                "predictor": interaction_service.predictor.name,
                "predictor_version": interaction_service.predictor.version,
                "vlm_configured": bool(settings.iul_vlm_intent_url),
                "vlm_intent_url": settings.iul_vlm_intent_url,
                "planner_model": settings.iul_vlm_model,
                "fallback_endpoint_count": len(
                    [
                        item.strip()
                        for item in (settings.iul_vlm_fallback_urls or "").split(",")
                        if item.strip()
                    ]
                ),
            },
            "workers": {
                "geometry_processing": {
                    "ok": True,
                    "mode": "local_service_boundary",
                },
                "render_preview": {
                    "ok": bool(render_preview_worker.blender_bin)
                    or bool((remote_health or {}).get("render_preview_ready")),
                    "engine": "blender",
                    "blender_bin": render_preview_worker.blender_bin,
                    "mode": "local_blender"
                    if render_preview_worker.blender_bin
                    else (
                        "remote_worker"
                        if (remote_health or {}).get("render_preview_ready")
                        else "unavailable"
                    ),
                    "remote_blender_bin": (remote_health or {}).get("blender_bin"),
                },
            },
            "sessions": len(studio_store.sessions),
            "jobs": len(studio_store.jobs),
        }

    @app.get("/api/v1/remote-worker/health")
    async def remote_worker_health() -> dict[str, object]:
        try:
            return await remote_worker_adapter.health()
        except Exception as exc:
            return {
                "ok": False,
                "configured": remote_worker_adapter.is_configured,
                "error": str(exc),
            }

    @app.get("/api/v1/remote-worker/preflight")
    async def remote_worker_preflight() -> dict[str, object]:
        try:
            return await remote_worker_adapter.creativeflow_preflight()
        except Exception as exc:
            return {
                "ok": False,
                "configured": remote_worker_adapter.is_configured,
                "error": str(exc),
            }

    @app.get("/api/v1/remote-worker/artifact-file")
    async def remote_worker_artifact_file(path: str) -> Response:
        try:
            content, content_type = await remote_worker_adapter.get_artifact_file(path)
            return Response(content=content, media_type=content_type)
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/api/v1/viewport-segmentation")
    async def create_viewport_segmentation(
        request: ViewportSegmentationRequest,
    ) -> ViewportSegmentationResponse:
        require_session(request.session_id)
        if request.asset_id and studio_store.get_asset(request.asset_id) is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {request.asset_id}")
        if not remote_worker_adapter.is_configured:
            raise HTTPException(status_code=503, detail="Remote worker is not configured")
        artifact_id = f"art_{uuid4().hex[:10]}"
        target_dir = files_root / "viewport-segmentations" / artifact_id
        target_dir.mkdir(parents=True, exist_ok=True)
        image_path = target_dir / "viewport.png"
        image_path.write_bytes(_decode_data_url(request.image_data_url))
        point_x = float(request.point.get("x", 0.5))
        point_y = float(request.point.get("y", 0.5))
        remote_job = await remote_worker_adapter._post_json(
            "/jobs/viewport-sam",
            {
                "flowstudio_job_id": f"viewport_sam_{artifact_id}",
                "image_path": str(image_path),
                "point_x": point_x,
                "point_y": point_y,
                "session_id": request.session_id,
                "asset_id": request.asset_id,
                "part_id": request.part_id,
                "label": request.label,
                "metadata": request.metadata,
            },
        )
        worker_job_id = str(remote_job.get("job_id") or "")
        worker_result = await _poll_remote_worker_job(worker_job_id, timeout_sec=35)
        result_json = (
            worker_result.get("result", {}).get("result_json")
            if isinstance(worker_result.get("result"), dict)
            else None
        )
        result_json = result_json if isinstance(result_json, dict) else {}
        mask_path = result_json.get("mask_path")
        overlay_path = result_json.get("overlay_path")
        mask_url = (
            f"/api/v1/remote-worker/artifact-file?path={quote(str(mask_path), safe='')}"
            if mask_path
            else None
        )
        overlay_url = (
            f"/api/v1/remote-worker/artifact-file?path={quote(str(overlay_path), safe='')}"
            if overlay_path
            else None
        )
        artifact = studio_store.save_artifact(
            ArtifactRecord(
                artifact_id=artifact_id,
                type="viewport_segmentation_mask",
                url=mask_url or f"/files/viewport-segmentations/{artifact_id}/viewport.png",
                session_id=request.session_id,
                asset_id=request.asset_id,
                part_id=request.part_id,
                worker="remote",
                operation="point_prompt_2d_segmentation",
                metadata={
                    "label": request.label,
                    "viewport": request.viewport,
                    "point": request.point,
                    "source_image_path": str(image_path),
                    "mask_url": mask_url,
                    "overlay_url": overlay_url,
                    "worker_job_id": worker_job_id,
                    "worker_result": worker_result,
                    "note": "2D viewport mask only; project to mesh before treating it as a stable 3D part.",
                    **request.metadata,
                },
            )
        )
        event = UserEvent(
            type="viewport_segmentation_completed",
            event_id=f"evt_{uuid4().hex[:10]}",
            session_id=request.session_id,
            payload={
                "asset_id": request.asset_id,
                "part_id": request.part_id,
                "selected_part_label": request.label,
                "artifact_id": artifact.artifact_id,
                "mask_url": mask_url,
                "overlay_url": overlay_url,
                "worker_job_id": worker_job_id,
                "segmentation_source": "viewport_sam_2d",
                "mask_coverage": result_json.get("mask_coverage"),
                "live_signals": {
                    "hover_count": 1,
                    "mask_coverage": result_json.get("mask_coverage") or 0,
                },
                "signals": {
                    "interaction": {"mode": "viewport_sam_hover"},
                    "semantic": {
                        "part_id": request.part_id,
                        "part_label": request.label,
                        "semantic_source": "viewport_sam_2d_tentative",
                    },
                },
            },
        )
        studio_store.save_event(event)

        part_lifecycle = None
        updated_part = None
        if request.asset_id and request.part_id:
            asset = studio_store.get_asset(request.asset_id)
            if asset is not None:
                target_part = find_part(asset.parts, request.part_id)
                if target_part is not None:
                    coverage = result_json.get("mask_coverage")
                    coverage_value = float(coverage) if isinstance(coverage, (int, float)) else None
                    previous_lifecycle = read_lifecycle(target_part)
                    updated_part = attach_viewport_2d_evidence(
                        target_part,
                        artifact_id=artifact.artifact_id,
                        mask_url=mask_url,
                        overlay_url=overlay_url,
                        mask_coverage=coverage_value,
                    )
                    part_lifecycle = read_lifecycle(updated_part)
                    # Phase B invariant: viewport SAM must not invent segmented_3d.
                    if previous_lifecycle != "segmented_3d" and part_lifecycle == "segmented_3d":
                        raise HTTPException(
                            status_code=500,
                            detail="viewport-sam incorrectly promoted part to segmented_3d",
                        )
                    asset.parts = [
                        updated_part if part.part_id == target_part.part_id else part
                        for part in asset.parts
                    ]
                    studio_store.assets[asset.asset_id] = asset

        await websocket_manager.broadcast(
            request.session_id,
            "viewport_segmentation_updated",
            {
                "artifact": artifact.model_dump(mode="json"),
                "event_id": event.event_id,
                "result": result_json,
                "worker_job": worker_result,
                "part_lifecycle": part_lifecycle,
                "part": updated_part.model_dump(mode="json") if updated_part else None,
                "note": "2D viewport mask only; not a stable 3D part.",
            },
        )
        return ViewportSegmentationResponse(
            session_id=request.session_id,
            asset_id=request.asset_id,
            part_id=request.part_id,
            status=str(worker_result.get("status") or remote_job.get("status") or "queued"),
            mask_url=mask_url,
            overlay_url=overlay_url,
            artifact_id=artifact.artifact_id,
            worker_job_id=worker_job_id,
            result=result_json,
            metadata={
                "worker_job": worker_result,
                "source_image_url": f"/files/viewport-segmentations/{artifact_id}/viewport.png",
                "part_lifecycle": part_lifecycle,
                "is_segmented_3d": False,
                "lifecycle_note": (
                    "viewport_sam attaches 2D evidence only; lifecycle becomes "
                    "viewport_2d_mask (or stays segmented_3d if already true 3D)."
                ),
            },
        )

    @app.get("/api/v1/assets/{asset_id}/export")
    async def export_asset_mesh(asset_id: str, format: str = "glb") -> Response:
        asset = studio_store.get_asset(asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {asset_id}")
        url = _export_url_for_format(asset.mesh_url, asset.obj_url, format)
        if not url:
            raise HTTPException(
                status_code=404,
                detail=f"Asset has no exportable {format.upper()} mesh",
            )
        content, content_type = await _read_export_artifact(url)
        filename = _export_filename(asset.label or asset.asset_id, format)
        return Response(
            content=content,
            media_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/v1/candidates/{candidate_id}/export")
    async def export_candidate_mesh(candidate_id: str, format: str = "glb") -> Response:
        candidate = studio_store.get_candidate(candidate_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail=f"Candidate not found: {candidate_id}")
        url = _export_url_for_format(candidate.mesh_url, candidate.obj_url, format)
        if not url:
            raise HTTPException(
                status_code=404,
                detail=f"Candidate has no exportable {format.upper()} mesh",
            )
        content, content_type = await _read_export_artifact(url)
        filename = _export_filename(candidate.label or candidate.candidate_id, format)
        return Response(
            content=content,
            media_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.post("/api/v1/sessions")
    async def create_session(request: SessionCreateRequest) -> SessionRecord:
        return studio_store.create_session(request)

    @app.get("/api/v1/sessions/{session_id}")
    async def get_session(session_id: str) -> SessionRecord:
        return require_session(session_id)

    @app.get("/api/v1/sessions/{session_id}/memory")
    async def get_session_memory(session_id: str) -> dict[str, object]:
        session = require_session(session_id)
        recent_events = studio_store.recent_events(session_id, limit=12)
        recent_interpretations = studio_store.recent_interpretations(session_id, limit=12)
        return {
            "session_id": session_id,
            "stage": session.stage.model_dump(mode="json"),
            "candidate_memory": session.metadata.get("candidate_memory", {}),
            "structured_memory": {
                category: [item.model_dump(mode="json") for item in rows]
                for category, rows in studio_store.memory_by_category(session_id, limit_per_category=8).items()
            },
            "recent_events": [
                {
                    "event_id": event.event_id,
                    "type": event.type,
                    "timestamp": event.timestamp.isoformat(),
                    "asset_id": event.payload.get("asset_id"),
                    "part_id": event.payload.get("part_id")
                    or (event.payload.get("selection") or {}).get("part_id"),
                    "creative_stage": event.payload.get("creative_stage")
                    or (event.payload.get("generation") or {}).get("metadata", {}).get("stage"),
                    "fidelity": event.payload.get("fidelity")
                    or (event.payload.get("generation") or {}).get("metadata", {}).get("fidelity"),
                    "candidate_id": event.payload.get("candidate_id"),
                }
                for event in recent_events
            ],
            "recent_interpretations": [
                {
                    "interpretation_id": item.interpretation_id,
                    "source_event_id": item.source_event_id,
                    "action_type": item.action_type,
                    "predictor": item.predictor,
                    "predictor_version": item.predictor_version,
                    "primary_intent": item.primary_intent.value,
                    "confidence": item.confidence,
                    "ambiguity": item.ambiguity,
                    "assistance_policy": item.assistance_policy.value,
                    "target": item.target.model_dump(mode="json"),
                }
                for item in recent_interpretations
            ],
        }

    @app.get("/api/v1/sessions/{session_id}/snapshot")
    async def get_session_snapshot(session_id: str) -> SessionSnapshotResponse:
        session = require_session(session_id)
        active_asset = studio_store.get_asset(session.stage.active_asset_id) if session.stage.active_asset_id else None
        active_job = studio_store.recent_session_job(session_id)
        visible_candidates: list[Candidate] = []
        if active_job:
            visible_candidates = [
                candidate
                for candidate_id in active_job.candidate_ids[:12]
                if (candidate := studio_store.get_candidate(candidate_id)) is not None
            ]
        artifacts = studio_store.list_artifacts(
            session_id=session_id,
            asset_id=active_asset.asset_id if active_asset else None,
            limit=50,
        )
        if active_job:
            for candidate in visible_candidates:
                artifacts.extend(
                    studio_store.list_artifacts(
                        session_id=session_id,
                        candidate_id=candidate.candidate_id,
                        limit=20,
                    )
                )
        deduped = {artifact.artifact_id: artifact for artifact in artifacts}
        return SessionSnapshotResponse(
            session=session,
            active_asset=active_asset,
            active_parts=active_asset.parts if active_asset else [],
            active_job=active_job,
            live_signals=_live_signals_payload(session)["live_signals"],
            visible_candidates=visible_candidates,
            recent_events=studio_store.recent_events(session_id, limit=20),
            recent_interpretations=studio_store.recent_interpretations(session_id, limit=20),
            artifacts=list(deduped.values())[:80],
            intent_drafts=studio_store.list_intent_drafts(session_id, include_archived=True),
            action_atoms=studio_store.list_action_atoms(session_id, limit=100),
            directions=studio_store.list_directions(session_id, limit=100),
            memory=studio_store.memory_by_category(session_id, limit_per_category=12),
            solution_space=build_solution_space_view(studio_store, session, limit=50),
        )

    @app.get("/api/v1/sessions/{session_id}/memories")
    async def list_session_memories(
        session_id: str,
        category: str | None = None,
        asset_id: str | None = None,
        part_id: str | None = None,
        candidate_id: str | None = None,
        limit: int = 100,
    ) -> MemoryListResponse:
        require_session(session_id)
        return MemoryListResponse(
            memories=studio_store.list_memories(
                session_id=session_id,
                category=category,
                asset_id=asset_id,
                part_id=part_id,
                candidate_id=candidate_id,
                limit=limit,
            )
        )

    @app.get("/api/v1/artifacts")
    async def list_artifacts(
        session_id: str | None = None,
        asset_id: str | None = None,
        candidate_id: str | None = None,
        worker: str | None = None,
        type: str | None = None,
        limit: int = 100,
    ) -> ArtifactListResponse:
        return ArtifactListResponse(
            artifacts=studio_store.list_artifacts(
                session_id=session_id,
                asset_id=asset_id,
                candidate_id=candidate_id,
                worker=worker,
                artifact_type=type,
                limit=limit,
            )
        )

    @app.get("/api/v1/artifacts/{artifact_id}")
    async def get_artifact(artifact_id: str) -> ArtifactRecord:
        artifact = studio_store.get_artifact(artifact_id)
        if artifact is None:
            raise HTTPException(status_code=404, detail=f"Artifact not found: {artifact_id}")
        return artifact

    @app.get("/api/v1/admin/state/export")
    async def export_store_state() -> StoreStateSnapshot:
        return studio_store.export_state()

    @app.post("/api/v1/admin/state/import")
    async def import_store_state(request: StoreStateImportRequest) -> StoreStateImportResponse:
        try:
            return studio_store.import_state(request.snapshot, replace=request.replace)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/v1/interpretations/{interpretation_id}/decision")
    async def decide_planner_interpretation(
        interpretation_id: str,
        request: PlannerInterpretationDecisionRequest,
    ) -> PlannerInterpretationDecisionResponse:
        session = require_session(request.session_id)
        interpretation = studio_store.get_interpretation(interpretation_id)
        if interpretation is None:
            raise HTTPException(
                status_code=404,
                detail=f"Interpretation not found: {interpretation_id}",
            )
        if interpretation.session_id != request.session_id:
            raise HTTPException(
                status_code=400,
                detail="Interpretation does not belong to the supplied session",
            )

        event_type = f"planner_interpretation_{request.decision}"
        event = UserEvent(
            type=event_type,
            event_id=f"evt_{uuid4().hex[:10]}",
            session_id=request.session_id,
            payload={
                "interpretation_id": interpretation.interpretation_id,
                "decision": request.decision,
                "reason": request.reason,
                "primary_intent": interpretation.primary_intent.value,
                "confidence": interpretation.confidence,
                "ambiguity": interpretation.ambiguity,
                "assistance_policy": interpretation.assistance_policy.value,
                "target": interpretation.target.model_dump(mode="json"),
                "suggested_assistance": [
                    item.model_dump(mode="json") for item in interpretation.suggested_assistance
                ],
                "metadata": request.metadata,
                "asset_id": interpretation.target.asset_id,
                "part_id": interpretation.target.part_id,
            },
        )
        studio_store.save_event(event)

        memory = MemoryRecord(
            memory_id=f"mem_{uuid4().hex[:10]}",
            session_id=request.session_id,
            category="reflective",
            type=event_type,
            source_id=interpretation.interpretation_id,
            asset_id=interpretation.target.asset_id,
            part_id=interpretation.target.part_id,
            candidate_id=interpretation.features.get("candidate_id")
            if isinstance(interpretation.features, dict)
            else None,
            confidence=interpretation.confidence,
            content={
                "decision": request.decision,
                "reason": request.reason,
                "primary_intent": interpretation.primary_intent.value,
                "assistance_policy": interpretation.assistance_policy.value,
                "suggested_assistance": [
                    item.model_dump(mode="json") for item in interpretation.suggested_assistance
                ],
                "evidence": interpretation.evidence,
                "metadata": request.metadata,
            },
            tags=["planner_control_gate", request.decision, interpretation.primary_intent.value],
        )
        studio_store.save_memory(memory)

        stage = session.stage
        if request.decision == "accepted":
            stage.confidence = interpretation.confidence
            stage.current_goal = f"Accepted planner intent: {interpretation.primary_intent.value}"
            stage.active_asset_id = interpretation.target.asset_id or stage.active_asset_id
            stage.active_part_id = interpretation.target.part_id or stage.active_part_id
            if interpretation.suggested_assistance:
                suggestion = interpretation.suggested_assistance[0]
                stage.suggested_action = str(
                    suggestion.metadata.get("suggested_next_action")
                    or suggestion.label
                    or suggestion.type
                )
            else:
                stage.suggested_action = "continue_with_confirmed_intent"
            if stage.phase == DesignPhase.idle:
                stage.phase = DesignPhase.exploring
            stage.evidence = [
                *stage.evidence[-5:],
                f"planner_interpretation_accepted:{interpretation.interpretation_id}",
            ]
        else:
            stage.confidence = min(stage.confidence, max(0.2, 1.0 - interpretation.ambiguity))
            stage.current_goal = "Planner interpretation rejected; revise intent or continue editing"
            stage.suggested_action = "revise_intent_or_continue_editing"
            stage.evidence = [
                *stage.evidence[-5:],
                f"planner_interpretation_rejected:{interpretation.interpretation_id}",
            ]
        studio_store.save_stage(request.session_id, stage)
        session.metadata.setdefault("planner_control_gate", {})
        if isinstance(session.metadata["planner_control_gate"], dict):
            session.metadata["planner_control_gate"] = {
                **session.metadata["planner_control_gate"],
                "last_interpretation_id": interpretation.interpretation_id,
                "last_decision": request.decision,
                "last_event_id": event.event_id,
                "last_memory_id": memory.memory_id,
            }
            studio_store.update_session(
                request.session_id,
                SessionUpdateRequest(metadata={"planner_control_gate": session.metadata["planner_control_gate"]}),
            )

        await websocket_manager.broadcast(
            request.session_id,
            "planner_interpretation_decision",
            {
                "interpretation_id": interpretation.interpretation_id,
                "decision": request.decision,
                "event_id": event.event_id,
                "memory_id": memory.memory_id,
            },
        )
        await websocket_manager.broadcast(
            request.session_id,
            "stage_update",
            stage.model_dump(mode="json"),
        )
        direction_response: CrossDomainDivergenceResponse | None = None
        if request.decision == "accepted" and request.metadata.get("auto_suggest_directions"):
            asset_id = interpretation.target.asset_id or stage.active_asset_id
            if asset_id and studio_store.get_asset(asset_id):
                direction_response = await create_direction_suggestions(
                    CrossDomainDivergenceRequest(
                        session_id=request.session_id,
                        asset_id=asset_id,
                        interpretation_id=interpretation.interpretation_id,
                        source_summary=str(
                            request.metadata.get("source_summary")
                            or "confirmed planner intent prompt expansion"
                        ),
                        constraints=[
                            str(value)
                            for value in request.metadata.get("preserved_constraints", [])
                            if isinstance(value, str)
                        ],
                        dimensions=request.metadata.get("dimensions", []),
                        candidate_count=int(request.metadata.get("direction_count") or 4),
                        metadata={
                            **request.metadata,
                            "auto_suggest_source": "planner_interpretation_decision",
                            "interpretation_id": interpretation.interpretation_id,
                        },
                    ),
                    endpoint_name="suggested_analogy_directions",
                )
        return PlannerInterpretationDecisionResponse(
            interpretation_id=interpretation.interpretation_id,
            session_id=request.session_id,
            decision=request.decision,
            event_id=event.event_id,
            memory_id=memory.memory_id,
            updated_stage=stage,
            suggested_directions=direction_response.directions if direction_response else [],
            direction_response=direction_response,
        )

    @app.patch("/api/v1/sessions/{session_id}")
    async def update_session(session_id: str, request: SessionUpdateRequest) -> SessionRecord:
        session = studio_store.update_session(session_id, request)
        if session is None:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
        return session

    @app.post("/api/v1/assets")
    async def create_asset(request: AssetCreateRequest) -> object:
        require_session(request.session_id)
        return studio_store.create_asset(request)

    @app.get("/api/v1/benchmark-assets")
    async def list_benchmark_assets() -> BenchmarkAssetListResponse:
        return BenchmarkAssetListResponse(assets=discover_benchmark_assets(files_root))

    @app.post("/api/v1/benchmark-assets/{benchmark_id}/load")
    async def load_benchmark_asset(
        benchmark_id: str,
        request: BenchmarkAssetLoadRequest,
    ) -> object:
        require_session(request.session_id)
        benchmarks = {item.benchmark_id: item for item in discover_benchmark_assets(files_root)}
        benchmark = benchmarks.get(benchmark_id)
        if benchmark is None:
            raise HTTPException(status_code=404, detail=f"Benchmark asset not found: {benchmark_id}")
        if benchmark.metadata.get("source") in {"creativeflow_github_pages_picked", "local_white_model"}:
            source_kind = str(benchmark.metadata.get("source") or "benchmark")
            return studio_store.create_asset(
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
                materialized_mesh = (_download_oss_object(oss_host, mesh_glb_key), ".glb")
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
                    materialized_mesh = (_download_oss_object(oss_host, mesh_obj_key), ".obj")
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
                materialized_mesh = (_download_oss_object(oss_host, mesh_obj_key), ".obj")
                materialized_source = "oss_obj"
            except OSError as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"Benchmark OBJ could not be loaded from OSS: {exc}",
                ) from exc
        if materialized_mesh is not None and materialized_mesh[1] == ".obj":
            material_key = str(benchmark.metadata.get("source_material_mtl_key") or "").strip()
            texture_key = _resolve_benchmark_texture_key(benchmark.metadata)
            if oss_host and material_key:
                try:
                    sidecar_files["material.mtl"] = _download_oss_object(oss_host, material_key)
                    if texture_key:
                        sidecar_files[Path(texture_key).name] = _download_oss_object(oss_host, texture_key)
                except OSError:
                    sidecar_files = {}
            elif oss_host and texture_key:
                try:
                    texture_name = Path(texture_key).name
                    sidecar_files["material.mtl"] = _benchmark_tree_material(texture_name)
                    sidecar_files[texture_name] = _download_oss_object(oss_host, texture_key)
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
                thumbnail_url=None,
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
        return asset

    @app.post("/api/v1/assets/upload")
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

    @app.post("/api/v1/reference-images/upload")
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

    @app.post("/api/v1/reference-models/upload")
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

    @app.get("/api/v1/assets/{asset_id}")
    async def get_asset(asset_id: str) -> object:
        asset = studio_store.get_asset(asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {asset_id}")
        return asset

    @app.get("/api/v1/assets/{asset_id}/parts")
    async def get_asset_parts(asset_id: str) -> AssetPartsResponse:
        asset = studio_store.get_asset(asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {asset_id}")
        return AssetPartsResponse(asset_id=asset_id, parts=asset.parts)

    @app.patch("/api/v1/assets/{asset_id}/parts/{part_id}")
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

    @app.post("/api/v1/parts/discover")
    async def discover_parts(request: PartDiscoveryRequest) -> PartDiscoveryResponse:
        require_session(request.session_id)
        if studio_store.get_asset(request.asset_id) is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {request.asset_id}")
        try:
            return await autopartgen_adapter.discover_parts(request)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/parts/from-mask")
    async def discover_parts_from_mask(request: PartDiscoveryRequest) -> PartDiscoveryResponse:
        request.mode = "image_mask"
        require_session(request.session_id)
        if studio_store.get_asset(request.asset_id) is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {request.asset_id}")
        return await autopartgen_adapter.discover_parts(request)

    @app.post("/api/v1/geometry/{operation}")
    async def run_geometry_operation(
        operation: str,
        request: GeometryWorkerRequest,
    ) -> GeometryWorkerResponse:
        _validate_optional_session(request.session_id)
        _hydrate_geometry_request(request)
        response = await geometry_worker.run(operation, request)
        artifacts = _register_worker_artifacts(worker="geometry", response=response, request=request)
        if artifacts:
            response.artifacts = {
                **response.artifacts,
                "artifact_ids": [artifact.artifact_id for artifact in artifacts],
            }
        _save_worker_job(worker="geometry", request=request, response=response, artifacts=artifacts)
        return response

    @app.get("/api/v1/geometry/jobs/{job_id}")
    async def get_geometry_job(job_id: str) -> GeometryWorkerResponse:
        job = studio_store.get_worker_job(job_id)
        if job is None or job.worker != "geometry":
            raise HTTPException(status_code=404, detail=f"Geometry worker job not found: {job_id}")
        return GeometryWorkerResponse(**job.response)

    @app.post("/api/v1/geometry/jobs/{job_id}/cancel")
    async def cancel_geometry_job(job_id: str) -> GeometryWorkerResponse:
        job = studio_store.get_worker_job(job_id)
        if job is None or job.worker != "geometry":
            raise HTTPException(status_code=404, detail=f"Geometry worker job not found: {job_id}")
        if job.status in {JobStatus.queued, JobStatus.running}:
            job.status = JobStatus.cancelled
            job.ok = False
            job.error = ApiErrorBody(code="GEOMETRY_JOB_CANCELLED", message="Geometry job cancelled.", retryable=False)
            job.response = {
                **job.response,
                "ok": False,
                "status": JobStatus.cancelled.value,
                "error": job.error.model_dump(mode="json"),
            }
            studio_store.save_worker_job(job)
        return GeometryWorkerResponse(**job.response)

    @app.post("/api/v1/render/{operation}")
    async def run_render_operation(
        operation: str,
        request: RenderPreviewRequest,
    ) -> RenderPreviewResponse:
        _validate_optional_session(request.session_id)
        _hydrate_render_request(request)
        response = await render_preview_worker.run(operation, request)
        artifacts = _register_worker_artifacts(worker="render", response=response, request=request)
        if artifacts:
            response.artifacts = {
                **response.artifacts,
                "artifact_ids": [artifact.artifact_id for artifact in artifacts],
            }
        _save_worker_job(worker="render", request=request, response=response, artifacts=artifacts)
        return response

    @app.get("/api/v1/render/jobs/{job_id}")
    async def get_render_job(job_id: str) -> RenderPreviewResponse:
        job = studio_store.get_worker_job(job_id)
        if job is None or job.worker != "render":
            raise HTTPException(status_code=404, detail=f"Render worker job not found: {job_id}")
        return RenderPreviewResponse(**job.response)

    @app.post("/api/v1/render/jobs/{job_id}/cancel")
    async def cancel_render_job(job_id: str) -> RenderPreviewResponse:
        job = studio_store.get_worker_job(job_id)
        if job is None or job.worker != "render":
            raise HTTPException(status_code=404, detail=f"Render worker job not found: {job_id}")
        if job.status in {JobStatus.queued, JobStatus.running}:
            job.status = JobStatus.cancelled
            job.ok = False
            job.error = ApiErrorBody(code="RENDER_JOB_CANCELLED", message="Render job cancelled.", retryable=False)
            job.response = {
                **job.response,
                "ok": False,
                "status": JobStatus.cancelled.value,
                "error": job.error.model_dump(mode="json"),
            }
            studio_store.save_worker_job(job)
        return RenderPreviewResponse(**job.response)

    @app.post("/api/v1/intent-drafts")
    async def create_intent_draft(request: IntentDraftCreateRequest) -> IntentDraft:
        require_session(request.session_id)
        if request.asset_id and studio_store.get_asset(request.asset_id) is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {request.asset_id}")
        draft = studio_store.create_intent_draft(request)
        await websocket_manager.broadcast(
            request.session_id,
            "intent_draft_saved",
            draft.model_dump(mode="json"),
        )
        return draft

    @app.post("/api/v1/sessions/{session_id}/actions")
    async def create_action_atom(
        session_id: str,
        request: ActionAtomCreateRequest,
    ) -> ActionAtom:
        require_session(session_id)
        if _looks_like_prompt_chip_action(request):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Prompt chips / analogy keywords are not ActionAtoms. "
                    "Use POST /api/v1/prompt/compose and generation.metadata.selected_prompt_tokens."
                ),
            )
        target_asset_id = (
            (request.target or {}).get("asset_id")
            or (request.evidence or {}).get("asset_id")
            or (request.metadata or {}).get("asset_id")
        )
        target_part_id = (
            (request.target or {}).get("part_id")
            or (request.evidence or {}).get("part_id")
            or (request.metadata or {}).get("part_id")
        )
        part_lifecycle = (
            (request.target or {}).get("lifecycle")
            or (request.evidence or {}).get("part_lifecycle")
            or (request.metadata or {}).get("lifecycle")
        )
        if target_asset_id and target_part_id:
            asset_for_atom = studio_store.get_asset(str(target_asset_id))
            if asset_for_atom is not None:
                matched = find_part(asset_for_atom.parts, str(target_part_id))
                if matched is not None:
                    part_lifecycle = read_lifecycle(matched)
        if not part_lifecycle:
            part_lifecycle = "tentative_raycast"

        evidence = dict(request.evidence or {})
        evidence["part_lifecycle"] = part_lifecycle
        target = dict(request.target or {})
        target["lifecycle"] = part_lifecycle
        atom = ActionAtom(
            atom_id=request.atom_id or f"atom_{uuid4().hex[:10]}",
            tool=request.tool,
            target=target,
            evidence={**evidence, "metadata": {**(request.metadata or {}), "part_lifecycle": part_lifecycle}}
            if request.metadata
            else evidence,
            order=request.order,
        )
        studio_store.save_action_atom(session_id, atom)
        event = UserEvent(
            type="action_atom_created",
            event_id=f"evt_{uuid4().hex[:10]}",
            session_id=session_id,
            payload={
                "atom": atom.model_dump(mode="json"),
                "asset_id": atom.target.get("asset_id") or atom.evidence.get("asset_id"),
                "part_id": atom.target.get("part_id") or atom.evidence.get("part_id"),
                "part_lifecycle": part_lifecycle,
                "selection": {
                    "type": "part" if atom.target.get("part_id") or atom.evidence.get("part_id") else "none",
                    "part_id": atom.target.get("part_id") or atom.evidence.get("part_id"),
                    "asset_id": atom.target.get("asset_id") or atom.evidence.get("asset_id"),
                    "label": atom.target.get("label"),
                    "lifecycle": part_lifecycle,
                },
                "intent_text": atom.evidence.get("intent_text") or atom.evidence.get("text"),
                "live_signals": atom.evidence.get("live_signals") or {},
            },
        )
        studio_store.save_event(event)
        live_signals_update = _update_session_live_signals(
            session_id,
            event.payload.get("live_signals"),
            "action_atom_created",
        )
        if live_signals_update["live_signals"]:
            await websocket_manager.broadcast(
                session_id,
                "live_signals_updated",
                live_signals_update,
            )
        await websocket_manager.broadcast(
            session_id,
            "action_atom_created",
            {
                "event_id": event.event_id,
                "action_atom_id": atom.atom_id,
                "atom": atom.model_dump(mode="json"),
            },
        )
        await interpret_and_publish(
            session_id=session_id,
            event=event,
            interaction_service=interaction_service,
            publish_perception=_publish_perception,
            defer_vlm=True,
        )
        return atom

    @app.get("/api/v1/sessions/{session_id}/actions")
    async def list_action_atoms(session_id: str, limit: int = 100) -> dict[str, list[ActionAtom]]:
        require_session(session_id)
        return {"actions": studio_store.list_action_atoms(session_id, limit=limit)}

    @app.post("/api/v1/annotations")
    async def create_annotation_artifact(
        request: AnnotationArtifactCreateRequest,
    ) -> ArtifactRecord:
        require_session(request.session_id)
        if request.asset_id and studio_store.get_asset(request.asset_id) is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {request.asset_id}")
        artifact_id = f"art_{uuid4().hex[:10]}"
        annotation_dir = files_root / "annotations" / artifact_id
        annotation_dir.mkdir(parents=True, exist_ok=True)
        target = annotation_dir / "stroke.json"
        payload = {
            "artifact_id": artifact_id,
            "session_id": request.session_id,
            "asset_id": request.asset_id,
            "part_id": request.part_id,
            "text": request.text,
            "strokes": request.strokes,
            "projection": request.projection,
            "metadata": request.metadata,
            "created_at": now_utc().isoformat(),
        }
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        artifact = studio_store.save_artifact(
            ArtifactRecord(
                artifact_id=artifact_id,
                type="annotation_stroke",
                url=f"/files/annotations/{artifact_id}/stroke.json",
                session_id=request.session_id,
                asset_id=request.asset_id,
                part_id=request.part_id,
                worker="manual",
                operation="annotation_stroke_commit",
                metadata={
                    **request.metadata,
                    "text": request.text,
                    "stroke_count": len(request.strokes),
                    "projection": request.projection,
                    "storage_path": str(target),
                },
            )
        )
        event = UserEvent(
            type="annotation_stroke_committed",
            event_id=f"evt_{uuid4().hex[:10]}",
            session_id=request.session_id,
            payload={
                "artifact_id": artifact.artifact_id,
                "stroke_url": artifact.url,
                "asset_id": request.asset_id,
                "part_id": request.part_id,
                "annotation_text": request.text,
                "stroke_count": len(request.strokes),
                "projection": request.projection,
            },
        )
        studio_store.save_event(event)
        studio_store.save_memory(
            MemoryRecord(
                memory_id=f"mem_{uuid4().hex[:10]}",
                session_id=request.session_id,
                category="working",
                type="annotation_stroke",
                source_id=artifact.artifact_id,
                asset_id=request.asset_id,
                part_id=request.part_id,
                content={
                    "artifact": artifact.model_dump(mode="json"),
                    "event_id": event.event_id,
                    "text": request.text,
                    "stroke_count": len(request.strokes),
                    "projection": request.projection,
                },
                tags=["annotation", "2d_pencil"],
            )
        )
        await websocket_manager.broadcast(
            request.session_id,
            "annotation_stroke_committed",
            {
                "artifact": artifact.model_dump(mode="json"),
                "event_id": event.event_id,
            },
        )
        return artifact

    @app.post("/api/v1/brush-masks")
    async def create_brush_mask_artifact(
        request: BrushMaskArtifactCreateRequest,
    ) -> ArtifactRecord:
        require_session(request.session_id)
        if request.asset_id and studio_store.get_asset(request.asset_id) is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {request.asset_id}")
        artifact_id = f"art_{uuid4().hex[:10]}"
        mask_dir = files_root / "brush-masks" / artifact_id
        mask_dir.mkdir(parents=True, exist_ok=True)
        target = mask_dir / "mask.json"
        payload = {
            "artifact_id": artifact_id,
            "session_id": request.session_id,
            "asset_id": request.asset_id,
            "part_id": request.part_id,
            "label": request.label,
            "mask": request.mask,
            "projection": request.projection,
            "metrics": request.metrics,
            "metadata": request.metadata,
            "created_at": now_utc().isoformat(),
        }
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        artifact = studio_store.save_artifact(
            ArtifactRecord(
                artifact_id=artifact_id,
                type="brush_mask",
                url=f"/files/brush-masks/{artifact_id}/mask.json",
                session_id=request.session_id,
                asset_id=request.asset_id,
                part_id=request.part_id,
                worker="manual",
                operation="brush_mask_commit",
                metrics=request.metrics,
                metadata={
                    **request.metadata,
                    "label": request.label,
                    "projection": request.projection,
                    "mask_kind": request.mask.get("kind"),
                    "coverage": request.metrics.get("coverage"),
                    "storage_path": str(target),
                },
            )
        )
        event = UserEvent(
            type="brush_mask_committed",
            event_id=f"evt_{uuid4().hex[:10]}",
            session_id=request.session_id,
            payload={
                "artifact_id": artifact.artifact_id,
                "mask_url": artifact.url,
                "asset_id": request.asset_id,
                "part_id": request.part_id,
                "label": request.label,
                "coverage": request.metrics.get("coverage"),
                "projection": request.projection,
            },
        )
        studio_store.save_event(event)
        studio_store.save_memory(
            MemoryRecord(
                memory_id=f"mem_{uuid4().hex[:10]}",
                session_id=request.session_id,
                category="working",
                type="brush_mask",
                source_id=artifact.artifact_id,
                asset_id=request.asset_id,
                part_id=request.part_id,
                content={
                    "artifact": artifact.model_dump(mode="json"),
                    "event_id": event.event_id,
                    "label": request.label,
                    "coverage": request.metrics.get("coverage"),
                    "projection": request.projection,
                    "mask": request.mask,
                },
                tags=["brush", "surface_mask", "3d_brush"],
            )
        )
        await websocket_manager.broadcast(
            request.session_id,
            "brush_mask_committed",
            {
                "artifact": artifact.model_dump(mode="json"),
                "event_id": event.event_id,
            },
        )
        return artifact

    @app.post("/api/v1/smooth-operations")
    async def create_smooth_operation_artifact(
        request: SmoothOperationArtifactCreateRequest,
    ) -> ArtifactRecord:
        require_session(request.session_id)
        if request.asset_id and studio_store.get_asset(request.asset_id) is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {request.asset_id}")
        artifact_id = f"art_{uuid4().hex[:10]}"
        operation_dir = files_root / "smooth-operations" / artifact_id
        operation_dir.mkdir(parents=True, exist_ok=True)
        target = operation_dir / "operation.json"
        payload = {
            "artifact_id": artifact_id,
            "session_id": request.session_id,
            "asset_id": request.asset_id,
            "part_id": request.part_id,
            "label": request.label,
            "region": request.region,
            "brush": request.brush,
            "parameters": request.parameters,
            "preview": request.preview,
            "metrics": request.metrics,
            "metadata": request.metadata,
            "created_at": now_utc().isoformat(),
        }
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        artifact = studio_store.save_artifact(
            ArtifactRecord(
                artifact_id=artifact_id,
                type="smooth_operation",
                url=f"/files/smooth-operations/{artifact_id}/operation.json",
                session_id=request.session_id,
                asset_id=request.asset_id,
                part_id=request.part_id,
                worker="manual",
                operation="smooth_operation_commit",
                metrics=request.metrics,
                metadata={
                    **request.metadata,
                    "label": request.label,
                    "region": request.region,
                    "brush_radius": request.brush.get("radius"),
                    "strength": request.parameters.get("strength"),
                    "preserve_boundary": request.parameters.get("preserve_boundary"),
                    "preview_mesh_url": request.preview.get("preview_mesh_url"),
                    "geometry_job_id": request.preview.get("geometry_job_id"),
                    "storage_path": str(target),
                },
            )
        )
        event = UserEvent(
            type="smooth_operation_committed",
            event_id=f"evt_{uuid4().hex[:10]}",
            session_id=request.session_id,
            payload={
                "artifact_id": artifact.artifact_id,
                "operation_url": artifact.url,
                "asset_id": request.asset_id,
                "part_id": request.part_id,
                "label": request.label,
                "region": request.region,
                "strength": request.parameters.get("strength"),
                "preserve_boundary": request.parameters.get("preserve_boundary"),
                "preview_mesh_url": request.preview.get("preview_mesh_url"),
                "geometry_job_id": request.preview.get("geometry_job_id"),
            },
        )
        studio_store.save_event(event)
        studio_store.save_memory(
            MemoryRecord(
                memory_id=f"mem_{uuid4().hex[:10]}",
                session_id=request.session_id,
                category="working",
                type="smooth_operation",
                source_id=artifact.artifact_id,
                asset_id=request.asset_id,
                part_id=request.part_id,
                content={
                    "artifact": artifact.model_dump(mode="json"),
                    "event_id": event.event_id,
                    "label": request.label,
                    "region": request.region,
                    "brush": request.brush,
                    "parameters": request.parameters,
                    "preview": request.preview,
                    "metrics": request.metrics,
                },
                tags=["smooth", "3d_sculpt", "local_geometry"],
            )
        )
        await websocket_manager.broadcast(
            request.session_id,
            "smooth_operation_committed",
            {
                "artifact": artifact.model_dump(mode="json"),
                "event_id": event.event_id,
            },
        )
        return artifact

    @app.post("/api/v1/primitive-additions")
    async def create_primitive_addition_artifact(
        request: PrimitiveAdditionArtifactCreateRequest,
    ) -> ArtifactRecord:
        require_session(request.session_id)
        if request.asset_id and studio_store.get_asset(request.asset_id) is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {request.asset_id}")
        artifact_id = f"art_{uuid4().hex[:10]}"
        primitive_dir = files_root / "primitive-additions" / artifact_id
        primitive_dir.mkdir(parents=True, exist_ok=True)
        target = primitive_dir / "primitive.json"
        payload = {
            "artifact_id": artifact_id,
            "session_id": request.session_id,
            "asset_id": request.asset_id,
            "part_id": request.part_id,
            "primitive": request.primitive,
            "transform": request.transform,
            "relation": request.relation,
            "constraints": request.constraints,
            "preview": request.preview,
            "metadata": request.metadata,
            "created_at": now_utc().isoformat(),
        }
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        artifact = studio_store.save_artifact(
            ArtifactRecord(
                artifact_id=artifact_id,
                type="primitive_addition",
                url=f"/files/primitive-additions/{artifact_id}/primitive.json",
                session_id=request.session_id,
                asset_id=request.asset_id,
                part_id=request.part_id,
                worker="manual",
                operation="primitive_addition_commit",
                metadata={
                    **request.metadata,
                    "primitive": request.primitive,
                    "transform": request.transform,
                    "relation": request.relation,
                    "constraint_count": len(request.constraints),
                    "storage_path": str(target),
                },
            )
        )
        event = UserEvent(
            type="primitive_addition_committed",
            event_id=f"evt_{uuid4().hex[:10]}",
            session_id=request.session_id,
            payload={
                "artifact_id": artifact.artifact_id,
                "primitive_url": artifact.url,
                "asset_id": request.asset_id,
                "part_id": request.part_id,
                "primitive": request.primitive,
                "transform": request.transform,
                "relation": request.relation,
                "constraints": request.constraints,
            },
        )
        studio_store.save_event(event)
        studio_store.save_memory(
            MemoryRecord(
                memory_id=f"mem_{uuid4().hex[:10]}",
                session_id=request.session_id,
                category="working",
                type="primitive_addition",
                source_id=artifact.artifact_id,
                asset_id=request.asset_id,
                part_id=request.part_id,
                content={
                    "artifact": artifact.model_dump(mode="json"),
                    "event_id": event.event_id,
                    "primitive": request.primitive,
                    "transform": request.transform,
                    "relation": request.relation,
                    "constraints": request.constraints,
                    "preview": request.preview,
                },
                tags=["add", "primitive", "3d_geometry"],
            )
        )
        await websocket_manager.broadcast(
            request.session_id,
            "primitive_addition_committed",
            {
                "artifact": artifact.model_dump(mode="json"),
                "event_id": event.event_id,
            },
        )
        return artifact

    @app.post("/api/v1/drag-operations")
    async def create_drag_operation_artifact(
        request: DragOperationArtifactCreateRequest,
    ) -> ArtifactRecord:
        require_session(request.session_id)
        if request.asset_id and studio_store.get_asset(request.asset_id) is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {request.asset_id}")
        artifact_id = f"art_{uuid4().hex[:10]}"
        drag_dir = files_root / "drag-operations" / artifact_id
        drag_dir.mkdir(parents=True, exist_ok=True)
        target = drag_dir / "drag.json"
        payload = {
            "artifact_id": artifact_id,
            "session_id": request.session_id,
            "asset_id": request.asset_id,
            "part_id": request.part_id,
            "label": request.label,
            "drag": request.drag,
            "region": request.region,
            "preview": request.preview,
            "metrics": request.metrics,
            "metadata": request.metadata,
            "created_at": now_utc().isoformat(),
        }
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        artifact = studio_store.save_artifact(
            ArtifactRecord(
                artifact_id=artifact_id,
                type="drag_operation",
                url=f"/files/drag-operations/{artifact_id}/drag.json",
                session_id=request.session_id,
                asset_id=request.asset_id,
                part_id=request.part_id,
                worker="manual",
                operation="drag_operation_commit",
                metrics=request.metrics,
                metadata={
                    **request.metadata,
                    "label": request.label,
                    "drag": request.drag,
                    "region": request.region,
                    "drag_length": request.metrics.get("drag_length"),
                    "direction_relation": request.metrics.get("direction_relation"),
                    "influence_radius": request.drag.get("influence_radius"),
                    "preview_mesh_url": request.preview.get("preview_mesh_url"),
                    "geometry_job_id": request.preview.get("geometry_job_id"),
                    "storage_path": str(target),
                },
            )
        )
        event = UserEvent(
            type="drag_operation_committed",
            event_id=f"evt_{uuid4().hex[:10]}",
            session_id=request.session_id,
            payload={
                "artifact_id": artifact.artifact_id,
                "drag_operation_url": artifact.url,
                "asset_id": request.asset_id,
                "part_id": request.part_id,
                "label": request.label,
                "drag": request.drag,
                "region": request.region,
                "preview": request.preview,
                "metrics": request.metrics,
            },
        )
        studio_store.save_event(event)
        studio_store.save_memory(
            MemoryRecord(
                memory_id=f"mem_{uuid4().hex[:10]}",
                session_id=request.session_id,
                category="working",
                type="drag_operation",
                source_id=artifact.artifact_id,
                asset_id=request.asset_id,
                part_id=request.part_id,
                content={
                    "artifact": artifact.model_dump(mode="json"),
                    "event_id": event.event_id,
                    "label": request.label,
                    "drag": request.drag,
                    "region": request.region,
                    "preview": request.preview,
                    "metrics": request.metrics,
                },
                tags=["drag", "3d_transform", "local_geometry"],
            )
        )
        await websocket_manager.broadcast(
            request.session_id,
            "drag_operation_committed",
            {
                "artifact": artifact.model_dump(mode="json"),
                "event_id": event.event_id,
            },
        )
        return artifact

    @app.post("/api/v1/focus-observations")
    async def create_focus_observation_artifact(
        request: FocusObservationArtifactCreateRequest,
    ) -> ArtifactRecord:
        require_session(request.session_id)
        if request.asset_id and studio_store.get_asset(request.asset_id) is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {request.asset_id}")
        artifact_id = f"art_{uuid4().hex[:10]}"
        focus_dir = files_root / "focus-observations" / artifact_id
        focus_dir.mkdir(parents=True, exist_ok=True)
        target = focus_dir / "focus.json"
        part_lifecycle = None
        if request.asset_id and request.part_id:
            asset_for_focus = studio_store.get_asset(request.asset_id)
            if asset_for_focus is not None:
                focused = find_part(asset_for_focus.parts, request.part_id)
                if focused is not None:
                    part_lifecycle = read_lifecycle(focused)
        if part_lifecycle is None:
            part_lifecycle = str(
                (request.metadata or {}).get("lifecycle")
                or (request.observation or {}).get("lifecycle")
                or "tentative_raycast"
            )
        observation = {
            **(request.observation or {}),
            "part_lifecycle": part_lifecycle,
            "lifecycle": part_lifecycle,
        }
        payload = {
            "artifact_id": artifact_id,
            "session_id": request.session_id,
            "asset_id": request.asset_id,
            "part_id": request.part_id,
            "label": request.label,
            "part_lifecycle": part_lifecycle,
            "observation": observation,
            "viewport": request.viewport,
            "metrics": request.metrics,
            "metadata": request.metadata,
            "created_at": now_utc().isoformat(),
        }
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        artifact = studio_store.save_artifact(
            ArtifactRecord(
                artifact_id=artifact_id,
                type="focus_observation",
                url=f"/files/focus-observations/{artifact_id}/focus.json",
                session_id=request.session_id,
                asset_id=request.asset_id,
                part_id=request.part_id,
                worker="manual",
                operation="focus_observation_commit",
                metrics=request.metrics,
                metadata={
                    **request.metadata,
                    "label": request.label,
                    "observation": observation,
                    "viewport": request.viewport,
                    "dwell_ms": request.metrics.get("dwell_ms"),
                    "focus_source": observation.get("focus_source"),
                    "part_lifecycle": part_lifecycle,
                    "storage_path": str(target),
                },
            )
        )
        event = UserEvent(
            type="focus_observation_committed",
            event_id=f"evt_{uuid4().hex[:10]}",
            session_id=request.session_id,
            payload={
                "artifact_id": artifact.artifact_id,
                "focus_observation_url": artifact.url,
                "asset_id": request.asset_id,
                "part_id": request.part_id,
                "label": request.label,
                "part_lifecycle": part_lifecycle,
                "observation": observation,
                "viewport": request.viewport,
                "metrics": request.metrics,
            },
        )
        studio_store.save_event(event)
        studio_store.save_memory(
            MemoryRecord(
                memory_id=f"mem_{uuid4().hex[:10]}",
                session_id=request.session_id,
                category="working",
                type="focus_observation",
                source_id=artifact.artifact_id,
                asset_id=request.asset_id,
                part_id=request.part_id,
                content={
                    "artifact": artifact.model_dump(mode="json"),
                    "event_id": event.event_id,
                    "label": request.label,
                    "observation": request.observation,
                    "viewport": request.viewport,
                    "metrics": request.metrics,
                },
                tags=["hover", "attention", "focus_observation"],
            )
        )
        await websocket_manager.broadcast(
            request.session_id,
            "focus_observation_committed",
            {"artifact": artifact.model_dump(mode="json"), "event_id": event.event_id},
        )
        return artifact

    @app.get("/api/v1/sessions/{session_id}/intent-drafts")
    async def list_intent_drafts(
        session_id: str,
        include_archived: bool = False,
    ) -> IntentDraftListResponse:
        require_session(session_id)
        return IntentDraftListResponse(
            drafts=studio_store.list_intent_drafts(
                session_id,
                include_archived=include_archived,
            )
        )

    @app.patch("/api/v1/intent-drafts/{draft_id}")
    async def update_intent_draft(
        draft_id: str,
        request: IntentDraftUpdateRequest,
    ) -> IntentDraft:
        draft = studio_store.update_intent_draft(draft_id, request)
        if draft is None:
            raise HTTPException(status_code=404, detail=f"Intent draft not found: {draft_id}")
        await websocket_manager.broadcast(
            draft.session_id,
            "intent_draft_saved",
            draft.model_dump(mode="json"),
        )
        return draft

    @app.post("/api/v1/sessions/{session_id}/episodes")
    async def create_intent_episode(
        session_id: str,
        request: IntentEpisodeCreateRequest,
    ) -> IntentEpisodeResponse:
        session = require_session(session_id)
        draft = None
        if request.intent_draft_id:
            draft = studio_store.get_intent_draft(request.intent_draft_id)
            if draft is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Intent draft not found: {request.intent_draft_id}",
                )
            if draft.session_id != session_id:
                raise HTTPException(status_code=400, detail="Intent draft belongs to another session")
        atoms: list[ActionAtom] = []
        seen: set[str] = set()
        for atom_id in request.action_atom_ids:
            atom = studio_store.get_action_atom(atom_id)
            if atom is None:
                raise HTTPException(status_code=404, detail=f"Action atom not found: {atom_id}")
            atoms.append(atom)
            seen.add(atom.atom_id)
        if draft:
            for atom in draft.behavior_atoms:
                if atom.atom_id not in seen:
                    atoms.append(atom)
                    seen.add(atom.atom_id)
        for atom in request.behavior_atoms:
            if atom.atom_id not in seen:
                atoms.append(atom)
                seen.add(atom.atom_id)
                studio_store.save_action_atom(session_id, atom)
        episode = IntentEpisodeResponse(
            episode_id=f"ep_{uuid4().hex[:10]}",
            session_id=session_id,
            asset_id=draft.asset_id if draft else session.stage.active_asset_id,
            intent_draft_id=request.intent_draft_id,
            behavior_atoms=sorted(atoms, key=lambda item: item.order),
            text=request.text if request.text is not None else (draft.text if draft else None),
            image_refs=request.image_refs or (draft.image_refs if draft else []),
            model_refs=request.model_refs or (draft.model_refs if draft else []),
            context_snapshot_id=request.context_snapshot_id,
            metadata={
                **request.metadata,
                "behavior_count": len(atoms),
                "compatibility_endpoint": True,
            },
        )
        event = UserEvent(
            type="intent_episode_submitted",
            event_id=f"evt_{uuid4().hex[:10]}",
            session_id=session_id,
            payload=episode.model_dump(mode="json"),
        )
        studio_store.save_event(event)
        interpretation = await interpret_and_publish(
            session_id=session_id,
            event=event,
            interaction_service=interaction_service,
            publish_perception=_publish_perception,
            defer_vlm=True,
        )
        episode.planner_interpretation = interpretation
        episode.metadata = {
            **episode.metadata,
            "planner_interpretation_id": interpretation.interpretation_id,
            "planner_confidence": interpretation.confidence,
            "planner_primary_intent": interpretation.primary_intent.value,
        }
        studio_store.save_memory(
            MemoryRecord(
                memory_id=f"mem_{uuid4().hex[:10]}",
                session_id=session_id,
                category="working",
                type="intent_episode",
                source_id=episode.episode_id,
                asset_id=episode.asset_id,
                confidence=0.84,
                content=episode.model_dump(mode="json"),
                tags=["intent_episode", "behavior_composition"],
            )
        )
        if draft and draft.status != "sent":
            studio_store.update_intent_draft(
                draft.draft_id,
                IntentDraftUpdateRequest(
                    status="sent",
                    metadata={"episode_id": episode.episode_id},
                ),
            )
        await websocket_manager.broadcast(
            session_id,
            "intent_episode_submitted",
            episode.model_dump(mode="json"),
        )
        return episode

    @app.patch("/api/v1/directions/{direction_id}")
    async def update_direction(
        direction_id: str,
        request: DirectionUpdateRequest,
    ) -> AnalogyDirection:
        direction = studio_store.get_direction(direction_id)
        if direction is None:
            raise HTTPException(status_code=404, detail=f"Direction not found: {direction_id}")
        if request.status is not None:
            direction.metadata["status"] = request.status
            direction.metadata["selected"] = request.status in {"selected", "pinned"}
        direction.metadata.update(request.metadata)
        session_id = str(direction.metadata.get("session_id") or "")
        if not session_id:
            session_id = _session_id_for_direction(direction_id)
        studio_store.save_direction(session_id, direction)
        await websocket_manager.broadcast(
            session_id,
            "directions_updated",
            {"directions": [direction.model_dump(mode="json")]},
        )
        return direction

    @app.post("/api/v1/prompt/compose")
    async def compose_prompt_tokens(request: PromptComposeRequest) -> PromptComposeResponse:
        require_session(request.session_id)
        if request.asset_id and studio_store.get_asset(request.asset_id) is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {request.asset_id}")
        package = _build_prompt_chip_package(request)
        event = UserEvent(
            type="prompt_tokens_composed",
            event_id=f"evt_{uuid4().hex[:10]}",
            session_id=request.session_id,
            payload={
                "asset_id": request.asset_id,
                "intent_draft_id": request.intent_draft_id,
                "analogy_prompt_package": package,
                "final_prompt": package["final_prompt"],
                "selected_prompt_tokens": package["selected_prompt_tokens"],
                "direction_ids": package["direction_ids"],
                "metadata": request.metadata,
            },
        )
        studio_store.save_event(event)
        memory = studio_store.save_memory(
            MemoryRecord(
                memory_id=f"mem_{uuid4().hex[:10]}",
                session_id=request.session_id,
                category="working",
                type="prompt_chip_composition",
                source_id=event.event_id,
                asset_id=request.asset_id,
                confidence=0.86,
                content=event.payload,
                tags=["prompt_chip_composition", "more_creative", "human_selectable_chips"],
            )
        )
        await websocket_manager.broadcast(
            request.session_id,
            "prompt_tokens_composed",
            {
                "event_id": event.event_id,
                "memory_id": memory.memory_id,
                "analogy_prompt_package": package,
            },
        )
        return PromptComposeResponse(
            session_id=request.session_id,
            asset_id=request.asset_id,
            final_prompt=package["final_prompt"],
            analogy_prompt_package=package,
            event_id=event.event_id,
            memory_id=memory.memory_id,
        )

    @app.get("/api/v1/candidates/{candidate_id}")
    async def get_candidate(candidate_id: str):
        candidate = studio_store.get_candidate(candidate_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail=f"Candidate not found: {candidate_id}")
        return candidate

    @app.post("/api/v1/candidates/{candidate_id}/accept")
    async def accept_candidate(
        candidate_id: str, request: CandidateDecisionRequest
    ) -> CandidateDecisionResponse:
        return await _decide_candidate(candidate_id, request, CandidateDecision.accepted)

    @app.post("/api/v1/candidates/{candidate_id}/reject")
    async def reject_candidate(
        candidate_id: str, request: CandidateDecisionRequest
    ) -> CandidateDecisionResponse:
        return await _decide_candidate(candidate_id, request, CandidateDecision.rejected)

    @app.post("/api/v1/candidates/{candidate_id}/preview")
    async def preview_candidate(candidate_id: str, request: CandidateDecisionRequest) -> Candidate:
        require_session(request.session_id)
        candidate = studio_store.get_candidate(candidate_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail=f"Candidate not found: {candidate_id}")
        if candidate.session_id != request.session_id:
            raise HTTPException(status_code=400, detail="Candidate belongs to another session")
        candidate.metadata["last_previewed_at"] = now_utc().isoformat()
        candidate.metadata["preview_reason"] = request.reason
        studio_store.save_candidate(candidate)
        event = UserEvent(
            type="candidate_compared",
            event_id=f"evt_{uuid4().hex[:10]}",
            session_id=request.session_id,
            payload={
                "candidate_id": candidate_id,
                "reason": request.reason,
                "asset_id": candidate.source_asset_id,
                "part_id": candidate.source_part_id,
                "artifact_level": "mesh" if candidate.mesh_url or candidate.obj_url else "image",
            },
        )
        studio_store.save_event(event)
        await websocket_manager.broadcast(
            request.session_id,
            "candidate_previewed",
            candidate.model_dump(mode="json"),
        )
        return candidate

    @app.post("/api/v1/candidates/{candidate_id}/commit")
    async def commit_candidate(
        candidate_id: str,
        request: CandidateDecisionRequest,
    ) -> CandidateDecisionResponse:
        request.make_active_asset = True
        return await _decide_candidate(candidate_id, request, CandidateDecision.accepted)

    @app.post("/api/v1/candidates/{candidate_id}/hy3d")
    async def generate_candidate_hy3d(candidate_id: str, request: CandidateDecisionRequest) -> Candidate:
        require_session(request.session_id)
        try:
            return await generation_orchestrator.generate_candidate_hy3d(
                candidate_id,
                request.session_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/api/v1/candidates/{candidate_id}/fit")
    async def fit_candidate(candidate_id: str, request: CandidateFitRequest) -> Candidate:
        require_session(request.session_id)
        try:
            return await generation_orchestrator.fit_candidate_to_part(candidate_id, request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    async def _decide_candidate(
        candidate_id: str,
        request: CandidateDecisionRequest,
        decision: CandidateDecision,
    ) -> CandidateDecisionResponse:
        session = require_session(request.session_id)
        candidate = studio_store.get_candidate(candidate_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail=f"Candidate not found: {candidate_id}")
        candidate.decision = decision
        studio_store.save_candidate(candidate)

        candidate_stage = str(candidate.metadata.get("stage") or "").strip()
        candidate_fidelity = str(candidate.metadata.get("fidelity") or "").strip()
        is_direction_candidate = candidate_stage in {"silhouette", "rough_form", "global", "form"}
        has_asset_output = bool(candidate.mesh_url or candidate.obj_url)
        commit_policy = "active_asset" if request.make_active_asset and has_asset_output else "direction_memory"

        active_asset_id = None
        if (
            decision == CandidateDecision.accepted
            and request.make_active_asset
            and has_asset_output
        ):
            active_asset = studio_store.create_asset(
                AssetCreateRequest(
                    session_id=request.session_id,
                    object_type=studio_store.get_asset(candidate.source_asset_id).object_type
                    if studio_store.get_asset(candidate.source_asset_id)
                    else "object",
                    label=candidate.label,
                    mesh_url=candidate.mesh_url,
                    obj_url=candidate.obj_url,
                    thumbnail_url=candidate.thumbnail_url,
                    metadata={"source_candidate_id": candidate.candidate_id},
                )
            )
            active_asset_id = active_asset.asset_id

        if decision == CandidateDecision.accepted:
            _record_candidate_memory(
                session,
                candidate,
                commit_policy,
                candidate_stage,
                candidate_fidelity,
            )
        else:
            _record_candidate_rejection(session, candidate, candidate_stage, candidate_fidelity)

        phase = (
            DesignPhase.exploring
            if decision == CandidateDecision.accepted
            and is_direction_candidate
            and commit_policy == "direction_memory"
            else DesignPhase.refinement
            if decision == CandidateDecision.accepted
            else DesignPhase.candidate_comparison
        )
        goal = request.reason
        if decision == CandidateDecision.accepted and not goal:
            if commit_policy == "direction_memory":
                goal = f"Accepted direction: {candidate.label}"
            else:
                goal = f"Accepted asset candidate: {candidate.label}"
        stage = StageState(
            phase=phase,
            confidence=0.86 if decision == CandidateDecision.accepted else 0.78,
            current_goal=goal,
            active_asset_id=active_asset_id or session.stage.active_asset_id,
            active_part_id=candidate.source_part_id or session.stage.active_part_id,
            suggested_action=_next_action_after_accept(candidate_stage, commit_policy)
            if decision == CandidateDecision.accepted
            else _next_action_after_reject(session, candidate_stage),
            evidence=[
                f"Candidate {decision.value}: {candidate_id}",
                f"commit_policy={commit_policy}",
                f"stage={candidate_stage or 'unspecified'}",
                f"fidelity={candidate_fidelity or 'unspecified'}",
            ],
        )
        studio_store.save_stage(request.session_id, stage)

        event = UserEvent(
            type=f"candidate_{decision.value}",
            event_id=f"evt_{uuid4().hex[:10]}",
            session_id=request.session_id,
            payload={
                "candidate_id": candidate_id,
                "reason": request.reason,
                "asset_id": candidate.source_asset_id,
                "part_id": candidate.source_part_id,
                "creative_stage": candidate_stage or None,
                "fidelity": candidate_fidelity or None,
                "commit_policy": commit_policy,
                "make_active_asset": bool(active_asset_id),
                "active_asset_id": active_asset_id,
                "suggested_action": stage.suggested_action,
            },
        )
        studio_store.save_event(event)
        await interpret_and_publish(
            session_id=request.session_id,
            event=event,
            interaction_service=interaction_service,
            publish_perception=_publish_perception,
            defer_vlm=True,
        )

        return CandidateDecisionResponse(
            candidate_id=candidate_id,
            decision=decision,
            active_asset_id=active_asset_id,
            updated_stage=studio_store.get_session(request.session_id).stage,
        )

    @app.post("/api/v1/cases")
    async def create_case(request: CaseCreateRequest) -> CaseRecord:
        session = require_session(request.session_id)
        asset = studio_store.get_asset(request.asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {request.asset_id}")
        if asset.session_id != request.session_id:
            raise HTTPException(status_code=400, detail="Asset does not belong to the session")
        for candidate_id in request.accepted_candidate_ids:
            candidate = studio_store.get_candidate(candidate_id)
            if candidate is None:
                raise HTTPException(status_code=404, detail=f"Candidate not found: {candidate_id}")
            if candidate.session_id != request.session_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"Candidate does not belong to the session: {candidate_id}",
                )
            if candidate.decision != CandidateDecision.accepted:
                raise HTTPException(
                    status_code=400,
                    detail=f"Candidate is not accepted: {candidate_id}",
                )
        case = studio_store.create_case(request)
        case_dir = files_root / "cases" / case.case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        report_path = case_dir / "report.html"
        manifest_path = case_dir / "case.json"
        accepted_candidates = [
            studio_store.get_candidate(candidate_id)
            for candidate_id in case.accepted_candidate_ids
            if studio_store.get_candidate(candidate_id) is not None
        ]
        case.metadata = {
            **case.metadata,
            "case_url": f"/files/cases/{case.case_id}/case.json",
            "case_index_url": "/files/cases/index.json",
        }
        studio_store.cases[case.case_id] = case
        manifest = build_case_manifest(case, session.stage, session.metadata, asset, accepted_candidates)
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        write_case_index(files_root / "cases", studio_store.cases.values())
        report_path.write_text(
            render_case_report(case, session.stage, session.metadata, asset, accepted_candidates),
            encoding="utf-8",
        )
        await websocket_manager.broadcast(
            request.session_id,
            "case_saved",
            {
                "case_id": case.case_id,
                "title": case.title,
                "asset_id": case.asset_id,
                "accepted_candidate_ids": case.accepted_candidate_ids,
                "report_url": case.report_url,
                "case_url": case.metadata.get("case_url"),
            },
        )
        return case

    @app.get("/api/v1/cases/{case_id}")
    async def get_case(case_id: str) -> CaseRecord:
        case = studio_store.get_case(case_id)
        if case is None:
            raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
        return case

    @app.websocket("/ws/sessions/{session_id}")
    async def session_websocket(websocket: WebSocket, session_id: str) -> None:
        if studio_store.get_session(session_id) is None:
            await websocket.accept()
            await websocket_manager.send(
                websocket,
                session_id,
                "error",
                {
                    "code": "SESSION_NOT_FOUND",
                    "message": f"Session not found: {session_id}",
                    "retryable": False,
                    "details": {},
                },
            )
            await websocket.close()
            return

        await websocket_manager.connect(session_id, websocket)
        try:
            await websocket_manager.send(websocket, session_id, "ack", {"connected": True})
            while True:
                raw = await websocket.receive_json()
                message = WebSocketMessage.model_validate(raw)
                event = UserEvent(
                    type=message.type,
                    event_id=message.event_id,
                    session_id=session_id,
                    timestamp=message.timestamp,
                    payload=message.payload,
                )
                studio_store.save_event(event)
                await websocket_manager.send(
                    websocket,
                    session_id,
                    "ack",
                    {"source_event_id": event.event_id, "type": event.type},
                )

                # Observation / completion for Perception must go through HTTP
                # /interaction/interpret or /sessions/{id}/actions. Keep a narrow
                # WS whitelist for in-tool events only; always use interpret_and_publish.
                if event.type in {
                    "brush_end",
                    "drag_end",
                    "part_select",
                    "undo",
                }:
                    interpretation = await interpret_and_publish(
                        session_id=session_id,
                        event=event,
                        interaction_service=interaction_service,
                        publish_perception=_publish_perception,
                        defer_vlm=True,
                    )
                    if interpretation.suggested_assistance:
                        await websocket_manager.send(
                            websocket,
                            session_id,
                            "assistance_suggestion",
                            {
                                "source_event_id": event.event_id,
                                "suggested_assistance": [
                                    item.model_dump(mode="json")
                                    for item in interpretation.suggested_assistance
                                ],
                            },
                        )
        except WebSocketDisconnect:
            websocket_manager.disconnect(session_id, websocket)
        except Exception as exc:
            await websocket_manager.send(
                websocket,
                session_id,
                "error",
                {
                    "code": "INVALID_EVENT",
                    "message": str(exc),
                    "retryable": True,
                    "details": {},
                },
            )
            websocket_manager.disconnect(session_id, websocket)

    return app


app = create_app()


def _record_candidate_memory(
    session: SessionRecord,
    candidate: Candidate,
    commit_policy: str,
    candidate_stage: str,
    candidate_fidelity: str,
) -> None:
    memory = session.metadata.setdefault("candidate_memory", {})
    accepted = memory.setdefault("accepted", [])
    accepted.append(
        {
            "candidate_id": candidate.candidate_id,
            "label": candidate.label,
            "stage": candidate_stage or None,
            "fidelity": candidate_fidelity or None,
            "commit_policy": commit_policy,
            "source_asset_id": candidate.source_asset_id,
            "source_part_id": candidate.source_part_id,
            "has_asset_output": bool(candidate.mesh_url or candidate.obj_url),
            "scores": candidate.scores,
        }
    )
    memory["last_accepted_candidate_id"] = candidate.candidate_id
    memory["last_accepted_stage"] = candidate_stage or None
    memory["last_commit_policy"] = commit_policy

    if commit_policy == "direction_memory":
        directions = memory.setdefault("accepted_direction_ids", [])
        if candidate.candidate_id not in directions:
            directions.append(candidate.candidate_id)
    studio_store.save_memory(
        MemoryRecord(
            memory_id=f"mem_{uuid4().hex[:10]}",
            session_id=session.session_id,
            category="semantic" if commit_policy == "direction_memory" else "procedural",
            type="candidate_accepted",
            source_id=candidate.candidate_id,
            asset_id=candidate.source_asset_id,
            part_id=candidate.source_part_id,
            candidate_id=candidate.candidate_id,
            confidence=0.86,
            content={
                "label": candidate.label,
                "commit_policy": commit_policy,
                "stage": candidate_stage or None,
                "fidelity": candidate_fidelity or None,
                "scores": candidate.scores,
                "solution_space": candidate.solution_space,
                "thumbnail_url": candidate.thumbnail_url,
                "mesh_url": candidate.mesh_url,
                "obj_url": candidate.obj_url,
            },
            tags=["accepted", commit_policy, candidate_stage or "stage_unspecified"],
        )
    )


def _next_action_after_accept(candidate_stage: str, commit_policy: str) -> str | None:
    if commit_policy == "active_asset":
        return None
    if candidate_stage in {"silhouette", "global"}:
        return "continue_rough_form_exploration"
    if candidate_stage in {"rough_form", "form"}:
        return "inspect_or_select_part"
    if candidate_stage == "part":
        return "validate_fitted_part"
    if candidate_stage == "texture":
        return "save_or_compare_finish"
    return None


def _record_candidate_rejection(
    session: SessionRecord,
    candidate: Candidate,
    candidate_stage: str,
    candidate_fidelity: str,
) -> None:
    memory = session.metadata.setdefault("candidate_memory", {})
    rejected = memory.setdefault("rejected", [])
    rejected.append(
        {
            "candidate_id": candidate.candidate_id,
            "label": candidate.label,
            "stage": candidate_stage or None,
            "fidelity": candidate_fidelity or None,
            "source_part_id": candidate.source_part_id,
            "scores": candidate.scores,
        }
    )
    memory["last_rejected_candidate_id"] = candidate.candidate_id
    memory["last_rejected_stage"] = candidate_stage or None
    studio_store.save_memory(
        MemoryRecord(
            memory_id=f"mem_{uuid4().hex[:10]}",
            session_id=session.session_id,
            category="reflective",
            type="candidate_rejected",
            source_id=candidate.candidate_id,
            asset_id=candidate.source_asset_id,
            part_id=candidate.source_part_id,
            candidate_id=candidate.candidate_id,
            confidence=0.78,
            content={
                "label": candidate.label,
                "stage": candidate_stage or None,
                "fidelity": candidate_fidelity or None,
                "scores": candidate.scores,
                "solution_space": candidate.solution_space,
            },
            tags=["rejected", candidate_stage or "stage_unspecified"],
        )
    )


def _next_action_after_reject(session: SessionRecord, candidate_stage: str) -> str:
    memory = session.metadata.get("candidate_memory", {})
    rejected = memory.get("rejected") if isinstance(memory, dict) else []
    recent_same_stage = 0
    if isinstance(rejected, list):
        for item in reversed(rejected[-6:]):
            if not isinstance(item, dict) or (item.get("stage") or "") != candidate_stage:
                break
            recent_same_stage += 1
    if recent_same_stage >= 2 and candidate_stage == "part":
        return "revise_part_direction"
    if recent_same_stage >= 2 and candidate_stage in {"silhouette", "global"}:
        return "revise_silhouette_direction"
    if recent_same_stage >= 2:
        return "revise_global_form_direction"
    return "revise_candidate_direction"


def render_case_report(
    case: CaseRecord,
    stage: StageState,
    session_metadata: dict[str, object],
    asset: object,
    accepted_candidates: list[object],
) -> str:
    asset_label = getattr(asset, "label", case.asset_id)
    mesh_url = getattr(asset, "mesh_url", None) or getattr(asset, "obj_url", None) or ""
    rows = "\n".join(
        "<tr>"
        f"<td>{escape(getattr(candidate, 'candidate_id', ''))}</td>"
        f"<td>{escape(getattr(candidate, 'label', ''))}</td>"
        f"<td>{_preview_cell(str(getattr(candidate, 'thumbnail_url', '') or ''))}</td>"
        f"<td>{escape(str(getattr(candidate, 'mesh_url', '') or ''))}</td>"
        f"<td>{escape(str(getattr(candidate, 'obj_url', '') or ''))}</td>"
        "</tr>"
        for candidate in accepted_candidates
    )
    if not rows:
        rows = '<tr><td colspan="5">No accepted candidates were attached.</td></tr>'
    memory_rows = _direction_memory_rows(session_metadata)
    pipeline_rows = _pipeline_evidence_rows(accepted_candidates)
    prompt_chip_rows = _prompt_chip_evidence_rows(accepted_candidates)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{escape(case.title)}</title>
    <style>
      body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 36px; color: #172033; line-height: 1.5; }}
      main {{ max-width: 880px; }}
      h1 {{ margin-bottom: 4px; }}
      section {{ border-top: 1px solid #d7e0eb; padding-top: 18px; margin-top: 18px; }}
      dl {{ display: grid; grid-template-columns: 160px 1fr; gap: 8px 14px; }}
      dt {{ color: #5f6f82; }}
      dd {{ margin: 0; overflow-wrap: anywhere; }}
      table {{ width: 100%; border-collapse: collapse; }}
      th, td {{ border: 1px solid #d7e0eb; padding: 8px; text-align: left; vertical-align: top; }}
      th {{ background: #f3f6fa; }}
      .preview-img {{ display: block; max-width: 180px; max-height: 130px; object-fit: contain; border: 1px solid #d7e0eb; background: #f8fafc; margin-bottom: 6px; }}
      a {{ color: #1d5fd3; overflow-wrap: anywhere; }}
    </style>
  </head>
  <body>
    <main>
      <h1>{escape(case.title)}</h1>
      <p>Saved FlowStudio case: {escape(case.case_id)}</p>
      <section>
        <h2>Design State</h2>
        <dl>
          <dt>Session</dt><dd>{escape(case.session_id)}</dd>
          <dt>Asset</dt><dd>{escape(case.asset_id)} - {escape(asset_label)}</dd>
          <dt>Mesh</dt><dd>{escape(mesh_url)}</dd>
          <dt>Phase</dt><dd>{escape(stage.phase.value)}</dd>
          <dt>Goal</dt><dd>{escape(stage.current_goal or "")}</dd>
        </dl>
      </section>
      <section>
        <h2>Direction Memory</h2>
        <table>
          <thead><tr><th>Candidate</th><th>Stage</th><th>Commit</th><th>Label</th></tr></thead>
          <tbody>{memory_rows}</tbody>
        </table>
      </section>
      <section>
        <h2>Accepted Candidates</h2>
        <table>
          <thead><tr><th>ID</th><th>Label</th><th>Preview</th><th>Mesh</th><th>OBJ</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </section>
      <section>
        <h2>Pipeline Evidence</h2>
        <table>
          <thead><tr><th>Candidate</th><th>Remote Job</th><th>Stage</th><th>Direction</th><th>Preview</th><th>Socket</th><th>Result</th></tr></thead>
          <tbody>{pipeline_rows}</tbody>
        </table>
      </section>
      <section>
        <h2>Prompt Chip Evidence</h2>
        <table>
          <thead><tr><th>Candidate</th><th>Mode</th><th>Selected Tokens</th><th>Source Directions</th><th>Final Prompt</th></tr></thead>
          <tbody>{prompt_chip_rows}</tbody>
        </table>
      </section>
      <section>
        <h2>Notes</h2>
        <p>{escape(case.notes or "")}</p>
      </section>
    </main>
  </body>
</html>
"""


def _preview_cell(url: str) -> str:
    if not url:
        return ""
    safe = escape(url)
    return f'<img class="preview-img" src="{safe}" alt="candidate preview" /><a href="{safe}">{safe}</a>'


def _pipeline_evidence_rows(candidates: list[object]) -> str:
    rows = []
    for candidate in candidates:
        metadata = getattr(candidate, "metadata", {})
        evidence = metadata.get("pipeline_evidence") if isinstance(metadata, dict) else None
        if not isinstance(evidence, dict):
            evidence = {}
        socket = _socket_evidence_label(evidence)
        rows.append(
            "<tr>"
            f"<td>{escape(getattr(candidate, 'candidate_id', ''))}</td>"
            f"<td>{escape(_evidence_value(evidence, metadata, 'remote_job_id'))}</td>"
            f"<td>{escape(_evidence_value(evidence, metadata, 'stage'))}</td>"
            f"<td>{escape(_evidence_value(evidence, metadata, 'direction_id'))}</td>"
            f"<td>{_preview_cell(_evidence_value(evidence, metadata, 'remote_image_url'))}</td>"
            f"<td>{escape(socket)}</td>"
            f"<td>{escape(_evidence_value(evidence, metadata, 'result_path', 'remote_result_path'))}</td>"
            "</tr>"
        )
    return "\n".join(rows) or '<tr><td colspan="7">No pipeline evidence was recorded.</td></tr>'


def _prompt_chip_evidence_rows(candidates: list[object]) -> str:
    rows = []
    for candidate in candidates:
        metadata = getattr(candidate, "metadata", {})
        evidence = metadata.get("pipeline_evidence") if isinstance(metadata, dict) else None
        if not isinstance(metadata, dict):
            metadata = {}
        if not isinstance(evidence, dict):
            evidence = {}
        package = metadata.get("analogy_prompt_package")
        if not isinstance(package, dict):
            package = {}
        tokens = (
            metadata.get("selected_prompt_tokens")
            or evidence.get("selected_prompt_tokens")
            or package.get("selected_prompt_tokens")
            or []
        )
        if isinstance(tokens, list):
            token_text = ", ".join(
                str(item.get("label") if isinstance(item, dict) else item)
                for item in tokens
                if item
            )
        else:
            token_text = ""
        direction_ids = (
            evidence.get("analogy_direction_ids")
            or package.get("direction_ids")
            or metadata.get("direction_ids")
            or []
        )
        if isinstance(direction_ids, list):
            direction_text = ", ".join(str(item) for item in direction_ids if item)
        else:
            direction_text = str(direction_ids or "")
        prompt = str(
            package.get("final_prompt")
            or metadata.get("execution_prompt")
            or evidence.get("execution_prompt")
            or ""
        )
        mode = str(
            metadata.get("prompt_token_mode")
            or evidence.get("prompt_token_mode")
            or package.get("prompt_token_mode")
            or ""
        )
        if not (mode or token_text or prompt):
            continue
        rows.append(
            "<tr>"
            f"<td>{escape(getattr(candidate, 'candidate_id', ''))}</td>"
            f"<td>{escape(mode)}</td>"
            f"<td>{escape(token_text)}</td>"
            f"<td>{escape(direction_text)}</td>"
            f"<td>{escape(prompt)}</td>"
            "</tr>"
        )
    return "\n".join(rows) or '<tr><td colspan="5">No prompt-chip evidence was recorded.</td></tr>'


def _evidence_value(
    evidence: dict[str, object],
    metadata: object,
    key: str,
    metadata_key: str | None = None,
) -> str:
    value = evidence.get(key)
    if value is None and isinstance(metadata, dict):
        value = metadata.get(metadata_key or key)
    return str(value or "")


def _socket_evidence_label(evidence: dict[str, object]) -> str:
    source_part = evidence.get("source_part_id") or evidence.get("target_part_id")
    face_count = evidence.get("socket_face_count")
    if source_part and face_count:
        return f"{source_part} / {face_count} faces"
    if source_part:
        return str(source_part)
    if face_count:
        return f"{face_count} faces"
    return ""


def build_case_manifest(
    case: CaseRecord,
    stage: StageState,
    session_metadata: dict[str, object],
    asset: object,
    accepted_candidates: list[object],
) -> dict[str, object]:
    candidates = [
        candidate.model_dump(mode="json")
        for candidate in accepted_candidates
        if hasattr(candidate, "model_dump")
    ]
    asset_payload = asset.model_dump(mode="json") if hasattr(asset, "model_dump") else {}
    return {
        "schema_version": "flowstudio.case.v1",
        "case": case.model_dump(mode="json"),
        "stage": stage.model_dump(mode="json"),
        "asset": asset_payload,
        "accepted_candidates": candidates,
        "direction_memory": _case_direction_memory(session_metadata),
        "pipeline_evidence": [
            {
                "candidate_id": item.get("candidate_id"),
                "evidence": item.get("metadata", {}).get("pipeline_evidence", {}),
                "mesh_url": item.get("mesh_url"),
                "obj_url": item.get("obj_url"),
                "thumbnail_url": item.get("thumbnail_url"),
            }
            for item in candidates
            if isinstance(item.get("metadata"), dict)
        ],
    }


def write_case_index(cases_root: Path, cases: object) -> None:
    cases_root.mkdir(parents=True, exist_ok=True)
    rows_by_id = {
        str(row["case_id"]): row
        for row in _read_existing_case_index_rows(cases_root / "index.json")
        if row.get("case_id")
    }
    current_rows = [
        {
            "case_id": case.case_id,
            "session_id": case.session_id,
            "title": case.title,
            "asset_id": case.asset_id,
            "report_url": case.report_url,
            "case_url": case.metadata.get("case_url"),
            "accepted_candidate_ids": case.accepted_candidate_ids,
            "created_at": case.created_at.isoformat(),
        }
        for case in cases
    ]
    rows_by_id.update({str(row["case_id"]): row for row in current_rows})
    rows = list(rows_by_id.values())
    rows.sort(key=lambda item: str(item["created_at"]), reverse=True)
    (cases_root / "index.json").write_text(
        json.dumps(
            {
                "schema_version": "flowstudio.case_index.v1",
                "cases": rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def discover_benchmark_assets(files_root: Path) -> list[BenchmarkAssetRecord]:
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
        records.append(
            BenchmarkAssetRecord(
                benchmark_id=str(item.get("benchmark_id") or f"white:{category}:{Path(obj_url).stem}"),
                label=f"{category.replace('_', ' ').title()} · {label}",
                object_type=str(item.get("object_type") or category),
                obj_url=obj_url,
                file_size_bytes=int(item.get("file_size_bytes") or 0),
                reference_status="LOCAL_WHITE_MODEL",
                model_available=True,
                metadata={
                    "source": "local_white_model",
                    "asset_kind": "white_model_source",
                    "category": category,
                    "collection": item.get("collection"),
                    "source_zip": item.get("source_zip"),
                    "image": item.get("thumbnail_url"),
                    "storage_path": storage_path,
                    "texture_index_rule": _benchmark_texture_index_rule("source_obj"),
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
            urlopen(request, timeout=30, context=ssl._create_unverified_context())
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
                urlopen(request, timeout=30, context=ssl._create_unverified_context())
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


def _read_existing_case_index_rows(index_path: Path) -> list[dict[str, object]]:
    if not index_path.exists():
        return []
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    rows = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _case_direction_memory(session_metadata: dict[str, object]) -> dict[str, object]:
    memory = session_metadata.get("candidate_memory")
    return memory if isinstance(memory, dict) else {}


def _planner_control_context(session: SessionRecord) -> dict[str, object]:
    gate = session.metadata.get("planner_control_gate")
    if not isinstance(gate, dict):
        return {
            "status": "unconfirmed",
            "last_decision": None,
            "confirmed_intent": None,
            "rejected_intent": None,
        }
    interpretation_id = gate.get("last_interpretation_id")
    interpretation = (
        studio_store.get_interpretation(str(interpretation_id))
        if isinstance(interpretation_id, str)
        else None
    )
    last_decision = gate.get("last_decision")
    context: dict[str, object] = {
        "status": "confirmed" if last_decision == "accepted" else "rejected"
        if last_decision == "rejected"
        else "unconfirmed",
        "last_decision": last_decision if isinstance(last_decision, str) else None,
        "last_interpretation_id": interpretation_id if isinstance(interpretation_id, str) else None,
        "last_event_id": gate.get("last_event_id") if isinstance(gate.get("last_event_id"), str) else None,
        "last_memory_id": gate.get("last_memory_id") if isinstance(gate.get("last_memory_id"), str) else None,
        "confirmed_intent": None,
        "rejected_intent": None,
    }
    if interpretation is not None:
        payload = {
            "interpretation_id": interpretation.interpretation_id,
            "primary_intent": interpretation.primary_intent.value,
            "confidence": interpretation.confidence,
            "ambiguity": interpretation.ambiguity,
            "assistance_policy": interpretation.assistance_policy.value,
            "target": interpretation.target.model_dump(mode="json"),
            "evidence": interpretation.evidence[:5],
            "suggested_assistance": [
                item.model_dump(mode="json") for item in interpretation.suggested_assistance[:3]
            ],
        }
        if last_decision == "accepted":
            context["confirmed_intent"] = payload
        elif last_decision == "rejected":
            context["rejected_intent"] = payload
    return context


def _request_image_ref_count(image_refs: list[object], reference_images: list[object]) -> int:
    keys: set[str] = set()
    for item in image_refs:
        if isinstance(item, str) and item:
            keys.add(item)
    for item in reference_images:
        if isinstance(item, dict):
            value = item.get("url") or item.get("artifact_id")
            if isinstance(value, str) and value:
                keys.add(value)
        elif isinstance(item, str) and item:
            keys.add(item)
    return len(keys)


def _build_cross_domain_response(
    request: CrossDomainDivergenceRequest,
    asset: object,
    draft: IntentDraft | None,
    session: SessionRecord,
) -> CrossDomainDivergenceResponse:
    object_type = str(getattr(asset, "object_type", None) or "object")
    label = str(getattr(asset, "label", None) or object_type)
    draft_text = draft.text if draft and draft.text else None
    control_context = _planner_control_context(session)
    reference_images = request.metadata.get("reference_images")
    if not isinstance(reference_images, list):
        reference_images = []
    image_refs = request.metadata.get("image_refs")
    if not isinstance(image_refs, list):
        image_refs = []
    image_ref_count = _request_image_ref_count(image_refs, reference_images)
    confirmed_intent = control_context.get("confirmed_intent")
    rejected_intent = control_context.get("rejected_intent")
    confirmed_intent_text = (
        str(confirmed_intent.get("primary_intent"))
        if isinstance(confirmed_intent, dict)
        else ""
    )
    rejected_intent_text = (
        str(rejected_intent.get("primary_intent"))
        if isinstance(rejected_intent, dict)
        else ""
    )
    source_summary = (
        request.source_summary
        or draft_text
        or f"{label}: a {object_type} with the current confirmed edits and constraints"
    )
    constraints = list(
        dict.fromkeys(
            [
                *request.constraints,
                "preserve object identity",
                *(
                    [f"honor confirmed planner intent: {confirmed_intent_text}"]
                    if confirmed_intent_text
                    else []
                ),
                *(
                    [f"do not act on rejected planner intent: {rejected_intent_text}"]
                    if rejected_intent_text
                    else []
                ),
            ]
        )
    )
    ir_matches = _cross_domain_ir_matches(
        request=request,
        object_type=object_type,
        source_summary=source_summary,
        draft=draft,
        control_context=control_context,
    )
    ir_reused = any(isinstance(match, dict) and match.get("ir_reuse") for match in ir_matches)
    ir_recommended_axes = _recommended_axes_from_ir_matches(ir_matches)
    selected_dimensions = request.dimensions or ir_recommended_axes or ["Aesthetic", "Functional", "Structural"]
    qwen_response = _qwen_cross_domain_response(
        request=request,
        asset_label=label,
        object_type=object_type,
        source_summary=source_summary,
        constraints=constraints,
        selected_dimensions=selected_dimensions,
        draft=draft,
        ir_matches=ir_matches,
        control_context=control_context,
    )
    if qwen_response is not None:
        qwen_response.metadata = {
            **qwen_response.metadata,
            "ir_reused_from_interpretation": ir_reused,
            "task": "direction_suggest",
            "interpretation_id": request.interpretation_id
            or request.metadata.get("interpretation_id"),
        }
        return qwen_response
    templates = [
        (
            "Aesthetic",
            "fashion accessory",
            "transfer softness, cuteness, color rhythm, and visual character",
            "Use fashion styling as an analogy source while keeping the base object's recognizability.",
        ),
        (
            "Structural",
            "architecture",
            "transfer layered support, openings, modules, and boundary logic",
            "Use architectural composition to suggest bigger form moves without overwriting protected regions.",
        ),
        (
            "Functional",
            "tool ergonomics",
            "transfer grasp, affordance, visibility, and action cues",
            "Use tool-use relations to turn ambiguous added shapes into purposeful parts.",
        ),
        (
            "Aesthetic",
            "toy design",
            "transfer friendliness, exaggeration, and simplified readable proportions",
            "Use toy-language proportions to make the object more approachable and emotionally legible.",
        ),
        (
            "Structural",
            "plant growth",
            "transfer branching, swelling, tapering, and organic continuity",
            "Use growth patterns to guide extensions while preserving attachment continuity.",
        ),
        (
            "Functional",
            "wearable product",
            "transfer comfort, wrap, fastening, and material-function coupling",
            "Use wearable constraints to reason about additions that touch or surround the object.",
        ),
    ]
    directions: list[AnalogyDirection] = []
    for index, (dimension, target_domain, relation, rationale) in enumerate(templates, start=1):
        if dimension not in selected_dimensions:
            continue
        direction = AnalogyDirection(
            direction_id=f"xdom_{uuid4().hex[:8]}",
            label=f"{dimension}: {object_type} as {target_domain}",
            dimension=dimension,  # type: ignore[arg-type]
            source_domain=f"current {object_type}",
            target_domain=target_domain,
            relation=relation,
            transfer_rationale=rationale,
            constraints=constraints,
            score=max(0.56, 0.86 - index * 0.035),
            metadata={
                "asset_label": label,
                "requested_dimensions": selected_dimensions,
                "intent_draft_id": request.intent_draft_id,
                "behavior_count": len(draft.behavior_atoms) if draft else 0,
                "image_ref_count": image_ref_count,
                "reference_images": reference_images[:6],
                "planner_control_gate": control_context,
                "uses_design_state_ir": bool(ir_matches),
                "ir_recommended_axes": ir_recommended_axes,
                "analogy_expansion_mode": "prompt_chip_composition",
                "retrieved_ir_cases": [match.get("case_id") for match in ir_matches[:3]],
                "prompt_tokens": _analogy_prompt_tokens(
                    dimension=dimension,
                    target_domain=target_domain,
                    relation=relation,
                    object_type=object_type,
                ),
            },
        )
        directions.append(direction)
        if len(directions) >= request.candidate_count:
            break
    return CrossDomainDivergenceResponse(
        session_id=request.session_id,
        asset_id=request.asset_id,
        intent_draft_id=request.intent_draft_id,
        source_summary=source_summary,
        directions=directions,
        evidence=[
            f"active_asset={label}",
            f"object_type={object_type}",
            f"intent_draft={request.intent_draft_id or 'none'}",
            f"planner_gate={control_context.get('status')}",
            f"image_refs={image_ref_count}",
            f"dimensions={','.join(selected_dimensions)}",
            f"design_state_ir={','.join(str(match.get('case_id')) for match in ir_matches[:3]) or 'none'}",
        ],
        metadata={
            "planner_mode": "whole_object_cross_domain_divergence",
            "direct_generation": False,
            "planner_source": "rule_fallback",
            "prompt_token_mode": "human_selectable_chips",
            "analogy_expansion_mode": "prompt_chip_composition",
            "planner_control_gate": control_context,
            "image_refs": image_refs,
            "reference_images": reference_images,
            "uses_design_state_ir": bool(ir_matches),
            "ir_reused_from_interpretation": ir_reused,
            "task": "direction_suggest",
            "interpretation_id": request.interpretation_id
            or request.metadata.get("interpretation_id"),
            "ir_recommended_axes": ir_recommended_axes,
            "retrieved_design_state_ir": ir_matches[:4],
            "retrieved_ir_cases": ir_matches[:4],
            "scope": request.metadata.get("scope"),
            "context_snapshot_id": request.metadata.get("context_snapshot_id"),
            "minimum_semantic_distance": request.metadata.get("minimum_semantic_distance"),
        },
    )


def _qwen_cross_domain_response(
    *,
    request: CrossDomainDivergenceRequest,
    asset_label: str,
    object_type: str,
    source_summary: str,
    constraints: list[str],
    selected_dimensions: list[str],
    draft: IntentDraft | None,
    ir_matches: list[dict[str, object]],
    control_context: dict[str, object],
) -> CrossDomainDivergenceResponse | None:
    endpoint = settings.iul_vlm_intent_url
    if not endpoint:
        return None
    request_image_refs = (
        request.metadata.get("image_refs")
        if isinstance(request.metadata.get("image_refs"), list)
        else []
    )
    request_reference_images = (
        request.metadata.get("reference_images")
        if isinstance(request.metadata.get("reference_images"), list)
        else []
    )
    request_image_ref_count = _request_image_ref_count(
        request_image_refs,
        request_reference_images,
    )
    ir_recommended_axes = _recommended_axes_from_ir_matches(ir_matches)
    behavior_atoms = [
        {
            "tool": atom.tool,
            "target": atom.target,
            "evidence": atom.evidence,
            "order": atom.order,
        }
        for atom in (draft.behavior_atoms if draft else [])
    ][:12]
    prompt = {
        "task": "direction_suggest",
        "task_description": (
            "Generate cross-domain analogy directions for an interaction-aware 3D creative tool."
        ),
        "object_type": object_type,
        "asset_label": asset_label,
        "source_summary": source_summary,
        "confirmed_constraints": constraints,
        "planner_control_gate": control_context,
        "reference_images": request_reference_images,
        "image_refs": request_image_refs,
        "requested_dimensions": selected_dimensions,
        "ir_recommended_axes": ir_recommended_axes,
        "intent_draft": {
            "draft_id": draft.draft_id if draft else None,
            "title": draft.title if draft else None,
            "text": draft.text if draft else None,
            "behavior_atoms": behavior_atoms,
        },
        "retrieved_design_state_ir": ir_matches,
        "requirements": [
            "Return directions for the whole object, not only one part.",
            "Keep object identity and confirmed constraints.",
            "If planner_control_gate.status is confirmed, use confirmed_intent as the stable user-approved context.",
            "If planner_control_gate.status is rejected, do not act on rejected_intent; offer broader or clarification-oriented prompt tokens instead.",
            "This is prompt expansion, not the original CreativeFlow structured-transfer or KG generation pipeline.",
            "Each direction must be specific, explainable, and suitable for later human prompt composition.",
            "For each direction, include 3-6 short prompt_tokens that a human can click and combine into a final image prompt.",
            "Prompt tokens should be concrete words or short phrases, not full sentences.",
            "Do not imply that selecting a direction directly generates an image or mesh; generation happens only after the human confirms the composed prompt.",
            "Do not include prose outside JSON.",
        ],
        "response_schema": {
            "directions": [
                {
                    "label": "short readable label",
                    "dimension": "Aesthetic | Functional | Structural",
                    "source_domain": f"current {object_type}",
                    "target_domain": "cross-domain source",
                    "relation": "what relation transfers",
                    "transfer_rationale": "why the analogy helps this intent",
                    "prompt_tokens": [
                        {
                            "label": "short selectable word or phrase",
                            "dimension": "Aesthetic | Functional | Structural",
                            "role": "style | structure | material | behavior | mood"
                        }
                    ],
                    "constraints": ["constraint strings"],
                    "score": 0.0,
                }
            ],
            "evidence": ["short evidence strings"],
        },
    }
    payload = {
        "model": settings.iul_vlm_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are the hidden Planner for FlowStudio. Return compact JSON only. "
                    "Do not call tools and do not generate final images or meshes. "
                    "The first character of your response must be { and the last character must be }."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(prompt, ensure_ascii=False),
            },
        ],
        "temperature": 0.2,
        "max_tokens": 900,
        "response_format": {"type": "json_object"},
    }
    try:
        http_request = UrlRequest(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(http_request, timeout=max(settings.iul_vlm_timeout_sec, 30)) as response:
            raw = json.loads(response.read().decode("utf-8"))
        content = _chat_completion_content(raw)
        parsed = _extract_json_payload(content)
        raw_directions = parsed.get("directions")
        if not isinstance(raw_directions, list):
            return None
        directions: list[AnalogyDirection] = []
        for index, item in enumerate(raw_directions[: request.candidate_count], start=1):
            if not isinstance(item, dict):
                continue
            fallback_dimension = selected_dimensions[(index - 1) % len(selected_dimensions)]
            direction_dimension = _safe_direction_dimension(item.get("dimension"), fallback=fallback_dimension)
            try:
                direction = AnalogyDirection(
                    direction_id=f"xdom_qwen_{uuid4().hex[:8]}",
                    label=str(item.get("label") or f"Cross-domain direction {index}")[:96],
                    dimension=direction_dimension,
                    divergence_mode="cross_domain",
                    source_domain=str(item.get("source_domain") or f"current {object_type}")[:80],
                    target_domain=str(item.get("target_domain") or "cross-domain source")[:80],
                    relation=str(item.get("relation") or "transfer a relevant relation")[:240],
                    transfer_rationale=str(
                        item.get("transfer_rationale") or item.get("rationale") or ""
                    )[:360],
                    constraints=[
                        str(value)[:120]
                        for value in dict.fromkeys(
                            [
                                *(
                                    item.get("constraints")
                                    if isinstance(item.get("constraints"), list)
                                    else []
                                ),
                                *constraints,
                            ]
                        )
                    ][:8],
                    score=max(0.0, min(1.0, float(item.get("score", 0.74)))),
                    metadata={
                        "planner_source": "qwen3-planner",
                        "planner_model": settings.iul_vlm_model,
                        "intent_draft_id": request.intent_draft_id,
                        "behavior_count": len(behavior_atoms),
                        "image_ref_count": request_image_ref_count,
                        "planner_control_gate": control_context,
                        "uses_design_state_ir": True,
                        "ir_recommended_axes": ir_recommended_axes,
                        "analogy_expansion_mode": "prompt_chip_composition",
                        "prompt_tokens": _coerce_prompt_tokens(
                            item.get("prompt_tokens"),
                            fallback_dimension=direction_dimension,
                            target_domain=str(item.get("target_domain") or "cross-domain source"),
                            relation=str(item.get("relation") or "transfer a relevant relation"),
                            object_type=object_type,
                        ),
                    },
                )
            except (TypeError, ValueError):
                continue
            directions.append(direction)
        if not directions:
            return None
        evidence = parsed.get("evidence")
        if not isinstance(evidence, list):
            evidence = [
                f"active_asset={asset_label}",
                f"object_type={object_type}",
                "planner=qwen3-planner",
            ]
        evidence = [
            *[str(value)[:160] for value in evidence[:8]],
            f"planner_gate={control_context.get('status')}",
        ]
        return CrossDomainDivergenceResponse(
            session_id=request.session_id,
            asset_id=request.asset_id,
            intent_draft_id=request.intent_draft_id,
            source_summary=source_summary,
            directions=directions,
            evidence=list(dict.fromkeys(evidence))[:9],
            metadata={
                "planner_mode": "whole_object_cross_domain_divergence",
                "direct_generation": False,
                "planner_source": "qwen3-planner",
                "planner_model": settings.iul_vlm_model,
                "prompt_token_mode": "human_selectable_chips",
                "analogy_expansion_mode": "prompt_chip_composition",
                "planner_control_gate": control_context,
                "image_refs": request_image_refs,
                "reference_images": request_reference_images,
                "fallback_used": False,
                "uses_design_state_ir": True,
                "ir_recommended_axes": ir_recommended_axes,
                "retrieved_design_state_ir": ir_matches[:4],
                "retrieved_ir_cases": [match.get("case_id") for match in ir_matches[:4]],
                "scope": request.metadata.get("scope"),
                "context_snapshot_id": request.metadata.get("context_snapshot_id"),
                "minimum_semantic_distance": request.metadata.get("minimum_semantic_distance"),
            },
        )
    except Exception:
        return None


def _chat_completion_content(response: dict[str, object]) -> str:
    choices = response.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"]
            if isinstance(first.get("text"), str):
                return first["text"]
    if isinstance(response.get("content"), str):
        return response["content"]
    return json.dumps(response, ensure_ascii=False)


def _extract_json_payload(content: str) -> dict[str, object]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.IGNORECASE).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if match is None:
            return {}
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return payload if isinstance(payload, dict) else {}


def _safe_direction_dimension(value: object, fallback: str = "Aesthetic") -> str:
    text = str(value or "").strip()
    if text in {"Aesthetic", "Functional", "Structural"}:
        return text
    return fallback if fallback in {"Aesthetic", "Functional", "Structural"} else "Aesthetic"


def _analogy_prompt_tokens(
    *,
    dimension: str,
    target_domain: str,
    relation: str,
    object_type: str,
) -> list[dict[str, object]]:
    base: list[tuple[str, str]] = [
        (target_domain, "source_domain"),
        (relation, "relation"),
    ]
    if dimension == "Aesthetic":
        base.extend([("cute proportion", "style"), ("soft color rhythm", "style")])
    elif dimension == "Structural":
        base.extend([("layered silhouette", "structure"), ("modular outline", "structure")])
    elif dimension == "Functional":
        base.extend([("clear affordance", "behavior"), ("purposeful detail", "behavior")])
    else:
        base.extend([("cross-domain analogy", "mood"), (f"recognizable {object_type}", "constraint")])
    tokens: list[dict[str, object]] = []
    seen: set[str] = set()
    for index, (label, role) in enumerate(base, start=1):
        clean = re.sub(r"\s+", " ", str(label)).strip(" .,:;")
        if not clean or clean.lower() in seen:
            continue
        seen.add(clean.lower())
        tokens.append(
            {
                "token_id": f"tok_{uuid4().hex[:8]}",
                "label": clean[:64],
                "dimension": dimension if dimension in {"Aesthetic", "Functional", "Structural"} else "Aesthetic",
                "role": role,
                "source": "planner_rule",
                "weight": max(0.55, 0.9 - index * 0.06),
            }
        )
        if len(tokens) >= 5:
            break
    return tokens


def _coerce_prompt_tokens(
    value: object,
    *,
    fallback_dimension: str,
    target_domain: str,
    relation: str,
    object_type: str,
) -> list[dict[str, object]]:
    tokens: list[dict[str, object]] = []
    if isinstance(value, list):
        for item in value[:8]:
            if isinstance(item, str):
                label = item
                dimension = fallback_dimension
                role = "analogy"
            elif isinstance(item, dict):
                label = str(item.get("label") or item.get("text") or "").strip()
                dimension = str(item.get("dimension") or fallback_dimension)
                role = str(item.get("role") or "analogy")
            else:
                continue
            label = re.sub(r"\s+", " ", label).strip(" .,:;")
            if not label:
                continue
            tokens.append(
                {
                    "token_id": f"tok_qwen_{uuid4().hex[:8]}",
                    "label": label[:64],
                    "dimension": dimension if dimension in {"Aesthetic", "Functional", "Structural"} else "Aesthetic",
                    "role": role[:32],
                    "source": "qwen3-planner",
                    "weight": 0.78,
                }
            )
    if tokens:
        return tokens[:6]
    return _analogy_prompt_tokens(
        dimension=fallback_dimension,
        target_domain=target_domain,
        relation=relation,
        object_type=object_type,
    )


def _recommended_axes_from_ir_matches(matches: list[dict[str, object]]) -> list[str]:
    scores: dict[str, float] = {}
    for match in matches:
        strength = {"high": 1.0, "medium": 0.75, "low": 0.45}.get(
            str(match.get("evidence_strength") or "low"),
            0.45,
        )
        raw_axes = match.get("recommended_axes")
        if not isinstance(raw_axes, list):
            continue
        match_score = float(match.get("score") or 0.0)
        for rank, raw_axis in enumerate(raw_axes):
            axis = str(raw_axis)
            if axis not in {"Aesthetic", "Functional", "Structural"}:
                continue
            scores[axis] = scores.get(axis, 0.0) + match_score * strength * max(0.35, 1.0 - rank * 0.18)
    return [axis for axis, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)[:3]]


def _cross_domain_ir_matches(
    *,
    request: CrossDomainDivergenceRequest,
    object_type: str,
    source_summary: str,
    draft: IntentDraft | None,
    control_context: dict[str, object],
) -> list[dict[str, object]]:
    interpretation_id = request.interpretation_id or request.metadata.get("interpretation_id")
    if isinstance(interpretation_id, str) and interpretation_id:
        interpretation = studio_store.get_interpretation(interpretation_id)
        if interpretation is not None:
            ir_block = interpretation.features.get("design_state_ir")
            if isinstance(ir_block, dict):
                matches = ir_block.get("matches")
                if isinstance(matches, list) and matches:
                    reused: list[dict[str, object]] = []
                    for item in matches:
                        if isinstance(item, dict):
                            row = dict(item)
                            row.setdefault("ir_reuse", True)
                            row.setdefault("interpretation_id", interpretation_id)
                            reused.append(row)
                    if reused:
                        return reused

    retriever = interaction_service.ir_retriever
    if not retriever.ready:
        return []
    behavior_tools = [
        str(atom.tool)
        for atom in (draft.behavior_atoms if draft else [])
    ]
    confirmed = control_context.get("confirmed_intent")
    rejected = control_context.get("rejected_intent")
    confirmed_text = (
        str(confirmed.get("primary_intent"))
        if isinstance(confirmed, dict)
        else ""
    )
    rejected_text = (
        str(rejected.get("primary_intent"))
        if isinstance(rejected, dict)
        else ""
    )
    image_refs = request.metadata.get("image_refs")
    if not isinstance(image_refs, list):
        image_refs = []
    reference_images = request.metadata.get("reference_images")
    if not isinstance(reference_images, list):
        reference_images = []
    image_ref_count = _request_image_ref_count(image_refs, reference_images)
    live_signals = request.metadata.get("live_signals")
    if not isinstance(live_signals, dict):
        live_signals = {}
    features = {
        "event_type": "cross_domain_diverge",
        "selection_type": "none",
        "creative_stage": "global",
        "intent_text": " ".join(
            [
                source_summary,
                draft.text if draft and draft.text else "",
                confirmed_text,
                f"rejected:{rejected_text}" if rejected_text else "",
                f"image_refs:{image_ref_count}",
                " ".join(behavior_tools),
                object_type,
            ]
        ),
        "ir_scope_hint": "whole_object",
        "recent_reject_count": 0,
        "recent_accept_count": 1 if control_context.get("status") == "confirmed" else 0,
        "same_event_type_recent_count": len(behavior_tools),
        "live_signals": live_signals,
        "signals": {
            "interaction": {
                "event_type": "cross_domain_diverge",
                "behavior_tools": behavior_tools,
                "planner_gate_status": control_context.get("status"),
            },
            "semantic": {
                "object_type": object_type,
                "intent_text": source_summary,
                "confirmed_intent": confirmed_text,
                "rejected_intent": rejected_text,
                "image_ref_count": image_ref_count,
            },
            "visual_context": {
                "image_refs": image_refs,
                "reference_images": reference_images,
                "image_ref_count": image_ref_count,
            },
        },
    }
    return [match.to_feature() for match in retriever.retrieve(features, top_k=4)]


def _direction_memory_rows(session_metadata: dict[str, object]) -> str:
    memory = session_metadata.get("candidate_memory")
    if not isinstance(memory, dict):
        return '<tr><td colspan="4">No direction memory was recorded.</td></tr>'
    accepted = memory.get("accepted")
    if not isinstance(accepted, list) or not accepted:
        return '<tr><td colspan="4">No direction memory was recorded.</td></tr>'
    rows = []
    for item in accepted:
        if not isinstance(item, dict):
            continue
        rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('candidate_id') or ''))}</td>"
            f"<td>{escape(str(item.get('stage') or ''))}</td>"
            f"<td>{escape(str(item.get('commit_policy') or ''))}</td>"
            f"<td>{escape(str(item.get('label') or ''))}</td>"
            "</tr>"
        )
    return "\n".join(rows) or '<tr><td colspan="4">No direction memory was recorded.</td></tr>'
