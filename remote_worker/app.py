from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from mimetypes import guess_type
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from variation_image_scoring import pairwise_diversity, score_candidate_image

from mesh_utils import (
    bbox_from_part,
    bbox_metrics,
    build_bbox_fit_result,
    cluster_id_from_part,
    extract_faces_obj,
    extract_labeled_region_obj,
    face_labels_path_from_part,
    merge_obj_pair,
    normalize_obj,
    obj_bbox,
    open_boundary_metrics,
    parse_npy_ints,
    remove_labeled_faces,
    transform_obj,
)

from hy3d_gpu_pool import gpu_pool
from job_orchestration import (
    PersistentJobStore,
    WorkerJob,
    _clean_log_text,
    _create_job,
    _find_result,
    _normalize_transfer_result_for_hy3d,
    _read_env_exports,
    _read_json_result,
    _run_job,
    _sanitize_for_json,
    _v1_job_response,
    find_reusable_hy3d_job,
    jobs,
    now_iso,
    processes,
)

WORKER_ROOT = Path(__file__).resolve().parent
PIPELINE_ROOT = Path(os.getenv("CF_PIPELINE_ROOT", "/root/creativeflow_pipeline"))
PYTHON_BIN = Path(os.getenv("CF_WORKER_PYTHON") or os.getenv("CF_HY3D_PYTHON") or sys.executable)
TRANSFER_SCRIPT = PIPELINE_ROOT / "pipeline_transfer_engine.py"
TRANSFER_MINIMAL_SCRIPT = PIPELINE_ROOT / "pipeline_transfer_engine_minimal.py"
ORIGINAL_PIPELINE_SCRIPT = PIPELINE_ROOT / "pipeline.py"
HY3D_SCRIPT = PIPELINE_ROOT / "pipeline_hunyuan3d_post.py"
MESH_WORKER_SCRIPT = PIPELINE_ROOT / "step4_mesh_worker_mv.py"
_MV_MODEL_PATH = Path("/root/autodl-tmp/models/Hunyuan3D-2mv")


def _hy3d_subprocess_env(device: str | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.update(_read_env_exports(Path("/root/.oss_env")))
    env.setdefault("CF_HY3D_PYTHON", str(PYTHON_BIN))
    env.setdefault("HY21_ROOT", "/root/Hunyuan3D-2.1")
    env.setdefault("HY21_MODEL_ROOT", "/root/models")
    env.setdefault("CUDA_HOME", "/usr/local/cuda-12.4")
    env["PYTHONUNBUFFERED"] = "1"
    if device is not None:
        env["CUDA_VISIBLE_DEVICES"] = device
    if not _MV_MODEL_PATH.exists():
        env.setdefault("CF_ENABLE_MULTIVIEW", "0")
    return env


RUN_ROOT = Path(os.getenv("FLOWSTUDIO_WORKER_RUN_ROOT", "/root/autodl-tmp/flowstudio_worker_runs"))
ASSET_ROOT = Path(os.getenv("FLOWSTUDIO_WORKER_ASSET_ROOT", "/root/autodl-tmp/flowstudio_worker_assets"))
BENCHMARK_INPUT_ROOT = Path(
    os.getenv("FLOWSTUDIO_BENCHMARK_INPUT_ROOT", str(PIPELINE_ROOT / "benchmark_inputs"))
)
OSS_PREFIX_ROOT = os.getenv("FLOWSTUDIO_OSS_PREFIX_ROOT", "creativeflow/flowstudio")
QWEN_IMAGE_URL = os.getenv("CF_QWEN_IMAGE_URL", "").strip()
QWEN_CONDITIONED_URL = os.getenv("CF_QWEN_CONDITIONED_URL", "").strip()
PLANNER_API_BASE = os.getenv("CF_PLANNER_API_BASE", "").rstrip("/")
LEGACY_PLANNER_API_BASE = os.getenv("CF_LEGACY_PLANNER_API_BASE", "").rstrip("/")
MODEL_PHASE_SCRIPT = Path(
    os.getenv("CF_MODEL_PHASE_SCRIPT", str(WORKER_ROOT / "model_phase.sh"))
)
async def _run_hy3d_job(job_id: str, cmd: list[str], env: dict[str, str], expected_result_name: str) -> None:
    job = jobs.get(job_id)
    if job is not None:
        job.message = "排队等待 GPU"
        job.updated_at = now_iso()
        jobs[job_id] = job
    device = await gpu_pool().acquire()
    try:
        bound = dict(env)
        bound["CUDA_VISIBLE_DEVICES"] = device
        if job is not None:
            job.message = f"已提交 Hunyuan3D · GPU {device}"
            job.updated_at = now_iso()
            jobs[job_id] = job
        await _run_job(job_id, cmd, bound, expected_result_name)
    finally:
        gpu_pool().release(device)
PROMPT_LIBRARY_PATH = Path(
    os.getenv("CF_PROMPT_LIBRARY_PATH", str(WORKER_ROOT / "prompt_library.json"))
)
VARIATION_DIRECTION_SCRIPT = Path(
    os.getenv("CF_VARIATION_DIRECTION_SCRIPT", str(WORKER_ROOT / "variation_graph_directions.py"))
)
AUTOPARTGEN_ROOT = Path(os.getenv("AUTOPARTGEN_ROOT", "/root/autodl-tmp/AutoPartGen"))
AUTOPARTGEN_PYTHON = Path(
    os.getenv("AUTOPARTGEN_PYTHON", "/root/autodl-tmp/venvs/autopartgen/bin/python")
)
PARTFIELD_ROOT = Path(os.getenv("PARTFIELD_ROOT", "/root/autodl-tmp/PartField"))
PARTFIELD_PYTHON = Path(
    os.getenv("PARTFIELD_PYTHON", "/root/autodl-tmp/venvs/partfield/bin/python")
)
PARTFIELD_SETUP_LOG = Path(
    os.getenv("PARTFIELD_SETUP_LOG", "/root/flowstudio_remote_worker/setup_partfield_env.log")
)
PARTFIELD_MODEL = PARTFIELD_ROOT / "model" / "model_objaverse.ckpt"
SAM3D_ROOT = Path(os.getenv("SAM3D_ROOT", "/root/SAMPart3D"))
SAM3D_PYTHON = Path(
    os.getenv("SAM3D_PYTHON", "/root/autodl-tmp/data/flowstudio/envs/sam3d/bin/python")
)



def _run_model_phase_sync(phase_name: str, timeout: int = 480) -> str:
    """Switch mutually-exclusive GPU model residency.

    The single-GPU deployment cannot keep a large local planner and Qwen-image
    generation hot at the same time. This helper keeps the worker API stable
    while model_phase.sh handles the actual process/memory transition.
    """
    if not MODEL_PHASE_SCRIPT.is_file():
        return "model phase script missing; skipped"
    completed = subprocess.run(
        [str(MODEL_PHASE_SCRIPT), phase_name],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = "\n".join(part for part in [completed.stdout, completed.stderr] if part).strip()
    if completed.returncode != 0:
        raise RuntimeError(f"{phase_name} model phase failed: {output[-2000:]}")
    return output[-2000:]


async def _restore_planner_phase_after_generation() -> None:
    try:
        await asyncio.to_thread(_run_model_phase_sync, "planner", 480)
    except Exception as exc:
        # Do not flip a completed image job back to failed just because planner
        # warm-up is slow; surface it in logs for /jobs and server logs instead.
        print(f"[flowstudio] planner phase restore failed after generation: {exc}", flush=True)
SAM3D_MODEL = Path(
    os.getenv("SAM3D_MODEL", "/root/autodl-tmp/data/flowstudio/sam3d/checkpoints")
)
SAM3D_READY_SENTINEL = Path(os.getenv("SAM3D_READY_SENTINEL", str(SAM3D_MODEL / ".flowstudio_ready")))
BLENDER_BIN = Path(os.getenv("BLENDER_BIN", "/root/autodl-tmp/blender/blender-5.0.0-linux-x64/blender"))


class TransferJobRequest(BaseModel):
    flowstudio_job_id: str
    request: dict[str, Any]
    max_direction_paths: int | None = None
    candidates_per_rationale: int | None = None
    transfer_variant: str = "minimal"
    dry_run: bool = False


class CreativeFlowPartJobRequest(BaseModel):
    flowstudio_job_id: str
    request: dict[str, Any]
    stage: str = "part"
    fidelity: str = "medium"
    target_part: dict[str, Any] = Field(default_factory=dict)
    source_image_path: str | None = None
    source_mesh_path: str | None = None
    source_multiview_paths: list[str] = Field(default_factory=list)
    source_elements_path: str | None = None
    brush_mask_path: str | None = None
    sam3d_manifest_path: str | None = None
    part_semantics_path: str | None = None
    sam3d_projection_mask_path: str | None = None
    socket_constraints: dict[str, Any] = Field(default_factory=dict)
    divergence_axes: list[str] = Field(default_factory=list)
    candidate_count: int = 4
    kg_options: dict[str, Any] = Field(default_factory=dict)
    image_options: dict[str, Any] = Field(default_factory=dict)
    mesh_options: dict[str, Any] = Field(default_factory=dict)
    analogy_prompt_package: dict[str, Any] = Field(default_factory=dict)
    run_hy3d: bool | None = None
    dry_run: bool = True


class ViewportSamJobRequest(BaseModel):
    flowstudio_job_id: str
    image_path: str
    point_x: float
    point_y: float
    session_id: str = ""
    asset_id: str | None = None
    part_id: str | None = None
    label: str | None = None
    output_dir: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class VariationKGOptions(BaseModel):
    """Knowledge-graph controls that are wired to the Stage 1 implementation."""

    top_k: int = Field(default=4, ge=1, le=32)
    candidate_pool_size: int = Field(default=12, ge=1, le=64)
    scoring_enabled: bool = True
    generate_all_retrieved: bool = False
    cache_mode: str = Field(default="cache_first", pattern="^(cache_first|network_first|cache_only)$")
    request_timeout_sec: int = Field(default=8, ge=1, le=60)


class VariationImageOptions(BaseModel):
    width: int = Field(default=768, ge=256, le=1536)
    height: int = Field(default=768, ge=256, le=1536)
    steps: int = Field(default=20, ge=1, le=80)
    seed: int = Field(default=42, ge=0, le=2_147_483_647)
    source_strength: float | None = Field(default=None, ge=0.0, le=1.0)
    attempts_per_candidate: int = Field(default=3, ge=1, le=5)
    require_white_background: bool = True


class VariationMeshOptions(BaseModel):
    enabled: bool = True
    max_candidates: int = Field(default=4, ge=1, le=16)


class VariationSourceAssets(BaseModel):
    image_asset_id: str
    mesh_asset_id: str | None = None
    multiview_asset_ids: list[str] = Field(default_factory=list)
    source_elements_asset_id: str | None = None
    brush_mask_asset_id: str | None = None
    sam3d_manifest_asset_id: str | None = None
    part_semantics_asset_id: str | None = None
    sam3d_projection_mask_asset_id: str | None = None


class VariationJobV1Request(BaseModel):
    client_job_id: str
    variation: str = Field(pattern="^(low_fidelity|part|texture)$")
    object_type: str = Field(min_length=1, max_length=120)
    source: VariationSourceAssets
    prompt: str | None = None
    fidelity: str = Field(default="medium", pattern="^(low|medium|high)$")
    target_part: dict[str, Any] = Field(default_factory=dict)
    socket_constraints: dict[str, Any] = Field(default_factory=dict)
    divergence_axes: list[str] = Field(default_factory=list)
    kg: VariationKGOptions = Field(default_factory=VariationKGOptions)
    image: VariationImageOptions = Field(default_factory=VariationImageOptions)
    mesh: VariationMeshOptions = Field(default_factory=VariationMeshOptions)
    dry_run: bool = False


VARIATION_ALIASES = {
    "original": "original",
    "silhouette": "low_fidelity",
    "global": "low_fidelity",
    "low_fidelity": "low_fidelity",
    "low-fidelity": "low_fidelity",
    "detail": "part",
    "part": "part",
    "rough_form": "part",
    "form": "part",
    "texture": "texture",
}


def _canonical_variation(stage: str) -> str:
    return VARIATION_ALIASES.get(stage.strip().lower(), "part")


def _prompt_library() -> dict[str, Any]:
    try:
        payload = json.loads(PROMPT_LIBRARY_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _request_object_type(request: dict[str, Any]) -> str:
    direct = request.get("object_type")
    if direct:
        return str(direct).strip().lower()
    asset = request.get("asset")
    if isinstance(asset, dict) and asset.get("object_type"):
        return str(asset["object_type"]).strip().lower()
    return ""


def _library_variation(request: dict[str, Any], stage: str) -> dict[str, Any]:
    object_type = _request_object_type(request)
    objects = _prompt_library().get("objects", {})
    entry = objects.get(object_type, {}) if isinstance(objects, dict) else {}
    variations = entry.get("variations", {}) if isinstance(entry, dict) else {}
    value = variations.get(_canonical_variation(stage), {}) if isinstance(variations, dict) else {}
    return value if isinstance(value, dict) else {}


class Hy3DJobRequest(BaseModel):
    flowstudio_job_id: str
    transfer_result_path: str
    candidate_ids: list[str] = Field(default_factory=list)
    max_candidates: int = 0
    output_format: str = "glb"
    dry_run: bool = False


class Hy3DFromStagedJobRequest(BaseModel):
    flowstudio_job_id: str
    staged_result_path: str
    direction_ids: list[str] = Field(default_factory=list)
    max_candidates: int = 1
    output_format: str = "glb"
    dry_run: bool = False


class AutoPartGenJobRequest(BaseModel):
    flowstudio_job_id: str
    mode: str = "mesh"
    mesh_path: str | None = None
    image_path: str | None = None
    mask_path: str | None = None
    output_dir: str | None = None
    grid_size: int = 256
    seed: int = 42
    remove_background: bool = False
    dry_run: bool = True


class PartFieldJobRequest(BaseModel):
    flowstudio_job_id: str
    mesh_path: str
    granularity: str = "medium"
    max_parts: int = 16
    brush_mask_path: str | None = None
    output_dir: str | None = None
    dry_run: bool = True


class Sam3DJobRequest(BaseModel):
    flowstudio_job_id: str
    mesh_path: str
    granularity: str = "medium"
    max_parts: int = 16
    brush_mask_path: str | None = None
    output_dir: str | None = None
    epochs: int | None = None
    sample_num: int | None = None
    pixels_per_image: int | None = None
    mask_batch_size: int | None = None
    dry_run: bool = True


class GeometryJobRequest(BaseModel):
    flowstudio_job_id: str = "geometry"
    source_mesh_path: str | None = None
    candidate_mesh_path: str | None = None
    part: dict[str, Any] | None = None
    face_indices: list[int] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)


class GeometryJobResponse(BaseModel):
    ok: bool
    job_id: str
    flowstudio_job_id: str
    status: str
    operation: str
    result_mesh_path: str | None = None
    preview_mesh_path: str | None = None
    result_mesh_url: str | None = None
    preview_mesh_url: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class RenderJobRequest(BaseModel):
    flowstudio_job_id: str = "render"
    source_mesh_path: str | None = None
    source_mesh_url: str | None = None
    mesh_url: str | None = None
    candidate_mesh_path: str | None = None
    candidate_mesh_url: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class RenderJobResponse(BaseModel):
    ok: bool
    job_id: str
    flowstudio_job_id: str
    status: str
    operation: str
    thumbnail_path: str | None = None
    thumbnail_url: str | None = None
    views: dict[str, str] = Field(default_factory=dict)
    view_paths: dict[str, str] = Field(default_factory=dict)
    turntable_video_path: str | None = None
    turntable_video_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


app = FastAPI(
    title="FlowStudio Remote CreativeFlow Worker",
    version="1.0.0",
    description="Asynchronous CreativeFlow generation API for Low Fidelity, Part and Texture variations.",
)
_cors_origins = [
    origin.strip()
    for origin in os.getenv("CF_API_CORS_ORIGINS", "").split(",")
    if origin.strip()
]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-CreativeFlow-Key"],
    )


def _require_v1_api_key(
    x_creativeflow_key: str | None = Header(default=None),
) -> None:
    expected = os.getenv("CF_API_KEY", "").strip()
    if expected and x_creativeflow_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing X-CreativeFlow-Key")


def _asset_path(asset_id: str | None, label: str, *, required: bool = False) -> str | None:
    if not asset_id:
        if required:
            raise HTTPException(status_code=400, detail=f"{label} asset_id is required")
        return None
    if not re.fullmatch(r"rasset_[a-f0-9]{10}", asset_id):
        raise HTTPException(status_code=400, detail=f"Invalid {label} asset_id")
    asset_dir = (ASSET_ROOT / asset_id).resolve()
    root = ASSET_ROOT.resolve()
    if root not in asset_dir.parents or not asset_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"{label} asset not found")
    files = [path for path in asset_dir.iterdir() if path.is_file()]
    if len(files) != 1:
        raise HTTPException(status_code=409, detail=f"{label} asset is incomplete or ambiguous")
    return str(files[0])


def _artifact_url(path: str | None) -> str | None:
    if not path:
        return None
    return "/api/v1/artifact-file?" + urllib.parse.urlencode({"path": path})


@app.get("/health")
def health() -> dict[str, Any]:
    partfield_setup = _partfield_setup_state()
    creativeflow_pipeline = _creativeflow_pipeline_state()
    return {
        "ok": True,
        "pipeline_root": str(PIPELINE_ROOT),
        "python_bin": str(PYTHON_BIN),
        "python_bin_exists": PYTHON_BIN.exists(),
        "original_pipeline_exists": ORIGINAL_PIPELINE_SCRIPT.exists(),
        "transfer_script_exists": TRANSFER_SCRIPT.exists(),
        "transfer_minimal_script_exists": TRANSFER_MINIMAL_SCRIPT.exists(),
        "hy3d_script_exists": HY3D_SCRIPT.exists(),
        "mesh_worker_exists": MESH_WORKER_SCRIPT.exists(),
        "creativeflow_pipeline": creativeflow_pipeline,
        "autopartgen_root": str(AUTOPARTGEN_ROOT),
        "autopartgen_root_exists": AUTOPARTGEN_ROOT.exists(),
        "autopartgen_python": str(AUTOPARTGEN_PYTHON),
        "autopartgen_python_exists": AUTOPARTGEN_PYTHON.exists(),
        "autopartgen_dit_checkpoint_exists": (
            AUTOPARTGEN_ROOT / "checkpoints" / "autopartgen_dit.pth"
        ).exists(),
        "autopartgen_vae_checkpoint_exists": (
            AUTOPARTGEN_ROOT / "checkpoints" / "autopartgen_vae.pth"
        ).exists(),
        "partfield_root": str(PARTFIELD_ROOT),
        "partfield_root_exists": PARTFIELD_ROOT.exists(),
        "partfield_python": str(PARTFIELD_PYTHON),
        "partfield_python_exists": PARTFIELD_PYTHON.exists(),
        "partfield_model": str(PARTFIELD_MODEL),
        "partfield_model_exists": PARTFIELD_MODEL.exists(),
        "partfield_model_size": PARTFIELD_MODEL.stat().st_size if PARTFIELD_MODEL.exists() else 0,
        "partfield_model_ready": PARTFIELD_MODEL.exists() and PARTFIELD_MODEL.stat().st_size > 0,
        "partfield_worker_script_exists": (WORKER_ROOT / "flowstudio_partfield_worker.py").exists(),
        "sam3d_root": str(SAM3D_ROOT),
        "sam3d_root_exists": SAM3D_ROOT.exists(),
        "sam3d_python": str(SAM3D_PYTHON),
        "sam3d_python_exists": SAM3D_PYTHON.exists(),
        "sam3d_model": str(SAM3D_MODEL),
        "sam3d_model_exists": SAM3D_MODEL.exists(),
        "sam3d_checkpoint_exists": _sam3d_checkpoint_exists(),
        "viewport_sam_ready": (
            SAM3D_PYTHON.exists()
            and (SAM3D_MODEL / "sam_vit_h_4b8939.pth").exists()
            and (WORKER_ROOT / "flowstudio_viewport_sam_worker.py").exists()
        ),
        "sam3d_ready_sentinel": str(SAM3D_READY_SENTINEL),
        "sam3d_ready_sentinel_exists": SAM3D_READY_SENTINEL.exists(),
        "sam3d_worker_script_exists": (WORKER_ROOT / "flowstudio_sam3d_worker.py").exists(),
        "sam3d_ready": _sam3d_ready(),
        "segmentation_adapter": "sam3d",
        "segmentation_worker_ready": _sam3d_ready(),
        "geometry_worker_ready": (WORKER_ROOT / "mesh_utils.py").exists(),
        "geometry_endpoints": [
            "/geometry/normalize",
            "/geometry/bbox",
            "/geometry/extract-region",
            "/geometry/extract-faces",
            "/geometry/attachment-boundary",
            "/geometry/deform-preview",
            "/geometry/fit-candidate",
            "/geometry/seam-blend",
            "/geometry/cleanup",
            "/geometry/convert",
        ],
        "blender_bin": str(BLENDER_BIN),
        "blender_exists": BLENDER_BIN.exists(),
        "render_preview_ready": BLENDER_BIN.exists(),
        "render_endpoints": [
            "/render/thumbnail",
            "/render/multiview",
            "/render/turntable",
            "/render/before-after",
            "/render/mask-visualization",
            "/render/candidate-card",
            "/render/part-preview",
        ],
        "partfield_setup_running": partfield_setup["running"],
        "partfield_setup_processes": partfield_setup["processes"],
        "partfield_setup_log_path": str(PARTFIELD_SETUP_LOG),
        "partfield_setup_log_tail": partfield_setup["log_tail"],
        "run_root": str(RUN_ROOT),
        "asset_root": str(ASSET_ROOT),
        "jobs": len(jobs),
    }


@app.get("/preflight/creativeflow")
def creativeflow_preflight() -> dict[str, Any]:
    return _creativeflow_preflight_state()


@app.post("/geometry/{operation}")
def run_geometry_operation(operation: str, req: GeometryJobRequest) -> GeometryJobResponse:
    job_id = f"rw_geom_{operation.replace('-', '_')}_{uuid4().hex[:10]}"
    work_dir = RUN_ROOT / job_id / "geometry"
    work_dir.mkdir(parents=True, exist_ok=True)
    started_at = now_iso()
    try:
        result = _run_geometry_operation(operation.replace("_", "-"), req, work_dir)
        response = GeometryJobResponse(
            ok=True,
            job_id=job_id,
            flowstudio_job_id=req.flowstudio_job_id,
            status="completed",
            operation=operation.replace("_", "-"),
            created_at=started_at,
            updated_at=now_iso(),
            **result,
        )
    except Exception as exc:
        response = GeometryJobResponse(
            ok=False,
            job_id=job_id,
            flowstudio_job_id=req.flowstudio_job_id,
            status="failed",
            operation=operation.replace("_", "-"),
            error=str(exc),
            created_at=started_at,
            updated_at=now_iso(),
        )
    jobs[job_id] = WorkerJob(
        job_id=job_id,
        flowstudio_job_id=req.flowstudio_job_id,
        kind="geometry",
        status=response.status,
        stage=response.operation,
        progress=1.0,
        message="Geometry operation completed" if response.ok else "Geometry operation failed",
        request=req.model_dump(mode="json"),
        result=response.model_dump(mode="json"),
        error=response.error,
        work_dir=str(work_dir),
        created_at=response.created_at,
        updated_at=response.updated_at,
    )
    return response


@app.get("/geometry/jobs/{job_id}")
def get_geometry_job(job_id: str) -> GeometryJobResponse:
    job = jobs.get(job_id)
    if job is None or job.kind != "geometry":
        raise HTTPException(status_code=404, detail=f"Geometry job not found: {job_id}")
    return GeometryJobResponse(**job.result)


@app.post("/render/{operation}")
def run_render_operation(operation: str, req: RenderJobRequest) -> RenderJobResponse:
    job_id = f"rw_render_{operation.replace('-', '_')}_{uuid4().hex[:10]}"
    work_dir = RUN_ROOT / job_id / "render"
    work_dir.mkdir(parents=True, exist_ok=True)
    started_at = now_iso()
    try:
        result = _run_render_operation(operation.replace("_", "-"), req, work_dir)
        response = RenderJobResponse(
            ok=True,
            job_id=job_id,
            flowstudio_job_id=req.flowstudio_job_id,
            status="completed",
            operation=operation.replace("_", "-"),
            created_at=started_at,
            updated_at=now_iso(),
            **result,
        )
    except Exception as exc:
        response = RenderJobResponse(
            ok=False,
            job_id=job_id,
            flowstudio_job_id=req.flowstudio_job_id,
            status="failed",
            operation=operation.replace("_", "-"),
            error=str(exc),
            created_at=started_at,
            updated_at=now_iso(),
            metadata={"engine": "blender", "blender_bin": str(BLENDER_BIN)},
        )
    jobs[job_id] = WorkerJob(
        job_id=job_id,
        flowstudio_job_id=req.flowstudio_job_id,
        kind="render",
        status=response.status,
        stage=response.operation,
        progress=1.0,
        message="Render operation completed" if response.ok else "Render operation failed",
        request=req.model_dump(mode="json"),
        result=response.model_dump(mode="json"),
        error=response.error,
        work_dir=str(work_dir),
        created_at=response.created_at,
        updated_at=response.updated_at,
    )
    return response


@app.get("/render/jobs/{job_id}")
def get_render_job(job_id: str) -> RenderJobResponse:
    job = jobs.get(job_id)
    if job is None or job.kind != "render":
        raise HTTPException(status_code=404, detail=f"Render job not found: {job_id}")
    return RenderJobResponse(**job.result)


def _run_geometry_operation(
    operation: str,
    req: GeometryJobRequest,
    work_dir: Path,
) -> dict[str, Any]:
    if operation == "normalize":
        data = _read_geometry_mesh(req.source_mesh_path)
        obj_text, metrics = normalize_obj(data)
        path = _write_geometry_text(work_dir, "normalized.obj", obj_text)
        return _geometry_mesh_result(path, metrics)

    if operation == "bbox":
        data = _read_geometry_mesh(req.source_mesh_path)
        return {"metrics": bbox_metrics(data)}

    if operation in {"extract-region", "attachment-boundary"}:
        data = _read_geometry_mesh(req.source_mesh_path)
        labels = _read_geometry_labels(req)
        cluster_id = cluster_id_from_part(req.part)
        if cluster_id is None:
            raise ValueError("part metadata must include source_part_id or cluster_id")
        obj_text, metrics = extract_labeled_region_obj(data, labels, cluster_id)
        path = _write_geometry_text(work_dir, "selected_region.obj", obj_text)
        artifacts: dict[str, Any] = {"selected_region": _geometry_artifact(path)}
        if operation == "attachment-boundary":
            artifacts["attachment_boundary"] = {
                "boundary_edge_count": metrics.get("boundary_edge_count"),
                "boundary_centroid": metrics.get("boundary_centroid"),
            }
        return _geometry_mesh_result(path, metrics, artifacts)

    if operation == "extract-faces":
        data = _read_geometry_mesh(req.source_mesh_path)
        if not req.face_indices:
            raise ValueError("face_indices is required for extract-faces")
        obj_text, metrics = extract_faces_obj(data, set(req.face_indices))
        path = _write_geometry_text(work_dir, "selected_faces.obj", obj_text)
        return _geometry_mesh_result(path, metrics, {"selected_faces": _geometry_artifact(path)})

    if operation == "deform-preview":
        data = _read_geometry_mesh(req.source_mesh_path)
        transform = req.options.get("transform") or {
            "scale": req.options.get("scale", 1.0),
            "translation": req.options.get("translation", [0.0, 0.0, 0.0]),
        }
        obj_text = transform_obj(data, transform)
        path = _write_geometry_text(work_dir, "deform_preview.obj", obj_text)
        metrics = {"transform": transform, **bbox_metrics(obj_text.encode("utf-8"))}
        return _geometry_mesh_result(path, metrics)

    if operation == "fit-candidate":
        candidate = _read_geometry_mesh(req.candidate_mesh_path)
        target_bbox = req.options.get("target_bbox") or bbox_from_part(req.part)
        if not isinstance(target_bbox, dict):
            raise ValueError("target bbox is required via part.metadata.bbox3d or options.target_bbox")
        policy = str(req.options.get("fit_policy") or req.options.get("policy") or "bbox_uniform")
        fit = build_bbox_fit_result(
            obj_bbox(candidate),
            target_bbox,
            policy,
            target_part_id=(req.part or {}).get("part_id") if isinstance(req.part, dict) else None,
        )
        obj_text = transform_obj(candidate, fit["transform"])
        metrics = {**fit, "replacement_boundary": open_boundary_metrics(obj_text)}
        path = _write_geometry_text(work_dir, "fitted.obj", obj_text)
        return _geometry_mesh_result(path, metrics, {"fitted_mesh": _geometry_artifact(path)})

    if operation == "seam-blend":
        source = _read_geometry_mesh(req.source_mesh_path)
        candidate = _read_geometry_mesh(req.candidate_mesh_path)
        cluster_id = cluster_id_from_part(req.part)
        metrics: dict[str, Any] = {"replacement_mode": "assembly_overlay"}
        note = "overlay; source part was not removed"
        if cluster_id is not None:
            try:
                source, removal = remove_labeled_faces(source, _read_geometry_labels(req), cluster_id)
                metrics = {**metrics, **removal, "replacement_mode": "cluster_removed_assembly"}
                note = "target PartField cluster faces removed before fitted candidate insertion"
            except Exception as exc:
                metrics["label_removal_error"] = str(exc)
        obj_text = merge_obj_pair(source, candidate, note)
        path = _write_geometry_text(work_dir, "seam_preview.obj", obj_text)
        return _geometry_mesh_result(path, metrics, {"seam_preview": _geometry_artifact(path)})

    if operation == "cleanup":
        data = _read_geometry_mesh(req.source_mesh_path)
        text = data.decode("utf-8", errors="ignore")
        cleaned = "\n".join(line.rstrip() for line in text.splitlines() if line.strip()) + "\n"
        path = _write_geometry_text(work_dir, "cleaned.obj", cleaned)
        return _geometry_mesh_result(path, {"cleanup": "trimmed_blank_lines", **bbox_metrics(cleaned.encode("utf-8"))})

    if operation == "convert":
        data = _read_geometry_mesh(req.source_mesh_path)
        output_format = str(req.options.get("output_format") or "obj").lower().lstrip(".")
        if output_format != "obj":
            raise ValueError("MVP format conversion currently supports OBJ output only")
        path = _write_geometry_bytes(work_dir, "converted.obj", data)
        return _geometry_mesh_result(path, {"output_format": "obj", **bbox_metrics(data)})

    raise ValueError(f"Unsupported geometry operation: {operation}")


def _read_geometry_mesh(path: str | None) -> bytes:
    if not path:
        raise ValueError("mesh path is required")
    return _read_allowed_worker_file(path)


def _read_geometry_labels(req: GeometryJobRequest) -> list[int]:
    labels_path = req.options.get("face_labels_path") or face_labels_path_from_part(req.part)
    if not labels_path:
        raise ValueError("face_labels_path is required for this geometry operation")
    return parse_npy_ints(_read_allowed_worker_file(str(labels_path)))


def _worker_allowed_roots() -> list[Path]:
    extra_roots = [
        Path(os.getenv("FLOWSTUDIO_EXTRA_ARTIFACT_ROOT", "/root/autodl-tmp/creativeflow_variations_20260716")),
        Path("/root/autodl-tmp/creativeflow_variations_20260718"),
        Path("/root/autodl-tmp/data/flowstudio"),
    ]
    return [
        RUN_ROOT.resolve(),
        ASSET_ROOT.resolve(),
        BENCHMARK_INPUT_ROOT.resolve(),
        *(root.resolve() for root in extra_roots),
    ]


def _read_allowed_worker_file(path: str) -> bytes:
    requested = Path(path).resolve()
    allowed_roots = _worker_allowed_roots()
    if not any(requested == root or root in requested.parents for root in allowed_roots):
        raise ValueError(f"Path is outside allowed worker roots: {requested}")
    if not requested.exists() or not requested.is_file():
        raise ValueError(f"Geometry file is not readable: {requested}")
    return requested.read_bytes()


def _sam3d_checkpoint_exists() -> bool:
    if SAM3D_MODEL.is_file() and SAM3D_MODEL.stat().st_size > 0:
        return True
    if SAM3D_MODEL.is_dir():
        return any(path.is_file() and path.stat().st_size > 0 for path in SAM3D_MODEL.glob("*.pth"))
    root_ckpt = SAM3D_ROOT / "ckpt" / "ptv3-object.pth"
    return root_ckpt.exists() and root_ckpt.stat().st_size > 0


def _sam3d_ready() -> bool:
    return (
        SAM3D_ROOT.exists()
        and SAM3D_PYTHON.exists()
        and (WORKER_ROOT / "flowstudio_sam3d_worker.py").exists()
        and _sam3d_checkpoint_exists()
        and SAM3D_READY_SENTINEL.exists()
    )


def _write_geometry_text(work_dir: Path, name: str, text: str) -> Path:
    target = work_dir / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def _write_geometry_bytes(work_dir: Path, name: str, data: bytes) -> Path:
    target = work_dir / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def _geometry_artifact(path: Path) -> dict[str, str]:
    return {
        "path": str(path),
        "url": f"/artifact-file?path={urllib.parse.quote(str(path))}",
    }


def _geometry_mesh_result(
    path: Path,
    metrics: dict[str, Any],
    artifacts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifact = _geometry_artifact(path)
    return {
        "result_mesh_path": str(path),
        "preview_mesh_path": str(path),
        "result_mesh_url": artifact["url"],
        "preview_mesh_url": artifact["url"],
        "metrics": metrics,
        "artifacts": artifacts or {"result_mesh": artifact},
    }


def _run_render_operation(operation: str, req: RenderJobRequest, work_dir: Path) -> dict[str, Any]:
    if not BLENDER_BIN.exists():
        raise RuntimeError(f"Blender executable is not available: {BLENDER_BIN}")
    source = _resolve_render_mesh(
        req.source_mesh_path,
        req.source_mesh_url or req.mesh_url or _string_option(req.options, "source_mesh_url", "mesh_url"),
        work_dir,
        "source mesh",
    )
    candidate_url = req.candidate_mesh_url or _string_option(req.options, "candidate_mesh_url")
    candidate = (
        _resolve_render_mesh(req.candidate_mesh_path, candidate_url, work_dir, "candidate mesh")
        if req.candidate_mesh_path or candidate_url
        else None
    )

    if operation == "thumbnail":
        image = _render_mesh(source, work_dir, "thumb.png", view="three_quarter")
        url = _artifact_url(image)
        return {
            "thumbnail_path": str(image),
            "thumbnail_url": url,
            "views": {"three_quarter": url},
            "view_paths": {"three_quarter": str(image)},
            "metadata": _render_metadata(operation),
            "artifacts": {"thumbnail": _render_artifact(image)},
        }

    if operation in {"multiview", "part-preview", "mask-visualization", "candidate-card"}:
        views: dict[str, str] = {}
        view_paths: dict[str, str] = {}
        artifacts: dict[str, Any] = {}
        for view, filename in {
            "front": "front.png",
            "side": "side.png",
            "three_quarter": "three_quarter.png",
        }.items():
            image = _render_mesh(source, work_dir, filename, view=view)
            views[view] = _artifact_url(image)
            view_paths[view] = str(image)
            artifacts[view] = _render_artifact(image)
        return {
            "thumbnail_path": view_paths["three_quarter"],
            "thumbnail_url": views["three_quarter"],
            "views": views,
            "view_paths": view_paths,
            "metadata": _render_metadata(operation),
            "artifacts": artifacts,
        }

    if operation == "before-after":
        if candidate is None:
            raise ValueError("candidate_mesh_path is required for before-after render")
        before = _render_mesh(source, work_dir, "before.png", view="three_quarter")
        after = _render_mesh(candidate, work_dir, "after.png", view="three_quarter")
        return {
            "thumbnail_path": str(after),
            "thumbnail_url": _artifact_url(after),
            "views": {"before": _artifact_url(before), "after": _artifact_url(after)},
            "view_paths": {"before": str(before), "after": str(after)},
            "metadata": _render_metadata(operation),
            "artifacts": {"before": _render_artifact(before), "after": _render_artifact(after)},
        }

    if operation == "turntable":
        views: dict[str, str] = {}
        view_paths: dict[str, str] = {}
        for view, filename in {
            "front": "turntable_000.png",
            "side": "turntable_090.png",
            "back": "turntable_180.png",
            "three_quarter": "turntable_315.png",
        }.items():
            image = _render_mesh(source, work_dir, filename, view=view)
            views[view] = _artifact_url(image)
            view_paths[view] = str(image)
        return {
            "thumbnail_path": view_paths["three_quarter"],
            "thumbnail_url": views["three_quarter"],
            "views": views,
            "view_paths": view_paths,
            "metadata": _render_metadata(operation),
            "artifacts": {key: _render_artifact(Path(path)) for key, path in view_paths.items()},
        }

    raise ValueError(f"Unsupported render operation: {operation}")


def _readable_worker_path(path: str | None, label: str) -> Path:
    if not path:
        raise ValueError(f"{label} path is required")
    requested = Path(path).resolve()
    allowed_roots = _worker_allowed_roots()
    if not any(requested == root or root in requested.parents for root in allowed_roots):
        raise ValueError(f"{label} is outside allowed worker roots: {requested}")
    if not requested.exists() or not requested.is_file():
        raise ValueError(f"{label} is not readable: {requested}")
    return requested


def _resolve_render_mesh(path: str | None, url: str | None, work_dir: Path, label: str) -> Path:
    if path:
        return _readable_worker_path(path, label)
    if url:
        return _download_render_mesh(url, work_dir, label)
    raise ValueError(f"{label} path or URL is required")


def _string_option(options: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = options.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _download_render_mesh(url: str, work_dir: Path, label: str) -> Path:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{label} URL must be an absolute HTTP(S) URL")
    suffix = Path(parsed.path).suffix.lower()
    if suffix not in {".obj", ".glb", ".gltf"}:
        suffix = ".glb"
    target = work_dir / f"{label.replace(' ', '_')}{suffix}"
    request = urllib.request.Request(url, headers={"User-Agent": "FlowStudio-RemoteWorker/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            target.write_bytes(response.read())
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to download {label} URL: {exc}") from exc
    if not target.exists() or target.stat().st_size == 0:
        raise RuntimeError(f"Downloaded {label} URL is empty")
    return target


def _render_mesh(mesh_path: Path, work_dir: Path, filename: str, view: str) -> Path:
    output = work_dir / filename
    output.parent.mkdir(parents=True, exist_ok=True)
    script = output.parent / f"render_{filename}.py"
    script.write_text(_blender_render_script(mesh_path, output, view), encoding="utf-8")
    completed = subprocess.run(
        [str(BLENDER_BIN), "--background", "--python", str(script)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=180,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Blender render failed: " + (completed.stderr.strip() or completed.stdout.strip())[-1400:]
        )
    if not output.exists() or output.stat().st_size == 0:
        raise RuntimeError("Blender render did not create a non-empty output image")
    return output


def _artifact_url(path: Path) -> str:
    return f"/artifact-file?path={urllib.parse.quote(str(path))}"


def _render_artifact(path: Path) -> dict[str, Any]:
    return {"path": str(path), "url": _artifact_url(path), "size_bytes": path.stat().st_size if path.exists() else 0}


def _render_metadata(operation: str) -> dict[str, Any]:
    return {
        "engine": "blender",
        "blender_bin": str(BLENDER_BIN),
        "operation": operation,
        "camera_preset": "auto_object_fit",
        "lighting_preset": "studio_soft",
        "resolution": [512, 512],
    }


def _blender_render_script(mesh_path: Path, output_path: Path, view: str) -> str:
    config = {"mesh_path": str(mesh_path), "output_path": str(output_path), "view": view}
    return textwrap.dedent(
        f"""
        import bpy, json
        from mathutils import Vector

        config = json.loads({json.dumps(json.dumps(config))})
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete()

        path = config["mesh_path"]
        if path.lower().endswith(".obj"):
            bpy.ops.wm.obj_import(filepath=path)
        elif path.lower().endswith((".glb", ".gltf")):
            bpy.ops.import_scene.gltf(filepath=path)
        else:
            raise RuntimeError("Unsupported render mesh format")

        objects = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
        if not objects:
            raise RuntimeError("No mesh objects imported")

        min_corner = Vector((1e9, 1e9, 1e9))
        max_corner = Vector((-1e9, -1e9, -1e9))
        for obj in objects:
            for corner in obj.bound_box:
                world = obj.matrix_world @ Vector(corner)
                min_corner.x = min(min_corner.x, world.x)
                min_corner.y = min(min_corner.y, world.y)
                min_corner.z = min(min_corner.z, world.z)
                max_corner.x = max(max_corner.x, world.x)
                max_corner.y = max(max_corner.y, world.y)
                max_corner.z = max(max_corner.z, world.z)

        center = (min_corner + max_corner) * 0.5
        extent = max((max_corner - min_corner).length, 0.001)

        view = config["view"]
        if view == "front":
            camera_offset = Vector((0, -extent * 1.9, extent * 0.45))
        elif view == "side":
            camera_offset = Vector((extent * 1.9, 0, extent * 0.45))
        elif view == "back":
            camera_offset = Vector((0, extent * 1.9, extent * 0.45))
        else:
            camera_offset = Vector((extent * 1.35, -extent * 1.65, extent * 0.75))

        bpy.ops.object.camera_add(location=center + camera_offset)
        camera = bpy.context.object
        direction = center - camera.location
        camera.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
        camera.data.lens = 68
        bpy.context.scene.camera = camera

        front_position = camera.location + Vector((0, 0, extent * 0.25))
        bpy.ops.object.light_add(type='AREA', location=front_position)
        key = bpy.context.object
        key.name = 'FlowStudio saturated front key'
        key.data.energy = 1800
        key.data.size = max(3.0, extent * 1.2)

        bpy.ops.object.light_add(type='AREA', location=(center.x - extent, center.y - extent * 0.35, center.z + extent * 0.75))
        fill = bpy.context.object
        fill.name = 'FlowStudio color fill'
        fill.data.energy = 950
        fill.data.size = max(2.0, extent * 0.9)

        bpy.ops.object.light_add(type='AREA', location=(center.x + extent * 0.8, center.y + extent * 0.8, center.z + extent))
        rim = bpy.context.object
        rim.name = 'FlowStudio rim light'
        rim.data.energy = 1200
        rim.data.size = max(2.0, extent * 0.75)

        # Blender 5 exposes Eevee as BLENDER_EEVEE; Blender 4.x used
        # BLENDER_EEVEE_NEXT.  Falling back to Workbench silently discards the
        # imported GLB PBR material and produces the misleading grey renders
        # that this evidence renderer must never publish.
        engine_items = bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items
        engine_ids = {{item.identifier for item in engine_items}}
        if 'BLENDER_EEVEE' in engine_ids:
            bpy.context.scene.render.engine = 'BLENDER_EEVEE'
        elif 'BLENDER_EEVEE_NEXT' in engine_ids:
            bpy.context.scene.render.engine = 'BLENDER_EEVEE_NEXT'
        else:
            raise RuntimeError('Eevee is unavailable; refusing a material-less Workbench render')
        bpy.context.scene.render.resolution_x = 512
        bpy.context.scene.render.resolution_y = 512
        bpy.context.scene.render.film_transparent = False
        world = bpy.context.scene.world
        world.use_nodes = True
        background = world.node_tree.nodes.get('Background')
        if background:
            background.inputs['Color'].default_value = (0.78, 0.84, 0.92, 1.0)
            background.inputs['Strength'].default_value = 0.65
        bpy.context.scene.view_settings.view_transform = 'Standard'
        bpy.context.scene.view_settings.look = 'Medium High Contrast'
        bpy.context.scene.view_settings.exposure = 0
        bpy.context.scene.view_settings.gamma = 1
        bpy.context.scene.render.image_settings.file_format = 'PNG'
        bpy.context.scene.render.filepath = config["output_path"]
        bpy.ops.render.render(write_still=True)
        """
    )


def _creativeflow_pipeline_state() -> dict[str, Any]:
    scripts = {
        "legacy_pipeline": ORIGINAL_PIPELINE_SCRIPT,
        "structured_transfer": TRANSFER_SCRIPT,
        "minimal_transfer": TRANSFER_MINIMAL_SCRIPT,
        "hunyuan3d_post": HY3D_SCRIPT,
        "mesh_worker_mv": MESH_WORKER_SCRIPT,
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
        "root": str(PIPELINE_ROOT),
        "root_exists": PIPELINE_ROOT.exists(),
        "python": str(PYTHON_BIN),
        "python_exists": PYTHON_BIN.exists(),
        "scripts": script_state,
        "structured_transfer_ready": PYTHON_BIN.exists() and TRANSFER_SCRIPT.exists(),
        "minimal_transfer_ready": PYTHON_BIN.exists() and TRANSFER_MINIMAL_SCRIPT.exists(),
        "legacy_pipeline_ready": PYTHON_BIN.exists() and ORIGINAL_PIPELINE_SCRIPT.exists(),
        "hy3d_ready": PYTHON_BIN.exists() and HY3D_SCRIPT.exists() and MESH_WORKER_SCRIPT.exists(),
        "staged_endpoints": [
            "/jobs/creativeflow-original",
            "/jobs/creativeflow-low-fidelity",
            "/jobs/creativeflow-part",
            "/jobs/creativeflow-texture",
            # Backward-compatible aliases:
            "/jobs/creativeflow-silhouette",
            "/jobs/creativeflow-detail",
            "/jobs/creativeflow-global",
            "/jobs/creativeflow-form",
        ],
        "qwen_image_url_configured": bool(QWEN_IMAGE_URL),
        "oss_prefix_root": OSS_PREFIX_ROOT,
    }


def _creativeflow_preflight_state() -> dict[str, Any]:
    pipeline = _creativeflow_pipeline_state()
    qwen_probe = _probe_url(QWEN_IMAGE_URL, method="GET", timeout=1.5)
    kb_probes = {
        "wikidata": _probe_kb_url(
            "https://www.wikidata.org/w/api.php?action=wbsearchentities&search=lantern&language=en&format=json&limit=1",
            timeout=2.0,
        ),
        "getty_aat": _probe_kb_url("https://vocab.getty.edu/aat/300037680.json", timeout=2.0),
    }
    oss_env = _oss_env_state()
    missing_required_paths = [
        item["path"]
        for item in [
            pipeline["scripts"]["structured_transfer"],
            pipeline["scripts"]["hunyuan3d_post"],
            pipeline["scripts"]["mesh_worker_mv"],
        ]
        if not item["exists"]
    ]
    ready_for_transfer = (
        pipeline["structured_transfer_ready"]
        or pipeline["minimal_transfer_ready"]
    ) and pipeline["python_exists"]
    ready_for_hy3d = bool(pipeline["hy3d_ready"])
    oss_ready = all((oss_env.get("configured_keys") or {}).values())
    kb_ready = all(item.get("reachable") for item in kb_probes.values())
    kb_cache_dir = Path(
        os.getenv("CF_KB_CACHE_DIR", "/root/creativeflow_pipeline/data/kb_cache")
    )
    kb_cache_first_ok = kb_cache_dir.exists() and any(kb_cache_dir.glob("**/*"))
    qwen_ready = bool(qwen_probe.get("reachable"))
    core_ready = ready_for_transfer and ready_for_hy3d and not missing_required_paths
    # Graph expansion can proceed via live KB *or* existing cache-first mode.
    long_run_ready = (
        core_ready and qwen_ready and oss_ready and (kb_ready or kb_cache_first_ok)
    )
    return {
        # `ok` tracks whether the worker can serve the main transfer/hy3d path.
        # `long_run_ready` is stricter (KB/OSS/Qwen for full structured batches).
        "ok": core_ready,
        "core_ready": core_ready,
        "long_run_ready": long_run_ready,
        "pipeline": pipeline,
        "missing_required_paths": missing_required_paths,
        "qwen_image": {
            "url_configured": bool(QWEN_IMAGE_URL),
            "url": QWEN_IMAGE_URL,
            "probe": qwen_probe,
            "note": "GET may return 405/404 for POST-only generators; reachable HTTP still proves the service answered.",
        },
        "kb_network": {
            **kb_probes,
            "cache_dir": str(kb_cache_dir),
            "cache_first_ok": kb_cache_first_ok,
            "live_kb_ready": kb_ready,
        },
        "oss": oss_env,
        "warnings": _preflight_warnings(
            pipeline,
            qwen_probe,
            kb_probes,
            oss_env,
            kb_cache_first_ok=kb_cache_first_ok,
        ),
    }


def _probe_url(url: str, method: str = "GET", timeout: float = 4.0) -> dict[str, Any]:
    return _probe_url_with_env(url, method=method, timeout=timeout, env={})


def _kg_proxy_url() -> str:
    """Paid jump / explicit proxy only — never invent a dead 33210 default."""
    return (
        os.getenv("CF_KG_PROXY", "").strip()
        or os.getenv("CF_KB_CURL_PROXY", "").strip()
        or os.getenv("https_proxy", "").strip()
        or os.getenv("HTTPS_PROXY", "").strip()
        or os.getenv("http_proxy", "").strip()
        or os.getenv("HTTP_PROXY", "").strip()
    )


def _probe_kb_url(url: str, timeout: float = 2.0) -> dict[str, Any]:
    # Empty ProxyHandler bypasses process-level proxy env for a true direct probe.
    direct = _probe_url_with_env(url, timeout=timeout, env={})
    if direct.get("reachable"):
        direct["route"] = "direct"
        return direct
    proxy = _kg_proxy_url()
    if not proxy:
        direct["route"] = "direct"
        return direct
    proxied = _probe_url_with_env(
        url,
        timeout=timeout + 2.0,
        env={"http": proxy, "https": proxy},
    )
    proxied["route"] = "proxy"
    proxied["proxy"] = proxy
    proxied["direct_error"] = direct.get("error")
    return proxied


def _probe_url_with_env(
    url: str,
    method: str = "GET",
    timeout: float = 4.0,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    if not (url or "").strip():
        return {
            "reachable": False,
            "status": None,
            "elapsed_sec": 0,
            "error": "not configured",
        }
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler(env or {})
    )
    request = urllib.request.Request(url, method=method)
    start = datetime.now(timezone.utc)
    try:
        with opener.open(request, timeout=timeout) as response:
            elapsed = (datetime.now(timezone.utc) - start).total_seconds()
            return {
                "reachable": True,
                "status": response.status,
                "elapsed_sec": round(elapsed, 3),
                "error": None,
            }
    except urllib.error.HTTPError as exc:
        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
        return {
            "reachable": True,
            "status": exc.code,
            "elapsed_sec": round(elapsed, 3),
            "error": f"HTTP {exc.code}",
        }
    except Exception as exc:
        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
        return {
            "reachable": False,
            "status": None,
            "elapsed_sec": round(elapsed, 3),
            "error": type(exc).__name__,
        }


def _oss_env_state() -> dict[str, Any]:
    export_env = _read_env_exports(Path("/root/.oss_env"))
    keys = [
        "OSS_ACCESS_KEY_ID",
        "OSS_ACCESS_KEY_SECRET",
        "OSS_ENDPOINT",
        "OSS_BUCKET",
    ]
    return {
        "env_file_exists": Path("/root/.oss_env").exists(),
        "configured_keys": {
            key: bool(os.getenv(key) or export_env.get(key))
            for key in keys
        },
        "prefix_root": OSS_PREFIX_ROOT,
    }


def _preflight_warnings(
    pipeline: dict[str, Any],
    qwen_probe: dict[str, Any],
    kb_probes: dict[str, Any],
    oss_env: dict[str, Any],
    *,
    kb_cache_first_ok: bool = False,
) -> list[str]:
    warnings: list[str] = []
    if not pipeline.get("legacy_pipeline_ready"):
        warnings.append("legacy pipeline.py is missing; old CreativeFlow pipeline is not runnable.")
    if not pipeline.get("structured_transfer_ready"):
        warnings.append("structured transfer script is missing.")
    if not pipeline.get("hy3d_ready"):
        warnings.append("Hunyuan3D postprocess or mesh worker script is missing.")
    if not qwen_probe.get("reachable"):
        warnings.append("Qwen image service did not answer the preflight probe.")
    if not all(item.get("reachable") for item in kb_probes.values()):
        proxy = _kg_proxy_url()
        if kb_cache_first_ok:
            warnings.append(
                "Live Wikidata/Getty probe failed, but KB cache is present — "
                "transfer will use CF_KB_CACHE_MODE=cache_first. "
                + (
                    f"Configured jump proxy in use: {proxy}."
                    if proxy
                    else "Set CF_KG_PROXY (or https_proxy) to your paid jump host for live expansion on new nouns."
                )
            )
        else:
            warnings.append(
                "KB graph endpoints unreachable and no KB cache found; "
                + (
                    f"check paid jump proxy ({proxy})."
                    if proxy
                    else "set CF_KG_PROXY / https_proxy to your paid jump host before long graph expansion."
                )
            )
    configured_keys = oss_env.get("configured_keys") or {}
    if not all(configured_keys.values()):
        warnings.append("OSS environment appears incomplete; mesh upload may fail.")
    return warnings


def _partfield_setup_state() -> dict[str, Any]:
    running = False
    setup_processes: list[dict[str, Any]] = []
    try:
        proc = subprocess.run(
            [
                "ps",
                "-eo",
                "pid,ppid,etime,pcpu,pmem,args",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=2,
        )
        for line in proc.stdout.splitlines()[1:]:
            if not any(
                marker in line
                for marker in [
                    "setup_partfield_env.sh",
                    "continue_partfield_after_torch.sh",
                    "/venvs/partfield/bin/python -m pip",
                    "model_objaverse.ckpt",
                ]
            ):
                continue
            parts = line.split(None, 5)
            if len(parts) < 6:
                continue
            pid, ppid, elapsed, cpu, mem, command = parts
            setup_processes.append(
                {
                    "pid": pid,
                    "ppid": ppid,
                    "elapsed": elapsed,
                    "cpu": cpu,
                    "mem": mem,
                    "command": command[:240],
                }
            )
        running = bool(setup_processes)
    except Exception:
        running = False
    log_tail = None
    if PARTFIELD_SETUP_LOG.exists():
        try:
            text = PARTFIELD_SETUP_LOG.read_text(encoding="utf-8", errors="replace")
            log_tail = text[-1200:]
        except OSError:
            log_tail = None
    return {"running": running, "processes": setup_processes, "log_tail": log_tail}


@app.post("/assets/upload")
@app.post("/api/v1/assets", dependencies=[Depends(_require_v1_api_key)])
async def upload_asset(
    request: Request,
    flowstudio_asset_id: str = Form(...),
    session_id: str = Form(""),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    suffix = Path(file.filename or "source.glb").suffix.lower()
    if suffix not in {
        ".glb", ".obj", ".zip",
        ".png", ".jpg", ".jpeg", ".webp",
        ".json", ".npy",
    }:
        raise HTTPException(status_code=400, detail=f"Unsupported asset type: {suffix}")
    asset_id = f"rasset_{uuid4().hex[:10]}"
    asset_dir = ASSET_ROOT / asset_id
    asset_dir.mkdir(parents=True, exist_ok=True)
    target = asset_dir / f"source{suffix}"
    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    result = {
        "asset_id": asset_id,
        "flowstudio_asset_id": flowstudio_asset_id,
        "session_id": session_id,
        "filename": file.filename,
        "content_type": file.content_type or guess_type(str(target))[0],
        "size_bytes": target.stat().st_size,
    }
    if not request.url.path.startswith("/api/v1/"):
        result["path"] = str(target)
    return result


def variation_capabilities_v1() -> dict[str, Any]:
    return {
        "api_version": "v1",
        "execution": "asynchronous",
        "variations": {
            "low_fidelity": {
                "required_assets": ["image_asset_id"],
                "changes": "global silhouette/massing",
            },
            "part": {
                "required_assets": [
                    "image_asset_id",
                    "mesh_asset_id",
                    "brush_mask_asset_id",
                    "sam3d_manifest_asset_id",
                    "part_semantics_asset_id",
                ],
                "changes": "one SAM3D-resolved part",
            },
            "texture": {
                "required_assets": ["image_asset_id"],
                "changes": "material/PBR appearance while preserving structure",
            },
        },
        "parameters": {
            "kg": VariationKGOptions().model_dump(),
            "image": VariationImageOptions().model_dump(),
            "mesh": VariationMeshOptions().model_dump(),
        },
        "routes": {
            "upload": "POST /api/v1/assets",
            "submit": "POST /api/v1/variation-jobs",
            "status_and_results": "GET /api/v1/variation-jobs/{job_id}",
            "cancel": "POST /api/v1/variation-jobs/{job_id}/cancel",
            "openapi": "/docs",
        },
    }


@app.post(
    "/api/v1/variation-jobs",
    dependencies=[Depends(_require_v1_api_key)],
)
async def submit_variation_v1(req: VariationJobV1Request) -> dict[str, Any]:
    stage = _canonical_variation(req.variation)
    expected_kind = f"creativeflow_{stage}"
    for existing in jobs.values():
        if (
            existing.flowstudio_job_id == req.client_job_id
            and existing.kind == expected_kind
            and existing.status != "failed"
        ):
            return _v1_job_response(existing)
    source_image_path = _asset_path(req.source.image_asset_id, "source image", required=True)
    source_mesh_path = _asset_path(req.source.mesh_asset_id, "source mesh")
    brush_mask_path = _asset_path(req.source.brush_mask_asset_id, "brush mask")
    sam3d_manifest_path = _asset_path(req.source.sam3d_manifest_asset_id, "SAM3D manifest")
    part_semantics_path = _asset_path(req.source.part_semantics_asset_id, "part semantics")
    if stage == "part":
        missing = [
            name
            for name, value in {
                "mesh_asset_id": source_mesh_path,
                "brush_mask_asset_id": brush_mask_path,
                "sam3d_manifest_asset_id": sam3d_manifest_path,
                "part_semantics_asset_id": part_semantics_path,
            }.items()
            if not value
        ]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Part variation requires real SAM3D assets: {', '.join(missing)}",
            )
    internal = CreativeFlowPartJobRequest(
        flowstudio_job_id=req.client_job_id,
        request={
            "object_type": req.object_type.strip().lower(),
            "intent": {"text": req.prompt} if req.prompt else {},
        },
        stage=stage,
        fidelity=req.fidelity,
        target_part=req.target_part,
        source_image_path=source_image_path,
        source_mesh_path=source_mesh_path,
        source_multiview_paths=[
            str(_asset_path(asset_id, "multiview", required=True))
            for asset_id in req.source.multiview_asset_ids
        ],
        source_elements_path=_asset_path(
            req.source.source_elements_asset_id, "source elements"
        ),
        brush_mask_path=brush_mask_path,
        sam3d_manifest_path=sam3d_manifest_path,
        part_semantics_path=part_semantics_path,
        sam3d_projection_mask_path=_asset_path(
            req.source.sam3d_projection_mask_asset_id, "SAM3D projection mask"
        ),
        socket_constraints=req.socket_constraints,
        divergence_axes=req.divergence_axes,
        candidate_count=req.kg.candidate_pool_size,
        kg_options=req.kg.model_dump(),
        image_options=req.image.model_dump(),
        mesh_options=req.mesh.model_dump(),
        run_hy3d=req.mesh.enabled,
        dry_run=req.dry_run,
    )
    job = _creativeflow_staged_job(stage, internal)
    return _v1_job_response(job)


@app.get(
    "/api/v1/variation-jobs/{job_id}",
    dependencies=[Depends(_require_v1_api_key)],
)
def get_variation_v1(job_id: str) -> dict[str, Any]:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.kind.startswith("creativeflow_"):
        raise HTTPException(status_code=404, detail="Variation job not found")
    return _v1_job_response(job)


@app.post(
    "/api/v1/variation-jobs/{job_id}/cancel",
    dependencies=[Depends(_require_v1_api_key)],
)
async def cancel_variation_v1(job_id: str) -> dict[str, Any]:
    job = await cancel_job(job_id)
    return _v1_job_response(job)


@app.post("/jobs/transfer")
async def submit_transfer(req: TransferJobRequest) -> WorkerJob:
    _preflight()
    script = TRANSFER_MINIMAL_SCRIPT if req.transfer_variant == "minimal" else TRANSFER_SCRIPT
    if not script.exists():
        raise HTTPException(status_code=503, detail=f"Missing transfer script: {script}")
    job = _create_job("transfer", req.flowstudio_job_id, req.model_dump())
    request_path = Path(job.work_dir) / "request.json"
    transfer_out = Path(job.work_dir) / "transfer"
    transfer_out.mkdir(parents=True, exist_ok=True)
    request_path.write_text(json.dumps(_to_creativeflow_request(req.request), indent=2), encoding="utf-8")

    env = os.environ.copy()
    if req.max_direction_paths is not None:
        env["CF_MAX_DIRECTION_PATHS"] = str(req.max_direction_paths)
    if req.candidates_per_rationale is not None:
        env["CF_GENERATION_CANDIDATES_PER_RATIONALE"] = str(req.candidates_per_rationale)
    env.setdefault("CF_KB_HTTP_TIMEOUT_SEC", "2")
    env.setdefault("CF_KB_HTTP_RETRIES", "0")
    env.setdefault("CF_KB_CACHE_MODE", "cache_first")
    env.setdefault("CF_KB_CACHE_STALE_ON_ERROR", "1")
    library = _library_variation(req.request, "original")
    env.setdefault("CF_GRAPH_PROMPT_FALLBACK", "1")
    if library.get("fallback_graph_labels"):
        env.setdefault(
            "CF_GRAPH_FALLBACK_LABELS",
            json.dumps(library["fallback_graph_labels"], ensure_ascii=False),
        )
    proxy = _kg_proxy_url()
    if proxy:
        env.setdefault("https_proxy", proxy)
        env.setdefault("http_proxy", proxy)
        env.setdefault("CF_KB_CURL_PROXY", proxy)
        env.setdefault("CF_KG_PROXY", proxy)
    if QWEN_IMAGE_URL:
        env.setdefault("CF_QWEN_IMAGE_URL", QWEN_IMAGE_URL)
    env.setdefault("CF_QWEN_IMAGE_WIDTH", "512")
    env.setdefault("CF_QWEN_IMAGE_HEIGHT", "512")
    env.setdefault("CF_QWEN_IMAGE_STEPS", "4")

    cmd = [
        str(PYTHON_BIN),
        str(script),
        "--request-json",
        str(request_path),
        "--out-dir",
        str(transfer_out),
    ]
    if req.dry_run:
        job.status = "completed"
        job.stage = "dry_run"
        job.progress = 1
        job.message = "Transfer dry run completed"
        job.result = {"cmd": cmd, "request_path": str(request_path), "out_dir": str(transfer_out)}
        job.updated_at = now_iso()
        jobs[job.job_id] = job
        return job
    asyncio.create_task(_run_job(job.job_id, cmd, env, "transfer_engine_result.json"))
    return job


@app.post("/jobs/creativeflow-part")
async def submit_creativeflow_part(req: CreativeFlowPartJobRequest) -> WorkerJob:
    return _creativeflow_staged_job("part", req)


@app.post("/jobs/creativeflow-global")
async def submit_creativeflow_global(req: CreativeFlowPartJobRequest) -> WorkerJob:
    return _creativeflow_staged_job("low_fidelity", req)


@app.post("/jobs/creativeflow-form")
async def submit_creativeflow_form(req: CreativeFlowPartJobRequest) -> WorkerJob:
    return _creativeflow_staged_job("part", req)


@app.post("/jobs/creativeflow-texture")
async def submit_creativeflow_texture(req: CreativeFlowPartJobRequest) -> WorkerJob:
    return _creativeflow_staged_job("texture", req)


@app.post("/jobs/creativeflow-original")
async def submit_creativeflow_original(req: CreativeFlowPartJobRequest) -> WorkerJob:
    return _creativeflow_staged_job("original", req)


@app.post("/jobs/creativeflow-silhouette")
async def submit_creativeflow_silhouette(req: CreativeFlowPartJobRequest) -> WorkerJob:
    return _creativeflow_staged_job("low_fidelity", req)


@app.post("/jobs/creativeflow-detail")
async def submit_creativeflow_detail(req: CreativeFlowPartJobRequest) -> WorkerJob:
    return _creativeflow_staged_job("part", req)


@app.post("/jobs/creativeflow-low-fidelity")
async def submit_creativeflow_low_fidelity(req: CreativeFlowPartJobRequest) -> WorkerJob:
    return _creativeflow_staged_job("low_fidelity", req)


def _load_json_object(path: str | None, label: str) -> dict[str, Any]:
    if not path:
        return {}
    resolved = Path(path)
    if not resolved.is_file():
        raise HTTPException(status_code=400, detail=f"Missing {label}: {resolved}")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail=f"{label} must contain a JSON object")
    return payload


def _creativeflow_staged_job(stage: str, req: CreativeFlowPartJobRequest) -> WorkerJob:
    stage = _canonical_variation(stage)
    # FlowStudio can ask for prompt-driven whole-object divergence from a 3D
    # white model before a viewport screenshot/mask exists.  In that case Qwen
    # Image should still generate text-only visual candidates instead of
    # rejecting the job.  If a source image is present we use the conditioned
    # path below; otherwise this becomes an unconditioned image generation.
    conditioned = bool(req.source_image_path)
    if stage == "part" and not req.dry_run and conditioned:
        if not req.source_mesh_path or not req.brush_mask_path:
            raise HTTPException(
                status_code=400,
                detail="Conditioned CreativeFlow Part requires source_mesh_path and brush_mask_path",
            )
        if not req.sam3d_manifest_path or not req.part_semantics_path:
            raise HTTPException(
                status_code=400,
                detail=(
                    "CreativeFlow Part requires sam3d_manifest_path and part_semantics_path; "
                    "the brush mask is semantic-resolution evidence only and PartField is not supported"
                ),
            )
    kind = f"creativeflow_{stage}"
    job = _create_job(kind, req.flowstudio_job_id, {**req.model_dump(), "stage": stage})
    out_dir = Path(job.work_dir) / kind
    out_dir.mkdir(parents=True, exist_ok=True)
    result_path = out_dir / f"{kind}_result.json"
    part_semantics = _load_json_object(
        req.part_semantics_path, "SAM3D part semantics"
    ) if req.part_semantics_path else {}
    source_elements = _load_json_object(
        req.source_elements_path, "source elements"
    ) if req.source_elements_path else {}
    stage_profile = _stage_profile(stage, req.fidelity)
    image_options = dict(req.image_options)
    mesh_options = dict(req.mesh_options)
    analogy_prompt_package = _coerce_analogy_prompt_package(
        req.analogy_prompt_package
        or ((req.request.get("generation") or {}).get("metadata") or {}).get("analogy_prompt_package")
        or {}
    )
    if image_options:
        stage_profile["image_width"] = int(image_options.get("width") or stage_profile["image_resolution"])
        stage_profile["image_height"] = int(image_options.get("height") or stage_profile["image_resolution"])
        stage_profile["image_steps"] = int(image_options.get("steps") or stage_profile["image_steps"])
    if mesh_options.get("max_candidates") is not None:
        stage_profile["hy3d_max_candidates"] = int(mesh_options["max_candidates"])
    if mesh_options.get("enabled") is not None:
        stage_profile["run_hy3d"] = bool(mesh_options["enabled"])
    if req.run_hy3d is not None:
        stage_profile["run_hy3d"] = req.run_hy3d
    requested_prompt = (
        req.request.get("intent", {}).get("text")
        if isinstance(req.request.get("intent"), dict)
        else None
    )
    library = _library_variation(req.request, stage)
    prompt = requested_prompt or library.get("prompt") or stage_profile["default_prompt"]
    part_label = str(
        part_semantics.get("canonical_name")
        or req.target_part.get("label")
        or req.target_part.get("part_id")
        or "target part"
    )
    axes = req.divergence_axes or library.get("axes") or stage_profile["axes"]
    jump_facets = library.get("jump_facets") or axes
    locked_facets = library.get("locked_facets") or ["object_identity"]
    directions: list[dict[str, Any]] = []
    if analogy_prompt_package:
        directions = _directions_from_analogy_prompt_package(
            analogy_prompt_package,
            stage=stage,
            object_type=_request_object_type(req.request),
            fidelity_profile=stage_profile,
        )
    prompt_chip_mode = bool(analogy_prompt_package)
    result_json: dict[str, Any] = {
        "mode": f"creativeflow-{stage}",
        "variation": f"creativeflow-{stage.replace('_', '-')}",
        "variation_label": stage_profile["label"],
        "stage": stage,
        "conditioned": conditioned,
        "image_mode": "conditioned" if conditioned else "text_only",
        "fidelity": req.fidelity,
        "fidelity_profile": stage_profile,
        "target_part": req.target_part,
        "socket_constraints": req.socket_constraints,
        "source_image_path": req.source_image_path,
        "source_mesh_path": req.source_mesh_path,
        "source_multiview_paths": req.source_multiview_paths,
        "source_elements_path": req.source_elements_path,
        "source_elements": source_elements,
        "brush_mask_path": req.brush_mask_path,
        "brush_mask_role": "part_semantic_resolution_only",
        "sam3d_manifest_path": req.sam3d_manifest_path,
        "part_semantics_path": req.part_semantics_path,
        "part_semantics": part_semantics,
        "sam3d_projection_mask_path": req.sam3d_projection_mask_path,
        "divergence_axes": axes,
        "jump_facets": jump_facets,
        "locked_facets": locked_facets,
        "prompt_source": "human_selected_prompt_chips"
        if prompt_chip_mode
        else ("request" if requested_prompt else ("prompt_library" if library else "stage_default")),
        "analogy_expansion_mode": "prompt_chip_composition"
        if prompt_chip_mode
        else "creativeflow_transfer_engine",
        "knowledge_graph_policy": "not_used_for_prompt_chip_composition"
        if prompt_chip_mode
        else "original_transfer_engine_wikidata_getty_asknature_near_far_balanced",
        "object_type": _request_object_type(req.request),
        "user_prompt": prompt,
        "part_label": part_label,
        "candidate_count": max(1, req.candidate_count),
        "kg_options": dict(req.kg_options),
        "image_options": image_options,
        "mesh_options": mesh_options,
        "analogy_prompt_package": analogy_prompt_package,
        "prompt_token_mode": analogy_prompt_package.get("prompt_token_mode")
        if analogy_prompt_package
        else None,
        "directions": directions,
    }
    result_path.write_text(json.dumps(result_json, ensure_ascii=False, indent=2), encoding="utf-8")
    if not req.dry_run:
        job.status = "running"
        job.stage = "image_generation"
        job.progress = 0.15
        job.message = f"CreativeFlow {stage} image generation started"
        job.result = {"result_path": str(result_path), "result_json": result_json}
        job.updated_at = now_iso()
        jobs[job.job_id] = job
        asyncio.create_task(
            _run_staged_image_generation(
                job.job_id, directions, result_json, result_path, stage_profile,
                req.source_image_path,
            )
        )
        return job
    job.status = "completed"
    job.stage = "dry_run"
    job.progress = 1
    job.message = f"CreativeFlow {stage} dry run completed"
    job.result = {
        "result_path": str(result_path),
        "result_json": result_json,
    }
    job.updated_at = now_iso()
    jobs[job.job_id] = job
    return job


async def _run_staged_image_generation(
    job_id: str,
    directions: list[dict[str, Any]],
    result_json: dict[str, Any],
    result_path: Path,
    stage_profile: dict[str, Any],
    source_image_path: str | None = None,
) -> None:
    job = jobs[job_id]
    image_dir = result_path.parent / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    generated: list[dict[str, Any]] = []
    image_phase_entered = False
    try:
        image_options = result_json.get("image_options") or {}
        attempts_per_candidate = int(image_options.get("attempts_per_candidate") or 3)
        base_seed = int(image_options.get("seed") or 42)
        source_strength = image_options.get("source_strength")
        if not directions:
            job.stage = "knowledge_graph_expansion"
            job.message = "Expanding near/far directions from the CreativeFlow knowledge graphs"
            jobs[job_id] = job
            directions = await asyncio.to_thread(
                _expand_variation_directions_sync, result_json, result_path.parent
            )
            result_json["directions"] = directions
            result_path.write_text(json.dumps(result_json, ensure_ascii=False, indent=2), encoding="utf-8")
        if not directions:
            raise RuntimeError("CreativeFlow knowledge-graph expansion returned no retained directions")
        job.stage = "model_phase_image"
        job.message = "Preparing Qwen-image GPU phase"
        job.updated_at = now_iso()
        jobs[job_id] = job
        phase_output = await asyncio.to_thread(_run_model_phase_sync, "image", 480)
        result_json.setdefault("model_phase_log", {})["image"] = phase_output
        image_phase_entered = True
        for index, direction in enumerate(directions):
            job.progress = min(0.9, 0.15 + 0.75 * (index / max(1, len(directions))))
            job.message = f"Generating staged preview {index + 1}/{len(directions)}"
            job.updated_at = now_iso()
            jobs[job_id] = job
            prompt = str(direction.get("execution_prompt") or direction.get("label") or "design variant")
            out_path = image_dir / f"{direction.get('direction_id') or f'dir_{index + 1:02d}'}.png"
            generator = _generate_qwen_image_sync
            generator_args: tuple[Any, ...] = ()
            conditioned = bool(source_image_path) and result_json.get(
                "stage"
            ) in {"low_fidelity", "part", "texture"}
            if conditioned:
                generator = _generate_qwen_conditioned_sync
                generator_args = (
                    str(result_json.get("stage")), source_image_path,
                )
            else:
                prompt = _text_only_execution_prompt(result_json, direction, prompt)
            image_score: dict[str, Any] = {}
            generation_attempts: list[dict[str, Any]] = []
            for attempt in range(attempts_per_candidate):
                seed = base_seed + index + attempt * 101
                conditioned_args = generator_args
                if generator is _generate_qwen_conditioned_sync:
                    conditioned_args = (*generator_args, source_strength)
                await asyncio.to_thread(
                    generator,
                    prompt,
                    out_path,
                    int(stage_profile.get("image_width") or stage_profile.get("image_resolution") or 512),
                    int(stage_profile.get("image_height") or stage_profile.get("image_resolution") or 512),
                    int(stage_profile.get("image_steps") or 8),
                    seed,
                    *conditioned_args,
                )
                if result_json.get("stage") in {"low_fidelity", "part", "texture"} and source_image_path:
                    image_score = await asyncio.to_thread(
                        score_candidate_image,
                        stage=str(result_json["stage"]),
                        source_image_path=str(source_image_path),
                        candidate_image_path=str(out_path),
                    )
                else:
                    image_score = {
                        "image_qa_passed": True,
                        "reasons": [],
                        "metrics": {},
                        "mode": "text_only_no_source_image",
                    }
                generation_attempts.append(
                    {"attempt": attempt + 1, "seed": seed, "image_score": image_score}
                )
                if image_score.get("image_qa_passed"):
                    break
            if not image_score.get("image_qa_passed"):
                raise RuntimeError(
                    f"direction {direction.get('direction_id')} failed image QA after "
                    f"{attempts_per_candidate} attempts: "
                    f"{image_score.get('reasons')}"
                )
            direction["preview_image_path"] = str(out_path)
            direction["image_score"] = image_score
            direction["generation_attempts"] = generation_attempts
            generated.append(
                {
                    "direction_id": direction.get("direction_id"),
                    "prompt": prompt,
                    "image": str(out_path),
                    "image_score": image_score,
                }
            )
        diversity = await asyncio.to_thread(
            pairwise_diversity, [item["image"] for item in generated]
        )
        result_json["pairwise_diversity"] = diversity
        if not diversity.get("passed"):
            raise RuntimeError("generated directions failed pairwise image diversity QA")
        result_json["generated_previews"] = generated
        if stage_profile.get("run_hy3d"):
            try:
                hy3d_summary = await _run_staged_hy3d(
                    job_id, result_path.parent, result_json, stage_profile
                )
                result_json["hy3d_summary"] = hy3d_summary
                _attach_staged_meshes(result_json, hy3d_summary)
            except Exception as exc:
                # Images are the primary deliverable; a mesh-stage failure must
                # not discard valid visual candidates from the frontend.
                result_json["hy3d_error"] = str(exc)
        result_path.write_text(json.dumps(result_json, ensure_ascii=False, indent=2), encoding="utf-8")
        job.status = "completed"
        job.stage = "completed"
        job.progress = 1
        job.message = "CreativeFlow staged image generation completed"
        job.result = {"result_path": str(result_path), "result_json": result_json}
        job.updated_at = now_iso()
        jobs[job_id] = job
    except Exception as exc:
        job.status = "failed"
        job.stage = "failed"
        job.progress = 1
        job.error = str(exc)
        job.message = "CreativeFlow staged image generation failed"
        job.updated_at = now_iso()
        jobs[job_id] = job
    finally:
        if image_phase_entered:
            asyncio.create_task(_restore_planner_phase_after_generation())


def _expand_variation_directions_sync(
    result_json: dict[str, Any], out_dir: Path
) -> list[dict[str, Any]]:
    if MODEL_PHASE_SCRIPT.is_file():
        phase = subprocess.run(
            [str(MODEL_PHASE_SCRIPT), "planner"],
            capture_output=True,
            text=True,
            timeout=360,
        )
        if phase.returncode != 0:
            raise RuntimeError(
                f"planner model phase failed: {(phase.stderr or phase.stdout)[-2000:]}"
            )
    request_path = out_dir / "variation_direction_request.json"
    output_path = out_dir / "variation_direction_result.json"
    inferred_object_type = _infer_object_type(result_json)
    if not inferred_object_type:
        inferred_object_type = "object"
    payload = {
        "stage": result_json["stage"],
        "object_type": result_json.get("object_type") or inferred_object_type,
        "source_id": f"flowstudio_{result_json.get('stage')}",
        "source_image_path": result_json.get("source_image_path"),
        "source_mesh_path": result_json.get("source_mesh_path"),
        "source_multiview_paths": result_json.get("source_multiview_paths") or [],
        "source_elements": result_json.get("source_elements") or {},
        "source_elements_path": result_json.get("source_elements_path"),
        "target_part": result_json.get("part_label"),
        "part_semantics": result_json.get("part_semantics") or {},
        "part_semantics_path": result_json.get("part_semantics_path"),
        "user_prompt": result_json.get("user_prompt"),
        "candidate_count": result_json.get("candidate_count", 4),
    }
    if str(result_json.get("object_type") or "").strip() in {"", "object"}:
        fallback = _directions_from_request_fallback(
            result_json,
            reason="object_type_unspecified",
        )
        if fallback:
            result_json["object_type"] = inferred_object_type
            return fallback
        raise RuntimeError("variation graph expansion requires a concrete object_type")
    request_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    env = os.environ.copy()
    kg_options = result_json.get("kg_options") or {}
    if bool(kg_options.get("skip_kg_expansion", False)):
        fallback = _directions_from_request_fallback(
            result_json,
            reason="skip_kg_expansion",
        )
        if fallback:
            return fallback
    top_k = max(1, int(kg_options.get("top_k") or payload["candidate_count"]))
    candidate_pool_size = max(
        top_k, int(kg_options.get("candidate_pool_size") or payload["candidate_count"])
    )
    env["CF_TRANSFER_PIPELINE_ROOT"] = str(PIPELINE_ROOT)
    env.setdefault("CF_VISION_LLM_API_BASE", PLANNER_API_BASE)
    env.setdefault("CF_VISION_LLM_MODEL", "qwen3-planner")
    env.setdefault("CF_TEXT_LLM_API_BASE", PLANNER_API_BASE)
    env.setdefault("CF_TEXT_LLM_MODEL", "qwen3-planner")
    proxy = _kg_proxy_url()
    use_proxy = bool(kg_options.get("use_proxy", False)) or bool(proxy)
    if use_proxy and proxy:
        env.setdefault("https_proxy", proxy)
        env.setdefault("http_proxy", proxy)
        env.setdefault("CF_KB_CURL_PROXY", proxy)
        env.setdefault("CF_KG_PROXY", proxy)
    elif not env.get("CF_KB_CURL_PROXY") and not env.get("CF_KG_PROXY"):
        env.pop("https_proxy", None)
        env.pop("http_proxy", None)
        env.pop("HTTPS_PROXY", None)
        env.pop("HTTP_PROXY", None)
        env.pop("all_proxy", None)
        env.pop("ALL_PROXY", None)
    env["CF_KB_CACHE_MODE"] = str(kg_options.get("cache_mode") or "cache_first")
    if bool(kg_options.get("allow_partial_graph", True)):
        env["CF_KG_ALLOW_PARTIAL"] = "1"
    env.setdefault("CF_KB_CACHE_TTL_SEC", "0")
    env["CF_KB_HTTP_TIMEOUT_SEC"] = str(
        max(1, int(kg_options.get("request_timeout_sec") or 25))
    )
    env.setdefault("CF_KB_HTTP_RETRIES", "0")
    env.setdefault("CF_GRAPH_AAT_SEARCH_LIMIT", "0")
    env.setdefault("CF_GRAPH_CONCEPT_PROBE_LIMIT", "0")
    env["CF_MAX_DIRECTION_PATHS"] = str(candidate_pool_size)
    env["CF_STAGE1_TOP_K"] = str(top_k)
    env["CF_GRAPH_NEAR_QUOTA"] = str(max(1, candidate_pool_size // 2))
    env["CF_GRAPH_FAR_QUOTA"] = str(max(1, candidate_pool_size // 2))
    if not bool(kg_options.get("scoring_enabled", True)):
        env["CF_SKIP_CANDIDATE_SCORING"] = "1"
    else:
        env.pop("CF_SKIP_CANDIDATE_SCORING", None)
    if bool(kg_options.get("generate_all_retrieved", False)):
        env["CF_GENERATE_ALL_GRAPH_CANDIDATES"] = "1"
    else:
        env.pop("CF_GENERATE_ALL_GRAPH_CANDIDATES", None)
    direction_timeout_sec = max(15, int(kg_options.get("direction_timeout_sec") or 240))
    proc: subprocess.CompletedProcess[str] | None = None
    try:
        proc = subprocess.run(
            [
                str(PYTHON_BIN),
                str(VARIATION_DIRECTION_SCRIPT),
                "--input",
                str(request_path),
                "--output",
                str(output_path),
            ],
            capture_output=True,
            text=True,
            timeout=direction_timeout_sec,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        partial = _directions_from_partial_graph_output(
            output_path,
            result_json,
            reason=f"direction_timeout_{direction_timeout_sec}s",
        )
        if partial:
            return partial
        fallback = _directions_from_request_fallback(
            result_json,
            reason=f"direction_timeout_{direction_timeout_sec}s",
        )
        if fallback:
            return fallback
        raise RuntimeError(
            f"variation graph expansion timed out after {direction_timeout_sec}s"
        ) from exc
    if proc.returncode != 0:
        partial = _directions_from_partial_graph_output(
            output_path,
            result_json,
            reason=f"direction_returncode_{proc.returncode}",
        )
        if partial:
            return partial
        fallback = _directions_from_request_fallback(
            result_json,
            reason=f"direction_returncode_{proc.returncode}",
        )
        if fallback:
            return fallback
        raise RuntimeError(f"variation graph expansion failed: {proc.stderr[-3000:]}")
    graph_result = json.loads(output_path.read_text(encoding="utf-8"))
    if graph_result.get("status") != "completed":
        partial = _directions_from_partial_graph_result(
            graph_result,
            result_json,
            reason=f"direction_status_{graph_result.get('status', 'unknown')}",
        )
        if partial:
            return partial
        fallback = _directions_from_request_fallback(
            result_json,
            reason=f"direction_status_{graph_result.get('status', 'unknown')}",
        )
        if fallback:
            return fallback
        raise RuntimeError(
            f"variation Stage 1 did not complete: {graph_result.get('status', 'unknown')}"
        )
    result_json["source_elements"] = graph_result.get("source_elements") or {}
    result_json["part_semantics"] = graph_result.get("part_semantics") or {}
    result_json["graph_candidates"] = graph_result.get("graph_candidates", [])
    result_json["seed_attributes"] = graph_result.get("seed_attributes", [])
    result_json["abstract_descriptors"] = graph_result.get("abstract_descriptors", [])
    directions = graph_result.get("directions", [])
    stage = str(result_json["stage"])
    part_label = str(result_json.get("part_label") or "selected part")
    for direction in directions:
        anchor = str(direction.get("anchor") or "creative transfer")
        transfer_spec = direction.get("transfer_spec") or {}
        direction["label"] = str(transfer_spec.get("direction_title") or anchor)
        direction["rationale"] = str(transfer_spec.get("semantic_bridge") or "")
        raw_target = str(transfer_spec.get("graph_anchor") or anchor).strip()
        direction["execution_prompt"] = _stage_execution_prompt(
            stage,
            raw_target,
            part_label,
            str(result_json.get("object_type") or "object"),
            require_white_background=bool(
                (result_json.get("image_options") or {}).get("require_white_background", True)
            ),
        )
        direction["fidelity_profile"] = result_json.get("fidelity_profile", {})
    return directions


def _directions_from_request_fallback(
    result_json: dict[str, Any],
    *,
    reason: str,
) -> list[dict[str, Any]]:
    kg_options = result_json.get("kg_options") or {}
    if not bool(kg_options.get("allow_rule_fallback", True)):
        return []
    object_type = str(result_json.get("object_type") or "").strip()
    if not object_type or object_type == "object":
        object_type = _infer_object_type(result_json) or "设计对象"
        result_json["object_type"] = object_type
    stage = str(result_json["stage"])
    part_label = str(result_json.get("part_label") or "selected part")
    axes = result_json.get("divergence_axes") or result_json.get("jump_facets") or ["silhouette"]
    axis_text = ", ".join(str(axis) for axis in axes[:3])
    prompt = str(result_json.get("user_prompt") or "").strip()
    if stage == "low_fidelity":
        raw_target = f"cute plush-toy {object_type} silhouette"
        rationale = (
            f"Smoke fallback direction from the current request: vary {axis_text} while preserving "
            f"the visible {object_type} identity. User intent: {prompt}"
        )
    elif stage == "texture":
        raw_target = f"soft tactile {object_type} material language"
        rationale = (
            f"Smoke fallback direction from the current request: vary material and surface while "
            f"preserving {object_type} geometry. User intent: {prompt}"
        )
    else:
        raw_target = f"playful {part_label} variation"
        rationale = (
            f"Smoke fallback direction from the current request: vary the selected part while "
            f"preserving attachment context. User intent: {prompt}"
        )
    slug = re.sub(r"[^a-z0-9]+", "_", raw_target.lower()).strip("_")[:48] or "request_fallback"
    direction = {
        "direction_id": f"dir_01_{slug}",
        "anchor": raw_target,
        "request_fallback": True,
        "request_fallback_reason": reason,
        "transfer_spec": {
            "direction_title": raw_target,
            "semantic_bridge": rationale,
            "graph_anchor": raw_target,
        },
        "label": raw_target,
        "rationale": rationale,
        "execution_prompt": _stage_execution_prompt(
            stage,
            raw_target,
            part_label,
            object_type,
            require_white_background=bool(
                (result_json.get("image_options") or {}).get("require_white_background", True)
            ),
        ),
        "fidelity_profile": result_json.get("fidelity_profile", {}),
    }
    result_json["directions"] = [direction]
    result_json["request_fallback"] = {
        "used": True,
        "reason": reason,
        "object_type": object_type,
        "axes": axes,
    }
    return [direction]


def _infer_object_type(result_json: dict[str, Any]) -> str:
    """Best-effort object label from the user prompt for generic assets."""
    object_type = str(result_json.get("object_type") or "").strip().lower()
    if object_type and object_type != "object":
        return object_type
    prompt = str(result_json.get("user_prompt") or "").strip()
    lowered = prompt.lower()
    for marker in ("this ", "the ", "a ", "an ", "这个", "那个", "把"):
        idx = lowered.find(marker)
        if idx < 0:
            continue
        chunk = prompt[idx + len(marker):]
        word = re.split(r"[^A-Za-z0-9\u4e00-\u9fff]+", chunk, maxsplit=1)[0]
        word = word.strip("的")
        if word and len(word) <= 24:
            return word
    return ""


def _coerce_analogy_prompt_package(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    tokens = value.get("selected_prompt_tokens")
    final_prompt = str(value.get("final_prompt") or "").strip()
    selected_text = str(value.get("selected_prompt_text") or "").strip()
    if not isinstance(tokens, list):
        tokens = []
    clean_tokens: list[dict[str, Any]] = []
    for item in tokens[:24]:
        if isinstance(item, str):
            label = item.strip()
            record = {"label": label, "role": "keyword"}
        elif isinstance(item, dict):
            label = str(item.get("label") or "").strip()
            record = dict(item)
            record["label"] = label
        else:
            continue
        if label:
            clean_tokens.append(record)
    if not final_prompt and not selected_text and not clean_tokens:
        return {}
    package = dict(value)
    package["selected_prompt_tokens"] = clean_tokens
    package["final_prompt"] = final_prompt
    package["selected_prompt_text"] = selected_text or ", ".join(
        str(item.get("label")) for item in clean_tokens if item.get("label")
    )
    package["prompt_token_mode"] = str(
        package.get("prompt_token_mode") or "human_selectable_chips"
    )
    return package


def _directions_from_analogy_prompt_package(
    package: dict[str, Any],
    *,
    stage: str,
    object_type: str,
    fidelity_profile: dict[str, Any],
) -> list[dict[str, Any]]:
    final_prompt = str(package.get("final_prompt") or "").strip()
    selected_text = str(package.get("selected_prompt_text") or "").strip()
    token_labels = [
        str(item.get("label")).strip()
        for item in package.get("selected_prompt_tokens", [])
        if isinstance(item, dict) and str(item.get("label") or "").strip()
    ]
    if not final_prompt:
        final_prompt = ", ".join(token_labels) or selected_text
    if not final_prompt:
        return []
    direction_ids = [
        str(item)
        for item in package.get("direction_ids", [])
        if isinstance(item, str) and item.strip()
    ]
    label_source = selected_text or ", ".join(token_labels[:4]) or "selected analogy prompt"
    slug = re.sub(r"[^a-z0-9]+", "_", label_source.lower()).strip("_")[:48] or "prompt_tokens"
    return [
        {
            "direction_id": f"dir_01_prompt_{slug}",
            "anchor": label_source,
            "label": f"Prompt chips: {label_source[:72]}",
            "rationale": (
                "Human-selected analogy words from FlowStudio More Creative were composed "
                "into the final generation prompt."
            ),
            "execution_prompt": final_prompt,
            "request_prompt_tokens": token_labels,
            "request_direction_ids": direction_ids,
            "prompt_token_mode": package.get("prompt_token_mode"),
            "analogy_prompt_package": package,
            "transfer_spec": {
                "direction_title": f"Prompt chips: {label_source[:72]}",
                "semantic_bridge": "human_selectable_prompt_chip_composition",
                "graph_anchor": label_source,
            },
            "risk": {
                "identity": "medium",
                "fit": "not_applicable" if stage in {"low_fidelity", "texture"} else "medium",
                "source": "prompt_chips",
            },
            "fidelity_profile": fidelity_profile,
            "object_type": object_type,
        }
    ]


def _directions_from_partial_graph_output(
    output_path: Path,
    result_json: dict[str, Any],
    *,
    reason: str,
) -> list[dict[str, Any]]:
    if not output_path.exists():
        return []
    try:
        graph_result = json.loads(output_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return _directions_from_partial_graph_result(graph_result, result_json, reason=reason)


def _directions_from_partial_graph_result(
    graph_result: dict[str, Any],
    result_json: dict[str, Any],
    *,
    reason: str,
) -> list[dict[str, Any]]:
    kg_options = result_json.get("kg_options") or {}
    if not bool(kg_options.get("allow_partial_graph", True)):
        return []
    graph_candidates = [
        item for item in (graph_result.get("graph_candidates") or []) if isinstance(item, dict)
    ]
    if not graph_candidates:
        return []
    result_json["source_elements"] = graph_result.get("source_elements") or {}
    result_json["part_semantics"] = graph_result.get("part_semantics") or {}
    result_json["graph_candidates"] = graph_candidates
    result_json["seed_attributes"] = graph_result.get("seed_attributes", [])
    result_json["abstract_descriptors"] = graph_result.get("abstract_descriptors", [])
    stage = str(result_json["stage"])
    object_type = str(result_json.get("object_type") or "object")
    part_label = str(result_json.get("part_label") or "selected part")
    count = max(1, int(result_json.get("candidate_count") or 1))
    directions: list[dict[str, Any]] = []
    for index, candidate in enumerate(graph_candidates[:count], start=1):
        raw_target = str(
            candidate.get("raw_kg_target")
            or candidate.get("label")
            or candidate.get("candidate_id")
            or f"partial graph direction {index}"
        ).strip()
        rationale = str(
            candidate.get("same_attribute_rationale")
            or candidate.get("description")
            or "Partial graph evidence was available before the full direction planner finished."
        )
        slug = re.sub(r"[^a-z0-9]+", "_", raw_target.lower()).strip("_")[:48] or f"partial_{index}"
        direction = {
            "direction_id": f"dir_{index:02d}_{slug}",
            "anchor": raw_target,
            "partial_graph_fallback": True,
            "partial_graph_reason": reason,
            "graph_candidate": candidate,
            "transfer_spec": {
                "direction_title": raw_target,
                "semantic_bridge": rationale,
                "graph_anchor": raw_target,
            },
        }
        direction["label"] = raw_target
        direction["rationale"] = rationale
        direction["execution_prompt"] = _stage_execution_prompt(
            stage,
            raw_target,
            part_label,
            object_type,
            require_white_background=bool(
                (result_json.get("image_options") or {}).get("require_white_background", True)
            ),
        )
        direction["fidelity_profile"] = result_json.get("fidelity_profile", {})
        directions.append(direction)
    result_json["directions"] = directions
    result_json["partial_graph_fallback"] = {
        "used": True,
        "reason": reason,
        "graph_candidate_count": len(graph_candidates),
    }
    return directions


def _generate_qwen_image_sync(
    prompt: str,
    out_path: Path,
    width: int,
    height: int,
    steps: int,
    seed: int,
) -> None:
    payload = {
        "prompt": prompt,
        "width": width,
        "height": height,
        "num_inference_steps": steps,
        "seed": seed,
    }
    request = urllib.request.Request(
        QWEN_IMAGE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        # Qwen is a loopback service.  Never let the external KG proxy capture
        # this request when HTTP(S)_PROXY is enabled for graph expansion.
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
            request, timeout=240
        ) as response:
            out_path.write_bytes(response.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Qwen Image HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Qwen Image unavailable: {exc}") from exc


def _generate_qwen_conditioned_sync(
    prompt: str,
    out_path: Path,
    width: int,
    height: int,
    steps: int,
    seed: int,
    stage: str,
    source_image_path: str | None,
    source_strength: float | None = None,
) -> None:
    if not source_image_path:
        raise RuntimeError(f"CreativeFlow {stage} requires a source image")
    payload = {
        "prompt": prompt,
        "width": width,
        "height": height,
        "num_inference_steps": steps,
        "seed": seed,
        "source_image_path": source_image_path,
        "mode": "img2img",
        "strength": (
            float(source_strength)
            if source_strength is not None
            else 0.82 if stage == "low_fidelity" else 0.72 if stage == "part" else 0.62
        ),
    }
    request = urllib.request.Request(
        QWEN_CONDITIONED_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
            request, timeout=900
        ) as response:
            out_path.write_bytes(response.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Qwen conditioned Image HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Qwen conditioned Image unavailable: {exc}") from exc


async def _run_staged_hy3d(
    job_id: str,
    out_root: Path,
    result_json: dict[str, Any],
    stage_profile: dict[str, Any],
) -> dict[str, Any]:
    transfer_path = out_root / "staged_transfer_for_hy3d.json"
    hy3d_out = out_root / "hy3d"
    transfer_result = _staged_transfer_result(result_json)
    transfer_path.write_text(json.dumps(transfer_result, ensure_ascii=False, indent=2), encoding="utf-8")
    pbr_wrapper = Path(
        os.getenv(
            "CF_PBR_WRAPPER",
            "/root/flowstudio_app/remote_worker/run_hy3d_with_pbr.py",
        )
    )
    cmd = [
        str(PYTHON_BIN),
        str(pbr_wrapper),
        "--hy3d-script",
        str(HY3D_SCRIPT),
        "--transfer-result",
        str(transfer_path),
        "--worker-script",
        str(MESH_WORKER_SCRIPT),
        "--out-dir",
        str(hy3d_out),
        "--oss-prefix-root",
        f"{OSS_PREFIX_ROOT}/{job_id}",
        "--max-candidates",
        str(int(stage_profile.get("hy3d_max_candidates") or 1)),
    ]
    job = jobs[job_id]
    job.stage = "mesh_generation"
    job.progress = 0.92
    job.message = "排队等待 GPU"
    job.updated_at = now_iso()
    jobs[job_id] = job
    device = await gpu_pool().acquire()
    try:
        job.message = f"Generating rough staged mesh with Hy3D · GPU {device}"
        job.updated_at = now_iso()
        jobs[job_id] = job
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_hy3d_subprocess_env(device),
        )
        stdout, stderr = await proc.communicate()
    finally:
        gpu_pool().release(device)
    summary_path = hy3d_out / "hunyuan3d_post_summary.json"
    summary: dict[str, Any] = {
        "cmd": cmd,
        "return_code": proc.returncode,
        "stdout_tail": stdout.decode(errors="replace")[-4000:],
        "stderr_tail": stderr.decode(errors="replace")[-4000:],
        "result_path": str(summary_path),
    }
    if summary_path.exists():
        summary["result_json"] = json.loads(summary_path.read_text(encoding="utf-8"))
    if proc.returncode != 0:
        raise RuntimeError(f"Staged Hy3D failed: {summary['stderr_tail']}")
    return summary


def _staged_transfer_result(result_json: dict[str, Any]) -> dict[str, Any]:
    directions = result_json.get("directions", [])
    generated_targets = []
    for index, direction in enumerate(directions, start=1):
        if not isinstance(direction, dict) or not direction.get("preview_image_path"):
            continue
        direction_id = str(direction.get("direction_id") or f"dir_{index:02d}")
        generated_targets.append(
            {
                "candidate_id": direction_id,
                "rationale_id": direction_id,
                "canonical_image": direction["preview_image_path"],
                "execution_prompt": direction.get("execution_prompt", ""),
            }
        )
    return {
        "request_id": f"staged_{result_json.get('stage', 'creativeflow')}",
        "source": {"source_id": f"flowstudio_{result_json.get('stage', 'stage')}"},
        "creative_prompt": result_json.get("directions", [{}])[0].get("execution_prompt", "")
        if result_json.get("directions")
        else "",
        "generated_targets": generated_targets,
    }


def _attach_staged_meshes(result_json: dict[str, Any], hy3d_summary: dict[str, Any]) -> None:
    items = hy3d_summary.get("result_json", {}).get("items", [])
    by_direction = {
        str(item.get("rationale_id")): item
        for item in items
        if isinstance(item, dict) and item.get("rationale_id")
    }
    for direction in result_json.get("directions", []):
        if not isinstance(direction, dict):
            continue
        item = by_direction.get(str(direction.get("direction_id")))
        if not item:
            continue
        direction["mesh_glb"] = item.get("mesh_glb")
        direction["mesh_obj"] = item.get("mesh_obj")
        direction["multiview_grid"] = item.get("multiview_grid")
        direction["mesh_meta"] = item.get("mesh_meta")
        direction["oss_prefix"] = item.get("oss_prefix")


def _stage_profile(stage: str, fidelity: str) -> dict[str, Any]:
    profiles: dict[str, dict[str, Any]] = {
        "original": {
            "label": "CreativeFlow Original",
            "target_text": "complete object relation",
            "default_prompt": "preserve the complete object identity while exploring CreativeFlow relations",
            "axes": ["relation", "semantic_motif", "composition", "character"],
            "image_resolution": 512,
            "image_steps": 8,
            "run_hy3d": True,
            "hy3d_max_candidates": 4,
            "mesh_quality": "original_pipeline",
            "risk": {"fit": "low", "identity": "medium", "detail": "medium"},
        },
        "low_fidelity": {
            "label": "CreativeFlow Low Fidelity",
            "target_text": "global silhouette",
            "default_prompt": "explore broad object silhouettes",
            "axes": ["silhouette", "proportion", "stance", "mass_distribution"],
            "image_resolution": 768,
            "image_steps": 20,
            "run_hy3d": True,
            "hy3d_max_candidates": 4,
            "mesh_quality": "preview",
            "risk": {"fit": "not_applicable", "identity": "high", "detail": "low"},
        },
        "part": {
            "label": "CreativeFlow Part",
            "target_text": "local detail",
            "default_prompt": "preserve the global silhouette while exploring local parts and details",
            "axes": ["accessories", "facial_detail", "local_parts", "surface_depth"],
            "image_resolution": 768,
            "image_steps": 20,
            "run_hy3d": True,
            "hy3d_max_candidates": 4,
            "mesh_quality": "fit_candidate",
            "risk": {"fit": "medium", "identity": "low", "detail": "medium"},
        },
        "texture": {
            "label": "CreativeFlow Texture",
            "target_text": "surface treatment",
            "default_prompt": "explore material and texture variants",
            "axes": ["material", "color", "surface_pattern", "finish"],
            "image_resolution": 768,
            "image_steps": 12,
            "run_hy3d": True,
            "hy3d_max_candidates": 4,
            "mesh_quality": "pbr_material_variant",
            "risk": {"fit": "not_applicable", "identity": "low", "detail": "high"},
        },
    }
    profile = dict(profiles.get(_canonical_variation(stage), profiles["part"]))
    profile["fidelity"] = fidelity
    return profile


def _stage_execution_prompt(
    stage: str,
    raw_kg_target: str,
    part_label: str,
    object_type: str = "object",
    *,
    require_white_background: bool = True,
    conditioned: bool = True,
) -> str:
    stage = _canonical_variation(stage)
    white_background = (
        "纯白色无影棚背景（RGB 255,255,255），无地面、无阴影、无场景、无其他物体，单体居中，完整展示"
        if require_white_background
        else "单体居中，完整展示"
    )
    if stage == "original":
        return raw_kg_target
    if stage == "low_fidelity":
        return f"发挥你的创造力，畅想一个{raw_kg_target}形状的{object_type}，{white_background}"
    if stage == "rough_form":
        return raw_kg_target
    if stage == "texture":
        if not conditioned:
            return f"发挥你的创造力，畅想一个{raw_kg_target}材质的{object_type or '设计对象'}，{white_background}"
        return f"保留这张图中的{object_type}结构和元素不变，畅想一个{raw_kg_target}材质的{object_type}，{white_background}"
    if not conditioned:
        return (
            f"发挥你的创造力，畅想一个{raw_kg_target}形态{part_label}的"
            f"{object_type or '设计对象'}，{white_background}"
        )
    return (
        f"保留这张图中的{object_type}其它结构和元素不变，"
        f"把其中的{part_label}替换为{raw_kg_target}形态的部件，{white_background}"
    )


def _text_only_execution_prompt(
    result_json: dict[str, Any],
    direction: dict[str, Any],
    fallback_prompt: str,
) -> str:
    """Rebuild the prompt for unconditioned text-only generation."""
    stage = _canonical_variation(str(result_json.get("stage") or "part"))
    target = str(
        (direction.get("transfer_spec") or {}).get("graph_anchor")
        or direction.get("anchor")
        or direction.get("label")
        or fallback_prompt
    ).strip()
    part_label = str(result_json.get("part_label") or "设计部件")
    object_type = str(result_json.get("object_type") or "").strip()
    return _stage_execution_prompt(
        stage,
        target,
        part_label,
        object_type or "设计对象",
        require_white_background=bool(
            (result_json.get("image_options") or {}).get("require_white_background", True)
        ),
        conditioned=False,
    )


@app.post("/jobs/hy3d")
async def submit_hy3d(req: Hy3DJobRequest) -> WorkerJob:
    _preflight()
    transfer_result = Path(req.transfer_result_path)
    if not transfer_result.exists():
        raise HTTPException(status_code=400, detail=f"Missing transfer result: {transfer_result}")

    job = _create_job("hy3d", req.flowstudio_job_id, req.model_dump())
    out_dir = Path(job.work_dir) / "hy3d"
    out_dir.mkdir(parents=True, exist_ok=True)
    normalized_transfer_result = _normalize_transfer_result_for_hy3d(
        transfer_result,
        Path(job.work_dir) / "transfer_result_hy3d_normalized.json",
    )
    oss_prefix = f"{OSS_PREFIX_ROOT}/{job.job_id}"
    cmd = [
        str(PYTHON_BIN),
        str(HY3D_SCRIPT),
        "--transfer-result",
        str(normalized_transfer_result),
        "--worker-script",
        str(MESH_WORKER_SCRIPT),
        "--out-dir",
        str(out_dir),
        "--oss-prefix-root",
        oss_prefix,
        "--max-candidates",
        str(req.max_candidates),
    ]
    if req.dry_run:
        job.status = "completed"
        job.stage = "dry_run"
        job.progress = 1
        job.message = "Hy3D dry run completed"
        job.result = {"cmd": cmd, "out_dir": str(out_dir), "oss_prefix": oss_prefix}
        job.updated_at = now_iso()
        jobs[job.job_id] = job
        return job
    env = _hy3d_subprocess_env()
    job.message = "已提交 Hunyuan3D"
    job.progress = 0.08
    job.updated_at = now_iso()
    jobs[job.job_id] = job
    asyncio.create_task(_run_hy3d_job(job.job_id, cmd, env, "hunyuan3d_post_summary.json"))
    return job


@app.post("/jobs/hy3d-from-staged")
async def submit_hy3d_from_staged(req: Hy3DFromStagedJobRequest) -> WorkerJob:
    _preflight()
    staged_result = Path(req.staged_result_path)
    if not staged_result.exists():
        raise HTTPException(status_code=400, detail=f"Missing staged result: {staged_result}")

    staged_payload = json.loads(staged_result.read_text(encoding="utf-8"))
    if req.direction_ids:
        allowed = set(req.direction_ids)
        staged_payload["directions"] = [
            item
            for item in staged_payload.get("directions", [])
            if isinstance(item, dict) and str(item.get("direction_id")) in allowed
        ]
        staged_payload["generated_previews"] = [
            item
            for item in staged_payload.get("generated_previews", [])
            if isinstance(item, dict) and str(item.get("direction_id")) in allowed
        ]
    preview_by_direction = {
        str(item.get("direction_id")): item
        for item in staged_payload.get("generated_previews", [])
        if isinstance(item, dict) and item.get("direction_id")
    }
    for direction in staged_payload.get("directions", []):
        if not isinstance(direction, dict) or direction.get("preview_image_path"):
            continue
        preview = preview_by_direction.get(str(direction.get("direction_id")))
        if isinstance(preview, dict) and preview.get("image"):
            direction["preview_image_path"] = preview["image"]

    transfer_result = _staged_transfer_result(staged_payload)
    if not transfer_result.get("generated_targets"):
        raise HTTPException(status_code=400, detail="No staged preview image is available for Hy3D")
    if not req.dry_run:
        reuse_images = {
            str(target["canonical_image"])
            for target in transfer_result.get("generated_targets") or []
            if isinstance(target, dict) and target.get("canonical_image")
        }
        reused = find_reusable_hy3d_job(reuse_images)
        if reused is not None:
            return reused

    job = _create_job("hy3d_from_staged", req.flowstudio_job_id, req.model_dump())
    out_dir = Path(job.work_dir) / "hy3d"
    out_dir.mkdir(parents=True, exist_ok=True)
    transfer_path = Path(job.work_dir) / "staged_transfer_for_hy3d.json"
    transfer_path.write_text(json.dumps(transfer_result, ensure_ascii=False, indent=2), encoding="utf-8")
    oss_prefix = f"{OSS_PREFIX_ROOT}/{job.job_id}"
    pbr_wrapper = Path(
        os.getenv(
            "CF_PBR_WRAPPER",
            "/root/flowstudio_app/remote_worker/run_hy3d_with_pbr.py",
        )
    )
    cmd = [
        str(PYTHON_BIN),
        str(pbr_wrapper),
        "--hy3d-script",
        str(HY3D_SCRIPT),
        "--transfer-result",
        str(transfer_path),
        "--worker-script",
        str(MESH_WORKER_SCRIPT),
        "--out-dir",
        str(out_dir),
        "--oss-prefix-root",
        oss_prefix,
        "--max-candidates",
        str(max(1, req.max_candidates)),
    ]
    if req.dry_run:
        job.status = "completed"
        job.stage = "dry_run"
        job.progress = 1
        job.message = "Hy3D staged dry run completed"
        job.result = {
            "cmd": cmd,
            "out_dir": str(out_dir),
            "oss_prefix": oss_prefix,
            "transfer_result_path": str(transfer_path),
        }
        job.updated_at = now_iso()
        jobs[job.job_id] = job
        return job
    env = _hy3d_subprocess_env()
    job.message = "已提交 Hunyuan3D"
    job.progress = 0.08
    job.updated_at = now_iso()
    jobs[job.job_id] = job
    asyncio.create_task(_run_hy3d_job(job.job_id, cmd, env, "hunyuan3d_post_summary.json"))
    return job


@app.post("/jobs/autopartgen")
async def submit_autopartgen(req: AutoPartGenJobRequest) -> WorkerJob:
    if not AUTOPARTGEN_ROOT.exists():
        raise HTTPException(status_code=503, detail=f"Missing AutoPartGen root: {AUTOPARTGEN_ROOT}")
    job = _create_job("autopartgen", req.flowstudio_job_id, req.model_dump())
    out_dir = Path(req.output_dir) if req.output_dir else Path(job.work_dir) / "autopartgen"
    out_dir.mkdir(parents=True, exist_ok=True)
    script_path = Path(job.work_dir) / "run_autopartgen.py"
    script_path.write_text(_autopartgen_script(req, out_dir), encoding="utf-8")
    cmd = [str(AUTOPARTGEN_PYTHON), str(script_path)]
    if req.dry_run:
        job.status = "completed"
        job.stage = "dry_run"
        job.progress = 1
        job.message = "AutoPartGen dry run completed"
        job.result = {"cmd": cmd, "script_path": str(script_path), "out_dir": str(out_dir)}
        job.updated_at = now_iso()
        jobs[job.job_id] = job
        return job
    if not AUTOPARTGEN_PYTHON.exists():
        raise HTTPException(status_code=503, detail=f"Missing AutoPartGen Python: {AUTOPARTGEN_PYTHON}")
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{AUTOPARTGEN_ROOT}:{env.get('PYTHONPATH', '')}"
    asyncio.create_task(_run_job(job.job_id, cmd, env, "manifest.json"))
    return job


@app.post("/jobs/partfield")
async def submit_partfield(req: PartFieldJobRequest) -> WorkerJob:
    mesh_path = Path(req.mesh_path)
    if not mesh_path.exists():
        raise HTTPException(status_code=400, detail=f"Missing mesh path: {mesh_path}")
    job = _create_job("partfield", req.flowstudio_job_id, req.model_dump())
    out_dir = Path(req.output_dir) if req.output_dir else Path(job.work_dir) / "partfield"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "partfield_manifest.json"
    cmd = [
        str(PARTFIELD_PYTHON),
        str(WORKER_ROOT / "flowstudio_partfield_worker.py"),
        "--mesh",
        str(mesh_path),
        "--out-dir",
        str(out_dir),
        "--granularity",
        req.granularity,
        "--max-parts",
        str(req.max_parts),
        "--partfield-root",
        str(PARTFIELD_ROOT),
    ]
    if req.brush_mask_path:
        cmd.extend(["--brush-mask", req.brush_mask_path])
    if req.dry_run:
        manifest = {
            "parts": [],
            "face_labels_path": None,
            "segmented_mesh_path": None,
            "note": "PartField dry run only; install PartField and worker script for real execution.",
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        job.status = "completed"
        job.stage = "dry_run"
        job.progress = 1
        job.message = "PartField dry run completed"
        job.result = {
            "cmd": cmd,
            "out_dir": str(out_dir),
            "result_path": str(manifest_path),
            "result_json": manifest,
        }
        job.updated_at = now_iso()
        jobs[job.job_id] = job
        return job
    if not PARTFIELD_ROOT.exists():
        raise HTTPException(status_code=503, detail=f"Missing PartField root: {PARTFIELD_ROOT}")
    if not PARTFIELD_PYTHON.exists():
        raise HTTPException(status_code=503, detail=f"Missing PartField Python: {PARTFIELD_PYTHON}")
    if not PARTFIELD_MODEL.exists() or PARTFIELD_MODEL.stat().st_size <= 0:
        raise HTTPException(
            status_code=503,
            detail=f"Missing or empty PartField checkpoint: {PARTFIELD_MODEL}",
        )
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{WORKER_ROOT}:{PARTFIELD_ROOT}:{env.get('PYTHONPATH', '')}"
    asyncio.create_task(_run_job(job.job_id, cmd, env, "partfield_manifest.json"))
    return job


@app.post("/jobs/sam3d")
async def submit_sam3d(req: Sam3DJobRequest) -> WorkerJob:
    mesh_path = Path(req.mesh_path)
    if not mesh_path.exists():
        raise HTTPException(status_code=400, detail=f"Missing mesh path: {mesh_path}")
    job = _create_job("sam3d", req.flowstudio_job_id, req.model_dump())
    out_dir = Path(req.output_dir) if req.output_dir else Path(job.work_dir) / "sam3d"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "sam3d_manifest.json"
    cmd = [
        str(SAM3D_PYTHON),
        str(WORKER_ROOT / "flowstudio_sam3d_worker.py"),
        "--mesh",
        str(mesh_path),
        "--out-dir",
        str(out_dir),
        "--granularity",
        req.granularity,
        "--max-parts",
        str(req.max_parts),
        "--sam3d-root",
        str(SAM3D_ROOT),
        "--model-root",
        str(SAM3D_MODEL),
        "--blender-bin",
        str(BLENDER_BIN),
    ]
    if req.brush_mask_path:
        cmd.extend(["--brush-mask", req.brush_mask_path])
    if req.epochs is not None:
        cmd.extend(["--epochs", str(req.epochs)])
    if req.sample_num is not None:
        cmd.extend(["--sample-num", str(req.sample_num)])
    if req.pixels_per_image is not None:
        cmd.extend(["--pixels-per-image", str(req.pixels_per_image)])
    if req.mask_batch_size is not None:
        cmd.extend(["--mask-batch-size", str(req.mask_batch_size)])
    if req.dry_run:
        manifest = {
            "parts": [],
            "face_labels_path": None,
            "segmented_mesh_path": None,
            "adapter": "sam3d",
            "note": "SAM3D dry run only; install SAMPart3D/SAM3D worker for real execution.",
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        job.status = "completed"
        job.stage = "dry_run"
        job.progress = 1
        job.message = "SAM3D dry run completed"
        job.result = {
            "cmd": cmd,
            "out_dir": str(out_dir),
            "result_path": str(manifest_path),
            "result_json": manifest,
        }
        job.updated_at = now_iso()
        jobs[job.job_id] = job
        return job
    if not SAM3D_ROOT.exists():
        raise HTTPException(status_code=503, detail=f"Missing SAM3D root: {SAM3D_ROOT}")
    if not SAM3D_PYTHON.exists():
        raise HTTPException(status_code=503, detail=f"Missing SAM3D Python: {SAM3D_PYTHON}")
    worker_script = WORKER_ROOT / "flowstudio_sam3d_worker.py"
    if not worker_script.exists():
        raise HTTPException(status_code=503, detail=f"Missing SAM3D worker script: {worker_script}")
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{WORKER_ROOT}:{SAM3D_ROOT}:{env.get('PYTHONPATH', '')}"
    asyncio.create_task(_run_job(job.job_id, cmd, env, "sam3d_manifest.json"))
    return job


@app.post("/jobs/viewport-sam")
async def submit_viewport_sam(req: ViewportSamJobRequest) -> WorkerJob:
    image_path = Path(req.image_path)
    if not image_path.exists():
        raise HTTPException(status_code=400, detail=f"Missing viewport image: {image_path}")
    checkpoint = SAM3D_MODEL / "sam_vit_h_4b8939.pth"
    if not checkpoint.exists():
        raise HTTPException(status_code=503, detail=f"Missing SAM checkpoint: {checkpoint}")
    job = _create_job("viewport_sam", req.flowstudio_job_id, req.model_dump())
    out_dir = Path(req.output_dir) if req.output_dir else Path(job.work_dir) / "viewport_sam"
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(SAM3D_PYTHON),
        str(WORKER_ROOT / "flowstudio_viewport_sam_worker.py"),
        "--image",
        str(image_path),
        "--out-dir",
        str(out_dir),
        "--point-x",
        str(req.point_x),
        "--point-y",
        str(req.point_y),
        "--checkpoint",
        str(checkpoint),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{WORKER_ROOT}:{env.get('PYTHONPATH', '')}"
    asyncio.create_task(_run_job(job.job_id, cmd, env, "viewport_sam_manifest.json"))
    return job


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _sanitize_for_json(job.model_dump())


@app.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> WorkerJob:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    proc = processes.get(job_id)
    if proc and proc.returncode is None:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
    job.status = "cancelled"
    job.stage = "cancelled"
    job.message = "Job cancelled"
    job.updated_at = now_iso()
    jobs[job_id] = job
    return job


@app.get("/artifacts/{artifact_id}")
def get_artifact(artifact_id: str) -> dict[str, Any]:
    for job in jobs.values():
        if artifact_id == job.job_id:
            return {
                "artifact_id": artifact_id,
                "job_id": job.job_id,
                "work_dir": job.work_dir,
                "result": job.result,
            }
    raise HTTPException(status_code=404, detail="Artifact not found")


@app.get("/artifact-file")
@app.get("/api/v1/artifact-file", dependencies=[Depends(_require_v1_api_key)])
def get_artifact_file(path: str = Query(...)) -> FileResponse:
    requested = Path(path).resolve()
    allowed_roots = _worker_allowed_roots()
    if not any(requested == root or root in requested.parents for root in allowed_roots):
        raise HTTPException(status_code=403, detail="Artifact path is outside worker roots")
    if not requested.exists() or not requested.is_file():
        raise HTTPException(status_code=404, detail=f"Artifact file not found: {requested}")
    return FileResponse(str(requested))


@app.get("/oss-file")
def get_oss_file(key: str = Query(...)) -> Response:
    if not key.startswith("creativeflow/oneclick_cases/"):
        raise HTTPException(status_code=403, detail="OSS key is outside allowed CreativeFlow benchmark prefix")
    try:
        import oss2
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"oss2 is unavailable: {type(exc).__name__}") from exc
    access_key = os.getenv("OSS_ACCESS_KEY_ID")
    secret_key = os.getenv("OSS_ACCESS_KEY_SECRET")
    endpoint = os.getenv("OSS_ENDPOINT", "oss-cn-beijing.aliyuncs.com")
    bucket_name = os.getenv("OSS_BUCKET")
    if not all([access_key, secret_key, endpoint, bucket_name]):
        raise HTTPException(status_code=503, detail="OSS environment is not configured")
    try:
        bucket = oss2.Bucket(oss2.Auth(access_key, secret_key), endpoint, bucket_name)
        obj = bucket.get_object(key)
        content = obj.read()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OSS object read failed: {type(exc).__name__}") from exc
    content_type = guess_type(key)[0] or "application/octet-stream"
    return Response(content=content, media_type=content_type)


def _preflight() -> None:
    missing = [
        str(path)
        for path in [PIPELINE_ROOT, PYTHON_BIN, TRANSFER_SCRIPT, HY3D_SCRIPT, MESH_WORKER_SCRIPT]
        if not path.exists()
    ]
    if missing:
        raise HTTPException(status_code=503, detail={"missing_paths": missing})


def _to_creativeflow_request(flowstudio_request: dict[str, Any]) -> dict[str, Any]:
    asset_id = flowstudio_request.get("asset_id", "asset")
    intent = flowstudio_request.get("intent", {})
    selection = flowstudio_request.get("selection", {})
    object_type = flowstudio_request.get("object_type") or flowstudio_request.get("asset", {}).get("object_type") or "object"
    text = intent.get("text") or "creative design variation"
    return {
        "request_id": flowstudio_request.get("request_id") or f"flowstudio_{asset_id}",
        "source": {
            "source_id": asset_id,
            "object_type": object_type,
            "mesh_path": flowstudio_request.get("mesh_path", ""),
            "image_paths": flowstudio_request.get("image_paths", []),
            "identity_constraints": intent.get("constraints", ["preserve object identity"]),
            "selection": selection,
        },
        "creative_prompt": {
            "raw_text": text,
            "language": "en",
        },
    }


def _autopartgen_script(req: AutoPartGenJobRequest, out_dir: Path) -> str:
    mode = req.mode
    mesh_path = req.mesh_path or ""
    image_path = req.image_path or ""
    mask_path = req.mask_path or ""
    return f"""
from pathlib import Path
import json

from autopartgen.api import (
    GenerationOptions,
    generate_from_image,
    generate_from_image_and_mask,
    generate_from_mesh,
    load_pipeline,
)

pipeline = load_pipeline()
out_dir = Path({str(out_dir)!r})
out_dir.mkdir(parents=True, exist_ok=True)
mode = {mode!r}
options = GenerationOptions(
    grid_size={req.grid_size},
    seed={req.seed},
    remove_background={req.remove_background!r},
    isosurface_backend="skimage",
)

if mode == "mesh":
    result = generate_from_mesh(
        pipeline,
        {mesh_path!r},
        output_dir=out_dir,
        options=options,
    )
elif mode == "image_mask":
    result = generate_from_image_and_mask(
        pipeline,
        {image_path!r},
        {mask_path!r},
        mesh={mesh_path!r} or None,
        output_dir=out_dir,
        options=options,
    )
else:
    result = generate_from_image(
        pipeline,
        {image_path!r},
        output_dir=out_dir,
        options=options,
    )

manifest = {{
    "mode": mode,
    "output_dir": str(out_dir),
    "result_type": type(result).__name__,
    "files": [str(p) for p in out_dir.glob("*")],
}}
(out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(json.dumps(manifest))
"""
