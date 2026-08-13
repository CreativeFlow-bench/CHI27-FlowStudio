from __future__ import annotations

import argparse
import io
import json
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw


def get_json(url: str) -> dict:
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
        url, timeout=15
    ) as response:
        return json.loads(response.read().decode("utf-8"))


def post_png(url: str, payload: dict, output: Path, timeout: int = 1800) -> None:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
        request, timeout=timeout
    ) as response:
        raw = response.read()
        if response.headers.get_content_type() != "image/png":
            raise RuntimeError(f"unexpected content type: {response.headers}")
    with Image.open(io.BytesIO(raw)) as image:
        image.verify()
    output.write_bytes(raw)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smoke-test Qwen-Image-2512 and Qwen-Image-Edit-2511."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:18082")
    parser.add_argument("--source-image", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=("generate", "edit", "all"),
        default="all",
    )
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    health = get_json(args.base_url.rstrip("/") + "/health")
    if not health.get("ok"):
        raise RuntimeError(f"image service is unhealthy: {health}")

    common = {
        "width": 512,
        "height": 512,
        "num_inference_steps": 8,
        "true_cfg_scale": 3.5,
        "max_sequence_length": 256,
        "seed": 20260730,
    }
    outputs: list[str] = []

    if args.mode in {"generate", "all"}:
        output = args.out_dir / "qwen_image_2512_smoke.png"
        post_png(
            args.base_url.rstrip("/") + "/generate",
            {
                **common,
                "prompt": (
                    "A single friendly snowman product figurine, rounded three-layer "
                    "body, knitted hat and scarf, clean white studio background, "
                    "centered front three-quarter view, no text"
                ),
            },
            output,
        )
        outputs.append(str(output))

    if args.mode in {"edit", "all"}:
        source = Image.open(args.source_image).convert("RGB").resize((512, 512))
        source_path = args.out_dir / "edit_source.png"
        source.save(source_path)
        mask = Image.new("L", source.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((145, 30, 370, 205), fill=255)
        mask_path = args.out_dir / "edit_mask.png"
        mask.save(mask_path)

        conditioned = args.out_dir / "qwen_image_edit_2511_smoke.png"
        post_png(
            args.base_url.rstrip("/") + "/generate-conditioned",
            {
                **common,
                "prompt": (
                    "Keep the same snowman and composition. Make the knitted hat "
                    "softer, rounder, and slightly more playful; preserve the body."
                ),
                "source_image_path": str(source_path),
                "mode": "img2img",
                "strength": 0.6,
            },
            conditioned,
        )
        outputs.append(str(conditioned))

        masked = args.out_dir / "qwen_image_edit_2511_masked_smoke.png"
        post_png(
            args.base_url.rstrip("/") + "/generate-masked",
            {
                **common,
                "prompt": (
                    "Change the hat into a soft mint-green knitted hat with a round "
                    "pom-pom. Keep all unselected parts unchanged."
                ),
                "source_image_path": str(source_path),
                "mask_image_path": str(mask_path),
                "mode": "inpaint",
                "strength": 0.6,
            },
            masked,
        )
        outputs.append(str(masked))

    print(json.dumps({"ok": True, "health": health, "outputs": outputs}, indent=2))


if __name__ == "__main__":
    main()
