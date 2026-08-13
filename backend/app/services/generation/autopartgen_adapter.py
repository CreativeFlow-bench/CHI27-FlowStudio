from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import urllib.parse
import urllib.error
import urllib.request
from uuid import uuid4

from app.models import AssetRecord, JobStatus, PartDiscoveryRequest, PartDiscoveryResponse, PartRecord
from app.services.generation.part_lifecycle import (
    annotate_obj_group_part,
    annotate_segmented_3d_part,
    lifecycle_summary,
    read_lifecycle,
)
from app.services.storage.studio_store import InMemoryStudioStore


class AutoPartGenAdapter:
    """Boundary for future AutoPartGen reproduction and worker integration."""

    def __init__(
        self,
        store: InMemoryStudioStore,
        remote_worker_url: str | None = None,
        segmentation_adapter: str = "sam3d",
        real_segmentation_default: bool = True,
        wait_timeout_sec: float = 120,
        poll_interval_sec: float = 2,
    ) -> None:
        self.store = store
        self.remote_worker_url = remote_worker_url.rstrip("/") if remote_worker_url else None
        self.segmentation_adapter = _segmentation_adapter_name(segmentation_adapter)
        self.real_segmentation_default = real_segmentation_default
        self.wait_timeout_sec = wait_timeout_sec
        self.poll_interval_sec = poll_interval_sec

    async def discover_parts(self, request: PartDiscoveryRequest) -> PartDiscoveryResponse:
        asset = self.store.get_asset(request.asset_id)
        if asset is None:
            raise ValueError(f"Asset not found: {request.asset_id}")

        remote_result = await self._submit_remote_segmentation(request, asset)
        parts = self._parts_from_remote_segmentation(remote_result)
        fallback_adapter = None
        previous_lifecycle = {
            part.part_id: read_lifecycle(part) for part in (asset.parts or [])
        }
        if not parts:
            parts = self._parts_from_obj_groups(asset, request)
            if parts:
                fallback_adapter = "obj_group_fallback"
        adapter_name = self.segmentation_adapter if parts else f"{self.segmentation_adapter}_unavailable"
        if fallback_adapter:
            adapter_name = fallback_adapter
            parts = [annotate_obj_group_part(part) for part in parts]
        elif parts:
            parts = [annotate_segmented_3d_part(part) for part in parts]
            for part in parts:
                part.metadata["replaced_lifecycles"] = previous_lifecycle
        if not parts:
            asset.metadata["part_discovery"] = {
                "mode": request.mode,
                "adapter": adapter_name,
                "prompt": request.prompt,
                "image_url": request.image_url,
                "mask_url": request.mask_url,
                "remote_result": remote_result,
                "error": (
                    f"{self.segmentation_adapter} returned no usable parts; "
                    "no mock semantic parts were created."
                ),
            }
            self.store.assets[asset.asset_id] = asset
            return PartDiscoveryResponse(
                job_id=f"partjob_{uuid4().hex[:10]}",
                session_id=request.session_id,
                asset_id=request.asset_id,
                status=JobStatus.failed,
                parts=[],
                metadata={
                    "adapter": adapter_name,
                    "future_worker": "SAM3D/SAMPart3D segmentation, AutoPartGen optional future prior",
                    "remote_result": remote_result,
                    "error": (
                        f"{self.segmentation_adapter} returned no usable parts; "
                        "no mock semantic parts were created."
                    ),
                },
            )
        asset.parts = parts
        summary = lifecycle_summary(parts)
        asset.metadata["part_discovery"] = {
            "mode": request.mode,
            "adapter": adapter_name,
            "prompt": request.prompt,
            "image_url": request.image_url,
            "mask_url": request.mask_url,
            "remote_result": remote_result,
            "lifecycle_summary": summary,
            "previous_part_lifecycles": previous_lifecycle,
        }
        if fallback_adapter:
            asset.metadata["part_discovery"]["fallback_reason"] = (
                f"{self.segmentation_adapter} returned no usable parts; "
                "used OBJ object/group records from the source mesh."
            )
        else:
            asset.metadata["part_discovery"]["upgrade"] = "segmented_3d"
        self.store.assets[asset.asset_id] = asset

        return PartDiscoveryResponse(
            job_id=f"partjob_{uuid4().hex[:10]}",
            session_id=request.session_id,
            asset_id=request.asset_id,
            status=JobStatus.completed,
            parts=parts,
            metadata={
                "adapter": adapter_name,
                "future_worker": "SAM3D/SAMPart3D segmentation, AutoPartGen optional future prior",
                "remote_result": remote_result,
                "fallback": fallback_adapter,
                "lifecycle_summary": summary,
            },
        )

    async def _submit_remote_segmentation(
        self, request: PartDiscoveryRequest, asset: AssetRecord
    ) -> dict | None:
        if not self.remote_worker_url:
            return None
        remote_mesh_path = await self._resolve_remote_mesh_path(asset)
        if not remote_mesh_path:
            return {
                "ok": False,
                "adapter": self.segmentation_adapter,
                "error": (
                    f"No server-readable mesh path is available for {self.segmentation_adapter}."
                ),
            }
        explicit_real = (
            request.metadata.get("segmentation_real")
            or request.metadata.get("sam3d_real")
            or request.metadata.get("partfield_real")
        )
        if explicit_real is None and _is_local_white_model(asset):
            return {
                "ok": False,
                "adapter": self.segmentation_adapter,
                "status": "skipped",
                "reason": (
                    "local white models use immediate OBJ group fallback by default; "
                    "pass metadata.segmentation_real=true to run SAM3D/SAMPart3D."
                ),
            }
        use_real = self.real_segmentation_default
        if explicit_real is not None:
            use_real = str(explicit_real).lower() in {"1", "true", "yes"}
        payload = {
            "flowstudio_job_id": f"partjob_{request.asset_id}",
            "mesh_path": remote_mesh_path,
            "granularity": _segmentation_granularity(request.metadata.get("granularity")),
            "max_parts": int(request.metadata.get("max_parts") or 16),
            "brush_mask_path": request.mask_url,
            "dry_run": not use_real,
        }
        endpoint = "/jobs/sam3d" if self.segmentation_adapter in {"sam3d", "sampart3d"} else "/jobs/partfield"
        result = await asyncio.to_thread(self._post_json, endpoint, payload)
        if result.get("status") == "completed" and result.get("result", {}).get("result_json"):
            return result
        if use_real and result.get("job_id"):
            return await self._wait_for_remote_job(str(result["job_id"]))
        return result

    async def _wait_for_remote_job(self, job_id: str) -> dict:
        deadline = asyncio.get_running_loop().time() + self.wait_timeout_sec
        latest: dict = {"job_id": job_id, "status": "queued"}
        while asyncio.get_running_loop().time() < deadline:
            latest = await asyncio.to_thread(self._get_json, f"/jobs/{job_id}")
            if latest.get("status") in {"completed", "failed", "cancelled"}:
                return latest
            await asyncio.sleep(self.poll_interval_sec)
        latest["ok"] = False
        latest["timeout"] = True
        latest["error"] = (
            f"Timed out waiting for {self.segmentation_adapter} job "
            f"after {self.wait_timeout_sec:.0f}s"
        )
        return latest

    async def _resolve_remote_mesh_path(self, asset: AssetRecord) -> str | None:
        remote_asset = asset.metadata.get("remote_asset")
        if isinstance(remote_asset, dict) and remote_asset.get("path"):
            return str(remote_asset["path"])
        storage_path = asset.metadata.get("storage_path")
        if storage_path and Path(str(storage_path)).exists():
            uploaded = await asyncio.to_thread(
                self._post_multipart_file_sync,
                "/assets/upload",
                str(storage_path),
                asset.asset_id,
                asset.session_id,
            )
            if uploaded.get("path"):
                asset.metadata["remote_asset"] = uploaded
                self.store.assets[asset.asset_id] = asset
                return str(uploaded["path"])
        if asset.mesh_url and os.path.isabs(asset.mesh_url):
            return asset.mesh_url
        return None

    def _post_json(self, path: str, payload: dict) -> dict:
        assert self.remote_worker_url is not None
        req = urllib.request.Request(
            f"{self.remote_worker_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            return {"ok": False, "error": str(exc)}

    def _get_json(self, path: str) -> dict:
        assert self.remote_worker_url is not None
        try:
            with urllib.request.urlopen(f"{self.remote_worker_url}{path}", timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": str(exc)}

    def _post_multipart_file_sync(
        self, path: str, file_path: str, asset_id: str, session_id: str
    ) -> dict:
        assert self.remote_worker_url is not None
        import mimetypes
        import uuid

        boundary = f"----FlowStudio{uuid.uuid4().hex}"
        file_name = Path(file_path).name
        mime = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
        fields = {
            "flowstudio_asset_id": asset_id,
            "session_id": session_id,
        }
        body = bytearray()
        for name, value in fields.items():
            body.extend(f"--{boundary}\r\n".encode())
            body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
            body.extend(str(value).encode())
            body.extend(b"\r\n")
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            (
                f'Content-Disposition: form-data; name="file"; filename="{file_name}"\r\n'
                f"Content-Type: {mime}\r\n\r\n"
            ).encode()
        )
        body.extend(Path(file_path).read_bytes())
        body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode())
        req = urllib.request.Request(
            f"{self.remote_worker_url}{path}",
            data=bytes(body),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            return {"ok": False, "error": str(exc)}

    def _parts_from_remote_segmentation(self, remote_result: dict | None) -> list[PartRecord]:
        if not isinstance(remote_result, dict):
            return []
        result_json = remote_result.get("result", {}).get("result_json")
        if not isinstance(result_json, dict):
            return []
        parts = []
        rows = [row for row in (result_json.get("parts") or []) if isinstance(row, dict)]
        rows.sort(key=lambda row: int(row.get("face_count") or 0), reverse=True)
        segmented_mesh_path = result_json.get("segmented_mesh_path")
        segmented_mesh_url = (
            f"/api/v1/remote-worker/artifact-file?path={urllib.parse.quote(str(segmented_mesh_path))}"
            if segmented_mesh_path
            else None
        )
        for index, row in enumerate(rows, start=1):
            source_part_id = str(row.get("part_id") or f"part_{index:02d}")
            part_id = f"seg_part_{index:02d}"
            bbox = row.get("bbox")
            metadata = {
                "source": self.segmentation_adapter,
                "lifecycle": "segmented_3d",
                "source_part_id": source_part_id,
                "face_count": row.get("face_count"),
                "bbox3d": bbox,
                "confidence": row.get("confidence"),
                "preview_path": row.get("preview_path"),
                "face_labels_path": result_json.get("face_labels_path"),
                "segmented_mesh_path": segmented_mesh_path,
                "segmented_mesh_url": segmented_mesh_url,
            }
            parts.append(
                annotate_segmented_3d_part(
                    PartRecord(
                        part_id=part_id,
                        label=f"discovered part {index:02d}",
                        type=self.segmentation_adapter,
                        lifecycle="segmented_3d",
                        metadata=metadata,
                    )
                )
            )
        return parts

    def _parts_from_obj_groups(
        self, asset: AssetRecord, request: PartDiscoveryRequest
    ) -> list[PartRecord]:
        storage_path = asset.metadata.get("storage_path")
        if not isinstance(storage_path, str) or not storage_path.lower().endswith(".obj"):
            return []
        path = Path(storage_path)
        if not path.exists():
            return []
        max_parts = max(1, min(int(request.metadata.get("max_parts") or 8), 32))
        face_counts: dict[str, int] = {}
        current = "default"
        try:
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith(("o ", "g ")):
                    current = line[2:].strip() or current
                    face_counts.setdefault(current, 0)
                elif line.startswith("f "):
                    face_counts[current] = face_counts.get(current, 0) + 1
        except OSError:
            return []
        rows = [
            (name, count)
            for name, count in face_counts.items()
            if count > 0 and name.lower() != "default"
        ]
        rows.sort(key=lambda item: item[1], reverse=True)
        parts: list[PartRecord] = []
        for index, (name, face_count) in enumerate(rows[:max_parts], start=1):
            parts.append(
                annotate_obj_group_part(
                    PartRecord(
                        part_id=f"obj_group_{index:02d}",
                        label=_clean_obj_group_label(name),
                        type="obj_group",
                        lifecycle="obj_group_fallback",
                        metadata={
                            "source": "obj_group_fallback",
                            "lifecycle": "obj_group_fallback",
                            "source_part_id": name,
                            "face_count": face_count,
                            "confidence": 0.62,
                            "segmentation_unavailable": True,
                        },
                    )
                )
            )
        return parts


def _clean_obj_group_label(value: str) -> str:
    label = value.replace("_", " ").strip()
    if len(label) > 48:
        label = label[:45].rstrip() + "..."
    return label or "OBJ group"


def _segmentation_granularity(value: object) -> str:
    normalized = str(value or "medium").strip().lower()
    aliases = {
        "coarse": "low",
        "rough": "low",
        "normal": "medium",
        "med": "medium",
        "fine": "high",
        "detailed": "high",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in {"low", "medium", "high"} else "medium"


def _segmentation_adapter_name(value: object) -> str:
    normalized = str(value or "sam3d").strip().lower().replace("_", "-")
    if normalized in {"sam3d", "sam-3d", "sampart3d", "sam-part-3d", "sam-part3d"}:
        return "sam3d"
    if normalized in {"partfield", "part-field"}:
        return "partfield"
    return "sam3d"


def _is_local_white_model(asset: AssetRecord) -> bool:
    benchmark_metadata = asset.metadata.get("benchmark_metadata")
    return bool(
        asset.metadata.get("white_model_category")
        or (
            isinstance(benchmark_metadata, dict)
            and benchmark_metadata.get("source") == "local_white_model"
        )
    )
