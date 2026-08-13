"""③ Semantic & language supervisor: natural language, semantic distance,
hand-drawn annotation, uploaded references.

This supervisor names the target: it turns text/drawing/reference evidence
into semantic candidates (label_zh/en) plus an operation hint.
"""

from __future__ import annotations

from typing import Any

from app.models import SupervisorVote
from app.services.shared.labels import ZH_LABELS, zh_label

OPERATION_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("弯曲", "curve", "bend", "拱"), "deform"),
    (("替换", "replace", "换成"), "replace"),
    (("延伸", "向外", "extend", "outward", "拉长"), "extend"),
    (("开口", "镂空", "open", "hollow"), "open"),
    (("穿孔", "perforat", "孔"), "perforate"),
    (("哑光", "matte", "抛光", "光滑", "finish", "材质", "表面", "texture"), "finish"),
    (("平滑", "smooth", "圆润"), "deform"),
]

LEVEL_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("轮廓", "silhouette", "整体", "包络", "比例"), "silhouette"),
    (("材质", "表面", "纹理", "material", "surface", "texture"), "material_region"),
    (("整体", "whole", "全身"), "whole"),
]


def supervise_semantic_language(features: dict[str, Any]) -> SupervisorVote:
    intent_text = str(features.get("intent_text") or "").lower()
    semantic_distance = float(features.get("semantic_distance") or 0)
    part_id = features.get("part_id")
    part_label = None
    signals = features.get("signals") if isinstance(features.get("signals"), dict) else {}
    semantic = signals.get("semantic") if isinstance(signals.get("semantic"), dict) else {}
    part_label = str(semantic.get("part_label") or "") or None
    object_label = str(features.get("object_label") or "").strip().lower()
    object_label_zh = str(features.get("object_label_zh") or "").strip().lower()
    drawing = str(semantic.get("drawing_content") or features.get("drawing_content") or "")
    visual = signals.get("visual_context") if isinstance(signals.get("visual_context"), dict) else {}
    reference_images = visual.get("reference_images") or visual.get("image_refs") or []
    image_ref_count = int(features.get("image_ref_count") or len(reference_images) if isinstance(reference_images, list) else 0)

    level_scores = {"whole": 0.05, "silhouette": 0.1, "part": 0.1, "material_region": 0.05}
    part_candidates: list[dict[str, Any]] = []
    material_candidates: list[dict[str, Any]] = []
    silhouette_evidence: list[str] = []
    evidence: list[str] = []

    operation_hint: str | None = None
    for keywords, operation in OPERATION_KEYWORDS:
        if any(keyword in intent_text for keyword in keywords):
            operation_hint = operation
            evidence.append(f"text_op:{operation}")
            break

    for keywords, level in LEVEL_KEYWORDS:
        if any(keyword in intent_text for keyword in keywords):
            level_scores[level] = min(1.0, level_scores[level] + 0.45)
            if level == "silhouette":
                silhouette_evidence.append("text_silhouette")
            evidence.append(f"text_level:{level}")
            break

    # Named part in text (zh or en), registered asset part labels, or current part label.
    named_part: str | None = None
    named_part_id: str | None = None
    if part_label and part_label.lower() in intent_text:
        named_part = part_label
        named_part_id = str(part_id) if part_id else None
    if named_part is None:
        # Registered asset parts are more specific than the fixed vocabulary;
        # they take precedence so "雪人的帽子" resolves to the hat part.
        registered_parts = features.get("part_labels")
        if isinstance(registered_parts, list):
            for entry in registered_parts:
                if not isinstance(entry, dict):
                    continue
                label = str(entry.get("label") or "").strip()
                if (
                    label
                    and label.lower() not in {object_label, object_label_zh}
                    and label.lower() in intent_text
                ):
                    named_part = label
                    named_part_id = str(entry.get("part_id") or "") or None
                    break
    if named_part is None:
        for en, zh in ZH_LABELS.items():
            if (
                en.lower() == object_label
                or zh.lower() == object_label
                or en.lower() == object_label_zh
                or zh.lower() == object_label_zh
            ):
                # The object's own name is not a part target ("雪人" is the
                # whole snowman, not a component of it).
                continue
            if en in intent_text or zh in intent_text:
                named_part = en
                break
    if named_part:
        level_scores["part"] = min(1.0, level_scores["part"] + 0.55)
        part_candidates.append(
            {
                "part_id": named_part_id or (str(part_id) if part_id else None),
                "label_zh": zh_label(named_part) or named_part,
                "label_en": named_part,
                "role": "named_in_text",
                "score": 0.55,
                "evidence": [f"text_part:{named_part}"],
            }
        )
        evidence.append(f"text_part:{named_part}")
    elif part_id:
        part_candidates.append(
            {
                "part_id": str(part_id),
                "label_zh": part_label or None,
                "role": "current_selection",
                "score": 0.3,
                "evidence": ["selected_part"],
            }
        )

    # Drawing / hand-drawn annotation: whole contour vs local mark.
    if drawing:
        if any(word in drawing for word in ("轮廓", "triangle", "outline", "整体", "contour")):
            level_scores["silhouette"] = min(1.0, level_scores["silhouette"] + 0.4)
            silhouette_evidence.append(f"drawing:{drawing}")
            evidence.append("drawing_silhouette")
        else:
            level_scores["part"] = min(1.0, level_scores["part"] + 0.3)
            evidence.append("drawing_local")

    # Reference images: shape → silhouette, material → material region.
    roles = [str(item.get("role") or "") for item in reference_images if isinstance(item, dict) and item.get("role")]
    if image_ref_count > 0:
        if any("material" in role or "finish" in role for role in roles):
            level_scores["material_region"] = min(1.0, level_scores["material_region"] + 0.45)
            material_candidates.append(
                {"label_zh": None, "role": "material_reference", "score": 0.45, "evidence": [f"ref_role:{role}" for role in roles]}
            )
            evidence.append("ref_material")
        elif any("shape" in role or "silhouette" in role or "contour" in role for role in roles):
            level_scores["silhouette"] = min(1.0, level_scores["silhouette"] + 0.4)
            silhouette_evidence.append("ref_shape")
            evidence.append("ref_shape")
        else:
            level_scores["whole"] = min(1.0, level_scores["whole"] + 0.25)
            evidence.append("ref_whole")

    # Semantic distance: seeking alternatives / divergence.
    if semantic_distance >= 0.45:
        level_scores["whole"] = min(1.0, level_scores["whole"] + 0.2)
        level_scores["silhouette"] = min(1.0, level_scores["silhouette"] + 0.15)
        evidence.append(f"semantic_distance:{semantic_distance:.2f}")

    return SupervisorVote(
        supervisor="semantic_language",
        level_scores={key: round(value, 3) for key, value in level_scores.items()},
        part_candidates=part_candidates,
        material_candidates=material_candidates,
        silhouette_evidence=silhouette_evidence,
        operation_hint=operation_hint,
        conflict=None,
        evidence=evidence or ["no_semantic_signal"],
    )
