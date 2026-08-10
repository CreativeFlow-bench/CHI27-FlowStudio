"""Provider-neutral types for the external model runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ModelStage(str, Enum):
    INTENT = "intent"
    PERCEPTION = "perception"
    REREPRESENTATION = "rerepresentation"
    SEMANTIC_DIVERGENCE = "semantic_divergence"
    PROMPT_COMPOSITION = "prompt_composition"
    IMAGE = "image"


@dataclass(frozen=True, slots=True)
class ModelRoute:
    primary_model: str
    fallback_model: str | None
