#!/usr/bin/env python3
"""Low Fidelity Stage 1: source-conditioned silhouette-delta planner.

This version intentionally does NOT use ConceptNet, KG target nouns, semantic
distance buckets, masks, or image geometry operations.  Low Fidelity is treated
as a controlled macro-silhouette family-variation problem:

    same source identity + locked visual cues + clear geometric silhouette archetype

The VLM reads the source image for identity/style locks.  Shape candidates are
stable geometric archetypes such as square/blocky, triangular/conical,
long-vertical, flat-wide, cylindrical/barrel-volume, hourglass/waisted, etc.
They are shape primitives, not donor object nouns.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


PLANNER_SYSTEM = """
You are the Low Fidelity planner for CreativeFlow.

Your job is NOT to invent a new object. Your job is to analyze the source image
and preserve the exact source identity while proposing clear macro-silhouette
variations. The variation must be visible in the whole-body outline: square,
triangular/conical, long vertical, flat wide, cylindrical, waisted, broad-base,
or broad-top. It must still read as the same source object.

Return strict JSON only.
""".strip()


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return text[:48] or "silhouette_delta"


def clean_delta_name(value: str) -> str:
    text = _clean(value)
    text = re.sub(r"_?snake_case_name$", "", text, flags=re.I)
    text = re.sub(r"\s*snake case name\s*$", "", text, flags=re.I)
    return text or "silhouette_delta"


def _list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_clean(item) for item in value if _clean(item)]


def _image_data_url(path: str) -> str:
    suffix = Path(path).suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/webp" if suffix == ".webp" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(Path(path).read_bytes()).decode("ascii")


def call_runtime_json(
    system_prompt: str,
    user_prompt: str,
    *,
    image_paths: list[str] | None = None,
    max_tokens: int = 1536,
) -> dict[str, Any] | None:
    api_base = os.getenv("CF_TEXT_LLM_API_BASE", "http://127.0.0.1:18084/v1").rstrip("/")
    model = os.getenv("CF_TEXT_LLM_MODEL", "qwen3-planner")
    user_content: str | list[dict[str, Any]] = user_prompt
    if image_paths:
        user_content = [{"type": "text", "text": user_prompt}]
        for path in image_paths:
            if path and Path(path).is_file():
                user_content.append({"type": "image_url", "image_url": {"url": _image_data_url(path)}})
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.15,
        "max_tokens": max_tokens,
    }
    request = urllib.request.Request(
        api_base + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=240) as response:
            payload = json.loads(response.read().decode("utf-8"))
        text = str(payload["choices"][0]["message"]["content"]).strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S)
        start = text.find("{")
        if start < 0:
            raise ValueError("runtime response contains no JSON object")
        decoded, _ = json.JSONDecoder().raw_decode(text[start:])
        return decoded if isinstance(decoded, dict) else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"[low_delta] runtime_json_http_error: {exc.code} {detail}", file=sys.stderr, flush=True)
        return None
    except Exception as exc:
        print(f"[low_delta] runtime_json_error: {exc}", file=sys.stderr, flush=True)
        return None


def planner_prompt(source_noun: str, designer_intent: str, source_facts: dict[str, Any]) -> str:
    return f"""
Source object noun:
{source_noun}

Designer intent:
{designer_intent or 'create low-fidelity global silhouette variations while preserving source identity'}

Optional authoritative source facts:
{json.dumps(source_facts, ensure_ascii=False)}

Read the attached source image. Produce a source-conditioned low-fidelity
silhouette plan.

The result must follow these principles:
1. The generated object must still be clearly recognizable as the same
   "{source_noun}".
2. Preserve the source's object category, main parts, color palette, material
   feeling, camera/view direction, lighting direction, pose/stance, and iconic
   identity cues.
3. Only change global silhouette parameters: overall height, width, length,
   body massing, top/bottom volume ratio, taper, blockiness, triangularity,
   cylindricality, elongation, flatness, waist curve, segment rhythm, and
   outside contour.
4. Do NOT propose donor object nouns such as cucumber, pear, lantern, rocket,
   mushroom, etc. Geometric shape words are allowed and encouraged: square,
   blocky, triangular, conical, long-strip, flat-wide, cylindrical,
   barrel-volume, hourglass-waisted, broad-base, broad-top.
5. Do NOT change texture, material, color, style, scene, background, accessory,
   selected part, or object identity.

Generate 8 diverse macro silhouette deltas across multiple dimensions:
- square/blocky body
- triangular/conical body
- long vertical / stretched height
- flat wide / compressed height
- cylindrical / barrel-volume body
- hourglass / waist-in body
- broad base / narrow top
- broad top / narrow base

Each delta should be executable as a prompt fragment and should feel like a
same-object design-family variation, not a replacement object. The difference
must be obvious at thumbnail scale.

Return exactly this JSON shape:
{{
  "source_noun": "{source_noun}",
  "identity_cues": ["concrete visible cue to preserve"],
  "style_locks": ["same color palette", "same camera angle", "..."],
  "current_silhouette": {{
    "overall_height": "...",
    "overall_width": "...",
    "massing": "...",
    "proportion": "...",
    "contour_language": "...",
    "segment_rhythm": "..."
  }},
  "silhouette_deltas": [
    {{
      "delta_id": "delta_01",
      "name": "short stable snake_case name",
      "dimension_focus": ["height", "width"],
      "delta": "Chinese neutral geometric delta only; no donor object noun",
      "identity_preservation": "why the source identity remains intact",
      "risk_to_avoid": "what would make it become another object"
    }}
  ]
}}
""".strip()


FORBIDDEN_DONOR_TERMS = {
    # English donor/object nouns that previously caused identity replacement.
    "barrel", "cucumber", "column", "pear", "bean", "crescent", "banana",
    "goblet", "vase", "bottle", "lantern", "rocket", "tower", "pillar",
    "mushroom", "pumpkin", "bell", "bulb", "dome",
    # Chinese equivalents / direct comparisons.
    "黄瓜", "梨", "豆", "月牙", "香蕉", "高脚杯", "花瓶",
    "瓶子", "灯笼", "火箭", "塔", "蘑菇", "南瓜", "灯泡",
}


BAD_AXIS_TERMS = {
    "change texture", "change material", "change color", "change background", "change scene", "change style",
    "改变材质", "更换材质", "改变材料", "改变颜色", "更换颜色", "改变背景", "改变场景", "改变风格", "改变纹理",
}


def valid_delta(delta: dict[str, Any]) -> tuple[bool, str]:
    text = json.dumps(
        {
            "name": delta.get("name"),
            "dimension_focus": delta.get("dimension_focus"),
            "delta": delta.get("delta"),
        },
        ensure_ascii=False,
    ).lower()
    if any(term.lower() in text for term in FORBIDDEN_DONOR_TERMS):
        return False, "contains donor/object comparison term"
    if any(term.lower() in text for term in BAD_AXIS_TERMS):
        return False, "changes non-silhouette axis"
    words = _clean(delta.get("delta"))
    if len(words) < 8:
        return False, "delta is too short to execute"
    if "%" in words or re.fullmatch(r"[+\-0-9.,\s_a-zA-Z]+", words):
        return False, "delta is numeric or label-like rather than descriptive"
    return True, "passed"


def fallback_deltas(source_noun: str) -> list[dict[str, Any]]:
    """Deterministic backup if the VLM returns too few usable deltas."""
    raw = [
        ("blocky_square_body", ["blockiness", "width", "corner_roundness"], "把主体大轮廓改成更方块化的几何体量：整体更接近方形或立方块比例，左右边界更直，角仍保持圆润；保留原有头部、五官、配件和颜色，使它仍然是同一个物体"),
        ("triangular_cone_body", ["taper", "triangularity", "height"], "把主体大轮廓改成明显上窄下宽的三角形或圆锥形体量：底部更宽更稳，顶部逐渐收窄；核心身份部件仍放在对应位置，不改变物体类别"),
        ("long_vertical_body", ["height", "elongation", "slenderness"], "把主体大轮廓改成长条形竖向体量：整体高度显著增加，宽度收窄，主要部件沿竖向重新排布但身份特征、颜色和材质保持一致"),
        ("flat_wide_body", ["width", "flatness", "height"], "把主体大轮廓改成扁宽形体量：整体高度降低，横向宽度显著增加，主体更低矮展开；所有关键识别元素仍保留并按同一视角呈现"),
        ("cylindrical_body", ["cylindricality", "straight_sides", "segment_rhythm"], "把主体大轮廓改成圆柱形或桶形体量：上下宽度更接近，侧边更直，顶底轮廓更平整；保持同一个物体的部件、表情、配色和材质"),
        ("hourglass_waisted_body", ["waist_curve", "width_distribution", "curve"], "把主体大轮廓改成沙漏式腰收体量：上部和下部保持饱满，中部明显收窄，形成清楚的曲线节奏；核心部件和身份线索不变"),
        ("broad_base_body", ["base_volume", "taper", "mass_distribution"], "把主体大轮廓改成底部很宽、上部较窄的稳定体量：下半部显著扩大，上半部轻一些，整体重心更低；仍然清楚可识别为同一个物体"),
        ("broad_top_body", ["upper_volume", "reverse_taper", "mass_distribution"], "把主体大轮廓改成上部更宽、下部较窄的倒锥式体量：上半部显著扩大，下半部收窄但保持站立稳定；原有关键部件和颜色材质不变"),
    ]
    return [
        {
            "delta_id": f"delta_{index:02d}",
            "name": name,
            "dimension_focus": focus,
            "delta": delta,
            "identity_preservation": f"仍保持为同一个{source_noun}，只调整整体轮廓和比例。",
            "risk_to_avoid": "不要引入新的物体类别、材质、颜色、场景或额外部件。",
        }
        for index, (name, focus, delta) in enumerate(raw, start=1)
    ]


def normalize_delta_text(name: str, raw_delta: str) -> str:
    """Keep planner / shape-library wording as-is.

    Earlier versions normalized labels such as ``triangular_cone`` into safer,
    milder Chinese geometry deltas. That made Low Fidelity too conservative: the
    intended macro silhouette transfer was flattened into tiny proportion edits.
    For Low Fidelity we want the raw silhouette concept to survive into the
    generation prompt.
    """
    return _clean(raw_delta)


def build_prompt(source_noun: str, identity_cues: list[str], style_locks: list[str], delta: str) -> str:
    cues = "、".join(identity_cues[:10]) if identity_cues else f"{source_noun}的主要身份特征"
    return (
        f"生成一个{source_noun}。它必须仍然清楚可识别为{source_noun}，"
        f"保留核心身份线索：{cues}。"
        f"这次 Low Fidelity 的目标是让大轮廓变化在缩略图尺度也明显可见：{delta}。"
        "不要保持原来的默认轮廓；必须把主体身体的整体几何外轮廓改出来。"
        "可以让帽子、围巾、表情、配件、局部比例和轻微色彩跟随新轮廓自然协同变化，"
        "但不要改变物体类别，不要变成其他物体。"
        "纯白背景、无地面、无投影、单体，三维资产渲染，四分之三视角，有真实体积和深度。"
    )


def plan(source_image: str, source_noun: str, designer_intent: str, source_facts: dict[str, Any]) -> dict[str, Any]:
    prompt = planner_prompt(source_noun, designer_intent, source_facts)
    for _ in range(3):
        result = call_runtime_json(
            PLANNER_SYSTEM,
            prompt,
            image_paths=[source_image],
            max_tokens=3072,
        )
        if isinstance(result, dict) and len(result.get("silhouette_deltas") or []) >= 4:
            return result
    raise RuntimeError("Low Fidelity VLM planner did not return usable silhouette deltas")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--top-k", type=int, default=4)
    args = parser.parse_args()

    request = json.loads(Path(args.input).read_text(encoding="utf-8"))
    source_image = _clean(request.get("source_image_path"))
    source_noun = _clean(request.get("object_type"))
    if not Path(source_image).is_file() or not source_noun:
        raise ValueError("source_image_path and object_type are required")

    source_facts = request.get("source_elements") if isinstance(request.get("source_elements"), dict) else {}
    planned = plan(
        source_image,
        source_noun,
        _clean(request.get("user_prompt")),
        source_facts,
    )

    identity_cues = _list(planned.get("identity_cues"))
    style_locks = _list(planned.get("style_locks"))
    if not identity_cues:
        identity_cues = [f"{source_noun}的主要可见部件", f"{source_noun}的类别识别特征"]
    if not style_locks:
        style_locks = ["same color palette", "same material feeling", "same camera angle", "same lighting direction"]

    current_silhouette = planned.get("current_silhouette") if isinstance(planned.get("current_silhouette"), dict) else {}

    usable: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_delta_text: set[str] = set()
    # Macro silhouette primitives are prioritized.  The VLM is used mainly for
    # source identity/style locks and can add extra deltas after the stable
    # geometry library, but it should not dilute the main Low Fidelity effect.
    for raw in fallback_deltas(source_noun) + list(planned.get("silhouette_deltas") or []):
        name = clean_delta_name(raw.get("name")) or _slug(_clean(raw.get("delta")))
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        delta = {
            "delta_id": _clean(raw.get("delta_id")) or f"delta_{len(audit) + 1:02d}",
            "name": name,
            "dimension_focus": _list(raw.get("dimension_focus")),
            "delta": normalize_delta_text(name, _clean(raw.get("delta"))),
            "identity_preservation": _clean(raw.get("identity_preservation")),
            "risk_to_avoid": _clean(raw.get("risk_to_avoid")),
        }
        passed, reason = valid_delta(delta)
        delta_key = re.sub(r"\s+", "", delta["delta"]).lower()
        if passed and delta_key in seen_delta_text:
            passed, reason = False, "duplicate normalized silhouette delta"
        audit.append({**delta, "passed": passed, "gate_reason": reason})
        if passed and len(usable) < max(args.top_k, 1):
            usable.append(delta)
            seen_delta_text.add(delta_key)
        if len(usable) >= max(args.top_k, 1):
            break

    if len(usable) < max(args.top_k, 1):
        raise RuntimeError(f"only {len(usable)} usable silhouette deltas; required={args.top_k}")

    directions: list[dict[str, Any]] = []
    for index, item in enumerate(usable[: args.top_k], start=1):
        direction_id = f"low_fidelity_{index:02d}_{_slug(item['name'])}"
        prompt = build_prompt(source_noun, identity_cues, style_locks, item["delta"])
        directions.append(
            {
                "direction_id": direction_id,
                "anchor": item["name"],
                "silhouette_delta": item["delta"],
                "dimension_focus": item["dimension_focus"],
                "source_contour": current_silhouette,
                "variation_gate": {
                    "passed": True,
                    "policy": "identity_locked_silhouette_delta_no_conceptnet",
                    "reason": "neutral geometric delta; no donor noun; no non-silhouette axis",
                },
                "transfer_spec": {
                    "direction_title": item["name"],
                    "graph_anchor": item["name"],
                    "prompt": prompt,
                    "silhouette_delta": item["delta"],
                    "identity_cues": identity_cues,
                    "style_locks": style_locks,
                    "changed_shape_axes": item["dimension_focus"],
                },
            }
        )

    result = {
        "schema_version": "creativeflow.low-fidelity-source-conditioned-delta.v2",
        "status": "completed",
        "stage": "low_fidelity",
        "source_image_path": source_image,
        "source_noun": source_noun,
        "planner_mode": "qwen_vlm_source_identity_plus_silhouette_delta",
        "expansion_provider": "source-conditioned VLM planner + deterministic silhouette-delta fallback",
        "conceptnet_status": "disabled_not_used",
        "semantic_distance_constraint": "none",
        "identity_cues": identity_cues,
        "style_locks": style_locks,
        "current_silhouette": current_silhouette,
        "all_silhouette_deltas": audit,
        "directions": directions,
        "selection_policy": {
            "top_k": args.top_k,
            "object_identity_locked": True,
            "colors_materials_camera_lighting_locked": True,
            "parts_accessories_locked": True,
            "only_global_silhouette_delta": True,
            "conceptnet": False,
            "kg_target_nouns": False,
            "scoring_model": False,
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
