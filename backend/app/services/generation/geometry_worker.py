from __future__ import annotations

import json
import io
import math
import shutil
import subprocess
import urllib.parse
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.models import ApiErrorBody, GeometryWorkerRequest, GeometryWorkerResponse, JobStatus
from app.services.generation.generation_orchestrator import RemoteCreativeFlowWorkerAdapter
from app.services.shared.mesh_utils import (
    bbox_from_part,
    bbox_metrics,
    build_bbox_fit_result,
    cluster_id_from_part,
    extract_faces_obj,
    extract_labeled_region_obj,
    face_labels_path_from_part,
    files_root,
    merge_obj_pair,
    normalize_obj,
    obj_bbox,
    open_boundary_metrics,
    parse_obj_vertices,
    parse_npy_ints,
    remove_labeled_faces,
    transform_obj,
)


class GeometryProcessingWorker:
    def __init__(self, remote_adapter: RemoteCreativeFlowWorkerAdapter) -> None:
        self.remote_adapter = remote_adapter
        self.blender_bin = shutil.which("blender")

    async def run(self, operation: str, request: GeometryWorkerRequest) -> GeometryWorkerResponse:
        job_id = f"geomjob_{uuid4().hex[:10]}"
        operation = operation.replace("_", "-")
        try:
            result = await self._run_operation(operation, request, job_id)
            return GeometryWorkerResponse(
                ok=True,
                job_id=job_id,
                status=JobStatus.completed,
                operation=operation,
                **result,
            )
        except Exception as exc:
            return GeometryWorkerResponse(
                ok=False,
                job_id=job_id,
                status=JobStatus.failed,
                operation=operation,
                error=ApiErrorBody(
                    code="GEOMETRY_WORKER_FAILED",
                    message=str(exc),
                    retryable=True,
                ),
            )

    async def _run_operation(
        self,
        operation: str,
        request: GeometryWorkerRequest,
        job_id: str,
    ) -> dict:
        interactive_previews = {
            "deform-preview",
            "sculpt-grab",
            "sculpt-draw",
            "sculpt-plateau",
            "add-primitive",
        }
        prefer_local = (
            operation in interactive_previews
            and self.blender_bin is not None
            and request.options.get("prefer_local_blender", True)
        )
        if prefer_local:
            try:
                local_result = await self._run_local_operation(operation, request, job_id)
                metrics = local_result.setdefault("metrics", {})
                if isinstance(metrics, dict):
                    metrics["sculpt_engine"] = "blender_headless_local"
                return local_result
            except Exception as exc:
                if not request.options.get("allow_local_fallback", True):
                    raise
                remote_result = await self._run_remote_operation(operation, request, job_id)
                metrics = remote_result.setdefault("metrics", {})
                if isinstance(metrics, dict):
                    metrics["local_blender_error"] = str(exc)[-500:]
                return remote_result
        if self.remote_adapter.is_configured:
            try:
                return await self._run_remote_operation(operation, request, job_id)
            except Exception as exc:
                if not request.options.get("allow_local_fallback", True):
                    raise
                local_result = await self._run_local_operation(operation, request, job_id)
                metadata = local_result.setdefault("metrics", {})
                if isinstance(metadata, dict):
                    metadata["remote_geometry_fallback_error"] = str(exc)
                return local_result
        return await self._run_local_operation(operation, request, job_id)

        return await self._run_local_operation(operation, request, job_id)

    async def _run_local_operation(
        self,
        operation: str,
        request: GeometryWorkerRequest,
        job_id: str,
    ) -> dict:
        if operation == "normalize":
            data = await self._read_source_mesh(request)
            obj_text, metrics = normalize_obj(data)
            url = self._write_text(job_id, "normalized.obj", obj_text)
            return {"result_mesh_url": url, "preview_mesh_url": url, "metrics": metrics}

        if operation == "bbox":
            data = await self._read_source_mesh(request)
            return {"metrics": bbox_metrics(data)}

        if operation in {"extract-region", "attachment-boundary"}:
            data = await self._read_source_mesh(request)
            labels = await self._read_part_labels(request)
            cluster_id = cluster_id_from_part(request.part)
            if cluster_id is None:
                raise ValueError("part metadata must include source_part_id or cluster_id")
            obj_text, metrics = extract_labeled_region_obj(data, labels, cluster_id)
            url = self._write_text(job_id, "selected_region.obj", obj_text)
            artifacts = {"selected_region": url}
            if operation == "attachment-boundary":
                artifacts["attachment_boundary"] = {
                    "boundary_edge_count": metrics.get("boundary_edge_count"),
                    "boundary_centroid": metrics.get("boundary_centroid"),
                }
            return {
                "result_mesh_url": url,
                "preview_mesh_url": url,
                "metrics": metrics,
                "artifacts": artifacts,
            }

        if operation == "extract-faces":
            data = await self._read_source_mesh(request)
            if not request.face_indices:
                raise ValueError("face_indices is required for extract-faces")
            obj_text, metrics = extract_faces_obj(data, set(request.face_indices))
            url = self._write_text(job_id, "selected_faces.obj", obj_text)
            return {
                "result_mesh_url": url,
                "preview_mesh_url": url,
                "metrics": metrics,
                "artifacts": {"selected_faces": url},
            }

        if operation == "deform-preview":
            tool = str(request.options.get("tool") or request.options.get("sculpt_tool") or "grab").lower()
            if tool in {"move", "drag", "grab"}:
                return await self._run_sculpt_like_operation("grab", request, job_id)
            if tool in {"draw", "brush", "clay"}:
                return await self._run_sculpt_like_operation("draw", request, job_id)
            if tool in {"smooth", "plateau", "flatten"}:
                return await self._run_sculpt_like_operation("plateau", request, job_id)
            return await self._run_sculpt_like_operation("grab", request, job_id)

        if operation in {"sculpt-grab", "sculpt-draw", "sculpt-plateau"}:
            return await self._run_sculpt_like_operation(operation.removeprefix("sculpt-"), request, job_id)

        if operation == "add-primitive":
            return await self._run_add_primitive_operation(request, job_id)

        if operation == "fit-candidate":
            source_candidate = await self._read_candidate_mesh(request)
            target_bbox = request.options.get("target_bbox") or bbox_from_part(request.part)
            if not isinstance(target_bbox, dict):
                raise ValueError("target bbox is required via part.metadata.bbox3d or options.target_bbox")
            policy = str(request.options.get("fit_policy") or request.options.get("policy") or "bbox_uniform")
            fit = build_bbox_fit_result(
                obj_bbox(source_candidate),
                target_bbox,
                policy,
                target_part_id=(request.part or {}).get("part_id") if isinstance(request.part, dict) else None,
            )
            obj_text = transform_obj(source_candidate, fit["transform"])
            boundary = open_boundary_metrics(obj_text)
            url = self._write_text(job_id, "fitted.obj", obj_text)
            return {
                "result_mesh_url": url,
                "preview_mesh_url": url,
                "metrics": {**fit, "replacement_boundary": boundary},
                "artifacts": {"fitted_mesh": url},
            }

        if operation == "seam-blend":
            source = await self._read_source_mesh(request)
            candidate = await self._read_candidate_mesh(request)
            labels = None
            cluster_id = cluster_id_from_part(request.part)
            try:
                labels = await self._read_part_labels(request)
            except Exception:
                labels = None
            note = "overlay; source part was not removed"
            metrics = {"replacement_mode": "assembly_overlay"}
            if labels is not None and cluster_id is not None:
                source, removal = remove_labeled_faces(source, labels, cluster_id)
                metrics = {**metrics, **removal, "replacement_mode": "cluster_removed_assembly"}
                note = "target PartField cluster faces removed before fitted candidate insertion"
            obj_text = merge_obj_pair(source, candidate, note)
            url = self._write_text(job_id, "seam_preview.obj", obj_text)
            return {
                "result_mesh_url": url,
                "preview_mesh_url": url,
                "metrics": metrics,
                "artifacts": {"seam_preview": url},
            }

        if operation == "cleanup":
            data = await self._read_source_mesh(request)
            text = data.decode("utf-8", errors="ignore")
            cleaned = "\n".join(line.rstrip() for line in text.splitlines() if line.strip()) + "\n"
            url = self._write_text(job_id, "cleaned.obj", cleaned)
            return {
                "result_mesh_url": url,
                "preview_mesh_url": url,
                "metrics": {"cleanup": "trimmed_blank_lines", **bbox_metrics(cleaned.encode("utf-8"))},
            }

        if operation == "convert":
            data = await self._read_source_mesh(request)
            output_format = str(request.options.get("output_format") or "obj").lower().lstrip(".")
            if output_format != "obj":
                raise ValueError("MVP format conversion currently supports OBJ output only")
            url = self._write_bytes(job_id, "converted.obj", data)
            return {
                "result_mesh_url": url,
                "preview_mesh_url": url,
                "metrics": {"output_format": "obj", **bbox_metrics(data)},
            }

        raise ValueError(f"Unsupported geometry operation: {operation}")

    async def _run_remote_operation(
        self,
        operation: str,
        request: GeometryWorkerRequest,
        job_id: str,
    ) -> dict:
        payload: dict[str, Any] = {
            "flowstudio_job_id": job_id,
            "part": await self._remote_part_payload(request, job_id),
            "face_indices": request.face_indices,
            "options": await self._remote_options_payload(request, job_id),
        }
        if request.source_mesh_path or request.source_mesh_url:
            payload["source_mesh_path"] = await self._remote_mesh_path(
                request.source_mesh_path or request.source_mesh_url,
                job_id,
                "source",
            )
        if request.candidate_mesh_path or request.candidate_mesh_url:
            payload["candidate_mesh_path"] = await self._remote_mesh_path(
                request.candidate_mesh_path or request.candidate_mesh_url,
                job_id,
                "candidate",
            )

        remote = await self.remote_adapter._post_json(f"/geometry/{operation}", payload)
        if not remote.get("ok"):
            raise RuntimeError(str(remote.get("error") or "Remote geometry worker failed"))
        return self._localize_remote_geometry(remote)

    async def _remote_mesh_path(self, value: str | None, job_id: str, role: str) -> str:
        if not value:
            raise ValueError(f"{role} mesh path or URL is required")
        remote_path = self._remote_artifact_path(value)
        if remote_path:
            local = Path(remote_path)
            if local.exists() and local.is_file():
                if local.read_bytes().startswith(b"glTF"):
                    converted = self._artifact_path(job_id, f"{role}_source.obj")
                    converted.write_bytes(_convert_glb_to_obj(local.read_bytes()))
                    local = converted
                uploaded = await self.remote_adapter.upload_file(
                    str(local),
                    flowstudio_asset_id=f"{job_id}_{role}",
                    session_id="geometry",
                )
                if uploaded and uploaded.get("path"):
                    return str(uploaded["path"])
            return remote_path
        if value.startswith("/files/"):
            local_path = files_root() / value.removeprefix("/files/")
            if local_path.read_bytes().startswith(b"glTF"):
                converted = self._artifact_path(job_id, f"{role}_source.obj")
                converted.write_bytes(_convert_glb_to_obj(local_path.read_bytes()))
                local_path = converted
            uploaded = await self.remote_adapter.upload_file(
                str(local_path),
                flowstudio_asset_id=f"{job_id}_{role}",
                session_id="geometry",
            )
            if not uploaded or not uploaded.get("path"):
                raise RuntimeError("Remote geometry asset upload failed")
            return str(uploaded["path"])
        local = Path(value)
        if local.exists():
            if local.read_bytes().startswith(b"glTF"):
                converted = self._artifact_path(job_id, f"{role}_source.obj")
                converted.write_bytes(_convert_glb_to_obj(local.read_bytes()))
                local = converted
            uploaded = await self.remote_adapter.upload_file(
                str(local),
                flowstudio_asset_id=f"{job_id}_{role}",
                session_id="geometry",
            )
            if not uploaded or not uploaded.get("path"):
                raise RuntimeError("Remote geometry asset upload failed")
            return str(uploaded["path"])
        if value.startswith("/"):
            return value
        raise ValueError(f"Mesh is not readable by remote geometry worker: {value}")

    async def _remote_part_payload(self, request: GeometryWorkerRequest, job_id: str) -> dict[str, Any] | None:
        if not isinstance(request.part, dict):
            return request.part
        part = _copy_json_dict(request.part)
        labels_path = face_labels_path_from_part(part)
        if labels_path:
            remote_labels = await self._remote_file_path(labels_path, job_id, "part_labels")
            metadata = part.get("metadata") if isinstance(part.get("metadata"), dict) else part
            metadata["face_labels_path"] = remote_labels
        return part

    async def _remote_options_payload(self, request: GeometryWorkerRequest, job_id: str) -> dict[str, Any]:
        options = _copy_json_dict(request.options)
        labels_path = options.get("face_labels_path")
        if isinstance(labels_path, str) and labels_path:
            options["face_labels_path"] = await self._remote_file_path(labels_path, job_id, "option_labels")
        return options

    async def _remote_file_path(self, value: str, job_id: str, role: str) -> str:
        remote_path = self._remote_artifact_path(value)
        if remote_path:
            return remote_path
        if value.startswith("/files/"):
            local_path = files_root() / value.removeprefix("/files/")
        else:
            local_path = Path(value)
        if local_path.exists():
            uploaded = await self.remote_adapter.upload_file(
                str(local_path),
                flowstudio_asset_id=f"{job_id}_{role}",
                session_id="geometry",
            )
            if not uploaded or not uploaded.get("path"):
                raise RuntimeError("Remote geometry support-file upload failed")
            return str(uploaded["path"])
        if value.startswith("/"):
            return value
        raise ValueError(f"File is not readable by remote geometry worker: {value}")

    def _remote_artifact_path(self, value: str) -> str | None:
        if value.startswith("/api/v1/remote-worker/artifact-file") or value.startswith("/artifact-file"):
            parsed = urllib.parse.urlparse(value)
            query = urllib.parse.parse_qs(parsed.query)
            remote_path = (query.get("path") or [None])[0]
            if not remote_path:
                raise ValueError("remote artifact URL is missing path query")
            return remote_path
        return None

    def _localize_remote_geometry(self, remote: dict[str, Any]) -> dict[str, Any]:
        result_path = remote.get("result_mesh_path")
        preview_path = remote.get("preview_mesh_path")
        return {
            "result_mesh_url": self.remote_adapter.artifact_proxy_url(str(result_path)) if result_path else None,
            "preview_mesh_url": self.remote_adapter.artifact_proxy_url(str(preview_path)) if preview_path else None,
            "metrics": {
                **(remote.get("metrics") if isinstance(remote.get("metrics"), dict) else {}),
                "remote_geometry_job_id": remote.get("job_id"),
            },
            "artifacts": self._localize_remote_artifacts(
                remote.get("artifacts") if isinstance(remote.get("artifacts"), dict) else {}
            ),
        }

    def _localize_remote_artifacts(self, artifacts: dict[str, Any]) -> dict[str, Any]:
        localized: dict[str, Any] = {}
        for key, value in artifacts.items():
            if isinstance(value, dict):
                item = dict(value)
                path = item.get("path")
                if path:
                    item["url"] = self.remote_adapter.artifact_proxy_url(str(path))
                localized[str(key)] = item
            elif isinstance(value, str):
                localized[str(key)] = self.remote_adapter.artifact_proxy_url(value) if value.startswith("/") else value
            else:
                localized[str(key)] = value
        return localized

    async def _read_source_mesh(self, request: GeometryWorkerRequest) -> bytes:
        return await self._read_mesh(request.source_mesh_path or request.source_mesh_url)

    async def _read_candidate_mesh(self, request: GeometryWorkerRequest) -> bytes:
        return await self._read_mesh(request.candidate_mesh_path or request.candidate_mesh_url)

    async def _read_mesh(self, value: str | None) -> bytes:
        if not value:
            raise ValueError("mesh path or URL is required")
        if value.startswith("/api/v1/remote-worker/artifact-file"):
            parsed = urllib.parse.urlparse(value)
            query = urllib.parse.parse_qs(parsed.query)
            remote_path = (query.get("path") or [None])[0]
            if not remote_path:
                raise ValueError("remote artifact URL is missing path query")
            local = Path(remote_path)
            if local.exists() and local.is_file():
                # Backend and worker share the same host: read the artifact
                # directly so worker-root restrictions do not block local
                # geometry previews (brush/drag/smooth/add).
                return local.read_bytes()
            data, _content_type = await self.remote_adapter.get_artifact_file(remote_path)
            return data
        if value.startswith("/files/"):
            path = files_root() / value.removeprefix("/files/")
            return path.read_bytes()
        path = Path(value)
        if path.exists():
            return path.read_bytes()
        if value.startswith("/"):
            data, _content_type = await self.remote_adapter.get_artifact_file(value)
            return data
        raise ValueError(f"Mesh is not readable by backend: {value}")

    async def _read_part_labels(self, request: GeometryWorkerRequest) -> list[int]:
        labels_path = request.options.get("face_labels_path") or face_labels_path_from_part(request.part)
        if not labels_path:
            raise ValueError("face_labels_path is required for this geometry operation")
        if isinstance(labels_path, str) and labels_path.startswith("/files/"):
            data = (files_root() / labels_path.removeprefix("/files/")).read_bytes()
        else:
            data, _content_type = await self.remote_adapter.get_artifact_file(str(labels_path))
        return parse_npy_ints(data)

    def _write_text(self, job_id: str, name: str, text: str) -> str:
        directory = files_root() / "geometry" / job_id
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / name
        target.write_text(text, encoding="utf-8")
        return f"/files/geometry/{job_id}/{name}"

    def _write_bytes(self, job_id: str, name: str, data: bytes) -> str:
        directory = files_root() / "geometry" / job_id
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / name
        target.write_bytes(data)
        return f"/files/geometry/{job_id}/{name}"

    def _artifact_path(self, job_id: str, name: str) -> Path:
        directory = files_root() / "geometry" / job_id
        directory.mkdir(parents=True, exist_ok=True)
        return directory / name

    async def _source_mesh_artifact_path(self, request: GeometryWorkerRequest, job_id: str) -> Path:
        source_path = self._artifact_path(job_id, "source.obj")
        source_path.write_bytes(_convert_glb_to_obj(await self._read_source_mesh(request)))
        return source_path

    async def _run_sculpt_like_operation(
        self,
        sculpt_tool: str,
        request: GeometryWorkerRequest,
        job_id: str,
    ) -> dict[str, Any]:
        source_path = await self._source_mesh_artifact_path(request, job_id)
        output_path = self._artifact_path(job_id, f"{sculpt_tool}_preview.obj")
        spec = self._sculpt_spec(sculpt_tool, request)
        script_path = self._write_blender_sculpt_script(job_id, source_path, output_path, spec)
        executed = False
        if self.blender_bin and request.options.get("use_blender", True):
            try:
                self._run_blender_script(script_path)
                executed = output_path.exists()
            except Exception as exc:
                spec["blender_error"] = str(exc)[-500:]
        if not executed:
            output_path.write_text(
                sculpt_obj_text(source_path.read_bytes(), spec),
                encoding="utf-8",
            )
        data = output_path.read_bytes()
        url = f"/files/geometry/{job_id}/{output_path.name}"
        return {
            "result_mesh_url": url,
            "preview_mesh_url": url,
            "metrics": {
                **bbox_metrics(data),
                "sculpt_tool": sculpt_tool,
                "sculpt_engine": "blender_headless" if executed else "python_obj_fallback",
                "brush_radius": spec["radius"],
                "strength": spec["strength"],
                "vector": spec["vector"],
                "center": spec["center"],
                **({"blender_error": spec["blender_error"]} if spec.get("blender_error") else {}),
            },
            "artifacts": {
                "blender_script_url": f"/files/geometry/{job_id}/{script_path.name}",
                "sculpt_spec": spec,
            },
        }

    async def _run_add_primitive_operation(
        self,
        request: GeometryWorkerRequest,
        job_id: str,
    ) -> dict[str, Any]:
        source_path = await self._source_mesh_artifact_path(request, job_id)
        output_path = self._artifact_path(job_id, "add_primitive_preview.obj")
        spec = self._primitive_spec(request)
        script_path = self._write_blender_add_primitive_script(job_id, source_path, output_path, spec)
        executed = False
        if self.blender_bin and request.options.get("use_blender", True):
            try:
                self._run_blender_script(script_path)
                executed = output_path.exists()
            except Exception as exc:
                spec["blender_error"] = str(exc)[-500:]
        if not executed:
            output_path.write_text(
                append_primitive_obj_text(source_path.read_bytes(), spec),
                encoding="utf-8",
            )
        data = output_path.read_bytes()
        url = f"/files/geometry/{job_id}/{output_path.name}"
        return {
            "result_mesh_url": url,
            "preview_mesh_url": url,
            "metrics": {
                **bbox_metrics(data),
                "primitive": spec["primitive"],
                "sculpt_engine": "blender_headless" if executed else "python_obj_fallback",
                **({"blender_error": spec["blender_error"]} if spec.get("blender_error") else {}),
            },
            "artifacts": {
                "blender_script_url": f"/files/geometry/{job_id}/{script_path.name}",
                "primitive_spec": spec,
            },
        }

    def _run_blender_script(self, script_path: Path) -> None:
        assert self.blender_bin is not None
        completed = subprocess.run(
            [self.blender_bin, "--background", "--python", str(script_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr.strip() or completed.stdout.strip())[-1200:])

    def _sculpt_spec(self, sculpt_tool: str, request: GeometryWorkerRequest) -> dict[str, Any]:
        options = request.options
        transform = options.get("transform") if isinstance(options.get("transform"), dict) else {}
        vector = options.get("vector") or transform.get("translation") or [0.12, 0.0, 0.0]
        if sculpt_tool == "draw":
            vector = options.get("vector") or [0.0, 0.08, 0.0]
        if sculpt_tool == "plateau":
            vector = options.get("normal") or [0.0, 1.0, 0.0]
        center = options.get("center") or bbox_center_from_part(request.part) or [0.0, 0.35, 0.0]
        return {
            "tool": sculpt_tool,
            "center": vec3(center, [0.0, 0.35, 0.0]),
            "vector": vec3(vector, [0.12, 0.0, 0.0]),
            "radius": float(options.get("radius") or options.get("influence_radius") or 0.45),
            "strength": float(options.get("strength") or (0.55 if sculpt_tool == "plateau" else 0.75)),
            "plateau_depth": float(options.get("plateau_depth") or 0.0),
            "face_indices": request.face_indices,
            "preserve_boundary": bool(options.get("preserve_boundary", True)),
            "part": request.part or {},
        }

    def _primitive_spec(self, request: GeometryWorkerRequest) -> dict[str, Any]:
        options = request.options
        transform = options.get("transform") if isinstance(options.get("transform"), dict) else {}
        return {
            "primitive": str(options.get("primitive") or "sphere").lower(),
            "position": vec3(transform.get("position") or options.get("position"), [0.0, 0.6, 0.0]),
            "scale": vec3(transform.get("scale") or options.get("scale"), [0.25, 0.25, 0.25]),
            "rotation": vec3(transform.get("rotation") or options.get("rotation"), [0.0, 0.0, 0.0]),
            "relation": options.get("relation") if isinstance(options.get("relation"), dict) else {},
        }

    def _write_blender_sculpt_script(
        self,
        job_id: str,
        source_path: Path,
        output_path: Path,
        spec: dict[str, Any],
    ) -> Path:
        script_path = self._artifact_path(job_id, f"run_{spec['tool']}.py")
        script_path.write_text(blender_sculpt_script(source_path, output_path, spec), encoding="utf-8")
        return script_path

    def _write_blender_add_primitive_script(
        self,
        job_id: str,
        source_path: Path,
        output_path: Path,
        spec: dict[str, Any],
    ) -> Path:
        script_path = self._artifact_path(job_id, "run_add_primitive.py")
        script_path.write_text(blender_add_primitive_script(source_path, output_path, spec), encoding="utf-8")
        return script_path

    def copy_into_artifact(self, source: Path, job_id: str, name: str) -> str:
        directory = files_root() / "geometry" / job_id
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / name
        shutil.copyfile(source, target)
        return f"/files/geometry/{job_id}/{name}"


def _copy_json_dict(value: dict[str, Any]) -> dict[str, Any]:
    copied: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, dict):
            copied[key] = _copy_json_dict(item)
        elif isinstance(item, list):
            copied[key] = [_copy_json_dict(entry) if isinstance(entry, dict) else entry for entry in item]
        else:
            copied[key] = item
    return copied


def _convert_glb_to_obj(data: bytes) -> bytes:
    """Convert binary GLB bytes to OBJ text so the OBJ-based geometry workers
    (Blender headless or Python fallback) can sculpt/preview them."""
    if not data.startswith(b"glTF"):
        return data
    import trimesh

    scene = trimesh.load(io.BytesIO(data), file_type="glb", force=None)
    if isinstance(scene, trimesh.Scene):
        geometries = [geometry for geometry in scene.geometry.values() if geometry is not None]
        if not geometries:
            raise ValueError("GLB scene has no geometry")
        mesh = geometries[0] if len(geometries) == 1 else trimesh.util.concatenate(geometries)
    else:
        mesh = scene
    obj_text = trimesh.exchange.obj.export_obj(mesh, include_texture=False)
    return obj_text.encode("utf-8")


def vec3(value: Any, default: list[float]) -> list[float]:
    if isinstance(value, (int, float)):
        number = float(value)
        return [number, number, number]
    if isinstance(value, list) and len(value) >= 3:
        try:
            return [float(value[0]), float(value[1]), float(value[2])]
        except (TypeError, ValueError):
            return default
    return default


def bbox_center_from_part(part: dict[str, Any] | None) -> list[float] | None:
    if not isinstance(part, dict):
        return None
    bbox = part.get("bbox") or (part.get("metadata") if isinstance(part.get("metadata"), dict) else {}).get("bbox3d")
    if isinstance(bbox, dict) and isinstance(bbox.get("min"), list) and isinstance(bbox.get("max"), list):
        return [(float(bbox["min"][i]) + float(bbox["max"][i])) / 2.0 for i in range(3)]
    if isinstance(bbox, list) and len(bbox) >= 6:
        return [(float(bbox[i]) + float(bbox[i + 3])) / 2.0 for i in range(3)]
    return None


def sculpt_obj_text(data: bytes, spec: dict[str, Any]) -> str:
    text = data.decode("utf-8", errors="ignore")
    center = spec["center"]
    vector = spec["vector"]
    radius = max(1e-6, float(spec["radius"]))
    strength = max(0.0, min(1.0, float(spec["strength"])))
    tool = str(spec["tool"])
    selected_vertices = selected_vertices_from_faces(text, set(spec.get("face_indices") or []))
    vertices = parse_obj_vertices(text)
    if tool == "plateau":
        normal = normalize(vector)
        candidates = selected_vertices or set(range(len(vertices)))
        heights = [dot(sub(vertices[index], center), normal) for index in candidates if index < len(vertices)]
        target_height = (sum(heights) / len(heights)) + float(spec.get("plateau_depth") or 0.0) if heights else 0.0
    else:
        normal = normalize(vector)
        target_height = 0.0
    output: list[str] = []
    vertex_index = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("v "):
            output.append(raw_line)
            continue
        fields = line.split()
        try:
            point = [float(fields[1]), float(fields[2]), float(fields[3])]
        except (IndexError, ValueError):
            output.append(raw_line)
            continue
        if selected_vertices and vertex_index not in selected_vertices:
            moved = point
        else:
            distance = math.dist(point, center)
            falloff = smooth_falloff(distance / radius)
            if tool == "grab":
                moved = [point[i] + vector[i] * strength * falloff for i in range(3)]
            elif tool == "draw":
                moved = [point[i] + normal[i] * strength * radius * 0.35 * falloff for i in range(3)]
            elif tool == "plateau":
                height = dot(sub(point, center), normal)
                correction = (target_height - height) * strength * falloff
                moved = [point[i] + normal[i] * correction for i in range(3)]
            else:
                moved = point
        suffix = " ".join(fields[4:])
        output.append(
            f"v {format_float(moved[0])} {format_float(moved[1])} {format_float(moved[2])} {suffix}".rstrip()
        )
        vertex_index += 1
    return "\n".join(output) + "\n"


def append_primitive_obj_text(data: bytes, spec: dict[str, Any]) -> str:
    source = data.decode("utf-8", errors="ignore").rstrip()
    vertices, faces = primitive_mesh(spec["primitive"], spec["position"], spec["scale"])
    offset = len(parse_obj_vertices(source))
    lines = [source, f"o flowstudio_added_{spec['primitive']}"]
    for point in vertices:
        lines.append(f"v {format_float(point[0])} {format_float(point[1])} {format_float(point[2])}")
    for face in faces:
        lines.append("f " + " ".join(str(index + offset) for index in face))
    return "\n".join(lines) + "\n"


def primitive_mesh(primitive: str, position: list[float], scale: list[float]) -> tuple[list[list[float]], list[list[int]]]:
    if primitive in {"plane", "circle"}:
        sides = 24 if primitive == "circle" else 4
        sx, _sy, sz = [item / 2.0 for item in scale]
        if primitive == "plane":
            vertices = [[-sx, 0.0, -sz], [sx, 0.0, -sz], [sx, 0.0, sz], [-sx, 0.0, sz]]
            faces = [[1, 2, 3, 4]]
        else:
            vertices = [[0.0, 0.0, 0.0]]
            for i in range(sides):
                angle = math.tau * i / sides
                vertices.append([math.cos(angle) * sx, 0.0, math.sin(angle) * sz])
            faces = [[1, i + 2, ((i + 1) % sides) + 2] for i in range(sides)]
    elif primitive in {"cube", "box"}:
        sx, sy, sz = [item / 2.0 for item in scale]
        vertices = [
            [-sx, -sy, -sz],
            [sx, -sy, -sz],
            [sx, sy, -sz],
            [-sx, sy, -sz],
            [-sx, -sy, sz],
            [sx, -sy, sz],
            [sx, sy, sz],
            [-sx, sy, sz],
        ]
        faces = [[1, 2, 3, 4], [5, 8, 7, 6], [1, 5, 6, 2], [2, 6, 7, 3], [3, 7, 8, 4], [4, 8, 5, 1]]
    elif primitive in {"cylinder", "cone"}:
        sides = 16
        top_radius = 0.0 if primitive == "cone" else scale[0] / 2.0
        bottom_radius = scale[0] / 2.0
        half_h = scale[1] / 2.0
        vertices = []
        for z, radius in [(-half_h, bottom_radius), (half_h, top_radius)]:
            for i in range(sides):
                angle = math.tau * i / sides
                vertices.append([math.cos(angle) * radius, z, math.sin(angle) * radius])
        faces = []
        for i in range(sides):
            j = (i + 1) % sides
            if primitive == "cone":
                faces.append([i + 1, j + 1, sides + 1])
            else:
                faces.append([i + 1, j + 1, sides + j + 1, sides + i + 1])
        if primitive == "cone":
            vertices = vertices[:sides] + [[0.0, half_h, 0.0]]
        faces.append([i + 1 for i in range(sides)])
    elif primitive in {"torus"}:
        major_segments = 16
        minor_segments = 8
        major = max(scale[0], scale[2]) * 0.35
        minor = max(0.01, min(scale) * 0.16)
        vertices = []
        for i in range(major_segments):
            theta = math.tau * i / major_segments
            for j in range(minor_segments):
                phi = math.tau * j / minor_segments
                ring = major + minor * math.cos(phi)
                vertices.append([ring * math.cos(theta), minor * math.sin(phi), ring * math.sin(theta)])
        faces = []
        for i in range(major_segments):
            for j in range(minor_segments):
                a = i * minor_segments + j + 1
                b = ((i + 1) % major_segments) * minor_segments + j + 1
                c = ((i + 1) % major_segments) * minor_segments + ((j + 1) % minor_segments) + 1
                d = i * minor_segments + ((j + 1) % minor_segments) + 1
                faces.append([a, b, c, d])
    else:
        # low-poly sphere/ico fallback
        sx, sy, sz = [item / 2.0 for item in scale]
        vertices = [[0, sy, 0], [sx, 0, 0], [0, 0, sz], [-sx, 0, 0], [0, 0, -sz], [0, -sy, 0]]
        faces = [[1, 2, 3], [1, 3, 4], [1, 4, 5], [1, 5, 2], [6, 3, 2], [6, 4, 3], [6, 5, 4], [6, 2, 5]]
    moved = [[point[0] + position[0], point[1] + position[1], point[2] + position[2]] for point in vertices]
    return moved, faces


def selected_vertices_from_faces(text: str, face_indices: set[int]) -> set[int]:
    if not face_indices:
        return set()
    selected: set[int] = set()
    face_index = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("f "):
            if face_index in face_indices:
                selected.update(index - 1 for index in face_vertex_indices(line) if index > 0)
            face_index += 1
    return selected


def face_vertex_indices(line: str) -> list[int]:
    indices: list[int] = []
    for item in line.split()[1:]:
        try:
            indices.append(int(item.split("/")[0]))
        except ValueError:
            continue
    return indices


def smooth_falloff(t: float) -> float:
    if t >= 1.0:
        return 0.0
    t = max(0.0, t)
    return 1.0 - (3.0 * t * t - 2.0 * t * t * t)


def normalize(vector: list[float]) -> list[float]:
    length = math.sqrt(sum(item * item for item in vector)) or 1.0
    return [item / length for item in vector]


def sub(a: list[float], b: list[float]) -> list[float]:
    return [a[i] - b[i] for i in range(3)]


def dot(a: list[float], b: list[float]) -> float:
    return sum(a[i] * b[i] for i in range(3))


def format_float(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"


def blender_sculpt_script(source_path: Path, output_path: Path, spec: dict[str, Any]) -> str:
    payload = json.dumps(spec, ensure_ascii=False)
    return f"""import bpy, bmesh, json, math
from mathutils import Vector

SOURCE = {str(source_path)!r}
OUTPUT = {str(output_path)!r}
SPEC = json.loads({payload!r})

def import_obj(path):
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    if hasattr(bpy.ops.wm, 'obj_import'):
        bpy.ops.wm.obj_import(filepath=path)
    else:
        bpy.ops.import_scene.obj(filepath=path)
    obj = bpy.context.selected_objects[0]
    bpy.context.view_layer.objects.active = obj
    return obj

def export_obj(path):
    if hasattr(bpy.ops.wm, 'obj_export'):
        bpy.ops.wm.obj_export(filepath=path, export_selected_objects=True)
    else:
        bpy.ops.export_scene.obj(filepath=path, use_selection=True)

def falloff(t):
    if t >= 1.0:
        return 0.0
    t = max(0.0, t)
    return 1.0 - (3.0 * t * t - 2.0 * t * t * t)

obj = import_obj(SOURCE)
mesh = obj.data
bm = bmesh.new()
bm.from_mesh(mesh)
bm.verts.ensure_lookup_table()
center = Vector(SPEC['center'])
vector = Vector(SPEC['vector'])
normal = vector.normalized() if vector.length else Vector((0, 1, 0))
radius = max(1e-6, float(SPEC['radius']))
strength = max(0.0, min(1.0, float(SPEC['strength'])))
tool = SPEC['tool']
face_indices = set(SPEC.get('face_indices') or [])
selected = set()
if face_indices:
    bm.faces.ensure_lookup_table()
    for index in face_indices:
        if index < len(bm.faces):
            selected.update(v.index for v in bm.faces[index].verts)

if tool == 'plateau':
    verts = [v for v in bm.verts if (not selected or v.index in selected)]
    heights = [(v.co - center).dot(normal) for v in verts]
    target = (sum(heights) / len(heights) if heights else 0.0) + float(SPEC.get('plateau_depth') or 0.0)
else:
    target = 0.0

for vert in bm.verts:
    if selected and vert.index not in selected:
        continue
    w = falloff((vert.co - center).length / radius)
    if w <= 0:
        continue
    if tool == 'grab':
        vert.co += vector * strength * w
    elif tool == 'draw':
        vert.co += normal * strength * radius * 0.35 * w
    elif tool == 'plateau':
        height = (vert.co - center).dot(normal)
        vert.co += normal * ((target - height) * strength * w)

bm.to_mesh(mesh)
bm.free()
obj.select_set(True)
export_obj(OUTPUT)
"""


def blender_add_primitive_script(source_path: Path, output_path: Path, spec: dict[str, Any]) -> str:
    payload = json.dumps(spec, ensure_ascii=False)
    return f"""import bpy, json, math

SOURCE = {str(source_path)!r}
OUTPUT = {str(output_path)!r}
SPEC = json.loads({payload!r})

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
if hasattr(bpy.ops.wm, 'obj_import'):
    bpy.ops.wm.obj_import(filepath=SOURCE)
else:
    bpy.ops.import_scene.obj(filepath=SOURCE)
source_objects = list(bpy.context.selected_objects)

primitive = SPEC.get('primitive', 'sphere')
position = SPEC.get('position', [0, 0.6, 0])
scale = SPEC.get('scale', [0.25, 0.25, 0.25])
if primitive in ('cube', 'box'):
    bpy.ops.mesh.primitive_cube_add(size=1, location=position)
elif primitive in ('plane',):
    bpy.ops.mesh.primitive_plane_add(size=1, location=position)
elif primitive in ('circle',):
    bpy.ops.mesh.primitive_circle_add(vertices=32, radius=0.5, fill_type='TRIFAN', location=position)
elif primitive in ('cylinder',):
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.5, depth=1.0, location=position)
elif primitive in ('cone',):
    bpy.ops.mesh.primitive_cone_add(vertices=32, radius1=0.5, radius2=0, depth=1.0, location=position)
elif primitive in ('torus',):
    bpy.ops.mesh.primitive_torus_add(major_radius=0.35, minor_radius=0.12, location=position)
else:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=0.5, location=position)
added = bpy.context.object
added.name = 'flowstudio_added_' + primitive
added.scale = scale
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

bpy.ops.object.select_all(action='DESELECT')
for obj in source_objects + [added]:
    obj.select_set(True)
bpy.context.view_layer.objects.active = added
if hasattr(bpy.ops.wm, 'obj_export'):
    bpy.ops.wm.obj_export(filepath=OUTPUT, export_selected_objects=True)
else:
    bpy.ops.export_scene.obj(filepath=OUTPUT, use_selection=True)
"""
