from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app, studio_store
from app.models import PartRecord
from app.services.generation.part_lifecycle import (
    attach_viewport_2d_evidence,
    annotate_obj_group_part,
    annotate_segmented_3d_part,
    read_lifecycle,
)


client = TestClient(app)


def test_viewport_mask_is_not_segmented_3d_part() -> None:
    obj_part = annotate_obj_group_part(
        PartRecord(
            part_id="obj_group_01",
            label="Branch",
            type="obj_group",
            metadata={"source": "obj_group_fallback"},
        )
    )
    assert read_lifecycle(obj_part) == "obj_group_fallback"

    updated = attach_viewport_2d_evidence(
        obj_part,
        artifact_id="art_mask_1",
        mask_url="/files/mask.png",
        overlay_url="/files/overlay.png",
        mask_coverage=0.17,
    )
    assert read_lifecycle(updated) == "viewport_2d_mask"
    assert read_lifecycle(updated) != "segmented_3d"
    assert updated.metadata["has_viewport_2d_mask"] is True
    assert updated.metadata["evidence"]["viewport_mask_artifact_id"] == "art_mask_1"
    assert updated.metadata["mesh_source_lifecycle"] == "obj_group_fallback"

    real_part = annotate_segmented_3d_part(
        PartRecord(
            part_id="seg_part_01",
            label="Branch",
            type="sam3d",
            metadata={"source": "sam3d", "segmented_mesh_path": "/tmp/x.obj"},
        )
    )
    enriched = attach_viewport_2d_evidence(
        real_part,
        artifact_id="art_mask_2",
        mask_url="/files/mask2.png",
        mask_coverage=0.2,
    )
    assert read_lifecycle(enriched) == "segmented_3d"
    assert enriched.metadata["has_viewport_2d_mask"] is True


def test_discover_obj_groups_set_obj_group_lifecycle(tmp_path: Path) -> None:
    obj_path = tmp_path / "toy.obj"
    obj_path.write_text(
        "\n".join(
            [
                "o Hat",
                "v 0 0 0",
                "v 1 0 0",
                "v 0 1 0",
                "f 1 2 3",
                "o Body",
                "v 0 0 0",
                "v 1 0 0",
                "v 0 1 0",
                "f 1 2 3",
                "f 1 2 3",
            ]
        ),
        encoding="utf-8",
    )
    session = client.post("/api/v1/sessions", json={"title": "part lifecycle discover"}).json()
    asset = client.post(
        "/api/v1/assets",
        json={
            "session_id": session["session_id"],
            "object_type": "snowman",
            "label": "toy",
            "obj_url": f"file://{obj_path}",
            "metadata": {
                "storage_path": str(obj_path),
                "source": "local_white_model",
            },
        },
    ).json()
    # Ensure storage_path sticks for adapter.
    stored = studio_store.get_asset(asset["asset_id"])
    assert stored is not None
    stored.metadata["storage_path"] = str(obj_path)
    stored.metadata["source"] = "local_white_model"
    studio_store.assets[asset["asset_id"]] = stored

    response = client.post(
        "/api/v1/parts/discover",
        json={
            "session_id": session["session_id"],
            "asset_id": asset["asset_id"],
            "mode": "mesh",
            "metadata": {"max_parts": 4},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["parts"]
    assert all(part.get("lifecycle") == "obj_group_fallback" for part in body["parts"])
    assert body["metadata"]["lifecycle_summary"]["has_obj_group_fallback"] is True
    assert body["metadata"]["lifecycle_summary"]["has_segmented_3d"] is False


def test_focus_observation_includes_part_lifecycle() -> None:
    session = client.post("/api/v1/sessions", json={"title": "focus lifecycle"}).json()
    asset = client.post(
        "/api/v1/assets",
        json={"session_id": session["session_id"], "object_type": "snowman"},
    ).json()
    stored = studio_store.get_asset(asset["asset_id"])
    assert stored is not None
    stored.parts = [
        annotate_obj_group_part(
            PartRecord(
                part_id="obj_group_01",
                label="Branch",
                type="obj_group",
                metadata={"source": "obj_group_fallback"},
            )
        )
    ]
    studio_store.assets[asset["asset_id"]] = stored

    response = client.post(
        "/api/v1/focus-observations",
        json={
            "session_id": session["session_id"],
            "asset_id": asset["asset_id"],
            "part_id": "obj_group_01",
            "label": "Branch",
            "observation": {"focus_source": "toolbar_hover_commit"},
            "viewport": {"display_mode": "textured"},
            "metrics": {"dwell_ms": 1200},
            "metadata": {},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["part_lifecycle"] == "obj_group_fallback"


def test_action_atom_embeds_part_lifecycle() -> None:
    session = client.post("/api/v1/sessions", json={"title": "action lifecycle"}).json()
    asset = client.post(
        "/api/v1/assets",
        json={"session_id": session["session_id"], "object_type": "snowman"},
    ).json()
    stored = studio_store.get_asset(asset["asset_id"])
    assert stored is not None
    stored.parts = [
        annotate_segmented_3d_part(
            PartRecord(
                part_id="seg_part_01",
                label="Hat",
                type="sam3d",
                metadata={"source": "sam3d"},
            )
        )
    ]
    studio_store.assets[asset["asset_id"]] = stored

    response = client.post(
        f"/api/v1/sessions/{session['session_id']}/actions",
        json={
            "tool": "hover",
            "target": {
                "asset_id": asset["asset_id"],
                "part_id": "seg_part_01",
                "label": "Hat",
            },
            "evidence": {"live_signals": {"hover_count": 1}},
            "order": 0,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["target"]["lifecycle"] == "segmented_3d"
    assert body["evidence"]["part_lifecycle"] == "segmented_3d"
