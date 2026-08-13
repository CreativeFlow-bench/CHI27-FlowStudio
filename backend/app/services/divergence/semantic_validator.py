"""Deterministic validation for generated semantic divergence candidates."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import re
import unicodedata
from typing import Iterable

from app.models import SemanticCandidate, SemanticDivergenceRequest


def _contains_cjk(value: str) -> bool:
    return any("\u4e00" <= character <= "\u9fff" for character in value)


def _normalize_chinese_label(value: str) -> str:
    return "".join(
        character
        for character in value.strip().casefold()
        if not character.isspace() and not unicodedata.category(character).startswith("P")
    )


def _normalize_label(value: str) -> str:
    if _contains_cjk(value):
        return _normalize_chinese_label(value)
    return value.strip().casefold()


def _normalize_taxonomy_label(value: str) -> str:
    return _normalize_chinese_label(value)


_TAXONOMY_LABELS = frozenset(
    _normalize_taxonomy_label(label)
    for label in {
        "aesthetic",
        "structural",
        "functional",
        "cross-domain",
        "shape",
        "connection",
        "material",
        "surface",
        "silhouette",
        "ornament",
        "美学",
        "审美",
        "结构",
        "功能",
        "跨域",
        "形状",
        "连接",
        "材料",
        "材质",
        "表面",
        "轮廓",
        "装饰",
        "设计",
        "概念",
        "方案",
        "风格",
        "变化",
        "concept",
        "design",
        "proposal",
        "plan",
        "style",
        "variation",
        "change",
    }
)

_GENERIC_LABEL_STEMS = frozenset(
    _normalize_taxonomy_label(label)
    for label in {
        "概念",
        "设计",
        "方案",
        "风格",
        "变化",
        "灵感",
        "选项",
        "方向",
        "替代",
        "变体",
        "创意",
        "想法",
        "点子",
        "样式",
        "类别",
        "idea",
        "option",
        "direction",
        "alternative",
        "variant",
        "generic",
        "category",
        "theme",
        "concept",
        "design",
        "proposal",
        "plan",
        "style",
        "variation",
        "change",
    }
)

_CHINESE_NUMERAL_CHARACTERS = frozenset(
    "零〇一二三四五六七八九十百千万亿兆两壹贰叁肆伍陆柒捌玖拾佰仟萬億"
)
_ENGLISH_SMALL_CARDINALS = frozenset(
    {
        "zero",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
    }
)
_ENGLISH_UNITS = frozenset(
    {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine"}
)
_ENGLISH_TENS = frozenset(
    {"twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"}
)
_ENGLISH_SCALES = {
    "thousand": 1_000,
    "million": 1_000_000,
    "billion": 1_000_000_000,
    "trillion": 1_000_000_000_000,
    "quadrillion": 1_000_000_000_000_000,
}
_ENGLISH_ORDINAL_TO_CARDINAL = {
    "zeroth": "zero",
    "first": "one",
    "second": "two",
    "third": "three",
    "fourth": "four",
    "fifth": "five",
    "sixth": "six",
    "seventh": "seven",
    "eighth": "eight",
    "ninth": "nine",
    "tenth": "ten",
    "eleventh": "eleven",
    "twelfth": "twelve",
    "thirteenth": "thirteen",
    "fourteenth": "fourteen",
    "fifteenth": "fifteen",
    "sixteenth": "sixteen",
    "seventeenth": "seventeen",
    "eighteenth": "eighteen",
    "nineteenth": "nineteen",
    "twentieth": "twenty",
    "thirtieth": "thirty",
    "fortieth": "forty",
    "fiftieth": "fifty",
    "sixtieth": "sixty",
    "seventieth": "seventy",
    "eightieth": "eighty",
    "ninetieth": "ninety",
    "hundredth": "hundred",
    **{f"{scale}th": scale for scale in _ENGLISH_SCALES},
}
_ENGLISH_NUMBER_TOKENS = tuple(
    sorted(
        _ENGLISH_SMALL_CARDINALS
        | _ENGLISH_TENS
        | _ENGLISH_SCALES.keys()
        | _ENGLISH_ORDINAL_TO_CARDINAL.keys()
        | {"hundred", "and"},
        key=len,
        reverse=True,
    )
)
_ROMAN_NUMERAL = re.compile(
    r"M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})"
)


@dataclass
class ValidationReport:
    accepted: list[SemanticCandidate] = field(default_factory=list)
    rejected: list[SemanticCandidate] = field(default_factory=list)
    rejection_counts: dict[str, int] = field(default_factory=dict)
    needs_fallback: bool = False


class SemanticCandidateValidator:
    """Apply the shared, model-independent semantic candidate contract."""

    def validate(
        self,
        request: SemanticDivergenceRequest,
        candidates: list[SemanticCandidate],
    ) -> ValidationReport:
        counts: Counter[str] = Counter()
        rejected: list[SemanticCandidate] = []
        valid: list[tuple[int, SemanticCandidate]] = []

        for index, candidate in enumerate(candidates):
            reason = self._rejection_reason(request, candidate)
            if reason is None:
                valid.append((index, candidate))
            else:
                counts[reason] += 1
                if isinstance(candidate, SemanticCandidate):
                    rejected.append(candidate)

        accepted, duplicates = self._deduplicate(valid)
        rejected.extend(duplicates)
        counts["duplicate"] += len(duplicates)
        if not duplicates:
            del counts["duplicate"]

        if len(accepted) > request.candidate_count:
            overflow = accepted[request.candidate_count :]
            rejected.extend(overflow)
            counts["candidate_limit"] += len(overflow)
            accepted = accepted[: request.candidate_count]

        needs_fallback = self._apply_collection_gate(request, accepted, counts)
        return ValidationReport(
            accepted=accepted,
            rejected=rejected,
            rejection_counts=dict(counts),
            needs_fallback=needs_fallback,
        )

    def _rejection_reason(
        self, request: SemanticDivergenceRequest, candidate: object
    ) -> str | None:
        # The order is intentional: counts are an audit trail, not a scorecard.
        if not self._has_schema(candidate):
            return "schema"
        assert isinstance(candidate, SemanticCandidate)
        if self._is_taxonomy_label(candidate):
            return "taxonomy_label"
        if not 2 <= len(_normalize_chinese_label(candidate.display_label_zh)) <= 8:
            return "display_length"
        if self._is_inherited_duplicate(request, candidate):
            return "inherited_duplicate"
        if not self._target_exists(request, candidate):
            return "target_not_found"
        if not self._matches_scope_and_operation(request, candidate):
            return "scope_or_operation"
        thresholds = request.params.thresholds
        if candidate.scores.identity < thresholds["identity"]:
            return "identity_below_threshold"
        if candidate.scores.scope < thresholds["scope"]:
            return "scope_below_threshold"
        if candidate.scores.relevance < thresholds["relevance"]:
            return "relevance_below_threshold"
        if candidate.scores.specificity <= 0:
            return "specificity_zero"
        if not self._provenance_is_consistent(candidate):
            return "provenance_inconsistent"
        return None

    @staticmethod
    def _has_schema(candidate: object) -> bool:
        if not isinstance(candidate, SemanticCandidate):
            return False
        fields = (
            candidate.candidate_id,
            candidate.display_label_zh,
            candidate.label_en,
            candidate.target_ref.asset_id,
            candidate.target_ref.type,
            candidate.operation,
            candidate.semantic_anchor,
            candidate.prompt_phrase,
            candidate.attribute_delta.attribute,
            candidate.attribute_delta.change,
            candidate.provenance.generator,
            candidate.provenance.mode,
        )
        return all(isinstance(value, str) and value.strip() for value in fields)

    @staticmethod
    def _is_taxonomy_label(candidate: SemanticCandidate) -> bool:
        return any(
            _normalize_taxonomy_label(label) in _TAXONOMY_LABELS
            or _is_generic_stem_label(label)
            for label in (candidate.display_label_zh, candidate.label_en)
        )

    @staticmethod
    def _is_inherited_duplicate(
        request: SemanticDivergenceRequest, candidate: SemanticCandidate
    ) -> bool:
        inherited = {_normalize_label(keyword) for keyword in request.inherited_keywords if keyword.strip()}
        return bool(inherited & {_normalize_label(candidate.display_label_zh), _normalize_label(candidate.label_en)})

    @staticmethod
    def _target_exists(request: SemanticDivergenceRequest, candidate: SemanticCandidate) -> bool:
        target = candidate.target_ref
        if request.scope.strip().lower() == "material_region":
            authoritative_region = (
                request.semantic_target.mask_ref or request.semantic_target.part_id
            )
            return (
                target.asset_id == request.asset_id
                and target.type == "material_region"
                and bool(authoritative_region)
                and target.id == authoritative_region
            )
        return (
            target.asset_id == request.asset_id
            and target.type in {"part", "whole"}
            and (target.type != "part" or bool(target.id and target.id.strip()))
        )

    @staticmethod
    def _matches_scope_and_operation(
        request: SemanticDivergenceRequest, candidate: SemanticCandidate
    ) -> bool:
        if not candidate.operation.strip():
            return False
        part_scope = request.scope.strip().lower() == "part"
        target = candidate.target_ref
        if part_scope:
            return target.type == "part" and target.id == request.semantic_target.part_id
        if request.scope.strip().lower() == "material_region":
            authoritative_region = (
                request.semantic_target.mask_ref or request.semantic_target.part_id
            )
            return target.type == "material_region" and target.id == authoritative_region
        return target.type == "whole" and target.id is None

    @staticmethod
    def _provenance_is_consistent(candidate: SemanticCandidate) -> bool:
        provenance = candidate.provenance
        source_count = sum(
            len(source) for source in (provenance.wikidata, provenance.getty_aat, provenance.asknature)
        )
        if provenance.mode == "model_only":
            return source_count == 0
        return provenance.mode == "knowledge_augmented" and source_count > 0

    def _deduplicate(
        self, candidates: Iterable[tuple[int, SemanticCandidate]]
    ) -> tuple[list[SemanticCandidate], list[SemanticCandidate]]:
        ordered = sorted(
            candidates,
            key=lambda item: (
                -self._quality(item[1])[0],
                -self._quality(item[1])[1],
                item[0],
            ),
        )
        labels: set[str] = set()
        semantic_keys: set[tuple[str, str, str, str]] = set()
        accepted: list[SemanticCandidate] = []
        rejected: list[SemanticCandidate] = []
        for _, candidate in ordered:
            candidate_labels = {
                f"zh:{_normalize_label(candidate.display_label_zh)}",
                f"en:{_normalize_label(candidate.label_en)}",
            }
            semantic_key = (
                candidate.target_ref.id or "",
                candidate.operation.strip().casefold(),
                candidate.attribute_delta.attribute.strip().casefold(),
                candidate.attribute_delta.change.strip().casefold(),
            )
            if labels & candidate_labels or semantic_key in semantic_keys:
                rejected.append(candidate)
                continue
            accepted.append(candidate)
            labels.update(candidate_labels)
            semantic_keys.add(semantic_key)
        return accepted, rejected

    @staticmethod
    def _quality(candidate: SemanticCandidate) -> tuple[float, int]:
        scores = candidate.scores
        score = scores.identity + scores.scope + scores.relevance + scores.specificity + scores.novelty
        provenance = candidate.provenance
        source_count = sum(
            len(source) for source in (provenance.wikidata, provenance.getty_aat, provenance.asknature)
        )
        return score, source_count

    def _apply_collection_gate(
        self,
        request: SemanticDivergenceRequest,
        candidates: list[SemanticCandidate],
        counts: Counter[str],
    ) -> bool:
        needs_fallback = False
        if request.params.per_group_count is not None:
            required = request.params.per_group_count
            groups = ("shape", "connection", "surface", "semantic_transfer")
            group_counts = Counter(candidate.group for candidate in candidates)
            for group in groups:
                missing_group = required - group_counts[group]
                if missing_group > 0:
                    counts[f"minimum_{group}"] += missing_group
                    needs_fallback = True
            return needs_fallback

        missing = 9 - len(candidates)
        if missing > 0:
            counts["minimum_candidates"] += missing
            needs_fallback = True

        relevant_groups = self._relevant_groups(request.user_semantic_intent)
        group_count = len({candidate.group for candidate in candidates} & relevant_groups)
        if group_count < 2:
            counts["group_coverage"] += 2 - group_count
            needs_fallback = True

        if request.temperature >= 0.7:
            transfers = sum(candidate.group == "semantic_transfer" for candidate in candidates)
            if transfers < 2:
                counts["minimum_semantic_transfer"] += 2 - transfers
                needs_fallback = True
        return needs_fallback

    @staticmethod
    def _relevant_groups(intent: str) -> set[str]:
        text = intent.casefold()
        matches: set[str] = set()
        if any(token in text for token in ("shape", "form", "contour", "silhouette", "形状", "造型", "轮廓")):
            matches.add("shape")
        if any(token in text for token in ("connect", "joint", "attach", "连接", "关节")):
            matches.add("connection")
        if any(
            token in text
            for token in ("surface", "material", "texture", "color", "finish", "表面", "材质", "纹理", "颜色")
        ):
            matches.add("surface")
        if not matches:
            return {"shape", "connection", "surface", "semantic_transfer"}
        return matches | {"semantic_transfer"}


def _is_generic_stem_label(value: str) -> bool:
    normalized = _normalize_taxonomy_label(value)
    for stem in _GENERIC_LABEL_STEMS:
        if normalized == stem:
            return True
        if normalized.startswith(stem) and _is_identifier_suffix(value, normalized[len(stem) :]):
            return True
    return False


def _is_identifier_suffix(value: str, suffix: str) -> bool:
    if all(unicodedata.category(character).startswith("N") for character in suffix):
        return True
    if all(character in _CHINESE_NUMERAL_CHARACTERS for character in suffix):
        return True
    if len(suffix) == 1 and suffix.isascii() and suffix.isalpha():
        return True
    if _is_english_number_expression(suffix):
        return True

    cased_value = "".join(
        character
        for character in value.strip()
        if not character.isspace() and not unicodedata.category(character).startswith("P")
    )
    cased_suffix = cased_value[-len(suffix) :]
    letters = [
        character for character in cased_suffix if character.isascii() and character.isalpha()
    ]
    numbers = [
        character
        for character in cased_suffix
        if unicodedata.category(character).startswith("N")
    ]
    if len(letters) + len(numbers) == len(cased_suffix):
        if letters and numbers and (len(letters) <= 2 or all(letter.isupper() for letter in letters)):
            return True
        if not numbers and 1 < len(letters) <= 3 and all(letter.isupper() for letter in letters):
            return True
    return (
        cased_suffix.casefold() == suffix
        and cased_suffix.isascii()
        and cased_suffix.isupper()
        and _ROMAN_NUMERAL.fullmatch(cased_suffix) is not None
    )


def _is_english_number_expression(value: str) -> bool:
    tokens: list[str] = []
    offset = 0
    while offset < len(value):
        token = next(
            (token for token in _ENGLISH_NUMBER_TOKENS if value.startswith(token, offset)),
            None,
        )
        if token is None:
            return False
        tokens.append(token)
        offset += len(token)

    if not tokens or tokens[0] == "and" or tokens[-1] == "and":
        return False
    for index, token in enumerate(tokens):
        if token == "and" and tokens[index - 1] not in {"hundred", *_ENGLISH_SCALES}:
            return False

    ordinal_positions = [
        index for index, token in enumerate(tokens) if token in _ENGLISH_ORDINAL_TO_CARDINAL
    ]
    if ordinal_positions and ordinal_positions != [len(tokens) - 1]:
        return False
    if ordinal_positions:
        tokens[-1] = _ENGLISH_ORDINAL_TO_CARDINAL[tokens[-1]]
    cardinal_tokens = [token for token in tokens if token != "and"]
    return _is_english_cardinal(cardinal_tokens)


def _is_english_cardinal(tokens: list[str]) -> bool:
    if len(tokens) == 1:
        return tokens[0] in (
            _ENGLISH_SMALL_CARDINALS | _ENGLISH_TENS | _ENGLISH_SCALES.keys() | {"hundred"}
        )

    last_scale = float("inf")
    chunk: list[str] = []
    for token in tokens:
        if token not in _ENGLISH_SCALES:
            chunk.append(token)
            continue
        scale = _ENGLISH_SCALES[token]
        if not chunk or scale >= last_scale or not _is_english_under_thousand(chunk):
            return False
        chunk = []
        last_scale = scale
    return not chunk or _is_english_under_thousand(chunk)


def _is_english_under_thousand(tokens: list[str]) -> bool:
    if "hundred" not in tokens:
        return _is_english_under_hundred(tokens)
    if tokens.count("hundred") != 1 or len(tokens) < 2:
        return False
    hundred_index = tokens.index("hundred")
    if hundred_index != 1 or tokens[0] not in _ENGLISH_UNITS:
        return False
    remainder = tokens[2:]
    return not remainder or _is_english_under_hundred(remainder)


def _is_english_under_hundred(tokens: list[str]) -> bool:
    return (
        len(tokens) == 1
        and tokens[0] in (_ENGLISH_SMALL_CARDINALS | _ENGLISH_TENS)
        or len(tokens) == 2
        and tokens[0] in _ENGLISH_TENS
        and tokens[1] in _ENGLISH_UNITS
    )


__all__ = ["SemanticCandidateValidator", "ValidationReport"]
