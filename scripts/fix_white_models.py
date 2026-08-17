import json
import os
import shutil
from pathlib import Path

root = Path("/Users/bytedance/Desktop/creative flow/CHI27-FlowStudio")
src_dir = root / "whiteModel"
dest_dir = root / "backend/storage/files/white-models"

dest_dir.mkdir(parents=True, exist_ok=True)

# Link extracted models
extracted_src = src_dir / "extracted"
extracted_dest = dest_dir / "extracted"
if not extracted_dest.exists():
    os.symlink(extracted_src, extracted_dest)

# Parse the source manifest
src_manifest = json.loads((src_dir / "WHITE_MODEL_CONTENT_MANIFEST.json").read_text())

dest_manifest = {
    "assets": [],
    "quarantined_assets": [
        {
            "benchmark_id": "white:christmas:chimney",
            "reason": "high-poly over 500k faces"
        },
        {
            "benchmark_id": "white:toy_animals:toy-animal-collection-07",
            "reason": "high-poly and caused browser timeout"
        }
    ]
}

for asset in src_manifest.get("assets", []):
    if asset.get("status") == "active_model" and asset.get("path", "").endswith(".obj"):
        path = asset["path"]
        # path is like "whiteModel/extracted/bakery/Croissant.obj"
        rel_path = path.replace("whiteModel/", "")
        
        category = asset["category"]
        name = asset["name"]
        
        dest_manifest["assets"].append({
            "benchmark_id": f"white:{category}:{name.replace(' ', '-').lower()}",
            "label": name,
            "category": category,
            "object_type": name.lower(),
            "obj_url": f"/files/white-models/{rel_path}",
            "file_size_bytes": asset.get("file_size_bytes", 0)
        })

(dest_dir / "manifest.json").write_text(json.dumps(dest_manifest, indent=2))
print("Fixed white models manifest and created symlinks.")
