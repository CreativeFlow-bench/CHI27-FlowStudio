"""Route semantic-divergence requests to bounded knowledge evidence."""

from __future__ import annotations

from app.models import KnowledgeEvidence, KnowledgeRoute, SemanticDivergenceRequest
from app.services.divergence import contextual_graph_policy as policy
from app.services.divergence import knowledge_adapters as kb


_MATERIAL_TERMS = ("material", "texture", "fabric", "leather", "材质", "纹理", "工艺", "表面")
_MECHANISM_TERMS = ("function", "mechanism", "biomimetic", "biomimicry", "仿生", "功能", "机制", "承重")
_CROSS_DOMAIN_TERMS = ("cross-domain", "cross domain", "跨域", "迁移", "transfer")


def intent_flags(text: str, semantic_role: str | None = None) -> dict[str, bool]:
    """Classify routing intent in the sole keyword table for this feature."""
    normalized = f"{text} {semantic_role or ''}".lower()
    return {
        "material": any(term in normalized for term in _MATERIAL_TERMS),
        "mechanism": any(term in normalized for term in _MECHANISM_TERMS),
        "cross_domain": any(term in normalized for term in _CROSS_DOMAIN_TERMS),
    }


class SemanticKnowledgeRouter:
    """Deterministically select optional donor-evidence sources."""

    def choose_route(self, request: SemanticDivergenceRequest) -> KnowledgeRoute:
        flags = intent_flags(
            request.user_semantic_intent,
            request.semantic_target.semantic_role,
        )
        if request.temperature >= 0.7 or flags["cross_domain"]:
            return KnowledgeRoute(
                mode="knowledge_augmented",
                use_wikidata=True,
                use_getty_aat=True,
                use_asknature=True,
                reasons=["high_temperature_or_cross_domain"],
            )
        if request.scope == "material_region" or flags["material"]:
            return KnowledgeRoute(
                mode="knowledge_augmented",
                use_wikidata=True,
                use_getty_aat=True,
                reasons=["material_scope_or_intent"],
            )
        if flags["mechanism"]:
            return KnowledgeRoute(
                mode="knowledge_augmented",
                use_wikidata=True,
                use_asknature=True,
                reasons=["mechanism_intent"],
            )
        if request.temperature <= 0.3:
            return KnowledgeRoute(reasons=["low_temperature_refinement"])
        return KnowledgeRoute(
            mode="knowledge_augmented",
            use_wikidata=True,
            use_getty_aat=True,
            reasons=["default_knowledge_route"],
        )

    def collect(self, request: SemanticDivergenceRequest, route: KnowledgeRoute) -> KnowledgeEvidence:
        """Collect only donor evidence reachable through a Wikidata first hop."""
        evidence = KnowledgeEvidence(route=route.model_copy(deep=True))
        if not route.use_wikidata:
            return evidence

        target = request.semantic_target
        qid = target.wikidata_qid
        if qid:
            source = {
                "graph": "wikidata",
                "id": qid,
                "label": target.label_en or request.object_identity,
                "url": f"https://www.wikidata.org/wiki/{qid}",
            }
        else:
            try:
                source = kb.ground_wikidata(
                    target.label_en or target.label_zh or "",
                    parent_label=request.object_identity,
                )
            except Exception as exc:
                evidence.errors.append(f"wikidata_grounding_error: {type(exc).__name__}: {exc}")
                source = None
        if source is None:
            evidence.errors.append("wikidata_grounding_failed")
            evidence.route = KnowledgeRoute(mode="model_only", reasons=["wikidata_grounding_failed"])
            return evidence

        evidence.wikidata.append(source)
        evidence.route.source_statuses["wikidata"] = "ok"
        scope = "selected_part" if request.scope == "part" else request.scope
        try:
            donors = kb.wikidata_first_hop(str(source["id"]), policy.allowed_relations(scope), limit=8)
        except Exception as exc:
            evidence.errors.append(f"wikidata_first_hop: {type(exc).__name__}: {exc}")
            evidence.route.source_statuses["wikidata"] = "partial"
            return evidence

        evidence.wikidata.extend(donors)
        for donor in donors:
            term = str(donor.get("label") or "").split("(")[0].strip()
            if not term:
                continue
            source_errors: list[str] = []
            try:
                second_hops = kb.second_hop_parallel(
                    term,
                    limit=4,
                    use_getty_aat=route.use_getty_aat,
                    use_asknature=route.use_asknature,
                    errors=source_errors,
                )
            except Exception as exc:
                source_errors.append(f"second_hop: {type(exc).__name__}: {exc}")
                second_hops = {}
            evidence.getty_aat.extend(second_hops.get("getty_aat") or [])
            evidence.asknature.extend(second_hops.get("asknature") or [])
            for error in source_errors:
                source_name = error.partition(":")[0]
                affected_sources = (
                    ("getty_aat", "asknature") if source_name == "second_hop" else (source_name,)
                )
                for affected_source in affected_sources:
                    if affected_source not in evidence.partial_sources:
                        evidence.partial_sources.append(affected_source)
                evidence.errors.append(error)

        for source_name, enabled in (
            ("getty_aat", route.use_getty_aat),
            ("asknature", route.use_asknature),
        ):
            if enabled:
                evidence.route.source_statuses[source_name] = (
                    "partial" if source_name in evidence.partial_sources else "ok"
                )
        return evidence
