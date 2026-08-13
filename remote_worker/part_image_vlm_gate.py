#!/usr/bin/env python3
"""VLM gate for CreativeFlow Part image candidates.

This is a semantic gate, not a pixel scorer. It checks whether a generated
candidate truly performs local selected-part replacement while preserving the
source object and 3D context.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def image_data_url(path: str | Path) -> str:
    path = Path(path)
    suffix = path.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/webp" if suffix == ".webp" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def call_vlm_json(
    *,
    api_base: str,
    model: str,
    prompt: str,
    image_paths: list[str | Path],
    temperature: float = 0.0,
    max_tokens: int = 1400,
) -> dict[str, Any] | None:
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for path in image_paths:
        if Path(path).is_file():
            content.append({"type": "image_url", "image_url": {"url": image_data_url(path)}})
    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a strict visual QA judge for CreativeFlow Part variation. "
                    "Return JSON only. Do not be polite; identify failures."
                ),
            },
            {"role": "user", "content": content},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        api_base.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=240) as response:
            payload = json.loads(response.read().decode("utf-8"))
        text = str(payload["choices"][0]["message"]["content"]).strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S)
        start = text.find("{")
        if start < 0:
            return None
        decoded, _ = json.JSONDecoder().raw_decode(text[start:])
        return decoded if isinstance(decoded, dict) else None
    except Exception as exc:
        print(f"[part_image_vlm_gate] VLM error: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return None


def judge_prompt(
    *,
    object_type: str,
    part_name: str,
    part_semantics: dict[str, Any],
    anchor: str,
    generation_phrase: str,
) -> str:
    return f"""
We need to judge whether image B is a valid CreativeFlow Part variation of image A.

Image A: original source image.
Image B: generated candidate image.

Source object: {object_type}
Selected SAM3D part: {part_name}
Selected part semantics:
{json.dumps(part_semantics, ensure_ascii=False)}

Candidate transfer concept: {anchor}
Candidate generation phrase:
{generation_phrase}

Expected result:
- The source object identity is preserved.
- Only the selected part is creatively replaced.
- The replacement must be a real 3D local component in the original 3D context.
- The candidate should show meaningful analogical design, not trivial color/noise.
- It should be suitable for later single-view Hunyuan3D reconstruction.

Important failure cases:
- HIGHEST REJECT: donor appears as side-body decoration, sticker, badge, decal, charm, prop, or second object. This means the selected SAM3D part was NOT replaced.
- HIGHEST REJECT: donor modifies the wrong part/location instead of the selected SAM3D part.
- unselected parts or global body are redesigned heavily.
- selected part remains almost unchanged.
- candidate adds water stream, hose, cable, beam, motion effect, text, scene, or background object.
- for nozzle/outlet: only the frontmost outlet tip/rim on the barrel axis may change; no side-mounted lens/flower/shell/coral, no second nozzle, no hose, no water stream.
- for grip/handle: only the handle/grip may change; no dangling appendage, charm, chain, creature, face, or extra component.

Identity judging rule:
- Do NOT mark source_identity_preserved=false merely because the selected part changed.
- A candidate preserves identity if the object category and unselected components remain visually the same.
- For nozzle/outlet/aperture/rim tasks, changing the front aperture/rim is the intended edit; judge identity by the rest of the gun body, tank, grip, trigger, barrel casing, colors, pose, and camera.
- If the donor is placed on the side body while the original selected part remains unchanged, mark bad_side_decoration=true, locality_ok=false, selected_part_changed=false, and rejection_score should be near 100.

Return JSON only:
{{
  "source_identity_preserved": true/false,
  "selected_part_changed": true/false,
  "locality_ok": true/false,
  "creative_analogy_visible": true/false,
  "single_object_3d_render": true/false,
  "bad_side_decoration": true/false,
  "wrong_part_modified": true/false,
  "bad_extra_prop_or_second_component": true/false,
  "bad_water_stream_or_hose": true/false,
  "bad_global_redesign": true/false,
  "background_ok_for_3d": true/false,
  "hunyuan3d_ready": true/false,
  "creativity_score": 0-5,
  "locality_score": 0-5,
  "identity_score": 0-5,
  "overall_score": 0-100,
  "rejection_score": 0-100,
  "decision": "accept" | "maybe" | "reject",
  "short_reason": "one short sentence",
  "best_use": "send_to_3d | rerun_prompt | discard"
}}
""".strip()


def normalize_decision(record: dict[str, Any]) -> dict[str, Any]:
    bool_keys = [
        "source_identity_preserved",
        "selected_part_changed",
        "locality_ok",
        "creative_analogy_visible",
        "single_object_3d_render",
        "bad_side_decoration",
        "wrong_part_modified",
        "bad_extra_prop_or_second_component",
        "bad_water_stream_or_hose",
        "bad_global_redesign",
        "background_ok_for_3d",
        "hunyuan3d_ready",
    ]
    for key in bool_keys:
        record[key] = bool(record.get(key))
    for key in ["creativity_score", "locality_score", "identity_score"]:
        try:
            record[key] = max(0, min(5, int(float(record.get(key, 0)))))
        except Exception:
            record[key] = 0
    try:
        quality_score = max(0, min(100, int(float(record.get("overall_score", 0)))))
    except Exception:
        quality_score = 0
    try:
        vlm_rejection_score = max(0, min(100, int(float(record.get("rejection_score", 0)))))
    except Exception:
        vlm_rejection_score = 0
    rejection_reasons: list[str] = []
    rejection_score = 0
    if record.get("wrong_part_modified"):
        rejection_score = max(rejection_score, 100)
        rejection_reasons.append("wrong_part_modified")
    if record.get("bad_side_decoration"):
        rejection_score = max(rejection_score, 100)
        rejection_reasons.append("side_body_decoration")
    if record.get("bad_extra_prop_or_second_component"):
        rejection_score = max(rejection_score, 90)
        rejection_reasons.append("extra_prop_or_second_component")
    if record.get("bad_water_stream_or_hose"):
        rejection_score = max(rejection_score, 88)
        rejection_reasons.append("water_stream_or_hose")
    if record.get("bad_global_redesign"):
        rejection_score = max(rejection_score, 82)
        rejection_reasons.append("global_redesign")
    if not record["source_identity_preserved"]:
        rejection_score = max(rejection_score, 78)
        rejection_reasons.append("source_identity_lost")
    if not record["locality_ok"]:
        rejection_score = max(rejection_score, 74)
        rejection_reasons.append("locality_failed")
    if not record["selected_part_changed"]:
        rejection_score = max(rejection_score, 55)
        rejection_reasons.append("selected_part_unchanged")
    if not record["creative_analogy_visible"]:
        rejection_score = max(rejection_score, 35)
        rejection_reasons.append("creative_analogy_not_visible")
    rejection_score = max(rejection_score, vlm_rejection_score)
    if rejection_score:
        quality_score = min(quality_score, max(0, 100 - rejection_score))
    record["overall_score"] = quality_score
    record["quality_score"] = quality_score
    record["rejection_score"] = rejection_score
    record["rejection_reasons"] = rejection_reasons
    hard_fail = any(
        record.get(key)
        for key in [
            "wrong_part_modified",
            "bad_side_decoration",
            "bad_extra_prop_or_second_component",
            "bad_water_stream_or_hose",
            "bad_global_redesign",
        ]
    )
    if (
        hard_fail
        or not record["source_identity_preserved"]
        or not record["selected_part_changed"]
        or not record["locality_ok"]
    ):
        record["decision"] = "reject"
        record["best_use"] = "discard" if hard_fail else "rerun_prompt"
    elif record["overall_score"] >= 72 and record["hunyuan3d_ready"]:
        record["decision"] = "accept"
        record["best_use"] = "send_to_3d"
    elif record["overall_score"] >= 55:
        record["decision"] = "maybe"
        record["best_use"] = "rerun_prompt"
    else:
        record["decision"] = "reject"
        record["best_use"] = "rerun_prompt"
    if record.get("bad_side_decoration"):
        record["short_reason"] = (
            "Donor concept appears as a side-body decoration/sticker/extra prop instead of replacing the selected SAM3D part."
        )
    elif record.get("wrong_part_modified"):
        record["short_reason"] = "Wrong location was modified; the selected SAM3D part was not correctly replaced."
    elif record.get("bad_extra_prop_or_second_component"):
        record["short_reason"] = "Candidate adds an extra prop/second component instead of a local part replacement."
    elif record.get("bad_water_stream_or_hose"):
        record["short_reason"] = "Candidate adds water stream or hose-like effect, which is outside the selected part."
    else:
        record["short_reason"] = clean(record.get("short_reason")) or "No reason returned."
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage2-result", required=True)
    parser.add_argument("--stage1-result", required=True)
    parser.add_argument("--source-image", required=True)
    parser.add_argument("--object-type", required=True)
    parser.add_argument("--part-name", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--api-base", default=os.getenv("CF_TEXT_LLM_API_BASE", "http://127.0.0.1:18084/v1"))
    parser.add_argument("--model", default=os.getenv("CF_TEXT_LLM_MODEL", "qwen3-planner"))
    args = parser.parse_args()

    stage2_path = Path(args.stage2_result)
    stage1_path = Path(args.stage1_result)
    stage2 = json.loads(stage2_path.read_text(encoding="utf-8"))
    stage1 = json.loads(stage1_path.read_text(encoding="utf-8"))
    part_semantics = stage1.get("part_semantics") or {}
    directions = {row.get("direction_id"): row for row in stage1.get("directions") or []}

    results: list[dict[str, Any]] = []
    for item in stage2.get("items") or []:
        direction = directions.get(item.get("direction_id")) or {}
        spec = direction.get("transfer_spec") or {}
        candidate = direction.get("candidate") or {}
        image_path = item.get("image_path")
        prompt = judge_prompt(
            object_type=args.object_type,
            part_name=args.part_name,
            part_semantics=part_semantics,
            anchor=clean(item.get("anchor") or spec.get("graph_anchor")),
            generation_phrase=clean(spec.get("generation_phrase") or candidate.get("generation_phrase")),
        )
        raw = call_vlm_json(
            api_base=args.api_base,
            model=args.model,
            prompt=prompt,
            image_paths=[args.source_image, image_path],
        )
        gate = normalize_decision(raw or {"decision": "reject", "short_reason": "VLM did not return valid JSON"})
        results.append(
            {
                "direction_id": item.get("direction_id"),
                "anchor": item.get("anchor"),
                "image_path": image_path,
                "candidate": candidate,
                "stage2_visual_acceptance": item.get("visual_acceptance"),
                "vlm_gate": gate,
            }
        )

    accepted = [row for row in results if (row.get("vlm_gate") or {}).get("decision") == "accept"]
    maybes = [row for row in results if (row.get("vlm_gate") or {}).get("decision") == "maybe"]
    output = {
        "schema_version": "creativeflow.part-image-vlm-gate.v1",
        "status": "completed",
        "stage2_result": str(stage2_path),
        "stage1_result": str(stage1_path),
        "source_image": args.source_image,
        "object_type": args.object_type,
        "part_name": args.part_name,
        "items": results,
        "accepted_count": len(accepted),
        "maybe_count": len(maybes),
        "rejected_count": len(results) - len(accepted) - len(maybes),
        "accepted_for_3d": [
            {
                "direction_id": row["direction_id"],
                "anchor": row["anchor"],
                "image_path": row["image_path"],
                "overall_score": row["vlm_gate"]["overall_score"],
                "short_reason": row["vlm_gate"]["short_reason"],
            }
            for row in sorted(accepted, key=lambda r: r["vlm_gate"]["overall_score"], reverse=True)
        ],
    }
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output["accepted_for_3d"], ensure_ascii=False, indent=2))
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
