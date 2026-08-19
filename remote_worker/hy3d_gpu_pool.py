"""Per-GPU Hunyuan slots. Extra jobs wait; adding a card is an env/restart change."""

from __future__ import annotations

import asyncio
import os
import subprocess


def list_cuda_devices() -> list[str]:
    raw = os.getenv("CF_HY3D_GPUS", "").strip()
    if raw:
        return [part.strip() for part in raw.split(",") if part.strip()]
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index", "--format=csv,noheader"],
            text=True,
            timeout=5,
        )
        found = [line.strip() for line in output.splitlines() if line.strip().isdigit()]
        if found:
            return found
    except Exception:
        pass
    return ["0"]


def slots_per_gpu() -> int:
    return max(1, int(os.getenv("CF_HY3D_SLOTS_PER_GPU", "2")))


class GpuSlotPool:
    def __init__(self, devices: list[str], copies: int = 1) -> None:
        self.devices = devices
        self._slots: asyncio.Queue[str] = asyncio.Queue()
        for device in devices:
            for _ in range(max(1, copies)):
                self._slots.put_nowait(device)

    @classmethod
    def from_env(cls) -> "GpuSlotPool":
        return cls(list_cuda_devices(), slots_per_gpu())

    async def acquire(self) -> str:
        return await self._slots.get()

    def release(self, device: str) -> None:
        self._slots.put_nowait(device)


_POOL: GpuSlotPool | None = None


def gpu_pool() -> GpuSlotPool:
    global _POOL
    if _POOL is None:
        _POOL = GpuSlotPool.from_env()
    return _POOL
