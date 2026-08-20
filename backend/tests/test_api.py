import asyncio
import json
from pathlib import Path
import struct

from fastapi.testclient import TestClient
import pytest

from app.main import app, remote_worker_adapter, studio_store, write_case_index
from app.models import (
    Candidate,
    CandidateDecision,
    CaseRecord,
    GenerationMode,
    GenerationOptions,
    GenerationRequest,
    Intent,
    JobStage,
    JobStatus,
    Selection,
    SelectionType,
    UserEvent,
)
from app.services.generation.generation_orchestrator import (
    GenerationOrchestrator,
    JobCancelled,
    RemoteCreativeFlowWorkerAdapter,
)
from app.services.intent import multimodal_intent_predictor as predictor_module
from app.services.intent.multimodal_intent_predictor import VLMIntentPredictor
from app.services.storage.websocket_manager import WebSocketManager


client = TestClient(app)
CASE_INDEX_PATH = (
    Path(__file__).resolve().parents[1] / "storage" / "files" / "cases" / "index.json"
)


@pytest.fixture(autouse=True)
def preserve_case_index_file():
    original = CASE_INDEX_PATH.read_bytes() if CASE_INDEX_PATH.exists() else None
    yield
    if original is None:
        CASE_INDEX_PATH.unlink(missing_ok=True)
        return
    CASE_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    CASE_INDEX_PATH.write_bytes(original)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "creativeflow_local" in body
    assert "remote_worker_ok" in body
    assert "remote_creativeflow_pipeline" in body


def test_action_atom_updates_perception_with_design_state_ir() -> None:
    session = client.post("/api/v1/sessions", json={"title": "IR action perception"}).json()
    asset = client.post(
        "/api/v1/assets",
        json={"session_id": session["session_id"], "object_type": "snowman"},
    ).json()

    response = client.post(
        f"/api/v1/sessions/{session['session_id']}/actions",
        json={
            "tool": "hover",
            "target": {"asset_id": asset["asset_id"], "label": "whole snowman"},
            "evidence": {
                "intent_text": "make the whole snowman more cute",
                "live_signals": {
                    "dwell_ms": 2200,
                    "viewport_orbit_count": 3,
                    "viewport_zoom_count": 1,
                    "tool_switch_count": 4,
                    "compare_dwell_ms": 2100,
                },
            },
            "order": 0,
        },
    )

    assert response.status_code == 200
    latest = client.get(f"/api/v1/sessions/{session['session_id']}/perception/latest").json()
    perception = latest["perception"]
    assert latest["status"] == "ready"
    assert perception["confidence"] > 0
    ir = perception["features"]["design_state_ir"]
    assert ir["ready"] is True
    assert ir["retrieval_mode"] == "ir_then_content"
    assert "rapid_tool_switch" in ir["query_signals"]
    assert "long_compare" in ir["query_signals"]
    assert ir["matches"]
    assert ir["axis_scores"]
    assert ir.get("predicted_state") in {None, "Exploration", "Formation", "Refinement", "Evaluation"}
    assert ir.get("predicted_hierarchy") in {None, "Silhouette", "Part", "Material"}
    live = client.get(f"/api/v1/sessions/{session['session_id']}/live-signals").json()
    assert live["live_signals"]["tool_switch_count"] == 4
    snapshot = client.get(f"/api/v1/sessions/{session['session_id']}/snapshot").json()
    assert snapshot["live_signals"]["compare_dwell_ms"] == 2100


def test_live_signals_endpoint_persists_session_snapshot() -> None:
    session = client.post("/api/v1/sessions", json={"title": "Live signals"}).json()

    response = client.put(
        f"/api/v1/sessions/{session['session_id']}/live-signals",
        json={"live_signals": {"dwell_ms": 1300, "viewport_orbit_count": 2}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["live_signals"]["dwell_ms"] == 1300
    assert body["source"] == "live_signals_endpoint"
    assert body["silent_ir"]["ready"] is True
    assert body["silent_ir"]["recommended_axes"]

    response = client.put(
        f"/api/v1/sessions/{session['session_id']}/live-signals",
        json={"viewport_zoom_count": 1},
    )
    body = response.json()
    assert body["live_signals"]["dwell_ms"] == 1300
    assert body["live_signals"]["viewport_zoom_count"] == 1


def test_local_white_models_are_discoverable_and_loadable() -> None:
    response = client.get("/api/v1/benchmark-assets")
    assert response.status_code == 200
    white_models = [
        item
        for item in response.json()["assets"]
        if item["metadata"].get("source") == "local_white_model"
    ]
    assert len(white_models) >= 3
    assert {"bakery", "christmas", "toy_animals"}.issubset(
        {item["metadata"].get("category") for item in white_models}
    )
    assert any(item["benchmark_id"] == "white:toy_animals:bulldog" for item in white_models)

    session = client.post("/api/v1/sessions", json={"title": "White model load"}).json()
    first = next(item for item in white_models if item["object_type"] == "snowman")
    load = client.post(
        f"/api/v1/benchmark-assets/{first['benchmark_id']}/load",
        json={"session_id": session["session_id"]},
    )
    assert load.status_code == 200
    asset = load.json()
    assert asset["obj_url"].endswith(".obj")
    assert asset["metadata"]["white_model_category"] == "christmas"
    assert asset["metadata"]["storage_path"].endswith(".obj")


def test_local_white_model_part_discovery_falls_back_to_obj_groups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.generation.autopartgen_adapter.AutoPartGenAdapter._submit_remote_segmentation",
        lambda self, request, asset: asyncio.sleep(
            0,
            result={
                "status": "failed",
                "result": {"result_json": {"parts": []}},
            },
        ),
    )
    session = client.post("/api/v1/sessions", json={"title": "White model parts"}).json()
    assets = client.get("/api/v1/benchmark-assets").json()["assets"]
    snowman = next(item for item in assets if item["benchmark_id"] == "white:christmas:snowman")
    asset = client.post(
        f"/api/v1/benchmark-assets/{snowman['benchmark_id']}/load",
        json={"session_id": session["session_id"]},
    ).json()

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
    assert body["metadata"]["adapter"] == "obj_group_fallback"
    assert len(body["parts"]) == 4
    assert body["parts"][0]["metadata"]["source"] == "obj_group_fallback"


def test_prompt_compose_records_selected_tokens() -> None:
    session = client.post("/api/v1/sessions", json={"title": "Prompt compose"}).json()
    asset = client.post(
        "/api/v1/assets",
        json={"session_id": session["session_id"], "object_type": "snowman"},
    ).json()

    response = client.post(
        "/api/v1/prompt/compose",
        json={
            "session_id": session["session_id"],
            "asset_id": asset["asset_id"],
            "base_prompt": "make it cute",
            "selected_prompt_tokens": [
                {"label": "fluffy", "dimension": "Aesthetic", "role": "texture"},
                {"label": "fluffy", "dimension": "Aesthetic", "role": "texture"},
                {"label": "rounded silhouette", "dimension": "Structural", "role": "shape"},
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "Analogy keywords: fluffy, rounded silhouette" in body["final_prompt"]
    assert len(body["analogy_prompt_package"]["selected_prompt_tokens"]) == 2
    memories = client.get(
        f"/api/v1/sessions/{session['session_id']}/memories?category=working"
    ).json()["memories"]
    assert any(item["type"] == "prompt_chip_composition" for item in memories)


def test_admin_state_export_import_roundtrip() -> None:
    session_response = client.post(
        "/api/v1/sessions",
        json={"title": "State snapshot smoke", "user_id": "snapshot_tester"},
    )
    assert session_response.status_code == 200
    session = session_response.json()
    asset_response = client.post(
        "/api/v1/assets",
        json={
            "session_id": session["session_id"],
            "object_type": "snapshot_asset",
            "label": "snapshot asset",
        },
    )
    assert asset_response.status_code == 200

    export_response = client.get("/api/v1/admin/state/export")
    assert export_response.status_code == 200
    snapshot = export_response.json()
    assert snapshot["version"] == 1
    assert any(item["session_id"] == session["session_id"] for item in snapshot["sessions"])
    assert any(item["session_id"] == session["session_id"] for item in snapshot["assets"])

    import_response = client.post(
        "/api/v1/admin/state/import",
        json={"snapshot": snapshot, "replace": True},
    )
    assert import_response.status_code == 200
    body = import_response.json()
    assert body["replaced"] is True
    assert body["imported"]["sessions"] == len(snapshot["sessions"])

    restored = client.get(f"/api/v1/sessions/{session['session_id']}/snapshot")
    assert restored.status_code == 200
    assert restored.json()["session"]["title"] == "State snapshot smoke"


def test_candidate_generation_stub_gone() -> None:
    response = client.post(
        "/api/v1/candidates",
        json={
            "asset_id": "speaker-demo",
            "source_part_id": "grille",
            "relation_prompt": "organic porous bionic grille",
            "candidate_count": 3,
        },
    )

    assert response.status_code == 410
    body = response.json()
    assert body["error"]["code"] == "CANDIDATES_ENDPOINT_GONE"
    assert body["error"]["details"]["canonical_endpoint"] == "/api/v1/generation/replace"


def test_contract_session_asset_generation_flow() -> None:
    session_response = client.post(
        "/api/v1/sessions",
        json={"title": "Contract smoke", "user_id": "tester"},
    )
    assert session_response.status_code == 200
    session = session_response.json()

    asset_response = client.post(
        "/api/v1/assets",
        json={
            "session_id": session["session_id"],
            "object_type": "design_db_asset",
            "label": "contract asset",
        },
    )
    assert asset_response.status_code == 200
    asset = asset_response.json()
    assert asset["parts"] == []

    generation_response = client.post(
        "/api/v1/generation/replace",
        json={
            "session_id": session["session_id"],
            "asset_id": asset["asset_id"],
            "selection": {
                "type": "part",
                "part_id": "body",
                "label": "main body",
            },
            "intent": {
                "mode": "replace",
                "text": "make it organic and porous",
            },
            "generation": {
                "candidate_count": 2,
                "diversity": 0.7,
                "output_format": "glb",
            },
        },
    )
    assert generation_response.status_code == 200
    job_id = generation_response.json()["job_id"]

    job_response = client.get(f"/api/v1/jobs/{job_id}")
    assert job_response.status_code == 200
    assert job_response.json()["session_id"] == session["session_id"]
    studio_store.save_candidate(
        Candidate(
            candidate_id=f"cand_{job_id}_contract",
            job_id=job_id,
            session_id=session["session_id"],
            source_asset_id=asset["asset_id"],
            source_part_id="body",
            label="Contract candidate",
        )
    )

    candidates_response = client.get(f"/api/v1/jobs/{job_id}/candidates")
    assert candidates_response.status_code == 200
    candidates = candidates_response.json()
    assert len(candidates) >= 1
    assert candidates[0]["job_id"] == job_id


def test_intent_episode_direction_preview_contract() -> None:
    session = client.post(
        "/api/v1/sessions",
        json={"title": "Intent evidence contract", "user_id": "tester"},
    ).json()
    asset = client.post(
        "/api/v1/assets",
        json={
            "session_id": session["session_id"],
            "object_type": "snowman",
            "label": "evidence snowman",
        },
    ).json()

    action_response = client.post(
        f"/api/v1/sessions/{session['session_id']}/actions",
        json={
            "tool": "annotation",
            "target": {"asset_id": asset["asset_id"], "part_id": None},
            "evidence": {"annotation_mode": "2d_pencil", "text": "make it cute"},
            "order": 0,
        },
    )
    assert action_response.status_code == 200
    atom = action_response.json()
    assert atom["atom_id"].startswith("atom_")

    draft = client.post(
        "/api/v1/intent-drafts",
        json={
            "session_id": session["session_id"],
            "asset_id": asset["asset_id"],
            "title": "cute intent",
            "text": "make it cute",
            "behavior_atoms": [atom],
        },
    ).json()

    episode_response = client.post(
        f"/api/v1/sessions/{session['session_id']}/episodes",
        json={
            "intent_draft_id": draft["draft_id"],
            "action_atom_ids": [atom["atom_id"]],
            "text": "make it cute",
            "metadata": {"test": True},
        },
    )
    assert episode_response.status_code == 200
    episode = episode_response.json()
    assert episode["episode_id"].startswith("ep_")
    assert episode["behavior_atoms"][0]["atom_id"] == atom["atom_id"]
    assert episode["planner_interpretation"]["source_event_id"].startswith("evt_")
    assert episode["planner_interpretation"]["primary_intent"] == "explore_shape"
    assert episode["planner_interpretation"]["confidence"] >= 0.7
    assert episode["metadata"]["planner_interpretation_id"] == episode["planner_interpretation"]["interpretation_id"]

    directions_response = client.post(
        "/api/v1/directions/cross-domain",
        json={
            "session_id": session["session_id"],
            "asset_id": asset["asset_id"],
            "intent_draft_id": draft["draft_id"],
            "source_summary": "make the whole snowman more cute",
            "dimensions": ["Aesthetic", "Structural"],
            "candidate_count": 2,
        },
    )
    assert directions_response.status_code == 200
    directions = directions_response.json()["directions"]
    assert directions
    assert directions[0]["metadata"]["prompt_tokens"]

    list_response = client.get(f"/api/v1/sessions/{session['session_id']}/directions")
    assert list_response.status_code == 200
    assert any(item["direction_id"] == directions[0]["direction_id"] for item in list_response.json()["directions"])

    selected_response = client.patch(
        f"/api/v1/directions/{directions[0]['direction_id']}",
        json={"status": "selected", "metadata": {"selected_prompt": "fluffy, soft"}},
    )
    assert selected_response.status_code == 200
    assert selected_response.json()["metadata"]["status"] == "selected"
    assert selected_response.json()["metadata"]["selected"] is True

    request = GenerationRequest(
        session_id=session["session_id"],
        asset_id=asset["asset_id"],
        selection=Selection(type=SelectionType.none),
        intent=Intent(mode=GenerationMode.diverge, text="preview"),
        generation=GenerationOptions(candidate_count=1),
    )
    job = studio_store.create_job(request)
    candidate = studio_store.save_candidate(
        Candidate(
            candidate_id=f"cand_{job.job_id}_preview",
            job_id=job.job_id,
            session_id=session["session_id"],
            source_asset_id=asset["asset_id"],
            label="image-only direction",
            thumbnail_url="/files/candidates/preview.png",
        )
    )
    preview_response = client.post(
        f"/api/v1/candidates/{candidate.candidate_id}/preview",
        json={"session_id": session["session_id"], "reason": "compare only"},
    )
    assert preview_response.status_code == 200
    assert preview_response.json()["metadata"]["preview_reason"] == "compare only"

    commit_response = client.post(
        f"/api/v1/candidates/{candidate.candidate_id}/commit",
        json={"session_id": session["session_id"], "reason": "save direction"},
    )
    assert commit_response.status_code == 200
    assert commit_response.json()["active_asset_id"] is None

    solution_response = client.get(f"/api/v1/sessions/{session['session_id']}/solution-space")
    assert solution_response.status_code == 200
    solution = solution_response.json()
    assert any(node["candidate_id"] == candidate.candidate_id for node in solution["nodes"])
    assert any(item["direction_id"] == directions[0]["direction_id"] for item in solution["directions"])

    empty_perception = client.get(f"/api/v1/sessions/{session['session_id']}/perception/latest")
    assert empty_perception.status_code == 200
    assert empty_perception.json()["status"] == "ready"

    interpret_response = client.post(
        "/api/v1/interaction/interpret",
        json={
            "type": "intent_episode_sent",
            "event_id": "evt_intent_contract",
            "session_id": session["session_id"],
            "payload": {
                "asset_id": asset["asset_id"],
                "intent_text": "make it cute",
                "signals": {"semantic": {"object_type": "snowman"}},
            },
        },
    )
    assert interpret_response.status_code == 200
    latest_perception = client.get(f"/api/v1/sessions/{session['session_id']}/perception/latest")
    assert latest_perception.status_code == 200
    assert latest_perception.json()["status"] == "ready"
    perception_body = latest_perception.json()
    assert perception_body["evidence_summary"][0]["label"] == "intent"
    assert perception_body["perception"]["evidence_summary"][0]["source"] == "planner"


def test_frontend_spec_aliases_for_cursor_integration() -> None:
    session = client.post("/api/v1/sessions", json={"title": "Cursor contract"}).json()
    asset = client.post(
        "/api/v1/assets",
        json={
            "session_id": session["session_id"],
            "object_type": "snowman",
            "label": "cursor snowman",
        },
    ).json()

    action_response = client.post(
        f"/api/v1/sessions/{session['session_id']}/actions",
        json={
            "action_id": "act_cursor_001",
            "tool": "hover",
            "target": {"asset_id": asset["asset_id"]},
            "evidence": {"dwell_ms": 1800},
        },
    )
    assert action_response.status_code == 200
    atom = action_response.json()
    assert atom["atom_id"] == "act_cursor_001"
    assert atom["action_id"] == "act_cursor_001"

    draft = client.post(
        "/api/v1/intent-drafts",
        json={
            "session_id": session["session_id"],
            "asset_id": asset["asset_id"],
            "title": "Cursor draft",
            "behavior_atoms": [atom],
        },
    ).json()
    assert draft["intent_draft_id"] == draft["draft_id"]
    assert draft["action_ids"] == ["act_cursor_001"]

    direct_draft = client.post(
        "/api/v1/intent-drafts",
        json={
            "session_id": session["session_id"],
            "asset_id": asset["asset_id"],
            "title": "Cursor direct draft",
            "behavior_atoms": [
                {
                    "atom_id": "act_cursor_direct_001",
                    "tool": "annotation",
                    "target": {"asset_id": asset["asset_id"]},
                    "evidence": {"drawing_content": "closed_contour"},
                    "order": 1,
                }
            ],
        },
    ).json()
    assert direct_draft["action_ids"] == ["act_cursor_direct_001"]

    status_response = client.patch(
        f"/api/v1/intent-drafts/{draft['draft_id']}",
        json={"status": "submitted"},
    )
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "sent"

    directions_response = client.post(
        "/api/v1/directions/suggest",
        json={
            "session_id": session["session_id"],
            "asset_id": asset["asset_id"],
            "intent_draft_id": draft["draft_id"],
            "preserved_constraints": ["preserve snowman identity"],
            "dimensions": ["aesthetic", "structural"],
            "direction_count": 2,
            "scope": {"type": "whole_object", "part_id": None},
            "context_snapshot_id": "ctx_cursor",
            "minimum_semantic_distance": 0.55,
        },
    )
    assert directions_response.status_code == 200
    body = directions_response.json()
    assert len(body["directions"]) <= 2
    assert body["directions"][0]["dimension"] in {"Aesthetic", "Structural"}
    assert "preserve snowman identity" in body["directions"][0]["constraints"]
    assert body["metadata"]["scope"]["type"] == "whole_object"
    assert body["metadata"]["context_snapshot_id"] == "ctx_cursor"

    snapshot = client.get(f"/api/v1/sessions/{session['session_id']}/snapshot").json()
    assert any(item["action_id"] == "act_cursor_001" for item in snapshot["action_atoms"])
    assert any(item["action_id"] == "act_cursor_direct_001" for item in snapshot["action_atoms"])
    assert any(item["intent_draft_id"] == draft["draft_id"] for item in snapshot["intent_drafts"])
    assert snapshot["directions"]


def test_candidate_fit_endpoint_returns_transform_ready(monkeypatch) -> None:
    async def fake_get_artifact_file(remote_path: str) -> tuple[bytes, str]:
        assert remote_path == "/remote/part_candidate.obj"
        return b"v 0 0 0\nv 2 1 2\n", "text/plain"

    monkeypatch.setattr(remote_worker_adapter, "get_artifact_file", fake_get_artifact_file)

    session = client.post("/api/v1/sessions", json={"title": "Fit endpoint"}).json()
    asset_response = client.post(
        "/api/v1/assets",
        json={
            "session_id": session["session_id"],
            "object_type": "speaker",
            "label": "speaker",
            "parts": [
                {
                    "part_id": "pf_part_01",
                    "label": "front grille",
                    "metadata": {
                        "bbox3d": {
                            "min": [10, 20, 30],
                            "max": [14, 22, 34],
                        }
                    },
                }
            ],
        },
    )
    assert asset_response.status_code == 200
    asset = asset_response.json()
    request = GenerationRequest(
        session_id=session["session_id"],
        asset_id=asset["asset_id"],
        selection=Selection(type=SelectionType.part, part_id="pf_part_01"),
        intent=Intent(mode=GenerationMode.replace, text="replace grille"),
        generation=GenerationOptions(candidate_count=1),
    )
    job = studio_store.create_job(request)
    candidate = studio_store.save_candidate(
        Candidate(
            candidate_id="cand_fit_endpoint",
            job_id=job.job_id,
            session_id=session["session_id"],
            source_asset_id=asset["asset_id"],
            source_part_id="pf_part_01",
            label="candidate grille",
            obj_url="/api/v1/remote-worker/artifact-file?path=/remote/part_candidate.obj",
            metadata={"pipeline_evidence": {}},
        )
    )

    response = client.post(
        f"/api/v1/candidates/{candidate.candidate_id}/fit",
        json={"session_id": session["session_id"], "target_part_id": "pf_part_01"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mesh_url"] is None
    assert body["obj_url"] == "/files/fitted/cand_fit_endpoint/fitted.obj"
    assert body["metadata"]["fit_result"]["status"] == "review_needed"
    assert body["metadata"]["pipeline_evidence"]["fit_status"] == "review_needed"
    assert body["metadata"]["pipeline_evidence"]["fit_target_part_id"] == "pf_part_01"
    assert body["metadata"]["pipeline_evidence"]["seam_validation"]["status"] == "review_needed"

    fitted_response = client.get(body["obj_url"])
    assert fitted_response.status_code == 200
    assert b"v 10" in fitted_response.content


def test_mesh_export_endpoints_return_real_files(monkeypatch) -> None:
    async def fake_get_artifact_file(remote_path: str) -> tuple[bytes, str]:
        if remote_path.endswith("mesh.glb"):
            return b"glb-bytes", "model/gltf-binary"
        if remote_path.endswith("mesh.obj"):
            return b"o mesh\n", "text/plain"
        raise RuntimeError(remote_path)

    monkeypatch.setattr(remote_worker_adapter, "get_artifact_file", fake_get_artifact_file)

    session = client.post("/api/v1/sessions", json={"title": "Export endpoint"}).json()
    asset = client.post(
        "/api/v1/assets",
        json={
            "session_id": session["session_id"],
            "object_type": "snowman",
            "label": "export snowman",
            "mesh_url": "/api/v1/remote-worker/artifact-file?path=/remote/mesh.glb",
            "obj_url": "/api/v1/remote-worker/artifact-file?path=/remote/mesh.obj",
        },
    ).json()

    glb_response = client.get(f"/api/v1/assets/{asset['asset_id']}/export?format=glb")
    assert glb_response.status_code == 200
    assert glb_response.content == b"glb-bytes"
    assert "attachment" in glb_response.headers["content-disposition"]

    obj_response = client.get(f"/api/v1/assets/{asset['asset_id']}/export?format=obj")
    assert obj_response.status_code == 200
    assert obj_response.content == b"o mesh\n"

    request = GenerationRequest(
        session_id=session["session_id"],
        asset_id=asset["asset_id"],
        selection=Selection(type=SelectionType.none),
        intent=Intent(mode=GenerationMode.diverge, text="image only"),
        generation=GenerationOptions(candidate_count=1),
    )
    job = studio_store.create_job(request)
    image_candidate = studio_store.save_candidate(
        Candidate(
            candidate_id="cand_export_image_only",
            job_id=job.job_id,
            session_id=session["session_id"],
            source_asset_id=asset["asset_id"],
            label="image only",
            thumbnail_url="/files/candidates/image.png",
        )
    )
    missing_response = client.get(f"/api/v1/candidates/{image_candidate.candidate_id}/export?format=glb")
    assert missing_response.status_code == 404

    mesh_candidate = studio_store.save_candidate(
        Candidate(
            candidate_id="cand_export_mesh",
            job_id=job.job_id,
            session_id=session["session_id"],
            source_asset_id=asset["asset_id"],
            label="mesh candidate",
            mesh_url="/api/v1/remote-worker/artifact-file?path=/remote/mesh.glb",
            obj_url="/api/v1/remote-worker/artifact-file?path=/remote/mesh.obj",
        )
    )
    candidate_response = client.get(f"/api/v1/candidates/{mesh_candidate.candidate_id}/export?format=obj")
    assert candidate_response.status_code == 200
    assert candidate_response.content == b"o mesh\n"


def test_asset_upload_creates_static_asset_and_updates_stage() -> None:
    session_response = client.post("/api/v1/sessions", json={"title": "Upload smoke"})
    assert session_response.status_code == 200
    session_id = session_response.json()["session_id"]

    upload_response = client.post(
        "/api/v1/assets/upload",
        data={
            "session_id": session_id,
            "object_type": "speaker",
            "label": "uploaded prototype",
            "metadata": '{"source":"test"}',
        },
        files={"file": ("prototype.glb", b"glTF fake content", "model/gltf-binary")},
    )

    assert upload_response.status_code == 200
    asset = upload_response.json()
    assert asset["asset_id"].startswith("asset_")
    assert asset["mesh_url"].endswith("/source.glb")
    assert asset["metadata"]["uploaded_filename"] == "prototype.glb"

    session = client.get(f"/api/v1/sessions/{session_id}").json()
    assert session["stage"]["active_asset_id"] == asset["asset_id"]

    file_response = client.get(asset["mesh_url"])
    assert file_response.status_code == 200
    assert file_response.content == b"glTF fake content"


def test_reference_image_upload_records_artifact_event_memory_and_intent_refs() -> None:
    session = client.post("/api/v1/sessions", json={"title": "Reference image"}).json()
    asset = client.post(
        "/api/v1/assets",
        json={
            "session_id": session["session_id"],
            "object_type": "snowman",
            "label": "reference snowman",
        },
    ).json()

    response = client.post(
        "/api/v1/reference-images/upload",
        data={
            "session_id": session["session_id"],
            "asset_id": asset["asset_id"],
            "role": "shape_reference",
            "metadata": json.dumps({"source": "test"}),
        },
        files={"file": ("ref.png", b"\\x89PNG\\r\\n\\x1a\\nref", "image/png")},
    )
    assert response.status_code == 200
    artifact = response.json()
    assert artifact["type"] == "reference_image"
    assert artifact["url"].startswith("/files/references/")
    assert artifact["metadata"]["role"] == "shape_reference"

    file_response = client.get(artifact["url"])
    assert file_response.status_code == 200
    assert file_response.content.startswith(b"\\x89PNG")

    memory = client.get(f"/api/v1/sessions/{session['session_id']}/memory").json()
    assert any(
        item["type"] == "event:reference_image_attached"
        for item in memory["structured_memory"]["episodic"]
    )
    assert any(
        item["type"] == "reference_image"
        and item["source_id"] == artifact["artifact_id"]
        for item in memory["structured_memory"]["working"]
    )

    draft_response = client.post(
        "/api/v1/intent-drafts",
        json={
            "session_id": session["session_id"],
            "asset_id": asset["asset_id"],
            "title": "image ref draft",
            "text": "use this image as a cute shape reference",
            "image_refs": [artifact["url"]],
            "metadata": {
                "reference_images": [
                    {"artifact_id": artifact["artifact_id"], "url": artifact["url"]}
                ]
            },
        },
    )
    assert draft_response.status_code == 200
    draft = draft_response.json()
    assert draft["image_refs"] == [artifact["url"]]

    episode_response = client.post(
        f"/api/v1/sessions/{session['session_id']}/episodes",
        json={
            "intent_draft_id": draft["draft_id"],
            "text": draft["text"],
            "image_refs": draft["image_refs"],
        },
    )
    assert episode_response.status_code == 200
    assert episode_response.json()["image_refs"] == [artifact["url"]]

    interpret_response = client.post(
        "/api/v1/interaction/interpret",
        json={
            "type": "intent_episode_sent",
            "event_id": "evt_reference_image_episode",
            "session_id": session["session_id"],
            "timestamp": "2026-07-06T00:00:00Z",
            "payload": {
                "asset_id": asset["asset_id"],
                "intent_text": draft["text"],
                "image_refs": draft["image_refs"],
                "reference_images": [
                    {"artifact_id": artifact["artifact_id"], "url": artifact["url"], "role": "shape_reference"}
                ],
            },
        },
    )
    assert interpret_response.status_code == 200
    interpretation = interpret_response.json()
    visual_context = interpretation["features"]["signals"]["visual_context"]
    assert visual_context["image_ref_count"] == 1
    assert visual_context["image_refs"] == [artifact["url"]]
    assert visual_context["reference_images"][0]["artifact_id"] == artifact["artifact_id"]


def test_reference_model_upload_records_artifact_event_memory_and_intent_refs() -> None:
    session = client.post("/api/v1/sessions", json={"title": "Reference model"}).json()
    asset = client.post(
        "/api/v1/assets",
        json={
            "session_id": session["session_id"],
            "object_type": "snowman",
            "label": "reference model snowman",
        },
    ).json()
    previous_active_asset_id = client.get(f"/api/v1/sessions/{session['session_id']}").json()["stage"][
        "active_asset_id"
    ]

    response = client.post(
        "/api/v1/reference-models/upload",
        data={
            "session_id": session["session_id"],
            "asset_id": asset["asset_id"],
            "role": "model_reference",
            "metadata": json.dumps({"source": "test"}),
        },
        files={"file": ("ref.glb", b"glTF reference content", "model/gltf-binary")},
    )
    assert response.status_code == 200
    artifact = response.json()
    assert artifact["type"] == "reference_model"
    assert artifact["url"].startswith("/files/reference-models/")
    assert artifact["metadata"]["role"] == "model_reference"
    assert artifact["metadata"]["model_ref_kind"] == "intent_reference_not_active_asset"

    assert client.get(f"/api/v1/sessions/{session['session_id']}").json()["stage"][
        "active_asset_id"
    ] == previous_active_asset_id

    file_response = client.get(artifact["url"])
    assert file_response.status_code == 200
    assert file_response.content == b"glTF reference content"

    memory = client.get(f"/api/v1/sessions/{session['session_id']}/memory").json()
    assert any(
        item["type"] == "event:reference_model_attached"
        for item in memory["structured_memory"]["episodic"]
    )
    assert any(
        item["type"] == "reference_model"
        and item["source_id"] == artifact["artifact_id"]
        for item in memory["structured_memory"]["working"]
    )

    draft_response = client.post(
        "/api/v1/intent-drafts",
        json={
            "session_id": session["session_id"],
            "asset_id": asset["asset_id"],
            "title": "model ref draft",
            "text": "use this model as a shape reference",
            "model_refs": [artifact["url"]],
            "metadata": {
                "reference_models": [
                    {"artifact_id": artifact["artifact_id"], "url": artifact["url"]}
                ]
            },
        },
    )
    assert draft_response.status_code == 200
    draft = draft_response.json()
    assert draft["model_refs"] == [artifact["url"]]

    episode_response = client.post(
        f"/api/v1/sessions/{session['session_id']}/episodes",
        json={
            "intent_draft_id": draft["draft_id"],
            "text": draft["text"],
            "model_refs": draft["model_refs"],
        },
    )
    assert episode_response.status_code == 200
    assert episode_response.json()["model_refs"] == [artifact["url"]]

    interpret_response = client.post(
        "/api/v1/interaction/interpret",
        json={
            "type": "intent_episode_sent",
            "event_id": "evt_reference_model_episode",
            "session_id": session["session_id"],
            "timestamp": "2026-07-06T00:00:00Z",
            "payload": {
                "asset_id": asset["asset_id"],
                "intent_text": draft["text"],
                "model_refs": draft["model_refs"],
                "reference_models": [
                    {"artifact_id": artifact["artifact_id"], "url": artifact["url"], "role": "model_reference"}
                ],
            },
        },
    )
    assert interpret_response.status_code == 200
    visual_context = interpret_response.json()["features"]["signals"]["visual_context"]
    assert visual_context["model_ref_count"] == 1
    assert visual_context["model_refs"] == [artifact["url"]]
    assert visual_context["reference_models"][0]["artifact_id"] == artifact["artifact_id"]


def test_annotation_artifact_records_stroke_event_memory_and_planner_features() -> None:
    session = client.post("/api/v1/sessions", json={"title": "Annotation artifact"}).json()
    asset = client.post(
        "/api/v1/assets",
        json={
            "session_id": session["session_id"],
            "object_type": "snowman",
            "label": "annotation snowman",
        },
    ).json()

    response = client.post(
        "/api/v1/annotations",
        json={
            "session_id": session["session_id"],
            "asset_id": asset["asset_id"],
            "part_id": None,
            "text": "draw a triangle silhouette",
            "strokes": [
                {
                    "stroke_id": "stroke_triangle",
                    "tool": "pencil",
                    "shape_hint": "triangle",
                    "points": [{"x": 0.3, "y": 0.7}, {"x": 0.5, "y": 0.2}, {"x": 0.7, "y": 0.7}],
                }
            ],
            "projection": {"space": "screen_normalized", "target": "whole_object"},
            "metadata": {"source": "test"},
        },
    )
    assert response.status_code == 200
    artifact = response.json()
    assert artifact["type"] == "annotation_stroke"
    assert artifact["url"].startswith("/files/annotations/")
    assert artifact["metadata"]["stroke_count"] == 1

    stroke_file = client.get(artifact["url"])
    assert stroke_file.status_code == 200
    stroke_payload = stroke_file.json()
    assert stroke_payload["strokes"][0]["shape_hint"] == "triangle"

    memory = client.get(f"/api/v1/sessions/{session['session_id']}/memory").json()
    assert any(
        item["type"] == "event:annotation_stroke_committed"
        for item in memory["structured_memory"]["episodic"]
    )
    assert any(
        item["type"] == "annotation_stroke"
        and item["source_id"] == artifact["artifact_id"]
        for item in memory["structured_memory"]["working"]
    )

    interpret_response = client.post(
        "/api/v1/interaction/interpret",
        json={
            "type": "annotation_commit",
            "event_id": "evt_annotation_artifact",
            "session_id": session["session_id"],
            "timestamp": "2026-07-06T00:00:00Z",
            "payload": {
                "asset_id": asset["asset_id"],
                "intent_text": "draw a triangle silhouette",
                "annotation_artifact_id": artifact["artifact_id"],
                "stroke_url": artifact["url"],
                "annotation_shape": "triangle",
                "projection": {"space": "screen_normalized", "target": "whole_object"},
            },
        },
    )
    assert interpret_response.status_code == 200
    visual_context = interpret_response.json()["features"]["signals"]["visual_context"]
    assert visual_context["annotation_artifact_id"] == artifact["artifact_id"]
    assert visual_context["annotation_stroke_url"] == artifact["url"]
    assert visual_context["annotation_projection"]["target"] == "whole_object"


def test_brush_mask_artifact_records_surface_region_event_memory_and_planner_features() -> None:
    session = client.post("/api/v1/sessions", json={"title": "Brush mask artifact"}).json()
    asset = client.post(
        "/api/v1/assets",
        json={
            "session_id": session["session_id"],
            "object_type": "snowman",
            "label": "brush snowman",
            "parts": [{"part_id": "scarf", "label": "scarf"}],
        },
    ).json()

    response = client.post(
        "/api/v1/brush-masks",
        json={
            "session_id": session["session_id"],
            "asset_id": asset["asset_id"],
            "part_id": "scarf",
            "label": "scarf",
            "mask": {
                "kind": "surface_region",
                "representation": "normalized_screen_polyline_with_part_anchor",
                "screen_path": [{"x": 0.4, "y": 0.5}, {"x": 0.5, "y": 0.55}],
                "bbox": [0.4, 0.5, 0.5, 0.55],
            },
            "projection": {"space": "screen_to_surface", "target": "part_surface"},
            "metrics": {"coverage": 0.18, "confidence": 0.76},
            "metadata": {"source": "test"},
        },
    )
    assert response.status_code == 200
    artifact = response.json()
    assert artifact["type"] == "brush_mask"
    assert artifact["url"].startswith("/files/brush-masks/")
    assert artifact["metrics"]["coverage"] == 0.18
    assert artifact["metadata"]["mask_kind"] == "surface_region"

    mask_file = client.get(artifact["url"])
    assert mask_file.status_code == 200
    mask_payload = mask_file.json()
    assert mask_payload["mask"]["kind"] == "surface_region"
    assert mask_payload["projection"]["target"] == "part_surface"

    memory = client.get(f"/api/v1/sessions/{session['session_id']}/memory").json()
    assert any(
        item["type"] == "event:brush_mask_committed"
        for item in memory["structured_memory"]["episodic"]
    )
    assert any(
        item["type"] == "brush_mask"
        and item["source_id"] == artifact["artifact_id"]
        and "surface_mask" in item["tags"]
        for item in memory["structured_memory"]["working"]
    )

    interpret_response = client.post(
        "/api/v1/interaction/interpret",
        json={
            "type": "brush_end",
            "event_id": "evt_brush_mask_artifact",
            "session_id": session["session_id"],
            "timestamp": "2026-07-06T00:00:00Z",
            "payload": {
                "asset_id": asset["asset_id"],
                "intent_text": "make this scarf softer",
                "brush_mask_artifact_id": artifact["artifact_id"],
                "brush_mask_url": artifact["url"],
                "brush_coverage": 0.18,
                "brush_projection": {"space": "screen_to_surface", "target": "part_surface"},
                "selection": {
                    "type": "brush",
                    "part_id": "scarf",
                    "label": "scarf",
                    "mask_url": artifact["url"],
                    "brush_mask_artifact_id": artifact["artifact_id"],
                    "coverage": 0.18,
                    "bbox": [120, 82, 360, 264],
                },
            },
        },
    )
    assert interpret_response.status_code == 200
    interpretation = interpret_response.json()
    assert interpretation["primary_intent"] == "replace_region"
    signals = interpretation["features"]["signals"]
    assert signals["visual_context"]["brush_mask_artifact_id"] == artifact["artifact_id"]
    assert signals["visual_context"]["brush_mask_url"] == artifact["url"]
    assert signals["visual_context"]["brush_coverage"] == 0.18
    assert signals["geometric"]["brush_coverage"] == 0.18
    assert signals["semantic"]["brush_mask_artifact_id"] == artifact["artifact_id"]


def test_viewport_screenshot_artifact_records_capture_event() -> None:
    session = client.post("/api/v1/sessions", json={"title": "Screenshot artifact"}).json()
    asset = client.post(
        "/api/v1/assets",
        json={
            "session_id": session["session_id"],
            "object_type": "teapot",
            "label": "screenshot teapot",
        },
    ).json()

    response = client.post(
        "/api/v1/screenshots",
        data={
            "session_id": session["session_id"],
            "asset_id": asset["asset_id"],
            "metadata": json.dumps({"trigger": "annotation_commit", "width": 640}),
        },
        files={
            "file": (
                "viewport.jpg",
                b"\xff\xd8\xff\xe0" + b"\x00" * 64,
                "image/jpeg",
            )
        },
    )
    assert response.status_code == 200
    artifact = response.json()
    assert artifact["type"] == "viewport_screenshot"
    assert artifact["url"].startswith("/files/screenshots/")
    assert artifact["metadata"]["trigger"] == "annotation_commit"
    assert artifact["metadata"]["captured_from"] == "client_webgl"

    image_file = client.get(artifact["url"])
    assert image_file.status_code == 200
    assert image_file.content.startswith(b"\xff\xd8")

    memory = client.get(f"/api/v1/sessions/{session['session_id']}/memory").json()
    assert any(
        item["type"] == "event:viewport_screenshot_captured"
        for item in memory["structured_memory"]["episodic"]
    )
    assert any(
        item["type"] == "viewport_screenshot"
        and item["source_id"] == artifact["artifact_id"]
        for item in memory["structured_memory"]["working"]
    )


def test_smooth_operation_artifact_records_sculpt_event_memory_and_planner_features() -> None:
    session = client.post("/api/v1/sessions", json={"title": "Smooth artifact"}).json()
    asset = client.post(
        "/api/v1/assets",
        json={
            "session_id": session["session_id"],
            "object_type": "snowman",
            "label": "smooth snowman",
            "parts": [{"part_id": "body", "label": "body"}],
        },
    ).json()

    response = client.post(
        "/api/v1/smooth-operations",
        json={
            "session_id": session["session_id"],
            "asset_id": asset["asset_id"],
            "part_id": "body",
            "label": "body",
            "region": {
                "type": "local_surface_patch",
                "target": "part_surface",
                "normalized_bbox": [0.34, 0.36, 0.63, 0.62],
            },
            "brush": {
                "kind": "smoothing_brush",
                "radius": 0.18,
                "falloff": "soft",
                "path": [{"x": 0.42, "y": 0.48}, {"x": 0.56, "y": 0.49}],
            },
            "parameters": {"strength": 0.64, "iterations": 2, "preserve_boundary": True},
            "preview": {"geometry_job_id": "geom_smooth_test", "preview_mesh_url": "/files/geometry/preview.obj"},
            "metrics": {"local_region_coverage": 0.16},
            "metadata": {"source": "test"},
        },
    )
    assert response.status_code == 200
    artifact = response.json()
    assert artifact["type"] == "smooth_operation"
    assert artifact["url"].startswith("/files/smooth-operations/")
    assert artifact["metadata"]["strength"] == 0.64
    assert artifact["metadata"]["preserve_boundary"] is True

    operation_file = client.get(artifact["url"])
    assert operation_file.status_code == 200
    operation_payload = operation_file.json()
    assert operation_payload["brush"]["kind"] == "smoothing_brush"
    assert operation_payload["parameters"]["preserve_boundary"] is True

    memory = client.get(f"/api/v1/sessions/{session['session_id']}/memory").json()
    assert any(
        item["type"] == "event:smooth_operation_committed"
        for item in memory["structured_memory"]["episodic"]
    )
    assert any(
        item["type"] == "smooth_operation"
        and item["source_id"] == artifact["artifact_id"]
        and "local_geometry" in item["tags"]
        for item in memory["structured_memory"]["working"]
    )

    interpret_response = client.post(
        "/api/v1/interaction/interpret",
        json={
            "type": "smooth_end",
            "event_id": "evt_smooth_operation_artifact",
            "session_id": session["session_id"],
            "timestamp": "2026-07-06T00:00:00Z",
            "payload": {
                "asset_id": asset["asset_id"],
                "part_id": "body",
                "intent_text": "make the body softer and smoother",
                "smooth_operation_artifact_id": artifact["artifact_id"],
                "smooth_operation_url": artifact["url"],
                "smooth_region": {
                    "type": "local_surface_patch",
                    "target": "part_surface",
                    "normalized_bbox": [0.34, 0.36, 0.63, 0.62],
                },
                "smooth_strength": 0.64,
                "smooth_brush_radius": 0.18,
                "smooth_preserve_boundary": True,
                "smooth_preview_mesh_url": "/files/geometry/preview.obj",
                "smooth_geometry_job_id": "geom_smooth_test",
            },
        },
    )
    assert interpret_response.status_code == 200
    interpretation = interpret_response.json()
    assert interpretation["primary_intent"] == "deform_surface"
    signals = interpretation["features"]["signals"]
    assert signals["visual_context"]["smooth_operation_artifact_id"] == artifact["artifact_id"]
    assert signals["visual_context"]["smooth_operation_url"] == artifact["url"]
    assert signals["visual_context"]["smooth_geometry_job_id"] == "geom_smooth_test"
    assert signals["geometric"]["smooth_strength"] == 0.64
    assert signals["geometric"]["smooth_brush_radius"] == 0.18
    assert signals["geometric"]["smooth_preserve_boundary"] is True
    assert signals["semantic"]["smooth_operation_artifact_id"] == artifact["artifact_id"]


def test_primitive_addition_artifact_records_add_event_memory_and_planner_features() -> None:
    session = client.post("/api/v1/sessions", json={"title": "Primitive addition"}).json()
    asset = client.post(
        "/api/v1/assets",
        json={
            "session_id": session["session_id"],
            "object_type": "snowman",
            "label": "add snowman",
            "parts": [{"part_id": "base", "label": "base"}],
        },
    ).json()

    response = client.post(
        "/api/v1/primitive-additions",
        json={
            "session_id": session["session_id"],
            "asset_id": asset["asset_id"],
            "part_id": "base",
            "primitive": "sphere",
            "transform": {"position": [0, 0.6, 0], "scale": [0.25, 0.25, 0.25], "rotation": [0, 0, 0]},
            "relation": {"type": "attached_to_part_or_nearby", "target_part_id": "base"},
            "constraints": ["preserve object identity"],
            "preview": {"local_preview_only": True},
            "metadata": {"source": "test"},
        },
    )
    assert response.status_code == 200
    artifact = response.json()
    assert artifact["type"] == "primitive_addition"
    assert artifact["url"].startswith("/files/primitive-additions/")
    assert artifact["metadata"]["primitive"] == "sphere"

    primitive_file = client.get(artifact["url"])
    assert primitive_file.status_code == 200
    primitive_payload = primitive_file.json()
    assert primitive_payload["primitive"] == "sphere"
    assert primitive_payload["relation"]["target_part_id"] == "base"

    memory = client.get(f"/api/v1/sessions/{session['session_id']}/memory").json()
    assert any(
        item["type"] == "event:primitive_addition_committed"
        for item in memory["structured_memory"]["episodic"]
    )
    assert any(
        item["type"] == "primitive_addition"
        and item["source_id"] == artifact["artifact_id"]
        and "3d_geometry" in item["tags"]
        for item in memory["structured_memory"]["working"]
    )

    interpret_response = client.post(
        "/api/v1/interaction/interpret",
        json={
            "type": "primitive_add_intent",
            "event_id": "evt_primitive_addition_artifact",
            "session_id": session["session_id"],
            "timestamp": "2026-07-06T00:00:00Z",
            "payload": {
                "asset_id": asset["asset_id"],
                "part_id": "base",
                "intent_text": "add a round stable base",
                "primitive": "sphere",
                "primitive_addition_artifact_id": artifact["artifact_id"],
                "primitive_addition_url": artifact["url"],
                "primitive_transform": {"position": [0, 0.6, 0], "scale": [0.25, 0.25, 0.25]},
                "primitive_relation": {"type": "attached_to_part_or_nearby", "target_part_id": "base"},
                "primitive_constraints": ["preserve object identity"],
            },
        },
    )
    assert interpret_response.status_code == 200
    interpretation = interpret_response.json()
    assert interpretation["primary_intent"] == "deform_surface"
    signals = interpretation["features"]["signals"]
    assert signals["visual_context"]["primitive_addition_artifact_id"] == artifact["artifact_id"]
    assert signals["visual_context"]["primitive_addition_url"] == artifact["url"]
    assert signals["semantic"]["primitive"] == "sphere"
    assert signals["semantic"]["primitive_addition_artifact_id"] == artifact["artifact_id"]
    assert signals["geometric"]["primitive_relation"]["target_part_id"] == "base"


def test_drag_operation_artifact_records_drag_event_memory_and_planner_features() -> None:
    session = client.post("/api/v1/sessions", json={"title": "Drag operation"}).json()
    asset = client.post(
        "/api/v1/assets",
        json={
            "session_id": session["session_id"],
            "object_type": "snowman",
            "label": "drag snowman",
            "parts": [{"part_id": "arm", "label": "arm"}],
        },
    ).json()

    response = client.post(
        "/api/v1/drag-operations",
        json={
            "session_id": session["session_id"],
            "asset_id": asset["asset_id"],
            "part_id": "arm",
            "label": "arm",
            "drag": {
                "start": [0.0, 0.0, 0.0],
                "end": [0.42, 0.12, 0.0],
                "vector": [0.42, 0.12, 0.0],
                "space": "world",
                "influence_radius": 0.25,
            },
            "region": {"type": "local_part_or_region", "target": "part", "part_id": "arm"},
            "preview": {"geometry_job_id": "geom_drag_test", "preview_mesh_url": "/files/geometry/drag_preview.obj"},
            "metrics": {"drag_length": 0.4368, "direction_relation": "outward_from_part_center"},
            "metadata": {"source": "test"},
        },
    )
    assert response.status_code == 200
    artifact = response.json()
    assert artifact["type"] == "drag_operation"
    assert artifact["url"].startswith("/files/drag-operations/")
    assert artifact["metadata"]["drag_length"] == 0.4368

    drag_file = client.get(artifact["url"])
    assert drag_file.status_code == 200
    drag_payload = drag_file.json()
    assert drag_payload["drag"]["influence_radius"] == 0.25
    assert drag_payload["preview"]["geometry_job_id"] == "geom_drag_test"

    memory = client.get(f"/api/v1/sessions/{session['session_id']}/memory").json()
    assert any(
        item["type"] == "event:drag_operation_committed"
        for item in memory["structured_memory"]["episodic"]
    )
    assert any(
        item["type"] == "drag_operation"
        and item["source_id"] == artifact["artifact_id"]
        and "3d_transform" in item["tags"]
        for item in memory["structured_memory"]["working"]
    )

    interpret_response = client.post(
        "/api/v1/interaction/interpret",
        json={
            "type": "drag_end",
            "event_id": "evt_drag_operation_artifact",
            "session_id": session["session_id"],
            "timestamp": "2026-07-06T00:00:00Z",
            "payload": {
                "asset_id": asset["asset_id"],
                "part_id": "arm",
                "intent_text": "pull the arm outward",
                "drag_operation_artifact_id": artifact["artifact_id"],
                "drag_operation_url": artifact["url"],
                "drag_preview_mesh_url": "/files/geometry/drag_preview.obj",
                "drag_geometry_job_id": "geom_drag_test",
                "drag": {
                    "start": [0.0, 0.0, 0.0],
                    "end": [0.42, 0.12, 0.0],
                    "space": "world",
                    "influence_radius": 0.25,
                },
            },
        },
    )
    assert interpret_response.status_code == 200
    interpretation = interpret_response.json()
    assert interpretation["primary_intent"] == "extend_part"
    signals = interpretation["features"]["signals"]
    assert signals["geometric"]["drag_operation_artifact_id"] == artifact["artifact_id"]
    assert signals["geometric"]["drag_geometry_job_id"] == "geom_drag_test"
    assert signals["visual_context"]["drag_operation_url"] == artifact["url"]
    assert signals["semantic"]["drag_operation_artifact_id"] == artifact["artifact_id"]


def test_focus_observation_artifact_records_hover_attention_memory_and_planner_features() -> None:
    session = client.post("/api/v1/sessions", json={"title": "Focus observation"}).json()
    asset = client.post(
        "/api/v1/assets",
        json={
            "session_id": session["session_id"],
            "object_type": "snowman",
            "label": "focus snowman",
            "parts": [{"part_id": "head", "label": "head"}],
        },
    ).json()

    response = client.post(
        "/api/v1/focus-observations",
        json={
            "session_id": session["session_id"],
            "asset_id": asset["asset_id"],
            "part_id": "head",
            "label": "head",
            "observation": {"focus_source": "toolbar_hover_probe", "selection_type": "part"},
            "viewport": {"display_mode": "parts", "camera_position": [0, 1.5, 4]},
            "metrics": {"dwell_ms": 1200, "confidence": 0.72},
            "metadata": {"source": "test"},
        },
    )
    assert response.status_code == 200
    artifact = response.json()
    assert artifact["type"] == "focus_observation"
    assert artifact["url"].startswith("/files/focus-observations/")
    assert artifact["metrics"]["dwell_ms"] == 1200

    focus_file = client.get(artifact["url"])
    assert focus_file.status_code == 200
    focus_payload = focus_file.json()
    assert focus_payload["observation"]["focus_source"] == "toolbar_hover_probe"
    assert focus_payload["viewport"]["display_mode"] == "parts"

    memory = client.get(f"/api/v1/sessions/{session['session_id']}/memory").json()
    assert any(
        item["type"] == "event:focus_observation_committed"
        for item in memory["structured_memory"]["episodic"]
    )
    assert any(
        item["type"] == "focus_observation"
        and item["source_id"] == artifact["artifact_id"]
        and "attention" in item["tags"]
        for item in memory["structured_memory"]["working"]
    )

    interpret_response = client.post(
        "/api/v1/interaction/interpret",
        json={
            "type": "hover_focus",
            "event_id": "evt_focus_observation_artifact",
            "session_id": session["session_id"],
            "timestamp": "2026-07-06T00:00:00Z",
            "payload": {
                "asset_id": asset["asset_id"],
                "part_id": "head",
                "selected_part_label": "head",
                "focus_observation_artifact_id": artifact["artifact_id"],
                "focus_observation_url": artifact["url"],
                "focus_source": "toolbar_hover_probe",
                "dwell_ms": 1200,
            },
        },
    )
    assert interpret_response.status_code == 200
    interpretation = interpret_response.json()
    assert interpretation["primary_intent"] == "target_part"
    signals = interpretation["features"]["signals"]
    assert signals["geometric"]["focus_observation_artifact_id"] == artifact["artifact_id"]
    assert signals["geometric"]["dwell_ms"] == 1200
    assert signals["semantic"]["focus_observation_artifact_id"] == artifact["artifact_id"]
    assert signals["visual_context"]["focus_observation_url"] == artifact["url"]


def test_benchmark_assets_read_github_pages_picked_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = client.post("/api/v1/sessions", json={"title": "Picked benchmark"}).json()[
        "session_id"
    ]
    monkeypatch.setattr(
        "app.services.storage.benchmark._read_creativeflow_picked_dataset",
        lambda _files_root: {
            "sources": [
                {
                    "id": "src_picked_001",
                    "project": "case_picked",
                    "noun": "lamp",
                    "category": "Furniture & Interior",
                    "image": "https://creativeflow.oss-cn-beijing.aliyuncs.com/creativeflow/v2/case_picked/src_picked_001/source/image_v01.png",
                    "mesh_glb": "https://creativeflow.oss-cn-beijing.aliyuncs.com/creativeflow/v2/case_picked/src_picked_001/source3d/mesh.glb",
                    "mesh_obj": "https://creativeflow.oss-cn-beijing.aliyuncs.com/creativeflow/v2/case_picked/src_picked_001/source3d/mesh.obj",
                    "multiview": "https://creativeflow.oss-cn-beijing.aliyuncs.com/creativeflow/v2/case_picked/src_picked_001/source3d/multiview/grid.png",
                    "relation_count": 1,
                    "target_count": 1,
                    "target_image_count": 1,
                    "target_mesh_count": 1,
                    "relations": [
                        {
                            "id": "rel_picked_001",
                            "label": "preserve identity while migrating toward coral growth",
                            "targets": [
                                {
                                    "id": "target_picked_001",
                                    "text": "lamp with coral branching shade",
                                    "image": "https://creativeflow.oss-cn-beijing.aliyuncs.com/creativeflow/v2/case_picked/src_picked_001/targets/g01-r02/e01-t03/image.png",
                                    "mesh_glb": "https://creativeflow.oss-cn-beijing.aliyuncs.com/creativeflow/v2/case_picked/src_picked_001/targets/g01-r02/e01-t03/mesh.glb",
                                    "mesh_ready": True,
                                }
                            ],
                        }
                    ],
                }
            ]
        },
    )

    assets = client.get("/api/v1/benchmark-assets").json()["assets"]
    benchmark = next(item for item in assets if item["benchmark_id"] == "src_picked_001")
    assert benchmark["benchmark_id"] == "src_picked_001"
    assert benchmark["label"] == "lamp"
    assert benchmark["reference_status"] == "GITHUB_PAGES_PICKED"
    assert benchmark["mesh_url"].endswith("/source3d/mesh.glb")
    assert benchmark["obj_url"].endswith("/source3d/mesh.obj")
    assert benchmark["metadata"]["source"] == "creativeflow_github_pages_picked"
    assert benchmark["metadata"]["asset_kind"] == "github_picked_source"
    # 列表是菜单投影：深层 metadata 由 load 端点携带（下方 load 断言覆盖）。
    assert "creativeflow_tree" not in benchmark["metadata"]
    assert "mesh_glb_key" not in benchmark["metadata"]

    load_response = client.post(
        f"/api/v1/benchmark-assets/{benchmark['benchmark_id']}/load",
        json={"session_id": session_id},
    )
    assert load_response.status_code == 200
    asset = load_response.json()
    assert asset["mesh_url"].endswith("/source3d/mesh.glb")
    assert asset["obj_url"].endswith("/source3d/mesh.obj")
    assert asset["thumbnail_url"].endswith("/source/image_v01.png")
    assert asset["metadata"]["benchmark_metadata"]["picked_dataset_url"].endswith(
        "/data/creativeflow-picked.json"
    )
    assert len(asset["metadata"]["benchmark_metadata"]["relations"]) == 1


def test_benchmark_assets_read_pinpoint_source_relation_target_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = client.post("/api/v1/sessions", json={"title": "Pinpoint benchmark"}).json()[
        "session_id"
    ]
    monkeypatch.setattr("app.services.storage.benchmark._read_creativeflow_picked_dataset", lambda _files_root: {})
    monkeypatch.setattr(
        "app.services.storage.benchmark._read_pinpoint_benchmark_index",
        lambda _files_root: {
            "sources": [
                {
                    "source_id": "src_pinpoint_001",
                    "project_id": "case_pinpoint",
                    "noun_text": "backpack",
                    "source_image_url": "https://creativeflow.oss-cn-beijing.aliyuncs.com/creativeflow/v2/case_pinpoint/src_pinpoint_001/source/image_v01.png",
                    "source_mesh_url": "https://creativeflow.oss-cn-beijing.aliyuncs.com/creativeflow/v2/case_pinpoint/src_pinpoint_001/source3d/mesh.glb",
                    "preview_image_url": "https://creativeflow.oss-cn-beijing.aliyuncs.com/creativeflow/v2/case_pinpoint/src_pinpoint_001/targets/g01-r02/e01-t03/image.png",
                    "target_count": 1,
                    "target_mesh_ready_count": 1,
                    "relation_count": 1,
                    "benchmark_status": "candidate",
                    "source_status": "MESH_READY",
                }
            ]
        },
    )

    class FakeOssResponse:
        def __enter__(self) -> "FakeOssResponse":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self) -> bytes:
            return b"glTF pinpoint"

    def fake_urlopen(url: str, timeout: int = 30, context: object | None = None) -> FakeOssResponse:
        assert url.endswith("/targets/g01-r02/e01-t03/mesh.glb")
        return FakeOssResponse()

    monkeypatch.setattr("app.services.storage.benchmark.urlopen", fake_urlopen)

    assets = client.get("/api/v1/benchmark-assets").json()["assets"]
    benchmark = next(
        item
        for item in assets
        if item["benchmark_id"] == "pinpoint:src_pinpoint_001:g01-r02:e01-t03"
    )
    assert benchmark["benchmark_id"] == "pinpoint:src_pinpoint_001:g01-r02:e01-t03"
    assert benchmark["reference_status"] == "PINPOINT_BENCHMARK_TREE"
    assert benchmark["metadata"]["asset_kind"] == "pinpoint_target"
    # 列表是菜单投影：深层 creativeflow_tree 由 load 端点携带（下方 load 断言覆盖）。
    assert "creativeflow_tree" not in benchmark["metadata"]

    load_response = client.post(
        f"/api/v1/benchmark-assets/{benchmark['benchmark_id']}/load",
        json={"session_id": session_id},
    )
    assert load_response.status_code == 200
    asset = load_response.json()
    assert asset["mesh_url"].endswith("/source.glb")
    assert asset["metadata"]["materialized_source"] == "oss_glb"
    assert client.get(asset["mesh_url"]).content == b"glTF pinpoint"


def test_benchmark_assets_list_reads_creativeflow_oss_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = client.post("/api/v1/sessions", json={"title": "Benchmark load"}).json()[
        "session_id"
    ]
    monkeypatch.setattr("app.services.storage.benchmark._read_creativeflow_picked_dataset", lambda _files_root: {})
    monkeypatch.setattr("app.services.storage.benchmark._read_pinpoint_benchmark_index", lambda _files_root: {})

    class FakeOssResponse:
        def __enter__(self) -> "FakeOssResponse":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self) -> bytes:
            return b"glTF benchmark"

    def fake_urlopen(url: str, timeout: int = 30, context: object | None = None) -> FakeOssResponse:
        assert url.endswith("/mesh.glb")
        return FakeOssResponse()

    monkeypatch.setattr("app.services.storage.benchmark.urlopen", fake_urlopen)

    list_response = client.get("/api/v1/benchmark-assets")

    assert list_response.status_code == 200
    assets = list_response.json()["assets"]
    assert assets
    assert any(item["object_type"] == "ankle boot" for item in assets)
    benchmark = next(
        item
        for item in assets
        if item["object_type"] == "ankle boot"
        and item["metadata"].get("asset_kind") == "native_generated_target"
    )
    assert benchmark["model_available"] is True
    assert benchmark["mesh_url"] is None
    assert benchmark["obj_url"] is None
    assert benchmark["metadata"]["source"] == "creativeflow_benchmark_oss_manifest"
    # 列表是菜单投影：只保留分组所需 metadata，避免 16MB 大响应拖慢初始化；
    # 完整 metadata（creativeflow_tree / texture 规则等）由 load 端点按 id 重新发现。
    assert "creativeflow_tree" not in benchmark["metadata"]
    assert "texture_index_rule" not in benchmark["metadata"]

    load_response = client.post(
        f"/api/v1/benchmark-assets/{benchmark['benchmark_id']}/load",
        json={"session_id": session_id},
    )

    assert load_response.status_code == 200
    asset = load_response.json()
    assert asset["session_id"] == session_id
    assert asset["object_type"] == "ankle boot"
    assert asset["mesh_url"].startswith("/files/assets/")
    assert asset["mesh_url"].endswith("/source.glb")
    assert asset["obj_url"] is None
    assert asset["metadata"]["source"] == "benchmark"
    assert asset["metadata"]["materialized_from_remote"] is True
    assert asset["metadata"]["materialized_source"] == "oss_glb"
    assert asset["metadata"]["remote_asset"] is None
    assert asset["metadata"]["benchmark_metadata"]["source"] == "creativeflow_benchmark_oss_manifest"
    file_response = client.get(asset["mesh_url"])
    assert file_response.status_code == 200
    assert file_response.content == b"glTF benchmark"


def test_benchmark_asset_load_falls_back_to_oss(monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = client.post("/api/v1/sessions", json={"title": "Benchmark OSS fallback"}).json()[
        "session_id"
    ]
    monkeypatch.setattr("app.services.storage.benchmark._read_creativeflow_picked_dataset", lambda _files_root: {})
    monkeypatch.setattr("app.services.storage.benchmark._read_pinpoint_benchmark_index", lambda _files_root: {})
    benchmark = next(
        item
        for item in client.get("/api/v1/benchmark-assets").json()["assets"]
        if item["benchmark_id"].startswith("native15:")
    )

    async def fake_get_artifact_file(path: str) -> tuple[bytes, str]:
        raise RuntimeError("remote unavailable")

    class FakeOssResponse:
        def __enter__(self) -> "FakeOssResponse":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def __init__(self, data: bytes) -> None:
            self.data = data

        def read(self) -> bytes:
            return self.data

    def fake_urlopen(url: str, timeout: int = 30, context: object | None = None) -> FakeOssResponse:
        assert url.startswith("https://creativeflow.oss-cn-beijing.aliyuncs.com/")
        assert timeout == 30
        assert context is not None
        if url.endswith("/source.png"):
            return FakeOssResponse(b"PNG")
        return FakeOssResponse(b"o oss-benchmark\nmtllib material.mtl\nusemtl material_0\nv 1 0 0\n")

    monkeypatch.setattr(remote_worker_adapter, "get_artifact_file", fake_get_artifact_file)
    monkeypatch.setattr("app.services.storage.benchmark.urlopen", fake_urlopen)

    load_response = client.post(
        f"/api/v1/benchmark-assets/{benchmark['benchmark_id']}/load",
        json={"session_id": session_id},
    )

    assert load_response.status_code == 200
    asset = load_response.json()
    assert asset["obj_url"].startswith("/files/assets/")
    assert asset["metadata"]["materialized_from_remote"] is True
    assert asset["metadata"]["materialized_source"] == "oss_obj"
    assert asset["metadata"]["material_sidecars"] == ["material.mtl", "source.png"]
    file_response = client.get(asset["obj_url"])
    assert b"mtllib material.mtl" in file_response.content
    assert b"map_Kd source.png" in client.get(asset["obj_url"].replace("source.obj", "material.mtl")).content
    assert client.get(asset["obj_url"].replace("source.obj", "source.png")).content == b"PNG"


def test_benchmark_asset_load_uses_explicit_texture_index(monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = client.post("/api/v1/sessions", json={"title": "Benchmark texture index"}).json()[
        "session_id"
    ]
    monkeypatch.setattr("app.services.storage.benchmark._read_creativeflow_picked_dataset", lambda _files_root: {})
    monkeypatch.setattr("app.services.storage.benchmark._read_pinpoint_benchmark_index", lambda _files_root: {})
    manifest = json.loads(
        (Path(__file__).resolve().parents[1] / "storage" / "benchmark" / "creativeflow_oss_manifest.json").read_text()
    )
    manifest["native_sources"][0]["source_material_mtl_key"] = "indexed/material.mtl"
    manifest["native_sources"][0]["source_texture_key"] = "indexed/texture.png"

    async def fake_get_artifact_file(path: str) -> tuple[bytes, str]:
        if path.endswith(".glb"):
            raise RuntimeError("no glb for this test")
        return b"o indexed\nmtllib material.mtl\nusemtl material_0\nv 0 0 0\n", "text/plain"

    class FakeOssResponse:
        def __init__(self, data: bytes) -> None:
            self.data = data

        def __enter__(self) -> "FakeOssResponse":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self) -> bytes:
            return self.data

    def fake_urlopen(url: str, timeout: int = 30, context: object | None = None) -> FakeOssResponse:
        if url.endswith("indexed/material.mtl"):
            return FakeOssResponse(b"newmtl material_0\nmap_Kd texture.png\n")
        if url.endswith("indexed/texture.png"):
            return FakeOssResponse(b"PNG")
        raise AssertionError(url)

    monkeypatch.setattr(remote_worker_adapter, "get_artifact_file", fake_get_artifact_file)
    monkeypatch.setattr("app.services.storage.benchmark._read_benchmark_oss_manifest", lambda _files_root: manifest)
    monkeypatch.setattr("app.services.storage.benchmark.urlopen", fake_urlopen)

    benchmark = next(
        item
        for item in client.get("/api/v1/benchmark-assets").json()["assets"]
        if item["benchmark_id"].startswith("native15:")
    )
    load_response = client.post(
        f"/api/v1/benchmark-assets/{benchmark['benchmark_id']}/load",
        json={"session_id": session_id},
    )

    assert load_response.status_code == 200
    asset = load_response.json()
    assert asset["metadata"]["material_sidecars"] == ["material.mtl", "texture.png"]
    assert client.get(asset["obj_url"].replace("source.obj", "material.mtl")).content == b"newmtl material_0\nmap_Kd texture.png\n"
    assert client.get(asset["obj_url"].replace("source.obj", "texture.png")).content == b"PNG"


def test_websocket_interaction_interpretation() -> None:
    session_id = client.post("/api/v1/sessions", json={"title": "WS smoke"}).json()[
        "session_id"
    ]

    with client.websocket_connect(f"/ws/sessions/{session_id}") as websocket:
        assert websocket.receive_json()["type"] == "ack"
        websocket.send_json(
            {
                "type": "drag_end",
                "event_id": "evt_test_drag",
                "session_id": session_id,
                "timestamp": "2026-07-06T00:00:00Z",
                "payload": {
                    "asset_id": "asset_demo",
                    "part_id": "handle",
                    "drag": {
                        "start": [0.0, 0.0, 0.0],
                        "end": [0.4, 0.1, 0.0],
                        "space": "world",
                        "influence_radius": 0.25,
                    },
                },
            }
        )
        assert websocket.receive_json()["type"] == "ack"
        interpretation = websocket.receive_json()
        assert interpretation["type"] == "interaction_interpretation"
        assert interpretation["payload"]["primary_intent"] == "extend_part"
        signals = interpretation["payload"]["features"]["signals"]
        assert signals["geometric"]["drag_length"] > 0
        assert signals["interaction"]["is_drag"] is True
        assert "semantic" in signals
        perception = websocket.receive_json()
        assert perception["type"] == "perception_updated"
        stage = websocket.receive_json()
        assert stage["type"] == "stage_update"
        assert stage["payload"]["phase"] == "drag_modification"


def test_http_interaction_interpretation_exposes_predictor_boundary() -> None:
    session_id = client.post("/api/v1/sessions", json={"title": "HTTP intent"}).json()[
        "session_id"
    ]

    response = client.post(
        "/api/v1/interaction/interpret",
        json={
            "type": "brush_end",
            "event_id": "evt_http_brush",
            "session_id": session_id,
            "timestamp": "2026-07-06T00:00:00Z",
            "payload": {
                "asset_id": "asset_demo",
                "selection": {
                    "type": "brush",
                    "part_id": "grille",
                    "label": "front grille",
                    "bbox": [120, 82, 360, 264],
                },
                "intent_text": "replace this with woven metal",
                "viewport": {"camera": "front"},
            },
        },
    )

    assert response.status_code == 200
    interpretation = response.json()
    assert interpretation["primary_intent"] == "replace_region"
    assert interpretation["predictor"] == "rule_based_multisignal"
    assert interpretation["predictor_metadata"]["vlm_ready"] is True
    assert "visual_context" in interpretation["features"]["signals"]

    memory = client.get(f"/api/v1/sessions/{session_id}/memory").json()
    assert memory["recent_interpretations"][-1]["predictor"] == "rule_based_multisignal"
    assert memory["stage"]["phase"] == "local_replacement"
    assert any(
        item["type"] == "event:brush_end"
        for item in memory["structured_memory"]["episodic"]
    )
    assert any(
        item["type"] == "interpretation"
        and item["content"]["primary_intent"] == "replace_region"
        for item in memory["structured_memory"]["working"]
    )

    working_memory = client.get(
        f"/api/v1/sessions/{session_id}/memories?category=working"
    )
    assert working_memory.status_code == 200
    assert any(
        item["content"]["primary_intent"] == "replace_region"
        for item in working_memory.json()["memories"]
    )


def test_planner_interpretation_decision_control_gate_records_memory_and_stage() -> None:
    session_id = client.post("/api/v1/sessions", json={"title": "Planner gate"}).json()[
        "session_id"
    ]

    interpretation_response = client.post(
        "/api/v1/interaction/interpret",
        json={
            "type": "intent_text_changed",
            "event_id": "evt_planner_gate_text",
            "session_id": session_id,
            "timestamp": "2026-07-06T00:00:00Z",
            "payload": {
                "asset_id": "asset_gate",
                "intent_text": "make the whole snowman more cute",
            },
        },
    )
    assert interpretation_response.status_code == 200
    interpretation = interpretation_response.json()

    accept_response = client.post(
        f"/api/v1/interpretations/{interpretation['interpretation_id']}/decision",
        json={
            "session_id": session_id,
            "decision": "accepted",
            "reason": "this matches my current intention",
            "metadata": {"surface": "perception_panel"},
        },
    )
    assert accept_response.status_code == 200
    accepted = accept_response.json()
    assert accepted["decision"] == "accepted"
    assert accepted["updated_stage"]["current_goal"].startswith("Accepted planner intent:")
    assert (
        f"planner_interpretation_accepted:{interpretation['interpretation_id']}"
        in accepted["updated_stage"]["evidence"]
    )

    memory = client.get(f"/api/v1/sessions/{session_id}/memories?category=reflective")
    assert memory.status_code == 200
    rows = memory.json()["memories"]
    assert any(
        item["type"] == "planner_interpretation_accepted"
        and item["source_id"] == interpretation["interpretation_id"]
        and item["content"]["reason"] == "this matches my current intention"
        for item in rows
    )

    reject_response = client.post(
        f"/api/v1/interpretations/{interpretation['interpretation_id']}/decision",
        json={
            "session_id": session_id,
            "decision": "rejected",
            "reason": "the target is wrong",
        },
    )
    assert reject_response.status_code == 200
    rejected = reject_response.json()
    assert rejected["decision"] == "rejected"
    assert rejected["updated_stage"]["suggested_action"] == "revise_intent_or_continue_editing"
    assert "rejected" in rejected["updated_stage"]["evidence"][-1]


def test_cute_text_intent_maps_to_whole_object_exploration() -> None:
    session_id = client.post("/api/v1/sessions", json={"title": "Cute text"}).json()[
        "session_id"
    ]
    response = client.post(
        "/api/v1/interaction/interpret",
        json={
            "type": "intent_text_changed",
            "event_id": "evt_cute_text",
            "session_id": session_id,
            "timestamp": "2026-07-06T00:00:00Z",
            "payload": {
                "asset_id": "asset_cute",
                "intent_text": "I want this snowman become more cute",
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["primary_intent"] == "explore_shape"
    assert body["confidence"] >= 0.6
    assert "whole-object aesthetic" in body["evidence"][0]


def test_cross_domain_directions_use_planner_control_gate_context() -> None:
    session = client.post("/api/v1/sessions", json={"title": "Gate-aware divergence"}).json()
    asset = client.post(
        "/api/v1/assets",
        json={
            "session_id": session["session_id"],
            "object_type": "snowman",
            "label": "gate snowman",
        },
    ).json()

    interpretation = client.post(
        "/api/v1/interaction/interpret",
        json={
            "type": "intent_text_changed",
            "event_id": "evt_gate_xdom_text",
            "session_id": session["session_id"],
            "timestamp": "2026-07-06T00:00:00Z",
            "payload": {
                "asset_id": asset["asset_id"],
                "intent_text": "make the whole snowman more cute",
            },
        },
    ).json()

    accept_response = client.post(
        f"/api/v1/interpretations/{interpretation['interpretation_id']}/decision",
        json={"session_id": session["session_id"], "decision": "accepted"},
    )
    assert accept_response.status_code == 200

    directions_response = client.post(
        "/api/v1/directions/cross-domain",
        json={
            "session_id": session["session_id"],
            "asset_id": asset["asset_id"],
            "source_summary": "more cute whole-object prompt words",
            "dimensions": ["Aesthetic", "Structural"],
            "candidate_count": 2,
            "metadata": {
                "image_refs": ["/files/references/ref_gate.png"],
                "reference_images": [
                    {
                        "artifact_id": "art_gate_ref",
                        "url": "/files/references/ref_gate.png",
                        "role": "shape_reference",
                    }
                ],
            },
        },
    )
    assert directions_response.status_code == 200
    body = directions_response.json()
    gate = body["metadata"]["planner_control_gate"]
    assert gate["status"] == "confirmed"
    assert gate["confirmed_intent"]["interpretation_id"] == interpretation["interpretation_id"]
    assert any("planner_gate=confirmed" == item for item in body["evidence"])
    assert body["directions"][0]["metadata"]["planner_control_gate"]["status"] == "confirmed"
    assert body["metadata"]["image_refs"] == ["/files/references/ref_gate.png"]
    assert body["directions"][0]["metadata"]["image_ref_count"] == 1
    assert any(
        "honor confirmed planner intent" in constraint
        for constraint in body["directions"][0]["constraints"]
    )

    reject_response = client.post(
        f"/api/v1/interpretations/{interpretation['interpretation_id']}/decision",
        json={"session_id": session["session_id"], "decision": "rejected"},
    )
    assert reject_response.status_code == 200

    rejected_directions = client.post(
        "/api/v1/directions/cross-domain",
        json={
            "session_id": session["session_id"],
            "asset_id": asset["asset_id"],
            "source_summary": "more cute whole-object prompt words",
            "dimensions": ["Aesthetic"],
            "candidate_count": 1,
        },
    ).json()
    rejected_gate = rejected_directions["metadata"]["planner_control_gate"]
    assert rejected_gate["status"] == "rejected"
    assert rejected_gate["rejected_intent"]["interpretation_id"] == interpretation["interpretation_id"]
    assert any(
        "do not act on rejected planner intent" in constraint
        for constraint in rejected_directions["directions"][0]["constraints"]
    )


def test_planner_decision_can_auto_suggest_directions() -> None:
    session = client.post("/api/v1/sessions", json={"title": "Auto suggest after accept"}).json()
    asset = client.post(
        "/api/v1/assets",
        json={
            "session_id": session["session_id"],
            "object_type": "snowman",
            "label": "auto suggest snowman",
        },
    ).json()
    interpretation = client.post(
        "/api/v1/interaction/interpret",
        json={
            "type": "intent_text_changed",
            "event_id": "evt_auto_suggest_text",
            "session_id": session["session_id"],
            "payload": {
                "asset_id": asset["asset_id"],
                "intent_text": "make the whole snowman more cute",
            },
        },
    ).json()

    response = client.post(
        f"/api/v1/interpretations/{interpretation['interpretation_id']}/decision",
        json={
            "session_id": session["session_id"],
            "decision": "accepted",
            "metadata": {
                "auto_suggest_directions": True,
                "source_summary": "confirmed cute snowman direction",
                "dimensions": ["aesthetic", "structural"],
                "direction_count": 1,
                "preserved_constraints": ["preserve snowman identity"],
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["suggested_directions"]
    assert body["direction_response"]["metadata"]["direction_endpoint"] == "suggested_analogy_directions"
    assert body["direction_response"]["metadata"]["planner_control_gate"]["status"] == "confirmed"
    assert body["suggested_directions"][0]["metadata"]["prompt_tokens"]


def test_vlm_intent_predictor_consumes_remote_hypotheses(monkeypatch) -> None:
    predictor = VLMIntentPredictor("http://vlm.local/intent")
    captured: dict[str, object] = {}

    def fake_post_json(payload: dict[str, object]) -> dict[str, object]:
        captured.update(payload)
        return {
            "hypotheses": [
                {
                    "intent": "refine_boundary",
                    "confidence": 0.91,
                    "evidence": ["VLM saw a brush close to the existing part boundary."],
                }
            ]
        }

    monkeypatch.setattr(predictor, "_post_json", fake_post_json)
    event = UserEvent(
        type="brush_end",
        event_id="evt_vlm",
        session_id="sess_vlm",
        payload={"intent_text": "clean up this edge"},
    )
    prediction = predictor.predict(
        event,
        {
            "signals": {
                "geometric": {"bbox": [0, 0, 100, 80]},
                "semantic": {"part_label": "front grille"},
            },
            "intent_text": "clean up this edge",
        },
    )

    assert prediction.predictor == "vlm_multisignal"
    assert prediction.metadata["fallback_used"] is False
    assert prediction.hypotheses[0].intent == "refine_boundary"
    assert prediction.hypotheses[0].confidence == 0.91
    assert "rule_based_prior" in captured
    assert captured["valid_intents"]


def test_vlm_intent_predictor_supports_openai_chat_completions(monkeypatch) -> None:
    predictor = VLMIntentPredictor("http://vlm.local/v1/chat/completions")
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "hypotheses": [
                                            {
                                                "intent": "explore_shape",
                                                "confidence": 0.82,
                                                "evidence": ["Chat model understood the submitted episode."],
                                            }
                                        ]
                                    }
                                )
                            }
                        }
                    ]
                }
            ).encode()

    def fake_urlopen(request, timeout):
        captured.update(json.loads(request.data.decode()))
        return FakeResponse()

    monkeypatch.setattr(predictor_module.urllib.request, "urlopen", fake_urlopen)
    prediction = predictor.predict(
        UserEvent(
            type="intent_episode_submitted",
            event_id="evt_chat_vlm",
            session_id="sess_chat_vlm",
            payload={"text": "make this snowman cuter"},
        ),
        {"intent_text": "make this snowman cuter"},
    )

    assert captured["model"] == "qwen3-planner"
    assert captured["messages"][0]["role"] == "system"
    assert prediction.metadata["fallback_used"] is False
    assert prediction.hypotheses[0].intent == "explore_shape"
    assert prediction.hypotheses[0].confidence == 0.82


def test_vlm_intent_predictor_falls_back_to_rules(monkeypatch) -> None:
    predictor = VLMIntentPredictor("http://vlm.local/intent")

    def fail_post_json(payload: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("offline")

    monkeypatch.setattr(predictor, "_post_json", fail_post_json)
    event = UserEvent(
        type="brush_end",
        event_id="evt_vlm_fallback",
        session_id="sess_vlm",
        payload={"intent_text": "replace this with woven metal"},
    )

    prediction = predictor.predict(event, {"intent_text": "replace this with woven metal"})

    assert prediction.predictor == "rule_based_multisignal"
    assert prediction.metadata["fallback_used"] is True
    assert "vlm_error" in prediction.metadata
    assert prediction.hypotheses[0].intent == "replace_region"


def test_refine_boundary_returns_executable_boundary_generation_suggestion() -> None:
    session_id = client.post("/api/v1/sessions", json={"title": "Boundary refine"}).json()[
        "session_id"
    ]

    payload = {
        "asset_id": "asset_demo",
        "selection": {
            "type": "brush",
            "part_id": "grille",
            "label": "front grille",
            "bbox": [120, 82, 360, 264],
        },
        "intent_text": "clean up this edge and preserve the boundary",
    }
    for index in range(3):
        response = client.post(
            "/api/v1/interaction/interpret",
            json={
                "type": "brush_end",
                "event_id": f"evt_refine_boundary_{index}",
                "session_id": session_id,
                "timestamp": "2026-07-06T00:00:00Z",
                "payload": payload,
            },
        )
        assert response.status_code == 200

    body = response.json()
    assert body["primary_intent"] == "refine_boundary"
    suggestion = body["suggested_assistance"][0]
    assert suggestion["type"] == "generate"
    assert suggestion["mode"] == "replace"
    assert suggestion["metadata"]["suggested_next_action"] == "generate_boundary_refinements"
    assert suggestion["metadata"]["preserve_boundary"] is True


def test_drag_end_returns_executable_drag_generation_suggestion() -> None:
    session_id = client.post("/api/v1/sessions", json={"title": "Drag action"}).json()[
        "session_id"
    ]

    response = client.post(
        "/api/v1/interaction/interpret",
        json={
            "type": "drag_end",
            "event_id": "evt_drag_action",
            "session_id": session_id,
            "timestamp": "2026-07-06T00:00:00Z",
            "payload": {
                "asset_id": "asset_demo",
                "part_id": "grille",
                "drag": {
                    "start": [0.0, 0.0, 0.0],
                    "end": [0.42, 0.12, 0.0],
                    "space": "world",
                    "influence_radius": 0.25,
                },
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["primary_intent"] == "extend_part"
    suggestion = body["suggested_assistance"][0]
    assert suggestion["type"] == "generate"
    assert suggestion["mode"] == "drag_regenerate"


def test_websocket_brush_interpretation_returns_generate_suggestion() -> None:
    session_id = client.post("/api/v1/sessions", json={"title": "WS brush"}).json()[
        "session_id"
    ]

    with client.websocket_connect(f"/ws/sessions/{session_id}") as websocket:
        assert websocket.receive_json()["type"] == "ack"
        websocket.send_json(
            {
                "type": "brush_end",
                "event_id": "evt_test_brush",
                "session_id": session_id,
                "timestamp": "2026-07-06T00:00:00Z",
                "payload": {
                    "asset_id": "asset_demo",
                    "selection": {
                        "type": "brush",
                        "part_id": "grille",
                        "label": "front grille",
                        "bbox": [120, 82, 360, 264],
                    },
                    "intent_text": "make this region more porous",
                },
            }
        )
        assert websocket.receive_json()["type"] == "ack"
        interpretation = websocket.receive_json()
        assert interpretation["type"] == "interaction_interpretation"
        assert interpretation["payload"]["primary_intent"] == "replace_region"
        assert interpretation["payload"]["suggested_assistance"][0]["type"] == "generate"
        assert interpretation["payload"]["suggested_assistance"][0]["mode"] == "replace"


def test_http_generation_requested_carries_staged_signals() -> None:
    """generation_requested is not on the narrow WS whitelist; use HTTP interpret."""
    session_id = client.post("/api/v1/sessions", json={"title": "Generation HTTP"}).json()[
        "session_id"
    ]
    response = client.post(
        "/api/v1/interaction/interpret",
        json={
            "type": "generation_requested",
            "event_id": "evt_generation_stage",
            "session_id": session_id,
            "timestamp": "2026-07-06T00:00:00Z",
            "payload": {
                "asset_id": "asset_demo",
                "mode": "diverge",
                "intent": {"mode": "diverge", "text": "explore silhouettes"},
                "generation": {
                    "candidate_count": 4,
                    "metadata": {
                        "stage": "silhouette",
                        "fidelity": "low",
                        "divergence_axes": ["silhouette", "stance"],
                    },
                },
            },
        },
    )
    assert response.status_code == 200
    interpretation = response.json()
    assert interpretation["primary_intent"] == "explore_shape"
    signals = interpretation["features"]["signals"]
    assert signals["semantic"]["creative_stage"] == "silhouette"
    assert signals["semantic"]["fidelity"] == "low"
    assert signals["semantic"]["divergence_axes"] == ["silhouette", "stance"]

    memory_response = client.get(f"/api/v1/sessions/{session_id}/memory")
    assert memory_response.status_code == 200
    memory = memory_response.json()
    assert memory["stage"]["phase"] == "exploring"
    assert memory["recent_events"][-1]["type"] == "generation_requested"
    assert memory["recent_events"][-1]["creative_stage"] == "silhouette"
    assert memory["recent_interpretations"][-1]["primary_intent"] == "explore_shape"


def test_http_candidate_compared_carries_visual_and_stage_signals() -> None:
    session_id = client.post("/api/v1/sessions", json={"title": "Compare HTTP"}).json()[
        "session_id"
    ]
    response = client.post(
        "/api/v1/interaction/interpret",
        json={
            "type": "candidate_compared",
            "event_id": "evt_compare_candidate",
            "session_id": session_id,
            "timestamp": "2026-07-06T00:00:00Z",
            "payload": {
                "asset_id": "asset_demo",
                "candidate_id": "cand_compare_001",
                "candidate_label": "organic grille candidate",
                "candidate_thumbnail_url": "/api/v1/remote-worker/artifact-file?path=/remote/preview.png",
                "mesh_url": "/api/v1/remote-worker/artifact-file?path=/remote/mesh.glb",
                "creative_stage": "part",
                "fidelity": "medium",
                "scores": {"socket_compatibility": 0.72},
                "pipeline_evidence": {
                    "socket_compatibility_score": 0.72,
                    "seam_validation": {"status": "geometry_preview_pass"},
                },
                "selection": {
                    "type": "part",
                    "part_id": "pf_part_01",
                    "label": "front grille",
                },
            },
        },
    )
    assert response.status_code == 200
    interpretation = response.json()
    assert interpretation["primary_intent"] == "compare_candidates"
    signals = interpretation["features"]["signals"]
    assert signals["interaction"]["is_compare"] is True
    assert signals["semantic"]["creative_stage"] == "part"
    assert signals["history"]["socket_compatibility_score"] == 0.72
    assert signals["visual_context"]["candidate_thumbnail_url"].endswith("preview.png")
    suggestions = interpretation["suggested_assistance"]
    assert suggestions[0]["type"] == "notify"
    assert suggestions[0]["label"] == "Socket fit is strong enough to preview or accept"
    assert suggestions[0]["metadata"]["socket_compatibility_score"] == 0.72
    session = client.get(f"/api/v1/sessions/{session_id}").json()
    assert session["stage"]["phase"] == "candidate_comparison"


def test_http_candidate_compared_weak_socket_suggests_more_variants() -> None:
    session_id = client.post("/api/v1/sessions", json={"title": "Weak socket compare"}).json()[
        "session_id"
    ]
    response = client.post(
        "/api/v1/interaction/interpret",
        json={
            "type": "candidate_compared",
            "event_id": "evt_compare_weak_socket",
            "session_id": session_id,
            "timestamp": "2026-07-06T00:00:00Z",
            "payload": {
                "asset_id": "asset_demo",
                "candidate_id": "cand_compare_weak",
                "creative_stage": "part",
                "fidelity": "medium",
                "scores": {"socket_compatibility": 0.42},
                "pipeline_evidence": {
                    "socket_compatibility_score": 0.42,
                    "seam_validation": {"status": "review_needed"},
                },
                "selection": {
                    "type": "part",
                    "part_id": "pf_part_01",
                    "label": "front grille",
                },
            },
        },
    )
    assert response.status_code == 200
    interpretation = response.json()
    suggestions = interpretation["suggested_assistance"]
    assert suggestions[0]["type"] == "notify"
    assert suggestions[0]["label"] == "Socket fit may need another variant"
    assert suggestions[0]["metadata"]["candidate_id"] == "cand_compare_weak"
    assert suggestions[0]["metadata"]["socket_compatibility_score"] == 0.42
    assert suggestions[0]["metadata"]["suggested_next_action"] == "compare_more_candidates"
    signals = interpretation["features"]["signals"]
    assert signals["history"]["socket_compatibility_score"] == 0.42
    session = client.get(f"/api/v1/sessions/{session_id}").json()
    assert session["stage"]["phase"] == "candidate_comparison"


def test_creativeflow_part_payload_carries_partfield_socket_metadata() -> None:
    adapter = RemoteCreativeFlowWorkerAdapter("http://worker")
    partfield_metadata = {
        "source_part_id": "part_26541",
        "face_count": 11720,
        "bbox3d": [0.1, 0.2, 0.3, 0.8, 0.9, 1.0],
        "face_labels_path": "/remote/source_face_labels.npy",
        "segmented_mesh_path": "/remote/source_0_04.ply",
        "segmented_mesh_url": "/api/v1/remote-worker/artifact-file?path=/remote/source_0_04.ply",
    }
    request = GenerationRequest(
        session_id="session_socket",
        asset_id="asset_socket",
        selection=Selection(
            type=SelectionType.part,
            part_id="pf_part_01",
            label="discovered part 01",
            metadata={
                "partfield": partfield_metadata,
                "part_record": {"part_id": "pf_part_01", "label": "discovered part 01"},
            },
        ),
        intent=Intent(
            mode=GenerationMode.replace,
            text="make this part more organic",
            constraints=["preserve object identity"],
        ),
        generation=GenerationOptions(
            metadata={
                "stage": "part",
                "fidelity": "medium",
                "fit_policy": "preserve_socket",
            },
        ),
    )

    target_part = adapter._target_part_payload(request)
    socket_constraints = adapter._socket_constraints(request)

    assert target_part["part_id"] == "pf_part_01"
    assert target_part["partfield"]["source_part_id"] == "part_26541"
    assert target_part["face_count"] == 11720
    assert target_part["bbox3d"] == [0.1, 0.2, 0.3, 0.8, 0.9, 1.0]
    assert target_part["face_labels_path"] == "/remote/source_face_labels.npy"
    assert target_part["segmented_mesh_path"] == "/remote/source_0_04.ply"
    assert socket_constraints["preserve_boundary"] is True
    assert socket_constraints["source_part_id"] == "part_26541"
    assert socket_constraints["face_count"] == 11720
    assert socket_constraints["bbox3d"] == [0.1, 0.2, 0.3, 0.8, 0.9, 1.0]
    assert socket_constraints["face_labels_path"] == "/remote/source_face_labels.npy"
    assert socket_constraints["segmented_mesh_path"] == "/remote/source_0_04.ply"


def test_hy3d_outputs_are_mapped_to_artifact_proxy_urls() -> None:
    orchestrator = GenerationOrchestrator(
        studio_store,
        WebSocketManager(),
        RemoteCreativeFlowWorkerAdapter("http://worker"),
    )
    candidate = Candidate(
        candidate_id="cand_hy3d_proxy",
        job_id="job_hy3d_proxy",
        session_id="session_hy3d_proxy",
        source_asset_id="asset_hy3d_proxy",
        source_part_id="grille",
        label="Hy3D candidate",
        metadata={
            "rationale_id": "rat_001",
            "pipeline_evidence": {"adapter": "remote-creativeflow-worker"},
        },
    )
    studio_store.save_candidate(candidate)

    orchestrator._attach_hy3d_outputs(
        [candidate],
        {
            "result": {
                "result_json": {
                    "items": [
                        {
                            "rationale_id": "rat_001",
                            "mesh_glb": "/remote/hy3d/mesh.glb",
                            "mesh_obj": "/remote/hy3d/mesh.obj",
                            "multiview_grid": "/remote/hy3d/grid.png",
                            "oss_prefix": "creativeflow/flowstudio/job/rat_001",
                        }
                    ]
                }
            }
        },
    )

    updated = studio_store.get_candidate("cand_hy3d_proxy")
    assert updated is not None
    assert updated.mesh_url == "/api/v1/remote-worker/artifact-file?path=/remote/hy3d/mesh.glb"
    assert updated.obj_url == "/api/v1/remote-worker/artifact-file?path=/remote/hy3d/mesh.obj"
    assert updated.metadata["remote_mesh_glb"] == "/remote/hy3d/mesh.glb"
    assert updated.metadata["remote_mesh_url"] == updated.mesh_url
    assert updated.metadata["remote_multiview_grid_url"] == (
        "/api/v1/remote-worker/artifact-file?path=/remote/hy3d/grid.png"
    )
    assert updated.metadata["pipeline_evidence"]["hy3d_mesh_url"] == updated.mesh_url


def test_cancelled_job_is_not_overwritten_by_late_updates() -> None:
    session = client.post("/api/v1/sessions", json={"title": "Cancel guard"}).json()
    asset = client.post(
        "/api/v1/assets",
        json={"session_id": session["session_id"], "object_type": "speaker"},
    ).json()
    request = GenerationRequest(
        session_id=session["session_id"],
        asset_id=asset["asset_id"],
        intent=Intent(mode=GenerationMode.diverge, text="explore silhouettes"),
        generation=GenerationOptions(metadata={"stage": "silhouette", "fidelity": "low"}),
    )
    job = studio_store.create_job(request, stage=JobStage.transfer)
    job.status = JobStatus.cancelled
    job.message = "Job cancelled"
    studio_store.save_job(job)
    orchestrator = GenerationOrchestrator(
        studio_store,
        WebSocketManager(),
        RemoteCreativeFlowWorkerAdapter("http://worker"),
    )

    try:
        asyncio.run(
            orchestrator._update_job(
                job,
                JobStatus.running,
                JobStage.image_generation,
                0.65,
                "late update",
            )
        )
    except JobCancelled:
        pass
    else:
        raise AssertionError("Expected cancelled jobs to reject late updates")

    updated = studio_store.get_job(job.job_id)
    assert updated is not None
    assert updated.status == JobStatus.cancelled
    assert updated.message == "Job cancelled"
    assert updated.stage == JobStage.transfer


def test_cancel_job_forwards_to_remote_worker_and_records_results(monkeypatch) -> None:
    session = client.post("/api/v1/sessions", json={"title": "Remote cancel"}).json()
    asset = client.post(
        "/api/v1/assets",
        json={"session_id": session["session_id"], "object_type": "speaker"},
    ).json()
    request = GenerationRequest(
        session_id=session["session_id"],
        asset_id=asset["asset_id"],
        intent=Intent(mode=GenerationMode.diverge, text="explore silhouettes"),
        generation=GenerationOptions(metadata={"stage": "silhouette", "fidelity": "low"}),
    )
    job = studio_store.create_job(request, stage=JobStage.transfer)
    job.metadata["remote_staged_creativeflow"] = {"job_id": "rw_stage_cancel"}
    job.metadata["remote_hy3d"] = {"job_id": "rw_hy3d_cancel"}
    studio_store.save_job(job)
    cancelled: list[str] = []

    async def fake_cancel(remote_job_id: str) -> dict[str, str]:
        cancelled.append(remote_job_id)
        return {"job_id": remote_job_id, "status": "cancelled", "stage": "cancelled"}

    monkeypatch.setattr(remote_worker_adapter, "cancel_job", fake_cancel)

    response = client.post(f"/api/v1/jobs/{job.job_id}/cancel")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "cancelled"
    assert cancelled == ["rw_stage_cancel", "rw_hy3d_cancel"]
    assert body["metadata"]["remote_cancel"] == [
        {
            "remote_job_id": "rw_stage_cancel",
            "status": "cancelled",
            "stage": "cancelled",
            "ok": True,
        },
        {
            "remote_job_id": "rw_hy3d_cancel",
            "status": "cancelled",
            "stage": "cancelled",
            "ok": True,
        },
    ]


def test_artifact_path_from_remote_worker_url() -> None:
    from app.services.generation.autopartgen_adapter import _artifact_path_from_url

    assert (
        _artifact_path_from_url(
            "/api/v1/remote-worker/artifact-file?path=%2Fremote%2Fhy3d%2Fmesh.glb"
        )
        == "/remote/hy3d/mesh.glb"
    )
    assert _artifact_path_from_url("/local/mesh.glb") is None


def test_part_discovery_updates_asset_parts() -> None:
    session_id = client.post("/api/v1/sessions", json={"title": "Parts"}).json()["session_id"]
    asset = client.post(
        "/api/v1/assets",
        json={"session_id": session_id, "object_type": "design_db_asset"},
    ).json()

    response = client.post(
        "/api/v1/parts/discover",
        json={
            "session_id": session_id,
            "asset_id": asset["asset_id"],
            "mode": "mesh",
            "prompt": "discover editable parts",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["parts"] == []
    assert body["metadata"]["adapter"] == "sam3d_unavailable"

    parts_response = client.get(f"/api/v1/assets/{asset['asset_id']}/parts")
    assert parts_response.status_code == 200
    assert parts_response.json()["parts"] == []


def test_part_label_update_changes_asset_parts() -> None:
    session_id = client.post("/api/v1/sessions", json={"title": "Part rename"}).json()[
        "session_id"
    ]
    asset = client.post(
        "/api/v1/assets",
        json={
            "session_id": session_id,
            "object_type": "design_db_asset",
            "parts": [
                {
                    "part_id": "body",
                    "label": "main body",
                    "type": "semantic",
                }
            ],
        },
    ).json()

    response = client.patch(
        f"/api/v1/assets/{asset['asset_id']}/parts/body",
        json={"label": "main editable body", "metadata": {"user_labeled": True}},
    )

    assert response.status_code == 200
    part = response.json()
    assert part["part_id"] == "body"
    assert part["label"] == "main editable body"
    assert part["metadata"]["user_labeled"] is True

    parts_response = client.get(f"/api/v1/assets/{asset['asset_id']}/parts")
    assert parts_response.status_code == 200
    labels = {item["part_id"]: item["label"] for item in parts_response.json()["parts"]}
    assert labels["body"] == "main editable body"


def test_geometry_worker_bbox_normalize_and_extract_region() -> None:
    session_id = client.post("/api/v1/sessions", json={"title": "Geometry worker"}).json()[
        "session_id"
    ]
    obj = b"v 0 0 0\nv 2 0 0\nv 0 2 0\nv 0 0 2\nf 1 2 3\nf 1 3 4\n"
    upload = client.post(
        "/api/v1/assets/upload",
        data={"session_id": session_id, "object_type": "tetra", "label": "tetra"},
        files={"file": ("tetra.obj", obj, "text/plain")},
    )
    assert upload.status_code == 200
    asset = upload.json()

    bbox = client.post("/api/v1/geometry/bbox", json={"session_id": session_id, "asset_id": asset["asset_id"]})
    assert bbox.status_code == 200
    bbox_body = bbox.json()
    assert bbox_body["ok"] is True
    assert bbox_body["metrics"]["bbox3d"]["max"] == [2.0, 2.0, 2.0]
    assert bbox_body["metrics"]["face_count"] == 2

    normalized = client.post(
        "/api/v1/geometry/normalize",
        json={"session_id": session_id, "asset_id": asset["asset_id"]},
    )
    assert normalized.status_code == 200
    normalized_body = normalized.json()
    assert normalized_body["ok"] is True
    assert normalized_body["result_mesh_url"].startswith("/files/geometry/")
    assert normalized_body["artifacts"]["artifact_ids"]
    job_lookup = client.get(f"/api/v1/geometry/jobs/{normalized_body['job_id']}")
    assert job_lookup.status_code == 200
    assert job_lookup.json()["result_mesh_url"] == normalized_body["result_mesh_url"]
    artifact_response = client.get(f"/api/v1/artifacts/{normalized_body['artifacts']['artifact_ids'][0]}")
    assert artifact_response.status_code == 200
    assert artifact_response.json()["worker"] == "geometry"
    normalized_path = (
        Path(__file__).resolve().parents[1]
        / "storage"
        / "files"
        / normalized_body["result_mesh_url"].removeprefix("/files/")
    )
    assert normalized_path.exists()

    labels_url = _write_test_npy_labels("geometry_region_labels.npy", [3, 4])
    region = client.post(
        "/api/v1/geometry/extract-region",
        json={
            "session_id": session_id,
            "asset_id": asset["asset_id"],
            "part": {
                "part_id": "pf_part_01",
                "metadata": {
                    "source_part_id": "cluster_3",
                    "face_labels_path": labels_url,
                },
            },
        },
    )
    assert region.status_code == 200
    region_body = region.json()
    assert region_body["ok"] is True
    assert region_body["metrics"]["selected_face_count"] == 1
    assert region_body["metrics"]["boundary_edge_count"] >= 1
    artifacts = client.get(f"/api/v1/artifacts?session_id={session_id}&asset_id={asset['asset_id']}")
    assert artifacts.status_code == 200
    assert any(item["operation"] == "extract-region" for item in artifacts.json()["artifacts"])


def test_geometry_worker_fit_candidate_uses_candidate_and_part_bbox() -> None:
    session_id = client.post("/api/v1/sessions", json={"title": "Geometry fit"}).json()[
        "session_id"
    ]
    source = client.post(
        "/api/v1/assets/upload",
        data={"session_id": session_id, "object_type": "socket", "label": "socket"},
        files={"file": ("socket.obj", b"v 0 0 0\nv 4 0 0\nv 0 2 0\nf 1 2 3\n", "text/plain")},
    ).json()
    candidate_asset = client.post(
        "/api/v1/assets/upload",
        data={"session_id": session_id, "object_type": "part", "label": "part"},
        files={"file": ("candidate.obj", b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", "text/plain")},
    ).json()
    request = GenerationRequest(
        session_id=session_id,
        asset_id=source["asset_id"],
        selection=Selection(type=SelectionType.part, part_id="pf_part_01"),
        intent=Intent(mode=GenerationMode.replace),
        generation=GenerationOptions(candidate_count=1),
    )
    job = studio_store.create_job(request)
    candidate = Candidate(
        candidate_id="cand_geometry_fit",
        job_id=job.job_id,
        session_id=session_id,
        source_asset_id=source["asset_id"],
        source_part_id="pf_part_01",
        label="geometry fit candidate",
        obj_url=candidate_asset["obj_url"],
    )
    studio_store.save_candidate(candidate)

    response = client.post(
        "/api/v1/geometry/fit-candidate",
        json={
            "asset_id": source["asset_id"],
            "candidate_id": candidate.candidate_id,
            "part": {
                "part_id": "pf_part_01",
                "metadata": {
                    "bbox3d": {
                        "min": [10, 20, 30],
                        "max": [14, 22, 34],
                    }
                },
            },
            "options": {"fit_policy": "bbox_uniform"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["metrics"]["status"] == "transform_ready"
    assert body["result_mesh_url"].startswith("/files/geometry/")


def test_render_preview_worker_reports_blender_availability_truthfully() -> None:
    session_id = client.post("/api/v1/sessions", json={"title": "Render worker"}).json()[
        "session_id"
    ]
    asset = client.post(
        "/api/v1/assets/upload",
        data={"session_id": session_id, "object_type": "triangle", "label": "triangle"},
        files={"file": ("triangle.obj", b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", "text/plain")},
    ).json()
    response = client.post("/api/v1/render/thumbnail", json={"asset_id": asset["asset_id"]})
    assert response.status_code == 200
    body = response.json()
    lookup = client.get(f"/api/v1/render/jobs/{body['job_id']}")
    assert lookup.status_code == 200
    assert lookup.json()["status"] == body["status"]
    if body["ok"]:
        assert body["thumbnail_url"].startswith("/files/render/")
        assert body["metadata"]["engine"] == "blender"
        assert body["artifacts"]["artifact_ids"]
    else:
        assert body["status"] == "failed"
        assert body["error"]["code"] == "RENDER_PREVIEW_WORKER_FAILED"
        assert body["metadata"]["engine"] == "blender"


def test_worker_job_lookup_unknown_returns_404() -> None:
    assert client.get("/api/v1/geometry/jobs/geomjob_missing").status_code == 404
    assert client.get("/api/v1/render/jobs/renderjob_missing").status_code == 404


def test_session_snapshot_returns_active_state_candidates_and_artifacts() -> None:
    session_id = client.post("/api/v1/sessions", json={"title": "Snapshot"}).json()["session_id"]
    asset = client.post(
        "/api/v1/assets/upload",
        data={"session_id": session_id, "object_type": "triangle", "label": "triangle"},
        files={"file": ("triangle.obj", b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", "text/plain")},
    ).json()
    geometry = client.post("/api/v1/geometry/normalize", json={"session_id": session_id, "asset_id": asset["asset_id"]})
    assert geometry.status_code == 200
    request = GenerationRequest(
        session_id=session_id,
        asset_id=asset["asset_id"],
        selection=Selection(type=SelectionType.part, part_id="body"),
        intent=Intent(mode=GenerationMode.diverge),
        generation=GenerationOptions(candidate_count=1),
    )
    job = studio_store.create_job(request)
    studio_store.save_candidate(
        Candidate(
            candidate_id="cand_snapshot",
            job_id=job.job_id,
            session_id=session_id,
            source_asset_id=asset["asset_id"],
            source_part_id="body",
            label="snapshot candidate",
            thumbnail_url="/files/render/example.png",
        )
    )
    event = UserEvent(
        type="brush_end",
        event_id="evt_snapshot",
        session_id=session_id,
        payload={"asset_id": asset["asset_id"], "part_id": "body"},
    )
    studio_store.save_event(event)

    snapshot = client.get(f"/api/v1/sessions/{session_id}/snapshot")
    assert snapshot.status_code == 200
    body = snapshot.json()
    assert body["session"]["session_id"] == session_id
    assert body["active_asset"]["asset_id"] == asset["asset_id"]
    assert body["active_parts"] == []
    assert body["active_job"]["job_id"] == job.job_id
    assert body["visible_candidates"][0]["candidate_id"] == "cand_snapshot"
    assert body["recent_events"][0]["event_id"] == "evt_snapshot"
    assert any(item["worker"] == "geometry" for item in body["artifacts"])
    assert any(
        item["source_id"] == "evt_snapshot" and item["type"] == "event:brush_end"
        for item in body["memory"]["episodic"]
    )


def _write_test_npy_labels(name: str, labels: list[int]) -> str:
    root = Path(__file__).resolve().parents[1] / "storage" / "files" / "test_labels"
    root.mkdir(parents=True, exist_ok=True)
    header = f"{{'descr': '<i4', 'fortran_order': False, 'shape': ({len(labels)},), }}"
    header_bytes = header.encode("latin1")
    padding = 16 - ((10 + len(header_bytes) + 1) % 16)
    header_bytes = header_bytes + b" " * padding + b"\n"
    payload = b"".join(struct.pack("<i", item) for item in labels)
    (root / name).write_bytes(b"\x93NUMPY\x01\x00" + struct.pack("<H", len(header_bytes)) + header_bytes + payload)
    return f"/files/test_labels/{name}"


def test_case_save_updates_stage_and_writes_report() -> None:
    session_id = client.post("/api/v1/sessions", json={"title": "Case save"}).json()[
        "session_id"
    ]
    asset = client.post(
        "/api/v1/assets",
        json={"session_id": session_id, "object_type": "speaker", "label": "saved speaker"},
    ).json()

    response = client.post(
        "/api/v1/cases",
        json={
            "session_id": session_id,
            "title": "Saved direction",
            "asset_id": asset["asset_id"],
            "accepted_candidate_ids": [],
            "notes": "Keep this as the current study result.",
            "metadata": {"creative_stage": "rough_form"},
        },
    )

    assert response.status_code == 200
    case = response.json()
    assert case["case_id"].startswith("case_")
    assert case["report_url"].endswith("/report.html")
    assert case["metadata"]["case_url"].endswith("/case.json")
    assert case["metadata"]["case_index_url"] == "/files/cases/index.json"

    session = client.get(f"/api/v1/sessions/{session_id}").json()
    assert session["stage"]["phase"] == "finalizing"
    assert session["stage"]["current_goal"] == "Saved case: Saved direction"

    report = client.get(case["report_url"])
    assert report.status_code == 200
    assert "Saved direction" in report.text
    assert "saved speaker" in report.text

    manifest = client.get(case["metadata"]["case_url"])
    assert manifest.status_code == 200
    manifest_body = manifest.json()
    assert manifest_body["schema_version"] == "flowstudio.case.v1"
    assert manifest_body["case"]["case_id"] == case["case_id"]
    assert manifest_body["asset"]["asset_id"] == asset["asset_id"]

    index = client.get("/files/cases/index.json")
    assert index.status_code == 200
    assert any(item["case_id"] == case["case_id"] for item in index.json()["cases"])


def test_case_save_keeps_canvas_only_candidate_ids() -> None:
    session_id = client.post("/api/v1/sessions", json={"title": "Canvas case"}).json()[
        "session_id"
    ]
    asset = client.post(
        "/api/v1/assets",
        json={"session_id": session_id, "object_type": "candy", "label": "candy"},
    ).json()
    pending = Candidate(
        candidate_id="cand_pending_canvas",
        job_id="job_pending_canvas",
        session_id=session_id,
        source_asset_id=asset["asset_id"],
        label="pending candy",
        decision=CandidateDecision.pending,
    )
    studio_store.save_candidate(pending)

    response = client.post(
        "/api/v1/cases",
        json={
            "session_id": session_id,
            "title": "candy",
            "asset_id": asset["asset_id"],
            "accepted_candidate_ids": ["fourstage_candy_0", pending.candidate_id],
        },
    )

    assert response.status_code == 200
    case = response.json()
    assert case["accepted_candidate_ids"] == ["fourstage_candy_0", pending.candidate_id]
    assert case["metadata"]["unresolved_candidate_ids"] == ["fourstage_candy_0"]
    assert studio_store.get_candidate(pending.candidate_id).decision == CandidateDecision.accepted
    manifest = client.get(case["metadata"]["case_url"]).json()
    assert manifest["asset"]["asset_id"] == asset["asset_id"]
    assert any(item["candidate_id"] == pending.candidate_id for item in manifest["accepted_candidates"])


def test_case_index_preserves_existing_static_entries_after_restart(tmp_path) -> None:
    cases_root = tmp_path / "cases"
    cases_root.mkdir()
    (cases_root / "index.json").write_text(
        json.dumps(
            {
                "schema_version": "flowstudio.case_index.v1",
                "cases": [
                    {
                        "case_id": "case_old_static",
                        "session_id": "sess_old",
                        "title": "Old persisted case",
                        "asset_id": "asset_old",
                        "report_url": "/files/cases/case_old_static/report.html",
                        "case_url": "/files/cases/case_old_static/case.json",
                        "accepted_candidate_ids": ["cand_old"],
                        "created_at": "2026-07-07T01:00:00+00:00",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    write_case_index(
        cases_root,
        [
            CaseRecord(
                case_id="case_new_memory",
                session_id="sess_new",
                title="New memory case",
                asset_id="asset_new",
                report_url="/files/cases/case_new_memory/report.html",
                metadata={"case_url": "/files/cases/case_new_memory/case.json"},
            )
        ],
    )

    body = json.loads((cases_root / "index.json").read_text(encoding="utf-8"))
    rows = {item["case_id"]: item for item in body["cases"]}
    assert set(rows) == {"case_old_static", "case_new_memory"}
    assert rows["case_old_static"]["title"] == "Old persisted case"
    assert rows["case_new_memory"]["case_url"] == "/files/cases/case_new_memory/case.json"


def test_case_report_includes_pipeline_evidence_for_accepted_candidates() -> None:
    session = client.post("/api/v1/sessions", json={"title": "Evidence case"}).json()
    asset = client.post(
        "/api/v1/assets",
        json={"session_id": session["session_id"], "object_type": "speaker"},
    ).json()
    candidate = Candidate(
        candidate_id="cand_pipeline_evidence",
        job_id="job_pipeline_evidence",
        session_id=session["session_id"],
        source_asset_id=asset["asset_id"],
        source_part_id="pf_part_01",
        label="socket-aware part direction",
        decision=CandidateDecision.accepted,
        thumbnail_url="/api/v1/remote-worker/artifact-file?path=/remote/preview.png",
        metadata={
            "pipeline_evidence": {
                "remote_job_id": "rw_creativeflow_part_report",
                "stage": "part",
                "fidelity": "medium",
                "direction_id": "dir_01_motif",
                "source_part_id": "part_26541",
                "socket_face_count": 11720,
                "remote_image_url": "/api/v1/remote-worker/artifact-file?path=/remote/preview.png",
                "result_path": "/root/autodl-tmp/report/creativeflow_part_result.json",
            }
        },
    )
    studio_store.save_candidate(candidate)

    case_response = client.post(
        "/api/v1/cases",
        json={
            "session_id": session["session_id"],
            "title": "Pipeline evidence case",
            "asset_id": asset["asset_id"],
            "accepted_candidate_ids": [candidate.candidate_id],
            "notes": "Keep remote evidence with the case.",
        },
    )

    assert case_response.status_code == 200
    report = client.get(case_response.json()["report_url"])
    assert report.status_code == 200
    assert "Pipeline Evidence" in report.text
    assert "rw_creativeflow_part_report" in report.text
    assert "dir_01_motif" in report.text
    assert "part_26541 / 11720 faces" in report.text
    assert "creativeflow_part_result.json" in report.text
    assert 'class="preview-img"' in report.text
    assert "/remote/preview.png" in report.text
    manifest = client.get(case_response.json()["metadata"]["case_url"]).json()
    assert manifest["accepted_candidates"][0]["candidate_id"] == candidate.candidate_id
    assert manifest["pipeline_evidence"][0]["evidence"]["remote_job_id"] == (
        "rw_creativeflow_part_report"
    )
    assert manifest["pipeline_evidence"][0]["thumbnail_url"].endswith("preview.png")


def test_accept_low_fidelity_silhouette_updates_direction_memory_without_asset_swap() -> None:
    session = client.post("/api/v1/sessions", json={"title": "Direction memory"}).json()
    asset = client.post(
        "/api/v1/assets",
        json={"session_id": session["session_id"], "object_type": "chair"},
    ).json()
    candidate = Candidate(
        candidate_id="cand_direction_memory",
        job_id="job_direction_memory",
        session_id=session["session_id"],
        source_asset_id=asset["asset_id"],
        label="wide low silhouette",
        thumbnail_url="/files/previews/wide.png",
        metadata={"stage": "silhouette", "fidelity": "low"},
    )
    studio_store.save_candidate(candidate)

    response = client.post(
        f"/api/v1/candidates/{candidate.candidate_id}/accept",
        json={
            "session_id": session["session_id"],
            "reason": "interesting broad direction",
            "make_active_asset": False,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["active_asset_id"] is None
    assert body["updated_stage"]["active_asset_id"] == asset["asset_id"]
    assert body["updated_stage"]["phase"] == "exploring"
    assert body["updated_stage"]["suggested_action"] == "continue_rough_form_exploration"

    updated_session = client.get(f"/api/v1/sessions/{session['session_id']}").json()
    memory = updated_session["metadata"]["candidate_memory"]
    assert memory["last_commit_policy"] == "direction_memory"
    assert memory["last_accepted_stage"] == "silhouette"
    assert candidate.candidate_id in memory["accepted_direction_ids"]
    semantic_memory = client.get(
        f"/api/v1/sessions/{session['session_id']}/memories"
        f"?category=semantic&candidate_id={candidate.candidate_id}"
    )
    assert semantic_memory.status_code == 200
    assert any(
        item["type"] == "candidate_accepted"
        and item["content"]["commit_policy"] == "direction_memory"
        for item in semantic_memory.json()["memories"]
    )

    case_response = client.post(
        "/api/v1/cases",
        json={
            "session_id": session["session_id"],
            "title": "Direction memory case",
            "asset_id": asset["asset_id"],
            "accepted_candidate_ids": [candidate.candidate_id],
            "notes": "Save the accepted silhouette as design direction.",
        },
    )
    assert case_response.status_code == 200
    report = client.get(case_response.json()["report_url"])
    assert report.status_code == 200
    assert "Direction Memory" in report.text
    assert "wide low silhouette" in report.text
    assert "silhouette" in report.text
    assert "direction_memory" in report.text


def test_action_creates_single_perception_broadcast(monkeypatch: pytest.MonkeyPatch) -> None:
    broadcasts: list[tuple[str, str]] = []

    async def capture_broadcast(session_id: str, event_type: str, payload: object) -> None:
        broadcasts.append((session_id, event_type))

    monkeypatch.setattr(
        "app.main.websocket_manager.broadcast",
        capture_broadcast,
    )

    session = client.post("/api/v1/sessions", json={"title": "perception broadcast"}).json()
    asset = client.post(
        "/api/v1/assets",
        json={"session_id": session["session_id"], "object_type": "snowman"},
    ).json()
    response = client.post(
        f"/api/v1/sessions/{session['session_id']}/actions",
        json={
            "tool": "hover",
            "target": {"asset_id": asset["asset_id"], "label": "Branch"},
            "evidence": {"live_signals": {"hover_count": 1, "dwell_ms": 1200}},
            "order": 0,
        },
    )
    assert response.status_code == 200
    event_types = [item[1] for item in broadcasts if item[0] == session["session_id"]]
    assert event_types.count("perception_updated") == 1
    assert event_types.count("interaction_interpretation") == 1
    assert event_types.count("stage_update") == 1
    latest = client.get(f"/api/v1/sessions/{session['session_id']}/perception/latest").json()
    assert latest["status"] == "ready"
    assert latest["perception"]["perception_id"]


def test_prompt_chip_does_not_create_action_atom() -> None:
    session = client.post("/api/v1/sessions", json={"title": "prompt chip guard"}).json()
    asset = client.post(
        "/api/v1/assets",
        json={"session_id": session["session_id"], "object_type": "snowman"},
    ).json()
    response = client.post(
        f"/api/v1/sessions/{session['session_id']}/actions",
        json={
            "tool": "text",
            "target": {"asset_id": asset["asset_id"], "label": "whole object"},
            "evidence": {
                "source": "more_creative_prompt_chip",
                "selected_prompt_tokens": [{"label": "soft silhouette"}],
            },
            "order": 0,
        },
    )
    assert response.status_code == 400
    body = response.json()
    message = body.get("detail") or body.get("error", {}).get("message") or ""
    assert "Prompt chips" in message
    actions = client.get(f"/api/v1/sessions/{session['session_id']}/actions").json()
    assert actions["actions"] == []


def test_cross_domain_proxy_marks_deprecated() -> None:
    session = client.post("/api/v1/sessions", json={"title": "cross-domain proxy"}).json()
    asset = client.post(
        "/api/v1/assets",
        json={"session_id": session["session_id"], "object_type": "snowman"},
    ).json()
    response = client.post(
        "/api/v1/directions/cross-domain",
        json={
            "session_id": session["session_id"],
            "asset_id": asset["asset_id"],
            "candidate_count": 3,
            "source_summary": "make snowman cuter",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["directions"]
    assert body["metadata"]["deprecated"] is True
    assert body["metadata"]["canonical_endpoint"] == "/api/v1/directions/suggest"


def test_suggest_reuses_interpretation_ir(monkeypatch: pytest.MonkeyPatch) -> None:
    retrieve_calls = {"count": 0}
    original_retrieve = None

    session = client.post("/api/v1/sessions", json={"title": "suggest ir reuse"}).json()
    asset = client.post(
        "/api/v1/assets",
        json={"session_id": session["session_id"], "object_type": "snowman"},
    ).json()
    action = client.post(
        f"/api/v1/sessions/{session['session_id']}/actions",
        json={
            "tool": "hover",
            "target": {"asset_id": asset["asset_id"], "label": "whole snowman"},
            "evidence": {
                "intent_text": "make the whole snowman more cute",
                "live_signals": {"dwell_ms": 2200, "tool_switch_count": 3},
            },
            "order": 0,
        },
    )
    assert action.status_code == 200
    latest = client.get(f"/api/v1/sessions/{session['session_id']}/perception/latest").json()
    interpretation_id = latest["perception"]["perception_id"]
    assert interpretation_id

    from app.main import interaction_service

    original_retrieve = interaction_service.ir_retriever.retrieve

    def counting_retrieve(*args, **kwargs):
        retrieve_calls["count"] += 1
        return original_retrieve(*args, **kwargs)

    monkeypatch.setattr(interaction_service.ir_retriever, "retrieve", counting_retrieve)

    response = client.post(
        "/api/v1/directions/suggest",
        json={
            "session_id": session["session_id"],
            "asset_id": asset["asset_id"],
            "interpretation_id": interpretation_id,
            "candidate_count": 3,
            "source_summary": "confirmed cute snowman intent",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["metadata"].get("ir_reused_from_interpretation") is True
    assert retrieve_calls["count"] == 0


def test_generation_returns_job_before_candidates() -> None:
    session = client.post("/api/v1/sessions", json={"title": "gen async"}).json()
    asset = client.post(
        "/api/v1/assets",
        json={"session_id": session["session_id"], "object_type": "snowman"},
    ).json()
    response = client.post(
        "/api/v1/generation/diverge",
        json={
            "session_id": session["session_id"],
            "asset_id": asset["asset_id"],
            "intent": {
                "mode": "diverge",
                "text": "make it cuter",
            },
            "selection": {"type": "none"},
            "generation": {"candidate_count": 2},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"]
    assert "candidates" not in body


def test_repeated_part_rejections_suggest_revising_part_direction() -> None:
    session = client.post("/api/v1/sessions", json={"title": "Reject memory"}).json()
    asset = client.post(
        "/api/v1/assets",
        json={"session_id": session["session_id"], "object_type": "speaker"},
    ).json()
    candidates = [
        Candidate(
            candidate_id=f"cand_reject_part_{index}",
            job_id="job_reject_part",
            session_id=session["session_id"],
            source_asset_id=asset["asset_id"],
            source_part_id="grille",
            label=f"rejected part direction {index}",
            metadata={"stage": "part", "fidelity": "medium"},
        )
        for index in range(2)
    ]
    for candidate in candidates:
        studio_store.save_candidate(candidate)
        response = client.post(
            f"/api/v1/candidates/{candidate.candidate_id}/reject",
            json={"session_id": session["session_id"], "reason": "not the right local direction"},
        )
        assert response.status_code == 200

    updated_session = client.get(f"/api/v1/sessions/{session['session_id']}").json()
    assert updated_session["stage"]["suggested_action"] == "revise_part_direction"
    memory = updated_session["metadata"]["candidate_memory"]
    assert memory["last_rejected_stage"] == "part"
    assert len(memory["rejected"]) >= 2
    reflective_memory = client.get(
        f"/api/v1/sessions/{session['session_id']}/memories?category=reflective"
    )
    assert reflective_memory.status_code == 200
    rejected_ids = {
        item["candidate_id"]
        for item in reflective_memory.json()["memories"]
        if item["type"] == "candidate_rejected"
    }
    assert {candidate.candidate_id for candidate in candidates}.issubset(rejected_ids)


def test_interpret_rule_first_marks_intent_predict_task() -> None:
    session = client.post("/api/v1/sessions", json={"title": "rule first"}).json()
    response = client.post(
        "/api/v1/interaction/interpret",
        json={
            "type": "camera_observation_ended",
            "event_id": "evt_rule_first",
            "session_id": session["session_id"],
            "payload": {
                "asset_id": "asset_demo",
                "live_signals": {"dwell_ms": 1800, "viewport_orbit_count": 1},
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["predictor_metadata"].get("task") == "intent_predict"
    # Without VLM endpoint in tests, response is immediate rule path (not pending).
    assert body["predictor_metadata"].get("vlm_pending") in {None, False}


def test_snapshot_includes_solution_space_view() -> None:
    session = client.post("/api/v1/sessions", json={"title": "snapshot sol"}).json()
    asset = client.post(
        "/api/v1/assets",
        json={"session_id": session["session_id"], "object_type": "snowman"},
    ).json()
    studio_store.save_candidate(
        Candidate(
            candidate_id="cand_snapshot_sol",
            job_id="job_snapshot_sol",
            session_id=session["session_id"],
            source_asset_id=asset["asset_id"],
            label="snapshot node",
        )
    )
    snapshot = client.get(f"/api/v1/sessions/{session['session_id']}/snapshot")
    assert snapshot.status_code == 200
    body = snapshot.json()
    assert "solution_space" in body
    assert body["solution_space"]["session_id"] == session["session_id"]
    assert any(
        node["candidate_id"] == "cand_snapshot_sol"
        for node in body["solution_space"]["nodes"]
    )
    sol = client.get(f"/api/v1/sessions/{session['session_id']}/solution-space")
    assert sol.status_code == 200
    assert sol.json()["session_id"] == body["solution_space"]["session_id"]


def test_suggest_metadata_marks_direction_suggest_task() -> None:
    session = client.post("/api/v1/sessions", json={"title": "dir task"}).json()
    asset = client.post(
        "/api/v1/assets",
        json={"session_id": session["session_id"], "object_type": "snowman"},
    ).json()
    response = client.post(
        "/api/v1/directions/suggest",
        json={
            "session_id": session["session_id"],
            "asset_id": asset["asset_id"],
            "candidate_count": 2,
            "source_summary": "cute snowman",
        },
    )
    assert response.status_code == 200
    assert response.json()["metadata"].get("task") == "direction_suggest"
