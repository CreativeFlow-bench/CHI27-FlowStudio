"""Runtime service inventory and bootstrap endpoints (cloud operations)."""

from __future__ import annotations

from fastapi import APIRouter

from app.services import system_services


def create_system_router(*, enabled: bool = True) -> APIRouter:
    router = APIRouter(tags=["system"])

    @router.get("/api/v1/system/services")
    async def list_services() -> dict[str, object]:
        services = await system_services.probe_all() if enabled else []
        return {
            "ok": True,
            "enabled": enabled,
            "bootstrap": system_services.bootstrap_status(),
            "services": services,
        }

    @router.post("/api/v1/system/services/bootstrap")
    async def bootstrap_services() -> dict[str, object]:
        if not enabled:
            return {"ok": False, "error": "system services panel is disabled"}
        task_id = await system_services.start_bootstrap()
        return {
            "ok": True,
            "bootstrap_id": task_id,
            "message": "missing services are being started one by one",
        }

    @router.post("/api/v1/system/services/{service_id}/start")
    async def start_service(service_id: str) -> dict[str, object]:
        if not enabled:
            return {"ok": False, "error": "system services panel is disabled"}
        result = await system_services.start_service(service_id)
        return {"ok": bool(result.get("ok")), **result}

    return router
