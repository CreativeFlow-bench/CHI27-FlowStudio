#!/usr/bin/env python3
"""Assemble one auditable Source → three CreativeFlow variation case board."""

from __future__ import annotations

import argparse
import json
import textwrap
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps


STAGES = [
    ("low_fidelity", "LOW FIDELITY", "GLOBAL FORM · silhouette / proportion / mass", "#ff8a2b"),
    ("part", "PART", "LOCAL COMPONENT · SAM3D-selected nose only", "#438ee8"),
    ("texture", "TEXTURE", "SURFACE · material / color / PBR response", "#8657e8"),
]
VIEWS = [("front", "FRONT"), ("side", "SIDE"), ("three_quarter", "3/4")]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for candidate in candidates:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int, fill: str, outline: str | None = None, width: int = 1) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def fit_image(path: str | Path, size: tuple[int, int]) -> Image.Image:
    image = Image.open(path).convert("RGB")
    return ImageOps.contain(image, size, Image.Resampling.LANCZOS)


def paste_center(canvas: Image.Image, image: Image.Image, box: tuple[int, int, int, int], background: str = "#f1f3f7") -> None:
    x1, y1, x2, y2 = box
    panel = Image.new("RGB", (x2 - x1, y2 - y1), background)
    panel.paste(image, ((panel.width - image.width) // 2, (panel.height - image.height) // 2))
    canvas.paste(panel, (x1, y1))


def short(value: Any, width: int = 42) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= width else text[: width - 1].rstrip() + "…"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--source-image", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if payload.get("status") != "completed":
        raise RuntimeError("batch manifest must be completed")
    groups: dict[str, list[dict[str, Any]]] = {stage: [] for stage, *_ in STAGES}
    source_item: dict[str, Any] | None = None
    for item in payload.get("items", []):
        stage = str(item.get("job", {}).get("stage") or "")
        if stage == "source":
            source_item = item
        elif stage in groups:
            groups[stage].append(item)
    for stage, items in groups.items():
        if len(items) != 4:
            raise RuntimeError(f"case board requires four {stage} items, got {len(items)}")
    if not source_item:
        raise RuntimeError("case board manifest has no source item")
    for item in [source_item, *[entry for items in groups.values() for entry in items]]:
        paths = item.get("render_paths") or {}
        if any(not Path(str(paths.get(name) or "")).is_file() for name, _ in VIEWS):
            raise RuntimeError(f"missing three-view renders for {item.get('work_dir')}")
        if not item.get("meta", {}).get("pbr_validation", {}).get("passed"):
            raise RuntimeError(f"unvalidated PBR item in board: {item.get('work_dir')}")

    width, header_h, source_w, card_w, row_h = 4600, 190, 610, 955, 800
    margin, gap = 40, 22
    height = header_h + len(STAGES) * row_h + margin
    canvas = Image.new("RGB", (width, height), "#f5f7fb")
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, 30), "CreativeFlow · Three Variation Levels", font=font(54, True), fill="#181b24")
    draw.text(
        (margin, 102),
        "One snowman source · relation-first KG expansion · 2 near + 2 far per level · real Hunyuan3D 2.1 PBR meshes",
        font=font(25),
        fill="#596174",
    )

    source_x1, source_y1 = margin, header_h
    source_x2, source_y2 = margin + source_w, height - margin
    rounded(draw, (source_x1, source_y1, source_x2, source_y2), 24, "#ffffff", "#d8dce6", 2)
    draw.text((source_x1 + 28, source_y1 + 24), "SOURCE", font=font(30, True), fill="#222733")
    draw.text((source_x1 + 28, source_y1 + 66), "snowman_shared_source_v1", font=font(18), fill="#747d91")
    source_image = fit_image(args.source_image, (source_w - 56, 500))
    paste_center(canvas, source_image, (source_x1 + 28, source_y1 + 110, source_x2 - 28, source_y1 + 610), "#e9eef5")
    draw.text((source_x1 + 28, source_y1 + 628), "Original three-view PBR mesh", font=font(20, True), fill="#303747")
    sy = source_y1 + 680
    for view_name, view_label in VIEWS:
        image = fit_image(source_item["render_paths"][view_name], (source_w - 56, 500))
        paste_center(canvas, image, (source_x1 + 28, sy, source_x2 - 28, sy + 500), "#edf0f5")
        rounded(draw, (source_x1 + 42, sy + 18, source_x1 + 142, sy + 55), 10, "#ffffff")
        draw.text((source_x1 + 58, sy + 25), view_label, font=font(15, True), fill="#555d6d")
        sy += 540

    cards_x = source_x2 + gap
    for row, (stage, label, subtitle, color) in enumerate(STAGES):
        y1 = header_h + row * row_h
        y2 = y1 + row_h - gap
        rounded(draw, (cards_x, y1, width - margin, y2), 24, "#ffffff", "#d8dce6", 2)
        rounded(draw, (cards_x + 20, y1 + 18, cards_x + 250, y1 + 70), 14, color)
        draw.text((cards_x + 38, y1 + 28), label, font=font(23, True), fill="#ffffff")
        draw.text((cards_x + 275, y1 + 31), subtitle, font=font(20, True), fill="#3f4655")
        for column, item in enumerate(groups[stage]):
            x1 = cards_x + 20 + column * card_w
            x2 = x1 + card_w - gap
            card_y1, card_y2 = y1 + 90, y2 - 20
            rounded(draw, (x1, card_y1, x2, card_y2), 16, "#fafbfe", "#e1e4eb", 1)
            job = item.get("job") or {}
            relation = job.get("candidate_relation") or {}
            bucket = str(job.get("distance_bucket") or "").upper()
            badge_color = "#35a66f" if bucket == "NEAR" else "#cc5b67"
            rounded(draw, (x1 + 18, card_y1 + 16, x1 + 105, card_y1 + 52), 10, badge_color)
            draw.text((x1 + 34, card_y1 + 23), bucket, font=font(14, True), fill="#ffffff")
            draw.text((x1 + 122, card_y1 + 17), short(job.get("anchor"), 34), font=font(22, True), fill="#222733")
            predicate = short(relation.get("predicate") or "relation path", 54)
            draw.text((x1 + 18, card_y1 + 58), f"source —{predicate}→ target", font=font(15), fill="#687186")
            panel_top, panel_bottom = card_y1 + 96, card_y2 - 76
            panel_gap = 10
            panel_w = (x2 - x1 - 36 - 2 * panel_gap) // 3
            for view_index, (view_name, view_label) in enumerate(VIEWS):
                px1 = x1 + 18 + view_index * (panel_w + panel_gap)
                px2 = px1 + panel_w
                image = fit_image(item["render_paths"][view_name], (panel_w, panel_bottom - panel_top))
                paste_center(canvas, image, (px1, panel_top, px2, panel_bottom), "#edf0f5")
                rounded(draw, (px1 + 10, panel_top + 10, px1 + 78, panel_top + 38), 8, "#ffffff")
                draw.text((px1 + 20, panel_top + 15), view_label, font=font(11, True), fill="#555d6d")
            pbr = item.get("meta", {}).get("pbr_validation") or {}
            footer = (
                f"GLB + OBJ · BaseColor + Metallic/Roughness · "
                f"{pbr.get('material_count', 0)} material · PBR VERIFIED"
            )
            draw.text((x1 + 18, card_y2 - 52), footer, font=font(13, True), fill="#586174")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, quality=95)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
