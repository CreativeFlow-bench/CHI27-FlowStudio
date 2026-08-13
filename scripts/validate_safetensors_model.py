#!/usr/bin/env python3
"""Validate a sharded safetensors model before promoting it from staging."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from safetensors import safe_open


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("model_dir", type=Path)
    args = parser.parse_args()
    model_dir = args.model_dir.resolve()

    if not model_dir.is_dir():
        raise SystemExit(f"model directory does not exist: {model_dir}")

    incomplete = sorted(model_dir.rglob("*.incomplete"))
    if incomplete:
        raise SystemExit(f"download is incomplete: {len(incomplete)} temporary files remain")

    indexes = sorted(model_dir.rglob("*.safetensors.index.json"))
    referenced: set[Path] = set()
    tensor_references = 0
    for index_path in indexes:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
        weight_map = payload.get("weight_map")
        if not isinstance(weight_map, dict) or not weight_map:
            raise SystemExit(f"invalid or empty weight_map: {index_path}")
        tensor_references += len(weight_map)
        for relative_name in weight_map.values():
            shard_path = index_path.parent / relative_name
            if not shard_path.is_file() or shard_path.stat().st_size == 0:
                raise SystemExit(f"missing or empty indexed shard: {shard_path}")
            referenced.add(shard_path.resolve())

    shards = sorted(model_dir.rglob("*.safetensors"))
    if not shards:
        raise SystemExit(f"no safetensors files found: {model_dir}")

    tensor_entries = 0
    total_bytes = 0
    for shard_path in shards:
        if shard_path.stat().st_size == 0:
            raise SystemExit(f"empty safetensors file: {shard_path}")
        with safe_open(shard_path, framework="pt", device="cpu") as handle:
            tensor_entries += len(handle.keys())
        total_bytes += shard_path.stat().st_size

    missing_from_scan = referenced.difference(path.resolve() for path in shards)
    if missing_from_scan:
        raise SystemExit(
            "indexed shards were not included in the safetensors scan: "
            + ", ".join(str(path) for path in sorted(missing_from_scan))
        )

    print(
        json.dumps(
            {
                "ok": True,
                "model_dir": str(model_dir),
                "indexes": len(indexes),
                "shards": len(shards),
                "indexed_tensor_references": tensor_references,
                "tensor_entries": tensor_entries,
                "safetensors_gib": round(total_bytes / 1024**3, 2),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
