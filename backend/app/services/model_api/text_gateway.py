"""Stage-aware structured-output gateway for external text models."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from app.services.model_api.config import ModelApiProfile
from app.services.model_api.transport import (
    ModelTransportUnavailable,
    OpenAICompatibleTransport,
)
from app.services.model_api.types import ModelStage

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class StructuredModelResult(Generic[T]):
    value: T
    model: str
    provider: str
    fallback_used: bool


class TextModelGateway:
    def __init__(
        self,
        profile: ModelApiProfile,
        *,
        transport: OpenAICompatibleTransport | Any | None = None,
    ) -> None:
        self.profile = profile
        self.transport = transport or OpenAICompatibleTransport(
            api_base=profile.api_base,
            api_key=profile.api_key,
            timeout_sec=profile.timeout_sec,
            max_retries=profile.max_retries,
        )

    async def complete_json(
        self,
        stage: ModelStage,
        messages: list[dict[str, Any]],
        *,
        validator: Callable[[dict[str, Any]], T],
        repair_instruction: str | None = None,
        temperature: float = 0,
        max_tokens: int = 3600,
        models: list[str] | None = None,
        timeout_sec: float | None = None,
        max_retries: int | None = None,
        allow_repair: bool = True,
    ) -> StructuredModelResult[T]:
        route = self.profile.route_for(stage)
        if models is not None:
            ordered = [model for model in models if model]
        else:
            ordered = [route.primary_model]
            if route.fallback_model:
                ordered.append(route.fallback_model)
        last_transport_error: ModelTransportUnavailable | None = None
        for index, model in enumerate(ordered):
            try:
                raw = await self.transport.chat_json(
                    model=model,
                    messages=messages,
                    stage=stage,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout_sec=timeout_sec,
                    max_retries=max_retries,
                )
                try:
                    value = validator(raw)
                except Exception as validation_error:
                    if repair_instruction is None or not allow_repair:
                        raise
                    repair_messages = [
                        *messages,
                        {
                            "role": "assistant",
                            "content": json.dumps(raw, ensure_ascii=False),
                        },
                        {
                            "role": "user",
                            "content": (
                                f"{repair_instruction}\nValidation error: "
                                f"{validation_error}"
                            ),
                        },
                    ]
                    repaired = await self.transport.chat_json(
                        model=model,
                        messages=repair_messages,
                        stage=stage,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout_sec=timeout_sec,
                        max_retries=max_retries,
                    )
                    value = validator(repaired)
                return StructuredModelResult(
                    value=value,
                    model=model,
                    provider=self._provider_for(model),
                    fallback_used=index > 0,
                )
            except ModelTransportUnavailable as exc:
                last_transport_error = exc
        raise last_transport_error or ModelTransportUnavailable(
            f"no model is available for stage {stage.value}"
        )

    @staticmethod
    def _provider_for(model: str) -> str:
        return "gemini" if model.lower().startswith("gemini") else "openai"
