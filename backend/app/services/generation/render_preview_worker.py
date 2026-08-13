from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
import urllib.parse
import urllib.request
from pathlib import Path
from uuid import uuid4

from app.models import ApiErrorBody, JobStatus, RenderPreviewRequest, RenderPreviewResponse
from app.services.generation.generation_orchestrator import RemoteCreativeFlowWorkerAdapter
from app.services.shared.mesh_utils import files_root


class RenderPreviewWorker:
    def __init__(self, remote_adapter: RemoteCreativeFlowWorkerAdapter, blender_bin: str | None = None) -> None:
        self.remote_adapter = remote_adapter
        self.blender_bin = blender_bin or shutil.which("blender")

    async def run(self, operation: str, request: RenderPreviewRequest) -> RenderPreviewResponse:
        job_id = f"renderjob_{uuid4().hex[:10]}"
        operation = operation.replace("_", "-")
        try:
            result = await self._run_operation(operation, request, job_id)
            return RenderPreviewResponse(
                ok=True,
                job_id=job_id,
                status=JobStatus.completed,
                operation=operation,
                **result,
            )
        except Exception as exc:
            return RenderPreviewResponse(
                ok=False,
                job_id=job_id,
                status=JobStatus.failed,
                operation=operation,
                error=ApiErrorBody(
                    code="RENDER_PREVIEW_WORKER_FAILED",
                    message=str(exc),
                    retryable=True,
                ),
                metadata={
                    "engine": "blender",
                    "blender_configured": bool(self.blender_bin),
                },
            )

    async def _run_operation(
        self,
        operation: str,
        request: RenderPreviewRequest,
        job_id: str,
    ) -> dict:
        if not self.blender_bin:
            if self.remote_adapter.is_configured:
                return await self._run_remote_operation(operation, request, job_id)
            raise RuntimeError("Blender executable is not available on this machine")
        mesh_path = await self._materialize_mesh(request.source_mesh_path or request.source_mesh_url, job_id, "source.obj")
        candidate_path: Path | None = None
        if request.candidate_mesh_path or request.candidate_mesh_url:
            candidate_path = await self._materialize_mesh(
                request.candidate_mesh_path or request.candidate_mesh_url,
                job_id,
                "candidate.obj",
            )

        if operation == "thumbnail":
            image = self._render(
                mesh_path,
                job_id,
                "thumb.png",
                view="three_quarter",
                clay=bool(request.options.get("clay", False)),
            )
            return {
                "thumbnail_url": image,
                "views": {"three_quarter": image},
                "metadata": self._metadata("thumbnail"),
                "artifacts": {"thumbnail": image},
            }

        if operation in {"multiview", "part-preview", "mask-visualization", "candidate-card"}:
            clay = bool(request.options.get("clay", False))
            views = {
                "front": self._render(mesh_path, job_id, "front.png", view="front", clay=clay),
                "side": self._render(mesh_path, job_id, "side.png", view="side", clay=clay),
                "three_quarter": self._render(mesh_path, job_id, "three_quarter.png", view="three_quarter", clay=clay),
            }
            return {
                "thumbnail_url": views["three_quarter"],
                "views": views,
                "metadata": self._metadata(operation),
                "artifacts": {"views": views},
            }

        if operation == "before-after":
            if candidate_path is None:
                raise ValueError("candidate mesh is required for before-after render")
            before = self._render(mesh_path, job_id, "before.png", view="three_quarter")
            after = self._render(candidate_path, job_id, "after.png", view="three_quarter")
            return {
                "thumbnail_url": after,
                "views": {"before": before, "after": after},
                "metadata": self._metadata("before-after"),
                "artifacts": {"before": before, "after": after},
            }

        if operation == "turntable":
            views = {
                "front": self._render(mesh_path, job_id, "turntable_000.png", view="front"),
                "side": self._render(mesh_path, job_id, "turntable_090.png", view="side"),
                "back": self._render(mesh_path, job_id, "turntable_180.png", view="back"),
                "three_quarter": self._render(mesh_path, job_id, "turntable_315.png", view="three_quarter"),
            }
            return {
                "thumbnail_url": views["three_quarter"],
                "views": views,
                "metadata": self._metadata("turntable"),
                "artifacts": {"turntable_frames": views},
            }

        raise ValueError(f"Unsupported render operation: {operation}")

    async def _run_remote_operation(
        self,
        operation: str,
        request: RenderPreviewRequest,
        job_id: str,
    ) -> dict:
        source_path = await self._remote_mesh_path(
            request.source_mesh_path or request.source_mesh_url,
            job_id,
            "source",
        )
        candidate_path = None
        if request.candidate_mesh_path or request.candidate_mesh_url:
            candidate_path = await self._remote_mesh_path(
                request.candidate_mesh_path or request.candidate_mesh_url,
                job_id,
                "candidate",
            )
        remote = await self.remote_adapter._post_json(
            f"/render/{operation}",
            {
                "flowstudio_job_id": job_id,
                "source_mesh_path": source_path,
                "candidate_mesh_path": candidate_path,
                "options": request.options,
            },
        )
        if not remote.get("ok"):
            raise RuntimeError(str(remote.get("error") or "Remote render worker failed"))
        return self._localize_remote_render(remote)

    async def _remote_mesh_path(self, value: str | None, job_id: str, role: str) -> str:
        if not value:
            raise ValueError(f"{role} mesh path or URL is required")
        if value.startswith("/api/v1/remote-worker/artifact-file"):
            parsed = urllib.parse.urlparse(value)
            query = urllib.parse.parse_qs(parsed.query)
            remote_path = (query.get("path") or [None])[0]
            if not remote_path:
                raise ValueError("remote artifact URL is missing path query")
            return remote_path
        if value.startswith("/files/"):
            local_path = files_root() / value.removeprefix("/files/")
            uploaded = await self.remote_adapter.upload_file(
                str(local_path),
                flowstudio_asset_id=f"{job_id}_{role}",
                session_id="render",
            )
            if not uploaded or not uploaded.get("path"):
                raise RuntimeError("Remote render asset upload failed")
            return str(uploaded["path"])
        local = Path(value)
        if local.exists():
            uploaded = await self.remote_adapter.upload_file(
                str(local),
                flowstudio_asset_id=f"{job_id}_{role}",
                session_id="render",
            )
            if not uploaded or not uploaded.get("path"):
                raise RuntimeError("Remote render asset upload failed")
            return str(uploaded["path"])
        if value.startswith("/"):
            return value
        raise ValueError(f"Mesh is not readable by remote render worker: {value}")

    def _localize_remote_render(self, remote: dict) -> dict:
        thumbnail_path = remote.get("thumbnail_path")
        thumbnail_url = self.remote_adapter.artifact_proxy_url(thumbnail_path) if thumbnail_path else None
        view_paths = remote.get("view_paths") if isinstance(remote.get("view_paths"), dict) else {}
        views = {
            str(key): self.remote_adapter.artifact_proxy_url(str(path)) or ""
            for key, path in view_paths.items()
            if path
        }
        artifacts: dict[str, object] = {}
        raw_artifacts = remote.get("artifacts") if isinstance(remote.get("artifacts"), dict) else {}
        for key, value in raw_artifacts.items():
            if isinstance(value, dict) and value.get("path"):
                path = str(value["path"])
                artifacts[str(key)] = {
                    **value,
                    "url": self.remote_adapter.artifact_proxy_url(path),
                }
        return {
            "thumbnail_url": thumbnail_url,
            "views": views,
            "turntable_video_url": self.remote_adapter.artifact_proxy_url(remote.get("turntable_video_path"))
            if remote.get("turntable_video_path")
            else None,
            "metadata": {
                **(remote.get("metadata") if isinstance(remote.get("metadata"), dict) else {}),
                "remote_render_job_id": remote.get("job_id"),
            },
            "artifacts": artifacts,
        }

    async def _materialize_mesh(self, value: str | None, job_id: str, name: str) -> Path:
        if not value:
            raise ValueError("source mesh path or URL is required")
        target = files_root() / "render" / job_id / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if value.startswith("/api/v1/remote-worker/artifact-file"):
            parsed = urllib.parse.urlparse(value)
            query = urllib.parse.parse_qs(parsed.query)
            remote_path = (query.get("path") or [None])[0]
            if not remote_path:
                raise ValueError("remote artifact URL is missing path query")
            data, _content_type = await self.remote_adapter.get_artifact_file(remote_path)
            target.write_bytes(data)
            return target
        if value.startswith("/files/"):
            source = files_root() / value.removeprefix("/files/")
            shutil.copyfile(source, target)
            return target
        if value.startswith(("http://", "https://")):
            request = urllib.request.Request(value, headers={"User-Agent": "FlowStudio/1.0"})
            with urllib.request.urlopen(request, timeout=120) as response:
                target.write_bytes(response.read())
            return target
        source = Path(value)
        if source.exists():
            shutil.copyfile(source, target)
            return target
        if value.startswith("/"):
            data, _content_type = await self.remote_adapter.get_artifact_file(value)
            target.write_bytes(data)
            return target
        raise ValueError(f"Mesh is not readable by render worker: {value}")

    def _render(
        self,
        mesh_path: Path,
        job_id: str,
        name: str,
        view: str,
        *,
        clay: bool = False,
    ) -> str:
        assert self.blender_bin is not None
        output = files_root() / "render" / job_id / name
        output.parent.mkdir(parents=True, exist_ok=True)
        script = output.parent / f"render_{name}.py"
        script.write_text(_blender_script(mesh_path, output, view, clay=clay), encoding="utf-8")
        completed = subprocess.run(
            [self.blender_bin, "--background", "--python", str(script)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "Blender render failed: "
                + (completed.stderr.strip() or completed.stdout.strip())[-1000:]
            )
        if not output.exists():
            raise RuntimeError("Blender render did not create an output image")
        return f"/files/render/{job_id}/{name}"

    def _metadata(self, operation: str) -> dict[str, object]:
        return {
            "engine": "blender",
            "blender_bin": self.blender_bin,
            "operation": operation,
            "camera_preset": "auto_object_fit",
            "lighting_preset": "studio_soft",
        }


def _blender_script(mesh_path: Path, output_path: Path, view: str, *, clay: bool = False) -> str:
    config = {
        "mesh_path": str(mesh_path),
        "output_path": str(output_path),
        "view": view,
        "clay": clay,
    }
    return textwrap.dedent(
        f"""
        import bpy, math, json
        from mathutils import Vector

        config = json.loads({json.dumps(json.dumps(config))})
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete()

        path = config["mesh_path"]
        if path.lower().endswith(".obj"):
            bpy.ops.wm.obj_import(filepath=path)
        elif path.lower().endswith((".glb", ".gltf")):
            bpy.ops.import_scene.gltf(filepath=path)
        else:
            raise RuntimeError("Unsupported render mesh format")

        objects = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
        if not objects:
            raise RuntimeError("No mesh objects imported")

        if config["clay"]:
            clay = bpy.data.materials.new(name="FlowStudio White Clay")
            clay.diffuse_color = (0.78, 0.81, 0.86, 1.0)
            clay.use_nodes = True
            principled = clay.node_tree.nodes.get("Principled BSDF")
            principled.inputs["Base Color"].default_value = (0.78, 0.81, 0.86, 1.0)
            principled.inputs["Roughness"].default_value = 0.82
            principled.inputs["Metallic"].default_value = 0.0
            for obj in objects:
                obj.data.materials.clear()
                obj.data.materials.append(clay)

        bpy.ops.object.select_all(action='DESELECT')
        for obj in objects:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = objects[0]

        min_corner = Vector((1e9, 1e9, 1e9))
        max_corner = Vector((-1e9, -1e9, -1e9))
        for obj in objects:
            for corner in obj.bound_box:
                world = obj.matrix_world @ Vector(corner)
                min_corner.x = min(min_corner.x, world.x)
                min_corner.y = min(min_corner.y, world.y)
                min_corner.z = min(min_corner.z, world.z)
                max_corner.x = max(max_corner.x, world.x)
                max_corner.y = max(max_corner.y, world.y)
                max_corner.z = max(max_corner.z, world.z)

        center = (min_corner + max_corner) * 0.5
        extent = max((max_corner - min_corner).length, 0.001)

        view = config["view"]
        if view == "front":
            camera_offset = Vector((0, -extent * 1.9, extent * 0.45))
        elif view == "side":
            camera_offset = Vector((extent * 1.9, 0, extent * 0.45))
        elif view == "back":
            camera_offset = Vector((0, extent * 1.9, extent * 0.45))
        else:
            camera_offset = Vector((extent * 1.35, -extent * 1.65, extent * 0.75))

        bpy.ops.object.camera_add(location=center + camera_offset)
        camera = bpy.context.object
        direction = center - camera.location
        camera.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
        camera.data.lens = 55
        bpy.context.scene.camera = camera

        front_position = camera.location + Vector((0, 0, extent * 0.25))
        bpy.ops.object.light_add(type='AREA', location=front_position)
        key = bpy.context.object
        key.name = 'FlowStudio saturated front key'
        key.data.energy = 780
        key.data.size = max(3.0, extent * 1.2)

        bpy.ops.object.light_add(type='POINT', location=(center.x - extent, center.y + extent, center.z + extent))
        fill = bpy.context.object
        fill.name = 'FlowStudio color fill'
        fill.data.energy = 90

        bpy.context.scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in [item.identifier for item in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items] else 'BLENDER_EEVEE'
        bpy.context.scene.render.resolution_x = 512
        bpy.context.scene.render.resolution_y = 512
        bpy.context.scene.render.film_transparent = False
        bpy.context.scene.world.color = (0.985, 0.99, 1.0)
        bpy.context.scene.view_settings.view_transform = 'Standard'
        bpy.context.scene.view_settings.look = 'Medium High Contrast'
        bpy.context.scene.view_settings.exposure = 0
        bpy.context.scene.view_settings.gamma = 1
        bpy.context.scene.render.image_settings.file_format = 'PNG'
        bpy.context.scene.render.filepath = config["output_path"]
        bpy.ops.render.render(write_still=True)
        """
    )
