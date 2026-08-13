#!/usr/bin/env python3
"""Qwen-Image smoke test: generate N images and save them locally on the host.

Runs against the loopback Qwen-Image service (CF_QWEN_IMAGE_URL, default
http://127.0.0.1:18082/generate) and writes PNGs under --out-dir.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_PROMPTS = [
    "a single classic paper lantern with red silk body and wooden frame, centered, pure white background, 3/4 view, high detail, no text",
    "a single ceramic teapot with glazed blue finish and curved spout, centered, pure white background, 3/4 view, high detail",
    "a single white sneaker with chunky sole and laces, centered, pure white background, side 3/4 view, high detail",
    "a single mushroom with red cap and white dots on a small mossy base, centered, pure white background, 3/4 view, high detail",
    "a single cartoon owl with large eyes, round body, tiny wings, centered, pure white background, 3/4 view, high detail",
    "a single vintage bicycle with basket and curved handlebars, centered, pure white background, side 3/4 view, high detail",
    "a single acoustic guitar with wooden body and sound hole, centered, pure white background, front 3/4 view, high detail",
    "a single pineapple with spiky crown and textured skin, centered, pure white background, 3/4 view, high detail",
    "a single friendly robot with rounded head and antenna, centered, pure white background, 3/4 view, high detail",
    "a single blooming flower with layered petals and green stem, centered, pure white background, 3/4 view, high detail",
]


def generate_one(
    url: str,
    prompt: str,
    out_path: Path,
    *,
    width: int,
    height: int,
    steps: int,
    seed: int,
) -> float:
    payload = {
        "prompt": prompt,
        "width": width,
        "height": height,
        "num_inference_steps": steps,
        "seed": seed,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.time()
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
        request, timeout=300
    ) as response:
        out_path.write_bytes(response.read())
    return time.time() - started


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="/root/flowstudio_app/outputs/qwen_smoke_10")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=512)
    parser.add_argument("--steps", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--url", default=os.getenv("CF_QWEN_IMAGE_URL", "http://127.0.0.1:18082/generate"))
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prompts = DEFAULT_PROMPTS[: args.count]
    for index, prompt in enumerate(prompts, start=1):
        slug = "".join(
            ch for ch in prompt.split(" with ")[0].replace("a single ", "").replace(" ", "_") if ch.isalnum() or ch == "_"
        )[:32] or f"image_{index:02d}"
        out_path = out_dir / f"{index:02d}_{slug}.png"
        seed = args.seed + index * 101
        print(f"[qwen-smoke] {index}/{len(prompts)} {slug} seed={seed} ...", flush=True)
        elapsed = generate_one(
            args.url,
            prompt,
            out_path,
            width=args.width,
            height=args.height,
            steps=args.steps,
            seed=seed,
        )
        print(f"  -> OK {elapsed:.1f}s {out_path.stat().st_size} bytes", flush=True)
    print(f"[qwen-smoke] done: {out_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
