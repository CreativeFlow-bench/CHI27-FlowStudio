import json
from types import SimpleNamespace

from job_orchestration import apply_hy3d_progress_line


def test_apply_hy3d_progress_line_updates_message_and_progress() -> None:
    job = SimpleNamespace(message="Process started", stage="hy3d", progress=0.2, updated_at="")
    line = "HY3D_PROGRESS " + json.dumps(
        {"stage": "shape", "progress": 0.22, "message": "重建形体"},
        ensure_ascii=False,
    )
    assert apply_hy3d_progress_line(job, line) is True
    assert job.message == "重建形体"
    assert job.stage == "shape"
    assert job.progress == 0.22


def test_apply_hy3d_progress_line_ignores_noise() -> None:
    job = SimpleNamespace(message="Process started", stage="hy3d", progress=0.2, updated_at="")
    assert apply_hy3d_progress_line(job, "loading weights") is False
    assert job.message == "Process started"
