"""Model-client contracts for post-Gate semantic divergence."""

from __future__ import annotations

import asyncio
import copy
from hashlib import sha256
import json
import urllib.error

import pytest

from app.config import Settings
from app.models import (
    DecisionIR,
    DecisionOption,
    FourStageRun,
    FourStageStage,
    GateAction,
    GateDecision,
    IntentIR,
    KnowledgeEvidence,
    KnowledgeRoute,
    ScopeGate,
    SemanticCandidate,
    SemanticDivergenceParams,
    SemanticDivergenceRequest,
    SourceContext,
    UserEvent,
)
from app.services.divergence.semantic_divergence_service import SemanticDivergenceService
from app.services.divergence.semantic_model_clients import (
    GeminiSemanticGenerator,
    LocalVlmSemanticGenerator,
    SemanticModelOutputError,
    SemanticModelUnavailable,
)
from app.services.divergence.semantic_validator import SemanticCandidateValidator


def _request() -> SemanticDivergenceRequest:
    return SemanticDivergenceRequest(
        run_id="run_1",
        decision_id="decision_1",
        session_id="session_1",
        asset_id="asset_1",
        object_identity="table lamp",
        semantic_target={"level": "part", "part_id": "shade", "label_en": "shade"},
        scope="part",
        user_semantic_intent="make the shade feel warmer",
        behavior_summary="The user selected the lampshade after repeated surface edits.",
        behavior_window_id="window_1",
        params={"temperature": 0.4},
    )


def test_gemini_payload_uses_mapped_temperature() -> None:
    """Changing the shared temperature mapping must change provider payloads."""
    generator = GeminiSemanticGenerator(
        api_base="https://example.invalid/v1", api_key="", model="gemini-test"
    )

    payload = generator.build_payload(_request(), KnowledgeEvidence())

    assert payload["temperature"] == _request().params.model_temperature
    assert "2–8个字" in payload["messages"][0]["content"]
    assert "Aesthetic" in payload["messages"][0]["content"]


def test_semantic_prompt_preserves_authoritative_material_region_reference() -> None:
    """Without an explicit output rule, real models commonly collapse a mask to whole."""
    generator = GeminiSemanticGenerator(
        api_base="https://example.invalid/v1", api_key="", model="gemini-test"
    )
    request = SemanticDivergenceRequest.model_validate(
        {
            **_request().model_dump(mode="json"),
            "scope": "material_region",
            "semantic_target": {
                "level": "material_region",
                "part_id": "body_material",
                "mask_ref": "mask://handbag-body",
            },
        }
    )

    payload = generator.build_payload(request, KnowledgeEvidence())

    system_prompt = payload["messages"][0]["content"]
    assert "material_region" in system_prompt
    assert "mask_ref" in system_prompt


def _valid_semantic_response() -> dict[str, object]:
    return {
        "candidates": [
            {
                "candidate_id": f"kw_{index}",
                "display_label_zh": "熔岩流线",
                "label_en": "lava flow lines",
                "group": "semantic_transfer",
                "target_ref": {"asset_id": "asset_1", "type": "part", "id": "shade"},
                "operation": "deform",
                "semantic_anchor": "cooling lava",
                "prompt_phrase": "reshape only the shade with lava-flow contours",
                "attribute_delta": {"attribute": "contour", "change": "flow ridges"},
                "scores": {
                    "identity": 0.9,
                    "scope": 0.9,
                    "relevance": 0.9,
                    "specificity": 0.9,
                    "novelty": 0.8,
                },
                "provenance": {"generator": "untrusted", "mode": "model_only"},
            }
            for index in range(1, 10)
        ]
    }


def test_local_vlm_uses_same_response_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dropping the shared parser would return raw Qwen output instead of candidates."""
    generator = LocalVlmSemanticGenerator(
        endpoint_url="http://127.0.0.1:9999/v1/chat/completions", model="qwen2.5-vl"
    )
    monkeypatch.setattr(generator, "_post_json", lambda payload: _valid_semantic_response())

    result = generator.generate_sync(_request(), KnowledgeEvidence())

    assert result[0].candidate_id == "kw_1"
    assert result[0].provenance.generator == "qwen2.5-vl"


def test_local_vlm_payload_requests_nine_concise_candidates() -> None:
    generator = LocalVlmSemanticGenerator(
        endpoint_url="http://127.0.0.1:9999/v1/chat/completions", model="qwen2.5-vl"
    )

    payload = generator.build_payload(_request(), KnowledgeEvidence())
    content = json.loads(payload["messages"][1]["content"])

    assert content["response_schema"]["candidate_count"] == 9
    assert content["request"]["params"]["candidate_count"] == 9
    assert "exactly 9" in content["response_schema"]["requirements"][0]


def test_extract_json_accepts_complete_markdown_fence() -> None:
    response = {
        "choices": [
            {"message": {"content": "```json\n{\"candidates\": []}\n```"}}
        ]
    }

    assert LocalVlmSemanticGenerator._extract_json(response) == {"candidates": []}


def test_local_vlm_normalizes_only_known_group_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = LocalVlmSemanticGenerator(
        endpoint_url="http://127.0.0.1:9999/v1/chat/completions", model="qwen2.5-vl"
    )
    response = _valid_semantic_response()
    response["candidates"][0]["group"] = "material"  # type: ignore[index]
    monkeypatch.setattr(generator, "_post_json", lambda payload: response)

    result = generator.generate_sync(_request(), KnowledgeEvidence())

    assert result[0].group == "surface"


def test_async_generate_uses_the_same_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    """Removing the public async boundary would break service orchestration."""
    generator = LocalVlmSemanticGenerator(
        endpoint_url="http://127.0.0.1:9999/v1/chat/completions", model="qwen2.5-vl"
    )
    monkeypatch.setattr(generator, "_post_json", lambda payload: _valid_semantic_response())

    result = asyncio.run(generator.generate(_request(), KnowledgeEvidence()))

    assert result[0].provenance.generator == "qwen2.5-vl"


def test_transport_error_becomes_model_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Letting URLError escape would prevent the fallback policy from running."""
    generator = LocalVlmSemanticGenerator(endpoint_url="http://127.0.0.1:9999", model="qwen2.5-vl")
    calls = 0

    def offline(payload: object) -> object:
        nonlocal calls
        calls += 1
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(generator, "_post_json", offline)

    with pytest.raises(SemanticModelUnavailable):
        generator.generate_sync(_request(), KnowledgeEvidence())

    assert calls == 1


def test_invalid_json_becomes_model_output_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Treating a non-JSON HTTP body as unavailability would hide a provider contract failure."""
    generator = LocalVlmSemanticGenerator(endpoint_url="http://127.0.0.1:9999", model="qwen2.5-vl")

    class InvalidJsonResponse:
        def __enter__(self) -> "InvalidJsonResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        @staticmethod
        def read() -> bytes:
            return b"not json"

    monkeypatch.setattr(
        "app.services.divergence.semantic_model_clients.urllib.request.urlopen",
        lambda request, timeout: InvalidJsonResponse(),
    )

    with pytest.raises(SemanticModelOutputError):
        generator._post_json({"model": "gemini-test"})


def test_missing_prompt_phrase_becomes_model_output_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Accepting an incomplete candidate would break downstream prompt construction."""
    generator = LocalVlmSemanticGenerator(endpoint_url="http://127.0.0.1:9999", model="qwen2.5-vl")
    invalid = _valid_semantic_response()
    invalid["candidates"][0].pop("prompt_phrase")  # type: ignore[index]
    monkeypatch.setattr(generator, "_post_json", lambda payload: invalid)

    with pytest.raises(SemanticModelOutputError):
        generator.generate_sync(_request(), KnowledgeEvidence())


def test_non_object_candidate_becomes_model_output_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Silently dropping a malformed candidate would violate the 9–15-item contract."""
    generator = LocalVlmSemanticGenerator(endpoint_url="http://127.0.0.1:9999", model="qwen2.5-vl")
    invalid = _valid_semantic_response()
    invalid["candidates"][0] = "not a candidate"  # type: ignore[index]
    monkeypatch.setattr(generator, "_post_json", lambda payload: invalid)

    with pytest.raises(SemanticModelOutputError):
        generator.generate_sync(_request(), KnowledgeEvidence())


def test_invalid_output_is_repaired_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retrying malformed output more than once would multiply model calls without a new signal."""
    generator = LocalVlmSemanticGenerator(endpoint_url="http://127.0.0.1:9999", model="qwen2.5-vl")
    invalid = copy.deepcopy(_valid_semantic_response())
    invalid["candidates"][0].pop("prompt_phrase")  # type: ignore[index]
    responses = [invalid, _valid_semantic_response()]
    payloads: list[dict[str, object]] = []

    def reply(payload: dict[str, object]) -> dict[str, object]:
        payloads.append(payload)
        return responses.pop(0)

    monkeypatch.setattr(generator, "_post_json", reply)

    result = generator.generate_sync(_request(), KnowledgeEvidence())

    assert result[0].prompt_phrase == "reshape only the shade with lava-flow contours"
    assert len(payloads) == 2
    assert "previous_attempt_validation_errors" in payloads[1]["messages"][1]["content"]  # type: ignore[index]


def test_first_transport_invalid_json_is_repaired_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """A malformed provider body is repairable output, not immediate fallback."""
    generator = LocalVlmSemanticGenerator(endpoint_url="http://127.0.0.1:9999", model="qwen2.5-vl")
    responses: list[object] = [
        SemanticModelOutputError("semantic model returned invalid JSON"),
        _valid_semantic_response(),
    ]
    payloads: list[dict[str, object]] = []

    def reply(payload: dict[str, object]) -> dict[str, object]:
        payloads.append(payload)
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response  # type: ignore[return-value]

    monkeypatch.setattr(generator, "_post_json", reply)

    result = generator.generate_sync(_request(), KnowledgeEvidence())

    assert result[0].candidate_id == "kw_1"
    assert len(payloads) == 2
    assert "previous_attempt_validation_errors" in payloads[1]["messages"][1]["content"]  # type: ignore[index]


def test_persistent_transport_invalid_json_stops_after_one_repair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = LocalVlmSemanticGenerator(endpoint_url="http://127.0.0.1:9999", model="qwen2.5-vl")
    payloads: list[dict[str, object]] = []

    def invalid_json(payload: dict[str, object]) -> object:
        payloads.append(payload)
        raise SemanticModelOutputError("semantic model returned invalid JSON")

    monkeypatch.setattr(generator, "_post_json", invalid_json)

    with pytest.raises(SemanticModelOutputError, match="after one repair"):
        generator.generate_sync(_request(), KnowledgeEvidence())

    assert len(payloads) == 2


def test_semantic_client_defaults_are_bounded() -> None:
    """Removing the divergence-specific limits would leave generation unbounded."""
    settings = Settings()

    assert settings.semantic_divergence_enabled is True
    assert settings.semantic_divergence_timeout_sec == 25
    assert settings.semantic_divergence_vlm_timeout_sec == 35
    assert (settings.semantic_divergence_min_candidates, settings.semantic_divergence_max_candidates) == (9, 15)


@pytest.fixture
def request_factory():
    def make(**overrides: object) -> SemanticDivergenceRequest:
        payload: dict[str, object] = {
            "run_id": "run_1",
            "decision_id": "decision_1",
            "session_id": "session_1",
            "asset_id": "asset_1",
            "object_identity": "table lamp",
            "semantic_target": {"level": "part", "part_id": "shade", "label_en": "shade"},
            "scope": "part",
            "user_semantic_intent": "make the shade surface warmer",
            "behavior_summary": "The user selected the shade.",
            "behavior_window_id": "window_1",
            "params": {"temperature": 0.4, "strictness": 0.6},
        }
        target_id = overrides.pop("target_id", None)
        if target_id is not None:
            payload["semantic_target"] = {
                "level": "part",
                "part_id": target_id,
                "label_en": target_id,
            }
        payload.update(overrides)
        return SemanticDivergenceRequest.model_validate(payload)

    return make


@pytest.fixture
def semantic_request(request_factory):
    return request_factory()


@pytest.fixture
def candidate_factory():
    def make(
        *,
        candidate_id: str = "kw_1",
        label: str = "熔岩流线",
        label_en: str = "lava flow lines",
        group: str = "semantic_transfer",
        target_type: str = "part",
        target_id: str | None = "shade",
        asset_id: str = "asset_1",
        operation: str = "deform",
        attribute: str = "contour",
        change: str = "solidified flow ridges",
        identity: float = 0.9,
        scope_score: float = 0.9,
        relevance: float = 0.9,
        specificity: float = 0.9,
        novelty: float = 0.8,
        provenance_mode: str = "model_only",
        provenance_sources: list[dict[str, object]] | None = None,
    ) -> SemanticCandidate:
        sources = provenance_sources or []
        return SemanticCandidate.model_validate(
            {
                "candidate_id": candidate_id,
                "display_label_zh": label,
                "label_en": label_en,
                "group": group,
                "target_ref": {"asset_id": asset_id, "type": target_type, "id": target_id},
                "operation": operation,
                "semantic_anchor": "cooling lava",
                "prompt_phrase": "reshape only the shade with lava-flow contours",
                "attribute_delta": {"attribute": attribute, "change": change},
                "scores": {
                    "identity": identity,
                    "scope": scope_score,
                    "relevance": relevance,
                    "specificity": specificity,
                    "novelty": novelty,
                },
                "provenance": {
                    "generator": "gemini",
                    "mode": provenance_mode,
                    "wikidata": sources,
                },
            }
        )

    return make


@pytest.fixture
def validator() -> SemanticCandidateValidator:
    return SemanticCandidateValidator()


def test_validator_rejects_taxonomy_labels(validator, semantic_request, candidate_factory) -> None:
    """Removing the taxonomy guard would surface a category name as a direction."""
    report = validator.validate(semantic_request, [candidate_factory(label="Aesthetic")])

    assert report.accepted == []
    assert report.rejection_counts["taxonomy_label"] == 1


@pytest.mark.parametrize("label_en", ["cross domain", "cross_domain", "cross-domain"])
def test_validator_normalizes_english_banned_taxonomy_labels(
    validator, semantic_request, candidate_factory, label_en
) -> None:
    """Leaving separators intact would let a banned cross-domain label evade the guard."""
    report = validator.validate(
        semantic_request, [candidate_factory(label="熔岩流线", label_en=label_en)]
    )

    assert report.rejection_counts["taxonomy_label"] == 1


@pytest.mark.parametrize(
    "label_en", ["concept", "design", "proposal", "plan", "style", "variation", "change"]
)
def test_validator_rejects_english_generic_taxonomy_counterparts(
    validator, semantic_request, candidate_factory, label_en
) -> None:
    """Omitting English equivalents would expose the same banned taxonomy in another language."""
    report = validator.validate(
        semantic_request, [candidate_factory(label="熔岩流线", label_en=label_en)]
    )

    assert report.rejection_counts["taxonomy_label"] == 1


def test_validator_applies_strictness_thresholds(validator, request_factory, candidate_factory) -> None:
    """Ignoring strictness would let a weak identity score pass a strict request."""
    request = request_factory(params={"temperature": 0.4, "strictness": 0.8})
    report = validator.validate(
        request, [candidate_factory(identity=0.7, scope_score=0.95, relevance=0.95)]
    )

    assert report.rejection_counts["identity_below_threshold"] == 1


def test_part_scope_rejects_whole_object_operation(
    validator, request_factory, candidate_factory
) -> None:
    """Dropping the part gate would let a whole-object mutation escape a part edit."""
    request = request_factory(scope="part", target_id="hat")
    candidate = candidate_factory(target_type="whole", target_id=None)

    assert validator.validate(request, [candidate]).accepted == []


def test_material_region_scope_accepts_only_authoritative_mask_target(
    validator, request_factory, candidate_factory
) -> None:
    """Collapsing a masked material edit to whole loses the authoritative region."""
    request = request_factory(
        scope="material_region",
        semantic_target={
            "level": "material_region",
            "part_id": "body_material",
            "label_en": "handbag body material",
            "mask_ref": "mask://handbag-body",
        },
    )
    accepted = candidate_factory(
        target_type="material_region", target_id="mask://handbag-body"
    )
    wrong_mask = candidate_factory(
        candidate_id="wrong_mask",
        label="错误遮罩",
        label_en="wrong mask",
        target_type="material_region",
        target_id="mask://other",
    )
    whole = candidate_factory(
        candidate_id="whole_material",
        label="整体覆层",
        label_en="whole coating",
        target_type="whole",
        target_id=None,
    )

    assert validator.validate(request, [accepted]).accepted == [accepted]
    assert validator.validate(request, [wrong_mask]).rejection_counts["target_not_found"] == 1
    assert validator.validate(request, [whole]).accepted == []


def test_validator_uses_the_first_failed_check_for_audit_counts(
    validator, semantic_request, candidate_factory
) -> None:
    """Reordering checks would misattribute a taxonomy label to a later validation rule."""
    candidate = candidate_factory(label="Aesthetic", identity=0.0)

    report = validator.validate(semantic_request, [candidate])

    assert report.rejection_counts["taxonomy_label"] == 1
    assert "identity_below_threshold" not in report.rejection_counts


def test_validator_rejects_inherited_label_duplicates(validator, request_factory, candidate_factory) -> None:
    """Skipping normalized inherited-label checks would repeat a prior direction."""
    request = request_factory(params={"inherited_keywords": ["熔岩，流线"]})

    report = validator.validate(request, [candidate_factory(label="熔岩 流线")])

    assert report.rejection_counts["inherited_duplicate"] == 1


def test_validator_rejects_display_labels_outside_the_short_label_limit(
    validator, semantic_request, candidate_factory
) -> None:
    """Removing the UI length guard would expose sentence-like labels in the candidate strip."""
    report = validator.validate(semantic_request, [candidate_factory(label="短")])

    assert report.rejection_counts["display_length"] == 1


def test_validator_checks_target_existence_before_scope(validator, semantic_request, candidate_factory) -> None:
    """Checking scope first would misreport a candidate that points at another asset."""
    candidate = candidate_factory(asset_id="other_asset", target_type="whole", target_id=None)

    report = validator.validate(semantic_request, [candidate])

    assert report.rejection_counts["target_not_found"] == 1


def test_validator_keeps_the_higher_quality_semantic_duplicate(
    validator, semantic_request, candidate_factory
) -> None:
    """Keeping the first duplicate would discard the stronger candidate deterministically."""
    weaker = candidate_factory(candidate_id="weak", label="熔岩脊线", relevance=0.7)
    stronger = candidate_factory(candidate_id="strong", label="火山脊线", relevance=0.95)

    report = validator.validate(semantic_request, [weaker, stronger])

    assert [candidate.candidate_id for candidate in report.accepted] == ["strong"]
    assert report.rejection_counts["duplicate"] == 1


def test_validator_marks_small_collections_for_fallback(
    validator, semantic_request, candidate_factory
) -> None:
    """Removing the collection gate would send fewer than nine candidates downstream."""
    report = validator.validate(semantic_request, [candidate_factory()])

    assert report.needs_fallback is True
    assert report.rejection_counts["minimum_candidates"] == 8


def test_hot_requests_require_two_semantic_transfers(validator, request_factory, candidate_factory) -> None:
    """Ignoring temperature would allow high-diversity batches with too few transfers."""
    request = request_factory(params={"temperature": 0.7, "strictness": 0.6})
    candidates = [
        candidate_factory(
            candidate_id=f"kw_{index}",
            label=f"熔岩纹{index}",
            group="surface" if index % 2 else "shape",
            change=f"ridge {index}",
        )
        for index in range(9)
    ]

    report = validator.validate(request, candidates)

    assert report.needs_fallback is True
    assert report.rejection_counts["minimum_semantic_transfer"] == 2


def test_collection_gate_requires_two_intent_relevant_groups(
    validator, semantic_request, candidate_factory
) -> None:
    """Dropping group coverage would accept a one-dimensional surface-only batch."""
    candidates = [
        candidate_factory(
            candidate_id=f"kw_{index}",
            label=f"表面纹{index}",
            label_en=f"surface pattern {index}",
            group="surface",
            change=f"finish pattern {index}",
        )
        for index in range(9)
    ]

    report = validator.validate(semantic_request, candidates)

    assert report.needs_fallback is True
    assert report.rejection_counts["group_coverage"] == 1


def test_validator_rejects_a_complete_collection_of_distinct_generic_labels(
    validator, semantic_request, candidate_factory
) -> None:
    """Without a generic-label gate, numbered filler labels satisfy every collection count."""
    candidates = [
        candidate_factory(
            candidate_id=f"kw_{index}",
            label=f"方案{index}",
            label_en=f"option {index}",
            group="surface" if index % 2 else "semantic_transfer",
            change=f"finish {index}",
        )
        for index in range(9)
    ]

    report = validator.validate(semantic_request, candidates)

    assert report.accepted == []
    assert report.rejection_counts["taxonomy_label"] == 9
    assert "generic_label" not in report.rejection_counts
    assert report.needs_fallback is True


@pytest.mark.parametrize("generic_label", ["方案", "option"])
def test_validator_rejects_full_width_digit_padded_generic_labels(
    validator, semantic_request, candidate_factory, generic_label
) -> None:
    """ASCII-only suffix stripping would let full-width numbered filler satisfy the gate."""
    candidates = [
        candidate_factory(
            candidate_id=f"kw_{index}",
            label=f"{generic_label}{chr(0xFF10 + index)}",
            label_en=f"{generic_label}{chr(0xFF10 + index)}",
            group="surface" if index % 2 else "semantic_transfer",
            change=f"finish {index}",
        )
        for index in range(1, 10)
    ]

    report = validator.validate(semantic_request, candidates)

    assert report.accepted == []
    assert report.rejection_counts["taxonomy_label"] == 9
    assert "generic_label" not in report.rejection_counts
    assert report.needs_fallback is True


def test_validator_rejects_chinese_numeral_padded_generic_collection(
    validator, semantic_request, candidate_factory
) -> None:
    """Digit-only suffix handling would let Chinese-numbered filler complete the collection."""
    candidates = [
        candidate_factory(
            candidate_id=f"kw_{index}",
            label=f"方案{numeral}",
            label_en=f"lava ridge {index}",
            group="surface" if index % 2 else "semantic_transfer",
            change=f"finish {index}",
        )
        for index, numeral in enumerate("一二三四五六七八九", start=1)
    ]

    report = validator.validate(semantic_request, candidates)

    assert report.accepted == []
    assert report.rejection_counts["taxonomy_label"] == 9
    assert report.needs_fallback is True


@pytest.mark.parametrize(
    ("label", "label_en"),
    [
        ("方案一", "lava flow lines"),
        ("选项十", "lava flow lines"),
        ("熔岩流线", "option one"),
        ("熔岩流线", "option fifteen"),
    ],
)
def test_validator_rejects_common_number_word_generic_suffixes(
    validator, semantic_request, candidate_factory, label, label_en
) -> None:
    """A suffix recognizer limited to decimal digits would leave word-number padding valid."""
    report = validator.validate(
        semantic_request, [candidate_factory(label=label, label_en=label_en)]
    )

    assert report.rejection_counts["taxonomy_label"] == 1


def test_validator_rejects_compositional_number_word_generic_collection(
    validator, semantic_request, candidate_factory
) -> None:
    """A finite number-word list would let later numbered options complete the collection."""
    number_words = (
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
        "twenty",
        "twenty-one",
        "twenty two",
        "twentythree",
        "twentyfour",
    )
    candidates = [
        candidate_factory(
            candidate_id=f"kw_{index}",
            label=f"熔岩纹{index}",
            label_en=f"option {number_word}",
            group="surface" if index % 2 else "semantic_transfer",
            change=f"finish {index}",
        )
        for index, number_word in enumerate(number_words, start=16)
    ]

    report = validator.validate(semantic_request, candidates)

    assert report.accepted == []
    assert report.rejection_counts["taxonomy_label"] == 9
    assert report.needs_fallback is True


@pytest.mark.parametrize(
    ("label", "label_en"),
    [
        ("方案Ⅻ", "lava flow lines"),
        ("方案²", "lava flow lines"),
        ("方案四百二十一", "lava flow lines"),
        ("熔岩流线", "option one hundred and twenty-fourth"),
        ("熔岩流线", "option A"),
        ("熔岩流线", "option IX"),
    ],
)
def test_validator_rejects_generic_labels_with_identifier_only_suffixes(
    validator, semantic_request, candidate_factory, label, label_en
) -> None:
    """Restricting suffixes to decimal digits would miss standard enumerator forms."""
    report = validator.validate(
        semantic_request, [candidate_factory(label=label, label_en=label_en)]
    )

    assert report.rejection_counts["taxonomy_label"] == 1


def test_validator_rejects_alphanumeric_generic_enumerator_collection(
    validator, semantic_request, candidate_factory
) -> None:
    """Number-letter identifiers must not let generic options complete the collection."""
    candidates = [
        candidate_factory(
            candidate_id=f"kw_{index}",
            label=f"熔岩纹{index}",
            label_en=f"option {index}A",
            group="surface" if index % 2 else "semantic_transfer",
            change=f"finish {index}",
        )
        for index in range(1, 10)
    ]

    report = validator.validate(semantic_request, candidates)

    assert report.accepted == []
    assert report.rejection_counts["taxonomy_label"] == 9
    assert report.needs_fallback is True


@pytest.mark.parametrize("label_en", ["option A1", "option 1A", "option AA"])
def test_validator_rejects_generic_labels_with_enumerator_codes(
    validator, semantic_request, candidate_factory, label_en
) -> None:
    """Dropping either identifier order or short letter codes would reopen generic padding."""
    report = validator.validate(
        semantic_request, [candidate_factory(label="熔岩流线", label_en=label_en)]
    )

    assert report.rejection_counts["taxonomy_label"] == 1


@pytest.mark.parametrize(
    ("label", "label_en"),
    [
        ("方案流线", "option flow"),
        ("方案十字纹", "option first light"),
        ("熔岩流线", "option mix"),
        ("熔岩流线", "option flow2"),
    ],
)
def test_validator_keeps_generic_stems_with_meaningful_suffixes(
    validator, semantic_request, candidate_factory, label, label_en
) -> None:
    """Treating every generic-stem prefix as filler would reject semantic direction labels."""
    candidate = candidate_factory(label=label, label_en=label_en)

    report = validator.validate(semantic_request, [candidate])

    assert report.accepted == [candidate]
    assert "taxonomy_label" not in report.rejection_counts


def test_banned_label_precedes_inherited_duplicate(validator, request_factory, candidate_factory) -> None:
    """Moving generic labels past inherited checks would break the fixed audit order."""
    request = request_factory(params={"inherited_keywords": ["灵感"]})

    report = validator.validate(request, [candidate_factory(label="灵感")])

    assert report.rejection_counts["taxonomy_label"] == 1
    assert "inherited_duplicate" not in report.rejection_counts


def test_english_hyphen_variants_remain_distinct_for_deduplication(
    validator, semantic_request, candidate_factory
) -> None:
    """Using taxonomy normalization for dedupe would collapse distinct English labels."""
    hyphenated = candidate_factory(
        candidate_id="hyphenated",
        label="折纹一",
        label_en="re-form",
        group="surface",
        change="folded finish",
    )
    plain = candidate_factory(
        candidate_id="plain",
        label="折纹二",
        label_en="reform",
        change="reformed finish",
    )

    report = validator.validate(semantic_request, [hyphenated, plain])

    assert {candidate.candidate_id for candidate in report.accepted} == {"hyphenated", "plain"}
    assert "duplicate" not in report.rejection_counts


def test_english_hyphen_variants_remain_distinct_for_inherited_duplicates(
    validator, request_factory, candidate_factory
) -> None:
    """Applying separator-insensitive taxonomy matching to inheritance would reject a distinct label."""
    request = request_factory(params={"inherited_keywords": ["re-form"]})
    candidate = candidate_factory(label_en="reform")

    report = validator.validate(request, [candidate])

    assert report.accepted == [candidate]
    assert "inherited_duplicate" not in report.rejection_counts


# SemanticDivergenceService orchestration tests. The fakes replace only the
# external knowledge/model boundaries; request construction, validation,
# fallback policy, persistence, and audit behavior are exercised for real.
class _FakeStore:
    def __init__(self) -> None:
        self.saved_runs: list[FourStageRun] = []
        self.audits: list[dict[str, object]] = []
        self.runs: dict[str, FourStageRun] = {}

    def save_run(self, run: FourStageRun) -> FourStageRun:
        saved = run.model_copy(deep=True)
        self.saved_runs.append(saved)
        self.runs[run.run_id] = saved
        return run

    def get_run(self, run_id: str) -> FourStageRun | None:
        run = self.runs.get(run_id)
        return run.model_copy(deep=True) if run is not None else None

    def record_model_call(self, **audit: object) -> None:
        self.audits.append(audit)


class _FakeKnowledgeRouter:
    def __init__(self, order: list[str]) -> None:
        self.order = order
        self.choose_error: Exception | None = None
        self.collect_error: Exception | None = None
        self.route = KnowledgeRoute(mode="model_only", reasons=["test"])
        self.choose_calls = 0
        self.collect_calls = 0

    def choose_route(self, request: SemanticDivergenceRequest) -> KnowledgeRoute:
        self.choose_calls += 1
        self.order.append("choose_route")
        if self.choose_error is not None:
            raise self.choose_error
        return self.route.model_copy(deep=True)

    def collect(
        self, request: SemanticDivergenceRequest, route: KnowledgeRoute
    ) -> KnowledgeEvidence:
        self.collect_calls += 1
        self.order.append("collect")
        if self.collect_error is not None:
            raise self.collect_error
        return KnowledgeEvidence(route=route)


class _FakeGenerator:
    def __init__(
        self,
        model: str,
        provider: str,
        order: list[str],
        result: list[SemanticCandidate],
    ) -> None:
        self.model = model
        self.provider = provider
        self.order = order
        self.result = result
        self.error: BaseException | None = None
        self.calls = 0
        self.requests: list[SemanticDivergenceRequest] = []
        self.evidences: list[KnowledgeEvidence] = []
        self.started: asyncio.Event | None = None
        self.release: asyncio.Event | None = None

    async def generate(
        self, request: SemanticDivergenceRequest, evidence: KnowledgeEvidence
    ) -> list[SemanticCandidate]:
        self.calls += 1
        self.order.append(self.provider)
        self.requests.append(request)
        self.evidences.append(evidence)
        if self.started is not None:
            self.started.set()
        if self.release is not None:
            await self.release.wait()
        if self.error is not None:
            raise self.error
        return list(self.result)


_SERVICE_LABELS = (
    ("熔岩折纹", "lava fold"),
    ("水波细脊", "ripple ridge"),
    ("陶瓷渐变", "ceramic gradient"),
    ("花瓣层叠", "petal layering"),
    ("霜晶肌理", "frost texture"),
    ("海谜光泽", "sea glass sheen"),
    ("树皮浅纹", "bark striation"),
    ("云层浮雕", "cloud relief"),
    ("沙丘曲面", "dune surface"),
)


def _service_candidates(generator: str = "gemini") -> list[SemanticCandidate]:
    return [
        SemanticCandidate.model_validate(
            {
                "candidate_id": f"{generator}_{index}",
                "display_label_zh": label_zh,
                "label_en": label_en,
                "group": "surface" if index % 2 else "semantic_transfer",
                "target_ref": {"asset_id": "asset_1", "type": "part", "id": "shade"},
                "operation": "deform",
                "semantic_anchor": label_en,
                "prompt_phrase": f"change only the shade with {label_en}",
                "attribute_delta": {"attribute": "surface", "change": f"finish {index}"},
                "scores": {
                    "identity": 0.95,
                    "scope": 0.95,
                    "relevance": 0.95,
                    "specificity": 0.9,
                    "novelty": 0.8,
                },
                "provenance": {"generator": generator, "mode": "model_only"},
            }
        )
        for index, (label_zh, label_en) in enumerate(_SERVICE_LABELS, start=1)
    ]


@pytest.fixture
def divergence_run() -> FourStageRun:
    return FourStageRun(
        run_id="run_service_1",
        session_id="session_1",
        stage=FourStageStage.awaiting_gate,
        source_event_ids=["locked_event"],
        events=[
            UserEvent(
                type="surface.smoothed",
                event_id="locked_event",
                session_id="session_1",
                payload={
                    "summary": "smoothed the selected shade",
                    "image": "data:image/png;base64,SECRET_MUST_NOT_LEAK",
                },
            ),
            UserEvent(
                type="surface.changed_after_send",
                event_id="later_event",
                session_id="session_1",
                payload={"summary": "must not enter the locked behavior window"},
            ),
        ],
        source_context=SourceContext(
            asset_id="asset_1",
            object_type="table lamp",
            target_part_id="shade",
            target_mask_ref="mask://shade",
        ),
        intent_ir=IntentIR(
            ir_id="intent_1",
            run_id="run_service_1",
            session_id="session_1",
            source_event_ids=["locked_event"],
            target={"asset_id": "asset_1", "object_type": "table lamp", "part_id": "shade"},
            observations={"text": "fallback user text"},
            intent={
                "operation": "refine",
                "scope": "whole",
                "goal": "make the shade surface warmer",
                "constraints": ["preserve lamp identity"],
            },
        ),
        decision=DecisionIR(
            decision_id="decision_1",
            run_id="run_service_1",
            intent_ir_id="intent_1",
            semantic_target="lampshade",
            options=[
                DecisionOption(
                    option_id="option_1",
                    label="warm shade",
                    constraints=["change the shade only"],
                )
            ],
        ),
        scope_gate=ScopeGate(
            gate_id="gate_1",
            target="shade",
            scope="part",
            question="Change the shade?",
            status="accepted",
            user_action="accept",
        ),
        gate_decision=GateDecision(
            decision_id="decision_1",
            run_id="run_service_1",
            action=GateAction.accept_option,
            selected_option_id="option_1",
        ),
    )


@pytest.fixture
def divergence_params() -> SemanticDivergenceParams:
    return SemanticDivergenceParams(
        temperature=0.4,
        strictness=0.6,
        candidate_count=9,
        inherited_keywords=["existing", "existing"],
    )


@pytest.fixture
def divergence_service() -> SemanticDivergenceService:
    order: list[str] = []
    return SemanticDivergenceService(
        store=_FakeStore(),
        knowledge_router=_FakeKnowledgeRouter(order),
        gemini=_FakeGenerator("gemini-test", "gemini", order, _service_candidates()),
        local_vlm=_FakeGenerator(
            "qwen-test", "local_vlm", order, _service_candidates("qwen")
        ),
        validator=SemanticCandidateValidator(),
    )


def test_primary_success_does_not_call_local_vlm(
    divergence_service, divergence_run, divergence_params
) -> None:
    """Calling the backup after a valid primary result would waste GPU work."""
    response = asyncio.run(divergence_service.diverge(divergence_run, divergence_params))

    assert response.status == "completed"
    assert response.fallback_used is False
    assert divergence_service.local_vlm.calls == 0


def test_technical_failure_falls_back_to_local_vlm(
    divergence_service, divergence_run, divergence_params
) -> None:
    """Letting primary unavailability abort would violate the backup-model contract."""
    divergence_service.gemini.error = SemanticModelUnavailable("timeout")

    response = asyncio.run(divergence_service.diverge(divergence_run, divergence_params))

    assert response.status == "completed"
    assert response.fallback_used is True
    assert response.fallback_reason == "primary_model_unavailable"
    assert len(response.candidates) == 9


def test_quality_failure_falls_back_to_local_vlm(
    divergence_service, divergence_run, divergence_params
) -> None:
    """Trusting a taxonomy-only primary result would expose a fake direction."""
    divergence_service.gemini.result = [
        _service_candidates()[0].model_copy(update={"display_label_zh": "Aesthetic"})
    ]

    response = asyncio.run(divergence_service.diverge(divergence_run, divergence_params))

    assert response.fallback_used is True
    assert response.fallback_reason == "insufficient_valid_candidates"
    assert len(response.candidates) >= 9
    assert response.validation_counts["taxonomy_label"] == 1


def test_double_failure_returns_no_fake_keywords(
    divergence_service, divergence_run, divergence_params
) -> None:
    """Synthesizing placeholder keywords after both models fail would hide the outage."""
    divergence_service.gemini.error = SemanticModelUnavailable("timeout")
    divergence_service.local_vlm.error = SemanticModelUnavailable("offline")

    response = asyncio.run(divergence_service.diverge(divergence_run, divergence_params))

    assert response.status == "failed"
    assert response.candidates == []


def test_unexpected_primary_generator_error_uses_local_vlm(
    divergence_service, divergence_run, divergence_params
) -> None:
    """A new provider RuntimeError must remain a technical fallback, not escape as HTTP 500."""
    divergence_service.gemini.error = RuntimeError("provider regression")

    response = asyncio.run(divergence_service.diverge(divergence_run, divergence_params))

    assert response.status == "completed"
    assert response.fallback_used is True
    assert response.fallback_reason == "primary_technical_failure"
    assert divergence_service.local_vlm.calls == 1


def test_unexpected_primary_validator_error_uses_local_vlm(
    divergence_service, divergence_run, divergence_params, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A validator regression on primary output must enter the same technical fallback path."""
    real_validate = divergence_service.validator.validate
    calls = 0

    def fail_primary_once(request, candidates):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("primary validation regression")
        return real_validate(request, candidates)

    monkeypatch.setattr(divergence_service.validator, "validate", fail_primary_once)

    response = asyncio.run(divergence_service.diverge(divergence_run, divergence_params))

    assert response.status == "completed"
    assert response.fallback_reason == "primary_technical_failure"
    assert divergence_service.local_vlm.calls == 1


def test_unexpected_fallback_generator_error_persists_failed_response(
    divergence_service, divergence_run, divergence_params
) -> None:
    """An unknown backup-client error must persist a truthful empty failure response."""
    divergence_service.gemini.error = RuntimeError("primary regression")
    divergence_service.local_vlm.error = RuntimeError("fallback regression")

    response = asyncio.run(divergence_service.diverge(divergence_run, divergence_params))

    assert response.status == "failed"
    assert response.candidates == []
    assert divergence_run.semantic_divergence is response
    assert divergence_service.store.get_run(divergence_run.run_id).semantic_divergence is not None


def test_unexpected_fallback_validator_error_persists_failed_response(
    divergence_service, divergence_run, divergence_params, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A backup validation regression must not leak or return unvalidated candidates."""
    divergence_service.gemini.result = [
        _service_candidates()[0].model_copy(update={"display_label_zh": "Aesthetic"})
    ]
    real_validate = divergence_service.validator.validate
    calls = 0

    def fail_fallback_validation(request, candidates):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("fallback validation regression")
        return real_validate(request, candidates)

    monkeypatch.setattr(divergence_service.validator, "validate", fail_fallback_validation)

    response = asyncio.run(divergence_service.diverge(divergence_run, divergence_params))

    assert response.status == "failed"
    assert response.candidates == []
    assert divergence_run.semantic_divergence is response


def test_unexpected_merge_validator_error_persists_failed_response(
    divergence_service, divergence_run, divergence_params, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The final fallback merge validation is part of the guarded backup attempt."""
    divergence_service.gemini.result = [
        _service_candidates()[0].model_copy(update={"display_label_zh": "Aesthetic"})
    ]
    real_validate = divergence_service.validator.validate
    calls = 0

    def fail_merge_validation(request, candidates):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("merge validation regression")
        return real_validate(request, candidates)

    monkeypatch.setattr(divergence_service.validator, "validate", fail_merge_validation)

    response = asyncio.run(divergence_service.diverge(divergence_run, divergence_params))

    assert response.status == "failed"
    assert response.candidates == []
    assert divergence_run.semantic_divergence is response


def test_primary_cancellation_is_not_converted_to_fallback(
    divergence_service, divergence_run, divergence_params
) -> None:
    """Swallowing CancelledError would keep model work alive after request cancellation."""
    divergence_service.gemini.error = asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(divergence_service.diverge(divergence_run, divergence_params))

    assert divergence_service.local_vlm.calls == 0
    assert divergence_run.semantic_divergence is None


def test_service_builds_context_only_from_the_locked_run(
    divergence_service, divergence_run, divergence_params
) -> None:
    """Using later events or request-side identity fields would violate the trust boundary."""
    asyncio.run(divergence_service.diverge(divergence_run, divergence_params))

    request = divergence_service.gemini.requests[0]
    assert request.object_identity == "table lamp"
    assert request.semantic_target.part_id == "shade"
    assert request.semantic_target.mask_ref == "mask://shade"
    assert request.scope == "part"
    assert request.user_semantic_intent == "make the shade surface warmer"
    assert request.hard_constraints == ["preserve lamp identity", "change the shade only"]
    assert "smoothed the selected shade" in request.behavior_summary
    assert "later_event" not in request.behavior_summary
    assert "SECRET_MUST_NOT_LEAK" not in request.behavior_summary


def test_service_rejects_an_unaccepted_scope_gate(
    divergence_service, divergence_run, divergence_params
) -> None:
    """Generating before the user accepts the Gate would bypass the human checkpoint."""
    divergence_run.scope_gate.status = "pending"

    with pytest.raises(ValueError, match="accepted scope Gate"):
        asyncio.run(divergence_service.diverge(divergence_run, divergence_params))

    assert divergence_service.gemini.calls == 0
    assert divergence_service.local_vlm.calls == 0


def test_service_uses_fixed_order_and_knowledge_failure_does_not_force_fallback(
    divergence_service, divergence_run, divergence_params
) -> None:
    """Treating optional knowledge failure as model failure would invoke the backup needlessly."""
    divergence_service.knowledge_router.collect_error = RuntimeError("knowledge offline")

    response = asyncio.run(divergence_service.diverge(divergence_run, divergence_params))

    assert divergence_service.gemini.order == ["choose_route", "collect", "gemini"]
    assert response.status == "completed"
    assert response.fallback_used is False
    assert response.knowledge_route.mode == "model_only"
    assert "knowledge" in response.knowledge_route.source_statuses


def test_aggregate_knowledge_failure_preserves_enabled_source_audit(
    divergence_service, divergence_run, divergence_params
) -> None:
    """Replacing an attempted route with a generic failure would erase source fidelity."""
    divergence_service.knowledge_router.route = KnowledgeRoute(
        mode="knowledge_augmented",
        use_wikidata=True,
        use_getty_aat=True,
        use_asknature=True,
        reasons=["high_temperature_or_cross_domain"],
    )
    divergence_service.knowledge_router.collect_error = RuntimeError("aggregate offline")

    response = asyncio.run(divergence_service.diverge(divergence_run, divergence_params))

    assert response.status == "completed"
    assert response.fallback_used is False
    assert response.knowledge_route.mode == "model_only"
    assert response.knowledge_route.use_wikidata is True
    assert response.knowledge_route.use_getty_aat is True
    assert response.knowledge_route.use_asknature is True
    assert "high_temperature_or_cross_domain" in response.knowledge_route.reasons
    assert response.knowledge_route.source_statuses == {
        "wikidata": "partial",
        "getty_aat": "partial",
        "asknature": "partial",
    }
    assert divergence_service.gemini.evidences[0].partial_sources == [
        "wikidata",
        "getty_aat",
        "asknature",
    ]
    assert divergence_service.local_vlm.calls == 0


def test_matching_request_key_returns_persisted_response_without_external_calls(
    divergence_service, divergence_run, divergence_params
) -> None:
    """Repeating a settled slider request must not repeat knowledge or model calls."""
    first = asyncio.run(divergence_service.diverge(divergence_run, divergence_params))
    second = asyncio.run(divergence_service.diverge(divergence_run, divergence_params))

    assert second is divergence_run.semantic_divergence
    assert second.request_key == first.request_key
    assert divergence_service.gemini.calls == 1
    assert divergence_service.local_vlm.calls == 0
    assert len(divergence_service.store.saved_runs) == 1


def test_concurrent_identical_requests_share_one_inflight_response(
    divergence_service, divergence_run, divergence_params
) -> None:
    """Two simultaneous same-key requests must not duplicate knowledge or model work."""

    async def run_concurrently():
        divergence_service.gemini.started = asyncio.Event()
        divergence_service.gemini.release = asyncio.Event()
        second_run = divergence_run.model_copy(deep=True)
        first = asyncio.create_task(
            divergence_service.diverge(divergence_run, divergence_params)
        )
        await asyncio.wait_for(divergence_service.gemini.started.wait(), timeout=1)
        second = asyncio.create_task(
            divergence_service.diverge(second_run, divergence_params)
        )
        await asyncio.sleep(0.05)
        divergence_service.gemini.release.set()
        return await asyncio.gather(first, second)

    first_response, second_response = asyncio.run(run_concurrently())

    assert first_response is second_response
    assert divergence_service.knowledge_router.choose_calls == 1
    assert divergence_service.knowledge_router.collect_calls == 1
    assert divergence_service.gemini.calls == 1
    assert len(divergence_service.store.saved_runs) == 1
    assert divergence_service._inflight == {}


def test_cancelling_owner_does_not_cancel_shared_work_or_waiter(
    divergence_service, divergence_run, divergence_params
) -> None:
    """A disconnected first HTTP caller must not cancel another same-key request."""

    async def cancel_owner_with_waiter():
        divergence_service.gemini.started = asyncio.Event()
        divergence_service.gemini.release = asyncio.Event()
        second_run = divergence_run.model_copy(deep=True)
        owner = asyncio.create_task(
            divergence_service.diverge(divergence_run, divergence_params)
        )
        await asyncio.wait_for(divergence_service.gemini.started.wait(), timeout=1)
        waiter = asyncio.create_task(
            divergence_service.diverge(second_run, divergence_params)
        )
        await asyncio.sleep(0)
        owner.cancel()
        with pytest.raises(asyncio.CancelledError):
            await owner
        divergence_service.gemini.release.set()
        response = await asyncio.wait_for(waiter, timeout=1)
        await asyncio.sleep(0)
        return response

    response = asyncio.run(cancel_owner_with_waiter())

    assert response.status == "completed"
    assert divergence_service.knowledge_router.collect_calls == 1
    assert divergence_service.gemini.calls == 1
    assert divergence_service._inflight == {}


def test_cancelling_only_owner_still_cleans_registry_when_shared_work_finishes(
    divergence_service, divergence_run, divergence_params
) -> None:
    """Task cleanup must not depend on any caller remaining alive."""

    async def cancel_only_owner():
        divergence_service.gemini.started = asyncio.Event()
        divergence_service.gemini.release = asyncio.Event()
        owner = asyncio.create_task(
            divergence_service.diverge(divergence_run, divergence_params)
        )
        await asyncio.wait_for(divergence_service.gemini.started.wait(), timeout=1)
        key = divergence_service.request_key(divergence_run, divergence_params)
        shared_task = divergence_service._inflight[key]
        owner.cancel()
        with pytest.raises(asyncio.CancelledError):
            await owner
        divergence_service.gemini.release.set()
        response = await asyncio.wait_for(asyncio.shield(shared_task), timeout=1)
        await asyncio.sleep(0)
        return response

    response = asyncio.run(cancel_only_owner())

    assert response.status == "completed"
    assert len(divergence_service.store.saved_runs) == 1
    assert divergence_service._inflight == {}


def test_failed_inflight_entry_is_cleaned_before_retry(
    divergence_service, divergence_run, divergence_params
) -> None:
    """A completed failed task left in the registry would poison an explicit retry."""
    divergence_service.gemini.error = RuntimeError("primary regression")
    divergence_service.local_vlm.error = RuntimeError("fallback regression")
    failed = asyncio.run(divergence_service.diverge(divergence_run, divergence_params))

    assert failed.status == "failed"
    assert divergence_service._inflight == {}

    divergence_service.store.runs.clear()
    divergence_run.semantic_divergence = None
    divergence_service.gemini.error = None
    divergence_service.local_vlm.error = None
    completed = asyncio.run(divergence_service.diverge(divergence_run, divergence_params))

    assert completed.status == "completed"
    assert divergence_service.gemini.calls == 2


def test_failed_response_with_same_request_key_retries_models_without_manual_clear(
    divergence_service, divergence_run, divergence_params
) -> None:
    """Caching a failed response would make transient dual-model outages unrecoverable."""
    divergence_service.gemini.error = RuntimeError("primary transient outage")
    divergence_service.local_vlm.error = RuntimeError("fallback transient outage")
    failed = asyncio.run(divergence_service.diverge(divergence_run, divergence_params))
    assert failed.status == "failed"

    divergence_service.gemini.error = None
    divergence_service.local_vlm.error = None
    completed = asyncio.run(
        divergence_service.diverge(divergence_run, divergence_params)
    )

    assert completed.status == "completed"
    assert completed.request_key == failed.request_key
    assert divergence_service.gemini.calls == 2


def test_raised_shared_task_is_cleaned_before_retry(
    divergence_service, divergence_run, divergence_params
) -> None:
    """An exception before response persistence must not leave a poisoned task entry."""
    divergence_service.knowledge_router.choose_error = RuntimeError("router regression")

    with pytest.raises(RuntimeError, match="router regression"):
        asyncio.run(divergence_service.diverge(divergence_run, divergence_params))

    assert divergence_service._inflight == {}
    divergence_service.knowledge_router.choose_error = None
    response = asyncio.run(divergence_service.diverge(divergence_run, divergence_params))

    assert response.status == "completed"
    assert divergence_service.knowledge_router.choose_calls == 2
    assert divergence_service.gemini.calls == 1


def test_request_key_matches_the_canonical_material(
    divergence_service, divergence_run, divergence_params
) -> None:
    """Depending on inherited-keyword order would break semantic idempotency."""
    material = {
        "run_id": "run_service_1",
        "decision_id": "decision_1",
        "temperature": 0.4,
        "strictness": 0.6,
        "candidate_count": 9,
        "inherited_keywords": ["existing"],
    }
    expected = sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()

    assert divergence_service.request_key(divergence_run, divergence_params) == expected


def test_model_calls_are_audited_without_request_payloads(
    divergence_service, divergence_run, divergence_params
) -> None:
    """Passing the full request into audit could persist user images or credentials."""
    divergence_service.gemini.error = SemanticModelUnavailable("timeout")

    asyncio.run(divergence_service.diverge(divergence_run, divergence_params))

    assert [audit["provider"] for audit in divergence_service.store.audits] == [
        "gemini",
        "local_vlm",
    ]
    assert divergence_service.store.audits[0]["error_type"] == "SemanticModelUnavailable"
    assert divergence_service.store.audits[1]["error_type"] is None
    for audit in divergence_service.store.audits:
        assert audit["run_id"] == "run_service_1"
        assert isinstance(audit["latency_ms"], int)
        assert set(audit) == {"provider", "model", "run_id", "latency_ms", "error_type"}


def test_main_composes_one_semantic_divergence_service() -> None:
    """Creating an unshared store would break persistence across the FourStage runtime."""
    from app import main

    assert isinstance(main.semantic_divergence_service, SemanticDivergenceService)
    assert main.semantic_divergence_service.store is main.four_stage_store
    assert (
        main.semantic_divergence_service.gemini.model
        == main.settings.model_reasoning_text
    )
    assert (
        main.semantic_divergence_service.local_vlm.model
        == main.settings.model_fast_text
    )
