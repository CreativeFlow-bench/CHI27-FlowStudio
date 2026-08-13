"""EventNormalizer: bounded, aggregated normalized events for the encoder.

Rules (strategy doc 6.2):
- viewport orbit/zoom/pan/dwell events are aggregated into counts/sums, never
  sent frame-by-frame to the model;
- drawing/brush keep artifact URL + bbox + projection + statistics, never raw
  unbounded coordinates or base64 payloads;
- drag keeps the bounded 3D vector + influence radius;
- text is kept (truncated), image/model references are kept as bounded URL
  lists; everything dropped is counted in ``dropped_summary``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models import UserEvent


@dataclass
class NormalizedInteraction:
    event_id: str
    type: str
    target: dict[str, Any] = field(default_factory=dict)
    text: str | None = None
    artifact: dict[str, Any] | None = None
    vector: dict[str, Any] | None = None
    stats: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedEventBundle:
    session_id: str
    episode_id: str | None = None
    event_count: int = 0
    viewport: dict[str, Any] = field(default_factory=dict)
    interactions: list[NormalizedInteraction] = field(default_factory=list)
    text_segments: list[str] = field(default_factory=list)
    image_refs: list[str] = field(default_factory=list)
    model_refs: list[str] = field(default_factory=list)
    target_hints: list[str] = field(default_factory=list)
    dropped_summary: dict[str, int] = field(default_factory=dict)

    def to_bounded_json(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "episode_id": self.episode_id,
            "event_count": self.event_count,
            "viewport": self.viewport,
            "interactions": [
                {
                    "event_id": item.event_id,
                    "type": item.type,
                    "target": item.target,
                    "text": item.text,
                    "artifact": item.artifact,
                    "vector": item.vector,
                    "stats": item.stats,
                }
                for item in self.interactions
            ],
            "text_segments": self.text_segments,
            "image_refs": self.image_refs,
            "model_refs": self.model_refs,
            "target_hints": self.target_hints,
            "dropped_summary": self.dropped_summary,
        }


_VIEWPORT_TYPES = {
    "orbit",
    "orbit_end",
    "orbit_start",
    "zoom",
    "zoom_end",
    "pan",
    "pan_end",
    "camera_observation_ended",
    "viewport_observation",
    "focus_observation_ended",
}
_SELECTION_TYPES = {
    "part_select",
    "part_hover",
    "hover_focus",
    "semantic_hover_ended",
    "selection_ended",
}
_DRAWING_TYPES = {
    "brush",
    "brush_end",
    "annotation",
    "annotation_end",
    "stroke_ended",
    "drawing_ended",
}
_DRAG_TYPES = {"drag", "drag_end"}
_SMOOTH_TYPES = {"smooth", "smooth_end"}
_ADD_TYPES = {"add", "primitive_add", "primitive_added"}
_TEXT_TYPES = {"text", "text_input", "text_committed"}
_REF_TYPES = {"image_ref", "model_ref", "reference_image", "reference_model"}


class EventNormalizer:
    MAX_INTERACTIONS = 40
    MAX_TEXT_SEGMENTS = 8
    MAX_TEXT_CHARS = 400
    MAX_IMAGE_REFS = 4
    MAX_MODEL_REFS = 4
    MAX_TARGET_HINTS = 8
    MAX_B64_BYTES = 2_000_000
    MAX_COORD_POINTS = 512

    def normalize(
        self,
        events: list[UserEvent],
        *,
        session_context: dict[str, Any] | None = None,
    ) -> NormalizedEventBundle:
        session_context = session_context or {}
        bundle = NormalizedEventBundle(
            session_id=session_context.get("session_id") or (events[0].session_id if events else ""),
            episode_id=session_context.get("episode_id"),
            event_count=len(events),
        )
        viewport: dict[str, Any] = {
            "orbit_count": 0,
            "zoom_count": 0,
            "pan_count": 0,
            "dwell_ms_total": 0,
            "dwell_ms_max": 0,
        }
        for event in events[: self.MAX_INTERACTIONS * 3]:
            etype = event.type
            payload = event.payload or {}
            # Viewport screenshots and brush masks are source conditions, even
            # when they arrive attached to a sculpt/annotation event rather
            # than as a standalone ``image_ref`` event.
            screenshot_ref = payload.get("source_image_ref") or payload.get("viewport_screenshot_url")
            if screenshot_ref and len(bundle.image_refs) < self.MAX_IMAGE_REFS:
                ref = str(screenshot_ref).strip()
                if ref and ref not in bundle.image_refs:
                    bundle.image_refs.append(ref)
            model_ref = payload.get("source_model_ref") or payload.get("model_url")
            if model_ref and len(bundle.model_refs) < self.MAX_MODEL_REFS:
                ref = str(model_ref).strip()
                if ref and ref not in bundle.model_refs:
                    bundle.model_refs.append(ref)
            mask_ref = payload.get("target_mask_ref") or payload.get("brush_mask_url") or payload.get("mask_url")
            if mask_ref and len(bundle.interactions) < self.MAX_INTERACTIONS:
                bundle.target_hints.append(f"mask:{str(mask_ref).strip()}")
            if etype in _VIEWPORT_TYPES:
                if "orbit" in etype or etype == "viewport_observation":
                    viewport["orbit_count"] += 1
                elif "zoom" in etype:
                    viewport["zoom_count"] += 1
                elif "pan" in etype:
                    viewport["pan_count"] += 1
                dwell = int(payload.get("dwell_ms") or payload.get("duration_ms") or 0)
                if dwell > 0:
                    viewport["dwell_ms_total"] += dwell
                    viewport["dwell_ms_max"] = max(viewport["dwell_ms_max"], dwell)
                continue
            if etype in _SELECTION_TYPES:
                target: dict[str, Any] = {}
                for key in ("part_id", "label", "asset_id", "region", "scope"):
                    value = payload.get(key)
                    if value is not None:
                        target[key] = value
                if target.get("part_id"):
                    bundle.target_hints.append(f"part:{target['part_id']}")
                elif target.get("label"):
                    bundle.target_hints.append(f"label:{target['label']}")
                bundle.interactions.append(
                    NormalizedInteraction(
                        event_id=event.event_id,
                        type=etype,
                        target=target,
                        stats={
                            "dwell_ms": int(payload.get("dwell_ms") or 0),
                            "selection_type": payload.get("selection_type"),
                        },
                    )
                )
                continue
            if etype in _DRAWING_TYPES:
                bundle.interactions.append(
                    NormalizedInteraction(
                        event_id=event.event_id,
                        type=etype,
                        target={
                            key: payload.get(key)
                            for key in ("asset_id", "part_id", "label")
                            if payload.get(key) is not None
                        },
                        artifact=self._bounded_artifact(payload, bundle),
                        stats={
                            "bbox": self._bounded_bbox(payload.get("bbox")),
                            "projection": self._bounded_projection(payload.get("projection")),
                            "mask_stats": self._mask_stats(payload.get("mask") or payload.get("brush")),
                            "stroke_count": int(payload.get("stroke_count") or 0),
                            "point_count": self._point_count(payload),
                        },
                    )
                )
                continue
            if etype in _DRAG_TYPES:
                start = payload.get("start")
                end = payload.get("end")
                vector = None
                if isinstance(start, list) and isinstance(end, list):
                    vector = {
                        "start": [float(value) for value in start[:3]],
                        "end": [float(value) for value in end[:3]],
                        "space": payload.get("space") or "world",
                        "influence_radius": float(payload.get("influence_radius") or 0.25),
                    }
                bundle.interactions.append(
                    NormalizedInteraction(
                        event_id=event.event_id,
                        type=etype,
                        target={
                            key: payload.get(key)
                            for key in ("part_id", "label", "asset_id")
                            if payload.get(key) is not None
                        },
                        vector=vector,
                        stats={"drag_length": self._drag_length(start, end)},
                    )
                )
                continue
            if etype in _SMOOTH_TYPES:
                bundle.interactions.append(
                    NormalizedInteraction(
                        event_id=event.event_id,
                        type=etype,
                        target={
                            key: payload.get(key)
                            for key in ("part_id", "region", "asset_id")
                            if payload.get(key) is not None
                        },
                        stats={
                            "strength": float(payload.get("strength") or 0),
                            "preserve_boundary": bool(payload.get("preserve_boundary")),
                            "radius": float(payload.get("radius") or 0),
                        },
                    )
                )
                continue
            if etype in _ADD_TYPES:
                bundle.interactions.append(
                    NormalizedInteraction(
                        event_id=event.event_id,
                        type=etype,
                        stats={
                            "primitive": payload.get("primitive")
                            or payload.get("type")
                            or "unknown",
                            "transform": self._bounded_transform(payload.get("transform")),
                        },
                    )
                )
                continue
            if etype in _TEXT_TYPES:
                text = str(payload.get("text") or payload.get("content") or "").strip()
                if text and len(bundle.text_segments) < self.MAX_TEXT_SEGMENTS:
                    bundle.text_segments.append(text[: self.MAX_TEXT_CHARS])
                continue
            if etype in _REF_TYPES:
                ref = payload.get("url") or payload.get("artifact_url") or payload.get("ref")
                if ref:
                    if "image" in etype or etype == "reference_image":
                        if len(bundle.image_refs) < self.MAX_IMAGE_REFS:
                            bundle.image_refs.append(str(ref))
                    else:
                        if len(bundle.model_refs) < self.MAX_MODEL_REFS:
                            bundle.model_refs.append(str(ref))
                continue
            bundle.dropped_summary[f"dropped_{etype}"] = (
                bundle.dropped_summary.get(f"dropped_{etype}", 0) + 1
            )
        bundle.interactions = bundle.interactions[: self.MAX_INTERACTIONS]
        bundle.target_hints = bundle.target_hints[: self.MAX_TARGET_HINTS]
        bundle.viewport = viewport
        return bundle

    def _bounded_artifact(
        self, payload: dict[str, Any], bundle: NormalizedEventBundle
    ) -> dict[str, Any] | None:
        url = payload.get("artifact_url") or payload.get("url")
        data_url = payload.get("data_url") or payload.get("base64")
        if isinstance(data_url, str) and data_url:
            bundle.dropped_summary["dropped_base64_bytes"] = (
                bundle.dropped_summary.get("dropped_base64_bytes", 0) + len(data_url)
            )
        if isinstance(data_url, str) and len(data_url) > self.MAX_B64_BYTES:
            bundle.dropped_summary["dropped_oversized_base64"] = (
                bundle.dropped_summary.get("dropped_oversized_base64", 0) + 1
            )
        if url:
            return {"url": str(url), "artifact_type": payload.get("artifact_type") or payload.get("type")}
        return None

    def _bounded_bbox(self, bbox: Any) -> dict[str, Any] | None:
        if not isinstance(bbox, dict):
            return None
        out: dict[str, Any] = {}
        for key, value in bbox.items():
            if isinstance(value, list) and len(value) > 12:
                out[key] = value[:12]
                continue
            out[key] = value
        return out

    def _bounded_projection(self, projection: Any) -> dict[str, Any] | None:
        if not isinstance(projection, dict):
            return None
        summary: dict[str, Any] = {}
        for key, value in projection.items():
            if isinstance(value, list):
                summary[key] = f"points:{len(value)}"
            else:
                summary[key] = value
        return summary

    def _mask_stats(self, mask: Any) -> dict[str, Any] | None:
        if not isinstance(mask, dict):
            return None
        return {
            key: value
            for key, value in mask.items()
            if key in {"width", "height", "channels", "area_ratio", "bbox", "count"}
        }

    def _point_count(self, payload: dict[str, Any]) -> int:
        total = 0
        for key in ("points", "strokes", "vertices", "coordinates"):
            value = payload.get(key)
            if isinstance(value, list):
                total += len(value)
        return total

    def _bounded_transform(self, transform: Any) -> dict[str, Any] | None:
        if not isinstance(transform, dict):
            return None
        return {
            key: value
            for key, value in transform.items()
            if key in {"position", "rotation", "scale", "space"}
        }

    @staticmethod
    def _drag_length(start: Any, end: Any) -> float:
        if not isinstance(start, list) or not isinstance(end, list):
            return 0.0
        try:
            return round(
                sum((float(a) - float(b)) ** 2 for a, b in zip(start[:3], end[:3])) ** 0.5,
                4,
            )
        except (TypeError, ValueError):
            return 0.0
