"""FourStageEncodingService: normalizer + Qwen encoder + rule fallback.

Qwen schema-invalid output fails the stage (no fabricated IR). Model/transport
unavailability falls back to the deterministic rule encoder, which is clearly
marked in ``IntentIR.provenance``.
"""

from __future__ import annotations

import logging
import re
from uuid import uuid4

from app.models import (
    IntentCore,
    IntentIR,
    IntentObservations,
    IntentProvenance,
    IntentTarget,
    FourStageRun,
    SourceContext,
    is_concrete_object_type,
)
from app.services.encoding.event_normalizer import (
    EventNormalizer,
    NormalizedEventBundle,
)
from app.services.encoding.qwen_intent_encoder import (
    QwenEncodingError,
    QwenIntentEncoder,
    QwenUnavailable,
)

logger = logging.getLogger("flowstudio.encoding")


class RuleIntentEncoder:
    """Deterministic rule fallback; always marked in provenance."""

    def __init__(self, normalizer: EventNormalizer | None = None) -> None:
        self.normalizer = normalizer or EventNormalizer()

    async def encode(
        self,
        run: FourStageRun,
        bundle: NormalizedEventBundle | None = None,
    ) -> IntentIR:
        bundle = bundle or self._bundle(run)
        return self._rule_ir(run, bundle)

    def _bundle(self, run: FourStageRun) -> NormalizedEventBundle:
        return self.normalizer.normalize(
            run.events,
            session_context={"session_id": run.session_id, "episode_id": run.episode_id},
        )

    def _rule_ir(self, run: FourStageRun, bundle: NormalizedEventBundle) -> IntentIR:
        text = (bundle.text_segments[-1] if bundle.text_segments else None) or ""
        part_hint = next(
            (hint[5:] for hint in bundle.target_hints if hint.startswith("part:")),
            None,
        )
        text_part = infer_text_part(text)
        if not part_hint:
            part_hint = text_part
        has_drawing = any(item.type in {"brush", "brush_end", "annotation", "annotation_end"} for item in bundle.interactions)
        has_drag = any(item.type in {"drag", "drag_end"} for item in bundle.interactions)
        has_brush = any(item.type in {"brush", "brush_end"} for item in bundle.interactions)
        orbit_only = (
            not text
            and not part_hint
            and not has_drawing
            and not has_drag
            and not bundle.interactions
        )

        if orbit_only:
            intent = IntentCore(
                operation="observe",
                scope="whole",
                goal=None,
                constraints=[],
                preferred_axes=[],
            )
            confidence, ambiguity = 0.45, 0.55
        else:
            lowered = text.lower()
            material_change = any(
                marker in lowered
                for marker in (
                    "material", "surface", "texture", "color",
                    "材质", "表面", "纹理", "颜色",
                )
            )
            scope = (
                "material_region"
                if material_change and (part_hint or has_drawing)
                else "material"
                if material_change
                else "part"
                if part_hint or has_drawing
                else "whole"
            )
            constraints: list[str] = []
            for marker in ("preserve", "keep", "protect", "不要动", "保留", "保持"):
                if marker in lowered:
                    constraints.append("preserve non-target region")
                    break
            if has_drag:
                constraints.append("respect drag influence radius")
            intent = IntentCore(
                operation="explore_variations",
                scope=scope,
                goal=text[:120] or None,
                constraints=constraints,
                preferred_axes=["Aesthetic", "Structural"],
            )
            confidence = 0.72 if text else 0.58
            ambiguity = 0.28 if text else 0.42

        return IntentIR(
            ir_id=f"ir_{uuid4().hex[:10]}",
            run_id=run.run_id,
            session_id=run.session_id,
            episode_id=run.episode_id,
            source_event_ids=list(run.source_event_ids),
            target=IntentTarget(
                asset_id=bundle.interactions[0].target.get("asset_id")
                if bundle.interactions
                else None,
                part_id=part_hint,
                object_type=run.source_context.object_type if run.source_context else None,
            ),
            observations=IntentObservations(
                viewport=dict(bundle.viewport),
                interaction_summary={
                    "interaction_count": len(bundle.interactions),
                    "text_segments": len(bundle.text_segments),
                    "image_refs": len(bundle.image_refs),
                    "model_refs": len(bundle.model_refs),
                    "has_text": bool(text),
                    "has_brush": has_brush,
                    "has_drag": has_drag,
                    "has_drawing": has_drawing,
                    "selection_type": "part" if part_hint else "none",
                },
                text=text[:400] or None,
                image_refs=list(bundle.image_refs),
                model_refs=list(bundle.model_refs),
            ),
            intent=intent,
            confidence=confidence,
            ambiguity=ambiguity,
            provenance=IntentProvenance(
                encoder="rule-fallback",
                encoder_version="rule-intent-ir-v1",
                prompt_version="intent-ir-v1",
                fallback_used=True,
            ),
        )


_KNOWN_TEXT_PARTS = (
    "handle", "hat", "nose", "lid", "grip", "nozzle", "wheel", "arm", "leg",
    "button", "rim", "spout", "base", "cap", "strap", "scarf", "把手", "帽子", "鼻子", "盖子",
    "握把", "喷嘴", "车轮", "手臂", "腿", "按钮", "边缘", "底座", "围巾",
)


def infer_text_parts(text: str) -> list[str]:
    lowered = text.lower()
    result: list[str] = []
    for part in _KNOWN_TEXT_PARTS:
        if (part.isascii() and re.search(rf"\b{re.escape(part)}s?\b", lowered)) or (
            not part.isascii() and part in lowered
        ):
            result.append(part)
    return result


def infer_text_part(text: str) -> str | None:
    """Small deterministic fallback for Gate scope when the VLM is offline."""
    parts = infer_text_parts(text)
    if parts:
        return parts[0]
    lowered = text.lower()
    if re.search(r"\b(part|component|connection|joint)\b", lowered) or any(
        marker in text for marker in ("部件", "零件", "连接", "插接")
    ):
        return "当前部件"
    return None


class FourStageEncodingService:
    def __init__(
        self,
        *,
        normalizer: EventNormalizer,
        qwen_encoder: QwenIntentEncoder,
        rule_encoder: RuleIntentEncoder,
        asset_lookup=None,
    ) -> None:
        self.normalizer = normalizer
        self.qwen_encoder = qwen_encoder
        self.rule_encoder = rule_encoder
        self.asset_lookup = asset_lookup

    @property
    def gateway(self):
        """The TextModelGateway used by the V2 encoder (None for V1 / local-only)."""
        return getattr(self.qwen_encoder, "gateway", None)

    async def encode(self, run: FourStageRun) -> IntentIR:
        bundle = self.normalizer.normalize(
            run.events,
            session_context={"session_id": run.session_id, "episode_id": run.episode_id},
        )
        if not self.qwen_encoder.configured:
            logger.info("encoding qwen disabled; rule fallback run=%s", run.run_id)
            ir = await self.rule_encoder.encode(run, bundle)
            self._attach_asset_context(run, ir)
            return ir
        try:
            ir = await self.qwen_encoder.encode(bundle)
            self._normalize_ir_ids(run, ir)
            self._attach_asset_context(run, ir)
            if ir.provenance.fallback_used:
                logger.info("encoding qwen marked fallback run=%s", run.run_id)
            return ir
        except QwenUnavailable as exc:
            logger.warning("encoding qwen unavailable; rule fallback run=%s: %s", run.run_id, exc)
            ir = await self.rule_encoder.encode(run, bundle)
            self._attach_asset_context(run, ir)
            return ir
        except QwenEncodingError:
            # Invalid model JSON: do NOT fabricate an IR; fail the stage.
            raise

    async def generate_phenomenon(
        self, run: FourStageRun, intent_ir: IntentIR | None = None
    ) -> str | None:
        """Generate a natural-language description of the current design phenomenon.

        Calls the fast text model (PHENOMENON stage) to produce a short Chinese
        description of what the user is doing / trying to achieve, based on the
        interaction bundle. Falls back gracefully when the model is unavailable.

        Returns None on failure so callers never break on model unavailability.
        """
        gateway = self.gateway
        if gateway is None:
            return None
        bundle = self.normalizer.normalize(
            run.events,
            session_context={"session_id": run.session_id, "episode_id": run.episode_id},
        )
        goal_text = intent_ir.intent.goal if intent_ir else None
        text_segments = bundle.text_segments or []
        user_text = text_segments[-1] if text_segments else goal_text or ""
        object_type = (intent_ir.target.object_type if intent_ir else None) or "当前对象"
        scope = (intent_ir.intent.scope if intent_ir else None) or "整体"
        operation = (intent_ir.intent.operation if intent_ir else None) or "调整"
        system_msg = (
            "You are FlowStudio's perception narrator. "
            "Output ONLY one short Chinese sentence (≤ 60 chars) describing what the user "
            "is currently doing or trying to achieve based on the context. "
            "Be concrete and observe-based, not prescriptive."
        )
        user_msg = (
            f"Object: {object_type}\n"
            f"Scope: {scope}\n"
            f"Operation: {operation}\n"
            f"User text: {user_text or '(none)'}\n"
            f"Interaction count: {len(bundle.interactions)}\n"
            f"Tool types: {list({i.type for i in bundle.interactions})}\n"
            "Describe what the user is doing right now in one short Chinese sentence:"
        )
        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

        async def _parse(raw: dict[str, Any]) -> str:
            # Accept raw string content directly
            choices = raw.get("choices")
            if isinstance(choices, list) and choices:
                msg = choices[0].get("message", {})
                content = msg.get("content", "")
                if isinstance(content, str):
                    return content.strip()[:120]
            return raw.get("phenomenon", "")[:120] if isinstance(raw, dict) else str(raw)[:120]

        try:
            from app.services.model_api.types import ModelStage

            raw = await gateway.transport.chat_json(
                model=gateway.profile.fast_text_model,
                messages=messages,
                stage=ModelStage.PHENOMENON,
                temperature=0.3,
                max_tokens=80,
            )
            return await _parse(raw)
        except Exception:
            # Never surface model errors to the caller — phenomenon is best-effort.
            return None

    def _normalize_ir_ids(self, run: FourStageRun, ir: IntentIR) -> None:
        """Enforce structural ids on model output (model may echo schema placeholders)."""
        if not ir.ir_id or ir.ir_id == "generated":
            ir.ir_id = f"ir_{uuid4().hex[:10]}"
        ir.run_id = run.run_id
        ir.session_id = run.session_id
        if run.episode_id:
            ir.episode_id = run.episode_id
        if not ir.source_event_ids:
            ir.source_event_ids = list(run.source_event_ids)

    def _attach_asset_context(self, run: FourStageRun, ir: IntentIR) -> None:
        asset_id = None
        for event in run.events:
            candidate = (event.payload or {}).get("asset_id")
            if candidate:
                asset_id = str(candidate)
                break
        asset_id = ir.target.asset_id or asset_id
        if run.source_context is not None:
            asset_id = run.source_context.asset_id
        context: dict[str, object] = {}
        if asset_id and self.asset_lookup is not None:
            try:
                context = self.asset_lookup(asset_id) or {}
            except Exception:  # noqa: BLE001 - asset lookup must never break encoding
                logger.warning("asset lookup failed asset_id=%s", asset_id)
        if asset_id and not ir.target.asset_id:
            ir.target.asset_id = asset_id
        if context.get("object_type") and not ir.target.object_type:
            ir.target.object_type = str(context["object_type"])
        if not is_concrete_object_type(ir.target.object_type):
            # Keep the IR honest; generation will stop with a structured error.
            ir.target.object_type = None
        self._attach_source_context(run, ir, context)

    def _attach_source_context(
        self,
        run: FourStageRun,
        ir: IntentIR,
        asset_context: dict[str, object],
    ) -> None:
        if run.source_context is not None:
            if ir.target.part_id and not run.source_context.target_part_id:
                run.source_context.target_part_id = ir.target.part_id
            # Keep existing identity, but backfill a missing viewport image from events.
            if not run.source_context.source_image_ref:
                for event in run.events:
                    payload = event.payload or {}
                    image_ref = str(
                        payload.get("source_image_ref")
                        or payload.get("viewport_screenshot_url")
                        or payload.get("image_url")
                        or ""
                    ).strip()
                    if image_ref:
                        run.source_context.source_image_ref = image_ref
                        break
                if not run.source_context.source_image_ref:
                    thumb = _context_text(asset_context, "thumbnail_url")
                    if thumb:
                        run.source_context.source_image_ref = thumb
            return
        object_type = ir.target.object_type
        asset_id = ir.target.asset_id
        if not asset_id or not is_concrete_object_type(object_type):
            return

        image_ref: str | None = None
        model_ref: str | None = None
        mask_ref: str | None = None
        version_id: str | None = None
        camera_ref: str | None = None
        for event in run.events:
            payload = event.payload or {}
            image_ref = image_ref or str(
                payload.get("source_image_ref")
                or payload.get("viewport_screenshot_url")
                or payload.get("image_url")
                or ""
            ).strip() or None
            model_ref = model_ref or str(
                payload.get("source_model_ref") or payload.get("model_url") or ""
            ).strip() or None
            mask_ref = mask_ref or str(
                payload.get("target_mask_ref")
                or payload.get("brush_mask_url")
                or payload.get("mask_url")
                or ""
            ).strip() or None
            version_ref = payload.get("version_id")
            if version_ref and version_id is None:
                version_id = str(version_ref)
            camera = payload.get("camera_ref") or payload.get("viewport_screenshot_artifact_id")
            if camera and camera_ref is None:
                camera_ref = str(camera)
        image_ref = image_ref or _context_text(asset_context, "thumbnail_url")
        model_ref = model_ref or _context_text(asset_context, "mesh_url") or _context_text(asset_context, "obj_url")
        run.source_context = SourceContext(
            asset_id=str(asset_id),
            object_type=str(object_type),
            version_id=version_id,
            source_image_ref=image_ref,
            source_model_ref=model_ref,
            target_part_id=ir.target.part_id,
            target_mask_ref=mask_ref,
            camera_ref=camera_ref,
        )


def _context_text(context: dict[str, object], key: str) -> str | None:
    value = context.get(key)
    return str(value).strip() if value else None
