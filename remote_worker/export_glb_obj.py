#!/usr/bin/env python3
"""Blender-side GLB to OBJ/MTL export used by the variation PBR packager."""

from __future__ import annotations

import sys
from pathlib import Path

import bpy


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(argv) != 2:
        raise SystemExit("usage: blender --background --python export_glb_obj.py -- INPUT.glb OUTPUT.obj")
    source = Path(argv[0]).resolve()
    output = Path(argv[1]).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(source))
    mesh_objects = [item for item in bpy.context.scene.objects if item.type == "MESH"]
    if not mesh_objects:
        raise RuntimeError(f"GLB contains no mesh objects: {source}")
    for item in bpy.context.scene.objects:
        item.select_set(item in mesh_objects)
    bpy.context.view_layer.objects.active = mesh_objects[0]
    bpy.ops.wm.obj_export(
        filepath=str(output),
        export_selected_objects=True,
        export_materials=True,
        path_mode="COPY",
    )
    if not output.is_file() or output.stat().st_size <= 1024:
        raise RuntimeError(f"OBJ export failed: {output}")


if __name__ == "__main__":
    main()
