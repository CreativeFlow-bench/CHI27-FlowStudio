"""Remote worker job orchestration core (refactor plan P2).

Job lifecycle, persistent store and generic subprocess orchestration moved out
of app.py so the FastAPI assembly only wires handlers; KG pipeline body untouched.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, Field

RUN_ROOT = Path(os.getenv("FLOWSTUDIO_WORKER_RUN_ROOT", "/root/autodl-tmp/flowstudio_worker_runs"))
WORKER_ROOT = Path(__file__).resolve().parent


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkerJob(BaseModel):
    job_id: str
    flowstudio_job_id: str
    kind: str
    status: str = "queued"
    stage: str = "queued"
    progress: float = 0
    message: str | None = None
    request: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    work_dir: str
    pid: int | None = None


class PersistentJobStore(dict[str, WorkerJob]):
    """Small restart-safe store; GPU subprocess recovery remains explicit."""

    def __init__(self, run_root: Path) -> None:
        super().__init__()
        self.run_root = run_root
        if not run_root.is_dir():
            return
        for state_path in run_root.glob("rw_*/job_state.json"):
            try:
                job = WorkerJob.model_validate_json(state_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if job.status in {"queued", "running"}:
                job.status = "failed"
                job.stage = "worker_restarted"
                job.error = "Worker API restarted while this job was active"
                job.message = "Job could not be reattached after worker restart"
                job.updated_at = now_iso()
            super().__setitem__(job.job_id, job)
            self._persist(job)

    def _persist(self, job: WorkerJob) -> None:
        work_dir = Path(job.work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        target = work_dir / "job_state.json"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(job.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(target)

    def __setitem__(self, key: str, value: WorkerJob) -> None:
        super().__setitem__(key, value)
        self._persist(value)




jobs: PersistentJobStore = PersistentJobStore(RUN_ROOT)
processes: dict[str, asyncio.subprocess.Process] = {}
HY3D_PROGRESS_MARKER = "HY3D_PROGRESS "


def apply_hy3d_progress_line(job: WorkerJob, line: str) -> bool:
    """Update a live Hy3D job from a subprocess progress marker."""
    index = line.find(HY3D_PROGRESS_MARKER)
    if index < 0:
        return False
    try:
        payload = json.loads(line[index + len(HY3D_PROGRESS_MARKER) :].strip())
    except Exception:
        return False
    if not isinstance(payload, dict):
        return False
    message = payload.get("message")
    if message:
        job.message = str(message)
    stage = payload.get("stage")
    if stage:
        job.stage = str(stage)
    if payload.get("progress") is not None:
        try:
            job.progress = max(0.0, min(1.0, float(payload["progress"])))
        except (TypeError, ValueError):
            return False
    job.updated_at = now_iso()
    return True


async def _watch_job_stdout(job_id: str, proc: asyncio.subprocess.Process, stdout_path: Path) -> None:
    position = 0
    while True:
        ended = proc.returncode is not None
        try:
            data = stdout_path.read_bytes()
        except FileNotFoundError:
            data = b""
        chunk = data[position:]
        position = len(data)
        if chunk:
            job = jobs.get(job_id)
            if job is not None:
                changed = False
                for line in chunk.decode("utf-8", errors="replace").splitlines():
                    if apply_hy3d_progress_line(job, line):
                        changed = True
                if changed:
                    jobs[job_id] = job
        if ended:
            return
        await asyncio.sleep(0.4)


def _v1_job_response(job: WorkerJob) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "job_id": job.job_id,
        "client_job_id": job.flowstudio_job_id,
        "variation": job.kind.removeprefix("creativeflow_"),
        "status": job.status,
        "stage": job.stage,
        "progress": job.progress,
        "message": job.message,
        "error": job.error,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }
    result_json = job.result.get("result_json") if isinstance(job.result, dict) else {}
    candidates: list[dict[str, Any]] = []
    if isinstance(result_json, dict):
        for direction in result_json.get("directions") or []:
            if not isinstance(direction, dict):
                continue
            candidates.append(
                {
                    "candidate_id": direction.get("direction_id"),
                    "label": direction.get("label"),
                    "prompt": direction.get("execution_prompt"),
                    "image_url": _artifact_url(direction.get("preview_image_path")),
                    "mesh_glb_url": _artifact_url(direction.get("mesh_glb")),
                    "mesh_obj_url": _artifact_url(direction.get("mesh_obj")),
                    "multiview_url": _artifact_url(direction.get("multiview_grid")),
                    "graph_anchor": (direction.get("transfer_spec") or {}).get("graph_anchor"),
                    "mapping": direction.get("transfer_spec"),
                }
            )
    payload["candidates"] = candidates
    payload["result_manifest_url"] = _artifact_url(
        job.result.get("result_path") if isinstance(job.result, dict) else None
    )
    return payload


def _create_job(kind: str, flowstudio_job_id: str, request: dict[str, Any]) -> WorkerJob:
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    job_id = f"rw_{kind}_{uuid4().hex[:10]}"
    work_dir = RUN_ROOT / job_id
    work_dir.mkdir(parents=True, exist_ok=True)
    job = WorkerJob(
        job_id=job_id,
        flowstudio_job_id=flowstudio_job_id,
        kind=kind,
        request=request,
        work_dir=str(work_dir),
    )
    jobs[job_id] = job
    return job


async def _run_job(job_id: str, cmd: list[str], env: dict[str, str], expected_result_name: str) -> None:
    job = jobs[job_id]
    job.status = "running"
    job.stage = job.kind
    if job.progress <= 0:
        job.progress = 0.2
    if not job.message:
        job.message = "Process started"
    job.updated_at = now_iso()
    jobs[job_id] = job

    env = dict(env)
    env["PYTHONUNBUFFERED"] = "1"
    stdout_path = Path(job.work_dir) / "stdout.log"
    stderr_path = Path(job.work_dir) / "stderr.log"
    with stdout_path.open("wb", buffering=0) as stdout, stderr_path.open("wb", buffering=0) as stderr:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=stdout, stderr=stderr, env=env)
        processes[job_id] = proc
        job.pid = proc.pid
        jobs[job_id] = job
        watcher = asyncio.create_task(_watch_job_stdout(job_id, proc, stdout_path))
        try:
            return_code = await proc.wait()
        finally:
            await watcher

    job.updated_at = now_iso()
    job.progress = 1
    if return_code == 0:
        job.status = "completed"
        job.stage = "completed"
        job.message = "Process completed"
        result_path = _find_result(Path(job.work_dir), expected_result_name)
        job.result = {
            "return_code": return_code,
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
            "result_path": str(result_path) if result_path else None,
            "result_json": _read_json_result(result_path),
        }
    else:
        job.status = "failed"
        job.stage = "failed"
        job.message = "Process failed"
        job.error = _clean_log_text(stderr_path.read_text(encoding="utf-8", errors="replace"))[-4000:]
        if not job.error.strip():
            job.error = _clean_log_text(stdout_path.read_text(encoding="utf-8", errors="replace"))[-4000:]
        result_path = _find_result(Path(job.work_dir), expected_result_name)
        job.result = {
            "return_code": return_code,
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
            "result_path": str(result_path) if result_path else None,
            "result_json": _read_json_result(result_path),
        }
    jobs[job_id] = job
    processes.pop(job_id, None)


def _clean_log_text(text: str) -> str:
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    return "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)


def _sanitize_for_json(value: Any) -> Any:
    if isinstance(value, str):
        return _clean_log_text(value)
    if isinstance(value, list):
        return [_sanitize_for_json(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_for_json(item) for item in value]
    if isinstance(value, dict):
        return {
            _sanitize_for_json(key): _sanitize_for_json(item)
            for key, item in value.items()
        }
    return value


def _find_result(work_dir: Path, name: str) -> Path | None:
    direct = work_dir / name
    if direct.exists():
        return direct
    matches = list(work_dir.glob(f"**/{name}"))
    return matches[0] if matches else None


def _read_json_result(path: Path | None) -> dict[str, Any] | list[Any] | None:
    if path is None or not path.exists() or path.stat().st_size > 2_000_000:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _normalize_transfer_result_for_hy3d(source_path: Path, target_path: Path) -> Path:
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    changed = False
    for index, item in enumerate(payload.get("generated_targets", []), start=1):
        if not isinstance(item, dict):
            continue
        image = item.get("canonical_image") or item.get("image") or item.get("creative_image")
        if image and not item.get("canonical_image"):
            item["canonical_image"] = image
            item.setdefault("reconstruction_input_image", image)
            item.setdefault("creative_image", image)
            changed = True
        if not item.get("candidate_id"):
            rationale_id = str(item.get("rationale_id") or f"rat_{index}")
            item["candidate_id"] = f"{index:02d}_{rationale_id}"
            changed = True
    if not changed:
        return source_path
    target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target_path


def _read_env_exports(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            values[key] = value
    return values
