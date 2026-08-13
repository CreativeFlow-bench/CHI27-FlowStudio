#!/usr/bin/env python3
"""Render front, side, and three-quarter PNGs for a GLB/OBJ without app deps."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def blender_script(mesh_path: Path, output_path: Path, view: str, clay_material: bool) -> str:
    config = {
        "mesh_path": str(mesh_path),
        "output_path": str(output_path),
        "view": view,
        "clay_material": clay_material,
    }
    return f"""
import bpy, json
from mathutils import Vector

config = json.loads({json.dumps(json.dumps(config))})
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

path = config["mesh_path"]
if path.lower().endswith(".obj"):
    bpy.ops.wm.obj_import(filepath=path)
else:
    bpy.ops.import_scene.gltf(filepath=path)

objects = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
if not objects:
    raise RuntimeError("No mesh objects imported")

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
else:
    camera_offset = Vector((extent * 1.35, -extent * 1.65, extent * 0.75))

bpy.ops.object.camera_add(location=center + camera_offset)
camera = bpy.context.object
direction = center - camera.location
camera.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
camera.data.lens = 68
bpy.context.scene.camera = camera

if config.get("clay_material"):
    clay = bpy.data.materials.new(name="creativeflow_clay_preview")
    clay.use_nodes = True
    bsdf = clay.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.38, 0.38, 0.38, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.64
    clay.diffuse_color = (0.38, 0.38, 0.38, 1.0)
    for obj in objects:
        obj.data.materials.clear()
        obj.data.materials.append(clay)
else:
    for obj in objects:
        if not obj.data.materials:
            mat = bpy.data.materials.new(name="neutral_gray")
            mat.diffuse_color = (0.72, 0.72, 0.72, 1.0)
            obj.data.materials.append(mat)

bpy.ops.object.light_add(type='AREA', location=camera.location + Vector((0, 0, extent * 0.25)))
key = bpy.context.object
key.data.energy = 520 if config.get("clay_material") else 1800
key.data.size = max(3.0, extent * 1.2)
bpy.ops.object.light_add(type='AREA', location=(center.x + extent, center.y - extent, center.z + extent))
fill = bpy.context.object
fill.data.energy = 120 if config.get("clay_material") else 700
fill.data.size = max(2.0, extent)

engine_items = bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items
engine_ids = {{item.identifier for item in engine_items}}
if 'BLENDER_EEVEE' in engine_ids:
    bpy.context.scene.render.engine = 'BLENDER_EEVEE'
elif 'BLENDER_EEVEE_NEXT' in engine_ids:
    bpy.context.scene.render.engine = 'BLENDER_EEVEE_NEXT'

bpy.context.scene.render.resolution_x = 512
bpy.context.scene.render.resolution_y = 512
bpy.context.scene.render.film_transparent = False
if hasattr(bpy.context.scene, "eevee"):
    eevee = bpy.context.scene.eevee
    if hasattr(eevee, "use_gtao"):
        eevee.use_gtao = False
if hasattr(bpy.context.scene, "eevee_next"):
    eevee_next = bpy.context.scene.eevee_next
    if hasattr(eevee_next, "use_gtao"):
        eevee_next.use_gtao = False
world = bpy.context.scene.world
world.use_nodes = True
background = world.node_tree.nodes.get('Background')
if background:
    background.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0)
    background.inputs['Strength'].default_value = 1.0
bpy.context.scene.view_settings.view_transform = 'Standard'
bpy.context.scene.view_settings.exposure = 0.0
bpy.context.scene.view_settings.gamma = 1.0
bpy.context.scene.render.image_settings.file_format = 'PNG'
bpy.context.scene.render.filepath = config["output_path"]
bpy.ops.render.render(write_still=True)
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mesh", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--blender", default="/root/autodl-tmp/blender/blender-5.0.0-linux-x64/blender")
    parser.add_argument(
        "--clay-material",
        action="store_true",
        help="Override mesh materials with neutral gray for shape-only silhouette QA.",
    )
    args = parser.parse_args()

    mesh = Path(args.mesh)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = {}
    for view in ("front", "side", "three_quarter"):
        output = out_dir / f"{view}.png"
        script = out_dir / f"render_{view}.py"
        script.write_text(blender_script(mesh, output, view, args.clay_material), encoding="utf-8")
        log = out_dir / f"{view}.log"
        completed = subprocess.run(
            [args.blender, "--background", "--python", str(script)],
            stdout=log.open("w", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            text=True,
            timeout=240,
        )
        if completed.returncode != 0 or not output.is_file():
            raise RuntimeError(f"Blender render failed for {view}; see {log}")
        outputs[view] = str(output)
    (out_dir / "renders.json").write_text(json.dumps(outputs, indent=2), encoding="utf-8")
    print(json.dumps(outputs, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
