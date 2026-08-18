import json
import os
import sys
from pathlib import Path
try:
    import trimesh
    import pyrender
    import numpy as np
    from PIL import Image
    HAS_LIBS = True
except ImportError:
    HAS_LIBS = False

def install_libs():
    print("Installing dependencies (trimesh, pyrender, Pillow)...")
    os.system(f"{sys.executable} -m pip install trimesh pyrender Pillow pyglet")

def render_obj(obj_path, out_path):
    # Setup scene
    mesh = trimesh.load(obj_path, force='mesh')
    if isinstance(mesh, trimesh.Scene):
        if not mesh.geometry:
            return False
        # Merge if scene
        geom = list(mesh.geometry.values())
        if not geom: return False
        mesh = geom[0] if len(geom) == 1 else trimesh.util.concatenate(geom)
    
    # Center and scale
    mesh.apply_translation(-mesh.centroid)
    mesh.apply_scale(1.0 / np.max(mesh.extents))
    
    # Material (Light gray)
    mesh.visual.vertex_colors = np.array([200, 200, 210, 255], dtype=np.uint8)
    
    pyr_mesh = pyrender.Mesh.from_trimesh(mesh, smooth=True)
    scene = pyrender.Scene(bg_color=[245, 245, 250, 255])
    scene.add(pyr_mesh)
    
    # Camera
    camera = pyrender.PerspectiveCamera(yfov=np.pi / 3.0, aspectRatio=1.0)
    camera_pose = np.array([
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 0.866, 0.5, 1.2],
        [0.0, -0.5, 0.866, 1.5],
        [0.0, 0.0, 0.0, 1.0],
    ])
    scene.add(camera, pose=camera_pose)
    
    # Light
    light = pyrender.DirectionalLight(color=np.ones(3), intensity=3.0)
    scene.add(light, pose=camera_pose)
    
    # Render
    # Use EGL or OSMesa backend if possible.
    try:
        os.environ['PYOPENGL_PLATFORM'] = 'egl'
        r = pyrender.OffscreenRenderer(256, 256)
        color, _ = r.render(scene)
        r.delete()
        Image.fromarray(color).save(out_path)
        return True
    except Exception as e:
        print(f"Render error for {obj_path}: {e}")
        return False

def main():
    if not HAS_LIBS:
        install_libs()
        print("Please re-run this script now that libraries are installed.")
        return
        
    root = Path(__file__).resolve().parent.parent
    dest_dir = root / "backend/storage/files/white-models"
    manifest_path = dest_dir / "manifest.json"
    
    if not manifest_path.exists():
        print("Manifest not found. Make sure fix_white_models.py has been run.")
        return
        
    manifest = json.loads(manifest_path.read_text())
    
    for asset in manifest.get("assets", []):
        obj_url = asset.get("obj_url")
        if not obj_url: continue
        
        # /files/white-models/... -> backend/storage/files/white-models/...
        rel_path = obj_url.replace("/files/white-models/", "")
        obj_path = dest_dir / rel_path
        
        if not obj_path.exists() or not str(obj_path).endswith('.obj'):
            continue
            
        thumbnail_path = obj_path.with_suffix('.jpg')
        
        if not thumbnail_path.exists():
            print(f"Rendering thumbnail for {obj_path.name}...")
            success = render_obj(str(obj_path), str(thumbnail_path))
            if success:
                asset['thumbnail_url'] = obj_url.replace('.obj', '.jpg')
        else:
            asset['thumbnail_url'] = obj_url.replace('.obj', '.jpg')
            
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print("Thumbnails generated and manifest updated.")

if __name__ == "__main__":
    main()
