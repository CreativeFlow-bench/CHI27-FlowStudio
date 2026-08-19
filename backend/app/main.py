from __future__ import annotations

import base64
import asyncio
import json
import logging
import os
import re
import shutil
import ssl
import sys
import time
from html import escape
from pathlib import Path
from urllib.parse import quote, unquote, urlparse
from urllib.request import Request as UrlRequest, urlopen
from uuid import UUID, uuid4

logger = logging.getLogger("flowstudio.api")

# LaunchAgent runs uvicorn with WorkingDirectory=backend/, but post-process
# helpers live in the repo-root package ``remote_worker``.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

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
from starlette.middleware.gzip import GZipMiddleware

from app.api import (
    create_actions_router,
    create_assets_router,
    create_candidates_router,
    create_four_stage_router,
    create_realtime_observation_router,
    create_sessions_router,
    create_directions_router,
    create_generation_router,
    create_perception_router,
    create_sandbox_router,
    create_system_router,
    create_projects_router,
    create_interaction_router,
)
from app.api.perception_flow import interpret_and_publish
from app.api.solution_space import build_solution_space_view
from app.config import Settings, get_settings
from app.services import system_services
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
    AssetVersionRecord,
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
from app.services.generation.creativeflow_adapter import CreativeFlowAdapter
from app.services.generation.autopartgen_adapter import AutoPartGenAdapter
from app.services.divergence import contextual_divergence
from app.services.divergence.semantic_divergence_service import SemanticDivergenceService
from app.services.divergence.semantic_knowledge_router import SemanticKnowledgeRouter
from app.services.divergence.semantic_model_clients import (
    GeminiSemanticGenerator,
    LocalVlmSemanticGenerator,
)
from app.services.divergence.semantic_validator import SemanticCandidateValidator
from app.services.generation.generation_orchestrator import (
    GenerationOrchestrator,
    RemoteCreativeFlowWorkerAdapter,
    ThreeDGenerationDisabled,
)
from app.services.generation.geometry_worker import GeometryProcessingWorker
from app.services.intent.interaction_understanding import InteractionUnderstandingService
from app.services.storage.job_store import InMemoryJobStore
from app.services.intent.multimodal_intent_predictor import build_multimodal_intent_predictor
from app.services.encoding import EventNormalizer, FourStageEncodingService
from app.services.encoding.four_stage_encoding import RuleIntentEncoder
from app.services.encoding.qwen_intent_encoder import QwenIntentEncoder
from app.services.model_api.runtime import build_external_model_runtime
from app.services.retrieval import FourStageRetrievalService
from app.services.generation.four_stage_generation import FourStageGenerationService
from app.services.generation.four_stage_spec_builder import GenerationSpecBuilder
from app.services.generation.four_stage_quality import GenerationQualityGate
from app.services.generation.image_batch import generate_accepted_image_batch
from app.services.generation.qwen_image_client import QwenImageClient, QwenImageUnavailable
from app.services.rerepresentation import (
    EvidenceAssembler,
    FourStageDecisionService,
    GeminiClient,
    RuleDecisionService,
)
from app.services.pipeline.four_stage_orchestrator import (
    FourStageOrchestrator,
)
from app.services.intent.realtime_observation import RealtimeObservationService
from app.services.interaction import InteractionOrchestrator
from app.services.storage.four_stage_store import FourStageStore
from app.services.generation.part_lifecycle import (
    attach_viewport_2d_evidence,
    find_part,
    read_lifecycle,
)
from app.services.generation.render_preview_worker import RenderPreviewWorker
from app.services.storage.studio_store import InMemoryStudioStore
from app.services.storage.experiment_project_store import ExperimentProjectStore
from app.services.storage.websocket_manager import WebSocketManager
from app.services.divergence import create_direction_suggestion_builder
from app.services.storage.benchmark import (
    _benchmark_tree_material,
    _download_oss_object,
    _resolve_benchmark_texture_key,
    discover_benchmark_assets,
)
from app.services.divergence.cross_domain import (
    _build_cross_domain_response,
    _prompt_chip_evidence_rows,
    configure_cross_domain,
)
from app.services.divergence.prompt_chip import (
    _build_prompt_chip_package,
    configure_prompt_chip,
)
from app.services.intent.perception_helpers import (
    _compact_evidence_summary,
    _live_signals_payload,
    _perception_payload,
    _publish_perception,
    _update_session_live_signals,
    configure_perception,
)
from app.services.storage.cases import (
    _case_direction_memory,
    _direction_memory_rows,
    _read_existing_case_index_rows,
    configure_cases,
    render_case_report,
    write_case_index,
)

from app.services.intent.interaction_features import unique_ref_count as _request_image_ref_count

legacy_job_store = InMemoryJobStore()
studio_store = InMemoryStudioStore()
websocket_manager = WebSocketManager()
settings = get_settings()
four_stage_store = FourStageStore()
experiment_project_store = ExperimentProjectStore()
external_model_runtime = build_external_model_runtime(
    settings,
    audit=four_stage_store.record_model_call,
)
system_services.configure_runtime(
    enable_legacy_models=external_model_runtime.profile.enable_legacy_local_models,
    enable_3d=external_model_runtime.profile.enable_3d_generation,
)
if external_model_runtime.profile.enable_legacy_local_models:
    intent_model = QwenIntentEncoder(
        settings.iul_vlm_intent_url,
        model_name=settings.iul_vlm_model,
        timeout_sec=settings.iul_vlm_timeout_sec,
    )
    decision_model = GeminiClient(
        settings.gemini_api_base,
        settings.gemini_api_key,
        model=settings.gemini_model,
        timeout_sec=settings.gemini_timeout_sec,
        max_retries=settings.gemini_max_retries,
        max_images=settings.gemini_max_images,
        audit=four_stage_store.record_model_call,
    )
    semantic_primary_model = GeminiSemanticGenerator(
        settings.gemini_api_base,
        settings.gemini_api_key,
        model=settings.gemini_model,
        timeout_sec=settings.semantic_divergence_timeout_sec,
    )
    semantic_fallback_model = LocalVlmSemanticGenerator(
        settings.iul_vlm_intent_url or "",
        model=settings.iul_vlm_model,
        timeout_sec=settings.semantic_divergence_vlm_timeout_sec,
    )
else:
    intent_model = external_model_runtime.intent_encoder
    decision_model = external_model_runtime.decision_client
    semantic_primary_model = external_model_runtime.semantic_primary
    semantic_fallback_model = external_model_runtime.semantic_fallback

four_stage_encoding_service = FourStageEncodingService(
    normalizer=EventNormalizer(),
    qwen_encoder=intent_model,
    rule_encoder=RuleIntentEncoder(),
    asset_lookup=lambda asset_id: (
        {
            "object_type": asset.object_type,
            "label": asset.label,
            "mesh_url": asset.mesh_url,
            "obj_url": asset.obj_url,
            "thumbnail_url": asset.thumbnail_url,
            "metadata": asset.metadata,
        }
        if (asset := studio_store.get_asset(asset_id)) is not None
        else {}
    ),
)
four_stage_retrieval_service = FourStageRetrievalService(store=four_stage_store)
four_stage_decision_service = FourStageDecisionService(
    assembler=EvidenceAssembler(
        max_images=settings.gemini_max_images,
        max_image_bytes=settings.gemini_max_image_bytes,
    ),
    gemini_client=decision_model,
    rule_decision=RuleDecisionService(),
    enabled=(
        settings.gemini_rerepresentation_enabled
        if external_model_runtime.profile.enable_legacy_local_models
        else bool(external_model_runtime.profile.api_key)
    ),
    feedback_lookup=four_stage_store.retrieval_outcome_score,
)
semantic_divergence_service = SemanticDivergenceService(
    store=four_stage_store,
    knowledge_router=SemanticKnowledgeRouter(),
    gemini=semantic_primary_model,
    local_vlm=semantic_fallback_model,
    validator=SemanticCandidateValidator(),
    call_timeout_sec=settings.semantic_divergence_timeout_sec,
)


def _qwen_image_base() -> str:
    raw = os.environ.get("CF_QWEN_IMAGE_URL", "") or "http://127.0.0.1:18082"
    return raw.rsplit("/generate", 1)[0].rstrip("/") or "http://127.0.0.1:18082"


image_generation_client = (
    QwenImageClient(_qwen_image_base())
    if external_model_runtime.profile.enable_legacy_local_models
    else external_model_runtime.image_client
)


def _resolve_four_stage_image_ref(ref: str | None, files_root: Path) -> str | None:
    """Resolve a SourceContext image/mask reference to a local worker path."""
    if not ref:
        return None
    value = str(ref).strip()
    if value.startswith("/files/"):
        candidate = (files_root / value.removeprefix("/files/")).resolve()
        if files_root.resolve() in candidate.parents and candidate.is_file():
            return str(candidate)
        return None
    candidate = Path(value).expanduser()
    return str(candidate.resolve()) if candidate.is_file() else None


async def _materialize_four_stage_image_ref(
    ref: str | None,
    files_root: Path,
    destination: Path,
) -> str | None:
    """Materialize an external OSS image so the local Qwen service can read it."""
    local = _resolve_four_stage_image_ref(ref, files_root)
    if local:
        return local
    value = str(ref or "").strip()
    if not value.startswith(("http://", "https://")):
        return None
    try:
        def _download() -> bytes:
            with urlopen(value, timeout=45) as response:
                data = response.read(20 * 1024 * 1024 + 1)
            if len(data) > 20 * 1024 * 1024:
                raise ValueError("source image exceeds 20 MB")
            return data

        data = await asyncio.to_thread(_download)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        return str(destination)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not materialize source image %s: %s", value[:160], exc)
        return None


async def _four_stage_generate_images(
    spec,
    *,
    session_id: str | None = None,
    run_id: str | None = None,
) -> list[dict[str, object]]:
    """Edit the identity source through the active image API and persist PNGs."""
    import shutil

    files_root = Path(__file__).resolve().parents[1] / "storage" / "files"
    out_root = files_root / "four_stage" / spec.generation_id
    out_root.mkdir(parents=True, exist_ok=True)
    # 新批次按时间线生成：清理旧的 four_stage 批次，只保留最近 5 批，
    # 避免前端/Solution Space 看到历史残留图片。
    try:
        batches = sorted(
            (entry for entry in (files_root / "four_stage").iterdir() if entry.is_dir()),
            key=lambda entry: entry.stat().st_mtime,
            reverse=True,
        )
        for stale in batches[5:]:
            shutil.rmtree(stale, ignore_errors=True)
            logger.info("four_stage pruned stale batch %s", stale.name)
    except OSError:
        pass
    total = len(spec.prompt_candidates[: spec.candidate_count])
    source = getattr(spec, "source", None)
    source_image = await _materialize_four_stage_image_ref(
        getattr(source, "source_image_ref", None) if source else None,
        files_root,
        out_root / "source.png",
    )
    source_mask = await _materialize_four_stage_image_ref(
        getattr(source, "target_mask_ref", None) if source else None,
        files_root,
        out_root / "mask.png",
    )
    if not source_image:
        raise RuntimeError(
            "source identity image is required for four-stage generation; "
            "upload/attach a viewport image before Generate"
        )
    identity_mode = "masked" if source_mask else "conditioned"
    progress_artifacts: list[dict[str, object]] = []

    async def _generate_attempt(
        index: int,
        prompt: str,
        seed: int,
        attempt: int,
    ) -> dict[str, object] | None:
        retry_seed = seed + attempt * 1_000_003
        try:
            png = await image_generation_client.generate_conditioned(
                prompt,
                retry_seed,
                source_image_path=source_image,
                mask_image_path=source_mask,
            )
        except QwenImageUnavailable as exc:
            raise RuntimeError(f"Qwen-Image generation unavailable: {exc}") from exc
        relative = f"four_stage/{spec.generation_id}/candidate_{index + 1:02d}.png"
        image_path = out_root / f"candidate_{index + 1:02d}.png"
        image_path.write_bytes(png)
        from remote_worker.variation_stage2_images import (
            fit_generated_subject_safe_margin,
            normalize_generated_studio_background,
            visual_acceptance,
        )

        await asyncio.to_thread(normalize_generated_studio_background, image_path)
        await asyncio.to_thread(fit_generated_subject_safe_margin, image_path)

        qa = await asyncio.to_thread(
            visual_acceptance,
            image_path,
            stage=str(getattr(spec.target, "scope", "whole")),
        )
        # Soft QA only: selected-keyword Generate always ships the image.
        if not qa.get("accepted"):
            logger.warning(
                "four_stage soft-qa candidate=%s attempt=%s qa=%s",
                index + 1,
                attempt + 1,
                qa,
            )
            qa = {**qa, "accepted": True, "soft_override": True}
        artifact: dict[str, object] = {
            "candidate_id": f"cand_{spec.generation_id}_{index + 1:02d}",
            "url": f"/files/{relative}",
            "prompt": prompt,
            "seed": retry_seed,
            "identity_mode": identity_mode,
            "source_image_ref": getattr(source, "source_image_ref", None) if source else None,
            "target_mask_ref": getattr(source, "target_mask_ref", None) if source else None,
            "visual_acceptance": qa,
            "kind": "png",
        }
        progress_artifacts.append(artifact)
        # Persist mid-flight so frontend run polling can show cards even if WS drops.
        if run_id:
            try:
                current = four_stage_store.get_run(run_id)
                if current is not None:
                    current.generation_artifacts = list(progress_artifacts)
                    four_stage_store.save_run(current)
            except Exception:  # pragma: no cover
                logger.warning("four_stage progress persist failed", exc_info=True)
        # 串行生成：每完成一张就实时推给前端（进度 + 已完成产物），
        # 避免 8 张生成期间前端长时间无反馈。
        if session_id and websocket_manager is not None:
            try:
                await websocket_manager.broadcast(
                    session_id,
                    "four_stage.generation_progress",
                    {
                        "run_id": run_id,
                        "session_id": session_id,
                        "stage": "generation",
                        "generation_id": spec.generation_id,
                        "completed_count": len(progress_artifacts),
                        "total_count": total,
                        "artifacts": list(progress_artifacts),
                    },
                )
            except Exception:  # pragma: no cover - ws must not break generation
                logger.warning("four_stage progress ws failed", exc_info=True)
        return artifact

    return await generate_accepted_image_batch(
        spec.prompt_candidates[: spec.candidate_count],
        spec.seeds,
        generate_attempt=_generate_attempt,
        minimum_accepted=min(8, max(1, total)),
        max_attempts_per_prompt=2,
    )


async def _four_stage_dispatch(run, spec) -> dict[str, object]:
    """Render Gate-selected prompts; run the Hy3D 3D chain when requested."""
    if getattr(spec, "run_hy3d", False):
        if not external_model_runtime.profile.enable_3d_generation:
            raise ThreeDGenerationDisabled()
        return await _four_stage_dispatch_hy3d(run, spec)
    artifacts = await _four_stage_generate_images(
        spec,
        session_id=run.session_id,
        run_id=run.run_id,
    )
    return {
        "remote_job_id": f"direct_{spec.generation_id}",
        "artifacts": artifacts,
    }


async def _four_stage_dispatch_hy3d(run, spec) -> dict[str, object]:
    """Staged CreativeFlow -> candidates -> Hy3D mesh (strategy doc 9.4/9.5)."""
    if not external_model_runtime.profile.enable_3d_generation:
        raise ThreeDGenerationDisabled()
    from app.models import GenerationOptions, Intent, Selection, SelectionType

    is_part = bool(spec.target.part_id) or spec.target.scope == "part"
    stage = "part" if is_part else "silhouette"
    pipeline = f"creativeflow-{'part' if is_part else 'global'}"
    fidelity = "medium" if is_part else "low"
    request = GenerationRequest(
        session_id=run.session_id,
        asset_id=spec.asset_id or "",
        selection=Selection(
            type=SelectionType.part if is_part else SelectionType.none,
            part_id=spec.target.part_id,
            label=spec.target.part_id,
        ),
        intent=Intent(
            mode=GenerationMode.diverge,
            text=spec.prompt_candidates[0]
            if spec.prompt_candidates
            else (spec.keywords[0] if spec.keywords else "diverge"),
            constraints=spec.preserved_constraints,
            metadata={
                "four_stage_generation_id": spec.generation_id,
                "four_stage_run_id": run.run_id,
                "prompt_candidates": spec.prompt_candidates,
                "seeds": spec.seeds,
            },
        ),
        generation=GenerationOptions(
            candidate_count=spec.candidate_count,
            diversity=0.7,
            output_format="glb",
            metadata={
                "pipeline": pipeline,
                "stage": stage,
                "fidelity": fidelity,
                "divergence_axes": spec.keywords,
                "fit_policy": "preserve_socket" if is_part else "stage_default",
                "four_stage": True,
                "prompts": spec.prompt_candidates,
                "seeds": spec.seeds,
            },
        ),
    )
    job = await generation_orchestrator.create_generation_job(request)
    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        current = studio_store.get_job(job.job_id)
        if current is None:
            raise RuntimeError("hy3d source job disappeared")
        if current.status.value == "completed":
            break
        if current.status.value in {"failed", "cancelled"}:
            detail = current.error.message if current.error else "no detail"
            raise RuntimeError(f"hy3d staged source failed: {detail}")
        await asyncio.sleep(5)
    else:
        raise TimeoutError("hy3d staged source timed out")

    candidates = [
        candidate
        for candidate_id in (current.candidate_ids or [])
        if (candidate := studio_store.get_candidate(candidate_id)) is not None
    ]
    if not candidates:
        raise RuntimeError("hy3d staged source produced no candidates")
    target = candidates[0]
    await generation_orchestrator.generate_candidate_hy3d(
        target.candidate_id, run.session_id
    )
    refreshed = studio_store.get_candidate(target.candidate_id) or target
    artifacts: list[dict[str, object]] = []
    if refreshed.thumbnail_url:
        artifacts.append(
            {
                "candidate_id": refreshed.candidate_id,
                "url": refreshed.thumbnail_url,
                "kind": "image",
                "label": refreshed.label,
            }
        )
    if refreshed.mesh_url:
        artifacts.append(
            {
                "candidate_id": refreshed.candidate_id,
                "url": refreshed.mesh_url,
                "kind": "mesh_glb",
                "label": refreshed.label,
            }
        )
    if refreshed.obj_url:
        artifacts.append(
            {
                "candidate_id": refreshed.candidate_id,
                "url": refreshed.obj_url,
                "kind": "mesh_obj",
                "label": refreshed.label,
            }
        )
    if not artifacts:
        raise RuntimeError("hy3d produced no artifacts (image or mesh)")
    return {
        "remote_job_id": f"hy3d_{spec.generation_id}",
        "artifacts": artifacts,
    }


async def _four_stage_poll(remote_job_id: str) -> dict[str, object]:
    job = studio_store.get_job(remote_job_id)
    if job is None:
        return {"status": "running"}
    if job.status.value == "completed":
        candidates = [
            candidate
            for candidate in studio_store.candidates.values()
            if candidate.job_id == remote_job_id
        ]
        artifacts = [
            {
                "candidate_id": candidate.candidate_id,
                "url": candidate.thumbnail_url or candidate.mesh_url,
                "label": candidate.label,
            }
            for candidate in candidates
            if candidate.thumbnail_url or candidate.mesh_url
        ]
        return {"status": "completed", "artifacts": artifacts}
    if job.status.value in {"failed", "cancelled"}:
        return {
            "status": job.status.value,
            "error": job.error.model_dump(mode="json") if job.error else None,
        }
    return {"status": "running"}


four_stage_generation_service = FourStageGenerationService(
    four_stage_store,
    builder=GenerationSpecBuilder(model=external_model_runtime.profile.image_model),
    quality_gate=GenerationQualityGate(),
    dispatch=_four_stage_dispatch,
    poll=_four_stage_poll,
)
four_stage_orchestrator = FourStageOrchestrator(
    store=four_stage_store,
    encoding_service=four_stage_encoding_service,
    retrieval_service=four_stage_retrieval_service,
    decision_service=four_stage_decision_service,
    generation_service=four_stage_generation_service,
    semantic_divergence_service=semantic_divergence_service,
    websocket_manager=websocket_manager,
)
realtime_observation_service = RealtimeObservationService(
    four_stage_store,
    four_stage_orchestrator,
    recorder=experiment_project_store,
    text_gateway=external_model_runtime.text_gateway,
)
if "pytest" in sys.modules:
    realtime_observation_service.gate_llm_enabled = False
interaction_orchestrator = InteractionOrchestrator(
    store=four_stage_store,
    pipeline=four_stage_orchestrator,
    observation=realtime_observation_service,
    websocket_manager=websocket_manager,
)
realtime_observation_service.interaction_orchestrator = interaction_orchestrator


async def _four_stage_on_failed(run_id: str, error: Exception) -> None:
    await four_stage_orchestrator.finalize_generation(run_id, error=error)
    await realtime_observation_service.on_run_finished(run_id)


async def _four_stage_on_complete(
    run_id: str,
    artifacts: list[dict[str, object]] | None = None,
) -> None:
    await four_stage_orchestrator.finalize_generation(run_id, artifacts=artifacts)
    await realtime_observation_service.on_run_finished(run_id)


four_stage_generation_service.set_completion_callbacks(
    on_complete=_four_stage_on_complete,
    on_failed=_four_stage_on_failed,
)
interaction_predictor = (
    build_multimodal_intent_predictor(
        settings.iul_vlm_intent_url,
        timeout_sec=settings.iul_vlm_timeout_sec,
        fallback_to_rules=settings.iul_vlm_fallback_to_rules,
        fallback_endpoint_urls=[
            item.strip()
            for item in (settings.iul_vlm_fallback_urls or "").split(",")
            if item.strip()
        ],
        model_name=settings.iul_vlm_model,
    )
    if external_model_runtime.profile.enable_legacy_local_models
    else external_model_runtime.interaction_predictor
)
interaction_service = InteractionUnderstandingService(
    studio_store,
    predictor=interaction_predictor,
)
remote_worker_url = (
    settings.remote_creativeflow_worker_url
    if (
        external_model_runtime.profile.enable_legacy_local_models
        or external_model_runtime.profile.enable_3d_generation
    )
    else None
)
remote_worker_adapter = RemoteCreativeFlowWorkerAdapter(
    remote_worker_url,
    real_jobs=settings.remote_creativeflow_real_jobs,
    transfer_variant=settings.remote_creativeflow_transfer_variant,
)
generation_orchestrator = GenerationOrchestrator(
    studio_store,
    websocket_manager,
    remote_worker_adapter,
    auto_hy3d=settings.remote_creativeflow_auto_hy3d,
    hy3d_max_candidates=settings.remote_creativeflow_hy3d_max_candidates,
    enable_3d_generation=external_model_runtime.profile.enable_3d_generation,
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
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    storage_root = Path(__file__).resolve().parents[1] / "storage"
    files_root = storage_root / "files"
    files_root.mkdir(parents=True, exist_ok=True)
    realtime_observation_service.files_root = files_root
    configure_cross_domain(
        studio_store=studio_store,
        planner_control_context=_planner_control_context,
        interaction_service=interaction_service,
        settings=settings,
    )
    configure_perception(studio_store=studio_store, websocket_manager=websocket_manager, require_session=require_session)
    configure_cases(studio_store=studio_store, files_root=files_root)
    configure_prompt_chip(studio_store=studio_store)
    state_root = storage_root / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    state_snapshot_path = state_root / "latest.json"
    if "pytest" not in sys.modules:
        four_stage_store.reopen(storage_root / "four_stage.sqlite3")
        experiment_project_store.reopen(storage_root / "experiment_projects.sqlite3")
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
        create_sandbox_router(
            studio_store=studio_store,
            interaction_service=interaction_service,
            semantic_primary=semantic_primary_model,
            semantic_fallback=semantic_fallback_model,
            knowledge_router=semantic_divergence_service.knowledge_router,
            image_client=image_generation_client,
            image_model=external_model_runtime.profile.image_model,
            files_root=files_root,
            text_gateway=external_model_runtime.text_gateway,
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
    app.include_router(
        create_assets_router(
            require_session=require_session,
            studio_store=studio_store,
            files_root=files_root,
            websocket_manager=websocket_manager,
            remote_worker_adapter=remote_worker_adapter,
            autopartgen_adapter=autopartgen_adapter,
            discover_benchmark_assets=discover_benchmark_assets,
            download_oss_object=_download_oss_object,
            resolve_benchmark_texture_key=_resolve_benchmark_texture_key,
            benchmark_tree_material=_benchmark_tree_material,
            export_url_for_format=_export_url_for_format,
            read_export_artifact=_read_export_artifact,
            export_filename=_export_filename,
        )
    )
    app.include_router(
        create_actions_router(
            require_session=require_session,
            studio_store=studio_store,
            websocket_manager=websocket_manager,
            interaction_service=interaction_service,
            publish_perception=_publish_perception,
            update_session_live_signals=_update_session_live_signals,
            looks_like_prompt_chip_action=_looks_like_prompt_chip_action,
            files_root=files_root,
            find_part=find_part,
            read_lifecycle=read_lifecycle,
            interpret_and_publish=interpret_and_publish,
        )
    )
    app.include_router(
        create_sessions_router(
            require_session=require_session,
            studio_store=studio_store,
            websocket_manager=websocket_manager,
            live_signals_payload=_live_signals_payload,
            create_direction_suggestions=create_direction_suggestions,
            clear_four_stage_session=four_stage_store.clear_session,
        )
    )
    app.include_router(
        create_candidates_router(
            require_session=require_session,
            studio_store=studio_store,
            websocket_manager=websocket_manager,
            generation_orchestrator=generation_orchestrator,
            publish_perception=_publish_perception,
            interaction_service=interaction_service,
            record_candidate_memory=_record_candidate_memory,
            legacy_job_store=legacy_job_store,
            files_root=files_root,
            validate_optional_session=_validate_optional_session,
            record_candidate_rejection=_record_candidate_rejection,
            build_prompt_chip_package=_build_prompt_chip_package,
            hydrate_geometry_request=_hydrate_geometry_request,
            hydrate_render_request=_hydrate_render_request,
            next_action_after_accept=_next_action_after_accept,
            next_action_after_reject=_next_action_after_reject,
            geometry_worker=geometry_worker,
            render_preview_worker=render_preview_worker,
            interpret_and_publish=interpret_and_publish,
            create_direction_suggestions=create_direction_suggestions,
            register_worker_artifacts=_register_worker_artifacts,
            save_worker_job=_save_worker_job,
        )
    )
    app.include_router(create_system_router(enabled=settings.system_services_enabled))
    app.include_router(
        create_four_stage_router(
            orchestrator=four_stage_orchestrator,
            require_session=require_session,
            files_root=files_root,
            remote_worker_adapter=remote_worker_adapter,
            enable_3d_generation=external_model_runtime.profile.enable_3d_generation,
        )
    )
    app.include_router(
        create_realtime_observation_router(
            service=realtime_observation_service,
            require_session=require_session,
            interaction_service=interaction_orchestrator,
        )
    )
    app.include_router(
        create_interaction_router(
            service=interaction_orchestrator,
            require_session=require_session,
        )
    )
    app.include_router(
        create_projects_router(
            store=experiment_project_store,
            require_session=require_session,
            files_root=files_root,
        )
    )

    if (
        settings.system_services_auto_bootstrap
        and settings.system_services_enabled
        and "pytest" not in sys.modules
    ):

        @app.on_event("startup")
        async def _auto_bootstrap_services() -> None:
            # Start cheap infrastructure (tunnels/worker/frontend) only. GPU
            # model services are started explicitly from the UI bootstrap.
            started = await system_services.auto_bootstrap_infra()
            for item in started:
                logger.info("AUTO_BOOTSTRAP service=%s ok=%s", item.get("id"), item.get("ok"))

    if "pytest" not in sys.modules:

        @app.on_event("startup")
        async def _recover_four_stage_jobs() -> None:
            recovered = four_stage_generation_service.recover_pending_jobs()
            if recovered:
                logger.info("FOUR_STAGE_RECOVERED_JOBS count=%s", recovered)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict):
            code = str(exc.detail.get("code") or "INVALID_REQUEST")
            message = str(exc.detail.get("message") or "Request failed.")
            details = exc.detail.get("details")
            return api_error(
                code,
                message,
                exc.status_code,
                details=details if isinstance(details, dict) else {},
            )
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
            "model_runtime": {
                "configured": bool(external_model_runtime.profile.api_key),
                "api_base": external_model_runtime.profile.api_base,
                "fast_text": external_model_runtime.profile.fast_text_model,
                "reasoning_text": external_model_runtime.profile.reasoning_text_model,
                "image": external_model_runtime.profile.image_model,
                "legacy_local_models": (
                    external_model_runtime.profile.enable_legacy_local_models
                ),
                "3d_generation": external_model_runtime.profile.enable_3d_generation,
            },
            "interaction_understanding": {
                "predictor": interaction_service.predictor.name,
                "predictor_version": interaction_service.predictor.version,
                "vlm_configured": interaction_service.vlm_configured(),
                "vlm_intent_url": getattr(
                    interaction_service.predictor, "endpoint_url", None
                ),
                "planner_model": getattr(
                    interaction_service.predictor,
                    "model_name",
                    external_model_runtime.profile.fast_text_model,
                ),
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

    @app.get("/api/v1/model-api/probe")
    async def model_api_probe(include_image: bool = True) -> dict[str, object]:
        """Live ping for cloud text (+ optional image) before a study run."""
        from app.services.model_api.probe import probe_external_models

        return await probe_external_models(
            external_model_runtime,
            include_image=include_image,
        )

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
        try:
            image_path.write_bytes(_decode_data_url(request.image_data_url))
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid viewport image: {exc}") from exc
        point_x = float(request.point.get("x", 0.5))
        point_y = float(request.point.get("y", 0.5))
        try:
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
        except Exception as exc:
            logger.warning("viewport-sam worker failed: %s", exc)
            return ViewportSegmentationResponse(
                session_id=request.session_id,
                asset_id=request.asset_id,
                part_id=request.part_id,
                status="unavailable",
                result={"note": str(exc)[:240]},
                metadata={"error": str(exc)[:240]},
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
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
                if message.type == "interaction.replay":
                    cursor = int(message.payload.get("last_event_cursor") or 0)
                    for event in interaction_orchestrator.events(session_id, after_cursor=max(0, cursor)):
                        await websocket.send_json(
                            {
                                "type": "interaction.event",
                                "event_id": event.event_id,
                                "session_id": session_id,
                                "timestamp": event.occurred_at.isoformat(),
                                "payload": event.payload,
                                "event_cursor": event.event_cursor,
                                "event_type": event.event_type,
                                "revision_id": event.revision_id,
                                "aggregate_type": event.aggregate_type.value,
                                "aggregate_id": event.aggregate_id,
                                "aggregate_version": event.aggregate_version,
                                "correlation_id": event.correlation_id,
                            }
                        )
                    continue
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

create_direction_suggestions = create_direction_suggestion_builder(
    require_session=require_session,
    studio_store=studio_store,
    websocket_manager=websocket_manager,
    build_cross_domain_response=_build_cross_domain_response,
)


app = create_app()
