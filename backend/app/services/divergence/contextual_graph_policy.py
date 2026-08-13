"""Scope/operation -> Wikidata relation whitelist and column policy.

Incremental spec (FLOWSTUDIO_CONTEXTUAL_DIVERGENCE_FRAGMENT_PIPELINE_V1_ZH.md)
§5, §7: relation families are versioned, config-driven policy, never scattered
property IDs in code.
"""

from __future__ import annotations

from typing import Any


POLICY_VERSION = "contextual_graph_policy.v1"

# relation family -> Wikidata property ids (versioned whitelist)
RELATION_FAMILIES: dict[str, list[str]] = {
    "type_instance": ["P31", "P279"],
    "part_of_has_part": ["P527", "P361"],
    "material": ["P186"],
    "shape_characteristic": ["P2386", "P2067"],
    "use_function": ["P366"],
    "mechanism_bridge": ["P366", "P1542"],
}

# scope -> allowed relation families
SCOPE_RELATION_FAMILIES: dict[str, list[str]] = {
    "whole": ["type_instance", "part_of_has_part", "shape_characteristic", "use_function"],
    "silhouette": ["shape_characteristic", "part_of_has_part"],
    "selected_part": ["part_of_has_part", "use_function", "material"],
    "material_region": ["material", "shape_characteristic"],
}

# operation -> allowed scopes
OPERATION_SCOPES: dict[str, list[str]] = {
    "replace": ["selected_part", "material_region"],
    "deform": ["whole", "silhouette", "selected_part"],
    "extend": ["silhouette", "selected_part"],
    "open": ["whole", "selected_part"],
    "perforate": ["selected_part", "material_region"],
    "finish": ["whole", "selected_part", "material_region"],
}

# scope -> default visible columns (user-facing groups) + legacy dimension
SCOPE_GROUPS: dict[str, list[dict[str, str]]] = {
    "whole": [
        {"key": "global_form", "label_zh": "整体形态", "legacy": "Structural"},
        {"key": "composition", "label_zh": "构成", "legacy": "Structural"},
        {"key": "surface", "label_zh": "表面", "legacy": "Aesthetic"},
    ],
    "silhouette": [
        {"key": "proportion", "label_zh": "比例", "legacy": "Structural"},
        {"key": "envelope", "label_zh": "包络", "legacy": "Structural"},
        {"key": "posture", "label_zh": "姿态", "legacy": "Aesthetic"},
    ],
    "selected_part": [
        {"key": "shape", "label_zh": "形状", "legacy": "Structural"},
        {"key": "connection", "label_zh": "连接", "legacy": "Functional"},
        {"key": "surface", "label_zh": "表面", "legacy": "Aesthetic"},
    ],
    "material_region": [
        {"key": "material", "label_zh": "材质", "legacy": "Aesthetic"},
        {"key": "texture", "label_zh": "纹理", "legacy": "Aesthetic"},
        {"key": "surface_state", "label_zh": "表面状态", "legacy": "Functional"},
    ],
}

# AAT/AskNature donor term keywords -> executable attribute delta.
# Each donor must resolve to at least one delta to pass physically_expressible.
TERM_DELTA_MAP: dict[str, dict[str, str]] = {
    "curved": {"curvature": "increase"},
    "curving": {"curvature": "increase"},
    "arched": {"curvature": "increase"},
    "rounded": {"roundness": "increase"},
    "round": {"roundness": "increase"},
    "tapered": {"taper": "increase"},
    "tapering": {"taper": "increase"},
    "layered": {"layering": "increase"},
    "layers": {"layering": "increase"},
    "cylindrical": {"shape": "cylindrical"},
    "spherical": {"shape": "spherical"},
    "conical": {"shape": "conical"},
    "matte": {"finish": "matte"},
    "glossy": {"finish": "glossy"},
    "porous": {"porosity": "increase"},
    "perforated": {"porosity": "increase"},
    "flexible": {"flexibility": "increase"},
    "folded": {"folding": "increase"},
    "woven": {"weave": "increase"},
    "grippy": {"grip_texture": "increase"},
    "textured": {"texture_detail": "increase"},
    "smooth": {"roughness": "decrease"},
    "polished": {"finish": "polished"},
    "segmented": {"segmentation": "increase"},
    "modular": {"modularity": "increase"},
    "sloped": {"slope": "increase"},
    "flat": {"flatness": "increase"},
    "wide": {"width": "increase"},
    "narrow": {"width": "decrease"},
    "tall": {"height": "increase"},
    "short": {"height": "decrease"},
    "thick": {"thickness": "increase"},
    "thin": {"thickness": "decrease"},
    "hollow": {"hollowness": "increase"},
    "open": {"openness": "increase"},
    "springy": {"elasticity": "increase"},
    "bouncy": {"elasticity": "increase"},
    "rigid": {"rigidity": "increase"},
    "lightweight": {"weight": "decrease"},
    "heavy": {"weight": "increase"},
    "transparent": {"transparency": "increase"},
    "translucent": {"transparency": "increase"},
    "opaque": {"transparency": "decrease"},
    "ribbed": {"ribbing": "increase"},
    "grooved": {"grooving": "increase"},
    "fluted": {"grooving": "increase"},
    "beaded": {"beading": "increase"},
    "carved": {"carving": "increase"},
    "engraved": {"engraving": "increase"},
    "braided": {"braiding": "increase"},
    "knitted": {"knitting": "increase"},
    "sturdy": {"stability": "increase"},
    "stable": {"stability": "increase"},
    "wobbling": {"stability": "decrease"},
    "grip": {"grip_texture": "increase"},
    "grippy": {"grip_texture": "increase"},
    "fur": {"texture_detail": "increase"},
    "feather": {"weight": "decrease", "texture_detail": "increase"},
    "insulat": {"insulation": "increase"},
    "thermal": {"insulation": "increase"},
    "compact": {"compactness": "increase"},
    "streamlined": {"streamline": "increase"},
    "snowball": {"roundness": "increase", "compactness": "increase"},
    "decorat": {"ornamentation": "increase"},
    "ornate": {"ornamentation": "increase"},
    "sculpt": {"carving": "increase"},
    "ball": {"roundness": "increase"},
    "sphere": {"roundness": "increase"},
    "dome": {"roundness": "increase", "curvature": "increase"},
    "cushion": {"softness": "increase"},
    "spong": {"porosity": "increase"},
    "honeycomb": {"porosity": "increase", "perforation": "increase"},
    "skeleton": {"openness": "increase", "weight": "decrease"},
    "shell": {"hollowness": "increase"},
    "root": {"branching": "increase"},
    "branch": {"branching": "increase"},
    "leaf": {"thinness": "increase", "flatness": "increase"},
    "vault": {"curvature": "increase"},
    "arc": {"curvature": "increase"},
    "spiral": {"curvature": "increase", "spiraling": "increase"},
    "fan": {"spread": "increase"},
    "web": {"weave": "increase", "openness": "increase"},
    "net": {"openness": "increase", "weave": "increase"},
    "rib": {"ribbing": "increase"},
    "scale": {"texture_detail": "increase"},
    "spine": {"rigidity": "increase"},
    "tendon": {"tension": "increase"},
    "drip": {"drip_shape": "increase"},
    "droplet": {"roundness": "increase"},
    "bubble": {"roundness": "increase"},
    "ice": {"finish": "glossy", "stability": "increase"},
    "frost": {"texture_detail": "increase"},
}


def relation_families_for_scope(scope: str) -> list[str]:
    return SCOPE_RELATION_FAMILIES.get(scope, ["type_instance", "part_of_has_part"])


def allowed_relations(scope: str) -> list[str]:
    families = relation_families_for_scope(scope)
    return [prop for family in families for prop in RELATION_FAMILIES.get(family, [])]


def allowed_operations(scope: str) -> list[str]:
    return [op for op, scopes in OPERATION_SCOPES.items() if scope in scopes]


def operation_allowed(operation: str, scope: str) -> bool:
    return operation in OPERATION_SCOPES and scope in OPERATION_SCOPES[operation]


def groups_for_scope(scope: str) -> list[dict[str, str]]:
    return SCOPE_GROUPS.get(scope, SCOPE_GROUPS["selected_part"])


def group_key_for_delta(scope: str, delta: dict[str, str], relation_family: str) -> str:
    """Map an attribute delta + relation family to a visible column key."""
    attribute = str(delta.get("attribute") or "")
    groups = groups_for_scope(scope)
    surface_attributes = {
        "finish", "porosity", "texture_detail", "weave", "roughness", "transparency",
        "knitting", "braiding", "beading", "grip_texture", "ornamentation", "carving",
        "engraving", "grooving", "ribbing", "insulation", "frost",
    }
    form_attributes = {
        "height", "width", "thickness", "taper", "layering", "roundness", "compactness",
        "softness", "flatness", "slope", "streamline", "drip_shape", "spiraling", "shape",
    }
    structure_attributes = {
        "branching", "spread", "tension", "openness", "hollowness", "perforation",
        "segmentation", "modularity", "weave", "folding",
    }
    if attribute in surface_attributes:
        key = "surface" if scope in {"whole", "selected_part"} else "surface_state" if scope == "material_region" else "surface"
    elif attribute in structure_attributes:
        key = "connection" if scope == "selected_part" else "composition" if scope == "whole" else "envelope" if scope == "silhouette" else "surface_state"
    elif attribute in form_attributes:
        key = "proportion" if scope == "silhouette" else "global_form" if scope == "whole" else "shape"
    elif relation_family in {"part_of_has_part", "mechanism_bridge", "use_function"}:
        key = "connection" if scope == "selected_part" else "composition" if scope == "whole" else "envelope" if scope == "silhouette" else "surface_state"
    else:
        key = "shape" if scope == "selected_part" else "global_form" if scope == "whole" else "proportion" if scope == "silhouette" else "texture"
    if not any(g["key"] == key for g in groups):
        key = groups[0]["key"]
    return key


def scope_question(scope: str, target_label_zh: str | None) -> str:
    label = target_label_zh or "对象"
    return {
        "whole": f"你想如何改变这个{label}的整体？",
        "silhouette": f"你想如何改变这个{label}的轮廓？",
        "selected_part": f"你想如何改变这个{label}？",
        "material_region": f"你想如何改变这片{label}表面？",
    }.get(scope, f"你想如何改变这个{label}？")


def find_delta_for_term(term: str) -> dict[str, str] | None:
    lowered = term.lower().strip()
    for keyword, delta in TERM_DELTA_MAP.items():
        if keyword in lowered:
            return delta
    return None


def policy_state() -> dict[str, Any]:
    return {
        "version": POLICY_VERSION,
        "relation_families": RELATION_FAMILIES,
        "scope_relation_families": SCOPE_RELATION_FAMILIES,
        "operation_scopes": OPERATION_SCOPES,
    }
