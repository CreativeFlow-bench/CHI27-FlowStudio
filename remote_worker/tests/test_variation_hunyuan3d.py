from __future__ import annotations

import json
import struct
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from run_variation_hunyuan3d_batch import bind_obj_pbr_material, inspect_glb_pbr  # noqa: E402


def write_glb(path: Path, document: dict) -> None:
    encoded = json.dumps(document, separators=(",", ":")).encode("utf-8")
    encoded += b" " * ((4 - len(encoded) % 4) % 4)
    total = 12 + 8 + len(encoded)
    path.write_bytes(
        struct.pack("<4sII", b"glTF", 2, total)
        + struct.pack("<I4s", len(encoded), b"JSON")
        + encoded
    )


def test_inspect_glb_requires_basecolor_and_metallic_roughness(tmp_path: Path) -> None:
    glb = tmp_path / "mesh.glb"
    write_glb(
        glb,
        {
            "asset": {"version": "2.0"},
            "materials": [
                {
                    "pbrMetallicRoughness": {
                        "baseColorTexture": {"index": 0},
                        "metallicRoughnessTexture": {"index": 1},
                    }
                }
            ],
            "textures": [{"source": 0}, {"source": 1}],
            "images": [{"uri": "base.png"}, {"uri": "mr.png"}],
        },
    )
    result = inspect_glb_pbr(glb)
    assert result["passed"] is True
    assert result["base_color_texture_bound"] is True
    assert result["metallic_roughness_texture_bound"] is True


def test_bind_obj_uses_paintpbr_maps(tmp_path: Path) -> None:
    (tmp_path / "mesh.obj").write_text(
        "mtllib mesh.mtl\nv 0 0 0\nvt 0 0\nusemtl ImportedMaterial\nf 1/1 1/1 1/1\n",
        encoding="utf-8",
    )
    (tmp_path / "mesh_pbr.mtl").write_text(
        "newmtl Material\nmap_Kd mesh_pbr.jpg\nmap_Pm mesh_pbr_metallic.jpg\nmap_Pr mesh_pbr_roughness.jpg\n",
        encoding="utf-8",
    )
    for name in ("mesh_pbr.jpg", "mesh_pbr_metallic.jpg", "mesh_pbr_roughness.jpg"):
        (tmp_path / name).write_bytes(b"x" * 2048)
    result = bind_obj_pbr_material(tmp_path)
    assert result["passed"] is True
    assert result["material_name"] == "ImportedMaterial"
    assert (tmp_path / "mesh.mtl").read_text(encoding="utf-8").startswith(
        "newmtl ImportedMaterial"
    )
