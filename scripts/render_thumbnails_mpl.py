import json
import os
import sys
import subprocess
from pathlib import Path

try:
    import trimesh
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    HAS_LIBS = True
except ImportError:
    HAS_LIBS = False

def install_libs():
    print("Installing trimesh and matplotlib...")
    subprocess.run([sys.executable, "-m", "pip", "install", "trimesh", "matplotlib"])

def render_obj_mpl(obj_path, out_path):
    try:
        import trimesh
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
        mesh = trimesh.load(obj_path, force='mesh')
        if isinstance(mesh, trimesh.Scene):
            geom = list(mesh.geometry.values())
            if not geom: return False
            mesh = geom[0] if len(geom) == 1 else trimesh.util.concatenate(geom)
            
        fig = plt.figure(figsize=(2.56, 2.56), dpi=100)
        ax = fig.add_subplot(111, projection='3d')
        
        # Plot vertices (simplest rendering without taking too long)
        # For a better look, we can plot the faces
        vertices = mesh.vertices
        faces = mesh.faces
        
        # Subsample faces if too large to render fast
        if len(faces) > 5000:
            import numpy as np
            indices = np.random.choice(len(faces), 5000, replace=False)
            faces = faces[indices]
            
        mesh_3d = Poly3DCollection(vertices[faces], alpha=0.8, facecolor='#c0c0c8', edgecolor='none')
        ax.add_collection3d(mesh_3d)
        
        # Auto scale
        scale = mesh.vertices.flatten()
        ax.auto_scale_xyz(scale, scale, scale)
        
        ax.view_init(elev=20, azim=45)
        ax.axis('off')
        
        plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
        fig.savefig(out_path, transparent=True, facecolor='#f5f5fa')
        plt.close(fig)
        return True
    except Exception as e:
        print(f"Error rendering {obj_path}: {e}")
        return False

def main():
    if not HAS_LIBS:
        install_libs()
        import trimesh
        import matplotlib.pyplot as plt
        
    root = Path(__file__).resolve().parent.parent
    dest_dir = root / "backend/storage/files/white-models"
    manifest_path = dest_dir / "manifest.json"
    
    if not manifest_path.exists():
        print("Manifest not found.")
        return
        
    manifest = json.loads(manifest_path.read_text())
    
    for asset in manifest.get("assets", []):
        obj_url = asset.get("obj_url")
        if not obj_url: continue
        
        rel_path = obj_url.replace("/files/white-models/", "")
        obj_path = dest_dir / rel_path
        
        if not obj_path.exists():
            continue
            
        thumbnail_path = obj_path.with_suffix('.jpg')
        
        if not thumbnail_path.exists():
            print(f"Rendering thumbnail for {obj_path.name}...")
            success = render_obj_mpl(str(obj_path), str(thumbnail_path))
            if success:
                asset['thumbnail_url'] = obj_url.replace('.obj', '.jpg')
        else:
            asset['thumbnail_url'] = obj_url.replace('.obj', '.jpg')
            
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print("Thumbnails generated via matplotlib.")

if __name__ == "__main__":
    main()
