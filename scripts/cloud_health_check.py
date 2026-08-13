from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


BACKEND_URL = os.getenv("FLOWSTUDIO_CLOUD_BACKEND_URL", "http://127.0.0.1:18000")
WORKER_URL = os.getenv("FLOWSTUDIO_CLOUD_WORKER_URL", "http://127.0.0.1:18100")


def get_json(url: str, timeout: float = 5) -> tuple[bool, dict[str, Any] | str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return True, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')[:300]}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def reachable_value(probe: Any) -> bool | None:
    """Normalize preflight probe shapes without turning a warning into a crash."""
    if isinstance(probe, dict):
        value = probe.get("reachable")
        return value if isinstance(value, bool) else None
    return None


def main() -> int:
    ok = True
    backend_ok, backend = get_json(f"{BACKEND_URL}/health")
    worker_ok, worker = get_json(f"{WORKER_URL}/health")
    preflight_ok, preflight = get_json(f"{WORKER_URL}/preflight/creativeflow", timeout=30)

    if not backend_ok:
        ok = False
        print(f"cloud-backend: FAIL {backend}")
    else:
        workers = backend.get("workers") or {}
        print(
            "cloud-backend: OK "
            + json.dumps(
                {
                    "remote_worker_ok": backend.get("remote_worker_ok"),
                    "render_mode": (workers.get("render_preview") or {}).get("mode"),
                    "geometry": (workers.get("geometry_processing") or {}).get("ok"),
                    "sessions": backend.get("sessions"),
                    "jobs": backend.get("jobs"),
                },
                separators=(",", ":"),
            )
        )
        ok = ok and bool(backend.get("remote_worker_ok"))

    if not worker_ok:
        ok = False
        print(f"remote-worker: FAIL {worker}")
    else:
        pipeline = worker.get("creativeflow_pipeline") or {}
        print(
            "remote-worker: OK "
            + json.dumps(
                {
                    "geometry": worker.get("geometry_worker_ready"),
                    "render": worker.get("render_preview_ready"),
                    "blender": worker.get("blender_exists"),
                    "segmentation_adapter": worker.get("segmentation_adapter"),
                    "segmentation_ready": worker.get("segmentation_worker_ready")
                    or worker.get("sam3d_ready"),
                    "sam3d_root": worker.get("sam3d_root_exists"),
                    "sam3d_python": worker.get("sam3d_python_exists"),
                    "transfer_minimal": pipeline.get("minimal_transfer_ready"),
                    "hy3d": pipeline.get("hy3d_ready"),
                    "jobs": worker.get("jobs"),
                },
                separators=(",", ":"),
            )
        )
        ok = ok and bool(worker.get("geometry_worker_ready")) and bool(worker.get("render_preview_ready"))

    if not preflight_ok:
        ok = False
        print(f"remote-preflight: FAIL {preflight}")
    else:
        qwen = ((preflight.get("qwen_image") or {}).get("probe") or {})
        oss = ((preflight.get("oss") or {}).get("configured_keys") or {})
        kb = preflight.get("kb_network") or {}
        print(
            "remote-preflight: OK "
            + json.dumps(
                {
                    "core_ready": preflight.get("core_ready"),
                    "long_run_ready": preflight.get("long_run_ready"),
                    "qwen": qwen.get("reachable"),
                    "qwen_status": qwen.get("status"),
                    "oss_keys": f"{sum(1 for value in oss.values() if value)}/{len(oss)}",
                    "kb": {name: reachable_value(probe) for name, probe in kb.items()},
                    "warnings": len(preflight.get("warnings") or []),
                },
                separators=(",", ":"),
            )
        )
        ok = ok and bool(preflight.get("core_ready"))

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
