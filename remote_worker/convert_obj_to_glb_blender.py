#!/usr/bin/env python3
"""Convert OBJ/MTL assets to GLB using Blender in background mode."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def blender_script(obj_path: Path, glb_path: Path) -> str:
    payload = json.dumps({"obj_path": str(obj_path), "glb_path": str(glb_path)})
    return f"""
import bpy, json
config = json.loads({payload!r})
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
bpy.ops.wm.obj_import(filepath=config["obj_path"])
bpy.ops.object.select_all(action='SELECT')
for obj in bpy.context.selected_objects:
    if obj.type == 'MESH':
        bpy.context.view_layer.objects.active = obj
bpy.ops.export_scene.gltf(
    filepath=config["glb_path"],
    export_format='GLB',
    export_materials='EXPORT',
    export_image_format='AUTO',
)
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--obj", required=True)
    parser.add_argument("--glb", required=True)
    parser.add_argument("--blender", default="/root/autodl-tmp/blender/blender-5.0.0-linux-x64/blender")
    args = parser.parse_args()

    obj_path = Path(args.obj).resolve()
    glb_path = Path(args.glb).resolve()
    glb_path.parent.mkdir(parents=True, exist_ok=True)
    script_path = glb_path.with_suffix(".convert.py")
    log_path = glb_path.with_suffix(".convert.log")
    script_path.write_text(blender_script(obj_path, glb_path), encoding="utf-8")
    completed = subprocess.run(
        [args.blender, "--background", "--python", str(script_path)],
        stdout=log_path.open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        text=True,
        timeout=300,
    )
    if completed.returncode != 0 or not glb_path.is_file():
        raise RuntimeError(f"Blender conversion failed; see {log_path}")
    print(json.dumps({"obj": str(obj_path), "glb": str(glb_path), "log": str(log_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
