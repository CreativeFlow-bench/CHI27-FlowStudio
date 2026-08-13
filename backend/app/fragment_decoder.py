"""Constrained decode of donor concepts into selectable Chinese fragments.

Incremental spec §9: the LLM (or deterministic decoder here) may only turn
already retrieved and relation-filtered nodes into phrases bound to the
current target. Hard gates (§10) are boolean; no preference scores.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.divergence import contextual_graph_policy as policy


DELTA_PHRASE_ZH: dict[str, dict[str, str]] = {
    "curvature": {"increase": "更弯曲", "decrease": "更平直"},
    "roundness": {"increase": "更圆润", "decrease": "更锐利"},
    "taper": {"increase": "更锥形", "decrease": "更均一"},
    "layering": {"increase": "更多层次", "decrease": "更整体"},
    "finish": {"matte": "哑光", "glossy": "高光", "polished": "抛光"},
    "porosity": {"increase": "带细密孔隙", "decrease": "更致密"},
    "flexibility": {"increase": "更柔韧", "decrease": "更刚性"},
    "texture_detail": {"increase": "更细腻纹理", "decrease": "更平滑"},
    "roughness": {"decrease": "更光滑", "increase": "更粗糙"},
    "weave": {"increase": "编织纹理"},
    "folding": {"increase": "折叠结构"},
    "grip_texture": {"increase": "防滑纹理"},
    "segmentation": {"increase": "分段结构"},
    "modularity": {"increase": "模块化"},
    "slope": {"increase": "更倾斜"},
    "flatness": {"increase": "更扁平"},
    "width": {"increase": "更宽", "decrease": "更窄"},
    "height": {"increase": "更高", "decrease": "更矮"},
    "thickness": {"increase": "更厚", "decrease": "更薄"},
    "hollowness": {"increase": "中空"},
    "openness": {"increase": "更开放"},
    "elasticity": {"increase": "更有弹性", "decrease": "更刚硬"},
    "rigidity": {"increase": "更刚硬"},
    "weight": {"decrease": "更轻", "increase": "更重"},
    "transparency": {"increase": "更透明", "decrease": "更不透明"},
    "ribbing": {"increase": "带棱纹"},
    "grooving": {"increase": "带凹槽"},
    "beading": {"increase": "带珠状装饰"},
    "carving": {"increase": "带雕刻"},
    "engraving": {"increase": "带刻纹"},
    "braiding": {"increase": "编织"},
    "knitting": {"increase": "针织质感"},
    "stability": {"increase": "更稳定", "decrease": "更可摇动"},
    "shape": {"cylindrical": "圆柱形", "spherical": "球形", "conical": "锥形"},
    "insulation": {"increase": "更保温"},
    "compactness": {"increase": "更紧凑"},
    "streamline": {"increase": "更流线"},
    "ornamentation": {"increase": "更富装饰"},
    "softness": {"increase": "更柔软"},
    "perforation": {"increase": "带穿孔"},
    "branching": {"increase": "带分支结构"},
    "spread": {"increase": "更展开"},
    "tension": {"increase": "更有张紧感"},
    "drip_shape": {"increase": "水滴形"},
    "spiraling": {"increase": "螺旋形态"},
    "thinness": {"increase": "更轻薄"},
    "grip_texture": {"increase": "防滑握持纹理"},
}


def _delta_phrase(attribute_delta: dict[str, str]) -> str | None:
    attribute = str(attribute_delta.get("attribute") or "")
    change = str(attribute_delta.get("change") or "")
    phrase_map = DELTA_PHRASE_ZH.get(attribute, {})
    return phrase_map.get(change) or f"更{attribute}" if change else None


def _full_phrase(display: str, target_label_zh: str, operation: str, relation_family: str) -> str:
    target = target_label_zh or "对象"
    if operation == "replace":
        return f"替换为{display}的{target}"
    if operation == "extend":
        return f"向外延伸、{display}的{target}"
    if operation == "perforate":
        return f"带{display}的{target}"
    if operation == "open":
        return f"采用{display}的{target}结构"
    if relation_family in {"part_of_has_part", "mechanism_bridge", "use_function"} and operation == "replace":
        return f"采用{display}的{target}连接"
    if relation_family == "material":
        return f"表面使用{display}质感的{target}"
    return f"{display}的{target}"


def decode_fragment(
    *,
    asset_id: str,
    scope: str,
    target_label_zh: str,
    target_id: str | None,
    operation: str,
    constraints: list[str],
    source_entity: dict[str, Any],
    first_hop: dict[str, Any],
    second_hop: dict[str, Any],
    relation_family: str,
) -> dict[str, Any] | None:
    """Return a ContextualFragment-shaped dict or None when any gate fails."""
    label_en = str(second_hop.get("label") or first_hop.get("label") or "")
    raw_delta = policy.find_delta_for_term(label_en) or {}
    delta: dict[str, str] | None = None
    if raw_delta:
        attribute, change = next(iter(raw_delta.items()))
        delta = {"attribute": attribute, "change": change}
    target_exists = bool(asset_id and target_label_zh)
    scope_match = scope in {"whole", "silhouette", "selected_part", "material_region"}
    operation_compatible = policy.operation_allowed(operation, scope)
    entity_resolved = bool(source_entity.get("id"))
    first_hop_verified = bool(first_hop.get("id"))
    second_hop_verified = bool(second_hop.get("id") or second_hop.get("url"))
    physically_expressible = delta is not None
    display = _delta_phrase(delta) if delta else None
    if not display:
        if operation == "replace":
            display = f"嵌入式{target_label_zh or '部件'}"
        elif relation_family in {"part_of_has_part", "mechanism_bridge"}:
            display = label_en[:16] or "结构连接"
        elif relation_family == "material":
            display = f"{label_en[:16] or '材料'}质感"
        else:
            display = label_en[:16] or "形态变化"
    full_phrase = _full_phrase(display, target_label_zh, operation, relation_family)
    phrase_grounded = bool(display and full_phrase and target_label_zh)
    locks_preserved = True
    for constraint in constraints:
        low = constraint.lower()
        if any(token in low for token in ("preserve", "keep", "do not modify", "不变")):
            if label_en and re.search(r"\b(snowman|kettle|human|animal|building)\b", label_en.lower()):
                locks_preserved = False
    gates = {
        "entity_resolved": entity_resolved,
        "first_hop_verified": first_hop_verified,
        "second_hop_verified": second_hop_verified,
        "target_exists": target_exists,
        "scope_match": scope_match,
        "operation_compatible": operation_compatible,
        "locks_preserved": locks_preserved,
        "physically_expressible": physically_expressible,
        "phrase_grounded": phrase_grounded,
    }
    passed = all(gates.values())
    if not passed:
        return None
    group_key = policy.group_key_for_delta(scope, delta or {"attribute": "shape", "change": "increase"}, relation_family)
    group_label = next(
        (group["label_zh"] for group in policy.groups_for_scope(scope) if group["key"] == group_key),
        "形态",
    )
    legacy_dimension = next(
        (group["legacy"] for group in policy.groups_for_scope(scope) if group["key"] == group_key),
        "Structural",
    )
    return {
        "display_label_zh": display,
        "full_phrase_zh": full_phrase,
        "label_en": label_en,
        "group": {"key": group_key, "label_zh": group_label},
        "legacy_dimension": legacy_dimension,
        "scope": scope,
        "target_ref": {
            "asset_id": asset_id,
            "type": "part" if target_id and scope in {"selected_part", "material_region"} else "whole",
            "id": target_id,
            "label_zh": target_label_zh,
        },
        "operation": operation,
        "attribute_delta": delta or {},
        "provenance_path": {
            "source": source_entity,
            "first_hop": first_hop,
            "second_hop": second_hop,
        },
        "hard_gates": {**gates, "passed": passed},
        "constraints": constraints,
    }
