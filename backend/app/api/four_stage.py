"""Four-stage pipeline API (strategy doc section 10.1)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.models import (
    FourStageRun,
    FourStageRunCreateRequest,
    GateRequest,
    DivergenceSelection,
    SemanticDivergenceParams,
    SemanticDivergenceResponse,
    SessionRecord,
    VersionNodeStatus,
)
from app.services.pipeline.four_stage_orchestrator import (
    FourStageConflict,
    FourStageError,
    FourStageOrchestrator,
)


def _hy3d_artifact_paths(
    summary: dict[str, object],
) -> tuple[str | None, str | None, str | None]:
    """Read both legacy top-level and current worker ``items`` artifacts."""
    item: dict[str, object] = {}
    items = summary.get("items")
    if isinstance(items, list):
        item = next(
            (
                value
                for value in items
                if isinstance(value, dict) and value.get("ok", True) is not False
            ),
            {},
        )

    def first_path(*keys: str) -> str | None:
        for source in (summary, item):
            for key in keys:
                value = source.get(key)
                if value:
                    return str(value)
        return None

    return (
        first_path("mesh_path", "glb_path", "mesh_pbr_glb", "mesh_glb"),
        first_path("obj_path", "mesh_obj_path", "mesh_pbr_obj", "mesh_obj"),
        first_path("preview_path", "grid_path", "multiview_grid"),
    )


def _hy3d_job_payload(status: dict[str, Any], remote_job_id: str) -> dict[str, Any]:
    from urllib.parse import quote as _quote

    mesh_url: str | None = None
    obj_url: str | None = None
    preview_url: str | None = None
    mesh_path: str | None = None
    obj_path: str | None = None
    preview_path: str | None = None
    summary = (
        (status.get("result") or {}).get("result_json")
        if isinstance(status.get("result"), dict)
        else None
    )
    if isinstance(summary, dict):
        mesh_path, obj_path, preview_path = _hy3d_artifact_paths(summary)
        if mesh_path:
            mesh_url = f"/api/v1/remote-worker/artifact-file?path={_quote(str(mesh_path), safe='')}"
        if obj_path:
            obj_url = f"/api/v1/remote-worker/artifact-file?path={_quote(str(obj_path), safe='')}"
        if preview_path:
            preview_url = f"/api/v1/remote-worker/artifact-file?path={_quote(str(preview_path), safe='')}"
    return {
        "status": str(status.get("status") or "running"),
        "remote_job_id": remote_job_id,
        "message": status.get("message"),
        "progress": status.get("progress"),
        "stage": status.get("stage"),
        "mesh_url": mesh_url,
        "obj_url": obj_url,
        "preview_url": preview_url,
        "mesh_path": mesh_path,
        "obj_path": obj_path,
        "detail": status,
        "error": status.get("error"),
    }


# ponytail: 30 min at 5s. Hunyuan+queue is 3–15 min; the old 10 min / 2 min
# cutoffs left version nodes stuck on generating_3d.
_HY3D_FOLLOW_SLEEP_SEC = 5.0
_HY3D_FOLLOW_ATTEMPTS = 360
_hy3d_follow_ids: set[str] = set()


def _apply_hy3d_payload_to_node(
    store: Any,
    version_node_id: str | None,
    session_id: str,
    payload: dict[str, Any],
) -> None:
    if not version_node_id:
        return
    node = store.get_version_node(version_node_id)
    if node is None or node.session_id != session_id:
        return
    status = str(payload.get("status") or "")
    mesh_url = payload.get("mesh_url")
    obj_url = payload.get("obj_url")
    if mesh_url or obj_url:
        node.status = VersionNodeStatus.mesh_ready
        node.mesh_url = str(mesh_url or node.mesh_url or "") or None
        node.obj_url = str(obj_url or node.obj_url or "") or None
        if payload.get("preview_url"):
            node.preview_url = str(payload["preview_url"])
        node.error = None
    elif status in {"failed", "cancelled"}:
        node.status = VersionNodeStatus.mesh_failed
        node.error = str(payload.get("error") or payload.get("message") or status)[:500]
    if payload.get("remote_job_id"):
        node.hy3d_job_id = str(payload["remote_job_id"])
    store.save_version_node(node)


async def follow_four_stage_hy3d(
    *,
    remote_job_id: str,
    session_id: str,
    version_node_id: str | None,
    store: Any,
    remote_adapter: Any,
    websocket_manager: Any,
) -> None:
    """Poll the GPU job until it finishes and persist the version node."""
    if not remote_job_id or remote_job_id in _hy3d_follow_ids:
        return
    _hy3d_follow_ids.add(remote_job_id)
    try:
        for _ in range(_HY3D_FOLLOW_ATTEMPTS):
            try:
                status = await remote_adapter.get_job(remote_job_id)
            except Exception:
                await asyncio.sleep(_HY3D_FOLLOW_SLEEP_SEC)
                continue
            payload = _hy3d_job_payload(status, remote_job_id)
            if websocket_manager and session_id:
                await websocket_manager.broadcast(session_id, "hy3d_progress", payload)
            job_status = str(payload.get("status") or "")
            if payload.get("mesh_url") or payload.get("obj_url"):
                _apply_hy3d_payload_to_node(store, version_node_id, session_id, payload)
                return
            if job_status in {"failed", "cancelled"}:
                _apply_hy3d_payload_to_node(store, version_node_id, session_id, payload)
                return
            if job_status == "completed":
                payload["status"] = "failed"
                payload["error"] = "Hy3D completed without a mesh URL"
                _apply_hy3d_payload_to_node(store, version_node_id, session_id, payload)
                return
            await asyncio.sleep(_HY3D_FOLLOW_SLEEP_SEC)
        timeout_payload = {
            "status": "failed",
            "remote_job_id": remote_job_id,
            "message": "Hy3D timed out",
            "error": "Hy3D timed out",
            "progress": 0,
        }
        if websocket_manager and session_id:
            await websocket_manager.broadcast(session_id, "hy3d_progress", timeout_payload)
        _apply_hy3d_payload_to_node(store, version_node_id, session_id, timeout_payload)
    finally:
        _hy3d_follow_ids.discard(remote_job_id)


def _http_error(exc: FourStageError) -> HTTPException:
    if isinstance(exc, FourStageConflict):
        return HTTPException(status_code=409, detail=str(exc))
    message = str(exc)
    if message.startswith("run not found") or message.startswith("decision not found"):
        return HTTPException(status_code=404, detail=message)
    return HTTPException(status_code=400, detail=message)


def create_four_stage_router(
    *,
    orchestrator: FourStageOrchestrator,
    require_session: Callable[[str], SessionRecord],
    files_root: object | None = None,
    remote_worker_adapter: object | None = None,
    enable_3d_generation: bool = False,
) -> APIRouter:
    router = APIRouter(tags=["four-stage"])

    @router.post("/api/v1/four-stage/runs/{run_id}/hy3d-candidate")
    async def hy3d_candidate(
        run_id: str,
        request: dict,
    ) -> dict:
        """四阶段候选 PNG -> Hy3D mesh（PaintPBR 材质）。"""
        import json as _json
        from pathlib import Path as _Path
        from uuid import uuid4 as _uuid4

        if not enable_3d_generation:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "3D_GENERATION_DISABLED",
                    "message": "3D generation is disabled for this runtime",
                },
            )

        run = orchestrator.store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
        require_session(run.session_id)
        image_url = str(request.get("image_url") or "")
        if not image_url:
            raise HTTPException(status_code=400, detail="image_url is required")
        if remote_worker_adapter is None or not getattr(remote_worker_adapter, "is_configured", False):
            raise HTTPException(status_code=503, detail="Remote worker is not configured")
        # 把 /files/... 相对路径映射到磁盘文件
        if image_url.startswith("/files/"):
            disk_path = _Path(files_root) / image_url[len("/files/") :]
        else:
            disk_path = _Path(image_url)
        if not disk_path.exists():
            raise HTTPException(status_code=404, detail=f"candidate image not found: {image_url}")
        staged_dir = _Path(files_root) / "four_stage_hy3d"
        staged_dir.mkdir(parents=True, exist_ok=True)
        staged_path = staged_dir / f"staged_{_uuid4().hex[:10]}.json"
        prompt = str(request.get("prompt") or "diverge the current design")
        staged = {
            "stage": "four_stage_candidate",
            "directions": [
                {
                    "direction_id": "four_stage_hy3d",
                    "execution_prompt": prompt,
                    "preview_image_path": str(disk_path),
                }
            ],
            "generated_previews": [
                {"direction_id": "four_stage_hy3d", "image": str(disk_path)}
            ],
        }
        staged_path.write_text(_json.dumps(staged, ensure_ascii=False), encoding="utf-8")
        job_id = f"hy3d_cand_{_uuid4().hex[:10]}"
        hy3d_job = await remote_worker_adapter.submit_hy3d_from_staged(
            job_id,
            str(staged_path),
            direction_ids=["four_stage_hy3d"],
            max_candidates=1,
        )
        remote_job_id = str(hy3d_job.get("job_id") or "")
        if not remote_job_id:
            raise HTTPException(status_code=502, detail="Hy3D worker did not return a job id")
        payload = _hy3d_job_payload(hy3d_job, remote_job_id)
        if payload.get("mesh_url") or payload.get("obj_url"):
            payload["status"] = "completed"
            version_node_id = str(request.get("version_node_id") or "").strip() or None
            _apply_hy3d_payload_to_node(
                orchestrator.store,
                version_node_id,
                str(request.get("session_id") or run.session_id or ""),
                payload,
            )
            return payload
        session_id = str(request.get("session_id") or run.session_id or "")
        version_node_id = str(request.get("version_node_id") or "").strip() or None
        if version_node_id:
            node = orchestrator.store.get_version_node(version_node_id)
            if node is not None and node.session_id == session_id:
                node.status = VersionNodeStatus.generating_3d
                node.hy3d_job_id = remote_job_id
                node.error = None
                orchestrator.store.save_version_node(node)
        asyncio.create_task(
            follow_four_stage_hy3d(
                remote_job_id=remote_job_id,
                session_id=session_id,
                version_node_id=version_node_id,
                store=orchestrator.store,
                remote_adapter=remote_worker_adapter,
                websocket_manager=getattr(orchestrator, "websocket_manager", None),
            )
        )
        return {
            "status": str(hy3d_job.get("status") or "running"),
            "remote_job_id": remote_job_id,
            "message": hy3d_job.get("message") or "排队等待 GPU",
            "progress": hy3d_job.get("progress") or 0.08,
            "stage": hy3d_job.get("stage") or "queued",
            "mesh_url": None,
            "obj_url": None,
            "preview_url": None,
        }

    @router.get("/api/v1/four-stage/hy3d-jobs/{job_id}")
    async def hy3d_job_status(job_id: str) -> dict:
        if not enable_3d_generation:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "3D_GENERATION_DISABLED",
                    "message": "3D generation is disabled for this runtime",
                },
            )
        if remote_worker_adapter is None or not getattr(remote_worker_adapter, "is_configured", False):
            raise HTTPException(status_code=503, detail="Remote worker is not configured")
        status = await remote_worker_adapter.get_job(job_id)
        return _hy3d_job_payload(status, job_id)

    @router.post("/api/v1/four-stage/runs", response_model=FourStageRun)
    async def create_run(request: FourStageRunCreateRequest) -> FourStageRun:
        require_session(request.session_id)
        # 前端流式四阶段：交互先建 run（auto_advance=false 不自动推进），
        # 行为事件持续 append，意图判断/点关键词时再 advance 推进。
        return await orchestrator.create_run(request, auto_advance=request.auto_advance)

    @router.get("/api/v1/four-stage/runs/{run_id}", response_model=FourStageRun)
    async def get_run(run_id: str) -> FourStageRun:
        run = orchestrator.store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
        return run

    @router.post("/api/v1/four-stage/runs/{run_id}/events", response_model=FourStageRun)
    async def append_run_events(
        run_id: str,
        request: FourStageRunCreateRequest,
    ) -> FourStageRun:
        """交互中持续追加行为事件并自动推进编码（流式四阶段）。"""
        try:
            return await orchestrator.append_events(run_id, request.events)
        except FourStageError as exc:
            raise _http_error(exc) from exc

    @router.post("/api/v1/four-stage/runs/{run_id}/advance", response_model=FourStageRun)
    async def advance_run(
        run_id: str,
        body: dict | None = None,
    ) -> FourStageRun:
        """从当前阶段继续推进（意图判断→检索；点关键词→决策→awaiting_gate）。"""
        target = (body or {}).get("target") if isinstance(body, dict) else None
        try:
            return await orchestrator.advance_run(run_id, target)
        except FourStageError as exc:
            raise _http_error(exc) from exc

    @router.post("/api/v1/four-stage/runs/{run_id}/retry", response_model=FourStageRun)
    async def retry_run(run_id: str) -> FourStageRun:
        try:
            return await orchestrator.retry_run(run_id)
        except FourStageError as exc:
            raise _http_error(exc) from exc

    @router.post("/api/v1/four-stage/runs/{run_id}/cancel", response_model=FourStageRun)
    async def cancel_run(run_id: str) -> FourStageRun:
        try:
            return await orchestrator.cancel_run(run_id)
        except FourStageError as exc:
            raise _http_error(exc) from exc

    @router.get("/api/v1/four-stage/runs/{run_id}/intent-ir")
    async def get_intent_ir(run_id: str) -> dict:
        run = orchestrator.store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
        if run.intent_ir is None:
            raise HTTPException(status_code=409, detail="intent-ir not available yet")
        return run.intent_ir.model_dump(mode="json")

    @router.get("/api/v1/four-stage/runs/{run_id}/retrieval")
    async def get_retrieval(run_id: str) -> dict:
        run = orchestrator.store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
        if run.retrieval is None:
            raise HTTPException(status_code=409, detail="retrieval not available yet")
        return run.retrieval.model_dump(mode="json")

    @router.get("/api/v1/four-stage/runs/{run_id}/decision")
    async def get_decision(run_id: str) -> dict:
        run = orchestrator.store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
        if run.decision is None:
            raise HTTPException(status_code=409, detail="decision not available yet")
        return run.decision.model_dump(mode="json")

    @router.get("/api/v1/four-stage/runs/{run_id}/divergence-options")
    async def divergence_options(run_id: str) -> dict:
        run = orchestrator.store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
        options: list[dict[str, object]] = []
        if run.semantic_divergence is not None:
            options = [
                {
                    "candidate_id": candidate.candidate_id,
                    "label": candidate.display_label_zh,
                    "label_en": candidate.label_en,
                    "dimension": candidate.group,
                    "prompt_phrase": candidate.prompt_phrase,
                    "source": "semantic_divergence",
                }
                for candidate in run.semantic_divergence.candidates
            ]
        return {
            "run_id": run_id,
            "scope": run.intent_ir.intent.scope if run.intent_ir else "whole",
            "target_part_id": run.intent_ir.target.part_id if run.intent_ir else None,
            "options": options[:24],
            "selection": run.divergence_selection.model_dump(mode="json")
            if run.divergence_selection
            else None,
            "metadata": {
                "decision_seeds_deprecated": True,
                "semantic_divergence_request_key": (
                    run.semantic_divergence.request_key
                    if run.semantic_divergence is not None
                    else None
                ),
            },
        }

    @router.post(
        "/api/v1/four-stage/runs/{run_id}/semantic-divergence",
        response_model=SemanticDivergenceResponse,
    )
    async def refresh_semantic_divergence(
        run_id: str,
        request: SemanticDivergenceParams,
    ) -> SemanticDivergenceResponse:
        try:
            return await orchestrator.refresh_semantic_divergence(run_id, request)
        except FourStageError as exc:
            raise _http_error(exc) from exc

    @router.post("/api/v1/four-stage/runs/{run_id}/semantic-divergence/stream")
    async def refresh_semantic_divergence_stream(
        run_id: str,
        request: SemanticDivergenceParams,
    ) -> StreamingResponse:
        """SSE stream of semantic-divergence progress events.

        Each ``event: phase`` line is emitted as work progresses. The final
        ``event: done`` carries the full ``SemanticDivergenceResponse``.
        """
        queue: asyncio.Queue[tuple[str, Any] | None] = asyncio.Queue()

        async def on_progress(event: dict[str, Any]) -> None:
            await queue.put(("phase", event))

        async def runner() -> None:
            try:
                response = await orchestrator.refresh_semantic_divergence_stream(
                    run_id, request, on_progress=on_progress
                )
                tail = {
                    "phase": "final",
                    "request_key": response.request_key,
                    "validation_counts": response.validation_counts,
                    "fallback_used": response.fallback_used,
                    "fallback_reason": response.fallback_reason,
                    "latency_ms": response.latency_ms,
                }
                await queue.put(("final", tail))
                await queue.put(("done", json.loads(response.model_dump_json())))
            except FourStageError as exc:
                await queue.put(("error", {"phase": "error", "detail": str(exc)}))
            finally:
                await queue.put(None)

        asyncio.create_task(runner())

        async def _generator() -> Any:
            while True:
                item = await queue.get()
                if item is None:
                    break
                event, data = item
                payload = json.dumps(data, ensure_ascii=False)
                yield f"event: {event}\ndata: {payload}\n\n"

        return StreamingResponse(
            _generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    @router.put("/api/v1/four-stage/runs/{run_id}/divergence-selection", response_model=FourStageRun)
    async def save_divergence_selection(
        run_id: str,
        request: DivergenceSelection,
    ) -> FourStageRun:
        try:
            return await orchestrator.save_divergence_selection(run_id, request)
        except FourStageError as exc:
            raise _http_error(exc) from exc

    @router.post("/api/v1/four-stage/decisions/{decision_id}/gate", response_model=FourStageRun)
    async def gate_decision(
        decision_id: str,
        request: GateRequest,
        run_id: str | None = None,
    ) -> FourStageRun:
        """Resolve the direction-level Gate for a run in awaiting_gate.

        ``run_id`` is required until the decision -> run index exists; the
        canonical client passes both fields.
        """
        resolved_run_id = request.run_id or run_id
        if resolved_run_id is None:
            raise HTTPException(status_code=400, detail="run_id is required")
        try:
            return await orchestrator.resolve_gate(
                resolved_run_id,
                decision_id,
                request.action,
                selected_option_id=request.selected_option_id,
                user_revision=request.user_revision,
                reason=request.reason,
                auto_generate=request.auto_generate,
                divergence_params=request.divergence_params,
            )
        except FourStageError as exc:
            raise _http_error(exc) from exc

    @router.post("/api/v1/four-stage/runs/{run_id}/generation")
    async def start_generation(run_id: str) -> dict:
        try:
            return await orchestrator.start_generation(run_id)
        except FourStageError as exc:
            raise _http_error(exc) from exc

    return router
