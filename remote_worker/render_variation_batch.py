#!/usr/bin/env python3
"""Render front, side and three-quarter views from textured GLB assets."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

from app import _blender_render_script


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--blender", default="/root/autodl-tmp/blender/blender-5.0.0-linux-x64/blender")
    parser.add_argument("--skip-upload", action="store_true")
    args = parser.parse_args()
    manifest_path = Path(args.manifest)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("status") != "completed":
        raise RuntimeError("Hunyuan3D batch manifest is not complete")
    for index, item in enumerate(payload["items"], start=1):
        work_dir = Path(item["work_dir"])
        mesh = work_dir / "mesh.glb"
        if not item.get("meta", {}).get("textured") or not mesh.is_file():
            raise RuntimeError(f"item lacks a textured GLB: {work_dir}")
        render_dir = work_dir / "renders"
        render_dir.mkdir(parents=True, exist_ok=True)
        views: dict[str, str] = {}
        for view in ("front", "side", "three_quarter"):
            output = render_dir / f"{view}.png"
            script = render_dir / f"render_{view}.py"
            script.write_text(_blender_render_script(mesh, output, view), encoding="utf-8")
            completed = subprocess.run(
                [args.blender, "--background", "--python", str(script)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=240,
            )
            if completed.returncode != 0 or not output.is_file():
                raise RuntimeError(f"Blender failed for {work_dir}/{view}: {completed.stdout[-1200:]}")
            rgb = np.asarray(Image.open(output).convert("RGB"), dtype=np.float32)
            colorfulness = float((rgb.max(axis=2) - rgb.min(axis=2)).mean() / 255.0)
            if output.stat().st_size <= 50_000 or colorfulness < 0.01:
                raise RuntimeError(
                    f"render is empty or effectively gray for {work_dir}/{view}: "
                    f"bytes={output.stat().st_size}, colorfulness={colorfulness:.4f}"
                )
            views[view] = str(output)
        item["render_paths"] = views
        item["render_validation"] = {
            name: {
                "bytes": Path(path).stat().st_size,
                "colorfulness": round(
                    float(
                        (
                            np.asarray(Image.open(path).convert("RGB"), dtype=np.float32).max(axis=2)
                            - np.asarray(Image.open(path).convert("RGB"), dtype=np.float32).min(axis=2)
                        ).mean()
                        / 255.0
                    ),
                    6,
                ),
            }
            for name, path in views.items()
        }
        if not args.skip_upload:
            import oss2

            required = ("OSS_ACCESS_KEY_ID", "OSS_ACCESS_KEY_SECRET", "OSS_ENDPOINT", "OSS_BUCKET")
            missing = [name for name in required if not os.getenv(name)]
            if missing:
                raise RuntimeError(f"OSS environment is missing: {', '.join(missing)}")
            bucket = oss2.Bucket(
                oss2.Auth(os.environ["OSS_ACCESS_KEY_ID"], os.environ["OSS_ACCESS_KEY_SECRET"]),
                os.environ["OSS_ENDPOINT"],
                os.environ["OSS_BUCKET"],
            )
            final_keys = item.get("meta", {}).get("final_oss_keys") or []
            glb_keys = [str(key) for key in final_keys if str(key).endswith("/mesh.glb")]
            if len(glb_keys) != 1:
                raise RuntimeError(f"cannot derive OSS render prefix for {work_dir}")
            prefix = glb_keys[0].rsplit("/", 1)[0]
            item["render_oss_keys"] = {}
            for name, path in views.items():
                key = f"{prefix}/renders/{name}.png"
                bucket.put_object_from_file(key, path)
                item["render_oss_keys"][name] = key
        manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[{index}/{len(payload['items'])}] rendered {work_dir.name}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
