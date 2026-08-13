"""Action, intent-draft, annotation and observation routers (refactor plan P2).

Mechanical move out of main.py; behavior and endpoint contracts unchanged.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.models import (
    ActionAtom,
    ActionAtomCreateRequest,
    AnnotationArtifactCreateRequest,
    ArtifactRecord,
    BrushMaskArtifactCreateRequest,
    DragOperationArtifactCreateRequest,
    FocusObservationArtifactCreateRequest,
    IntentDraft,
    IntentDraftCreateRequest,
    IntentDraftListResponse,
    IntentDraftUpdateRequest,
    IntentEpisodeCreateRequest,
    IntentEpisodeResponse,
    MemoryRecord,
    PrimitiveAdditionArtifactCreateRequest,
    SmoothOperationArtifactCreateRequest,
    UserEvent,
    now_utc,
)
from app.services.storage.studio_store import InMemoryStudioStore


def create_actions_router(
    *,
    require_session,
    studio_store: InMemoryStudioStore,
    websocket_manager,
    interaction_service,
    publish_perception,
    update_session_live_signals,
    looks_like_prompt_chip_action,
    files_root,
    find_part,
    read_lifecycle,
    interpret_and_publish,
) -> APIRouter:
    router = APIRouter(tags=["actions"])

    @router.post("/api/v1/intent-drafts")
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

    @router.post("/api/v1/sessions/{session_id}/actions")
    async def create_action_atom(
        session_id: str,
        request: ActionAtomCreateRequest,
    ) -> ActionAtom:
        require_session(session_id)
        if looks_like_prompt_chip_action(request):
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
        live_signals_update = update_session_live_signals(
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
            publish_perception=publish_perception,
            defer_vlm=True,
        )
        return atom

    @router.get("/api/v1/sessions/{session_id}/actions")
    async def list_action_atoms(session_id: str, limit: int = 100) -> dict[str, list[ActionAtom]]:
        require_session(session_id)
        return {"actions": studio_store.list_action_atoms(session_id, limit=limit)}

    @router.post("/api/v1/annotations")
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

    @router.post("/api/v1/screenshots")
    async def create_viewport_screenshot_artifact(
        session_id: str = Form(...),
        asset_id: str | None = Form(None),
        part_id: str | None = Form(None),
        metadata: str | None = Form(None),
        file: UploadFile = File(...),
    ) -> ArtifactRecord:
        """Persist a compressed viewport screenshot as an evidence artifact (P1)."""
        require_session(session_id)
        if asset_id and studio_store.get_asset(asset_id) is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {asset_id}")
        suffix = Path(file.filename or "screenshot.jpg").suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise HTTPException(status_code=400, detail=f"Unsupported screenshot type: {suffix}")
        artifact_id = f"art_{uuid4().hex[:10]}"
        shot_dir = files_root / "screenshots" / artifact_id
        shot_dir.mkdir(parents=True, exist_ok=True)
        target = shot_dir / f"viewport{suffix}"
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
                type="viewport_screenshot",
                url=f"/files/screenshots/{artifact_id}/viewport{suffix}",
                session_id=session_id,
                asset_id=asset_id,
                part_id=part_id,
                worker="manual",
                operation="viewport_screenshot_capture",
                metadata={
                    **parsed_metadata,
                    "captured_from": "client_webgl",
                    "uploaded_filename": file.filename,
                    "storage_path": str(target),
                },
            )
        )
        event = UserEvent(
            type="viewport_screenshot_captured",
            event_id=f"evt_{uuid4().hex[:10]}",
            session_id=session_id,
            payload={
                "artifact_id": artifact.artifact_id,
                "screenshot_url": artifact.url,
                "asset_id": asset_id,
                "part_id": part_id,
                "captured_from": "client_webgl",
            },
        )
        studio_store.save_event(event)
        studio_store.save_memory(
            MemoryRecord(
                memory_id=f"mem_{uuid4().hex[:10]}",
                session_id=session_id,
                category="working",
                type="viewport_screenshot",
                source_id=artifact.artifact_id,
                asset_id=asset_id,
                part_id=part_id,
                content={
                    "artifact": artifact.model_dump(mode="json"),
                    "event_id": event.event_id,
                },
                tags=["screenshot", "viewport", "evidence"],
            )
        )
        await websocket_manager.broadcast(
            session_id,
            "viewport_screenshot_captured",
            {
                "artifact": artifact.model_dump(mode="json"),
                "event_id": event.event_id,
            },
        )
        return artifact

    @router.post("/api/v1/brush-masks")
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

    @router.post("/api/v1/smooth-operations")
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

    @router.post("/api/v1/primitive-additions")
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

    @router.post("/api/v1/drag-operations")
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

    @router.post("/api/v1/focus-observations")
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

    @router.get("/api/v1/sessions/{session_id}/intent-drafts")
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

    @router.patch("/api/v1/intent-drafts/{draft_id}")
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

    @router.post("/api/v1/sessions/{session_id}/episodes")
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
            publish_perception=publish_perception,
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

    return router
