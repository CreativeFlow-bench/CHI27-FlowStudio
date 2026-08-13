from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path


API_URL = os.getenv("FLOWSTUDIO_CLOUD_API_URL", "http://127.0.0.1:18000")


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
            '{"title":"frontend 3d viewer case smoke"}',
        ]
    )
    session_id = session["session_id"]

    with tempfile.TemporaryDirectory() as tmp:
        obj_path = Path(tmp) / "viewer_case.obj"
        obj_path.write_text(
            "\n".join(
                [
                    "o flowstudio_viewer_case",
                    "v -1 -1 -1",
                    "v 1 -1 -1",
                    "v 1 1 -1",
                    "v -1 1 -1",
                    "v -1 -1 1",
                    "v 1 -1 1",
                    "v 1 1 1",
                    "v -1 1 1",
                    "f 1 2 3 4",
                    "f 5 8 7 6",
                    "f 1 5 6 2",
                    "f 2 6 7 3",
                    "f 3 7 8 4",
                    "f 5 1 4 8",
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
                "object_type=viewer_case",
                "-F",
                "label=viewer_case_obj",
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
    normalized_url = geometry.get("result_mesh_url")

    render = run_json(
        [
            "curl",
            "-fsS",
            "-X",
            "POST",
            f"{API_URL}/api/v1/render/thumbnail",
            "-H",
            "Content-Type: application/json",
            "-d",
            json.dumps({"session_id": session_id, "source_mesh_url": normalized_url}),
        ]
    )

    case = run_json(
        [
            "curl",
            "-fsS",
            "-X",
            "POST",
            f"{API_URL}/api/v1/cases",
            "-H",
            "Content-Type: application/json",
            "-d",
            json.dumps(
                {
                    "session_id": session_id,
                    "asset_id": asset_id,
                    "title": "Frontend 3D viewer case smoke",
                    "accepted_candidate_ids": [],
                    "notes": "Real OBJ upload, remote geometry normalize, remote Blender thumbnail.",
                    "metadata": {
                        "normalized_mesh_url": normalized_url,
                        "thumbnail_url": render.get("thumbnail_url"),
                        "geometry_job_id": geometry.get("job_id"),
                        "remote_geometry_job_id": (geometry.get("metrics") or {}).get("remote_geometry_job_id"),
                        "render_job_id": render.get("job_id"),
                        "remote_render_job_id": (render.get("metadata") or {}).get("remote_render_job_id"),
                    },
                }
            ),
        ]
    )

    print(
        json.dumps(
            {
                "ok": True,
                "session_id": session_id,
                "asset_id": asset_id,
                "asset_obj_url": asset.get("obj_url"),
                "normalized_mesh_url": normalized_url,
                "thumbnail_url": render.get("thumbnail_url"),
                "case_id": case.get("case_id"),
                "case_url": (case.get("metadata") or {}).get("case_url"),
                "report_url": case.get("report_url"),
                "remote_geometry_job_id": (geometry.get("metrics") or {}).get("remote_geometry_job_id"),
                "remote_render_job_id": (render.get("metadata") or {}).get("remote_render_job_id"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
