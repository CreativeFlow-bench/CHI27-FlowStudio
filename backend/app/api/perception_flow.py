"""Shared Perception interpret → publish → optional async VLM refine."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.models import InteractionInterpretation, UserEvent
from app.services.intent.interaction_understanding import InteractionUnderstandingService

logger = logging.getLogger("flowstudio.api.perception")

PublishPerception = Callable[..., Awaitable[None]]


async def refine_perception_with_vlm(
    *,
    session_id: str,
    event: UserEvent,
    base: InteractionInterpretation,
    interaction_service: InteractionUnderstandingService,
    publish_perception: PublishPerception,
) -> None:
    try:
        refined = await asyncio.to_thread(
            interaction_service.refine_with_vlm,
            event,
            base,
        )
        await publish_perception(session_id, refined)
    except Exception:
        logger.exception(
            "VLM perception refine failed session_id=%s interpretation_id=%s",
            session_id,
            base.interpretation_id,
        )


def schedule_vlm_perception_refine(
    *,
    session_id: str,
    event: UserEvent,
    base: InteractionInterpretation,
    interaction_service: InteractionUnderstandingService,
    publish_perception: PublishPerception,
) -> None:
    if not base.predictor_metadata.get("vlm_pending"):
        return
    if not interaction_service.vlm_configured():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("No running loop; skipped VLM refine for %s", base.interpretation_id)
        return
    loop.create_task(
        refine_perception_with_vlm(
            session_id=session_id,
            event=event,
            base=base,
            interaction_service=interaction_service,
            publish_perception=publish_perception,
        )
    )


async def interpret_and_publish(
    *,
    session_id: str,
    event: UserEvent,
    interaction_service: InteractionUnderstandingService,
    publish_perception: PublishPerception,
    defer_vlm: bool = True,
) -> InteractionInterpretation:
    """Rule(+IR) first when VLM configured; schedule async perception_updated overwrite."""
    interpretation = interaction_service.interpret_event(event, defer_vlm=defer_vlm)
    await publish_perception(session_id, interpretation)
    schedule_vlm_perception_refine(
        session_id=session_id,
        event=event,
        base=interpretation,
        interaction_service=interaction_service,
        publish_perception=publish_perception,
    )
    return interpretation
