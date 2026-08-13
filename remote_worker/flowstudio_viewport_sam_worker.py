from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


def main() -> int:
    parser = argparse.ArgumentParser(description="FlowStudio viewport point-prompt SAM worker")
    parser.add_argument("--image", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--point-x", type=float, required=True)
    parser.add_argument("--point-y", type=float, required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--model-type", default="vit_h")
    parser.add_argument("--manifest", default="viewport_sam_manifest.json")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / args.manifest
    try:
        result = segment_viewport(args, out_dir)
        manifest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        result = {
            "adapter": "viewport_sam",
            "status": "failed",
            "error": str(exc),
            "mask_path": None,
        }
        manifest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2


def segment_viewport(args: argparse.Namespace, out_dir: Path) -> dict[str, Any]:
    import torch
    from segment_anything import SamPredictor, sam_model_registry

    image_path = Path(args.image)
    checkpoint = Path(args.checkpoint)
    if not image_path.exists():
        raise FileNotFoundError(f"Missing viewport image: {image_path}")
    if not checkpoint.exists():
        raise FileNotFoundError(f"Missing SAM checkpoint: {checkpoint}")

    image = Image.open(image_path).convert("RGB")
    width, height = image.size
    x = args.point_x * width if 0 <= args.point_x <= 1 else args.point_x
    y = args.point_y * height if 0 <= args.point_y <= 1 else args.point_y
    x = float(np.clip(x, 0, width - 1))
    y = float(np.clip(y, 0, height - 1))

    device = "cuda" if torch.cuda.is_available() else "cpu"
    sam = sam_model_registry[args.model_type](checkpoint=str(checkpoint))
    sam.to(device=device)
    predictor = SamPredictor(sam)
    predictor.set_image(np.asarray(image))
    masks, scores, logits = predictor.predict(
        point_coords=np.asarray([[x, y]], dtype=np.float32),
        point_labels=np.asarray([1], dtype=np.int32),
        multimask_output=True,
    )
    best = int(np.argmax(scores))
    mask = masks[best].astype(np.uint8) * 255
    mask_path = out_dir / "mask.png"
    overlay_path = out_dir / "overlay.png"
    Image.fromarray(mask, mode="L").save(mask_path)
    rgba = image.convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 220, 255, 0))
    overlay.putalpha(Image.fromarray((mask * 0.42).astype(np.uint8), mode="L"))
    Image.alpha_composite(rgba, overlay).save(overlay_path)
    ys, xs = np.where(mask > 0)
    bbox = None
    if len(xs) and len(ys):
        bbox = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
    return {
        "adapter": "viewport_sam",
        "status": "completed",
        "image_path": str(image_path),
        "image_size": [width, height],
        "point": {"x": x, "y": y, "input_x": args.point_x, "input_y": args.point_y},
        "mask_path": str(mask_path),
        "overlay_path": str(overlay_path),
        "mask_area_px": int(mask.sum() // 255),
        "mask_coverage": float((mask > 0).mean()),
        "bbox": bbox,
        "score": float(scores[best]),
        "all_scores": [float(value) for value in scores],
        "device": device,
        "note": "2D viewport mask only; project to mesh before treating it as a stable 3D part.",
    }


if __name__ == "__main__":
    raise SystemExit(main())
