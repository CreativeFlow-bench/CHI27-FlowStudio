"""Perception payload builders (refactor plan P2)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.models import InteractionInterpretation, SessionUpdateRequest, UserEvent, now_utc
from app.services.intent.design_state_ir import silent_ir_prior
from app.services.storage.studio_store import InMemoryStudioStore

_STORE: Any = None
_WS: Any = None
_REQUIRE_SESSION: Any = None


def configure_perception(*, studio_store: Any, websocket_manager: Any, require_session: Any) -> None:
    global _STORE, _WS, _REQUIRE_SESSION
    _STORE = studio_store
    _WS = websocket_manager
    _REQUIRE_SESSION = require_session


def _perception_payload(interpretation: InteractionInterpretation) -> dict[str, object]:
    return {
        "perception_id": interpretation.interpretation_id,
        "summary": interpretation.primary_intent.value,
        "behavior_label": interpretation.action_type,
        "confidence": interpretation.confidence,
        "ambiguity": interpretation.ambiguity,
        "evidence": interpretation.evidence,
        "evidence_summary": _compact_evidence_summary(interpretation),
        "features": interpretation.features,
        "created_at": interpretation.created_at.isoformat(),
    }


def _live_signals_payload(session: SessionRecord) -> dict[str, object]:
    signals = session.metadata.get("live_signals")
    silent_ir = session.metadata.get("silent_ir")
    return {
        "session_id": session.session_id,
        "live_signals": signals if isinstance(signals, dict) else {},
        "silent_ir": silent_ir if isinstance(silent_ir, dict) else None,
        "updated_at": session.metadata.get("live_signals_updated_at"),
        "source": session.metadata.get("live_signals_source"),
    }


def _compact_evidence_summary(interpretation: InteractionInterpretation) -> list[dict[str, object]]:
    features = interpretation.features if isinstance(interpretation.features, dict) else {}
    signals = features.get("signals") if isinstance(features.get("signals"), dict) else {}
    geometric = signals.get("geometric") if isinstance(signals.get("geometric"), dict) else {}
    semantic = signals.get("semantic") if isinstance(signals.get("semantic"), dict) else {}
    visual = signals.get("visual_context") if isinstance(signals.get("visual_context"), dict) else {}
    interaction = signals.get("interaction") if isinstance(signals.get("interaction"), dict) else {}
    rows: list[dict[str, object]] = [
        {
            "label": "intent",
            "value": interpretation.primary_intent.value,
            "source": "planner",
            "confidence": interpretation.confidence,
        }
    ]

    event_type = interaction.get("event_type") or features.get("event_type")
    if event_type:
        rows.append({"label": "behavior", "value": event_type, "source": "interaction"})
    part_label = semantic.get("part_label") or semantic.get("part_id")
    if part_label:
        rows.append({"label": "target", "value": part_label, "source": "semantic"})
    object_type = semantic.get("object_type")
    if object_type:
        rows.append({"label": "object", "value": object_type, "source": "semantic"})

    evidence_fields = [
        ("focus", "dwell_ms", geometric.get("dwell_ms"), "attention"),
        ("brush", "coverage", geometric.get("brush_coverage"), "surface mask"),
        ("drag", "length", geometric.get("drag_length"), "3d transform"),
        ("smooth", "strength", geometric.get("smooth_strength"), "local geometry"),
        ("add", "primitive", semantic.get("primitive"), "3d primitive"),
    ]
    for group, label, value, source in evidence_fields:
        if value is not None:
            rows.append({"label": f"{group}_{label}", "value": value, "source": source})

    artifact_fields = [
        ("focus_artifact", visual.get("focus_observation_artifact_id")),
        ("brush_artifact", visual.get("brush_mask_artifact_id")),
        ("drag_artifact", visual.get("drag_operation_artifact_id")),
        ("smooth_artifact", visual.get("smooth_operation_artifact_id")),
        ("add_artifact", visual.get("primitive_addition_artifact_id")),
        ("annotation_artifact", visual.get("annotation_artifact_id")),
    ]
    for label, value in artifact_fields:
        if value:
            rows.append({"label": label, "value": value, "source": "artifact"})
            break

    ir = features.get("design_state_ir") if isinstance(features.get("design_state_ir"), dict) else {}
    matches = ir.get("matches") if isinstance(ir.get("matches"), list) else []
    recommended_axes = ir.get("recommended_axes") if isinstance(ir.get("recommended_axes"), list) else []
    if recommended_axes:
        rows.append(
            {
                "label": "next_axes",
                "value": " / ".join(str(axis) for axis in recommended_axes[:3]),
                "source": "design_state_ir",
            }
        )
    if matches and isinstance(matches[0], dict):
        top = matches[0]
        design_state = top.get("design_state") or "matched_design_state"
        route = top.get("route") or "design_state_ir"
        case_id = top.get("case_id") or top.get("ir_id")
        rows.append(
            {
                "label": "ir_state",
                "value": f"{design_state} → {route}",
                "source": f"design_state_ir:{case_id}" if case_id else "design_state_ir",
                "score": top.get("score"),
            }
        )

    return rows[:8]


async def _publish_perception(
    session_id: str,
    interpretation: InteractionInterpretation,
    *,
    include_stage: bool = True,
) -> None:
    """Single broadcast path for interpretation → perception (+ optional stage)."""
    await _WS.broadcast(
        session_id,
        "interaction_interpretation",
        interpretation.model_dump(mode="json"),
    )
    await _WS.broadcast(
        session_id,
        "perception_updated",
        _perception_payload(interpretation),
    )
    if include_stage:
        session = _STORE.get_session(session_id)
        if session is not None:
            await _WS.broadcast(
                session_id,
                "stage_update",
                session.stage.model_dump(mode="json"),
            )


def _update_session_live_signals(
    session_id: str,
    raw_signals: object,
    source: str,
) -> dict[str, object]:
    clean = _clean_live_signals(raw_signals)
    if not clean:
        return _live_signals_payload(_REQUIRE_SESSION(session_id))
    session = _REQUIRE_SESSION(session_id)
    current = session.metadata.get("live_signals")
    if not isinstance(current, dict):
        current = {}
    updated = {**current, **clean}
    part_id = str(getattr(getattr(session, "stage", None), "active_part_id", None) or "")
    silent_ir = silent_ir_prior(updated, part_id=part_id or None)
    _STORE.update_session(
        session_id,
        SessionUpdateRequest(
            metadata={
                "live_signals": updated,
                "silent_ir": silent_ir,
                "live_signals_updated_at": now_utc().isoformat(),
                "live_signals_source": source,
            }
        ),
    )
    return _live_signals_payload(_REQUIRE_SESSION(session_id))


def _clean_live_signals(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        return {}
    clean: dict[str, object] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            clean[key] = value
    return clean
