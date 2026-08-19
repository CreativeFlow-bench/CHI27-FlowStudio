"""Sandbox APIs — Gate interpret + semantic divergence prompt lab."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.models import SessionCreateRequest, UserEvent
from app.models.semantic_divergence import (
    KnowledgeEvidence,
    KnowledgeRoute,
    SemanticDivergenceParams,
    SemanticDivergenceRequest,
    SemanticTarget,
)
from app.services.divergence.semantic_knowledge_router import SemanticKnowledgeRouter
from app.services.divergence.knowledge_adapters import vernacular_en_label
from app.services.divergence.semantic_model_clients import (
    DEFAULT_SEMANTIC_DIVERGENCE_SYSTEM_PROMPT,
    SemanticModelOutputError,
    SemanticModelUnavailable,
)
from app.services.generation.qwen_image_client import QwenImageUnavailable
from app.services.intent.interaction_understanding import InteractionUnderstandingService
from app.services.intent.multimodal_intent_predictor import DEFAULT_PLANNER_SYSTEM_PROMPT
from app.services.storage.studio_store import InMemoryStudioStore


class SandboxInterpretRequest(BaseModel):
    session_id: str | None = None
    event_type: str = "brush_end"
    object_type: str = "雪人"
    asset_id: str | None = None
    part_id: str | None = None
    part_label: str | None = None
    intent_text: str | None = None
    text_detail: str | None = None
    drag_length: float | None = None
    smooth_strength: float | None = None
    image_ref_count: int = 0
    system_prompt: str | None = None
    sync_vlm: bool = True
    preview_only: bool = False
    extra_payload: dict[str, Any] = Field(default_factory=dict)


class SandboxDivergeRequest(BaseModel):
    """Direct call into the live semantic-divergence generators (no four-stage run)."""

    object_type: str = "雪人"
    asset_id: str | None = None
    scope: str = "part"
    part_id: str | None = "head"
    part_label: str | None = "帽子"
    user_semantic_intent: str = "让帽子更高一点"
    behavior_summary: str = "brush_end on part"
    gate_question: str | None = None
    hard_constraints: list[str] = Field(default_factory=list)
    temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    strictness: float = Field(default=0.6, ge=0.0, le=1.0)
    per_group_count: int = Field(default=5, ge=5, le=8)
    system_prompt: str | None = None
    preview_only: bool = False
    # primary = gpt/gateway; fallback = secondary model (often faster)
    model_choice: Literal["primary", "fallback", "primary_then_fallback"] = "primary_then_fallback"
    knowledge_mode: Literal["auto", "on", "off"] = "auto"
    use_wikidata: bool | None = None
    use_getty_aat: bool | None = None
    use_asknature: bool | None = None


class SandboxGenerateImagesRequest(BaseModel):
    """Smoke-test the live image model with sandbox-composed prompts."""

    prompts: list[str] = Field(default_factory=list, min_length=1, max_length=4)
    labels: list[str] = Field(default_factory=list)
    # data URL or raw base64 PNG/JPEG; when set, uses identity edit path
    source_image_b64: str | None = None
    # optional /files/... identity image already on disk
    source_image_ref: str | None = None


class SandboxObserveNarrativeRequest(BaseModel):
    """UI-only 3D/context narrator. Never writes Gate / revision / run state."""

    object_type: str = "object"
    part_label: str | None = None
    part_id: str | None = None
    parts: list[str] = Field(default_factory=list, max_length=12)
    preview_image: str | None = Field(default=None, max_length=400_000)
    intent_text: str | None = None
    recent_actions: list[str] = Field(default_factory=list, max_length=16)
    signals: dict[str, Any] = Field(default_factory=dict)
    rule_summary: str | None = None


class SandboxDrawingSemanticRequest(BaseModel):
    """Infer short user intent text from 2D brush evidence when Send has no typed text."""

    object_type: str = "object"
    part_label: str | None = None
    stroke_count: int = 0
    brush_kinds: list[str] = Field(default_factory=list, max_length=8)
    brush_summary: str | None = None


_OBSERVE_NARRATIVE_SYSTEM = """You are FlowStudio's 3D context narrator.
A screenshot of the current 3D model is attached. Describe ONLY what is visible in that image.
Output ONE plain English sentence (10–24 words).
Rules:
1. The sentence MUST start with "This is". Name the object, then its visible style and form.
2. Style/form examples: cute, cartoon, toy-like, realistic, rounded edges, sharp edges, wrinkled, blocky, smooth clay.
3. Do not invent a cute look if the form is hard or faceted. Do not list parts.
4. Forbidden: you/you're/holding/observing/looking/watching/orbit/zoom/hover/inspect/action.
5. Never mention IDs, asset_*, Cube, Sphere, Mball, mesh names, "this part", or viewport.
6. Output JSON only: {"narrative":"This is a cute Santa Claus head with rounded, wrinkled clay-like features."}.
"""


def _is_mesh_jargon(label: str | None) -> bool:
    import re

    text = str(label or "").strip()
    if not text:
        return True
    if re.search(r"(?i)(?:^|_)(asset_|obj_group_|mesh_)", text):
        return True
    if re.search(r"(?i)\b(?:cube|mball|sphere|cylinder|torus|plane|mesh)(?:\.\d+)?\b", text):
        return True
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9]*\.\d+", text))


def _display_object_name(object_type: str | None) -> str:
    obj = str(object_type or "").strip() or "3D model"
    if _is_mesh_jargon(obj) or obj.lower() in {"object", "unknown", "item", "thing", "model", "asset"}:
        return "3D model"
    return obj


def _human_part_names(*labels: str | None) -> list[str]:
    names: list[str] = []
    for label in labels:
        text = str(label or "").strip()
        if not text or _is_mesh_jargon(text) or text in names:
            continue
        names.append(text)
    return names[:6]


def _is_object_state_narrative(text: str) -> bool:
    import re

    stripped = str(text or "").strip()
    if not re.match(r"(?i)^(?:this is|it is|it's)\b", stripped):
        return False
    if re.search(
        r"(?i)\b(?:this part|obj_group_|mball|cube\.\d|mesh_|sphere|cylinder|torus)\b",
        stripped,
    ):
        return False
    return not re.search(
        r"(?i)\b(?:you(?:'re| are)|the user|holding|observing|looking at|watching|orbit|hover|inspect|brushing|before taking)\b",
        stripped,
    )


def _scrub_observe_narrative(text: str) -> str:
    import re

    text = re.sub(r"(?i)\basset_[a-z0-9]+\b", "the model", text)
    text = re.sub(r"(?i)\b(?:obj_group_|mesh_)[a-z0-9_]+\b", "this part", text)
    text = re.sub(r"(?i)\b(?:Cube|Mball|Sphere|Cylinder|Torus|Plane|Mesh)\.\d+\b", "this part", text)
    return re.sub(r"\s+", " ", text).strip()


def _observe_user_content(prompt: str, preview_image: str | None) -> str | list[dict[str, Any]]:
    image = str(preview_image or "").strip()
    if image.startswith("data:image/") and len(image) <= 400_000:
        return [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": image}},
        ]
    return prompt


def _humanize_observe_fallback(
    part_label: str | None,
    object_type: str | None,
    parts: list[str] | None = None,
) -> str:
    del part_label, parts
    return f"This is a {_display_object_name(object_type)}."[:120]


def create_sandbox_router(
    *,
    studio_store: InMemoryStudioStore,
    interaction_service: InteractionUnderstandingService,
    semantic_primary: Any | None = None,
    semantic_fallback: Any | None = None,
    knowledge_router: SemanticKnowledgeRouter | None = None,
    image_client: Any | None = None,
    image_model: str | None = None,
    files_root: Path | None = None,
    text_gateway: Any | None = None,
) -> APIRouter:
    router = APIRouter(tags=["sandbox"])
    kb_router = knowledge_router or SemanticKnowledgeRouter()
    storage_files = Path(files_root) if files_root is not None else None

    @router.get("/api/v1/sandbox/defaults")
    async def sandbox_defaults() -> dict[str, object]:
        return {
            "default_system_prompt": DEFAULT_PLANNER_SYSTEM_PROMPT,
            "default_gate_system_prompt": DEFAULT_PLANNER_SYSTEM_PROMPT,
            "default_divergence_system_prompt": DEFAULT_SEMANTIC_DIVERGENCE_SYSTEM_PROMPT,
            "vlm_configured": interaction_service.vlm_configured(),
            "predictor": getattr(
                interaction_service.predictor, "name", type(interaction_service.predictor).__name__
            ),
            "divergence_primary_configured": bool(
                semantic_primary is not None and getattr(semantic_primary, "configured", False)
            ),
            "divergence_fallback_configured": bool(
                semantic_fallback is not None and getattr(semantic_fallback, "configured", False)
            ),
            "divergence_primary_model": getattr(semantic_primary, "model", None),
            "divergence_fallback_model": getattr(semantic_fallback, "model", None),
            "divergence_primary_provider": type(semantic_primary).__name__ if semantic_primary else None,
            "divergence_fallback_provider": type(semantic_fallback).__name__ if semantic_fallback else None,
            "image_model": image_model,
            "image_configured": image_client is not None,
            "observe_narrative_configured": bool(
                text_gateway is not None and getattr(getattr(text_gateway, "profile", None), "api_key", None)
            ),
            "notes": {
                "engine": "LLM semantic-divergence API (not local rule expansion)",
                "image_engine": "gpt-image-2 via /images/edits (conditioned) or /images/generations",
                "observe_narrative": "UI-only canvas narrator; does not mutate Gate/revision",
                "slow_reason": "primary model generates full candidate JSON (often 20 items); knowledge hops add latency",
                "weights": {
                    "temperature": "model sampling + knowledge route (>=0.7 opens full KB)",
                    "strictness": "validator thresholds",
                    "per_group_count": "candidates per group × 4 groups",
                },
            },
        }

    @router.post("/api/v1/sandbox/observe-narrative")
    async def sandbox_observe_narrative(body: SandboxObserveNarrativeRequest) -> dict[str, object]:
        """Return a short observation line for the AI Behavior panel only."""
        fallback = _humanize_observe_fallback(body.part_label, body.object_type, body.parts)
        preview = str(body.preview_image or "").strip()
        has_preview = preview.startswith("data:image/") and len(preview) <= 400_000
        if text_gateway is None or not getattr(getattr(text_gateway, "profile", None), "api_key", None):
            return {"narrative": fallback, "source": "fallback"}
        if "pytest" in __import__("sys").modules:
            return {"narrative": fallback, "source": "fallback"}
        if not has_preview:
            return {"narrative": fallback, "source": "fallback"}

        from app.services.model_api.types import ModelStage

        object_name = _display_object_name(body.object_type)

        def pick_narrative(raw: dict[str, Any]) -> str:
            import re

            for key in ("narrative", "text", "observation", "summary", "phenomenon"):
                text = str(raw.get(key) or "").strip()
                if len(text) < 6:
                    continue
                if re.search(r"[\u4e00-\u9fff]", text):
                    raise ValueError("narrative must be English-only")
                scrubbed = _scrub_observe_narrative(text)[:160]
                if not _is_object_state_narrative(scrubbed):
                    raise ValueError("narrative must start with 'This is' and describe the screenshot")
                return scrubbed
            raise ValueError(f"missing narrative in {list(raw)[:6]}")

        user_prompt = (
            "A screenshot of the current 3D model is attached. Describe only that image.\n"
            f"Name hint: {object_name}. Ignore the hint if the image shows something else.\n"
            "Write one English sentence starting with 'This is'. Mention visible style and form.\n"
            "Do not list parts or mesh names. Do not mention a user, hands, camera, or any action.\n"
            'Output only: {"narrative":"This is a cute Santa Claus head with rounded, wrinkled clay-like features."}'
        )
        user_content = _observe_user_content(user_prompt, body.preview_image)
        try:
            raw = await text_gateway.transport.chat_json(
                model=text_gateway.profile.fast_text_model,
                messages=[
                    {"role": "system", "content": _OBSERVE_NARRATIVE_SYSTEM},
                    {"role": "user", "content": user_content},
                ],
                stage=ModelStage.PHENOMENON,
                temperature=0.2,
                max_tokens=140,
                timeout_sec=16.0,
                max_retries=1,
            )
            return {
                "narrative": pick_narrative(raw if isinstance(raw, dict) else {}),
                "source": "llm",
                "model": text_gateway.profile.fast_text_model,
            }
        except Exception as first_exc:  # noqa: BLE001
            try:
                raw = await text_gateway.transport.chat_json(
                    model=text_gateway.profile.fast_text_model,
                    messages=[
                        {"role": "system", "content": _OBSERVE_NARRATIVE_SYSTEM},
                        {
                            "role": "user",
                            "content": _observe_user_content(
                                user_prompt
                                + "\nIMPORTANT: Start with 'This is'. Include style and form. Never write You are / holding / observing.",
                                body.preview_image,
                            ),
                        },
                    ],
                    stage=ModelStage.PHENOMENON,
                    temperature=0.1,
                    max_tokens=140,
                    timeout_sec=12.0,
                    max_retries=0,
                )
                return {
                    "narrative": pick_narrative(raw if isinstance(raw, dict) else {}),
                    "source": "llm",
                    "model": text_gateway.profile.fast_text_model,
                }
            except Exception as exc:  # noqa: BLE001 - UI narrator must never fail hard
                import logging

                logging.getLogger(__name__).warning(
                    "observe-narrative fallback: %s / retry: %s", first_exc, exc
                )
                return {"narrative": fallback, "source": "fallback"}

    @router.post("/api/v1/sandbox/drawing-semantic")
    async def sandbox_drawing_semantic(body: SandboxDrawingSemanticRequest) -> dict[str, object]:
        """Infer a short Chinese intent phrase from 2D annotation evidence."""
        kinds = "、".join(body.brush_kinds) if body.brush_kinds else "笔刷"
        focus = body.part_label or body.object_type or "当前对象"
        fallback = (
            f"请根据画面上的 {body.stroke_count or 1} 笔{kinds}标注理解意图，并调整{focus}。"
        )[:120]
        if text_gateway is None or not getattr(getattr(text_gateway, "profile", None), "api_key", None):
            return {"semantic": fallback, "source": "fallback"}
        if "pytest" in __import__("sys").modules:
            return {"semantic": fallback, "source": "fallback"}

        from app.services.model_api.types import ModelStage

        user_prompt = (
            "用户在 3D 模型上用 2D 笔刷画了标注，但发送意图时没有输入文字。"
            "请用一句中文概括绘制意图，供 Planner 使用（12–28 字）。\n"
            f"对象：{body.object_type}\n"
            f"焦点：{focus}\n"
            f"笔数：{body.stroke_count}\n"
            f"笔刷：{kinds}\n"
            f"摘要：{body.brush_summary or '无'}\n"
            '只输出 JSON：{"semantic":"..."}\n'
            '示例：{"semantic":"在可颂表面标出眼睛位置，请据此改造型"}'
        )
        try:
            raw = await text_gateway.transport.chat_json(
                model=text_gateway.profile.fast_text_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You infer short Chinese design-intent phrases from 2D brush marks. "
                            'Reply JSON only: {"semantic":"..."}.'
                        ),
                    },
                    {"role": "user", "content": user_prompt},
                ],
                stage=ModelStage.PHENOMENON,
                temperature=0.2,
                max_tokens=80,
                timeout_sec=12.0,
                max_retries=1,
            )
            semantic = ""
            if isinstance(raw, dict):
                for key in ("semantic", "text", "intent", "summary"):
                    text = str(raw.get(key) or "").strip()
                    if text:
                        semantic = text[:120]
                        break
            if not semantic:
                raise ValueError("missing semantic")
            return {
                "semantic": semantic,
                "source": "llm",
                "model": text_gateway.profile.fast_text_model,
            }
        except Exception as exc:  # noqa: BLE001 - Send must never fail hard on narrator
            import logging

            logging.getLogger(__name__).warning("drawing-semantic fallback: %s", exc)
            return {"semantic": fallback, "source": "fallback"}

    @router.post("/api/v1/sandbox/generate-images")
    async def sandbox_generate_images(body: SandboxGenerateImagesRequest) -> dict[str, object]:
        if image_client is None or storage_files is None:
            raise HTTPException(status_code=503, detail="sandbox image generation is not wired")
        prompts = [str(item).strip() for item in body.prompts if str(item).strip()]
        if not prompts:
            raise HTTPException(status_code=400, detail="at least one prompt is required")
        batch_id = f"sandbox_{uuid4().hex[:10]}"
        out_root = storage_files / "sandbox" / batch_id
        out_root.mkdir(parents=True, exist_ok=True)
        source_path = _materialize_sandbox_source(
            storage_files,
            out_root / "source.png",
            source_image_b64=body.source_image_b64,
            source_image_ref=body.source_image_ref,
        )
        mode = "conditioned" if source_path is not None else "text_only"
        started = perf_counter()
        artifacts: list[dict[str, object]] = []
        errors: list[str] = []
        for index, prompt in enumerate(prompts):
            label = body.labels[index] if index < len(body.labels) else f"prompt_{index + 1}"
            try:
                if source_path is not None:
                    png = await image_client.generate_conditioned(
                        prompt,
                        index + 1,
                        source_image_path=str(source_path),
                    )
                else:
                    png = await image_client.generate(prompt, index + 1)
            except (QwenImageUnavailable, Exception) as exc:  # noqa: BLE001
                errors.append(f"#{index + 1}: {exc}")
                continue
            relative = f"sandbox/{batch_id}/candidate_{index + 1:02d}.png"
            image_path = out_root / f"candidate_{index + 1:02d}.png"
            image_path.write_bytes(png)
            try:
                from remote_worker.variation_stage2_images import (
                    fit_generated_subject_safe_margin,
                    normalize_generated_studio_background,
                )

                await asyncio.to_thread(normalize_generated_studio_background, image_path)
                await asyncio.to_thread(fit_generated_subject_safe_margin, image_path)
            except Exception:  # noqa: BLE001 - sandbox still returns raw image
                pass
            artifacts.append(
                {
                    "index": index + 1,
                    "label": label,
                    "prompt": prompt,
                    "url": f"/files/{relative}",
                }
            )
        if not artifacts:
            raise HTTPException(
                status_code=502,
                detail={"message": "image generation failed", "errors": errors[:4]},
            )
        return {
            "status": "ok",
            "batch_id": batch_id,
            "model": image_model,
            "mode": mode,
            "elapsed_sec": round(perf_counter() - started, 2),
            "artifacts": artifacts,
            "errors": errors,
        }

    @router.post("/api/v1/sandbox/interpret")
    async def sandbox_interpret(body: SandboxInterpretRequest) -> dict[str, object]:
        session_id = body.session_id
        if not session_id or studio_store.get_session(session_id) is None:
            session = studio_store.create_session(
                SessionCreateRequest(
                    title=f"IR Sandbox ({body.object_type})",
                    metadata={"sandbox": True, "object_type": body.object_type},
                )
            )
            session_id = session.session_id

        asset_id = body.asset_id or f"sandbox-asset-{body.object_type}"
        image_refs = [f"sandbox-ref-{i}" for i in range(max(0, int(body.image_ref_count or 0)))]
        payload: dict[str, Any] = {
            "asset_id": asset_id,
            "active_asset_id": asset_id,
            "object_type": body.object_type,
            "part_id": body.part_id,
            "part_label": body.part_label or body.part_id,
            "selected_part_label": body.part_label or body.part_id,
            "intent_text": body.intent_text,
            "text": body.text_detail or body.intent_text,
            "text_detail": body.text_detail,
            "drag": {"length": body.drag_length} if body.drag_length is not None else {},
            "smooth_strength": body.smooth_strength,
            "image_refs": image_refs,
            "image_ref_count": len(image_refs),
            "selection": {
                "type": "part" if body.part_id else "none",
                "part_id": body.part_id,
                "asset_id": asset_id,
            },
            **body.extra_payload,
        }
        event = UserEvent(
            type=body.event_type,
            event_id=f"sandbox_{uuid4().hex[:10]}",
            session_id=session_id,
            timestamp=datetime.now(UTC),
            payload=payload,
        )
        studio_store.save_event(event)
        result = interaction_service.interpret_sandbox(
            event,
            system_prompt=body.system_prompt,
            sync_vlm=body.sync_vlm,
            preview_only=body.preview_only,
        )
        result["session_id"] = session_id
        result["event"] = event.model_dump(mode="json")
        result["gate_draft"] = _gate_draft_from_interpretation(
            result.get("interpretation") if isinstance(result.get("interpretation"), dict) else None,
            object_type=body.object_type,
            part_id=body.part_id,
            part_label=body.part_label,
            intent_text=body.intent_text,
            event_type=body.event_type,
        )
        return result

    @router.post("/api/v1/sandbox/diverge")
    async def sandbox_diverge(body: SandboxDivergeRequest) -> dict[str, object]:
        return await _run_sandbox_diverge(
            body,
            semantic_primary=semantic_primary,
            semantic_fallback=semantic_fallback,
            kb_router=kb_router,
            on_progress=None,
        )

    @router.post("/api/v1/sandbox/diverge/stream")
    async def sandbox_diverge_stream(body: SandboxDivergeRequest) -> StreamingResponse:
        queue: asyncio.Queue[tuple[str, Any] | None] = asyncio.Queue()

        async def on_progress(event: dict[str, Any]) -> None:
            await queue.put(("phase", event))

        async def runner() -> None:
            try:
                result = await _run_sandbox_diverge(
                    body,
                    semantic_primary=semantic_primary,
                    semantic_fallback=semantic_fallback,
                    kb_router=kb_router,
                    on_progress=on_progress,
                )
                await queue.put(("done", result))
            except HTTPException as exc:
                await queue.put(("error", {"phase": "error", "detail": exc.detail}))
            except Exception as exc:  # noqa: BLE001 — surface to SSE client
                await queue.put(
                    ("error", {"phase": "error", "detail": f"{type(exc).__name__}: {exc}"})
                )
            finally:
                await queue.put(None)

        asyncio.create_task(runner())

        async def _generator() -> Any:
            while True:
                item = await queue.get()
                if item is None:
                    break
                event, data = item
                payload = json.dumps(data, ensure_ascii=False, default=str)
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

    return router


def _materialize_sandbox_source(
    files_root: Path,
    destination: Path,
    *,
    source_image_b64: str | None,
    source_image_ref: str | None,
) -> Path | None:
    if source_image_b64:
        raw = source_image_b64.strip()
        if "," in raw and raw.lower().startswith("data:"):
            raw = raw.split(",", 1)[1]
        try:
            payload = base64.b64decode(raw, validate=False)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"invalid source_image_b64: {exc}") from exc
        if len(payload) < 32:
            raise HTTPException(status_code=400, detail="source_image_b64 is empty")
        destination.write_bytes(payload)
        return destination
    ref = str(source_image_ref or "").strip()
    if not ref:
        return None
    if ref.startswith("/files/"):
        candidate = (files_root / ref.removeprefix("/files/")).resolve()
    else:
        candidate = Path(ref).expanduser().resolve()
    root = files_root.resolve()
    if root not in candidate.parents and candidate != root:
        raise HTTPException(status_code=400, detail="source_image_ref escapes files root")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="source_image_ref not found")
    destination.write_bytes(candidate.read_bytes())
    return destination


async def _run_sandbox_diverge(
    body: SandboxDivergeRequest,
    *,
    semantic_primary: Any | None,
    semantic_fallback: Any | None,
    kb_router: SemanticKnowledgeRouter,
    on_progress: Any | None,
) -> dict[str, object]:
    primary = semantic_primary
    fallback = semantic_fallback
    if primary is None and fallback is None:
        raise HTTPException(status_code=503, detail="semantic divergence generators are not configured")

    request = _build_request(body)
    route = _resolve_route(body, request, kb_router)

    await _emit(
        on_progress,
        {
            "phase": "evidence",
            "message": f"Collecting knowledge evidence ({route.mode})",
            "knowledge_route": route.model_dump(mode="json"),
            "model_plan": _model_plan(body, primary, fallback),
        },
    )

    if route.mode == "model_only" and not (
        route.use_wikidata or route.use_getty_aat or route.use_asknature
    ):
        evidence = KnowledgeEvidence(route=route)
    else:
        try:
            evidence = await asyncio.to_thread(kb_router.collect, request, route)
        except Exception as exc:  # noqa: BLE001
            await _emit(
                on_progress,
                {
                    "phase": "evidence",
                    "status": "failed",
                    "message": f"evidence failed: {type(exc).__name__}: {exc}",
                },
            )
            evidence = KnowledgeEvidence(
                route=KnowledgeRoute(mode="model_only", reasons=["knowledge_collection_failed"]),
                errors=[f"{type(exc).__name__}: {exc}"],
            )

    await _emit(
        on_progress,
        {
            "phase": "evidence",
            "status": "ok",
            "message": (
                f"Knowledge ready · wikidata={len(evidence.wikidata)} "
                f"getty={len(evidence.getty_aat)} asknature={len(evidence.asknature)}"
                + (f" · errors={evidence.errors[:2]}" if evidence.errors else "")
            ),
            "knowledge_route": evidence.route.model_dump(mode="json"),
            "evidence_counts": {
                "wikidata": len(evidence.wikidata),
                "getty_aat": len(evidence.getty_aat),
                "asknature": len(evidence.asknature),
                "errors": len(evidence.errors),
            },
            "evidence_errors": evidence.errors[:5],
        },
    )

    order = _generator_order(body, primary, fallback)
    if not order:
        raise HTTPException(status_code=503, detail="no configured semantic divergence generator")

    first = order[0]
    payload = first.build_payload(request, evidence, system_prompt=body.system_prompt)
    if body.preview_only:
        return {
            "preview_only": True,
            "provider": type(first).__name__,
            "model": getattr(first, "model", None),
            "model_plan": _model_plan(body, primary, fallback),
            "knowledge_route": evidence.route.model_dump(mode="json"),
            "request": request.model_dump(mode="json"),
            "prompts": {
                "system": payload["messages"][0]["content"],
                "user": payload["messages"][1]["content"],
            },
            "candidates": [],
        }

    started = perf_counter()
    used = first
    fallback_used = False
    error: str | None = None
    candidates: list[Any] = []

    for index, generator in enumerate(order):
        role = "primary" if index == 0 else "fallback"
        model_name = str(getattr(generator, "model", type(generator).__name__))
        phase_call = "primary_call" if index == 0 else "fallback_call"
        phase_ok = "primary_returned" if index == 0 else "fallback_returned"
        phase_fail = "primary_failed" if index == 0 else "fallback_failed"
        await _emit(
            on_progress,
            {
                "phase": phase_call,
                "provider": type(generator).__name__,
                "generator_model": model_name,
                "message": f"Calling {role} model {model_name} (LLM API)",
            },
        )
        try:
            candidates = await generator.generate(
                request, evidence, system_prompt=body.system_prompt
            )
            used = generator
            if index > 0:
                fallback_used = True
            await _emit(
                on_progress,
                {
                    "phase": phase_ok,
                    "provider": type(generator).__name__,
                    "generator_model": model_name,
                    "generated": len(candidates),
                    "accepted": len(candidates),
                    "message": f"{role} returned {len(candidates)} candidates",
                    "preview_labels": [
                        getattr(item, "display_label_zh", None)
                        or getattr(item, "label_en", None)
                        or getattr(item, "candidate_id", "")
                        for item in candidates[:12]
                    ],
                    "candidates": [item.model_dump(mode="json") for item in candidates],
                },
            )
            error = None
            break
        except (SemanticModelUnavailable, SemanticModelOutputError, Exception) as exc:
            error = f"{type(exc).__name__}: {exc}"
            await _emit(
                on_progress,
                {
                    "phase": phase_fail,
                    "provider": type(generator).__name__,
                    "generator_model": model_name,
                    "reason": error,
                    "message": f"{role} failed: {error}",
                },
            )
            if index == len(order) - 1:
                raise HTTPException(status_code=502, detail=error) from exc
            continue

    latency_ms = max(0, round((perf_counter() - started) * 1000))
    result = {
        "preview_only": False,
        "provider": type(used).__name__,
        "model": getattr(used, "model", None),
        "fallback_used": fallback_used,
        "latency_ms": latency_ms,
        "model_plan": _model_plan(body, primary, fallback),
        "knowledge_route": evidence.route.model_dump(mode="json"),
        "evidence_counts": {
            "wikidata": len(evidence.wikidata),
            "getty_aat": len(evidence.getty_aat),
            "asknature": len(evidence.asknature),
            "errors": evidence.errors[:5],
        },
        "request": request.model_dump(mode="json"),
        "prompts": {
            "system": payload["messages"][0]["content"],
            "user": payload["messages"][1]["content"],
        },
        "candidates": [item.model_dump(mode="json") for item in candidates],
        "error": error,
        "engine": "llm_api",
    }
    await _emit(
        on_progress,
        {
            "phase": "completed",
            "accepted": len(candidates),
            "generator_model": getattr(used, "model", None),
            "latency_ms": latency_ms,
            "message": f"Selected {len(candidates)} candidates · {latency_ms}ms",
        },
    )
    return result


def _build_request(body: SandboxDivergeRequest) -> SemanticDivergenceRequest:
    asset_id = body.asset_id or f"sandbox-asset-{body.object_type}"
    scope = (body.scope or "part").strip().lower()
    part_id = body.part_id
    object_identity = (body.object_type or "").strip() or "object"
    label = body.part_label or part_id or object_identity
    intent = body.user_semantic_intent.strip() or f"围绕{object_identity}探索具体造型方向"
    if object_identity.lower() not in intent.casefold():
        intent = f"主体是{object_identity}。{intent}"
    params = SemanticDivergenceParams(
        temperature=body.temperature,
        strictness=body.strictness,
        per_group_count=body.per_group_count,
    )
    hard_constraints = list(
        dict.fromkeys(
            [
                *body.hard_constraints,
                f"preserve_object_identity:{object_identity}",
                f"all candidates must remain about {object_identity}",
                *([f"gate:{body.gate_question}"] if body.gate_question else []),
            ]
        )
    )
    return SemanticDivergenceRequest(
        run_id=f"sandbox_run_{uuid4().hex[:10]}",
        decision_id=f"sandbox_decision_{uuid4().hex[:8]}",
        session_id=f"sandbox_sess_{uuid4().hex[:8]}",
        asset_id=asset_id,
        object_identity=object_identity,
        semantic_target=SemanticTarget(
            level=scope,
            part_id=part_id,
            label_zh=label,
            label_en=vernacular_en_label(label),
            semantic_role="modify",
        ),
        scope=scope,
        user_semantic_intent=intent,
        behavior_summary=body.behavior_summary.strip()
        or f"{scope}:{part_id or 'whole'} · {intent}",
        behavior_window_id=f"sandbox_bw_{uuid4().hex[:8]}",
        hard_constraints=hard_constraints,
        params=params,
    )


def _resolve_route(
    body: SandboxDivergeRequest,
    request: SemanticDivergenceRequest,
    kb_router: SemanticKnowledgeRouter,
) -> KnowledgeRoute:
    if body.knowledge_mode == "off":
        return KnowledgeRoute(mode="model_only", reasons=["sandbox_knowledge_off"])
    if body.knowledge_mode == "on":
        return KnowledgeRoute(
            mode="knowledge_augmented",
            use_wikidata=True if body.use_wikidata is None else body.use_wikidata,
            use_getty_aat=True if body.use_getty_aat is None else body.use_getty_aat,
            use_asknature=True if body.use_asknature is None else body.use_asknature,
            reasons=["sandbox_knowledge_forced"],
        )
    route = kb_router.choose_route(request)
    if body.use_wikidata is not None:
        route.use_wikidata = body.use_wikidata
    if body.use_getty_aat is not None:
        route.use_getty_aat = body.use_getty_aat
    if body.use_asknature is not None:
        route.use_asknature = body.use_asknature
    if route.use_wikidata or route.use_getty_aat or route.use_asknature:
        route.mode = "knowledge_augmented"
    else:
        route.mode = "model_only"
    return route


def _generator_order(
    body: SandboxDivergeRequest,
    primary: Any | None,
    fallback: Any | None,
) -> list[Any]:
    def ok(item: Any | None) -> bool:
        return item is not None and bool(getattr(item, "configured", False))

    if body.model_choice == "primary":
        return [primary] if ok(primary) else ([fallback] if ok(fallback) else [])
    if body.model_choice == "fallback":
        return [fallback] if ok(fallback) else ([primary] if ok(primary) else [])
    order: list[Any] = []
    if ok(primary):
        order.append(primary)
    if ok(fallback) and fallback is not primary:
        order.append(fallback)
    return order


def _model_plan(
    body: SandboxDivergeRequest,
    primary: Any | None,
    fallback: Any | None,
) -> dict[str, Any]:
    return {
        "choice": body.model_choice,
        "primary": {
            "provider": type(primary).__name__ if primary else None,
            "model": getattr(primary, "model", None),
            "configured": bool(primary and getattr(primary, "configured", False)),
        },
        "fallback": {
            "provider": type(fallback).__name__ if fallback else None,
            "model": getattr(fallback, "model", None),
            "configured": bool(fallback and getattr(fallback, "configured", False)),
        },
        "engine": "LLM chat/completions API → JSON candidates",
    }


async def _emit(callback: Any | None, event: dict[str, Any]) -> None:
    if callback is None:
        return
    try:
        await callback(event)
    except Exception:
        pass


def _gate_draft_from_interpretation(
    interpretation: dict[str, Any] | None,
    *,
    object_type: str,
    part_id: str | None,
    part_label: str | None,
    intent_text: str | None,
    event_type: str,
) -> dict[str, Any]:
    """Compress interpret output into fields the diverge sandbox can edit/run."""
    if not interpretation:
        scope = "part" if part_id else "whole"
        label = part_label or part_id or object_type
        return {
            "scope": scope,
            "part_id": part_id,
            "part_label": label,
            "gate_question": f"确认修改范围是「{label}」吗？",
            "user_semantic_intent": intent_text or "",
            "behavior_summary": event_type,
            "primary_intent": None,
            "confidence": None,
        }

    target = interpretation.get("target") if isinstance(interpretation.get("target"), dict) else {}
    semantic_targets = interpretation.get("semantic_targets") or []
    first_sem = semantic_targets[0] if isinstance(semantic_targets, list) and semantic_targets else {}
    resolved_part = (
        target.get("part_id")
        or (first_sem.get("part_id") if isinstance(first_sem, dict) else None)
        or part_id
    )
    label = (
        part_label
        or (first_sem.get("label_zh") if isinstance(first_sem, dict) else None)
        or resolved_part
        or object_type
    )
    scope = "part" if resolved_part else "whole"
    features = interpretation.get("features") if isinstance(interpretation.get("features"), dict) else {}
    design_ir = features.get("design_state_ir") if isinstance(features.get("design_state_ir"), dict) else {}
    scope_hint = design_ir.get("scope_hint")
    if isinstance(scope_hint, str) and scope_hint.strip():
        scope = scope_hint.strip().lower()
        if scope in {"material", "material_region"}:
            scope = "material_region"

    suggestions = interpretation.get("suggested_assistance") or []
    gate_question = None
    if isinstance(suggestions, list):
        for item in suggestions:
            if not isinstance(item, dict):
                continue
            text = item.get("prompt") or item.get("message") or item.get("text")
            if isinstance(text, str) and text.strip():
                gate_question = text.strip()
                break
    if not gate_question:
        gate_question = f"确认修改范围是「{label}」吗？"

    return {
        "scope": scope,
        "part_id": resolved_part,
        "part_label": label,
        "gate_question": gate_question,
        "user_semantic_intent": intent_text
        or str(features.get("intent_text") or features.get("text") or ""),
        "behavior_summary": f"{event_type} · {interpretation.get('primary_intent')}",
        "primary_intent": interpretation.get("primary_intent"),
        "confidence": interpretation.get("confidence"),
        "assistance_policy": interpretation.get("assistance_policy"),
    }
