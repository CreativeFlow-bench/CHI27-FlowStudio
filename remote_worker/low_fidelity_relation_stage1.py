#!/usr/bin/env python3
"""Two-stage Qwen2.5-VL planner for Low Fidelity silhouette transfer.

Stage 1 produces eight candidates through explicit relational expansion and
implicit creative exploration. Stage 2 turns each candidate into a generation
prompt. There is no scoring, filtering, semantic-distance threshold, mask, or
image manipulation in this planner.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from low_fidelity_conceptnet import call_runtime_json, conceptnet_silhouette_evidence


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def stage1_prompt(source: str, source_description: str, relational_evidence: list[str]) -> str:
    evidence_text = ", ".join(relational_evidence) if relational_evidence else "None supplied"
    return f"""
You are a design reasoning assistant for creative 3D asset generation.

Your task is to expand a source object into a set of concept candidates for mild silhouette-level analogical transfer.

The goal is NOT to generate a final object directly.
Instead, generate a diverse set of candidate concepts that:
1. remain meaningfully related to the source object,
2. can inspire small-to-medium contour adjustment rather than a full identity change,
3. preserve some recognizable identity cues of the source,
4. stay in the local neighborhood of the source's silhouette language.

Please use two complementary reasoning modes:
- Explicit relational expansion: based on functional, structural, semantic, perceptual, or metaphorical relations (similar to ConceptNet-style reasoning).
- Implicit creative exploration: propose plausible but less obvious concepts that may not be directly listed in knowledge graphs, but still form meaningful analogical connections.

For each candidate, provide:
1. Candidate concept name
2. Relation to the source
3. Why it is relevant for silhouette transfer
4. Which silhouette traits can be borrowed
5. Transfer distance: near / medium
6. A short target prompt for later 3D generation
7. Source attributes used for comparison
8. Target attributes inferred from the candidate
9. Attribute-level mapping rationale
10. Compatibility risks that should be avoided in generation

Source object:
{source}

Optional source description:
{source_description}

Explicit relational evidence from the source contour neighborhood:
{evidence_text}

In this task, "meaningfully related" means related through shape, structure,
proportion, massing, or perceptual contour. It does NOT mean sharing the same
material, environment, season, story, or topical theme with the source.
The desired result should feel like Figure-2 style contour variation: the
source object is still immediately the same kind of object, and only the
large outer outline, width profile, height ratio, taper, bulge, corner
roundness, or segment rhythm is adjusted.

First reason from the source's current generic contour attributes, then expand
those contour attributes toward concrete shape-bearing nouns. Treat the
explicit relational evidence above as a noisy ConceptNet-style graph
neighborhood, not as mandatory final candidates. Use labels with strong
silhouette value, convert adjectives into concrete shape-bearing donor nouns
when useful, and discard labels that are only topical, moral, linguistic,
material, scene-related, or too abstract to change an object's outline. Fill
the remaining candidates with the implicit creative route.

At least 6 of the 8 candidate concept names must be chosen directly from the
explicit relational evidence above, or be a direct morphology-preserving noun
conversion of an evidence label. For example, "bean shaped" may become "bean"
and "dome shaped" may become "dome". Do not invent generic primitives such as
"sphere", "cone", or "cylinder" unless the corresponding evidence label is
present. Do not invent source-synonym candidates such as a same-material lump
or ball when they do not create a useful new silhouette.

Before selecting a candidate, compare attributes explicitly:
- source silhouette attributes: aspect ratio, stack/segment rhythm, width
  distribution, taper, roundness, symmetry, top-heavy/bottom-heavy massing,
  and whether recognizable identity cues can still be placed naturally.
- target silhouette attributes: the same dimensions for the candidate.
- mapping: which target attributes will replace or bend source attributes,
  and which source identity attributes stay fixed.

Reject candidates whose target attributes cannot preserve the source identity
or whose transfer would mainly create a literal unrelated object. For example,
an elongated donor is not enough by itself; it must still support the source's
recognizable part layout and category identity.
Reject candidates whose silhouette would collapse or replace the source's
functional layout. For example, a chair cannot become a freestanding column,
a sneaker cannot become a crescent, and a robot toy cannot become a single
smooth pillar, because the source's parts no longer have natural positions.

The source attributes must be read from the source image and description. Do
not invent them and do not copy the same attribute list into every target. If
the source has a broad lower body and smaller upper head, describe it as
bottom-heavy, not top-heavy. Each candidate must have target attributes
specific to that candidate, and the mapping must say exactly which source
attribute changes and which source identity cues remain fixed.

The target_attributes_inferred field must contain candidate-specific geometry
words derived from the target itself. For example, a crescent target should
mention curved/asymmetric arc massing, a columniform target should mention
tall vertical column massing, a disciform target should mention flattened
disc-like massing, and a bulb-shaped target should mention swollen bulbous
massing with taper. Never reuse the same target attribute list for all
candidates.
Also state whether the candidate is a mild adjustment, moderate adjustment,
or over-strong replacement. Only mild or moderate candidates should be marked
high/medium identity_fit.

Avoid donors that are merely the source's own material, a same-object synonym,
or a trivial restatement of the current silhouette. Avoid donors whose
identity would overpower the source, such as food, vehicles, people,
characters, landscapes, or scenes, unless their geometry can be abstracted
cleanly and still keep the source recognizable as {source}.
Prefer modifier-like shape donors such as bean-like, bell-like, barrel-like,
bulb-like, dome-like, oval-like, tapered, wider-base, squarer, softer-cornered,
or slightly elongated, when they preserve the part layout. Avoid full-object
replacement donors that make the result read as the donor rather than as
{source}.

Use each donor as a whole-envelope silhouette donor. Do not turn a donor into
a replacement head, hat, accessory, material, scene, or a second object. The
candidate concept must describe the complete outer contour and major massing
of the source.

Output 8 candidates in a structured list.
Prioritize silhouette-relevant concepts rather than texture/material-only concepts.
Avoid concepts that are only semantically related but have weak silhouette value.
Prefer compact single-object shape donors, simple artifact forms, geometric
forms, and natural formations that can be represented as one centered object.
Avoid landscapes, ranges, broad environments, named characters, moral
attributes, emotions, source accessories, source materials, and topic words
that do not directly donate a visible outer contour.

The eight candidates must not be minor variants of the same primitive, but
their transfer intensity must remain mild to moderate. Spread them across
overall aspect ratio, width distribution, tapering, corner roundness, bulge,
and segment rhythm. Do not choose candidates that erase required parts or
turn the source into a single unrelated geometric object.

Return JSON only in this exact structure:
{{
  "candidates": [
    {{
      "candidate_concept_name": "...",
      "reasoning_mode": "explicit relational expansion or implicit creative exploration",
      "source_attributes_compared": ["..."],
      "target_attributes_inferred": ["..."],
      "attribute_mapping": "...",
      "preserved_identity_cues": ["..."],
      "compatibility_risk": "...",
      "identity_fit": "high or medium or low",
      "transfer_intensity": "mild or moderate or over-strong",
      "relation_to_source": "...",
      "silhouette_relevance": "...",
      "silhouette_traits_to_borrow": "...",
      "transfer_distance": "near or medium or far",
      "short_target_prompt": "..."
    }}
  ]
}}
""".strip()


def stage2_prompt(source: str, source_description: str, candidate: dict[str, Any]) -> str:
    return f"""
You are a creative prompt writer for 3D asset generation.

Given a source object and a candidate transfer concept, write a target generation prompt that performs silhouette-level transfer.

The prompt should:
1. preserve recognizable identity cues of the source object,
2. modify the outer contour and major shape language according to the candidate concept,
3. focus on silhouette, massing, proportion, and overall shape rhythm,
4. avoid overemphasizing texture or small decorative details,
5. be suitable as a prompt for later target 3D generation.

The source object is always the grammatical and visual subject. The candidate
concept is only a donor for the source object's complete outer envelope. Never
generate the candidate itself. Apply the donor strongly enough that the result
has an unmistakably different silhouette at thumbnail scale, while retaining
the source's category-defining elements and arrangement.

Before writing the final prompt, abstract the donor into geometry only: width
distribution, aspect ratio, taper, bulge, lobe pattern, massing, and contour
rhythm. Also identify literal donor features that must NOT transfer. For
example, a vessel may donate its width profile but never its handle, opening,
rim, hoops, label, socket, or material. The output must remain the source, not a
hybrid object assembled from literal donor parts.

Please output:
1. A concise silhouette transfer description
2. A generation-ready target prompt
3. A short explanation of what source identity is preserved
4. A short explanation of what silhouette change is introduced

Source object:
{source}

Source description:
{source_description}

Candidate concept:
{clean(candidate.get('candidate_concept_name'))}

Source attributes compared:
{json.dumps(candidate.get('source_attributes_compared') or [], ensure_ascii=False)}

Target attributes inferred:
{json.dumps(candidate.get('target_attributes_inferred') or [], ensure_ascii=False)}

Attribute mapping:
{clean(candidate.get('attribute_mapping'))}

Preserved identity cues:
{json.dumps(candidate.get('preserved_identity_cues') or [], ensure_ascii=False)}

Compatibility risk to avoid:
{clean(candidate.get('compatibility_risk'))}

Relation to source:
{clean(candidate.get('relation_to_source'))}

Silhouette traits to borrow:
{clean(candidate.get('silhouette_traits_to_borrow'))}

The generation-ready prompt must also require a flat pure-white background,
no ground, no cast shadow, no scene, and one complete centered object.
It must describe a tangible 3D asset render, not a flat illustration, icon,
line drawing, poster, or 2D graphic. Use a three-quarter product-render camera
view with visible volume and depth.
Write the generation-ready prompt as one concise imperative sentence in
Chinese. The final prompt MUST NOT include the candidate concept name or any
literal donor noun. Convert the donor into geometric deltas only. Use this
semantic structure:
保持[source]仍然是同一个[source]，颜色、材质、视角、光影、姿态、主要部件和核心识别特征都与输入图一致；
只微调整体轮廓：[attribute delta, such as slightly wider / taller / shorter /
more rounded / more tapered / more bulbous / smoother curve / squarer corner /
different width distribution]；三维模型渲染，四分之三视角，有体积和深度；纯白背景、无地面、无投影、单体。

Explicitly mention the borrowed massing, proportion, and contour rhythm. Do
not describe the candidate as the generated object. Do not write phrases like
"like a bean", "like a barrel", "like a bell", or "like [candidate]". The model
must read the result as the SAME source object with a local silhouette-family
variation, not as another object.
Use the attribute mapping above as the main content of the prompt. If a donor
has a literal function, material, scene, or small part that is not part of the
mapped silhouette attributes, exclude it from the generation prompt.
Never list source identity cues as literal donor features to avoid. The source
identity cues, such as accessories, face parts, limbs, and semantic category
markers, must be explicitly preserved. Only donor-specific literal features
should be avoided.

Return JSON only in this exact structure:
{{
  "silhouette_transfer_description": "...",
  "generation_ready_target_prompt": "...",
  "source_identity_preserved": "...",
  "silhouette_change_introduced": "...",
  "literal_donor_features_to_avoid": "..."
}}
""".strip()


def resolve_relational_evidence(source: str, description: str, request: dict[str, Any]) -> dict[str, Any]:
    manual = [clean(item) for item in request.get("conceptnet_silhouette_evidence") or [] if clean(item)]
    if manual and request.get("use_manual_conceptnet_evidence"):
        return {
            "mode": "manual",
            "conceptnet_silhouette_evidence": manual,
            "seed_planner": None,
            "conceptnet_rows": [],
        }
    dynamic = conceptnet_silhouette_evidence(
        source=source,
        source_description=description,
        source_image_path=clean(request.get("source_image_path")),
        count=max(24, int(request.get("candidate_count") or 4) * 6),
    )
    if not dynamic.get("conceptnet_silhouette_evidence") and manual:
        dynamic["mode"] = "manual_fallback"
        dynamic["conceptnet_silhouette_evidence"] = manual
    else:
        dynamic["mode"] = "runtime_conceptnet"
    return dynamic


def run_stage1(request: dict[str, Any]) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    source = clean(request["object_type"])
    description = clean(request.get("source_description")) or "Infer the source function, structure, and visible appearance from the attached image."
    evidence_payload = resolve_relational_evidence(source, description, request)
    relational_evidence = [
        clean(item)
        for item in evidence_payload.get("conceptnet_silhouette_evidence") or []
        if clean(item)
    ]
    payload = call_runtime_json(
        "Follow the user's two-route concept-expansion instructions. Return JSON only.",
        stage1_prompt(
            source,
            description,
            relational_evidence,
        ),
        image_paths=[request["source_image_path"]],
        max_tokens=4096,
    )
    candidates = payload.get("candidates") if isinstance(payload, dict) else None
    if not isinstance(candidates, list) or not candidates:
        raise RuntimeError("Stage 1 returned no candidate list")
    return description, evidence_payload, [item for item in candidates if isinstance(item, dict)][:8]


def run_stage2(request: dict[str, Any], source_description: str, candidate: dict[str, Any]) -> dict[str, Any]:
    payload = call_runtime_json(
        "Follow the user's silhouette-transfer prompt-writing instructions. Return JSON only.",
        stage2_prompt(clean(request["object_type"]), source_description, candidate),
        image_paths=[request["source_image_path"]],
        max_tokens=1536,
    )
    if not isinstance(payload, dict):
        raise RuntimeError("Stage 2 returned no prompt object")
    return payload


def candidate_fit_rank(candidate: dict[str, Any]) -> int:
    value = clean(candidate.get("identity_fit")).lower()
    if value == "high":
        return 0
    if value == "medium":
        return 1
    if value == "low":
        return 3
    risk = clean(candidate.get("compatibility_risk")).lower()
    if risk and risk not in {"none", "no major risk", "low"}:
        return 2
    return 1


def neutral_shape_delta(candidate: dict[str, Any]) -> str:
    name = clean(candidate.get("candidate_concept_name")).lower()
    attrs = " ".join(clean(v).lower() for v in candidate.get("target_attributes_inferred") or [])
    mapping = clean(candidate.get("attribute_mapping")).lower()
    text = f"{name} {attrs} {mapping}"
    if any(term in text for term in ["barrel", "bulb", "plum", "olive"]):
        return "下半部宽度略增加，侧面曲线更饱满，整体体块更圆润紧凑"
    if any(term in text for term in ["bean", "almond"]):
        return "主体曲线略更柔和，左右宽度分布有轻微变化，但仍保持正面可识别的对称感"
    if any(term in text for term in ["bell"]):
        return "下半部略微外扩，上半部略收窄，整体高度和核心部件位置保持不变"
    if any(term in text for term in ["dome"]):
        return "头身外轮廓更圆滑，上部弧线更连续，底部体块仍保持稳定"
    if any(term in text for term in ["egg", "ellipsoid", "oval"]):
        return "整体高度略拉长，外轮廓更椭圆，宽度变化保持在轻微范围"
    if any(term in text for term in ["block", "cube", "rectangular", "squarer"]):
        return "主体边缘略更方正，转角仍保持柔和，主要部件位置不变"
    if any(term in text for term in ["taper", "cone", "narrow"]):
        return "上半部略收窄、下半部保持稳定，整体比例只做轻微调整"
    return "整体宽度、高度和外侧曲线做轻微变化，主体身份、颜色、材质、部件位置和视角保持一致"


def identity_cue_text(source: str, candidate: dict[str, Any]) -> str:
    cues = [clean(item) for item in candidate.get("preserved_identity_cues") or [] if clean(item)]
    if cues:
        return "、".join(cues[:10])
    return f"{source}的颜色、材质、姿态、主要部件、配件和核心识别特征"


def low_execution_prompt(source: str, candidate: dict[str, Any]) -> str:
    delta = neutral_shape_delta(candidate)
    cues = identity_cue_text(source, candidate)
    return (
        f"保持输入图中的{source}仍然是同一个{source}，颜色、材质、视角、光影、姿态、表情和所有核心部件都与输入图一致；"
        f"保留{cues}；只微调整体外轮廓：{delta}。"
        "不要改变物体类别，不要生成任何新的物体或道具，不要改变配色、材质、相机角度和光照方向。"
        "三维模型渲染，四分之三视角，有体积和深度；纯白背景、无地面、无投影、单体。"
    )


def source_layout_family(source: str, description: str) -> str:
    text = f"{source} {description}".lower()
    if any(term in text for term in ["snowman", "stacked snow", "snow body"]):
        return "stacked_character"
    if any(term in text for term in ["seat", "back", "armchair", "chair", "sofa"]):
        return "seating"
    if any(term in text for term in ["sneaker", "shoe", "sole", "toe", "heel", "lace"]):
        return "footwear"
    if any(term in text for term in ["robot", "toy-like mechanical", "torso", "limbs"]):
        return "humanoid_toy"
    if any(term in text for term in ["teapot", "spout", "handle", "lid"]):
        return "vessel_with_spout"
    if any(term in text for term in ["lantern", "light chamber", "frame", "portable"]):
        return "upright_vessel_frame"
    return "generic"


def candidate_gate_penalty(source: str, description: str, candidate: dict[str, Any]) -> tuple[int, list[str]]:
    name = clean(candidate.get("candidate_concept_name")).lower()
    attrs = " ".join(clean(v).lower() for v in candidate.get("target_attributes_inferred") or [])
    mapping = clean(candidate.get("attribute_mapping")).lower()
    text = f"{name} {attrs} {mapping}"
    family = source_layout_family(source, description)
    reasons: list[str] = []
    penalty = candidate_fit_rank(candidate)

    intensity = clean(candidate.get("transfer_intensity")).lower()
    if intensity == "over-strong":
        penalty += 5
        reasons.append("over-strong transfer")

    single_axis = {"column", "columniform", "pillar", "cylinder", "cylindric", "sphere", "ball", "cone"}
    flat_or_arc = {"crescent", "crescent moon", "disc", "disciform", "compact disc"}
    noisy_topic = {"piano", "bass", "car", "altitude", "level", "hearted", "pitched", "word"}
    if any(term in text for term in noisy_topic):
        penalty += 8
        reasons.append("graph label is topical noise rather than silhouette donor")
    if family in {"seating", "humanoid_toy"} and any(term in text for term in single_axis):
        penalty += 6
        reasons.append("single-axis donor would erase multi-part layout")
    if family in {"seating", "humanoid_toy"} and any(term in text for term in flat_or_arc):
        penalty += 5
        reasons.append("flat or arc donor would overtake multi-part 3D layout")
    if family == "stacked_character" and any(term in text for term in {"crescent", "disc", "disciform", "compact disc"}):
        penalty += 6
        reasons.append("flat or arc donor would erase stacked character layout")
    if family == "stacked_character" and any(term in text for term in {"column", "columniform", "pillar", "cylinder", "cylindric", "sphere", "ball", "cone"}):
        penalty += 4
        reasons.append("single primitive donor is too strong for stacked character")
    if family == "footwear" and any(term in text for term in single_axis | flat_or_arc):
        penalty += 6
        reasons.append("donor would erase sneaker sole/toe/heel layout")
    if family == "vessel_with_spout" and any(term in text for term in flat_or_arc):
        penalty += 5
        reasons.append("donor would flatten spout/handle vessel layout")
    if "literal" in clean(candidate.get("compatibility_risk")).lower() or "lose" in clean(candidate.get("compatibility_risk")).lower():
        penalty += 2
        reasons.append("candidate risk says identity may be lost")
    if not reasons:
        reasons.append("passes mild silhouette gate")
    return penalty, reasons


def unique_by_candidate_name(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for candidate in candidates:
        name = clean(candidate.get("candidate_concept_name")).lower()
        if not name or name in seen:
            continue
        seen.add(name)
        unique.append(candidate)
    return unique


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    output = Path(args.output)
    if output.is_file() and not args.refresh:
        try:
            cached = json.loads(output.read_text(encoding="utf-8"))
        except Exception:
            cached = {}
        if cached.get("status") == "completed" and cached.get("schema_version") == "creativeflow.low-two-stage.v1":
            print(output)
            return 0

    request = json.loads(Path(args.input).read_text(encoding="utf-8"))
    source = clean(request["object_type"])
    source_description, evidence_payload, candidates = run_stage1(request)
    planned_candidates: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates, start=1):
        composed = run_stage2(request, source_description, candidate)
        planned_candidates.append(
            {
                "candidate_id": f"low_candidate_{index:02d}",
                **candidate,
                "stage2_prompt_plan": composed,
            }
        )

    directions = []
    candidate_count = int(request.get("candidate_count") or 8)
    candidate_count = max(1, min(candidate_count, len(planned_candidates)))
    for candidate in planned_candidates:
        penalty, reasons = candidate_gate_penalty(source, source_description, candidate)
        candidate["low_fidelity_gate"] = {"penalty": penalty, "reasons": reasons}
    ranked_candidates = sorted(
        planned_candidates,
        key=lambda item: (
            (item.get("low_fidelity_gate") or {}).get("penalty", 99),
            clean(item.get("candidate_concept_name")),
        ),
    )
    selected_candidates = unique_by_candidate_name(ranked_candidates)[:candidate_count]
    for index, candidate in enumerate(selected_candidates, start=1):
        target = clean(candidate.get("candidate_concept_name"))
        prompt = low_execution_prompt(source, candidate)
        directions.append(
            {
                "direction_id": f"low_fidelity_{index:02d}",
                "anchor": target,
                "candidate": candidate,
                "transfer_spec": {"graph_anchor": target, "prompt": prompt},
            }
        )

    result = {
        "schema_version": "creativeflow.low-two-stage.v1",
        "status": "completed",
        "stage": "low_fidelity",
        "source_image_path": request["source_image_path"],
        "source_noun": source,
        "source_description": source_description,
        "conceptnet_evidence": evidence_payload,
        "stage1_candidates": candidates,
        "planned_candidates": planned_candidates,
        "selected_candidates": selected_candidates,
        "directions": directions,
        "pipeline": [
            "qwen2.5_vl_explicit_and_implicit_candidate_expansion",
            "qwen2.5_vl_silhouette_prompt_composition",
            "qwen_image_img2img",
            "hunyuan3d",
        ],
        "scoring": None,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
