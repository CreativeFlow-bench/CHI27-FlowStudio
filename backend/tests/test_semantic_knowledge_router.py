"""Knowledge-route decisions and their bounded evidence collection."""

from __future__ import annotations

import pytest

from app.models import SemanticDivergenceRequest
from app.services.divergence import knowledge_adapters as kb
from app.services.divergence.semantic_knowledge_router import SemanticKnowledgeRouter


@pytest.fixture
def router() -> SemanticKnowledgeRouter:
    return SemanticKnowledgeRouter()


@pytest.fixture
def request_factory():
    def make(
        *, scope: str, temperature: float, intent: str, semantic_role: str = "part"
    ) -> SemanticDivergenceRequest:
        return SemanticDivergenceRequest(
            run_id="run_1",
            decision_id="decision_1",
            session_id="session_1",
            asset_id="asset_1",
            object_identity="cap",
            semantic_target={
                "level": "part",
                "label_en": "brim",
                "semantic_role": semantic_role,
            },
            scope=scope,
            user_semantic_intent=intent,
            behavior_summary="refine the selected target",
            behavior_window_id="window_1",
            temperature=temperature,
        )

    return make


def test_low_temperature_part_refinement_is_model_only(router, request_factory) -> None:
    route = router.choose_route(request_factory(scope="part", temperature=0.2, intent="帽檐稍微外卷"))
    assert route.mode == "model_only"
    assert route.use_wikidata is False


def test_material_intent_routes_to_getty(router, request_factory) -> None:
    route = router.choose_route(request_factory(scope="material_region", temperature=0.5, intent="探索皮包材质"))
    assert route.use_wikidata is True
    assert route.use_getty_aat is True
    assert route.use_asknature is False


def test_biomimetic_intent_routes_to_asknature(router, request_factory) -> None:
    route = router.choose_route(request_factory(scope="part", temperature=0.6, intent="仿生承重连接"))
    assert route.use_asknature is True


def test_trusted_material_role_routes_neutral_low_temperature_request_to_getty(
    router, request_factory
) -> None:
    route = router.choose_route(
        request_factory(
            scope="part",
            temperature=0.2,
            intent="continue exploring this area",
            semantic_role="material",
        )
    )

    assert route.mode == "knowledge_augmented"
    assert route.use_getty_aat is True
    assert route.use_asknature is False


def test_trusted_mechanism_role_routes_neutral_low_temperature_request_to_asknature(
    router, request_factory
) -> None:
    route = router.choose_route(
        request_factory(
            scope="part",
            temperature=0.2,
            intent="continue exploring this area",
            semantic_role="mechanism",
        )
    )

    assert route.mode == "knowledge_augmented"
    assert route.use_asknature is True


def test_high_temperature_cross_domain_uses_both_second_hops(router, request_factory) -> None:
    route = router.choose_route(request_factory(scope="whole", temperature=0.9, intent="跨域结构迁移"))
    assert route.use_getty_aat is True
    assert route.use_asknature is True


def test_collect_keeps_asknature_evidence_when_getty_is_unavailable(router, request_factory, monkeypatch) -> None:
    request = request_factory(scope="whole", temperature=0.9, intent="跨域结构迁移")
    request.semantic_target.wikidata_qid = "Q123"
    monkeypatch.setattr(
        kb,
        "wikidata_first_hop",
        lambda *_args, **_kwargs: [{"id": "Q456", "label": "arch"}],
    )

    def unavailable_getty(*_args, **_kwargs):
        raise RuntimeError("getty unavailable")

    monkeypatch.setattr(kb, "getty_aat_search", unavailable_getty)
    monkeypatch.setattr(
        kb,
        "asknature_search",
        lambda *_args, **_kwargs: [{"graph": "asknature", "id": "strategy/arch", "label": "Arch Strategy"}],
    )

    evidence = router.collect(request, router.choose_route(request))

    assert evidence.partial_sources == ["getty_aat"]
    assert evidence.asknature == [{"graph": "asknature", "id": "strategy/arch", "label": "Arch Strategy"}]
    assert any("getty unavailable" in error for error in evidence.errors)


def test_collect_does_not_bypass_failed_wikidata_grounding(router, request_factory, monkeypatch) -> None:
    request = request_factory(scope="whole", temperature=0.9, intent="跨域结构迁移")
    calls: list[str] = []
    monkeypatch.setattr(kb, "ground_wikidata", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(kb, "second_hop_parallel", lambda *_args, **_kwargs: calls.append("second_hop") or {})

    evidence = router.collect(request, router.choose_route(request))

    assert evidence.route.mode == "model_only"
    assert "wikidata_grounding_failed" in evidence.errors
    assert calls == []


def test_collect_returns_wikidata_evidence_when_second_hop_wrapper_fails(router, request_factory, monkeypatch) -> None:
    request = request_factory(scope="whole", temperature=0.9, intent="跨域结构迁移")
    request.semantic_target.wikidata_qid = "Q123"
    monkeypatch.setattr(
        kb,
        "wikidata_first_hop",
        lambda *_args, **_kwargs: [{"id": "Q456", "label": "arch"}],
    )

    def unavailable_second_hop(*_args, **_kwargs):
        raise RuntimeError("second-hop unavailable")

    monkeypatch.setattr(kb, "second_hop_parallel", unavailable_second_hop)

    evidence = router.collect(request, router.choose_route(request))

    assert [item["id"] for item in evidence.wikidata] == ["Q123", "Q456"]
    assert any("second-hop unavailable" in error for error in evidence.errors)
