#!/usr/bin/env python3
"""Run the three FlowStudio white-model scenario prompt chains end to end.

Each case uses the production Observation -> immutable Send cutoff -> Gate ->
human keyword selection -> eight-candidate generation path.  The script saves
the exact prompt chain and artifact URLs as JSON so an experiment is auditable.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path


SCENARIOS = {
    "narrative_frog": {
        "benchmark_id": "src_20260403112017_d949",
        "object_type": "frog",
        "user_text": (
            "把这只小青蛙叙事迁移为石像青蛙；完整保留青蛙物种身份、头身比例、"
            "四肢数量、蹲伏姿态和轮廓，只探索石雕文化、年代与风化叙事。"
        ),
        "scope": "whole",
        "dimensions": {"Scenario": ["narrative_character"]},
        "keywords": [
            "weathered temple basalt",
            "moss-covered forest shrine relic",
            "cracked pale marble guardian",
            "eroded river-stone idol",
            "volcanic stone with glowing mineral seams",
            "ancient sandstone votive sculpture",
            "rain-polished granite monument",
            "archaeological patina and lichen",
        ],
        "behaviors": [
            {
                "tool": "drag",
                "stroke_count": 4,
                "operation_summary": {
                    "mode": "3d",
                    "gesture": "short outward silhouette pulls around brow and back",
                    "intent_signal": "test sculptural mass while retaining frog pose",
                },
            },
            {
                "tool": "smooth",
                "stroke_count": 7,
                "operation_summary": {
                    "mode": "3d",
                    "gesture": "smooth local transitions after drag",
                    "intent_signal": "stone-carved continuous surface",
                },
            },
        ],
    },
    "material_handbag": {
        "benchmark_id": "src_20260430155836_4808",
        "object_type": "leather handbag",
        "user_text": (
            "只探索同一个皮包的材质多样性；严格锁定包身轮廓、尺寸比例、提手、开口、"
            "缝线、五金位置和镜头，不允许改变任何几何结构。"
        ),
        "scope": "material",
        "dimensions": {"Scenario": ["product_material"]},
        "keywords": [
            "woven rattan body with leather trim",
            "frosted translucent polymer with metal hardware",
            "brushed aluminum panels with rubber handle",
            "warm cork with dark stitched edging",
            "quilted technical textile with anodized hardware",
            "matte recycled rubber with glossy accents",
            "ceramic glaze panels with leather joints",
            "iridescent bio-resin with woven handle",
        ],
        "behaviors": [
            {
                "tool": "brush",
                "stroke_count": 12,
                "operation_summary": {
                    "mode": "2d",
                    "brush_role": "material region indication",
                    "mask_area_ratio": 0.64,
                    "covered_regions": ["front body panel", "side panel"],
                    "excluded_regions": ["handle", "zipper", "hardware"],
                },
            }
        ],
    },
    "structure_coffee_table": {
        "benchmark_id": "src_20260429114410_5011",
        "object_type": "coffee table",
        "user_text": (
            "把这个茶几的结构迁移成正在流动并局部冷却的熔岩形态；必须仍是一张可用茶几，"
            "保留水平桌面、尺度、承重关系和桌面到支撑的拓扑，但结构家族要有明显多样性，"
            "不能只换熔岩贴图。"
        ),
        "scope": "whole",
        "dimensions": {"Scenario": ["product_structure"]},
        "keywords": [
            "cantilevered lava shelf",
            "braided molten support streams",
            "collapsed caldera pedestal",
            "basalt crust over flowing core",
            "dripping edge with stable stone legs",
            "lava tube structural frame",
            "layered cooled magma terraces",
            "tensioned molten bridge supports",
        ],
        "behaviors": [
            {
                "tool": "brush",
                "stroke_count": 15,
                "operation_summary": {
                    "mode": "3d",
                    "brush_role": "volumetric structural sculpt",
                    "affected_regions": ["tabletop edge", "support transitions", "base"],
                    "gesture": "downward flow strokes and support thickening",
                },
            }
        ],
    },
}


class Api:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, method: str, path: str, body: dict | None = None, timeout: int = 300) -> dict:
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(body).encode("utf-8") if body is not None else None,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        with self.opener.open(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def get(self, path: str) -> dict:
        return self.request("GET", path)

    def post(self, path: str, body: dict | None = None) -> dict:
        return self.request("POST", path, body or {})

    def put(self, path: str, body: dict) -> dict:
        return self.request("PUT", path, body)


def wait_revision(api: Api, session_id: str, revision_id: str, timeout: int = 180) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = api.get(f"/api/v1/sessions/{session_id}/realtime-observation")
        revision = next(item for item in snapshot["revisions"] if item["revision_id"] == revision_id)
        if revision["status"] != "planning":
            return revision
        time.sleep(2)
    raise TimeoutError(f"revision planning timed out: {revision_id}")


def wait_run(api: Api, run_id: str, timeout: int = 1800) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = api.get(f"/api/v1/four-stage/runs/{run_id}")
        artifacts = run.get("generation_artifacts") or []
        print(f"  generation stage={run['stage']} artifacts={len(artifacts)}/8", flush=True)
        if run["stage"] in {"completed", "failed", "cancelled"}:
            return run
        time.sleep(10)
    raise TimeoutError(f"generation timed out: {run_id}")


def run_scenario(api: Api, name: str, case: dict) -> dict:
    print(f"\n===== {name} =====", flush=True)
    session = api.post("/api/v1/sessions", {"title": f"three-scenario acceptance: {name}"})
    sid = session["session_id"]
    asset = api.post(
        f"/api/v1/benchmark-assets/{case['benchmark_id']}/load",
        {"session_id": sid},
    )
    source_image_ref = asset.get("thumbnail_url")
    if source_image_ref:
        rendered = {"ok": True, "thumbnail_url": source_image_ref, "cached": True}
    else:
        rendered = api.post(
            "/api/v1/render/thumbnail",
            {"session_id": sid, "asset_id": asset["asset_id"], "options": {"clay": True}},
        )
        if not rendered.get("ok") or not rendered.get("thumbnail_url"):
            raise RuntimeError(f"white-model render failed: {rendered.get('error')}")
        source_image_ref = rendered["thumbnail_url"]

    committed = []
    for behavior in case["behaviors"]:
        committed.append(
            api.post(
                f"/api/v1/sessions/{sid}/behaviors",
                {
                    **behavior,
                    "target": {"asset_id": asset["asset_id"], "object_type": case["object_type"]},
                    "start_views": {"front": source_image_ref},
                    "end_views": {"front": source_image_ref},
                    "evidence_refs": [source_image_ref],
                },
            )
        )

    created = api.post(
        f"/api/v1/sessions/{sid}/intent-revisions",
        {
            "user_text": case["user_text"],
            "cutoff_seq": committed[-1]["behavior_seq"],
            "source_context": {
                "asset_id": asset["asset_id"],
                "object_type": case["object_type"],
                "source_image_ref": source_image_ref,
                "source_model_ref": asset.get("mesh_url") or asset.get("obj_url"),
            },
        },
    )
    revision = wait_revision(api, sid, created["revision_id"])
    if revision["status"] != "awaiting_gate":
        raise RuntimeError(f"planning failed: {revision.get('error')}")
    run = api.get(f"/api/v1/four-stage/runs/{revision['run_id']}")
    option = run["decision"]["options"][0]
    print(f"  Gate: {revision['gate_question']}", flush=True)
    api.post(
        f"/api/v1/intent-revisions/{revision['revision_id']}/gate",
        {
            "accepted": True,
            "selected_option_id": option["option_id"],
            "divergence_params": {"temperature": 0.7, "strictness": 0.7},
        },
    )
    run = api.get(f"/api/v1/four-stage/runs/{revision['run_id']}")
    divergence = run.get("semantic_divergence") or {}
    candidates = divergence.get("candidates") or []
    if len(candidates) < 9:
        raise RuntimeError(
            f"semantic divergence returned {len(candidates)} candidates: "
            f"{divergence.get('status')} {divergence.get('error')}"
        )
    chosen = candidates[: min(3, len(candidates))]
    print(
        "  Semantic keywords: "
        + ", ".join(item["display_label_zh"] for item in chosen),
        flush=True,
    )
    selected = api.put(
        f"/api/v1/intent-revisions/{revision['revision_id']}/divergence-selection",
        {
            "scope": case["scope"],
            "selected_candidate_ids": [item["candidate_id"] for item in chosen],
        },
    )
    batch = api.post(f"/api/v1/intent-revisions/{revision['revision_id']}/generation")
    final = wait_run(api, revision["run_id"])
    return {
        "scenario": name,
        "session_id": sid,
        "asset": asset,
        "white_model_render": rendered,
        "behaviors": committed,
        "observation": api.get(f"/api/v1/sessions/{sid}/realtime-observation")["observation"],
        "revision": selected,
        "gate": {
            "question": revision["gate_question"],
            "target": revision["gate_target"],
            "scope": revision["gate_scope"],
        },
        "selected_option": option,
        "batch": batch,
        "generation_spec": final.get("generation_spec"),
        "artifacts": final.get("generation_artifacts") or [],
        "final_stage": final["stage"],
        "error": final.get("error"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument("--scenario", choices=list(SCENARIOS))
    parser.add_argument("--output", default="outputs/three_scenario_acceptance.json")
    args = parser.parse_args()
    api = Api(args.base_url)
    chosen = {args.scenario: SCENARIOS[args.scenario]} if args.scenario else SCENARIOS
    results = []
    failures = 0
    for name, case in chosen.items():
        try:
            result = run_scenario(api, name, case)
            failures += int(result["final_stage"] != "completed" or len(result["artifacts"]) < 6)
            results.append(result)
        except Exception as exc:  # keep the remaining experiments runnable
            failures += 1
            results.append({"scenario": name, "final_stage": "failed", "error": str(exc)})
            print(f"  FAILED: {exc}", flush=True)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({"results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nTHREE_SCENARIO_DONE failures={failures} output={args.output}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
