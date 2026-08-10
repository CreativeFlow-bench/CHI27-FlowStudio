import asyncio
from pathlib import Path
import struct
from typing import Any

import pytest

from app.models import (
    AssetCreateRequest,
    Candidate,
    CandidateFitRequest,
    GenerationMode,
    GenerationRequest,
    PartRecord,
    SessionCreateRequest,
)
from app.services.generation.generation_orchestrator import (
    GenerationOrchestrator,
    ThreeDGenerationDisabled,
)
from app.services.generation.generation_orchestrator import RemoteCreativeFlowWorkerAdapter
from app.services.storage.studio_store import InMemoryStudioStore
from app.services.storage.websocket_manager import WebSocketManager


def test_submit_hy3d_uses_transfer_result_path_and_candidate_limit() -> None:
    adapter = RemoteCreativeFlowWorkerAdapter(base_url="http://worker.example")
    captured: dict[str, Any] = {}

    async def fake_post_json(path: str, payload: dict[str, Any]) -> dict[str, Any]:
        captured["path"] = path
        captured["payload"] = payload
        return {"job_id": "rw_hy3d_test"}

    adapter._post_json = fake_post_json  # type: ignore[method-assign]

    result = asyncio.run(
        adapter.submit_hy3d(
            "job_flowstudio",
            "/remote/transfer_engine_result.json",
            candidate_ids=["01_rat_demo"],
            max_candidates=1,
        )
    )

    assert result["job_id"] == "rw_hy3d_test"
    assert captured["path"] == "/jobs/hy3d"
    assert captured["payload"]["flowstudio_job_id"] == "job_flowstudio"
    assert captured["payload"]["transfer_result_path"] == "/remote/transfer_engine_result.json"
    assert captured["payload"]["candidate_ids"] == ["01_rat_demo"]
    assert captured["payload"]["max_candidates"] == 1


def test_submit_hy3d_from_staged_uses_direction_filter() -> None:
    adapter = RemoteCreativeFlowWorkerAdapter(base_url="http://worker.example")
    captured: dict[str, Any] = {}

    async def fake_post_json(path: str, payload: dict[str, Any]) -> dict[str, Any]:
        captured["path"] = path
        captured["payload"] = payload
        return {"job_id": "rw_hy3d_from_staged_test"}

    adapter._post_json = fake_post_json  # type: ignore[method-assign]

    result = asyncio.run(
        adapter.submit_hy3d_from_staged(
            "job_flowstudio",
            "/remote/creativeflow_silhouette_result.json",
            direction_ids=["dir_01_silhouette"],
            max_candidates=1,
        )
    )

    assert result["job_id"] == "rw_hy3d_from_staged_test"
    assert captured["path"] == "/jobs/hy3d-from-staged"
    assert captured["payload"]["flowstudio_job_id"] == "job_flowstudio"
    assert captured["payload"]["staged_result_path"] == "/remote/creativeflow_silhouette_result.json"
    assert captured["payload"]["direction_ids"] == ["dir_01_silhouette"]
    assert captured["payload"]["max_candidates"] == 1


def test_staged_creativeflow_request_creates_direction_candidates() -> None:
    store = InMemoryStudioStore()
    adapter = RemoteCreativeFlowWorkerAdapter(base_url="http://worker.example")

    async def fake_staged(job: Any, asset: Any = None) -> dict[str, Any]:
        return {
            "job_id": "rw_creativeflow_silhouette_test",
            "status": "completed",
            "result": {
                "result_path": "/remote/creativeflow_silhouette_result.json",
                "result_json": {
                    "stage": "silhouette",
                    "fidelity": "low",
                    "directions": [
                        {
                            "direction_id": "dir_01_silhouette",
                            "label": "global silhouette variation",
                            "execution_prompt": "low-fidelity broad silhouette exploration",
                            "fit_contract": {"preserve_attachment_boundary": False},
                            "fidelity_profile": {"image_steps": 4, "run_hy3d": False},
                            "risk": {"fit": "not_applicable", "identity": "high"},
                        }
                    ],
                },
            },
        }

    adapter.submit_staged_creativeflow = fake_staged  # type: ignore[method-assign]
    orchestrator = GenerationOrchestrator(
        store,
        WebSocketManager(),
        adapter,
        enable_3d_generation=True,
    )
    session = store.create_session(SessionCreateRequest(title="Staged smoke"))
    asset = store.create_asset(
        AssetCreateRequest(session_id=session.session_id, object_type="chair", label="chair")
    )

    request = GenerationRequest.model_validate(
        {
            "session_id": session.session_id,
            "asset_id": asset.asset_id,
            "selection": {"type": "none"},
            "intent": {"mode": GenerationMode.diverge, "text": "try different overall shapes"},
            "generation": {
                "candidate_count": 1,
                "metadata": {
                    "pipeline": "creativeflow-silhouette",
                    "stage": "silhouette",
                    "fidelity": "low",
                    "analogy_prompt_package": {
                        "prompt_token_mode": "human_selectable_chips",
                        "final_prompt": "try different overall shapes\nAnalogy keywords: squishy, bouncy",
                        "selected_prompt_tokens": [
                            {
                                "label": "squishy",
                                "role": "material",
                                "source_direction_id": "dir_prompt_source",
                            },
                            {
                                "label": "bouncy",
                                "role": "behavior",
                                "source_direction_id": "dir_prompt_source",
                            },
                        ],
                        "direction_ids": ["dir_prompt_source"],
                    },
                },
            },
        }
    )
    job = asyncio.run(orchestrator.create_generation_job(request))
    asyncio.run(asyncio.sleep(0.05))
    stored_job = store.get_job(job.job_id)
    assert stored_job is not None
    assert stored_job.metadata["remote_staged_creativeflow"]["job_id"] == "rw_creativeflow_silhouette_test"
    assert stored_job.candidate_ids
    candidate = store.get_candidate(stored_job.candidate_ids[0])
    assert candidate is not None
    assert candidate.metadata["adapter"] == "remote-staged-creativeflow"
    assert candidate.metadata["stage"] == "silhouette"
    assert candidate.metadata["fidelity"] == "low"
    assert candidate.metadata["prompt_token_mode"] == "human_selectable_chips"
    assert candidate.metadata["selected_prompt_tokens"][0]["label"] == "squishy"
    assert candidate.metadata["analogy_prompt_package"]["direction_ids"] == ["dir_prompt_source"]
    evidence = candidate.metadata["pipeline_evidence"]
    assert evidence["adapter"] == "remote-staged-creativeflow"
    assert evidence["remote_job_id"] == "rw_creativeflow_silhouette_test"
    assert evidence["result_path"] == "/remote/creativeflow_silhouette_result.json"
    assert evidence["stage"] == "silhouette"
    assert evidence["fidelity"] == "low"
    assert evidence["direction_id"] == "dir_01_silhouette"
    assert evidence["analogy_direction_ids"] == ["dir_prompt_source"]
    assert evidence["selected_prompt_tokens"][1]["label"] == "bouncy"
    assert evidence["has_preview_image"] is False


def test_generate_candidate_hy3d_updates_staged_candidate_mesh_urls() -> None:
    store = InMemoryStudioStore()
    adapter = RemoteCreativeFlowWorkerAdapter(base_url="http://worker.example")
    captured: dict[str, Any] = {}

    async def fake_submit_hy3d_from_staged(
        flowstudio_job_id: str,
        staged_result_path: str,
        direction_ids: list[str] | None = None,
        max_candidates: int = 1,
    ) -> dict[str, Any]:
        captured["flowstudio_job_id"] = flowstudio_job_id
        captured["staged_result_path"] = staged_result_path
        captured["direction_ids"] = direction_ids
        captured["max_candidates"] = max_candidates
        return {"job_id": "rw_hy3d_from_staged_unit"}

    async def fake_get_job(remote_job_id: str) -> dict[str, Any]:
        assert remote_job_id == "rw_hy3d_from_staged_unit"
        return {
            "job_id": remote_job_id,
            "status": "completed",
            "result": {
                "result_json": {
                    "items": [
                        {
                            "rationale_id": "dir_01_silhouette",
                            "mesh_glb": "/remote/hy3d/dir_01_silhouette/mesh.glb",
                            "mesh_obj": "/remote/hy3d/dir_01_silhouette/mesh.obj",
                            "multiview_grid": "/remote/hy3d/dir_01_silhouette/grid.png",
                            "oss_prefix": "creativeflow/flowstudio/rw_hy3d/dir_01_silhouette",
                        }
                    ]
                }
            },
        }

    adapter.submit_hy3d_from_staged = fake_submit_hy3d_from_staged  # type: ignore[method-assign]
    adapter.get_job = fake_get_job  # type: ignore[method-assign]
    orchestrator = GenerationOrchestrator(
        store,
        WebSocketManager(),
        adapter,
        enable_3d_generation=True,
    )
    session = store.create_session(SessionCreateRequest(title="Candidate Hy3D"))
    asset = store.create_asset(
        AssetCreateRequest(session_id=session.session_id, object_type="chair", label="chair")
    )
    request = GenerationRequest.model_validate(
        {
            "session_id": session.session_id,
            "asset_id": asset.asset_id,
            "selection": {"type": "none"},
            "intent": {"mode": GenerationMode.diverge, "text": "try different overall shapes"},
            "generation": {
                "candidate_count": 1,
                "metadata": {"pipeline": "creativeflow-silhouette", "stage": "silhouette"},
            },
        }
    )
    job = store.create_job(request)
    candidate = Candidate(
        candidate_id="cand_generate_hy3d_unit",
        job_id=job.job_id,
        session_id=session.session_id,
        source_asset_id=asset.asset_id,
        label="silhouette direction",
        thumbnail_url="/api/v1/remote-worker/artifact-file?path=/remote/preview.png",
        metadata={
            "remote_result_path": "/remote/creativeflow_silhouette_result.json",
            "direction_id": "dir_01_silhouette",
            "pipeline_evidence": {
                "adapter": "remote-staged-creativeflow",
                "direction_id": "dir_01_silhouette",
            },
        },
    )
    store.save_candidate(candidate)

    updated = asyncio.run(orchestrator.generate_candidate_hy3d(candidate.candidate_id, session.session_id))

    assert captured["staged_result_path"] == "/remote/creativeflow_silhouette_result.json"
    assert captured["direction_ids"] == ["dir_01_silhouette"]
    assert updated.mesh_url == (
        "/api/v1/remote-worker/artifact-file?path=/remote/hy3d/dir_01_silhouette/mesh.glb"
    )
    assert updated.obj_url == (
        "/api/v1/remote-worker/artifact-file?path=/remote/hy3d/dir_01_silhouette/mesh.obj"
    )
    assert updated.metadata["hy3d_generated_from_candidate"] is True
    assert updated.metadata["remote_hy3d_job_id"] == "rw_hy3d_from_staged_unit"
    assert updated.metadata["pipeline_evidence"]["hy3d_mesh_url"] == updated.mesh_url


def test_generate_candidate_hy3d_rejects_candidates_without_staged_evidence() -> None:
    store = InMemoryStudioStore()
    orchestrator = GenerationOrchestrator(
        store,
        WebSocketManager(),
        RemoteCreativeFlowWorkerAdapter(base_url="http://worker.example"),
        enable_3d_generation=True,
    )
    session = store.create_session(SessionCreateRequest(title="Candidate Hy3D reject"))
    asset = store.create_asset(
        AssetCreateRequest(session_id=session.session_id, object_type="chair", label="chair")
    )
    request = GenerationRequest.model_validate(
        {
            "session_id": session.session_id,
            "asset_id": asset.asset_id,
            "selection": {"type": "none"},
            "intent": {"mode": GenerationMode.diverge, "text": "try different overall shapes"},
        }
    )
    job = store.create_job(request)
    candidate = Candidate(
        candidate_id="cand_generate_hy3d_missing_evidence",
        job_id=job.job_id,
        session_id=session.session_id,
        source_asset_id=asset.asset_id,
        label="image-only direction",
        metadata={"direction_id": "dir_01_silhouette"},
    )
    store.save_candidate(candidate)

    with pytest.raises(ValueError, match="remote staged CreativeFlow result path"):
        asyncio.run(orchestrator.generate_candidate_hy3d(candidate.candidate_id, session.session_id))


def test_hy3d_is_disabled_before_lookup_or_remote_submission() -> None:
    store = InMemoryStudioStore()
    adapter = RemoteCreativeFlowWorkerAdapter(base_url="http://worker.example")

    async def forbidden(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("remote Hy3D submission must not run")

    adapter.submit_hy3d_from_staged = forbidden  # type: ignore[method-assign]
    orchestrator = GenerationOrchestrator(store, WebSocketManager(), adapter)

    with pytest.raises(ThreeDGenerationDisabled) as error:
        asyncio.run(orchestrator.generate_candidate_hy3d("missing", "session"))

    assert error.value.code == "3D_GENERATION_DISABLED"


def test_generation_request_enriches_partfield_socket_metadata_from_asset_part() -> None:
    store = InMemoryStudioStore()
    adapter = RemoteCreativeFlowWorkerAdapter(base_url=None)
    orchestrator = GenerationOrchestrator(store, WebSocketManager(), adapter)
    session = store.create_session(SessionCreateRequest(title="PartField enrichment"))
    asset = store.create_asset(
        AssetCreateRequest(
            session_id=session.session_id,
            object_type="butterfly",
            label="butterfly",
            parts=[
                PartRecord(
                    part_id="pf_part_01",
                    label="primary wing cluster",
                    bbox=[0.1, 0.2, 0.3, 0.4],
                    metadata={
                        "source": "partfield",
                        "source_part_id": "part_2304",
                        "face_count": 11596,
                        "bbox3d": {
                            "min": [-0.08, -0.12, 0.32],
                            "max": [0.05, -0.04, 0.42],
                        },
                        "face_labels_path": "/remote/labels.npy",
                        "segmented_mesh_path": "/remote/segmented.ply",
                    },
                )
            ],
        )
    )
    request = GenerationRequest.model_validate(
        {
            "session_id": session.session_id,
            "asset_id": asset.asset_id,
            "selection": {"type": "part", "part_id": "pf_part_01"},
            "intent": {
                "mode": GenerationMode.replace,
                "text": "replace wing while preserving attachment boundary",
                "constraints": ["preserve attachment boundary"],
            },
            "generation": {
                "candidate_count": 1,
                "metadata": {
                    "pipeline": "creativeflow-part",
                    "stage": "part",
                    "fit_policy": "preserve_socket",
                },
            },
        }
    )

    job = asyncio.run(orchestrator.create_generation_job(request))

    stored_job = store.get_job(job.job_id)
    assert stored_job is not None
    assert stored_job.request is not None
    enriched = stored_job.request
    assert enriched.selection.label == "primary wing cluster"
    assert enriched.selection.bbox == [0.1, 0.2, 0.3, 0.4]
    assert enriched.selection.metadata["partfield"]["source_part_id"] == "part_2304"
    assert enriched.generation.metadata["target_part_metadata"]["face_labels_path"] == "/remote/labels.npy"

    target_part = adapter._target_part_payload(enriched)
    socket = adapter._socket_constraints(enriched)
    assert target_part["bbox3d"] == {"min": [-0.08, -0.12, 0.32], "max": [0.05, -0.04, 0.42]}
    assert target_part["face_count"] == 11596
    assert target_part["face_labels_path"] == "/remote/labels.npy"
    assert socket["bbox3d"] == target_part["bbox3d"]
    assert socket["source_part_id"] == "part_2304"
    assert socket["preserve_boundary"] is True


def test_fit_candidate_to_part_computes_obj_to_partfield_bbox_transform() -> None:
    store = InMemoryStudioStore()
    adapter = RemoteCreativeFlowWorkerAdapter(base_url="http://worker.example")

    async def fake_get_artifact_file(remote_path: str) -> tuple[bytes, str]:
        if remote_path == "/remote/source_face_labels.npy":
            return _npy_i4([2, 1]), "application/octet-stream"
        assert remote_path == "/remote/hy3d/mesh.obj"
        return (
            b"v -1 -0.5 0\nv 1 0.5 2\nv -1 0.5 2\nf 1 2 3\n",
            "text/plain",
        )

    adapter.get_artifact_file = fake_get_artifact_file  # type: ignore[method-assign]
    orchestrator = GenerationOrchestrator(store, WebSocketManager(), adapter)
    session = store.create_session(SessionCreateRequest(title="Candidate fit"))
    source_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "storage"
        / "files"
        / "test_sources"
        / "source_for_fit.obj"
    )
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(
        "v 10 20 30\nv 10 22 30\nv 14 20 30\nv 14 22 30\nf 1 2 3\nf 2 4 3\n",
        encoding="utf-8",
    )
    asset = store.create_asset(
        AssetCreateRequest(
            session_id=session.session_id,
            object_type="chair",
            label="chair",
            parts=[
                PartRecord(
                    part_id="pf_part_01",
                    label="arm rest",
                    metadata={
                        "bbox3d": {
                            "min": [10.0, 20.0, 30.0],
                            "max": [14.0, 22.0, 34.0],
                        },
                        "source": "partfield",
                        "source_part_id": "part_02",
                        "face_labels_path": "/remote/source_face_labels.npy",
                    },
                )
            ],
            metadata={"storage_path": str(source_path)},
        )
    )
    request = GenerationRequest.model_validate(
        {
            "session_id": session.session_id,
            "asset_id": asset.asset_id,
            "selection": {"type": "part", "part_id": "pf_part_01"},
            "intent": {"mode": GenerationMode.replace, "text": "replace arm rest"},
        }
    )
    job = store.create_job(request)
    candidate = Candidate(
        candidate_id="cand_fit_unit",
        job_id=job.job_id,
        session_id=session.session_id,
        source_asset_id=asset.asset_id,
        source_part_id="pf_part_01",
        label="replacement arm rest",
        obj_url="/api/v1/remote-worker/artifact-file?path=/remote/hy3d/mesh.obj",
        metadata={"pipeline_evidence": {"adapter": "remote-staged-creativeflow"}},
    )
    store.save_candidate(candidate)

    updated = asyncio.run(
        orchestrator.fit_candidate_to_part(
            candidate.candidate_id,
            CandidateFitRequest(session_id=session.session_id, policy="bbox_uniform"),
        )
    )

    fit_result = updated.metadata["fit_result"]
    assert fit_result["status"] == "geometry_preview_pass"
    assert fit_result["target_part_id"] == "pf_part_01"
    assert fit_result["source_bbox"] == {"min": [-1.0, -0.5, 0.0], "max": [1.0, 0.5, 2.0]}
    assert fit_result["target_bbox"] == {"min": [10.0, 20.0, 30.0], "max": [14.0, 22.0, 34.0]}
    assert fit_result["transform"]["scale"] == 2.0
    assert fit_result["transform"]["translation"] == [12.0, 21.0, 30.0]
    assert updated.mesh_url is None
    assert updated.obj_url == "/files/fitted/cand_fit_unit/assembly_preview.obj"
    assert updated.metadata["fitted_obj_url"] == "/files/fitted/cand_fit_unit/fitted.obj"
    assert updated.metadata["assembly_preview_obj_url"] == updated.obj_url
    assert updated.metadata["replacement_mode"] == "cluster_removed_assembly"
    assert updated.metadata["old_part_removed"] is True
    assert updated.metadata["removed_source_face_count"] == 1
    fitted_path = (
        Path(__file__).resolve().parents[1]
        / "storage"
        / "files"
        / "fitted"
        / "cand_fit_unit"
        / "fitted.obj"
    )
    assert "v 10 20 30" in fitted_path.read_text(encoding="utf-8")
    assert "v 14 22 34" in fitted_path.read_text(encoding="utf-8")
    assembly_path = fitted_path.with_name("assembly_preview.obj")
    assembly_text = assembly_path.read_text(encoding="utf-8")
    assert "Target PartField cluster faces were removed" in assembly_text
    assert "o flowstudio_fitted_replacement" in assembly_text
    assert "f 1 2 3" not in assembly_text
    assert "f 2 4 3" in assembly_text
    assert "f 5 6 7" in assembly_text
    evidence = updated.metadata["pipeline_evidence"]
    assert evidence["fit_status"] == "geometry_preview_pass"
    assert evidence["fit_target_part_id"] == "pf_part_01"
    assert evidence["fitted_obj_url"] == "/files/fitted/cand_fit_unit/fitted.obj"
    assert evidence["assembly_preview_obj_url"] == updated.obj_url
    assert evidence["old_part_removed"] is True
    assert evidence["seam_validation"]["status"] == "geometry_preview_pass"
    assert evidence["seam_validation"]["boundary_ring_checked"] is True
    assert evidence["seam_validation"]["boundary_edge_count"] == 1
    assert evidence["seam_validation"]["replacement_boundary_edge_count"] == 3
    assert evidence["seam_validation"]["boundary_match_score"] == 0.3333
    assert evidence["seam_validation"]["source_boundary_centroid"] == [12.0, 21.0, 30.0]
    assert evidence["seam_validation"]["replacement_boundary_centroid"] == [
        11.333333,
        21.333333,
        32.666667,
    ]
    assert evidence["seam_validation"]["boundary_position_score"] > 0.5
    assert evidence["seam_validation"]["socket_compatibility_score"] == pytest.approx(0.718, abs=0.002)
    assert evidence["socket_compatibility_score"] == pytest.approx(0.718, abs=0.002)
    assert updated.scores["socket_compatibility"] == pytest.approx(0.718, abs=0.002)
    assert evidence["seam_validation"]["watertight_boolean"] is False
    assert evidence["fit_quality"]["bbox_validation"]["status"] == "pass"


def _npy_i4(values: list[int]) -> bytes:
    header = f"{{'descr': '<i4', 'fortran_order': False, 'shape': ({len(values)},), }}".encode(
        "latin1"
    )
    padding = b" " * ((16 - ((10 + len(header) + 1) % 16)) % 16)
    header = header + padding + b"\n"
    return b"\x93NUMPY\x01\x00" + struct.pack("<H", len(header)) + header + struct.pack(
        f"<{len(values)}i", *values
    )
