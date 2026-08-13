from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


API_URL = "http://127.0.0.1:18000"


def run_json(command: list[str]) -> dict:
    completed = subprocess.run(command, check=True, text=True, capture_output=True)
    return json.loads(completed.stdout)


def main() -> None:
    session = run_json(
        [
            "curl",
            "-fsS",
            "-X",
            "POST",
            f"{API_URL}/api/v1/sessions",
            "-H",
            "Content-Type: application/json",
            "-d",
            '{"title":"cloud geometry smoke"}',
        ]
    )
    session_id = session["session_id"]

    with tempfile.TemporaryDirectory() as tmp:
        obj_path = Path(tmp) / "flowstudio_smoke.obj"
        obj_path.write_text(
            "\n".join(
                [
                    "v 0 0 0",
                    "v 2 0 0",
                    "v 0 3 0",
                    "v 0 0 4",
                    "f 1 2 3",
                    "f 1 2 4",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        asset = run_json(
            [
                "curl",
                "-fsS",
                "-X",
                "POST",
                f"{API_URL}/api/v1/assets/upload",
                "-F",
                f"session_id={session_id}",
                "-F",
                "object_type=smoke",
                "-F",
                "label=smoke_obj",
                "-F",
                f"file=@{obj_path}",
            ]
        )
    asset_id = asset["asset_id"]

    geometry = run_json(
        [
            "curl",
            "-fsS",
            "-X",
            "POST",
            f"{API_URL}/api/v1/geometry/normalize",
            "-H",
            "Content-Type: application/json",
            "-d",
            json.dumps({"session_id": session_id, "asset_id": asset_id}),
        ]
    )
    print(
        json.dumps(
            {
                "ok": geometry.get("ok"),
                "job_id": geometry.get("job_id"),
                "status": geometry.get("status"),
                "result_mesh_url": geometry.get("result_mesh_url"),
                "remote_geometry_job_id": (geometry.get("metrics") or {}).get("remote_geometry_job_id"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
