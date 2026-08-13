"""Encoding stage: event normalization + Qwen IntentIR encoder + rule fallback."""

from app.services.encoding.event_normalizer import EventNormalizer, NormalizedEventBundle
from app.services.encoding.four_stage_encoding import FourStageEncodingService

__all__ = ["EventNormalizer", "NormalizedEventBundle", "FourStageEncodingService"]
