"""FourStageGenerationService: GPU-serialized, recoverable generation jobs.

Strategy doc 9.3/9.5:
- one Qwen-Image job at a time via a single process-wide asyncio lock;
- the GPU scheduler is the ONLY owner of model phase switches; the UI panel
  explicit-start is an operator override, never a concurrent owner;
- jobs persist to SQLite (generation_jobs) with a lease; on restart,
  recover_pending_jobs() re-queues queued/running jobs whose lease is missing
  or expired;
- cancel stops subsequent candidates without deleting finished artifacts;
- only quality-gate-passing artifacts reach the frontend.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from app.models import FourStageRun, GenerationSpec
from app.services.generation.four_stage_quality import GenerationQualityGate
from app.services.generation.four_stage_spec_builder import GenerationSpecBuilder
from app.services.storage.four_stage_store import FourStageStore

logger = logging.getLogger("flowstudio.generation")


class FourStageGenerationService:
    def __init__(
        self,
        store: FourStageStore,
        *,
        builder: GenerationSpecBuilder | None = None,
        quality_gate: GenerationQualityGate | None = None,
        dispatch: Callable[[FourStageRun, GenerationSpec], Awaitable[dict[str, Any]]],
        poll: Callable[[str], Awaitable[dict[str, Any]]],
        lock: asyncio.Lock | None = None,
        poll_interval_sec: float = 2.0,
        max_poll_sec: float = 1800.0,
        lease_sec: float = 300.0,
    ) -> None:
        self.store = store
        self.builder = builder or GenerationSpecBuilder()
        self.quality_gate = quality_gate or GenerationQualityGate()
        self.dispatch = dispatch
        self.poll = poll
        self._lock = lock or asyncio.Lock()
        self.poll_interval_sec = poll_interval_sec
        self.max_poll_sec = max_poll_sec
        self.lease_sec = lease_sec
        self._on_complete: Callable[[str, list[dict[str, Any]]], Awaitable[None]] | None = None
        self._on_failed: Callable[[str, Exception], Awaitable[None]] | None = None
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def set_completion_callbacks(
        self,
        *,
        on_complete: Callable[[str, list[dict[str, Any]]], Awaitable[None]],
        on_failed: Callable[[str, Exception], Awaitable[None]],
    ) -> None:
        self._on_complete = on_complete
        self._on_failed = on_failed

    def build_spec(self, run: FourStageRun, selected_option_id: str) -> GenerationSpec:
        return self.builder.build_spec(run, selected_option_id)

    async def start_generation(
        self,
        run: FourStageRun,
        spec: GenerationSpec,
    ) -> dict[str, Any]:
        job_id = f"genjob_{uuid4().hex[:10]}"
        self.store.save_generation_job(
            {
                "job_id": job_id,
                "run_id": run.run_id,
                "session_id": run.session_id,
                "spec": spec.model_dump(mode="json"),
                "status": "queued",
            }
        )
        task = asyncio.create_task(self._run_job(run, spec, job_id), name=f"four-stage:{job_id}")
        self._tasks[job_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(job_id, None))
        return {"job_id": job_id, "status": "queued", "spec_id": spec.generation_id}

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel an in-process generation task and persist the terminal state."""
        task = self._tasks.get(job_id)
        if task is not None and not task.done():
            task.cancel()
        row = self.store.get_generation_job(job_id)
        if row is None:
            return False
        row.update({"status": "cancelled", "lease_owner": None, "lease_expires_at": None})
        self.store.save_generation_job(row)
        return True

    async def _run_job(
        self,
        run: FourStageRun,
        spec: GenerationSpec,
        job_id: str,
    ) -> None:
        async with self._lock:
            self._mark(job_id, "running", lease=True)
            try:
                remote = await self.dispatch(run, spec)
                if remote.get("artifacts"):
                    artifacts = remote["artifacts"]
                    quality = self.quality_gate.evaluate(spec, artifacts)
                    if not quality.passed:
                        raise RuntimeError(f"quality gate failed: {quality.reason}")
                    self.store.save_generation_job(
                        {
                            **self.store.get_generation_job(job_id),
                            "status": "completed",
                            "lease_owner": None,
                            "lease_expires_at": None,
                            "artifacts": artifacts,
                        }
                    )
                    if self._on_complete is not None:
                        await self._on_complete(run.run_id, artifacts)
                    return
                remote_job_id = str(remote.get("remote_job_id") or "")
                self.store.save_generation_job(
                    {
                        **self.store.get_generation_job(job_id),
                        "remote_job_id": remote_job_id,
                    }
                )
                artifacts: list[dict[str, Any]] = []
                deadline = asyncio.get_event_loop().time() + self.max_poll_sec
                while True:
                    status = await self.poll(remote_job_id)
                    if status.get("status") == "completed":
                        artifacts = status.get("artifacts") or []
                        break
                    if status.get("status") in {"failed", "cancelled"}:
                        raise RuntimeError(
                            f"remote generation {status.get('status')}: "
                            f"{status.get('error') or 'no detail'}"
                        )
                    if asyncio.get_event_loop().time() > deadline:
                        raise TimeoutError("remote generation exceeded max_poll_sec")
                    await asyncio.sleep(self.poll_interval_sec)
                quality = self.quality_gate.evaluate(spec, artifacts)
                if not quality.passed:
                    raise RuntimeError(f"quality gate failed: {quality.reason}")
                self.store.save_generation_job(
                    {
                        **self.store.get_generation_job(job_id),
                        "status": "completed",
                        "lease_owner": None,
                        "lease_expires_at": None,
                        "artifacts": artifacts,
                    }
                )
                if self._on_complete is not None:
                    await self._on_complete(run.run_id, artifacts)
            except asyncio.CancelledError:
                row = self.store.get_generation_job(job_id)
                if row is not None:
                    row.update({"status": "cancelled", "lease_owner": None, "lease_expires_at": None})
                    self.store.save_generation_job(row)
                raise
            except Exception as exc:  # noqa: BLE001
                logger.exception("generation job failed run=%s job=%s", run.run_id, job_id)
                self.store.save_generation_job(
                    {
                        **self.store.get_generation_job(job_id),
                        "status": "failed",
                        "lease_owner": None,
                        "lease_expires_at": None,
                        "error": {
                            "code": "generation_failed",
                            "message": str(exc)[:500],
                            "retryable": True,
                        },
                    }
                )
                if self._on_failed is not None:
                    await self._on_failed(run.run_id, exc)

    def _mark(self, job_id: str, status: str, *, lease: bool = False) -> None:
        from datetime import UTC, datetime, timedelta

        row = self.store.get_generation_job(job_id)
        if row is None:
            return
        now = datetime.now(UTC)
        row["status"] = status
        row["lease_owner"] = f"pid-{uuid4().hex[:8]}" if lease else None
        row["lease_expires_at"] = (
            (now + timedelta(seconds=self.lease_sec)).isoformat() if lease else None
        )
        self.store.save_generation_job(row)

    def recover_pending_jobs(self) -> int:
        """Re-queue expired jobs AND re-dispatch them (restart recovery).

        Strategy doc 9.5: after a backend restart, queued/running jobs with a
        missing or expired lease must be re-queued and actually run again.
        """
        requeued = self.store.recover_generation_jobs()
        if requeued <= 0:
            return requeued
        for job in self.store.list_generation_jobs():
            if job["status"] != "queued":
                continue
            run = self.store.get_run(job["run_id"])
            if run is None:
                continue
            try:
                spec = GenerationSpec.model_validate(job["spec"])
            except Exception:  # noqa: BLE001 - skip malformed rows
                logger.warning("skipping malformed generation job %s", job["job_id"])
                continue
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(self._run_job(run, spec, job["job_id"]))
            else:
                loop.create_task(self._run_job(run, spec, job["job_id"]))
        return requeued
