"""Declarative runtime service inventory for the FlowStudio cloud deployment.

The backend process lives on the same GPU host as the other services, so this
module both *reports* their health and can *start* the ones that went down.
Every start command is guarded by an explicit path existence check, so the
same code is harmless when the backend runs on a dev laptop where the cloud
paths do not exist.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# id -> definition.  `start` is optional; when present, all paths inside the
# command/cwd must exist before the service is offered as "startable".
# Single-host deploy (weste): Hunyuan worker, no local Qwen-Image / planner.
_SERVICE_DEFS: list[dict[str, Any]] = [
    {
        "id": "backend",
        "name": "FlowStudio Backend",
        "name_zh": "后端 API",
        "port": 18000,
        "group": "core",
        "required": True,
        "description": "本服务（当前进程），通常由运维脚本管理。",
        "health_url": "http://127.0.0.1:18000/health",
        "startable": False,
        "start_timeout_sec": 0,
    },
    {
        "id": "remote_worker",
        "name": "CreativeFlow Worker",
        "name_zh": "生成 Worker",
        "port": 18100,
        "group": "core",
        "required": True,
        "description": "执行图像/网格生成任务的后端 worker。",
        "health_url": "http://127.0.0.1:18100/health",
        "start": {
            "cwd": "/root/flowstudio_app/remote_worker",
            "cmd": [
                "/root/miniconda3/envs/hunyuan3d21/bin/python",
                "-m",
                "uvicorn",
                "app:app",
                "--host",
                "127.0.0.1",
                "--port",
                "18100",
            ],
            "env": {
                "CF_WORKER_PYTHON": "/root/miniconda3/envs/hunyuan3d21/bin/python",
                "CF_HY3D_PYTHON": "/root/miniconda3/envs/hunyuan3d21/bin/python",
                "CF_HY3D_SLOTS_PER_GPU": "2",
            },
        },
        "start_timeout_sec": 60,
    },
    {
        "id": "frontend",
        "name": "FlowStudio Web",
        "name_zh": "前端页面",
        "port": 5173,
        "group": "core",
        "required": True,
        "description": "静态前端站点（dist）。",
        "health_url": "http://127.0.0.1:5173/",
        "start": {
            "cwd": "/root/flowstudio_app/frontend/dist",
            "cmd": [
                "/root/miniconda3/bin/python3",
                "-m",
                "http.server",
                "5173",
                "--bind",
                "0.0.0.0",
                "--directory",
                "/root/flowstudio_app/frontend/dist",
            ],
        },
        "start_timeout_sec": 30,
    },
    {
        "id": "qwen_image",
        "name": "Qwen-Image",
        "name_zh": "文生图模型",
        "port": 18082,
        "group": "gpu",
        "required": True,
        "description": "Qwen-Image 生成/编辑服务（GPU，显式启动）。默认关闭；云端图片走 MODEL_API。",
        "health_url": "http://127.0.0.1:18082/health",
        "start": {
            "cwd": "/root/creativeflow_image_service",
            "cmd": [
                "/root/autodl-tmp/venvs/torch5090/bin/uvicorn",
                "app_qwen_image:app",
                "--host",
                "127.0.0.1",
                "--port",
                "18082",
            ],
            "env": {
                "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
                "QWEN_IMAGE_UNLOAD_AFTER_GENERATE": "0",
            },
        },
        "start_timeout_sec": 300,
    },
    {
        "id": "kg_gateway",
        "name": "KG Gateway Proxy",
        "name_zh": "知识图谱代理",
        "port": 33210,
        "group": "network",
        "required": False,
        "description": "到网关 VPS 的反向隧道 + HTTP/SOCKS 代理，用于知识图谱实时查询。",
        "health_url": "http://127.0.0.1:33210/",
        "start": {
            "cwd": "/root/flowstudio_app/remote_worker",
            "cmd": ["bash", "/root/flowstudio_app/remote_worker/run_api_reverse_tunnel.sh"],
        },
        "start_timeout_sec": 45,
    },
    {
        "id": "creativeflow_api",
        "name": "CreativeFlow API v1",
        "name_zh": "CreativeFlow 遗留 API",
        "port": 18080,
        "group": "optional",
        "required": False,
        "description": "遗留 /api/v1/variation-jobs 服务；FlowStudio 主链路不依赖。",
        "health_url": "http://127.0.0.1:18080/health",
        "start": {
            "cwd": "/root/flowstudio_app/remote_worker",
            "cmd": ["bash", "/root/flowstudio_app/remote_worker/run_api_v1.sh"],
            "requires_paths": [
                "/root/flowstudio_app/remote_worker/run_api_v1.sh",
                "/root/.creativeflow_api_v1.key",
            ],
            "env_from_file": {"CF_API_KEY": "/root/.creativeflow_api_v1.key"},
        },
        "start_timeout_sec": 60,
    },
]


_STARTING: dict[str, str] = {}
_START_RESULTS: dict[str, dict[str, Any]] = {}
_BOOTSTRAP_TASKS: dict[str, asyncio.Task[Any]] = {}
_BOOT_GPU_TASKS: list[asyncio.Task[Any]] = []
_LOCK = asyncio.Lock()
_ENABLE_LEGACY_MODELS = False
_ENABLE_3D = False

# Retired: planner_llm / intent_vlm (second-GPU Qwen). Optional local image model remains gated.
_LEGACY_MODEL_SERVICE_IDS = {"qwen_image"}
_THREE_D_SERVICE_IDS = {"remote_worker", "creativeflow_api"}


def configure_runtime(*, enable_legacy_models: bool, enable_3d: bool) -> None:
    """Set process-wide inventory visibility before routers probe services."""
    global _ENABLE_LEGACY_MODELS, _ENABLE_3D
    _ENABLE_LEGACY_MODELS = bool(enable_legacy_models)
    _ENABLE_3D = bool(enable_3d)


def _env_id(service_id: str) -> str:
    return service_id.upper()


def _definitions() -> list[dict[str, Any]]:
    defs: list[dict[str, Any]] = []
    for definition in _SERVICE_DEFS:
        if (
            definition["id"] in _LEGACY_MODEL_SERVICE_IDS
            and not _ENABLE_LEGACY_MODELS
        ):
            continue
        if definition["id"] in _THREE_D_SERVICE_IDS and not _ENABLE_3D:
            continue
        item = dict(definition)
        override = os.getenv(f"FLOWSTUDIO_SERVICE_{_env_id(item['id'])}_URL")
        if override:
            item["health_url"] = override
        start = item.get("start")
        if start:
            item["startable"] = _start_is_available(start)
        else:
            item["startable"] = False
        defs.append(item)
    return defs


def _start_is_available(start: dict[str, Any]) -> bool:
    cwd = start.get("cwd")
    if cwd and not Path(cwd).is_dir():
        return False
    for path in start.get("requires_paths") or []:
        if not Path(path).exists():
            return False
    cmd = start.get("cmd") or []
    for part in cmd:
        if part.startswith("/") and not Path(part).exists():
            return False
    return True


def _log_root() -> Path:
    root = Path(os.getenv("FLOWSTUDIO_CLOUD_LOG_DIR", "/root/flowstudio_app/logs"))
    try:
        root.mkdir(parents=True, exist_ok=True)
        return root
    except OSError:
        fallback = Path(tempfile.gettempdir()) / "flowstudio_services"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def _probe_sync(definition: dict[str, Any]) -> dict[str, Any]:
    service_id = str(definition["id"])
    health_url = str(definition["health_url"])
    started_at = _STARTING.get(service_id)
    start_result = _START_RESULTS.get(service_id) or {}
    started_ms = time.time()
    try:
        request = Request(health_url, headers={"User-Agent": "flowstudio-services"})
        with urlopen(request, timeout=3) as response:
            status = response.status
        state = "up" if status < 500 else "down"
        detail = f"HTTP {status}"
    except HTTPError as exc:
        state = "up" if exc.code < 500 else "down"
        detail = f"HTTP {exc.code}"
    except (URLError, TimeoutError, OSError) as exc:
        state = "down"
        detail = type(exc).__name__
    if state == "down" and started_at:
        state = "starting"
    return {
        "id": service_id,
        "name": definition.get("name"),
        "name_zh": definition.get("name_zh"),
        "port": definition.get("port"),
        "group": definition.get("group"),
        "required": bool(definition.get("required")),
        "description": definition.get("description"),
        "state": state,
        "detail": detail,
        "latency_ms": round((time.time() - started_ms) * 1000),
        "startable": bool(definition.get("startable")),
        "starting": started_at or None,
        "last_start": start_result or None,
    }


async def _probe_one(definition: dict[str, Any]) -> dict[str, Any]:
    # Run the blocking HTTP probe off the event loop; probing the backend's own
    # health URL would otherwise deadlock a single-worker uvicorn.
    return await asyncio.to_thread(_probe_sync, definition)


async def probe_all() -> list[dict[str, Any]]:
    definitions = _definitions()
    results = await asyncio.gather(*(_probe_one(item) for item in definitions))
    return sorted(results, key=lambda item: (item["group"], item["port"] or 0))


async def probe_one(service_id: str) -> dict[str, Any] | None:
    for definition in _definitions():
        if definition["id"] == service_id:
            return await _probe_one(definition)
    return None


def _start_detached(definition: dict[str, Any]) -> None:
    start = definition.get("start") or {}
    log_path = _log_root() / f"{definition['id']}.log"
    env = os.environ.copy()
    env.update({str(key): str(value) for key, value in (start.get("env") or {}).items()})
    for key, path in (start.get("env_from_file") or {}).items():
        try:
            env[key] = Path(path).read_text(encoding="utf-8").strip()
        except OSError:
            pass
    process = subprocess.Popen(
        list(start["cmd"]),
        cwd=str(start.get("cwd")) if start.get("cwd") else None,
        env=env,
        stdout=log_path.open("ab"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    _START_RESULTS[definition["id"]] = {
        "pid": process.pid,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "log": str(log_path),
        "error": None,
    }


async def _wait_healthy(definition: dict[str, Any], timeout_sec: int) -> dict[str, Any]:
    deadline = time.time() + timeout_sec
    last = None
    while time.time() < deadline:
        last = await _probe_one(definition)
        if last["state"] == "up":
            _STARTING.pop(definition["id"], None)
            return last
        await asyncio.sleep(2)
    _STARTING.pop(definition["id"], None)
    result = _START_RESULTS.get(definition["id"]) or {}
    result["error"] = f"service did not become healthy within {timeout_sec}s"
    _START_RESULTS[definition["id"]] = result
    last = last or await _probe_one(definition)
    return last


async def start_service(service_id: str) -> dict[str, Any]:
    definition = next((item for item in _definitions() if item["id"] == service_id), None)
    if definition is None:
        return {"ok": False, "error": f"unknown service: {service_id}"}
    if not definition.get("startable"):
        return {
            "ok": False,
            "error": "service is not startable on this host",
            "state": (await _probe_one(definition))["state"],
        }
    async with _LOCK:
        current = await _probe_one(definition)
        if current["state"] == "up":
            return {"ok": True, "state": "up", "message": "already running"}
        if _STARTING.get(service_id):
            return {"ok": True, "state": "starting", "message": "already starting"}
        _STARTING[service_id] = time.strftime("%Y-%m-%dT%H:%M:%S")
        try:
            await asyncio.to_thread(_start_detached, definition)
        except Exception as exc:
            _STARTING.pop(service_id, None)
            _START_RESULTS[service_id] = {"error": str(exc)}
            return {"ok": False, "error": str(exc)}
    final = await _wait_healthy(definition, int(definition.get("start_timeout_sec") or 60))
    return {"ok": final["state"] == "up", **final}


async def start_bootstrap() -> str:
    task_id = f"boot_{int(time.time())}"
    definitions = [item for item in _definitions() if item.get("startable") and item.get("required")]
    definitions.sort(key=lambda item: 0 if item["group"] == "core" else 1 if item["group"] == "gpu" else 2)

    async def run() -> None:
        for definition in definitions:
            try:
                await start_service(definition["id"])
            except Exception as exc:
                _START_RESULTS[definition["id"]] = {
                    **_START_RESULTS.get(definition["id"], {}),
                    "error": str(exc),
                }

    _BOOTSTRAP_TASKS[task_id] = asyncio.create_task(run())
    return task_id


def bootstrap_status() -> dict[str, Any]:
    return {
        "running": [key for key, task in _BOOTSTRAP_TASKS.items() if not task.done()],
        "recent": {
            key: {
                "done": task.done(),
                "cancelled": task.cancelled(),
            }
            for key, task in _BOOTSTRAP_TASKS.items()
        },
    }


async def auto_bootstrap_infra() -> list[dict[str, Any]]:
    """Start infrastructure + required GPU model services on boot.

    Cheap services (worker / frontend / kg gateway) start on boot.
    Local Qwen-Image / planner are retired; images go through MODEL_API.
    """
    infra_ids = {
        "kg_gateway",
        "remote_worker",
        "frontend",
    }
    started: list[dict[str, Any]] = []
    for definition in _definitions():
        if definition["id"] not in infra_ids or not definition.get("startable"):
            continue
        current = await _probe_one(definition)
        if current["state"] == "up":
            continue
        if definition["id"] in {"kg_gateway"}:
            # GPU/network services: background so the backend does not wait.
            async def _boot_service(service_id: str = definition["id"]) -> None:
                try:
                    await start_service(service_id)
                except Exception as exc:  # pragma: no cover - diagnostics only
                    print(f"AUTO_BOOTSTRAP {service_id} failed: {exc}", flush=True)
                    _START_RESULTS[service_id] = {"error": str(exc)}

            _BOOT_GPU_TASKS.append(asyncio.create_task(_boot_service()))
            started.append({"id": definition["id"], "ok": None, "state": "starting"})
            continue
        try:
            result = await start_service(definition["id"])
            started.append({"id": definition["id"], **result})
        except Exception as exc:
            started.append({"id": definition["id"], "ok": False, "error": str(exc)})
    return started
