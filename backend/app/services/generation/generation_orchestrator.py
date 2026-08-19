from __future__ import annotations

import asyncio
import json
import math
import re
import struct
import urllib.parse
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from app.models import (
    AssetRecord,
    Candidate,
    CandidateDecision,
    CandidateFitRequest,
    GenerationMode,
    GenerationRequest,
    JobRecord,
    JobStage,
    JobStatus,
)
from app.services.storage.studio_store import InMemoryStudioStore
from app.services.storage.websocket_manager import WebSocketManager


class JobCancelled(Exception):
    pass


class ThreeDGenerationDisabled(ValueError):
    code = "3D_GENERATION_DISABLED"

    def __init__(self) -> None:
        super().__init__(
            "3D_GENERATION_DISABLED: 3D generation is disabled for this runtime"
        )


class RemoteCreativeFlowWorkerAdapter:
    """HTTP boundary for the future GPU FastAPI worker."""

    def __init__(
        self,
        base_url: str | None = None,
        real_jobs: bool = False,
        transfer_variant: str = "minimal",
    ) -> None:
        self.base_url = base_url.rstrip("/") if base_url else None
        self.real_jobs = real_jobs
        self.transfer_variant = transfer_variant

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url)

    async def submit_transfer(self, job: JobRecord, asset: AssetRecord | None = None) -> dict[str, Any]:
        if not self.base_url:
            return {"ok": False, "error": "Remote worker is not configured"}
        request_payload = job.request.model_dump(mode="json") if job.request else {}
        if asset is not None:
            request_payload["asset"] = asset.model_dump(mode="json")
            remote_asset = await self.sync_asset(asset)
            if remote_asset:
                request_payload["mesh_path"] = remote_asset["path"]
                request_payload["asset"]["remote_asset"] = remote_asset
        payload = {
            "flowstudio_job_id": job.job_id,
            "request": request_payload,
            "dry_run": not self.real_jobs,
            "transfer_variant": self.transfer_variant,
        }
        return await self._post_json("/jobs/transfer", payload)

    async def submit_staged_creativeflow(
        self,
        job: JobRecord,
        asset: AssetRecord | None = None,
    ) -> dict[str, Any]:
        if not self.base_url:
            return {"ok": False, "error": "Remote worker is not configured"}
        assert job.request is not None
        stage = self._infer_stage(job.request)
        request_payload = job.request.model_dump(mode="json")
        if asset is not None:
            request_payload["asset"] = asset.model_dump(mode="json")
            remote_asset = await self.sync_asset(asset)
            if remote_asset:
                request_payload["mesh_path"] = remote_asset["path"]
                request_payload["asset"]["remote_asset"] = remote_asset
        metadata = job.request.generation.metadata
        payload = {
            "flowstudio_job_id": job.job_id,
            "request": request_payload,
            "stage": stage,
            "fidelity": str(metadata.get("fidelity") or self._default_fidelity(stage)),
            "target_part": self._target_part_payload(job.request),
            "socket_constraints": self._socket_constraints(job.request),
            "divergence_axes": self._divergence_axes(job.request, stage),
            "candidate_count": job.request.generation.candidate_count,
            "source_image_path": metadata.get("source_image_path"),
            "source_mesh_path": metadata.get("source_mesh_path"),
            "source_multiview_paths": metadata.get("source_multiview_paths") or [],
            "source_elements_path": metadata.get("source_elements_path"),
            "brush_mask_path": metadata.get("brush_mask_path"),
            "sam3d_manifest_path": metadata.get("sam3d_manifest_path"),
            "part_semantics_path": metadata.get("part_semantics_path"),
            "sam3d_projection_mask_path": metadata.get("sam3d_projection_mask_path"),
            "kg_options": metadata.get("kg_options") or {},
            "image_options": metadata.get("image_options") or {},
            "mesh_options": metadata.get("mesh_options") or {},
            "analogy_prompt_package": metadata.get("analogy_prompt_package") or {},
            "run_hy3d": metadata.get("run_hy3d"),
            "dry_run": not self.real_jobs,
        }
        return await self._post_json(f"/jobs/{self._stage_endpoint(stage)}", payload)

    async def sync_asset(self, asset: AssetRecord) -> dict[str, Any] | None:
        if not self.base_url:
            return None
        remote_asset = asset.metadata.get("remote_asset")
        if isinstance(remote_asset, dict) and remote_asset.get("path"):
            return remote_asset
        storage_path = asset.metadata.get("storage_path")
        if not storage_path:
            return None
        file_path = str(storage_path)
        return await asyncio.to_thread(
            self._post_multipart_file_sync,
            "/assets/upload",
            {
                "flowstudio_asset_id": asset.asset_id,
                "session_id": asset.session_id,
            },
            "file",
            file_path,
        )

    async def upload_file(
        self,
        file_path: str,
        *,
        flowstudio_asset_id: str,
        session_id: str = "render",
    ) -> dict[str, Any] | None:
        if not self.base_url:
            return None
        return await asyncio.to_thread(
            self._post_multipart_file_sync,
            "/assets/upload",
            {
                "flowstudio_asset_id": flowstudio_asset_id,
                "session_id": session_id,
            },
            "file",
            file_path,
        )

    async def health(self) -> dict[str, Any]:
        if not self.base_url:
            return {"ok": False, "configured": False}
        return await asyncio.to_thread(self._get_json_sync, "/health")

    async def creativeflow_preflight(self) -> dict[str, Any]:
        if not self.base_url:
            return {"ok": False, "configured": False}
        return await asyncio.to_thread(self._get_json_sync, "/preflight/creativeflow", 12)

    async def get_job(self, remote_job_id: str) -> dict[str, Any]:
        if not self.base_url:
            return {"status": "failed", "error": "Remote worker is not configured"}
        return await asyncio.to_thread(self._get_json_sync, f"/jobs/{remote_job_id}")

    async def cancel_job(self, remote_job_id: str) -> dict[str, Any]:
        if not self.base_url:
            return {"status": "cancelled", "stage": "unconfigured", "job_id": remote_job_id}
        return await self._post_json(f"/jobs/{remote_job_id}/cancel", {})

    async def get_artifact_file(self, remote_path: str) -> tuple[bytes, str]:
        if not self.base_url:
            raise RuntimeError("Remote worker is not configured")
        return await asyncio.to_thread(self._get_artifact_file_sync, remote_path)

    def artifact_proxy_url(self, remote_path: str | None) -> str | None:
        if not remote_path:
            return None
        return f"/api/v1/remote-worker/artifact-file?path={urllib.parse.quote(remote_path)}"

    async def submit_hy3d(
        self,
        flowstudio_job_id: str,
        transfer_result_path: str,
        candidate_ids: list[str] | None = None,
        max_candidates: int = 1,
    ) -> dict[str, Any]:
        if not self.base_url:
            return {"ok": False, "error": "Remote worker is not configured"}
        payload = {
            "flowstudio_job_id": flowstudio_job_id,
            "transfer_result_path": transfer_result_path,
            "candidate_ids": candidate_ids or [],
            "max_candidates": max_candidates,
            "output_format": "glb",
        }
        return await self._post_json("/jobs/hy3d", payload)

    async def submit_hy3d_from_staged(
        self,
        flowstudio_job_id: str,
        staged_result_path: str,
        direction_ids: list[str] | None = None,
        max_candidates: int = 1,
    ) -> dict[str, Any]:
        if not self.base_url:
            return {"ok": False, "error": "Remote worker is not configured"}
        payload = {
            "flowstudio_job_id": flowstudio_job_id,
            "staged_result_path": staged_result_path,
            "direction_ids": direction_ids or [],
            "max_candidates": max_candidates,
            "output_format": "glb",
        }
        return await self._post_json("/jobs/hy3d-from-staged", payload)

    async def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(self._post_json_sync, path, payload)

    def _post_json_sync(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        assert self.base_url is not None
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                data = response.read().decode("utf-8")
                return json.loads(data) if data else {}
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Remote worker HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Remote worker unavailable: {exc}") from exc

    def _post_multipart_file_sync(
        self,
        path: str,
        fields: dict[str, str],
        file_field: str,
        file_path: str,
    ) -> dict[str, Any]:
        assert self.base_url is not None
        boundary = "----flowstudio-boundary"
        file_name = file_path.rsplit("/", 1)[-1]
        chunks: list[bytes] = []
        for key, value in fields.items():
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode(),
                    f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode(),
                    str(value).encode(),
                    b"\r\n",
                ]
            )
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                (
                    f'Content-Disposition: form-data; name="{file_field}"; '
                    f'filename="{file_name}"\r\n'
                ).encode(),
                b"Content-Type: application/octet-stream\r\n\r\n",
            ]
        )
        with open(file_path, "rb") as file:
            chunks.append(file.read())
        chunks.extend([b"\r\n", f"--{boundary}--\r\n".encode()])
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=b"".join(chunks),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read().decode("utf-8")
                return json.loads(data) if data else {}
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Remote asset upload HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Remote asset upload unavailable: {exc}") from exc

    def _get_json_sync(self, path: str, timeout: float = 5) -> dict[str, Any]:
        assert self.base_url is not None
        try:
            with urllib.request.urlopen(f"{self.base_url}{path}", timeout=timeout) as response:
                data = response.read().decode("utf-8")
                return json.loads(data) if data else {}
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Remote worker HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Remote worker unavailable: {exc}") from exc

    def _get_artifact_file_sync(self, remote_path: str) -> tuple[bytes, str]:
        assert self.base_url is not None
        query = urllib.parse.urlencode({"path": remote_path})
        try:
            with urllib.request.urlopen(f"{self.base_url}/artifact-file?{query}", timeout=30) as response:
                return response.read(), response.headers.get("content-type", "application/octet-stream")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Remote artifact HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Remote artifact unavailable: {exc}") from exc

    def _infer_stage(self, request: GenerationRequest) -> str:
        metadata = request.generation.metadata
        explicit = metadata.get("stage") or metadata.get("pipeline_stage")
        if explicit:
            return str(explicit)
        pipeline = str(metadata.get("pipeline") or "")
        if pipeline.startswith("creativeflow-"):
            return pipeline.removeprefix("creativeflow-")
        text = (request.intent.text or "").lower()
        if any(term in text for term in ["texture", "material", "color", "matte", "metallic"]):
            return "texture"
        if any(term in text for term in ["detail", "accessory", "facial", "button", "scarf", "hat"]):
            return "part"
        if request.selection.part_id or request.selection.type in {"part", "mask", "region"}:
            return "part"
        if request.intent.mode == GenerationMode.drag_regenerate:
            return "part"
        return "low_fidelity"

    def _stage_endpoint(self, stage: str) -> str:
        mapping = {
            "original": "creativeflow-original",
            "global": "creativeflow-low-fidelity",
            "silhouette": "creativeflow-low-fidelity",
            "low_fidelity": "creativeflow-low-fidelity",
            "rough_form": "creativeflow-part",
            "form": "creativeflow-part",
            "part": "creativeflow-part",
            "detail": "creativeflow-part",
            "texture": "creativeflow-texture",
        }
        return mapping.get(stage, "creativeflow-part")

    def _default_fidelity(self, stage: str) -> str:
        if stage in {"silhouette", "global", "low_fidelity"}:
            return "low"
        if stage == "texture":
            return "high"
        return "medium"

    def _target_part_payload(self, request: GenerationRequest) -> dict[str, Any]:
        if not request.selection.part_id:
            return {}
        metadata = request.selection.metadata
        partfield = self._partfield_metadata(request)
        return {
            "part_id": request.selection.part_id,
            "label": request.selection.label or request.selection.part_id,
            "selection_type": request.selection.type,
            "mask_url": request.selection.mask_url,
            "bbox": request.selection.bbox,
            "metadata": metadata,
            "partfield": partfield,
            "source_part_id": partfield.get("source_part_id"),
            "face_count": partfield.get("face_count"),
            "bbox3d": partfield.get("bbox3d"),
            "face_labels_path": partfield.get("face_labels_path"),
            "segmented_mesh_path": partfield.get("segmented_mesh_path"),
        }

    def _socket_constraints(self, request: GenerationRequest) -> dict[str, Any]:
        metadata = request.generation.metadata
        partfield = self._partfield_metadata(request)
        return {
            "preserve_boundary": metadata.get("fit_policy") == "preserve_socket"
            or bool(request.selection.part_id),
            "scale_policy": metadata.get("scale_policy") or "fit_to_original_socket",
            "bbox": request.selection.bbox,
            "bbox3d": partfield.get("bbox3d"),
            "face_labels_path": partfield.get("face_labels_path"),
            "segmented_mesh_path": partfield.get("segmented_mesh_path"),
            "source_part_id": partfield.get("source_part_id"),
            "face_count": partfield.get("face_count"),
            "constraints": request.intent.constraints,
        }

    def _partfield_metadata(self, request: GenerationRequest) -> dict[str, Any]:
        selection_metadata = request.selection.metadata
        partfield = selection_metadata.get("partfield")
        if isinstance(partfield, dict):
            return partfield
        target_metadata = request.generation.metadata.get("target_part_metadata")
        if isinstance(target_metadata, dict):
            return target_metadata
        return {}

    def _divergence_axes(self, request: GenerationRequest, stage: str) -> list[str]:
        metadata_axes = request.generation.metadata.get("divergence_axes")
        if isinstance(metadata_axes, list):
            return [str(axis) for axis in metadata_axes]
        defaults = {
            "original": ["relation", "semantic_motif", "composition", "character"],
            "silhouette": ["silhouette", "proportion", "stance", "mass_distribution"],
            "global": ["silhouette", "proportion", "stance", "mass_distribution"],
            "low_fidelity": ["silhouette", "proportion", "stance", "mass_distribution"],
            "rough_form": ["accessories", "facial_detail", "local_parts", "surface_depth"],
            "form": ["accessories", "facial_detail", "local_parts", "surface_depth"],
            "part": ["accessories", "facial_detail", "local_parts", "surface_depth"],
            "detail": ["accessories", "facial_detail", "local_parts", "surface_depth"],
            "texture": ["material", "color", "surface_pattern", "finish"],
        }
        return defaults.get(stage, defaults["part"])


class GenerationOrchestrator:
    def __init__(
        self,
        store: InMemoryStudioStore,
        websocket_manager: WebSocketManager,
        remote_adapter: RemoteCreativeFlowWorkerAdapter,
        auto_hy3d: bool = False,
        hy3d_max_candidates: int = 1,
        enable_3d_generation: bool = False,
    ) -> None:
        self.store = store
        self.websocket_manager = websocket_manager
        self.remote_adapter = remote_adapter
        self.enable_3d_generation = bool(enable_3d_generation)
        self.auto_hy3d = bool(auto_hy3d and self.enable_3d_generation)
        self.hy3d_max_candidates = max(1, hy3d_max_candidates)

    async def create_generation_job(self, request: GenerationRequest) -> JobRecord:
        request = self._enrich_request_with_asset_part_metadata(request)
        job = self.store.create_job(request, stage=JobStage.transfer)
        asyncio.create_task(self._run_generation(job.job_id))
        return job

    def _enrich_request_with_asset_part_metadata(self, request: GenerationRequest) -> GenerationRequest:
        if not request.selection.part_id:
            return request
        asset = self.store.get_asset(request.asset_id)
        if asset is None:
            return request
        target_part = next(
            (part for part in asset.parts if part.part_id == request.selection.part_id),
            None,
        )
        if target_part is None:
            return request

        enriched = request.model_copy(deep=True)
        if not enriched.selection.label:
            enriched.selection.label = target_part.label
        if enriched.selection.bbox is None and target_part.bbox is not None:
            enriched.selection.bbox = target_part.bbox

        part_dump = target_part.model_dump(mode="json")
        partfield = dict(target_part.metadata or {})
        selection_metadata = dict(enriched.selection.metadata or {})
        selection_metadata.setdefault("part_record", part_dump)
        selection_metadata.setdefault("partfield", partfield)
        enriched.selection.metadata = selection_metadata

        generation_metadata = dict(enriched.generation.metadata or {})
        generation_metadata.setdefault("target_part_record", part_dump)
        generation_metadata.setdefault("target_part_metadata", partfield)
        enriched.generation.metadata = generation_metadata
        return enriched

    async def generate_candidate_hy3d(self, candidate_id: str, session_id: str) -> Candidate:
        if not self.enable_3d_generation:
            raise ThreeDGenerationDisabled()
        candidate = self.store.get_candidate(candidate_id)
        if candidate is None:
            raise ValueError(f"Candidate not found: {candidate_id}")
        if candidate.session_id != session_id:
            raise ValueError("Candidate does not belong to the session")
        if candidate.mesh_url or candidate.obj_url:
            return candidate
        hy3d_status = str(candidate.metadata.get("hy3d_status") or "").strip().lower()
        if hy3d_status in {"queued", "running"}:
            raise ValueError("Hy3D already in progress for this candidate")
        if candidate.metadata.get("hy3d_generated_from_candidate") or hy3d_status == "completed":
            return candidate
        if candidate.metadata.get("hy3d_source") == "auto" and hy3d_status not in {"", "failed"}:
            return candidate
        staged_result_path = candidate.metadata.get("remote_result_path")
        direction_id = candidate.metadata.get("direction_id")
        if not isinstance(staged_result_path, str) or not staged_result_path:
            raise ValueError("Candidate is missing a remote staged CreativeFlow result path")
        if not isinstance(direction_id, str) or not direction_id:
            raise ValueError("Candidate is missing a staged CreativeFlow direction id")

        source_job = self.store.get_job(candidate.job_id)
        if source_job is None or source_job.request is None:
            raise ValueError("Candidate is missing its source generation job")
        candidate.metadata["hy3d_status"] = "queued"
        candidate.metadata["hy3d_source"] = "manual"
        self.store.save_candidate(candidate)
        job = self.store.create_job(source_job.request, stage=JobStage.mesh_generation)
        job.message = f"Hy3D queued for {candidate.label}"
        job.metadata["source_candidate_id"] = candidate.candidate_id
        self.store.save_job(job)
        candidate.metadata["hy3d_status"] = "running"
        candidate.metadata["hy3d_job_id"] = job.job_id
        self.store.save_candidate(candidate)
        await self._update_job(
            job,
            JobStatus.running,
            JobStage.mesh_generation,
            0.08,
            f"Submitting Hy3D for {candidate.label}",
        )
        try:
            hy3d_job = await self.remote_adapter.submit_hy3d_from_staged(
                job.job_id,
                staged_result_path,
                direction_ids=[direction_id],
                max_candidates=1,
            )
            job.metadata["remote_hy3d"] = hy3d_job
            self.store.save_job(job)
            remote_job_id = str(hy3d_job.get("job_id") or "")
            if not remote_job_id:
                raise RuntimeError("Remote Hy3D did not return a job id")
            hy3d_result = await self._wait_for_remote_hy3d(job, remote_job_id)
            self._attach_hy3d_outputs([candidate], hy3d_result)
            refreshed = self.store.get_candidate(candidate_id) or candidate
            refreshed.metadata["hy3d_generated_from_candidate"] = True
            refreshed.metadata["hy3d_job_id"] = job.job_id
            refreshed.metadata["remote_hy3d_job_id"] = remote_job_id
            refreshed.metadata["hy3d_status"] = "completed"
            refreshed.metadata["hy3d_source"] = "manual"
            self.store.save_candidate(refreshed)
            await self._update_job(
                job,
                JobStatus.completed,
                JobStage.completed,
                1.0,
                f"Hy3D completed for {candidate.label}",
            )
            await self.websocket_manager.broadcast(
                session_id,
                "candidate_ready",
                {"job_id": candidate.job_id, "candidate_ids": [candidate.candidate_id]},
            )
            return refreshed
        except Exception:
            failed = self.store.get_candidate(candidate_id) or candidate
            failed.metadata["hy3d_status"] = "failed"
            failed.metadata["hy3d_source"] = "manual"
            self.store.save_candidate(failed)
            raise

    async def fit_candidate_to_part(self, candidate_id: str, request: CandidateFitRequest) -> Candidate:
        candidate = self.store.get_candidate(candidate_id)
        if candidate is None:
            raise ValueError(f"Candidate not found: {candidate_id}")
        if candidate.session_id != request.session_id:
            raise ValueError("Candidate does not belong to the session")
        target_part = self._candidate_target_part(candidate, request.target_part_id)
        target_bbox = _coerce_bbox3d(target_part.metadata.get("bbox3d"))
        if target_bbox is None:
            raise ValueError("Target part is missing PartField bbox3d metadata")
        obj_data = await self._candidate_source_obj(candidate)
        source_bbox = _obj_bbox(obj_data)
        fit_result = _build_bbox_fit_result(
            source_bbox=source_bbox,
            target_bbox=target_bbox,
            policy=request.policy,
            target_part_id=target_part.part_id,
        )
        fitted_obj_text = _transform_obj(obj_data, fit_result["transform"])
        replacement_boundary_metrics = _open_boundary_metrics(fitted_obj_text)
        fitted_url = _write_fitted_obj(candidate.candidate_id, obj_data, fit_result["transform"])
        assembly_url, replacement_mode, replacement_metrics = await self._write_assembly_preview(
            candidate,
            target_part,
            obj_data,
            fit_result["transform"],
        )
        replacement_metrics = {
            **replacement_metrics,
            "replacement_boundary_edge_count": replacement_boundary_metrics["boundary_edge_count"],
            "replacement_boundary_centroid": replacement_boundary_metrics["boundary_centroid"],
            "boundary_match_score": _boundary_match_score(
                replacement_metrics["boundary_edge_count"],
                replacement_boundary_metrics["boundary_edge_count"],
            ),
        }
        seam_validation = _finalize_seam_validation(
            fit_result,
            replacement_mode=replacement_mode,
            replacement_metrics=replacement_metrics,
            has_assembly=bool(assembly_url),
        )
        socket_compatibility_score = _socket_compatibility_score(fit_result, seam_validation)
        seam_validation["socket_compatibility_score"] = socket_compatibility_score
        fit_result["quality"]["socket_compatibility_score"] = socket_compatibility_score
        fit_result["quality"]["seam_validation"] = seam_validation
        fit_result["status"] = seam_validation["status"]
        candidate.metadata["fit_result"] = fit_result
        candidate.metadata.setdefault("original_mesh_url_before_fit", candidate.mesh_url)
        candidate.metadata.setdefault("original_obj_url_before_fit", candidate.obj_url)
        candidate.metadata["fitted_obj_url"] = fitted_url
        candidate.metadata["fitted_preview_type"] = "transformed_obj"
        if assembly_url:
            candidate.metadata["assembly_preview_obj_url"] = assembly_url
            candidate.metadata["replacement_mode"] = replacement_mode
            candidate.metadata["old_part_removed"] = replacement_mode == "cluster_removed_assembly"
            candidate.metadata["removed_source_face_count"] = replacement_metrics["removed_source_face_count"]
            candidate.metadata["boundary_edge_count"] = replacement_metrics["boundary_edge_count"]
            candidate.metadata["replacement_boundary_edge_count"] = replacement_metrics[
                "replacement_boundary_edge_count"
            ]
            candidate.metadata["boundary_match_score"] = replacement_metrics["boundary_match_score"]
            candidate.metadata["boundary_position_score"] = seam_validation["boundary_position_score"]
            candidate.metadata["fitted_preview_type"] = "assembly_overlay_obj"
        candidate.mesh_url = None
        candidate.obj_url = assembly_url or fitted_url
        evidence = candidate.metadata.setdefault("pipeline_evidence", {})
        if isinstance(evidence, dict):
            evidence["fit_status"] = fit_result["status"]
            evidence["fit_policy"] = fit_result["policy"]
            evidence["fit_transform"] = fit_result["transform"]
            evidence["fit_target_part_id"] = target_part.part_id
            evidence["fit_source_bbox"] = source_bbox
            evidence["fit_target_bbox"] = target_bbox
            evidence["seam_validation"] = seam_validation
            evidence["fit_quality"] = fit_result["quality"]
            evidence["socket_compatibility_score"] = socket_compatibility_score
            evidence["fitted_obj_url"] = fitted_url
            if assembly_url:
                evidence["assembly_preview_obj_url"] = assembly_url
                evidence["replacement_mode"] = replacement_mode
                evidence["old_part_removed"] = replacement_mode == "cluster_removed_assembly"
                evidence["removed_source_face_count"] = replacement_metrics["removed_source_face_count"]
                evidence["boundary_edge_count"] = replacement_metrics["boundary_edge_count"]
                evidence["replacement_boundary_edge_count"] = replacement_metrics[
                    "replacement_boundary_edge_count"
                ]
                evidence["boundary_match_score"] = replacement_metrics["boundary_match_score"]
                evidence["boundary_position_score"] = seam_validation["boundary_position_score"]
        candidate.scores["fit_score"] = max(
            candidate.scores.get("fit_score", 0.0),
            fit_result["quality"]["bbox_extent_similarity"],
        )
        candidate.scores["socket_compatibility"] = socket_compatibility_score
        self.store.save_candidate(candidate)
        await self.websocket_manager.broadcast(
            candidate.session_id,
            "candidate_fit",
            {"candidate_id": candidate.candidate_id, "fit_result": fit_result},
        )
        return candidate

    async def _write_assembly_preview(
        self,
        candidate: Candidate,
        target_part: Any,
        replacement_obj: bytes,
        transform: dict[str, Any],
    ) -> tuple[str | None, str, dict[str, Any]]:
        empty_metrics = _replacement_metrics()
        asset = self.store.get_asset(candidate.source_asset_id)
        if asset is None:
            return None, "none", empty_metrics
        source_path = asset.metadata.get("storage_path")
        if not isinstance(source_path, str) or not source_path.lower().endswith(".obj"):
            return None, "none", empty_metrics
        path = Path(source_path)
        if not path.exists():
            return None, "none", empty_metrics
        source_obj = path.read_bytes()
        source_obj, metrics = await self._source_obj_without_target_cluster(source_obj, target_part)
        fitted_obj_text = _transform_obj(replacement_obj, transform)
        mode = "cluster_removed_assembly" if metrics["removed_source_face_count"] > 0 else "assembly_overlay"
        return _write_assembly_obj(candidate.candidate_id, source_obj, fitted_obj_text.encode("utf-8"), mode), mode, metrics

    async def _source_obj_without_target_cluster(
        self,
        source_obj: bytes,
        target_part: Any,
    ) -> tuple[bytes, dict[str, int]]:
        metadata = getattr(target_part, "metadata", {})
        if not isinstance(metadata, dict):
            return source_obj, _replacement_metrics()
        labels_path = metadata.get("face_labels_path")
        cluster_id = _cluster_id_from_part_metadata(metadata)
        if not isinstance(labels_path, str) or cluster_id is None:
            return source_obj, _replacement_metrics()
        try:
            labels_data, _content_type = await self.remote_adapter.get_artifact_file(labels_path)
            labels = _parse_npy_ints(labels_data)
        except Exception:
            return source_obj, _replacement_metrics()
        return _remove_obj_faces_by_label(source_obj, labels, cluster_id)

    async def _run_generation(self, job_id: str) -> None:
        job = self.store.get_job(job_id)
        if job is None or job.request is None:
            return

        try:
            self._abort_if_cancelled(job)
            await self._update_job(job, JobStatus.running, JobStage.transfer, 0.1, "Preparing request")
            asset = self.store.get_asset(job.request.asset_id)
            if self._should_use_staged_creativeflow(job.request):
                remote_result = await self.remote_adapter.submit_staged_creativeflow(job, asset)
                self._abort_if_cancelled(job)
                job.metadata["remote_staged_creativeflow"] = remote_result
                self.store.save_job(job)
                if self.remote_adapter.real_jobs and remote_result.get("job_id"):
                    await self._wait_for_remote_staged_creativeflow(job, str(remote_result["job_id"]))
                    return
                self._abort_if_cancelled(job)
                candidates = self._remote_staged_candidates(job, remote_result)
                for candidate in candidates:
                    self.store.save_candidate(candidate)
                job.candidate_ids = [candidate.candidate_id for candidate in candidates]
                await self._update_job(
                    job,
                    JobStatus.completed,
                    JobStage.completed,
                    1.0,
                    "Staged CreativeFlow directions completed",
                )
                await self.websocket_manager.broadcast(
                    job.session_id,
                    "candidate_ready",
                    {"job_id": job.job_id, "candidate_ids": job.candidate_ids},
                )
                return
            remote_result = await self.remote_adapter.submit_transfer(job, asset)
            self._abort_if_cancelled(job)
            job.metadata["remote_transfer"] = remote_result
            self.store.save_job(job)
            if self.remote_adapter.real_jobs and remote_result.get("job_id"):
                await self._wait_for_remote_transfer(job, str(remote_result["job_id"]))
                return
            await asyncio.sleep(0.05)
            self._abort_if_cancelled(job)

            await self._update_job(
                job, JobStatus.running, JobStage.relation_generation, 0.35, "Exploring relations"
            )
            await asyncio.sleep(0.05)
            self._abort_if_cancelled(job)

            await self._update_job(
                job, JobStatus.running, JobStage.image_generation, 0.65, "Generating candidates"
            )
            self._abort_if_cancelled(job)
            raise RuntimeError("Remote CreativeFlow did not return a real job or candidates.")
        except JobCancelled:
            return
        except Exception as exc:
            self.store.fail_job(job, "REMOTE_WORKER_FAILED", str(exc), retryable=True)
            await self.websocket_manager.broadcast(
                job.session_id,
                "error",
                {
                    "code": "REMOTE_WORKER_FAILED",
                    "message": str(exc),
                    "retryable": True,
                    "details": {"job_id": job.job_id},
                },
            )

    async def _wait_for_remote_transfer(self, job: JobRecord, remote_job_id: str) -> None:
        await self._update_job(
            job,
            JobStatus.running,
            JobStage.transfer,
            0.2,
            f"Remote transfer running: {remote_job_id}",
        )
        for _ in range(360):
            self._abort_if_cancelled(job)
            remote = await self.remote_adapter.get_job(remote_job_id)
            status = remote.get("status")
            progress = float(remote.get("progress") or job.progress)
            stage_text = str(remote.get("stage") or "transfer")
            job.metadata["remote_transfer"] = remote
            self.store.save_job(job)
            self._abort_if_cancelled(job)
            if status == "completed":
                candidates = self._remote_transfer_candidates(job, remote_job_id, remote)
                for candidate in candidates:
                    self.store.save_candidate(candidate)
                job.candidate_ids = [candidate.candidate_id for candidate in candidates]
                if self.auto_hy3d:
                    await self._run_optional_remote_hy3d(job, candidates, remote)
                await self._update_job(
                    job,
                    JobStatus.completed,
                    JobStage.completed,
                    1.0,
                    "Remote CreativeFlow transfer completed",
                )
                await self.websocket_manager.broadcast(
                    job.session_id,
                    "candidate_ready",
                    {"job_id": job.job_id, "candidate_ids": job.candidate_ids},
                )
                return
            if status in {"failed", "cancelled"}:
                raise RuntimeError(f"Remote transfer {status}: {remote.get('error')}")
            job.progress = min(0.95, max(0.2, progress))
            job.stage = JobStage.transfer
            job.message = f"Remote stage: {stage_text}"
            self.store.save_job(job)
            await self.websocket_manager.broadcast(
                job.session_id,
                "job_update",
                {
                    "job_id": job.job_id,
                    "status": job.status,
                    "stage": job.stage,
                    "progress": job.progress,
                    "message": job.message,
                },
            )
            await asyncio.sleep(5)
        raise TimeoutError(f"Remote transfer timed out: {remote_job_id}")

    async def _wait_for_remote_staged_creativeflow(self, job: JobRecord, remote_job_id: str) -> None:
        await self._update_job(
            job,
            JobStatus.running,
            JobStage.relation_generation,
            0.2,
            f"Remote staged CreativeFlow running: {remote_job_id}",
        )
        # Staged CreativeFlow includes a GPU model-phase switch plus Qwen-image
        # generation; give it a generous poll budget so a slow-but-successful
        # job is not discarded as timed out before images reach the frontend.
        for _ in range(900):
            self._abort_if_cancelled(job)
            remote = await self.remote_adapter.get_job(remote_job_id)
            status = remote.get("status")
            job.metadata["remote_staged_creativeflow"] = remote
            self.store.save_job(job)
            self._abort_if_cancelled(job)
            if status == "completed":
                candidates = self._remote_staged_candidates(job, remote)
                for candidate in candidates:
                    self.store.save_candidate(candidate)
                job.candidate_ids = [candidate.candidate_id for candidate in candidates]
                await self._update_job(
                    job,
                    JobStatus.completed,
                    JobStage.completed,
                    1.0,
                    "Remote staged CreativeFlow completed",
                )
                await self.websocket_manager.broadcast(
                    job.session_id,
                    "candidate_ready",
                    {"job_id": job.job_id, "candidate_ids": job.candidate_ids},
                )
                return
            if status in {"failed", "cancelled"}:
                raise RuntimeError(f"Remote staged CreativeFlow {status}: {remote.get('error')}")
            await asyncio.sleep(2)
        raise TimeoutError(f"Remote staged CreativeFlow timed out: {remote_job_id}")

    async def _run_optional_remote_hy3d(
        self,
        job: JobRecord,
        candidates: list[Candidate],
        transfer_remote: dict[str, Any],
    ) -> None:
        transfer_result_path = (
            transfer_remote.get("result", {}).get("result_path")
            if isinstance(transfer_remote.get("result"), dict)
            else None
        )
        if not transfer_result_path:
            job.metadata["remote_hy3d_error"] = "Missing remote transfer result_path"
            self.store.save_job(job)
            return

        await self._update_job(
            job,
            JobStatus.running,
            JobStage.mesh_generation,
            0.82,
            "Remote Hy3D mesh generation running",
        )
        for candidate in candidates[: self.hy3d_max_candidates]:
            candidate.metadata["hy3d_status"] = "running"
            candidate.metadata["hy3d_source"] = "auto"
            self.store.save_candidate(candidate)
        try:
            hy3d_job = await self.remote_adapter.submit_hy3d(
                job.job_id,
                str(transfer_result_path),
                max_candidates=min(self.hy3d_max_candidates, len(candidates) or 1),
            )
            job.metadata["remote_hy3d"] = hy3d_job
            self.store.save_job(job)
            remote_job_id = str(hy3d_job.get("job_id") or "")
            if not remote_job_id:
                return
            hy3d_result = await self._wait_for_remote_hy3d(job, remote_job_id)
            self._abort_if_cancelled(job)
            self._attach_hy3d_outputs(candidates, hy3d_result)
            for candidate in candidates[: self.hy3d_max_candidates]:
                refreshed = self.store.get_candidate(candidate.candidate_id) or candidate
                refreshed.metadata["hy3d_status"] = "completed"
                refreshed.metadata["hy3d_source"] = "auto"
                self.store.save_candidate(refreshed)
        except JobCancelled:
            return
        except Exception as exc:
            job.metadata["remote_hy3d_error"] = str(exc)
            self.store.save_job(job)
            for candidate in candidates[: self.hy3d_max_candidates]:
                failed = self.store.get_candidate(candidate.candidate_id) or candidate
                failed.metadata["hy3d_status"] = "failed"
                failed.metadata["hy3d_source"] = "auto"
                self.store.save_candidate(failed)

    async def _wait_for_remote_hy3d(self, job: JobRecord, remote_job_id: str) -> dict[str, Any]:
        for _ in range(360):  # 30 min at 5s; the old 10 min cap left GPU jobs orphaned
            self._abort_if_cancelled(job)
            remote = await self.remote_adapter.get_job(remote_job_id)
            status = remote.get("status")
            raw_progress = remote.get("progress")
            progress = float(raw_progress) if raw_progress is not None else 0.08
            remote_message = str(remote.get("message") or "").strip()
            job.metadata["remote_hy3d"] = remote
            job.stage = JobStage.mesh_generation
            job.progress = min(0.98, max(0.08, progress))
            job.message = remote_message or f"Hy3D {status or 'running'}"
            self.store.save_job(job)
            await self.websocket_manager.broadcast(
                job.session_id,
                "hy3d_progress",
                {
                    "message": job.message,
                    "progress": job.progress,
                    "stage": remote.get("stage") or job.stage,
                    "status": status,
                    "remote_job_id": remote_job_id,
                },
            )
            await self.websocket_manager.broadcast(
                job.session_id,
                "job_update",
                {
                    "job_id": job.job_id,
                    "status": job.status,
                    "stage": job.stage,
                    "progress": job.progress,
                    "message": job.message,
                },
            )
            if status == "completed":
                return remote
            if status in {"failed", "cancelled"}:
                raise RuntimeError(f"Remote Hy3D {status}: {remote.get('error')}")
            await asyncio.sleep(5)
        raise TimeoutError(f"Remote Hy3D timed out: {remote_job_id}")

    def _candidate_target_part(self, candidate: Candidate, requested_part_id: str | None = None):
        asset = self.store.get_asset(candidate.source_asset_id)
        if asset is None:
            raise ValueError("Candidate source asset was not found")
        target_part_id = requested_part_id or candidate.source_part_id
        if target_part_id:
            for part in asset.parts:
                if part.part_id == target_part_id:
                    return part
            raise ValueError(f"Target part not found: {target_part_id}")
        partfield = candidate.metadata.get("partfield")
        source_part_id = partfield.get("source_part_id") if isinstance(partfield, dict) else None
        for part in asset.parts:
            metadata = part.metadata
            if metadata.get("source_part_id") == source_part_id and metadata.get("bbox3d"):
                return part
        for part in asset.parts:
            if part.metadata.get("bbox3d"):
                return part
        raise ValueError("No PartField-backed target part is available")

    async def _candidate_source_obj(self, candidate: Candidate) -> bytes:
        remote_obj = candidate.metadata.get("remote_mesh_obj") or candidate.metadata.get("mesh_obj")
        if isinstance(remote_obj, str) and remote_obj:
            data, _content_type = await self.remote_adapter.get_artifact_file(remote_obj)
            return data
        if isinstance(candidate.obj_url, str) and "path=" in candidate.obj_url:
            query = urllib.parse.urlparse(candidate.obj_url).query
            remote_path = urllib.parse.parse_qs(query).get("path", [""])[0]
            if remote_path:
                data, _content_type = await self.remote_adapter.get_artifact_file(remote_path)
                return data
        if isinstance(candidate.obj_url, str) and candidate.obj_url.startswith("/files/"):
            file_path = _files_root() / candidate.obj_url.removeprefix("/files/")
            if file_path.exists():
                return file_path.read_bytes()
        raise ValueError("Candidate needs an OBJ output before fitting")

    def _attach_hy3d_outputs(self, candidates: list[Candidate], hy3d_remote: dict[str, Any]) -> None:
        result = hy3d_remote.get("result", {})
        result_json = result.get("result_json", {}) if isinstance(result, dict) else {}
        items = result_json.get("items", []) if isinstance(result_json, dict) else []
        by_rationale = {
            str(item.get("rationale_id")): item
            for item in items
            if isinstance(item, dict) and item.get("rationale_id")
        }
        for candidate in candidates:
            rationale_id = str(
                candidate.metadata.get("rationale_id")
                or candidate.metadata.get("direction_id")
                or ""
            )
            item = by_rationale.get(rationale_id)
            if not item:
                continue
            mesh_glb = item.get("mesh_glb")
            mesh_obj = item.get("mesh_obj")
            multiview_grid = item.get("multiview_grid")
            candidate.mesh_url = self.remote_adapter.artifact_proxy_url(
                str(mesh_glb) if mesh_glb else None
            )
            candidate.obj_url = self.remote_adapter.artifact_proxy_url(
                str(mesh_obj) if mesh_obj else None
            )
            candidate.metadata["remote_hy3d_item"] = item
            candidate.metadata["remote_mesh_glb"] = mesh_glb
            candidate.metadata["remote_mesh_obj"] = mesh_obj
            candidate.metadata["remote_mesh_url"] = candidate.mesh_url
            candidate.metadata["remote_obj_url"] = candidate.obj_url
            candidate.metadata["remote_multiview_grid"] = multiview_grid
            candidate.metadata["remote_multiview_grid_url"] = self.remote_adapter.artifact_proxy_url(
                str(multiview_grid) if multiview_grid else None
            )
            candidate.metadata["remote_oss_prefix"] = item.get("oss_prefix")
            evidence = candidate.metadata.setdefault("pipeline_evidence", {})
            if isinstance(evidence, dict):
                evidence["hy3d_mesh_glb"] = mesh_glb
                evidence["hy3d_mesh_obj"] = mesh_obj
                evidence["hy3d_mesh_url"] = candidate.mesh_url
                evidence["hy3d_obj_url"] = candidate.obj_url
            self.store.save_candidate(candidate)

    def _remote_transfer_candidates(
        self, job: JobRecord, remote_job_id: str, remote: dict[str, Any]
    ) -> list[Candidate]:
        assert job.request is not None
        remote_result = remote.get("result", {})
        result_json = remote_result.get("result_json") or {}
        generated_targets = result_json.get("generated_targets") or []
        retained = result_json.get("retained_rationales") or []
        seed_attributes = [
            item.get("label")
            for item in result_json.get("seed_attributes", [])
            if isinstance(item, dict) and item.get("label")
        ]

        candidates: list[Candidate] = []
        rows = generated_targets if generated_targets else retained
        if not rows:
            rows = [{"rationale_id": "remote_01"}]
        for index, row in enumerate(rows[: job.request.generation.candidate_count]):
            if not isinstance(row, dict):
                continue
            rationale_id = str(row.get("rationale_id") or f"remote_{index + 1:02d}")
            rationale = next(
                (
                    item
                    for item in retained
                    if isinstance(item, dict) and item.get("rationale_id") == rationale_id
                ),
                {},
            )
            family = rationale.get("family_prior") if isinstance(rationale, dict) else {}
            family_label = family.get("label") if isinstance(family, dict) else None
            label = family_label or rationale_id.replace("_", " ").title()
            execution_prompt = row.get("execution_prompt") if isinstance(row, dict) else None
            image_path = row.get("image") or row.get("canonical_image") or row.get("creative_image")
            image_url = self.remote_adapter.artifact_proxy_url(image_path)
            candidates.append(
                Candidate(
                    candidate_id=f"cand_{job.job_id.removeprefix('job_')}_remote_{index + 1:02d}",
                    job_id=job.job_id,
                    session_id=job.session_id,
                    source_asset_id=job.request.asset_id,
                    source_part_id=job.request.selection.part_id,
                    label=f"Remote transfer: {label}",
                    thumbnail_url=image_url,
                    mesh_url=None,
                    obj_url=None,
                    scores={
                        "novelty": round(0.72 + index * 0.02, 3),
                        "intent_alignment": round(0.82 - index * 0.015, 3),
                        "identity_preservation": 0.74,
                    },
                    metadata={
                        "adapter": "remote-creativeflow-worker",
                        "remote_job_id": remote_job_id,
                        "remote_result_path": remote_result.get("result_path"),
                        "remote_image_path": image_path,
                        "remote_image_url": image_url,
                        "rationale_id": rationale_id,
                        "family_prior": family,
                        "seed_attributes": seed_attributes,
                        "execution_prompt": execution_prompt,
                        "remote_target": row,
                        "pipeline_evidence": {
                            "adapter": "remote-creativeflow-worker",
                            "remote_job_id": remote_job_id,
                            "result_path": remote_result.get("result_path"),
                            "rationale_id": rationale_id,
                            "has_preview_image": bool(image_path),
                            "seed_attribute_count": len(seed_attributes),
                        },
                    },
                )
            )
        return candidates

    def _remote_staged_candidates(self, job: JobRecord, remote: dict[str, Any]) -> list[Candidate]:
        assert job.request is not None
        result = remote.get("result", {}) if isinstance(remote, dict) else {}
        result_json = result.get("result_json", {}) if isinstance(result, dict) else {}
        directions = result_json.get("directions") or result_json.get("part_directions") or []
        generated_previews = {
            str(item.get("direction_id")): item
            for item in (result_json.get("generated_previews") or [])
            if isinstance(item, dict) and item.get("direction_id")
        }
        stage = str(result_json.get("stage") or self.remote_adapter._infer_stage(job.request))
        fidelity = str(result_json.get("fidelity") or job.request.generation.metadata.get("fidelity") or "")
        remote_stage = str(remote.get("stage") or "")
        analogy_prompt_package = job.request.generation.metadata.get("analogy_prompt_package")
        if not isinstance(analogy_prompt_package, dict):
            analogy_prompt_package = {}
        candidates: list[Candidate] = []
        for index, direction in enumerate(directions[: job.request.generation.candidate_count]):
            if not isinstance(direction, dict):
                continue
            risk = direction.get("risk") if isinstance(direction.get("risk"), dict) else {}
            fit_risk = str(risk.get("fit") or "medium")
            identity_risk = str(risk.get("identity") or "medium")
            preview = generated_previews.get(str(direction.get("direction_id") or ""))
            image_path = direction.get("preview_image_path") or (
                preview.get("image") if isinstance(preview, dict) else None
            )
            image_url = self.remote_adapter.artifact_proxy_url(
                str(image_path) if image_path else None
            )
            mesh_glb = direction.get("mesh_glb")
            mesh_obj = direction.get("mesh_obj")
            mesh_url = self.remote_adapter.artifact_proxy_url(str(mesh_glb) if mesh_glb else None)
            obj_url = self.remote_adapter.artifact_proxy_url(str(mesh_obj) if mesh_obj else None)
            provenance = (
                "real_worker_output"
                if mesh_glb or mesh_obj or remote_stage not in {"dry_run", "mock"}
                else "dry_run_contract"
            )
            target_part = result_json.get("target_part") if isinstance(result_json, dict) else {}
            socket_constraints = (
                result_json.get("socket_constraints") if isinstance(result_json, dict) else {}
            )
            candidates.append(
                Candidate(
                    candidate_id=f"cand_{job.job_id.removeprefix('job_')}_stage_{index + 1:02d}",
                    job_id=job.job_id,
                    session_id=job.session_id,
                    source_asset_id=job.request.asset_id,
                    source_part_id=job.request.selection.part_id,
                    label=str(direction.get("label") or f"{stage} direction {index + 1}"),
                    decision=CandidateDecision.pending,
                    thumbnail_url=image_url,
                    mesh_url=mesh_url,
                    obj_url=obj_url,
                    scores={
                        "novelty": round(0.78 + index * 0.015, 3),
                        "intent_alignment": round(0.84 - index * 0.01, 3),
                        "identity_preservation": 0.58 if identity_risk == "high" else 0.78,
                        "fit_score": 0.0 if fit_risk == "not_applicable" else 0.68,
                    },
                    solution_space={
                        "cluster": f"creativeflow_{stage}",
                        "stage": stage,
                        "fidelity": fidelity,
                    },
                    metadata={
                        "adapter": "remote-staged-creativeflow",
                        "remote_job_id": remote.get("job_id"),
                        "remote_result_path": result.get("result_path"),
                        "analogy_expansion_mode": result_json.get("analogy_expansion_mode"),
                        "prompt_source": result_json.get("prompt_source"),
                        "knowledge_graph_policy": result_json.get("knowledge_graph_policy"),
                        "stage": stage,
                        "fidelity": fidelity,
                        "direction_id": direction.get("direction_id"),
                        "execution_prompt": direction.get("execution_prompt"),
                        "analogy_prompt_package": analogy_prompt_package,
                        "selected_prompt_tokens": analogy_prompt_package.get("selected_prompt_tokens", []),
                        "prompt_token_mode": analogy_prompt_package.get("prompt_token_mode"),
                        "remote_image_path": direction.get("preview_image_path"),
                        "remote_image_url": image_url,
                        "remote_mesh_glb": mesh_glb,
                        "remote_mesh_obj": mesh_obj,
                        "remote_mesh_url": mesh_url,
                        "remote_obj_url": obj_url,
                        "remote_multiview_grid": direction.get("multiview_grid"),
                        "remote_oss_prefix": direction.get("oss_prefix"),
                        "fit_contract": direction.get("fit_contract"),
                        "fidelity_profile": direction.get("fidelity_profile"),
                        "risk": risk,
                        "target_part": target_part,
                        "socket_constraints": socket_constraints,
                        "pipeline_evidence": {
                            "adapter": "remote-staged-creativeflow",
                            "provenance": provenance,
                            "remote_stage": remote_stage or None,
                            "remote_job_id": remote.get("job_id"),
                            "result_path": result.get("result_path"),
                            "analogy_expansion_mode": result_json.get("analogy_expansion_mode"),
                            "prompt_source": result_json.get("prompt_source"),
                            "knowledge_graph_policy": result_json.get("knowledge_graph_policy"),
                            "stage": stage,
                            "fidelity": fidelity,
                            "direction_id": direction.get("direction_id"),
                            "analogy_direction_ids": analogy_prompt_package.get("direction_ids", []),
                            "selected_prompt_tokens": analogy_prompt_package.get("selected_prompt_tokens", []),
                            "prompt_token_mode": analogy_prompt_package.get("prompt_token_mode"),
                            "has_preview_image": bool(image_path),
                            "remote_image_path": image_path,
                            "remote_image_url": image_url,
                            "has_mesh_glb": bool(mesh_glb),
                            "has_mesh_obj": bool(mesh_obj),
                            "target_part_id": (
                                target_part.get("part_id") if isinstance(target_part, dict) else None
                            ),
                            "source_part_id": (
                                target_part.get("source_part_id") if isinstance(target_part, dict) else None
                            ),
                            "socket_face_count": (
                                socket_constraints.get("face_count")
                                if isinstance(socket_constraints, dict)
                                else None
                            ),
                            "fit_policy": (
                                socket_constraints.get("scale_policy")
                                if isinstance(socket_constraints, dict)
                                else None
                            ),
                        },
                        "remote_direction": direction,
                        "remote_generated_preview": preview,
                    },
                )
            )
        if not candidates:
            raise RuntimeError("Remote staged CreativeFlow returned no candidate directions.")
        return candidates

    def _should_use_staged_creativeflow(self, request: GenerationRequest) -> bool:
        metadata = request.generation.metadata
        pipeline = str(metadata.get("pipeline") or "")
        return bool(
            metadata.get("stage")
            or metadata.get("fidelity")
            or pipeline.startswith("creativeflow")
        )

    async def _update_job(
        self,
        job: JobRecord,
        status: JobStatus,
        stage: JobStage,
        progress: float,
        message: str,
    ) -> None:
        self._abort_if_cancelled(job)
        job.status = status
        job.stage = stage
        job.progress = progress
        job.message = message
        self.store.save_job(job)
        await self.websocket_manager.broadcast(
            job.session_id,
            "job_update",
            {
                "job_id": job.job_id,
                "status": job.status,
                "stage": job.stage,
                "progress": job.progress,
                "message": job.message,
            },
        )

    def _abort_if_cancelled(self, job: JobRecord) -> None:
        current = self.store.get_job(job.job_id)
        if current and current.status == JobStatus.cancelled:
            job.status = JobStatus.cancelled
            job.message = current.message or "Job cancelled"
            raise JobCancelled()

def _coerce_bbox3d(value: Any) -> dict[str, list[float]] | None:
    if isinstance(value, dict):
        mins = value.get("min") or value.get("mins")
        maxs = value.get("max") or value.get("maxs")
        if isinstance(mins, list) and isinstance(maxs, list) and len(mins) == 3 and len(maxs) == 3:
            try:
                return {
                    "min": [float(item) for item in mins],
                    "max": [float(item) for item in maxs],
                }
            except (TypeError, ValueError):
                return None
    if isinstance(value, list) and len(value) == 6:
        try:
            nums = [float(item) for item in value]
        except (TypeError, ValueError):
            return None
        return {"min": nums[:3], "max": nums[3:]}
    return None


def _obj_bbox(data: bytes) -> dict[str, list[float]]:
    mins = [math.inf, math.inf, math.inf]
    maxs = [-math.inf, -math.inf, -math.inf]
    vertices = 0
    for raw_line in data.decode("utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line.startswith("v "):
            continue
        fields = line.split()
        if len(fields) < 4:
            continue
        try:
            coords = [float(fields[1]), float(fields[2]), float(fields[3])]
        except ValueError:
            continue
        vertices += 1
        for axis, value in enumerate(coords):
            mins[axis] = min(mins[axis], value)
            maxs[axis] = max(maxs[axis], value)
    if vertices == 0:
        raise ValueError("Candidate OBJ contains no vertices")
    return {"min": mins, "max": maxs}


def _write_fitted_obj(candidate_id: str, data: bytes, transform: dict[str, Any]) -> str:
    fitted_dir = _files_root() / "fitted" / candidate_id
    fitted_dir.mkdir(parents=True, exist_ok=True)
    target = fitted_dir / "fitted.obj"
    target.write_text(_transform_obj(data, transform), encoding="utf-8")
    return f"/files/fitted/{candidate_id}/fitted.obj"


def _write_assembly_obj(candidate_id: str, source_obj: bytes, fitted_obj: bytes, mode: str) -> str:
    fitted_dir = _files_root() / "fitted" / candidate_id
    fitted_dir.mkdir(parents=True, exist_ok=True)
    target = fitted_dir / "assembly_preview.obj"
    source_text = source_obj.decode("utf-8", errors="ignore")
    fitted_text = fitted_obj.decode("utf-8", errors="ignore")
    vertex_offset = _obj_vertex_count(source_text)
    removal_note = (
        "# Target PartField cluster faces were removed before inserting the fitted part."
        if mode == "cluster_removed_assembly"
        else "# The original PartField cluster has not been removed."
    )
    target.write_text(
        "\n".join(
            [
                "# FlowStudio assembly preview: original OBJ plus fitted replacement part.",
                removal_note,
                source_text.rstrip(),
                "o flowstudio_fitted_replacement",
                _offset_obj_faces(fitted_text, vertex_offset).rstrip(),
                "",
            ]
        ),
        encoding="utf-8",
    )
    return f"/files/fitted/{candidate_id}/assembly_preview.obj"


def _cluster_id_from_part_metadata(metadata: dict[str, Any]) -> int | None:
    raw = metadata.get("source_part_id") or metadata.get("raw_cluster_id") or metadata.get("cluster_id")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        match = re.search(r"(-?\d+)$", raw)
        if match:
            return int(match.group(1))
    return None


def _parse_npy_ints(data: bytes) -> list[int]:
    if not data.startswith(b"\x93NUMPY"):
        raise ValueError("Not a numpy .npy file")
    major = data[6]
    if major == 1:
        header_len = struct.unpack("<H", data[8:10])[0]
        header_start = 10
    elif major in {2, 3}:
        header_len = struct.unpack("<I", data[8:12])[0]
        header_start = 12
    else:
        raise ValueError(f"Unsupported .npy version: {major}")
    header = data[header_start : header_start + header_len].decode("latin1")
    descr_match = re.search(r"'descr': '([^']+)'", header)
    shape_match = re.search(r"'shape': \(([^)]*)\)", header)
    fortran_match = re.search(r"'fortran_order': (False|True)", header)
    if not descr_match or not shape_match or not fortran_match:
        raise ValueError("Unsupported .npy header")
    if fortran_match.group(1) != "False":
        raise ValueError("Fortran-order .npy labels are not supported")
    descr = descr_match.group(1)
    dtype_map = {
        "<i1": ("b", 1),
        "|i1": ("b", 1),
        "<u1": ("B", 1),
        "|u1": ("B", 1),
        "<i2": ("h", 2),
        "<u2": ("H", 2),
        "<i4": ("i", 4),
        "<u4": ("I", 4),
        "<i8": ("q", 8),
        "<u8": ("Q", 8),
    }
    if descr not in dtype_map:
        raise ValueError(f"Unsupported .npy dtype: {descr}")
    fmt, item_size = dtype_map[descr]
    dims = [int(item.strip()) for item in shape_match.group(1).split(",") if item.strip()]
    count = math.prod(dims) if dims else 1
    payload = data[header_start + header_len :]
    if len(payload) < count * item_size:
        raise ValueError("Truncated .npy payload")
    return [
        int(struct.unpack_from(f"<{fmt}", payload, offset)[0])
        for offset in range(0, count * item_size, item_size)
    ]


def _replacement_metrics(
    removed_source_face_count: int = 0,
    boundary_edge_count: int = 0,
    labeled_face_count: int = 0,
    boundary_centroid: list[float] | None = None,
) -> dict[str, Any]:
    return {
        "removed_source_face_count": removed_source_face_count,
        "boundary_edge_count": boundary_edge_count,
        "labeled_face_count": labeled_face_count,
        "source_boundary_centroid": boundary_centroid,
    }


def _remove_obj_faces_by_label(source_obj: bytes, labels: list[int], cluster_id: int) -> tuple[bytes, dict[str, Any]]:
    output: list[str] = []
    face_index = 0
    removed = 0
    text = source_obj.decode("utf-8", errors="ignore")
    boundary_metrics = _boundary_metrics_for_cluster(text, labels, cluster_id)
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("f "):
            label = labels[face_index] if face_index < len(labels) else None
            face_index += 1
            if label == cluster_id:
                removed += 1
                continue
        output.append(raw_line)
    return (
        ("\n".join(output) + "\n").encode("utf-8"),
        _replacement_metrics(
            removed_source_face_count=removed,
            boundary_edge_count=boundary_metrics["boundary_edge_count"],
            labeled_face_count=min(len(labels), face_index),
            boundary_centroid=boundary_metrics["boundary_centroid"],
        ),
    )


def _boundary_metrics_for_cluster(text: str, labels: list[int], cluster_id: int) -> dict[str, Any]:
    vertices_by_index = _obj_vertices_by_index(text)
    edge_labels: dict[tuple[int, int], set[int]] = {}
    face_index = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("f "):
            continue
        label = labels[face_index] if face_index < len(labels) else None
        face_index += 1
        vertices = _face_vertex_indices(line)
        if label is None or len(vertices) < 2:
            continue
        for index, start in enumerate(vertices):
            end = vertices[(index + 1) % len(vertices)]
            if start == end:
                continue
            edge = tuple(sorted((start, end)))
            edge_labels.setdefault(edge, set()).add(label)
    boundary_edges = [
        edge
        for edge, labels_for_edge in edge_labels.items()
        if cluster_id in labels_for_edge and any(label != cluster_id for label in labels_for_edge)
    ]
    return {
        "boundary_edge_count": len(boundary_edges),
        "boundary_centroid": _edge_vertex_centroid(boundary_edges, vertices_by_index),
    }


def _open_boundary_metrics(text: str) -> dict[str, Any]:
    vertices_by_index = _obj_vertices_by_index(text)
    edge_counts: dict[tuple[int, int], int] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("f "):
            continue
        vertices = _face_vertex_indices(line)
        if len(vertices) < 2:
            continue
        for index, start in enumerate(vertices):
            end = vertices[(index + 1) % len(vertices)]
            if start == end:
                continue
            edge = tuple(sorted((start, end)))
            edge_counts[edge] = edge_counts.get(edge, 0) + 1
    boundary_edges = [edge for edge, count in edge_counts.items() if count == 1]
    return {
        "boundary_edge_count": len(boundary_edges),
        "boundary_centroid": _edge_vertex_centroid(boundary_edges, vertices_by_index),
    }


def _obj_vertices_by_index(text: str) -> dict[int, list[float]]:
    vertices: dict[int, list[float]] = {}
    index = 1
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("v "):
            continue
        fields = line.split()
        if len(fields) < 4:
            continue
        try:
            vertices[index] = [float(fields[1]), float(fields[2]), float(fields[3])]
        except ValueError:
            pass
        index += 1
    return vertices


def _edge_vertex_centroid(
    edges: list[tuple[int, int]],
    vertices_by_index: dict[int, list[float]],
) -> list[float] | None:
    vertex_ids = sorted({vertex for edge in edges for vertex in edge})
    points = [vertices_by_index[vertex] for vertex in vertex_ids if vertex in vertices_by_index]
    if not points:
        return None
    return [
        round(sum(point[axis] for point in points) / len(points), 6)
        for axis in range(3)
    ]


def _boundary_match_score(source_boundary_edges: int, replacement_boundary_edges: int) -> float:
    if source_boundary_edges <= 0 or replacement_boundary_edges <= 0:
        return 0.0
    return round(
        min(source_boundary_edges, replacement_boundary_edges)
        / max(source_boundary_edges, replacement_boundary_edges),
        4,
    )


def _face_vertex_indices(face_line: str) -> list[int]:
    vertices = []
    for token in face_line.split()[1:]:
        head = token.split("/")[0]
        try:
            value = int(head)
        except ValueError:
            continue
        if value > 0:
            vertices.append(value)
    return vertices


def _obj_vertex_count(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.strip().startswith("v "))


def _offset_obj_faces(text: str, vertex_offset: int) -> str:
    output: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("f "):
            output.append(raw_line)
            continue
        tokens = line.split()
        output.append(" ".join([tokens[0], *[_offset_face_token(token, vertex_offset) for token in tokens[1:]]]))
    return "\n".join(output) + "\n"


def _offset_face_token(token: str, vertex_offset: int) -> str:
    parts = token.split("/")
    if not parts or not parts[0]:
        return token
    try:
        vertex_index = int(parts[0])
    except ValueError:
        return token
    if vertex_index > 0:
        parts[0] = str(vertex_index + vertex_offset)
    return "/".join(parts)


def _transform_obj(data: bytes, transform: dict[str, Any]) -> str:
    scale = transform.get("scale", 1.0)
    translation = transform.get("translation", [0.0, 0.0, 0.0])
    if not isinstance(translation, list) or len(translation) != 3:
        raise ValueError("Fit transform translation must be a 3D vector")
    output: list[str] = []
    for raw_line in data.decode("utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line.startswith("v "):
            output.append(raw_line)
            continue
        fields = line.split()
        if len(fields) < 4:
            output.append(raw_line)
            continue
        try:
            coords = [float(fields[1]), float(fields[2]), float(fields[3])]
        except ValueError:
            output.append(raw_line)
            continue
        if isinstance(scale, list):
            scaled = [coords[i] * float(scale[i]) for i in range(3)]
        else:
            scaled = [coords[i] * float(scale) for i in range(3)]
        moved = [scaled[i] + float(translation[i]) for i in range(3)]
        suffix = " ".join(fields[4:])
        vertex = f"v {_format_obj_float(moved[0])} {_format_obj_float(moved[1])} {_format_obj_float(moved[2])}"
        output.append(f"{vertex} {suffix}".rstrip())
    return "\n".join(output) + "\n"


def _format_obj_float(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _files_root() -> Path:
    root = Path(__file__).resolve().parents[3] / "storage" / "files"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _build_bbox_fit_result(
    source_bbox: dict[str, list[float]],
    target_bbox: dict[str, list[float]],
    policy: str,
    target_part_id: str,
) -> dict[str, Any]:
    source_min = source_bbox["min"]
    source_max = source_bbox["max"]
    target_min = target_bbox["min"]
    target_max = target_bbox["max"]
    source_extent = [max(1e-6, source_max[i] - source_min[i]) for i in range(3)]
    target_extent = [max(1e-6, target_max[i] - target_min[i]) for i in range(3)]
    if policy == "bbox_axis_aligned":
        scale: float | list[float] = [target_extent[i] / source_extent[i] for i in range(3)]
        scaled_source_extent = target_extent
    else:
        uniform = min(target_extent[i] / source_extent[i] for i in range(3))
        scale = uniform
        scaled_source_extent = [source_extent[i] * uniform for i in range(3)]
    source_center = [(source_min[i] + source_max[i]) / 2 for i in range(3)]
    target_center = [(target_min[i] + target_max[i]) / 2 for i in range(3)]
    if isinstance(scale, list):
        scaled_source_center = [source_center[i] * scale[i] for i in range(3)]
    else:
        scaled_source_center = [source_center[i] * scale for i in range(3)]
    translation = [target_center[i] - scaled_source_center[i] for i in range(3)]
    extent_similarity = _extent_similarity(scaled_source_extent, target_extent)
    bbox_validation = _bbox_fit_validation(
        scaled_source_extent=scaled_source_extent,
        target_extent=target_extent,
        target_center=target_center,
        fitted_center=target_center,
        extent_similarity=extent_similarity,
    )
    return {
        "status": "transform_ready",
        "policy": policy,
        "target_part_id": target_part_id,
        "source_bbox": source_bbox,
        "target_bbox": target_bbox,
        "source_extent": source_extent,
        "target_extent": target_extent,
        "transform": {
            "scale": scale,
            "translation": translation,
            "rotation": [0.0, 0.0, 0.0],
            "source_center": source_center,
            "target_center": target_center,
        },
        "quality": {
            "bbox_extent_similarity": round(extent_similarity, 4),
            "center_alignment_error": bbox_validation["center_alignment_error"],
            "center_alignment_error_normalized": bbox_validation["center_alignment_error_normalized"],
            "volume_ratio": bbox_validation["volume_ratio"],
            "bbox_validation": bbox_validation,
            "seam_validation": {"status": "not_run"},
        },
        "next_step": "apply_transform_then_run_boundary_or_boolean_validation",
    }


def _bbox_fit_validation(
    scaled_source_extent: list[float],
    target_extent: list[float],
    target_center: list[float],
    fitted_center: list[float],
    extent_similarity: float,
) -> dict[str, Any]:
    center_error = math.dist(fitted_center, target_center)
    target_diagonal = max(math.dist([0.0, 0.0, 0.0], target_extent), 1e-6)
    source_volume = math.prod(max(value, 1e-6) for value in scaled_source_extent)
    target_volume = math.prod(max(value, 1e-6) for value in target_extent)
    volume_ratio = min(source_volume, target_volume) / max(source_volume, target_volume)
    normalized_error = center_error / target_diagonal
    status = "pass" if normalized_error <= 0.08 and extent_similarity >= 0.65 else "review"
    return {
        "status": status,
        "center_alignment_error": round(center_error, 6),
        "center_alignment_error_normalized": round(normalized_error, 6),
        "extent_similarity": round(extent_similarity, 4),
        "volume_ratio": round(volume_ratio, 4),
    }


def _finalize_seam_validation(
    fit_result: dict[str, Any],
    replacement_mode: str,
    replacement_metrics: dict[str, Any],
    has_assembly: bool,
) -> dict[str, Any]:
    bbox_validation = fit_result.get("quality", {}).get("bbox_validation", {})
    bbox_status = bbox_validation.get("status")
    removed_faces = replacement_metrics.get("removed_source_face_count", 0)
    boundary_edge_count = replacement_metrics.get("boundary_edge_count", 0)
    labeled_face_count = replacement_metrics.get("labeled_face_count", 0)
    replacement_boundary_edge_count = replacement_metrics.get("replacement_boundary_edge_count", 0)
    boundary_match_score = replacement_metrics.get("boundary_match_score", 0.0)
    source_boundary_centroid = replacement_metrics.get("source_boundary_centroid")
    replacement_boundary_centroid = replacement_metrics.get("replacement_boundary_centroid")
    centroid_metrics = _boundary_centroid_metrics(
        source_boundary_centroid,
        replacement_boundary_centroid,
        fit_result.get("target_extent", [1.0, 1.0, 1.0]),
    )
    old_part_removed = replacement_mode == "cluster_removed_assembly" and removed_faces > 0
    boundary_checked = old_part_removed and labeled_face_count > 0
    if bbox_status == "pass" and old_part_removed:
        status = "geometry_preview_pass"
        risk = (
            "medium_low"
            if boundary_match_score >= 0.4 and centroid_metrics["boundary_position_score"] >= 0.4
            else "medium"
        )
    elif bbox_status == "pass" and has_assembly:
        status = "review_needed"
        risk = "medium_high"
    else:
        status = "review_needed"
        risk = "high"
    return {
        "status": status,
        "risk": risk,
        "replacement_mode": replacement_mode,
        "old_part_removed": old_part_removed,
        "removed_source_face_count": removed_faces,
        "boundary_edge_count": boundary_edge_count,
        "replacement_boundary_edge_count": replacement_boundary_edge_count,
        "boundary_match_score": boundary_match_score,
        "source_boundary_centroid": source_boundary_centroid,
        "replacement_boundary_centroid": replacement_boundary_centroid,
        "boundary_centroid_distance": centroid_metrics["boundary_centroid_distance"],
        "boundary_centroid_error_normalized": centroid_metrics[
            "boundary_centroid_error_normalized"
        ],
        "boundary_position_score": centroid_metrics["boundary_position_score"],
        "labeled_source_face_count": labeled_face_count,
        "has_assembly_preview": has_assembly,
        "watertight_boolean": False,
        "boundary_ring_checked": boundary_checked,
        "bbox_status": bbox_status or "not_run",
    }


def _socket_compatibility_score(fit_result: dict[str, Any], seam_validation: dict[str, Any]) -> float:
    quality = fit_result.get("quality", {})
    bbox_score = float(quality.get("bbox_extent_similarity") or 0.0)
    boundary_match = float(seam_validation.get("boundary_match_score") or 0.0)
    boundary_position = float(seam_validation.get("boundary_position_score") or 0.0)
    removal_score = 1.0 if seam_validation.get("old_part_removed") else 0.0
    score = (
        bbox_score * 0.35
        + boundary_match * 0.25
        + boundary_position * 0.25
        + removal_score * 0.15
    )
    return round(max(0.0, min(1.0, score)), 4)


def _boundary_centroid_metrics(
    source_centroid: Any,
    replacement_centroid: Any,
    target_extent: Any,
) -> dict[str, float]:
    if not (
        isinstance(source_centroid, list)
        and isinstance(replacement_centroid, list)
        and len(source_centroid) == 3
        and len(replacement_centroid) == 3
    ):
        return {
            "boundary_centroid_distance": 0.0,
            "boundary_centroid_error_normalized": 1.0,
            "boundary_position_score": 0.0,
        }
    try:
        source = [float(item) for item in source_centroid]
        replacement = [float(item) for item in replacement_centroid]
        extent = [float(item) for item in target_extent]
    except (TypeError, ValueError):
        return {
            "boundary_centroid_distance": 0.0,
            "boundary_centroid_error_normalized": 1.0,
            "boundary_position_score": 0.0,
        }
    distance = math.dist(source, replacement)
    diagonal = max(math.dist([0.0, 0.0, 0.0], extent), 1e-6)
    normalized = distance / diagonal
    return {
        "boundary_centroid_distance": round(distance, 6),
        "boundary_centroid_error_normalized": round(normalized, 6),
        "boundary_position_score": round(max(0.0, 1.0 - normalized), 4),
    }


def _extent_similarity(source_extent: list[float], target_extent: list[float]) -> float:
    ratios = []
    for source, target in zip(source_extent, target_extent, strict=True):
        high = max(source, target, 1e-6)
        low = max(min(source, target), 1e-6)
        ratios.append(low / high)
    return sum(ratios) / len(ratios)
