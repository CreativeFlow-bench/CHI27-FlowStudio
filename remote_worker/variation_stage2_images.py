#!/usr/bin/env python3
"""Generate native image-to-image variations with Qwen-Image only.

Qwen2.5-VL has already composed the prompt from the source image and raw graph
target. Part can optionally use a real SAM3D projection mask through Qwen
inpainting. There is no SDXL, ControlNet, pixel compositing path, or image scorer.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path
from typing import Any

from PIL import Image


_IMAGE_PHASE_READY = False

MIN_BORDER_WHITE_RATIO = 0.95
MIN_SAFE_MARGIN_RATIO = 0.05
MIN_SUBJECT_RATIO = 0.10
MAX_SUBJECT_RATIO = 0.70


def normalize_generated_studio_background(path: Path) -> bool:
    """Turn a connected light neutral studio backdrop into flat white.

    Qwen occasionally returns a complete, well-framed object on a very light
    gray gradient.  Only pixels connected to the canvas edge are eligible, so
    light details and highlights inside the object are preserved.
    """
    image = Image.open(path).convert("RGB")
    width, height = image.size
    pixels = image.load()

    def is_light_neutral(px: tuple[int, int, int]) -> bool:
        return min(px) >= 210 and max(px) - min(px) <= 32

    edge_points: list[tuple[int, int]] = []
    for x in range(width):
        edge_points.extend(((x, 0), (x, height - 1)))
    for y in range(1, height - 1):
        edge_points.extend(((0, y), (width - 1, y)))

    queue = deque(edge_points)
    seen = set(edge_points)
    background: list[tuple[int, int]] = []
    while queue:
        x, y = queue.popleft()
        if not is_light_neutral(pixels[x, y]):
            continue
        background.append((x, y))
        for point in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            px, py = point
            if 0 <= px < width and 0 <= py < height and point not in seen:
                seen.add(point)
                queue.append(point)

    if not background:
        return False
    for point in background:
        pixels[point[0], point[1]] = (255, 255, 255)
    image.save(path)
    return True


def fit_generated_subject_safe_margin(
    path: Path,
    *,
    margin_ratio: float = 0.08,
) -> bool:
    """Normalize subject framing on a white canvas.

    - If the subject hugs the border, letterbox it inward to restore margin.
    - If the subject is tiny in a sea of white, crop and zoom it up so identity
      / catalog cards are not mostly empty studio space.
    """
    image = Image.open(path).convert("RGB")
    width, height = image.size
    if width < 2 or height < 2:
        return False

    def is_white(px: tuple[int, int, int]) -> bool:
        r, g, b = px
        return r >= 245 and g >= 245 and b >= 245 and max(r, g, b) - min(r, g, b) <= 10

    small = image.resize((128, 128))
    foreground = [
        (x, y)
        for y in range(128)
        for x in range(128)
        if not is_white(small.getpixel((x, y)))
    ]
    if not foreground:
        return False
    min_x = min(x for x, _ in foreground)
    min_y = min(y for _, y in foreground)
    max_x = max(x for x, _ in foreground)
    max_y = max(y for _, y in foreground)
    current_margin = min(min_x, min_y, 127 - max_x, 127 - max_y) / 128
    subject_width = max(1, max_x - min_x + 1)
    subject_height = max(1, max_y - min_y + 1)
    coverage = (subject_width * subject_height) / (128 * 128)

    # Zoom-in path: subject occupies too little of the canvas.
    if coverage < 0.28 or current_margin > 0.22:
        pad_x = max(1, int(subject_width * margin_ratio))
        pad_y = max(1, int(subject_height * margin_ratio))
        left = max(0, int((min_x - pad_x) * width / 128))
        top = max(0, int((min_y - pad_y) * height / 128))
        right = min(width, int((max_x + pad_x + 1) * width / 128))
        bottom = min(height, int((max_y + pad_y + 1) * height / 128))
        cropped = image.crop((left, top, right, bottom))
        fit = min(width / cropped.width, height / cropped.height) * (1.0 - 2.0 * margin_ratio)
        resized = cropped.resize(
            (max(1, round(cropped.width * fit)), max(1, round(cropped.height * fit))),
            Image.Resampling.LANCZOS,
        )
        canvas = Image.new("RGB", (width, height), (255, 255, 255))
        canvas.paste(
            resized,
            ((width - resized.width) // 2, (height - resized.height) // 2),
        )
        canvas.save(path)
        return True

    if current_margin >= margin_ratio:
        return False

    target_width = width * max(0.01, 1.0 - 2.0 * margin_ratio)
    target_height = height * max(0.01, 1.0 - 2.0 * margin_ratio)
    scale = min(
        1.0 - 2.0 * margin_ratio,
        target_width / (subject_width * width / 128),
        target_height / (subject_height * height / 128),
    )
    if scale >= 1.0:
        return False
    resized = image.resize(
        (max(1, round(width * scale)), max(1, round(height * scale))),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new("RGB", (width, height), (255, 255, 255))
    canvas.paste(resized, ((width - resized.width) // 2, (height - resized.height) // 2))
    canvas.save(path)
    return True


def ensure_image_phase() -> None:
    global _IMAGE_PHASE_READY
    if _IMAGE_PHASE_READY:
        return
    script = os.getenv("CF_MODEL_PHASE_SCRIPT", "").strip()
    if not script:
        return
    proc = subprocess.run(
        [script, "image"],
        capture_output=True,
        text=True,
        timeout=360,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"image model phase failed: {(proc.stderr or proc.stdout)[-2000:]}"
        )
    _IMAGE_PHASE_READY = True


def execution_prompt(stage: str, object_type: str, part_name: str, spec: dict[str, Any]) -> str:
    target = str(spec.get("graph_anchor") or spec.get("direction_title") or "alternative").strip()
    if stage == "low_fidelity":
        base = str(spec.get("prompt") or (
            f"生成一个{object_type}。把整体轮廓改成类似{target}的形状；"
            f"仍然清楚可识别为{object_type}的身份。纯白背景、无地面、无投影、单体。"
        )).strip()
        return (
            f"{base} Keep it recognizable as a {object_type}, but do not over-copy the source image pixels or "
            "its original round silhouette. Do not render the silhouette target as a separate object and do not introduce "
            "a new object category. Render as a single tangible "
            "3D asset in a clean three-quarter product-render view, with real volume, depth, PBR-like "
            "surface shading, and no 2D drawing style. The macro silhouette change must be clearly visible "
            "at thumbnail scale: square/blocky, triangular/conical, long vertical, flat wide, cylindrical, "
            "waisted, broad-base, or broad-top as requested by the Chinese prompt. It is a low-fidelity "
            "design-family variation: accessories, expression, small details, and slight palette differences may "
            "adapt naturally to the new silhouette as long as the object remains recognizable. "
            "If a source image is provided, use it only as loose identity reference, not as pixel-level structure control. "
            "Adjust width, height, length, large body shape, curve, taper, and outside massing boldly. "
            "Show the complete full-body object centered "
            "in frame with generous margins; no close-up crop, no cut-off hat, arms, base, or body. Fill every pixel outside the single "
            "object with flat RGB(255,255,255) white; no blue, gray, gradient, floor, horizon, "
            "environment, snow field, or cast shadow."
        )
    if stage == "part":
        base = str(spec.get("prompt") or "").strip()
        if base:
            if spec.get("minimal_prompt"):
                target_phrase = str(
                    spec.get("generation_phrase")
                    or spec.get("graph_anchor")
                    or spec.get("direction_title")
                    or target
                ).strip()
                selected = spec.get("selected_part") or {}
                part_label = str(selected.get("canonical_name") or part_name).strip()
                old_shape = str(selected.get("shape") or "").strip()
                old_color = str(selected.get("visible_color") or selected.get("color") or "").strip()
                old_material = str(selected.get("material") or "").strip()
                old_desc = ", ".join(x for x in [old_color, old_shape, old_material] if x)
                old_desc_sentence = (
                    f"The original {part_label} appearance ({old_desc}) must be completely gone. "
                    if old_desc
                    else f"The original {part_label} must be completely gone. "
                )
                semantic_role = str(selected.get("semantic_role") or "").strip()
                location_hint = str(
                    selected.get("image_location_hint")
                    or selected.get("visual_location_hint")
                    or selected.get("view_location_hint")
                    or ""
                ).strip()
                attachment = str(
                    selected.get("attachment")
                    or selected.get("attachment_socket")
                    or selected.get("socket")
                    or ""
                ).strip()
                scale_constraint = str(selected.get("scale_constraint") or selected.get("scale") or "").strip()
                anchor_text = " ".join([part_label, semantic_role, attachment]).lower()
                face_tokens = {"face", "facial", "eye", "eyes", "smile", "mouth", "nose"}
                anchor_words = set(token for token in re.findall(r"[a-zA-Z]+", anchor_text) if token)
                if anchor_words & face_tokens:
                    placement_sentence = (
                        f"The new {part_label} must be a real small 3D object physically embedded in the same socket, "
                        "centered between the two eyes and above the smile, protruding forward from the face. "
                    )
                    wrong_location_sentence = (
                        f"It must read as the {object_type}'s {part_label}, not as a sticker, badge, chest decoration, "
                        "hat decoration, handheld prop, second object, or background object. "
                    )
                else:
                    socket = attachment or f"the original {part_label} attachment point"
                    scale = scale_constraint or "matching the original local part scale"
                nozzle_tokens = {"nozzle", "outlet", "muzzle", "spout", "spray"}
                is_nozzle_like = bool(anchor_words & nozzle_tokens)
                is_aperture_rim_like = is_nozzle_like and (
                    "aperture" in anchor_words or "rim" in anchor_words or "opening" in anchor_words
                )
                if is_aperture_rim_like:
                    target_phrase = str(
                        spec.get("generation_phrase")
                        or spec.get("graph_anchor")
                        or spec.get("direction_title")
                        or target
                    ).strip()
                    location_sentence = f"Location: {location_hint}. " if location_hint else ""
                    return (
                        f"Use the provided source image as a strict reference. Create one clean 3D product-render image of the same {object_type}. "
                        f"Keep the entire toy water gun unchanged: same camera angle, same global silhouette, same blue body, same green tank, same orange barrel cylinder, "
                        "same trigger, grip, top ridges, side panels, proportions, lighting, and glossy toy-plastic style. "
                        f"Only modify the selected SAM3D part: {part_label}. {location_sentence}"
                        f"The modification must be physically built into the front circular opening/rim on the barrel axis: {target_phrase}. "
                        "Keep the surrounding orange nozzle cylinder and every unselected component exactly as in the source. "
                        "Do not place the donor shape on the side body, top, grip, tank, or background. "
                        "Do not add a separate prop, sticker, badge, flower, shell, hose, water stream, second nozzle, character face, eyes, mouth, or text. "
                        "The result should still instantly read as the same toy water gun; the only visible design variation is the local front aperture/rim geometry. "
                        "One complete object only, centered, full object visible, pure white RGB(255,255,255) background, no floor, no shadow, no scene."
                    )
                placement_sentence = (
                    f"The new {part_label} must be a real 3D local component attached at the same socket: {socket}. "
                    f"Keep its original connection direction, alignment, and scale constraints: {scale}. "
                    f"The target form must occupy the original visible {part_label} silhouette area and replace that protruding component itself; "
                    f"the old {part_label} must not remain unchanged next to it. "
                    f"Do not create anything outside the original {part_label} component volume except the required slight 3D thickness of the replacement itself. "
                )
                if is_nozzle_like:
                    location_sentence = (
                        f"Image-space location hint: {location_hint}. " if location_hint else ""
                    )
                    placement_sentence += (
                        f"The selected {part_label} is the frontmost outlet tip on the barrel axis. "
                        f"{location_sentence}"
                        "Change only that frontmost outlet tip/cylinder/rim, not the side body, not the water tank, not vents, not trigger, not grip, and not any rear or side accessory. "
                        "Keep the original body, water tank, barrel casing, trigger, grip, top ridges, side panels, and their original colors unchanged. "
                        "Do not add a hose, water stream, second nozzle, side-mounted donor object, extra rear tube, or decorative badge on the gun body. "
                    )
                wrong_location_sentence = (
                    f"It must read as the {object_type}'s functional {part_label}, not as a surface decoration, "
                    "not on the central body surface, not on the lid, not on the handle, not as a sticker, "
                    "separate prop, duplicate accessory, floating object, or background object. "
                )
                surface_only_sentence = (
                    f"If the candidate describes a tactile pattern, bumps, dimples, ridges, holes, scales, suction cups, beads, or woven detail, "
                    f"render those details as embedded surface features on the replacement {part_label} itself. "
                    "Do not add a dangling appendage, tail, tentacle, strand, chain, charm, loop, separate donor object, animal body, animal head, face, or eyes. "
                )
                if object_type.lower() == "snowman":
                    preserve_sentence = (
                        f"Preserve the same {object_type} identity, pose, camera angle, body proportions, "
                        "hat, scarf, arms, eyes, mouth, and body buttons. "
                    )
                else:
                    preserve_sentence = (
                        f"Preserve the same {object_type} identity, pose, camera angle, global silhouette, "
                        "main body proportions, material style, color palette, lighting style, and every unselected component. "
                        "Use the source image as a strong identity lock for all unselected parts: keep their shapes, sizes, colors, positions, surface style, and relationships visually the same. "
                        "Do not anthropomorphize it; do not add eyes, mouth, smile, face, character expression, or cartoon features. "
                    )
                return (
                    f"Edit the provided source image into a single isolated {object_type} 3D product render on a pure white studio cutout background. "
                    f"{preserve_sentence}"
                    f"Change only the selected local part: the {part_label}. "
                    f"Replace the old {part_label} with exactly one new {part_label}: {target_phrase}. "
                    f"{old_desc_sentence}"
                    f"{placement_sentence}"
                    f"{surface_only_sentence}"
                    f"{wrong_location_sentence}"
                    f"Do not change any unselected part. Do not add or remove accessories except replacing the {part_label}. "
                    "One complete object only, centered, full body visible, clean 3D render. "
                    "The image must look like a catalog asset cutout: no text, no labels, no cards, no frame, no scene, no floor plane, no horizon, no ambient background gradient, no vignette, no cast shadow. "
                    "Every pixel outside the single object should be flat pure white RGB(255,255,255)."
                )
            selected = spec.get("selected_part") or {}
            old_shape = str(selected.get("shape") or "").strip()
            old_name = str(selected.get("canonical_name") or part_name).strip()
            old_exclusion = ""
            if old_shape and not spec.get("positive_only"):
                old_exclusion = (
                    f" The new local part must no longer look like the original selected {old_name}: {old_shape}. "
                    f"Do not keep the old {old_name} silhouette or old {old_name} appearance."
                )
            return (
                f"{base} "
                f"{old_exclusion}"
                "Use the source image as identity reference only for unselected parts. "
                "The selected part must be genuinely regenerated as a new 3D local form, not pasted, masked, or painted over. "
                "Keep the rest of the object visually consistent and do not introduce any 2D flat patch. "
                "Render as a single tangible 3D asset in a clean three-quarter product-render view; "
                "fill every pixel outside the single object with pure RGB(255,255,255) white."
            )
        return (
            f"保留这张图中的{object_type}主体、姿态、轮廓和所有未选中部件不变；"
            f"只把原来的{part_name}替换成{target}形态，不要同时保留旧{part_name}，"
            f"不要新增第二个{part_name}，不要改变其它部件。三维模型渲染，四分之三视角，"
            "有体积和深度；纯白背景、无地面、无投影、单体。"
        )
    if stage == "texture":
        mapping = spec.get("structure_mapping") or {}
        donor_property = str(mapping.get("donor_relational_property") or "").strip()
        transfer_operation = str(mapping.get("transfer_operation") or "").strip()
        rationale = str(mapping.get("mapping_rationale") or "").strip()
        preserve_elements = [
            str(item).strip() for item in (spec.get("preserve_elements") or []) if str(item).strip()
        ]
        preservation = "; ".join(preserve_elements[:12])
        return (
            f"Use the provided image as a strict geometry and identity reference for one {object_type}. "
            f"Keep the exact silhouette, proportions, pose, camera angle, part inventory, part positions, and attachments unchanged. "
            f"Preserve these visible identity cues: {preservation or 'all recognizable source components and their layout'}. "
            f"Perform material-only analogical transfer from the knowledge-graph donor '{target}'. "
            f"Donor physical surface property: {donor_property or target}. "
            f"Apply this visible PBR material operation: {transfer_operation or f'replace the dominant surface response with the physical material behavior of {target}'}. "
            f"Analogy rationale: {rationale}. "
            "Make the new material unmistakably visible through coherent base color, roughness, specular/metallic response, translucency when physically relevant, "
            "and surface microstructure. Apply it as an integrated material over the existing source geometry, never as an added donor object, decoration, shell, accessory, or changed part. "
            "Do not redesign, reshape, add, remove, or relocate any component. Render a tangible high-quality 3D product asset with physically based material shading. "
            "Show one complete centered object only. Fill every pixel outside the object with flat pure RGB(255,255,255) white: no floor, horizon, environment, gradient, cast shadow, text, or frame."
        )
    raise ValueError(f"unsupported stage: {stage}")


def generate_qwen(
    *,
    base_url: str,
    prompt: str,
    source_image: str,
    mask_image: str | None,
    object_type: str,
    stage: str,
    output: Path,
    seed: int,
    width: int,
    height: int,
    steps: int,
    strength: float,
    mode: str,
    padding_mask_crop: int | None,
) -> None:
    ensure_image_phase()
    negative = (
        "background, colored background, blue background, gray background, gradient background, "
        "scene, scenery, landscape, snow ground, floor, floor plane, horizon, sky, shadow, cast shadow, drop shadow, ambient occlusion background, vignette, extra object, "
        "duplicate object, cropped object, text, watermark, blurry, low quality, flat 2d image, "
        "2d illustration, vector illustration, line art, icon, logo, poster, graphic design, "
        "orthographic blueprint, diagram, cartoon outline"
    )
    if stage == "part":
        negative += (
            ", old selected part, unchanged selected part, duplicate selected part, "
            "painted patch, sticker, pasted cutout, flat local patch, text, label, caption, "
            "instruction card, poster, sign, diagram, multiple objects, two objects, extra snowman, "
            "handheld prop, object on hat, object on body, colored background, orange background, yellow background"
            ", dangling appendage, tail, limb, strand, chain, charm, hanging loop, separate donor object, "
            "water stream, splash, hose, cable, tube connected outside the object, side-mounted donor object, "
            "changed body color, changed grip, changed trigger, changed tank, redesigned main body"
        )
        if object_type.lower() not in {"snowman", "character", "person", "animal", "creature", "robot toy", "robot"}:
            negative += (
                ", anthropomorphic face, cute face, eyes, mouth, smile, character expression, "
                "cartoon face, facial features, animal head, creature body, octopus body, tentacle creature, "
                "face on accessory, eyes on accessory"
            )
    payload: dict[str, Any] = {
        "prompt": prompt,
        "negative_prompt": negative,
        "width": width,
        "height": height,
        "num_inference_steps": steps,
        "true_cfg_scale": 4.0,
        "max_sequence_length": 384,
        "seed": seed,
    }
    if mode == "masked":
        if not mask_image:
            raise RuntimeError("masked mode requires --mask-image")
        url = base_url.rstrip("/") + "/generate-masked"
        payload.update(
            {
                "source_image_path": source_image,
                "mask_image_path": mask_image,
                "mode": "inpaint",
                "strength": strength,
                "padding_mask_crop": padding_mask_crop,
            }
        )
    elif mode == "img2img":
        url = base_url.rstrip("/") + "/generate-conditioned"
        payload.update(
            {
                "source_image_path": source_image,
                "mode": "img2img",
                "strength": strength,
            }
        )
    else:
        url = base_url.rstrip("/") + "/generate"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=1200) as response:
            output.write_bytes(response.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Qwen-Image HTTP {exc.code}: {body}") from exc


def write_result(
    path: Path,
    *,
    status: str,
    stage: str,
    source_image: str,
    stage1_path: Path,
    items: list[dict[str, Any]],
    total: int,
) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "creativeflow.qwen-image-only.v1",
                "status": status,
                "stage": stage,
                "source_image_path": source_image,
                "stage1_result_path": str(stage1_path),
                "items": items,
                "completed": len(items),
                "total": total,
                "image_model": "Qwen-Image",
                "scoring": None,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def visual_acceptance(path: Path, *, stage: str) -> dict[str, Any]:
    """Lightweight geometry/background QA for generated images.

    This is not a semantic judge. It only catches obvious failures that hurt
    3D: non-white background, multiple separated objects/cards, and tiny/cropped
    subjects.
    """
    image = Image.open(path).convert("RGB")
    width, height = image.size
    pixels = image.load()

    def is_white(px: tuple[int, int, int]) -> bool:
        r, g, b = px
        return r >= 245 and g >= 245 and b >= 245 and max(r, g, b) - min(r, g, b) <= 10

    border: list[tuple[int, int, int]] = []
    band = max(8, min(width, height) // 32)
    for y in range(height):
        for x in range(width):
            if x < band or x >= width - band or y < band or y >= height - band:
                border.append(pixels[x, y])
    border_white_ratio = sum(1 for px in border if is_white(px)) / max(1, len(border))

    # Downsample mask for connected components.
    small = image.resize((128, 128))
    sp = small.load()
    mask = [[not is_white(sp[x, y]) for x in range(128)] for y in range(128)]
    seen = [[False] * 128 for _ in range(128)]
    components: list[int] = []
    foreground_points: list[tuple[int, int]] = []
    for sy in range(128):
        for sx in range(128):
            if seen[sy][sx] or not mask[sy][sx]:
                continue
            stack = [(sx, sy)]
            seen[sy][sx] = True
            area = 0
            while stack:
                x, y = stack.pop()
                area += 1
                foreground_points.append((x, y))
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < 128 and 0 <= ny < 128 and not seen[ny][nx] and mask[ny][nx]:
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            if area >= 20:
                components.append(area)
    components.sort(reverse=True)
    nonwhite_ratio = sum(sum(1 for v in row if v) for row in mask) / (128 * 128)
    largest = components[0] if components else 0
    second = components[1] if len(components) > 1 else 0
    component_count = len([area for area in components if area >= max(60, largest * 0.08)])
    if foreground_points:
        min_x = min(point[0] for point in foreground_points)
        min_y = min(point[1] for point in foreground_points)
        max_x = max(point[0] for point in foreground_points)
        max_y = max(point[1] for point in foreground_points)
        safe_margin_ratio = min(min_x, min_y, 127 - max_x, 127 - max_y) / 128
        subject_bbox = [
            round(min_x * width / 128),
            round(min_y * height / 128),
            round((max_x + 1) * width / 128),
            round((max_y + 1) * height / 128),
        ]
    else:
        safe_margin_ratio = 0.0
        subject_bbox = None
    reasons: list[str] = []
    if border_white_ratio < MIN_BORDER_WHITE_RATIO:
        reasons.append("background_not_pure_white")
    if foreground_points and safe_margin_ratio < MIN_SAFE_MARGIN_RATIO:
        reasons.append("subject_touches_frame")
    if component_count > 1:
        reasons.append("multiple_large_subjects")
    if nonwhite_ratio < MIN_SUBJECT_RATIO:
        reasons.append("subject_too_small")
    if nonwhite_ratio > MAX_SUBJECT_RATIO:
        reasons.append("subject_too_large")
    accepted = not reasons
    return {
        "accepted": accepted,
        "reasons": reasons,
        "border_white_ratio": round(border_white_ratio, 4),
        "nonwhite_ratio": round(nonwhite_ratio, 4),
        "subject_bbox": subject_bbox,
        "safe_margin_ratio": round(safe_margin_ratio, 4),
        "component_count": component_count,
        "largest_component_area_128": largest,
        "second_component_area_128": second,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage1-result", required=True)
    parser.add_argument("--source-image", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--object-type", required=True)
    parser.add_argument("--part-name", default="selected part")
    parser.add_argument("--qwen-base-url", default="http://127.0.0.1:18082")
    parser.add_argument("--width", type=int, default=768)
    parser.add_argument("--height", type=int, default=768)
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--strength", type=float, default=0.84)
    parser.add_argument("--mode", choices=["masked", "img2img", "text2img"], default="img2img")
    parser.add_argument("--mask-image", default="")
    parser.add_argument("--padding-mask-crop", type=int, default=-1)
    parser.add_argument("--max-items", type=int, default=0)
    parser.add_argument("--seed-offset", type=int, default=0)
    args = parser.parse_args()

    stage1_path = Path(args.stage1_result)
    stage1 = json.loads(stage1_path.read_text(encoding="utf-8"))
    directions = stage1.get("directions") or []
    if stage1.get("status") != "completed" or not directions:
        raise RuntimeError("Stage 2 requires completed directions")
    if args.max_items > 0:
        directions = directions[: args.max_items]
    stage = str(stage1["stage"])
    mask_image = str(args.mask_image).strip() or None
    if args.mode == "masked" and stage != "part":
        raise RuntimeError("masked mode is only intended for Part variation")
    if args.mode == "masked" and (not mask_image or not Path(mask_image).is_file()):
        raise RuntimeError("masked mode requires an existing --mask-image path")
    padding_mask_crop = args.padding_mask_crop if args.padding_mask_crop >= 0 else None
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result_path = out_dir / "stage2_result.json"
    items: list[dict[str, Any]] = []
    generation_source = args.source_image

    for index, direction in enumerate(directions):
        spec = direction.get("transfer_spec") or {}
        prompt = execution_prompt(stage, args.object_type, args.part_name, spec)
        image_path = out_dir / f"{direction['direction_id']}.png"
        seed = 4200 + args.seed_offset + index * 137
        generate_qwen(
            base_url=args.qwen_base_url,
            prompt=prompt,
            source_image=generation_source,
            mask_image=mask_image,
            object_type=args.object_type,
            stage=stage,
            output=image_path,
            seed=seed,
            width=args.width,
            height=args.height,
            steps=args.steps,
            strength=args.strength,
            mode=args.mode,
            padding_mask_crop=padding_mask_crop,
        )
        qa = visual_acceptance(image_path, stage=stage)
        items.append(
            {
                "direction_id": direction["direction_id"],
                "anchor": direction["anchor"],
                "conceptnet_relation": direction.get("conceptnet_relation") or {},
                "execution_prompt": prompt,
                "generation_source_image": generation_source if args.mode in {"img2img", "masked"} else None,
                "generation_mask_image": mask_image if args.mode == "masked" else None,
                "generation_mode": args.mode,
                "image_path": str(image_path),
                "visual_acceptance": qa,
                "accepted_for_3d": image_path.is_file() and image_path.stat().st_size > 0 and qa["accepted"],
            }
        )
        write_result(
            result_path,
            status="running",
            stage=stage,
            source_image=args.source_image,
            stage1_path=stage1_path,
            items=items,
            total=len(directions),
        )

    write_result(
        result_path,
        status="completed",
        stage=stage,
        source_image=args.source_image,
        stage1_path=stage1_path,
        items=items,
        total=len(directions),
    )
    print(result_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
