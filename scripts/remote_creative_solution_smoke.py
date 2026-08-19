from __future__ import annotations

import json
import os
import sys
import textwrap

import paramiko


HOST = os.getenv("FLOWSTUDIO_REMOTE_HOST", "connect.weste.seetacloud.com")
PORT = int(os.getenv("FLOWSTUDIO_REMOTE_SSH_PORT", "10980"))
USER = os.getenv("FLOWSTUDIO_REMOTE_USER", "root")
PASSWORD = os.environ["FLOWSTUDIO_REMOTE_PASSWORD"]


REMOTE_SCRIPT = r"""
set -e
cd /root/flowstudio_app
/root/flowstudio_app/.venv/bin/python - <<'RPY'
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8000"


def post(path, payload):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def get(path, timeout=20):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


session = post("/api/v1/sessions", {"title": "server smoke creative solution space snowman"})
session_id = session["session_id"]
asset = post(
    "/api/v1/assets",
    {
        "session_id": session_id,
        "object_type": "snowman",
        "label": "Snowman source for staged CreativeFlow smoke",
        "thumbnail_url": (
            "/api/v1/remote-worker/artifact-file?path="
            "/root/autodl-tmp/flowstudio_worker_runs/snowman_inputs/source.png"
        ),
        "metadata": {
            "source": "server_smoke_existing_worker_input",
            "source_image_path": "/root/autodl-tmp/flowstudio_worker_runs/snowman_inputs/source.png",
            "remote_asset": {
                "source": "existing_worker_file",
                "path": (
                    "/root/autodl-tmp/creativeflow_variations_20260716/"
                    "hunyuan3d/source/snowman_source/mesh.glb"
                ),
            },
            "server_smoke": True,
        },
    },
)
asset_id = asset["asset_id"]
job = post(
    "/api/v1/generation/diverge",
    {
        "session_id": session_id,
        "asset_id": asset_id,
        "selection": {"type": "none"},
        "intent": {
            "mode": "diverge",
            "text": (
                "Make this snowman cuter by changing only the global silhouette and proportion; "
                "keep snowman identity, top hat, red scarf, carrot nose, twig arms and coal buttons recognizable."
            ),
            "constraints": [
                "preserve snowman identity",
                "preserve accessory inventory",
                "no 3D mesh in this smoke",
            ],
        },
        "generation": {
            "candidate_count": 1,
            "diversity": 0.45,
            "output_format": "glb",
            "metadata": {
                "pipeline": "creativeflow-silhouette",
                "stage": "silhouette",
                "fidelity": "low",
                "source_image_path": "/root/autodl-tmp/flowstudio_worker_runs/snowman_inputs/source.png",
                "divergence_axes": ["silhouette", "proportion", "cuteness"],
                "image_options": {
                    "width": 512,
                    "height": 512,
                    "steps": 6,
                    "attempts_per_candidate": 1,
                    "seed": 73,
                    "source_strength": 0.65,
                },
                "mesh_options": {"enabled": False, "max_candidates": 1},
                "kg_options": {
                    "top_k": 1,
                    "candidate_pool_size": 4,
                    "cache_mode": "cache_first",
                    "allow_partial_graph": True,
                    "request_timeout_sec": 3,
                    "direction_timeout_sec": 60,
                    "scoring_enabled": False,
                    "skip_kg_expansion": True,
                    "allow_rule_fallback": True,
                },
                "assistance_trigger": "server_smoke_minimal_no_hy3d",
            },
        },
    },
)
print("SESSION", session_id)
print("ASSET", asset_id)
print("JOB", json.dumps(job, ensure_ascii=False))
job_id = job["job_id"]
last = None
for index in range(90):
    state = get("/api/v1/jobs/" + job_id)
    digest = {key: state.get(key) for key in ["status", "stage", "progress", "message", "error"]}
    if digest != last:
        print("POLL", index, json.dumps(digest, ensure_ascii=False))
        last = digest
    if state.get("status") in ["completed", "failed", "cancelled"]:
        break
    time.sleep(2)
else:
    print("POLL_TIMEOUT")

state = get("/api/v1/jobs/" + job_id)
print(
    "FINAL_JOB",
    json.dumps(
        {
            key: state.get(key)
            for key in [
                "job_id",
                "status",
                "stage",
                "progress",
                "message",
                "error",
                "candidate_ids",
                "metadata",
            ]
        },
        ensure_ascii=False,
        indent=2,
    )[:6000],
)
candidates = get("/api/v1/jobs/" + job_id + "/candidates")
slim = []
for candidate in candidates:
    metadata = candidate.get("metadata") or {}
    pipeline_evidence = metadata.get("pipeline_evidence") or {}
    slim.append(
        {
            "candidate_id": candidate.get("candidate_id"),
            "label": candidate.get("label"),
            "thumbnail_url": candidate.get("thumbnail_url"),
            "solution_space": candidate.get("solution_space"),
            "scores": candidate.get("scores"),
            "pipeline_evidence": pipeline_evidence,
            "remote_direction_keys": sorted((metadata.get("remote_direction") or {}).keys())[:20],
        }
    )
print("CANDIDATES", json.dumps(slim, ensure_ascii=False, indent=2)[:8000])
RPY
free -h
nvidia-smi --query-gpu=index,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits || true
"""


def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=HOST,
        port=PORT,
        username=USER,
        password=PASSWORD,
        timeout=20,
        banner_timeout=20,
        auth_timeout=20,
    )
    stdin, stdout, stderr = client.exec_command("bash -s", timeout=260)
    stdin.write(REMOTE_SCRIPT)
    stdin.channel.shutdown_write()
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    client.close()
    print(out)
    if err:
        print("STDERR:\n" + err, file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
