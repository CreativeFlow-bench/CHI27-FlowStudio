from pathlib import Path

from job_orchestration import WorkerJob, find_reusable_hy3d_job


def _job(tmp_path: Path, *, job_id: str, status: str, image: Path, mesh: Path | None, updated_at: str) -> WorkerJob:
    result = {}
    if mesh is not None:
        result = {
            "result_json": {
                "items": [{"ok": True, "input_image": str(image), "mesh_pbr_glb": str(mesh)}],
            }
        }
    return WorkerJob(
        job_id=job_id,
        flowstudio_job_id="fs",
        kind="hy3d_from_staged",
        status=status,
        work_dir=str(tmp_path / job_id),
        result=result,
        updated_at=updated_at,
    )


def test_find_reusable_hy3d_job_returns_completed_mesh(tmp_path: Path) -> None:
    image = tmp_path / "candidate_01.png"
    image.write_bytes(b"png")
    mesh = tmp_path / "mesh_pbr.glb"
    mesh.write_bytes(b"glb")
    done = _job(tmp_path, job_id="rw_done", status="completed", image=image, mesh=mesh, updated_at="2026-08-19T10:00:00+00:00")
    found = find_reusable_hy3d_job({str(image)}, {done.job_id: done})
    assert found is done


def test_find_reusable_hy3d_job_prefers_completed_over_running(tmp_path: Path) -> None:
    image = tmp_path / "candidate_01.png"
    image.write_bytes(b"png")
    mesh = tmp_path / "mesh_pbr.glb"
    mesh.write_bytes(b"glb")
    running = _job(tmp_path, job_id="rw_run", status="running", image=image, mesh=None, updated_at="2026-08-19T11:00:00+00:00")
    running.request = {"staged_result_path": str(tmp_path / "missing.json")}
    (tmp_path / "rw_run").mkdir()
    transfer = tmp_path / "rw_run" / "staged_transfer_for_hy3d.json"
    transfer.write_text('{"generated_targets":[{"canonical_image":"%s"}]}' % image, encoding="utf-8")
    done = _job(tmp_path, job_id="rw_done", status="completed", image=image, mesh=mesh, updated_at="2026-08-19T10:00:00+00:00")
    found = find_reusable_hy3d_job({str(image)}, {running.job_id: running, done.job_id: done})
    assert found is done


def test_find_reusable_hy3d_job_returns_in_flight_when_no_mesh(tmp_path: Path) -> None:
    image = tmp_path / "candidate_01.png"
    image.write_bytes(b"png")
    running = _job(tmp_path, job_id="rw_run", status="queued", image=image, mesh=None, updated_at="2026-08-19T11:00:00+00:00")
    (tmp_path / "rw_run").mkdir()
    (tmp_path / "rw_run" / "staged_transfer_for_hy3d.json").write_text(
        '{"generated_targets":[{"canonical_image":"%s"}]}' % image,
        encoding="utf-8",
    )
    found = find_reusable_hy3d_job({str(image)}, {running.job_id: running})
    assert found is running


def test_find_reusable_hy3d_job_skips_completed_without_file(tmp_path: Path) -> None:
    image = tmp_path / "candidate_01.png"
    image.write_bytes(b"png")
    missing = tmp_path / "gone.glb"
    done = _job(tmp_path, job_id="rw_gone", status="completed", image=image, mesh=missing, updated_at="2026-08-19T10:00:00+00:00")
    assert find_reusable_hy3d_job({str(image)}, {done.job_id: done}) is None


def test_find_reusable_hy3d_job_reuses_failed_job_if_mesh_exists(tmp_path: Path) -> None:
    image = tmp_path / "candidate_01.png"
    image.write_bytes(b"png")
    mesh = tmp_path / "mesh_pbr.glb"
    mesh.write_bytes(b"glb")
    failed = _job(tmp_path, job_id="rw_failed", status="failed", image=image, mesh=mesh, updated_at="2026-08-19T10:00:00+00:00")
    found = find_reusable_hy3d_job({str(image)}, {failed.job_id: failed})
    assert found is failed
