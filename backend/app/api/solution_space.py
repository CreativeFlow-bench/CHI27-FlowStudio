"""Single aggregation path for Solution Space views."""

from __future__ import annotations

from typing import Any

from app.models import SessionRecord
from app.services.storage.studio_store import InMemoryStudioStore


def _candidate_direction_ids(candidate: Any) -> list[str]:
    metadata = candidate.metadata if isinstance(candidate.metadata, dict) else {}
    values: list[str] = []
    direct = metadata.get("direction_id")
    if isinstance(direct, str) and direct:
        values.append(direct)
    evidence = metadata.get("pipeline_evidence")
    if isinstance(evidence, dict):
        raw = evidence.get("analogy_direction_ids")
        if isinstance(raw, list):
            values.extend(str(item) for item in raw if item)
        evidence_direction = evidence.get("direction_id")
        if isinstance(evidence_direction, str) and evidence_direction:
            values.append(evidence_direction)
    package = metadata.get("analogy_prompt_package")
    if isinstance(package, dict) and isinstance(package.get("direction_ids"), list):
        values.extend(str(item) for item in package["direction_ids"] if item)
    direction_ids = metadata.get("direction_ids")
    if isinstance(direction_ids, list):
        values.extend(str(item) for item in direction_ids if item)
    return list(dict.fromkeys(values))


def build_solution_space_view(
    store: InMemoryStudioStore,
    session: SessionRecord,
    *,
    limit: int = 50,
) -> dict[str, object]:
    """Canonical solution-space payload; snapshot embeds the same structure."""
    limit = max(1, min(int(limit), 200))
    session_id = session.session_id
    active_asset = (
        store.get_asset(session.stage.active_asset_id)
        if session.stage.active_asset_id
        else None
    )
    candidates = [
        candidate
        for candidate in store.candidates.values()
        if candidate.session_id == session_id
    ]
    candidates = sorted(
        candidates,
        key=lambda item: (
            0 if item.decision.value == "pending" else 1,
            item.job_id,
            item.candidate_id,
        ),
        reverse=False,
    )[:limit]
    directions = store.list_directions(session_id, limit=limit)
    return {
        "session_id": session_id,
        "stage": session.stage.model_dump(mode="json"),
        "active_asset": active_asset.model_dump(mode="json") if active_asset else None,
        "nodes": [
            {
                "node_id": f"sol_{candidate.candidate_id}",
                "parent_node_id": candidate.source_asset_id,
                "candidate_id": candidate.candidate_id,
                "direction_ids": _candidate_direction_ids(candidate),
                "artifact_level": "mesh"
                if candidate.mesh_url or candidate.obj_url
                else "image"
                if candidate.thumbnail_url
                else "contract",
                "decision": candidate.decision.value,
                "is_active_asset": (
                    bool(active_asset)
                    and active_asset.metadata.get("source_candidate_id")
                    == candidate.candidate_id
                ),
                "provenance": {
                    "job_id": candidate.job_id,
                    "source_asset_id": candidate.source_asset_id,
                    "source_part_id": candidate.source_part_id,
                    "pipeline_evidence": candidate.metadata.get("pipeline_evidence", {}),
                },
                "candidate": candidate.model_dump(mode="json"),
            }
            for candidate in candidates
        ],
        "directions": [direction.model_dump(mode="json") for direction in directions],
        "memory": session.metadata.get("candidate_memory", {}),
    }
