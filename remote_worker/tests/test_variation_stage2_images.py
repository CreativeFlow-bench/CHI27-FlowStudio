from pathlib import Path

from PIL import Image, ImageDraw

from remote_worker.variation_stage2_images import (
    normalize_generated_studio_background,
    visual_acceptance,
)


def _draw_fixture(
    path: Path,
    *,
    background: tuple[int, int, int] = (255, 255, 255),
    boxes: tuple[tuple[int, int, int, int], ...] = ((32, 28, 224, 228),),
) -> None:
    image = Image.new("RGB", (256, 256), background)
    draw = ImageDraw.Draw(image)
    for box in boxes:
        draw.ellipse(box, fill=(70, 80, 95))
    image.save(path)


def test_accepts_one_complete_subject_on_pure_white(tmp_path: Path) -> None:
    path = tmp_path / "valid.png"
    _draw_fixture(path)

    result = visual_acceptance(path, stage="part")

    assert result["accepted"] is True
    assert result["border_white_ratio"] >= 0.95
    assert result["safe_margin_ratio"] >= 0.05
    assert result["component_count"] == 1


def test_rejects_gray_or_colored_background(tmp_path: Path) -> None:
    path = tmp_path / "gray.png"
    _draw_fixture(path, background=(230, 232, 236))

    result = visual_acceptance(path, stage="part")

    assert "background_not_pure_white" in result["reasons"]


def test_normalizes_only_edge_connected_light_neutral_background(tmp_path: Path) -> None:
    path = tmp_path / "gray-studio.png"
    image = Image.new("RGB", (256, 256), (228, 230, 232))
    draw = ImageDraw.Draw(image)
    draw.ellipse((32, 28, 224, 228), fill=(70, 80, 95))
    draw.ellipse((120, 100, 136, 116), fill=(230, 230, 230))
    image.save(path)

    assert normalize_generated_studio_background(path) is True

    normalized = Image.open(path).convert("RGB")
    assert normalized.getpixel((0, 0)) == (255, 255, 255)
    assert normalized.getpixel((128, 108)) == (230, 230, 230)
    assert visual_acceptance(path, stage="material")["accepted"] is True


def test_rejects_subject_touching_any_edge(tmp_path: Path) -> None:
    path = tmp_path / "cropped.png"
    _draw_fixture(path, boxes=((0, 28, 224, 228),))

    result = visual_acceptance(path, stage="part")

    assert "subject_touches_frame" in result["reasons"]


def test_rejects_two_separate_large_subjects(tmp_path: Path) -> None:
    path = tmp_path / "two.png"
    _draw_fixture(path, boxes=((22, 60, 112, 190), (144, 60, 234, 190)))

    result = visual_acceptance(path, stage="part")

    assert "multiple_large_subjects" in result["reasons"]
