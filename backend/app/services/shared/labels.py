"""Single source of truth for object/part label normalization (zh/en).

Replaces the duplicated ZH_LABELS maps that previously lived in
contextual_divergence, gui_interaction_supervisor and
semantic_language_supervisor (refactor plan P0).
"""

from __future__ import annotations


ZH_LABELS: dict[str, str] = {
    "snowman": "雪人",
    "hat": "帽子",
    "top hat": "高帽",
    "nose": "鼻子",
    "carrot": "胡萝卜",
    "scarf": "围巾",
    "arm": "手臂",
    "head": "头部",
    "body": "身体",
    "base": "底座",
    "button": "纽扣",
    "eye": "眼睛",
    "kettle": "水壶",
    "teapot": "茶壶",
    "handle": "把手",
    "spout": "壶嘴",
    "lid": "壶盖",
    "lamp": "灯",
    "lampshade": "灯罩",
    "vase": "花瓶",
    "speaker": "音箱",
    "grille": "网罩",
    "mesh": "网罩",
    "cup": "杯子",
    "mug": "马克杯",
    "chair": "椅子",
    "table": "桌子",
    "bottle": "瓶子",
    "jar": "罐子",
    "bowl": "碗",
    "robot": "机器人",
    "toy": "玩具",
    "car": "汽车",
    "helmet": "头盔",
    "sneaker": "运动鞋",
    "boot": "靴子",
    "umbrella": "雨伞",
    "keyboard": "键盘",
    "phone": "手机",
    "camera": "相机",
    "watch": "手表",
    "guitar": "吉他",
    "plant pot": "花盆",
}


def zh_label(value: str | None, fallback: str | None = None) -> str:
    """Map an english object/part label to its Chinese label."""
    if not value:
        return fallback or "对象"
    stripped = value.strip()
    lowered_full = stripped.lower()
    if lowered_full in ZH_LABELS:
        return ZH_LABELS[lowered_full]
    first = _first_token(lowered_full)
    return ZH_LABELS.get(first, stripped)


def clean_part_label(label: str | None) -> str | None:
    """Normalize a part label: drop id suffixes, map known names to zh."""
    if not label:
        return None
    cleaned = label.strip()
    if cleaned.lower().startswith("part_"):
        return None
    if "_" in cleaned:
        cleaned = cleaned.split("_")[0]
    lowered = cleaned.lower()
    if lowered in ZH_LABELS:
        return ZH_LABELS[lowered]
    return cleaned


def _first_token(value: str) -> str:
    for separator in (" ", "_", "-"):
        if separator in value:
            return value.split(separator)[0]
    return value
