#!/usr/bin/env python3
"""Two-stage planner for CreativeFlow Part variation.

This is the minimal, source-grounded Part path:

source noun + SAM3D/VLM selected part semantic ->
3D part context -> compatible part-affordance expansion -> part-only prompts.

It does not composite pixels, draw masks, use ControlNet, or pretend the fake
mask is a real segmentation result.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from low_fidelity_conceptnet import call_runtime_json


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def part_semantics_from_request(request: dict[str, Any]) -> dict[str, Any]:
    payload = request.get("part_semantics") or {}
    if not payload and request.get("part_semantics_path"):
        path = Path(str(request["part_semantics_path"]))
        if path.is_file():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload = loaded
    if not isinstance(payload, dict):
        payload = {}
    name = clean(
        payload.get("canonical_name")
        or payload.get("part_name")
        or request.get("part_name")
        or request.get("selected_part")
    )
    if not name:
        raise RuntimeError("Part variation requires part_semantics.canonical_name or part_name")
    payload.setdefault("canonical_name", name)
    if payload.get("fake_mask") is True:
        raise RuntimeError("Part variation now requires real SAM3D part evidence; fake_mask input is forbidden")
    part_id = clean(payload.get("part_id"))
    semantic_source = clean(payload.get("semantic_source"))
    sam3d_manifest = clean(payload.get("sam3d_manifest_path") or request.get("sam3d_manifest_path"))
    cluster_ids = payload.get("sam3d_cluster_ids") or payload.get("cluster_ids")
    has_sam3d_evidence = (
        part_id.startswith("sam3d_")
        or "sam3d" in semantic_source.lower()
        or bool(sam3d_manifest)
        or bool(cluster_ids)
    )
    if not has_sam3d_evidence:
        raise RuntimeError(
            "Part variation requires real SAM3D evidence: part_id=sam3d_*, "
            "semantic_source containing sam3d, sam3d_manifest_path, or sam3d_cluster_ids"
        )
    if not part_id:
        raise RuntimeError("Part variation requires a real SAM3D part_id or sam3d_cluster_ids")
    payload["part_id"] = part_id
    payload["semantic_source"] = semantic_source or "sam3d_cluster_semantic"
    if sam3d_manifest:
        payload["sam3d_manifest_path"] = sam3d_manifest
    if cluster_ids:
        payload["sam3d_cluster_ids"] = cluster_ids
    return payload


def planner_image_paths(request: dict[str, Any], part: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    source = clean(request.get("source_image_path"))
    crop = clean(part.get("crop_image_path"))
    overlay = clean(part.get("overlay_path"))
    for path in [source, crop, overlay]:
        if path and Path(path).is_file() and path not in paths:
            paths.append(path)
    return paths


def stage1_prompt(source: str, source_description: str, part: dict[str, Any], count: int) -> str:
    part_name = clean(part.get("canonical_name"))
    return f"""
You are a CreativeFlow design reasoning assistant for PART variation.

Goal:
Generate candidate concepts for changing ONLY the selected part of a source
object. This is not a full-object redesign and not a pixel collage.

The selected part was resolved from SAM3D / 3D part evidence. You must use the
3D semantic context of the part: its role, attachment socket, orientation,
scale, local shape, and relation to neighboring parts. Candidate concepts must
feel like they can become the same kind of part in that 3D context.

Source object:
{source}

Source description:
{source_description}

Selected part semantic:
{json.dumps(part, ensure_ascii=False)}

Reasoning task:
1. First infer the selected part's 3D semantic context:
   - role in the whole object
   - socket / contact interface
   - local orientation and protrusion direction
   - scale relative to neighboring parts
   - what must remain readable for it to still be a "{part_name}"
2. Then expand candidates by analogy using executable part attributes:
   local shape, protrusion profile, tip/base relation, socket compatibility,
   tactile feeling, symbolic role, and part affordance.
3. Candidate concepts should be "things/forms that can function as a
   {part_name}" in this source context, not arbitrary objects. For example, for
   a nose-like part, a candidate must plausibly become a small central facial
   protrusion: short beak, rounded button nose, peg/knob nose, bulbous nose,
   wedge nose, short cone, small nozzle-like nose, soft clay bump, etc.
4. Use implicit creative exploration and ConceptNet-style relation thinking,
   but always map back to the same selected-part role. The target may be a
   form/material metaphor, but the prompt must decode it as a replacement
   {part_name}.
5. Avoid candidates that require changing unselected parts, adding scenes,
   adding a second object, or replacing the whole source. Avoid material-only
   changes with no visible local shape change.
6. Avoid food/object labels that only resemble the current carrot material or
   color but do not add a useful part affordance. Do not output pepperoni,
   acorn, fruit slice, sticker, decoration, ornament, or flat patch for this
   smoke test unless it is explicitly converted into a nose-like protruding
   form with compatible socket and scale.
7. The candidate list must be diverse: do not repeat the same concept under
   slightly different names. Prefer different nose-affordance families:
   beak-like, button-like, knob/peg-like, bulbous, wedge/cone-like,
   nozzle-like, soft bump-like.

For each candidate, compare:
- source_part_attributes
- target_part_attributes
- attribute_mapping
- part_affordance_mapping: why the target can still act/read as the selected part
- socket_compatibility: how it attaches at the same 3D socket
- scale_orientation_constraints: how scale/orientation are kept compatible
- preserved_global_context
- compatibility_risk
Reject candidates that merely decorate the original part or attach extra
objects to it.

Output {count} candidates. Return JSON only:
{{
  "candidates": [
    {{
      "candidate_concept_name": "...",
      "reasoning_mode": "explicit relational expansion or implicit creative exploration",
      "source_part_attributes": ["..."],
      "target_part_attributes": ["..."],
      "attribute_mapping": "...",
      "part_affordance_mapping": "...",
      "socket_compatibility": "...",
      "scale_orientation_constraints": "...",
      "preserved_global_context": ["..."],
      "compatibility_risk": "...",
      "is_decoration": false,
      "identity_fit": "high or medium or low",
      "transfer_intensity": "mild or moderate or over-strong",
      "short_target_prompt": "..."
    }}
  ]
}}
""".strip()


def stage2_prompt(source: str, source_description: str, part: dict[str, Any], candidate: dict[str, Any]) -> str:
    part_name = clean(part.get("canonical_name"))
    return f"""
You are a prompt writer for CreativeFlow PART variation image generation.

Write one generation-ready prompt that changes only the selected part of the
source object. The result must be a tangible 3D asset render, not a 2D
illustration.

Source object:
{source}

Source description:
{source_description}

Selected part:
{part_name}

Part localization / mask hint:
{json.dumps(part, ensure_ascii=False)}

Candidate concept:
{clean(candidate.get("candidate_concept_name"))}

Source part attributes:
{json.dumps(candidate.get("source_part_attributes") or [], ensure_ascii=False)}

Target part attributes:
{json.dumps(candidate.get("target_part_attributes") or [], ensure_ascii=False)}

Attribute mapping:
{clean(candidate.get("attribute_mapping"))}

Part affordance mapping:
{clean(candidate.get("part_affordance_mapping"))}

Socket compatibility:
{clean(candidate.get("socket_compatibility"))}

Scale and orientation constraints:
{clean(candidate.get("scale_orientation_constraints"))}

Preserved global context:
{json.dumps(candidate.get("preserved_global_context") or [], ensure_ascii=False)}

Compatibility risk:
{clean(candidate.get("compatibility_risk"))}

Prompt requirements:
- Change only the selected {part_name}.
- Replace the original selected {part_name}; do not keep both old and new
  {part_name} at the same time.
- The new local form must still read as a plausible {part_name} for the
  {source}, because it preserves the selected part's 3D semantic role.
- Preserve all unselected parts, neighboring parts, and the global source
  structure.
- Keep the selected part attached at the same socket/contact interface, with
  compatible scale and protrusion/orientation.
- Use a visible but local change. It should not be a pasted patch or sticker.
- Single centered 3D asset render, three-quarter view, visible volume and depth.
- Pure white background, no ground, no shadow, no scene.
- Do not mention masks, segmentation, fake mask, or implementation details.
- If the selected part's original material or color changes, describe that as
  the local part replacement only, not as a contradiction.

Return JSON only:
{{
  "part_transfer_description": "...",
  "generation_ready_target_prompt": "...",
  "source_context_preserved": "...",
  "part_change_introduced": "..."
}}
""".strip()


def candidate_rank(candidate: dict[str, Any]) -> int:
    value = clean(candidate.get("identity_fit")).lower()
    intensity = clean(candidate.get("transfer_intensity")).lower()
    risk = clean(candidate.get("compatibility_risk")).lower()
    score = 0 if value == "high" else 1 if value == "medium" else 4
    if intensity == "over-strong":
        score += 4
    if any(term in risk for term in ["global", "unselected", "whole", "identity lost", "not compatible"]):
        score += 3
    if candidate.get("is_decoration") is True:
        score += 10
    name = clean(candidate.get("candidate_concept_name")).lower()
    if any(term in name for term in ["snowflake", "snow_flake", "bird", "butterfly", "fairy", "wing", "ornament"]):
        score += 10
    if any(term in name for term in ["pepperoni", "pizza", "slice", "sticker", "patch", "acorn"]):
        score += 6
    attrs = json.dumps(candidate.get("target_part_attributes") or [], ensure_ascii=False).lower()
    mapping = clean(candidate.get("part_affordance_mapping")).lower()
    if not any(term in (name + " " + attrs + " " + mapping) for term in ["nose", "protrusion", "socket", "beak", "knob", "peg", "bulb", "cone", "wedge", "nozzle", "bump"]):
        score += 5
    return score


def candidate_key(candidate: dict[str, Any]) -> str:
    name = clean(candidate.get("candidate_concept_name")).lower()
    # Collapse obvious duplicate families.
    for family, terms in {
        "beak": ["beak"],
        "button": ["button"],
        "knob": ["knob"],
        "peg": ["peg"],
        "bulb": ["bulb", "bulbous", "sphere", "ball"],
        "cone": ["cone", "conical", "wedge"],
        "nozzle": ["nozzle", "spout"],
        "bump": ["bump", "nub"],
    }.items():
        if any(term in name for term in terms):
            return family
    return re.sub(r"[^a-z0-9]+", "_", name).strip("_")[:40]


def run_stage1(request: dict[str, Any], part: dict[str, Any], count: int) -> list[dict[str, Any]]:
    source = clean(request["object_type"])
    description = clean(request.get("source_description")) or clean((request.get("source_elements") or {}).get("object_identity"))
    payload = call_runtime_json(
        "Follow the CreativeFlow part-only variation instructions. Return JSON only.",
        stage1_prompt(source, description, part, max(count * 2, count)),
        image_paths=planner_image_paths(request, part),
        max_tokens=4096,
    )
    candidates = payload.get("candidates") if isinstance(payload, dict) else None
    if not isinstance(candidates, list) or not candidates:
        raise RuntimeError("Part Stage 1 returned no candidate list")
    return [item for item in candidates if isinstance(item, dict)]


def run_stage2(request: dict[str, Any], part: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    source = clean(request["object_type"])
    description = clean(request.get("source_description")) or json.dumps(request.get("source_elements") or {}, ensure_ascii=False)
    payload = call_runtime_json(
        "Write a part-only generation prompt. Return JSON only.",
        stage2_prompt(source, description, part, candidate),
        image_paths=planner_image_paths(request, part),
        max_tokens=1536,
    )
    if not isinstance(payload, dict):
        raise RuntimeError("Part Stage 2 returned no prompt object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    output = Path(args.output)
    if output.is_file() and not args.refresh:
        cached = json.loads(output.read_text(encoding="utf-8"))
        if cached.get("status") == "completed" and cached.get("schema_version") == "creativeflow.part-two-stage.v1":
            print(output)
            return 0

    request = json.loads(Path(args.input).read_text(encoding="utf-8"))
    part = part_semantics_from_request(request)
    count = int(request.get("candidate_count") or 4)
    source = clean(request["object_type"])

    raw_candidates = run_stage1(request, part, count)
    planned: list[dict[str, Any]] = []
    for index, candidate in enumerate(raw_candidates, start=1):
        candidate = dict(candidate)
        candidate["part_gate"] = {"rank": candidate_rank(candidate)}
        composed = run_stage2(request, part, candidate)
        planned.append({
            "candidate_id": f"part_candidate_{index:02d}",
            **candidate,
            "stage2_prompt_plan": composed,
        })

    sorted_candidates = sorted(
        planned,
        key=lambda item: ((item.get("part_gate") or {}).get("rank", 99), clean(item.get("candidate_concept_name"))),
    )
    selected = []
    seen_families: set[str] = set()
    for item in sorted_candidates:
        key = candidate_key(item)
        if key in seen_families:
            continue
        selected.append(item)
        seen_families.add(key)
        if len(selected) >= count:
            break
    if len(selected) < count:
        for item in sorted_candidates:
            if item not in selected:
                selected.append(item)
            if len(selected) >= count:
                break
    directions: list[dict[str, Any]] = []
    for index, candidate in enumerate(selected, start=1):
        target = clean(candidate.get("candidate_concept_name"))
        plan = candidate.get("stage2_prompt_plan") or {}
        part_name = clean(part.get("canonical_name"))
        raw_target_attrs = [clean(x) for x in (candidate.get("target_part_attributes") or []) if clean(x)]
        # Candidate attributes often include inherited color/material evidence
        # from the source part.  For Part variation this is useful context, but
        # it must not become a hard pixel-level constraint; otherwise Qwen keeps
        # the original carrot-like nose.  Keep shape/role words in the visible
        # prompt and leave color/material free unless the candidate is itself a
        # color/material transfer.
        target_attrs = "、".join(
            x for x in raw_target_attrs
            if not any(term in x.lower() for term in ["color", "orange", "material", "plastic"])
        )
        affordance = clean(candidate.get("part_affordance_mapping"))
        socket = clean(candidate.get("socket_compatibility"))
        scale = clean(candidate.get("scale_orientation_constraints"))
        # Use a concise controlled prompt.  The LLM-composed prompt often
        # restated the old carrot nose as if it should remain visible, which
        # made Qwen keep both old and new parts.  Keep only the semantic mapping.
        prompt = (
            f"基于这张{source}图，SAM3D选中的局部部件是{part_name}。"
            f"目标不是贴图或装饰，而是测试这个3D局部语义是否能迁移。"
            f"请只把这个{part_name}替换成“{target}”形态"
            f"{'，重点局部形态属性：' + target_attrs if target_attrs else ''}。"
            f"新的局部必须仍然能作为{source}的{part_name}来阅读，保持同类功能/感受：{affordance}。"
            f"保持同一个3D连接位置、接触界面和朝向逻辑：{socket}。"
            f"局部大小要和原部件兼容，但允许明显看出形态已经改变：{scale}。"
            f"彻底替换原来的{part_name}，不要保留原部件外观，不要出现两个{part_name}。"
            f"除这个{part_name}外，{source}的整体轮廓、姿态、帽子、围巾、眼睛、嘴巴、身体、手臂、按钮和背景都尽量保持原图。"
            "完整单体三维产品渲染，三维体积清楚，白色干净背景。"
        )
        directions.append({
            "direction_id": f"part_{index:02d}",
            "anchor": target,
            "candidate": candidate,
            "transfer_spec": {
                "graph_anchor": target,
                "prompt": prompt,
                "selected_part": part,
                "fake_mask": False,
                "part_evidence_required": "real_sam3d",
            },
        })

    result = {
        "schema_version": "creativeflow.part-two-stage.v1",
        "status": "completed",
        "stage": "part",
        "source_image_path": request.get("source_image_path"),
        "source_noun": source,
        "part_semantics": part,
        "stage1_candidates": raw_candidates,
        "planned_candidates": planned,
        "selected_candidates": selected,
        "directions": directions,
        "pipeline": [
            "qwen2.5_vl_part_attribute_expansion",
            "qwen2.5_vl_part_prompt_composition",
            "qwen_image_part_only_img2img_or_text2img",
            "hunyuan3d",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
