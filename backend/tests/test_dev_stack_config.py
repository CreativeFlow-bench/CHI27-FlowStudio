from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_dev_stack_prints_local_external_api_defaults_without_starting_services() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    environment = {
        **os.environ,
        "FLOWSTUDIO_PRINT_CONFIG": "1",
    }
    environment.pop("ENABLE_LEGACY_LOCAL_MODELS", None)
    environment.pop("ENABLE_3D_GENERATION", None)

    completed = subprocess.run(
        ["bash", str(repo_root / "scripts" / "dev_stack.sh")],
        cwd=repo_root,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "backend=http://127.0.0.1:18001" in completed.stdout
    assert "frontend=http://127.0.0.1:5184" in completed.stdout
    assert "legacy_models=false" in completed.stdout
    assert "3d_generation=false" in completed.stdout
    assert "remote_worker=" in completed.stdout
    assert "127.0.0.1:18100" not in completed.stdout
    assert "127.0.0.1:18081" not in completed.stdout
