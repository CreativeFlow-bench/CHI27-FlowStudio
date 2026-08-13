#!/usr/bin/env python3
"""Planner stability test: white models + semantic parts -> KG attribute plan -> diverged words.

Selects a fixed set of 10 white models, each with a grounded inventory of
semantic parts, then runs the real CreativeFlow planner pipeline against the
live planner LLM (default :18085) for two representative parts per model:

  1. planner_seed_attributes(stage="part")  -> the KG-required attribute plan
  2. expand_attribute_queries(stage="part") -> diverged related words per graph

Outputs a machine-readable report.json plus a human-readable report.md under
--out-dir. Failures (planner instability) are captured per part, not fatal.

Run on the GPU server:
    /root/autodl-tmp/venvs/torch5090/bin/python \
      /root/flowstudio_app/scripts/planner_stability_test.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


WORKER_ROOT = Path(os.getenv("CF_WORKER_ROOT", "/root/flowstudio_app/remote_worker"))
PIPELINE_ROOT = Path(
    os.getenv("CF_TRANSFER_PIPELINE_ROOT", "/root/creativeflow_pipeline")
)
sys.path.insert(0, str(WORKER_ROOT))
sys.path.insert(0, str(PIPELINE_ROOT))

os.environ.setdefault("CF_TEXT_LLM_API_BASE", "http://127.0.0.1:18085/v1")
os.environ.setdefault("CF_VISION_LLM_API_BASE", "http://127.0.0.1:18085/v1")
os.environ.setdefault("CF_TEXT_LLM_MODEL", "qwen3-planner")

from pipeline_transfer_engine import SourceSpec  # noqa: E402
from variation_graph_directions import (  # noqa: E402
    FACETS,
    expand_attribute_queries_unconstrained,
    planner_seed_attributes,
)


# 10 white models from backend/storage/files/white-models/manifest.json, with
# canonical semantic parts grounded in the object's real anatomy.
WHITE_MODEL_PARTS: list[dict[str, Any]] = [
    {
        "model": "white:christmas:snowman",
        "label": "Snowman",
        "object_type": "snowman",
        "obj_path": "/files/white-models/christmas/snowman.obj",
        "intent": "把这个雪人的帽子做得更夸张有趣，保留雪人身份。",
        "parts": [
            {
                "canonical_name": "top hat",
                "semantic_role": "headwear",
                "shape": "tall cylindrical brimmed hat",
                "attachment": "rests on the head sphere",
                "function": "head covering and festive silhouette",
                "confidence": 0.92,
                "evidence": ["uppermost segment with cylindrical crown", "brim wider than head"],
            },
            {
                "canonical_name": "carrot nose",
                "semantic_role": "facial feature",
                "shape": "tapered orange cone protruding forward",
                "attachment": "inserted in the lower front of the head sphere",
                "function": "nose landmark of the face",
                "confidence": 0.9,
                "evidence": ["forward-pointing cone at face center", "contrasting thin shape"],
            },
            {
                "canonical_name": "scarf",
                "semantic_role": "neck accessory",
                "shape": "wrapped band with trailing ends",
                "attachment": "wrapped around the neck junction between head and body",
                "function": "neck covering and color accent",
                "confidence": 0.85,
                "evidence": ["band between head and body spheres", "hanging tail on one side"],
            },
        ],
    },
    {
        "model": "white:christmas:santa-head",
        "label": "Santa Head",
        "object_type": "santa head",
        "obj_path": "/files/white-models/christmas/santa-head.obj",
        "intent": "让圣诞老人的胡子更蓬松饱满。",
        "parts": [
            {
                "canonical_name": "santa hat",
                "semantic_role": "headwear",
                "shape": "soft conical cap with folded brim and pom-pom",
                "attachment": "sits on top of the head and forehead",
                "function": "head covering and festive marker",
                "confidence": 0.93,
                "evidence": ["conical mass above the head", "pom ball at the tip"],
            },
            {
                "canonical_name": "beard",
                "semantic_role": "facial hair",
                "shape": "large fluffy mass covering the lower face",
                "attachment": "covers the jaw and chin, wrapping around the mouth",
                "function": "facial hair defining the face silhouette",
                "confidence": 0.94,
                "evidence": ["bulky rounded mass below the nose", "wraps around cheeks"],
            },
            {
                "canonical_name": "eyebrows",
                "semantic_role": "facial feature",
                "shape": "two thick arched ridges above the eyes",
                "attachment": "on the upper forehead above the eye sockets",
                "function": "expression and face framing",
                "confidence": 0.72,
                "evidence": ["two raised ridges above the eyes"],
            },
        ],
    },
    {
        "model": "white:christmas:candle",
        "label": "Candle",
        "object_type": "candle",
        "obj_path": "/files/white-models/christmas/candle.obj",
        "intent": "把烛火做成更华丽的形态。",
        "parts": [
            {
                "canonical_name": "flame",
                "semantic_role": "light source",
                "shape": "teardrop flame rising from the wick",
                "attachment": "sits on top of the wick at the candle top",
                "function": "emits light and heat",
                "confidence": 0.9,
                "evidence": ["small teardrop volume at the very top", "distinct from wax body"],
            },
            {
                "canonical_name": "wick",
                "semantic_role": "combustion core",
                "shape": "thin vertical stalk inside the flame base",
                "attachment": "embedded in the top center of the wax body",
                "function": "conducts melted wax to the flame",
                "confidence": 0.78,
                "evidence": ["thin vertical column between wax and flame"],
            },
            {
                "canonical_name": "wax body",
                "semantic_role": "main body",
                "shape": "cylindrical column with slight taper",
                "attachment": "the main mass standing on the base",
                "function": "fuel reservoir and structural body",
                "confidence": 0.95,
                "evidence": ["dominant cylindrical volume", "vertical walls and base"],
            },
        ],
    },
    {
        "model": "white:christmas:sled",
        "label": "Sled",
        "object_type": "sled",
        "obj_path": "/files/white-models/christmas/sled.obj",
        "intent": "让雪橇的滑板更流线、更有速度感。",
        "parts": [
            {
                "canonical_name": "runner",
                "semantic_role": "ground contact rail",
                "shape": "long curved blade that touches the snow",
                "attachment": "below the side rails, curving up at the front",
                "function": "slides over snow and steers",
                "confidence": 0.93,
                "evidence": ["two long thin curved blades under the sled", "upturned front tips"],
            },
            {
                "canonical_name": "seat",
                "semantic_role": "sitting surface",
                "shape": "flat horizontal platform between the rails",
                "attachment": "spans across the top of the sled frame",
                "function": "supports the rider",
                "confidence": 0.88,
                "evidence": ["wide flat slab between the two sides"],
            },
            {
                "canonical_name": "side rail",
                "semantic_role": "frame member",
                "shape": "curved bar running along each side",
                "attachment": "connects the seat to the runners",
                "function": "structural frame and hand grip",
                "confidence": 0.84,
                "evidence": ["two parallel curved bars at the sides"],
            },
        ],
    },
    {
        "model": "white:christmas:bell",
        "label": "Bell",
        "object_type": "bell",
        "obj_path": "/files/white-models/christmas/bell.obj",
        "intent": "把铃铛的钟体做成更有层次的花瓣形态。",
        "parts": [
            {
                "canonical_name": "clapper",
                "semantic_role": "striker",
                "shape": "small sphere hanging inside the bell mouth",
                "attachment": "suspended from the crown inside the body",
                "function": "strikes the body to produce sound",
                "confidence": 0.86,
                "evidence": ["small sphere visible inside the open mouth"],
            },
            {
                "canonical_name": "handle",
                "semantic_role": "grip",
                "shape": "small loop or knob on top",
                "attachment": "attached to the crown of the bell body",
                "function": "holding and hanging point",
                "confidence": 0.82,
                "evidence": ["loop/knob above the domed body"],
            },
            {
                "canonical_name": "bell body",
                "semantic_role": "resonant shell",
                "shape": "inverted dome flaring to an open mouth",
                "attachment": "the main shell below the handle",
                "function": "resonates when struck",
                "confidence": 0.94,
                "evidence": ["dominant dome volume", "flared open rim at the bottom"],
            },
        ],
    },
    {
        "model": "white:christmas:wreath",
        "label": "Wreath",
        "object_type": "wreath",
        "obj_path": "/files/white-models/christmas/wreath.obj",
        "intent": "把花环的松枝质感做得更茂密。",
        "parts": [
            {
                "canonical_name": "foliage ring",
                "semantic_role": "main body",
                "shape": "torus-like ring of layered leaves",
                "attachment": "continuous circular band forming the wreath",
                "function": "structural ring and decorative body",
                "confidence": 0.95,
                "evidence": ["dominant circular band", "layered leaf texture around the loop"],
            },
            {
                "canonical_name": "berries",
                "semantic_role": "accent cluster",
                "shape": "small spheres clustered on the ring",
                "attachment": "scattered on the foliage ring surface",
                "function": "color accent and texture contrast",
                "confidence": 0.85,
                "evidence": ["small round bumps on the ring"],
            },
            {
                "canonical_name": "bow",
                "semantic_role": "decorative knot",
                "shape": "ribbon knot with two loops and tails",
                "attachment": "fixed at the bottom or top of the ring",
                "function": "ornamental focal point",
                "confidence": 0.83,
                "evidence": ["ribbon loops and trailing ends on the ring"],
            },
        ],
    },
    {
        "model": "white:christmas:gift-bag",
        "label": "Gift Bag",
        "object_type": "gift bag",
        "obj_path": "/files/white-models/christmas/gift-bag.obj",
        "intent": "把礼物袋的提手做得更精致。",
        "parts": [
            {
                "canonical_name": "handle",
                "semantic_role": "grip loop",
                "shape": "two ribbon loops rising from the top edges",
                "attachment": "attached to the folded top of the bag",
                "function": "carrying grip",
                "confidence": 0.88,
                "evidence": ["two loops above the bag opening"],
            },
            {
                "canonical_name": "bag body",
                "semantic_role": "container",
                "shape": "tall box-like body with tapered bottom",
                "attachment": "the main volume between top fold and base",
                "function": "holds contents",
                "confidence": 0.95,
                "evidence": ["dominant vertical container volume"],
            },
            {
                "canonical_name": "folded top",
                "semantic_role": "closure",
                "shape": "zigzag folded edge across the top opening",
                "attachment": "top of the bag body below the handles",
                "function": "closes the opening and stiffens the rim",
                "confidence": 0.8,
                "evidence": ["zigzag crease line at the top"],
            },
        ],
    },
    {
        "model": "white:christmas:sock",
        "label": "Sock",
        "object_type": "sock",
        "obj_path": "/files/white-models/christmas/sock.obj",
        "intent": "把袜子的袜口罗纹做得更立体。",
        "parts": [
            {
                "canonical_name": "cuff",
                "semantic_role": "opening band",
                "shape": "ribbed cylindrical band at the top opening",
                "attachment": "top edge of the leg tube",
                "function": "holds the sock on the leg",
                "confidence": 0.88,
                "evidence": ["ribbed band at the opening"],
            },
            {
                "canonical_name": "heel",
                "semantic_role": "foot section",
                "shape": "rounded bend where leg meets foot",
                "attachment": "rear corner of the foot tube",
                "function": "wraps the heel",
                "confidence": 0.84,
                "evidence": ["sharp rear bend in the foot tube"],
            },
            {
                "canonical_name": "toe",
                "semantic_role": "foot end",
                "shape": "rounded closed end of the foot tube",
                "attachment": "front end of the foot section",
                "function": "encloses the toes",
                "confidence": 0.86,
                "evidence": ["rounded closed tip opposite the heel"],
            },
        ],
    },
    {
        "model": "white:bakery:croissant",
        "label": "Croissant",
        "object_type": "croissant",
        "obj_path": "/files/white-models/bakery/croissant.obj",
        "intent": "让羊角包的酥皮层次更分明。",
        "parts": [
            {
                "canonical_name": "ridge",
                "semantic_role": "surface segment",
                "shape": "raised crescent ridges across the top",
                "attachment": "concentric arcs on the upper surface",
                "function": "lamination visual and texture",
                "confidence": 0.9,
                "evidence": ["parallel curved raised bands"],
            },
            {
                "canonical_name": "crescent tip",
                "semantic_role": "end point",
                "shape": "tapered pointed ends curving inward",
                "attachment": "two ends of the crescent body",
                "function": "defines the crescent silhouette",
                "confidence": 0.87,
                "evidence": ["two tapered inward-curving tips"],
            },
            {
                "canonical_name": "layered body",
                "semantic_role": "main mass",
                "shape": "crescent-shaped flaky volume",
                "attachment": "the central mass connecting both tips",
                "function": "structural body",
                "confidence": 0.94,
                "evidence": ["dominant crescent volume between the tips"],
            },
        ],
    },
    {
        "model": "white:bakery:pretzel",
        "label": "Pretzel",
        "object_type": "pretzel",
        "obj_path": "/files/white-models/bakery/pretzel.obj",
        "intent": "把椒盐卷饼的辫状扭结做得更清晰。",
        "parts": [
            {
                "canonical_name": "twist knot",
                "semantic_role": "central knot",
                "shape": "overlapping twist where the rope crosses",
                "attachment": "center of the pretzel where strands cross",
                "function": "distinctive braid structure",
                "confidence": 0.9,
                "evidence": ["central overlapping crossover"],
            },
            {
                "canonical_name": "loop segment",
                "semantic_role": "body arm",
                "shape": "thick rounded rope arms forming loops",
                "attachment": "two symmetric loops flanking the knot",
                "function": "defines the pretzel outline",
                "confidence": 0.92,
                "evidence": ["two symmetric thick loops"],
            },
            {
                "canonical_name": "rope body",
                "semantic_role": "dough strand",
                "shape": "continuous cylindrical dough strand",
                "attachment": "the whole continuous strand from loop to knot",
                "function": "structural strand",
                "confidence": 0.95,
                "evidence": ["continuous thick strand throughout"],
            },
        ],
    },
]


def _part_semantics_payload(model: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_name": part["canonical_name"],
        "semantic_role": part["semantic_role"],
        "shape": part["shape"],
        "attachment": part["attachment"],
        "function": part["function"],
        "confidence": part["confidence"],
        "evidence": part["evidence"],
        "object_type": model["object_type"],
    }


def run_part(model: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    record: dict[str, Any] = {
        "model": model["model"],
        "label": model["label"],
        "object_type": model["object_type"],
        "part": part["canonical_name"],
        "intent": model["intent"],
        "ok": False,
        "elapsed_sec": 0.0,
    }
    try:
        source = SourceSpec(
            source_id=f"planner_test_{model['object_type'].replace(' ', '_')}",
            object_type=model["object_type"],
            mesh_path="",
            image_paths=[],
            render_paths=[],
            identity_constraints=[f"lock {item}" for item in FACETS["part"]["locked"]],
        )
        part_semantics = _part_semantics_payload(model, part)
        attribute_plan = planner_seed_attributes(
            stage="part",
            source=source,
            object_type=model["object_type"],
            source_elements={},
            part_semantics=part_semantics,
            user_prompt=model["intent"],
        )
        queries = expand_attribute_queries_unconstrained(
            stage="part", attribute_plan=attribute_plan
        )
        record["ok"] = True
        record["attribute_plan"] = attribute_plan
        record["queries"] = queries
        record["query_count"] = len(queries)
        record["query_graphs"] = sorted({q["graph"] for q in queries})
        record["query_by_graph"] = {
            graph: sum(1 for q in queries if q["graph"] == graph) for graph in ("wikidata", "getty_aat", "asknature")
        }
    except Exception as exc:
        record["error"] = str(exc)
        record["error_type"] = type(exc).__name__
    record["elapsed_sec"] = round(time.time() - started, 2)
    return record


def build_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Planner 稳定性测试报告",
        "",
        f"- 模型数：{len(report['models'])}",
        f"- 部件级测试数：{len(report['records'])}，成功：{report['success_count']}，失败：{report['fail_count']}",
        f"- 总耗时：{report['total_elapsed_sec']}s",
        f"- planner：{report['planner_api_base']}",
        "",
    ]
    for model in report["models"]:
        lines.append(f"## {model['label']}（{model['object_type']}）")
        lines.append("")
        lines.append(f"部件：{', '.join(p['canonical_name'] for p in model['parts'])}")
        lines.append("")
        for record in report["records"]:
            if record["model"] != model["model"]:
                continue
            lines.append(f"### 部件：{record['part']}（{record['elapsed_sec']}s）")
            lines.append("")
            if not record["ok"]:
                lines.append(f"**失败**：{record.get('error')}")
                lines.append("")
                continue
            plan = record["attribute_plan"]
            lines.append("#### 1. KG 属性规划（attribute_plan）")
            lines.append("")
            lines.append(f"- source_anchor：{plan['source_anchor']}")
            lines.append(f"- source_noun：{plan['source_noun']}")
            lines.append("")
            lines.append("| attribute_id | dimension | value | evidence | transfer_question | confidence |")
            lines.append("|---|---|---|---|---|---|")
            for attr in plan["attributes"]:
                lines.append(
                    f"| {attr['attribute_id']} | {attr['dimension']} | {attr['value']} | "
                    f"{attr['evidence']} | {attr['transfer_question']} | {attr['confidence']} |"
                )
            lines.append("")
            lines.append("#### 2. 发散的相关词（KG 查询词）")
            lines.append("")
            for graph in ("wikidata", "getty_aat", "asknature"):
                graph_queries = [q for q in record["queries"] if q["graph"] == graph]
                lines.append(f"**{graph}**（{len(graph_queries)} 条）")
                for q in graph_queries:
                    lines.append(f"- `{q['term']}` — {q['same_attribute_rationale']}")
                lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="/root/flowstudio_app/outputs/planner_stability_test")
    parser.add_argument("--models", default="", help="comma-separated model ids to restrict run")
    parser.add_argument("--parts-per-model", type=int, default=2)
    parser.add_argument(
        "--rerun-failed",
        default="",
        help="path to a previous report.json; rerun only failed (model, part) pairs",
    )
    args = parser.parse_args()

    selected = [m for m in WHITE_MODEL_PARTS if not args.models or m["model"] in args.models.split(",")]
    if args.rerun_failed:
        previous = json.loads(Path(args.rerun_failed).read_text(encoding="utf-8"))
        failed = {
            (record["model"], record["part"])
            for record in previous.get("records", [])
            if not record.get("ok")
        }
        selected = [
            {**model, "parts": [p for p in model["parts"] if (model["model"], p["canonical_name"]) in failed]}
            for model in selected
        ]
        selected = [model for model in selected if model["parts"]]
    out_dir = Path(args.out_dir)
    run_dir = out_dir / time.strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    started_total = time.time()
    records: list[dict[str, Any]] = []
    for model in selected:
        chosen_parts = model["parts"][: args.parts_per_model]
        for part in chosen_parts:
            print(
                f"[planner-test] {model['label']} / {part['canonical_name']} ...",
                flush=True,
            )
            records.append(run_part(model, part))
            status = "OK" if records[-1]["ok"] else "FAIL"
            print(
                f"  -> {status} ({records[-1]['elapsed_sec']}s) "
                f"{records[-1].get('query_count', '')} queries",
                flush=True,
            )

    report = {
        "schema_version": "flowstudio.planner-stability-test.v1",
        "planner_api_base": os.environ["CF_TEXT_LLM_API_BASE"],
        "total_elapsed_sec": round(time.time() - started_total, 2),
        "models": selected,
        "records": records,
        "success_count": sum(1 for r in records if r["ok"]),
        "fail_count": sum(1 for r in records if not r["ok"]),
    }
    (run_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (run_dir / "report.md").write_text(build_markdown(report), encoding="utf-8")
    print(f"\n[planner-test] report: {run_dir}/report.md")
    print(f"[planner-test] success={report['success_count']} fail={report['fail_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
