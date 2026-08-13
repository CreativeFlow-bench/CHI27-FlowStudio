from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from variation_image_scoring import score_candidate_image  # noqa: E402


def test_part_scores_whole_generated_image_without_mask() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = Image.new("RGB", (64, 64), "white")
        ImageDraw.Draw(source).ellipse((12, 10, 52, 58), fill="lightblue")
        source.save(root / "source.png")
        candidate = source.copy()
        ImageDraw.Draw(candidate).ellipse((28, 27, 42, 37), fill="red")
        candidate.save(root / "candidate.png")
        result = score_candidate_image(
            stage="part",
            source_image_path=root / "source.png",
            candidate_image_path=root / "candidate.png",
        )
        assert "missing_effective_part_mask" not in result["reasons"]
        assert "inside_mask_mae" not in result["metrics"]
