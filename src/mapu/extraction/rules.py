"""Rule-based extractors: dates, cross-references, definitions, relations, amendments."""

from __future__ import annotations

import contextlib
import re
from datetime import datetime

import dateutil.parser as dateutil_parser

from mapu.extraction.types import (
    EntityMention,
    ExtractionContext,
    ExtractionSignal,
    ExtractorOutput,
    PropositionFrameCandidate,
)
from mapu.types import AttestationStrength, FrameType, Stance

_DATE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+\d{1,2},?\s+\d{4}\b"
    ),
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(
        r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+\d{4}\b"
    ),
)

_CROSS_REF_PATTERN = re.compile(
    r"(?:Section|Clause|Article|Paragraph|Schedule|Exhibit|Appendix)"
    r"\s+([A-Z](?:-\d+)?\b|\d+(?:\.\d+)*(?:\([a-z]\))?)",
    re.IGNORECASE,
)

_DEFINED_TERM_PATTERN = re.compile(
    r'"([A-Z][^"]{1,80})"\s+(?:means?|shall\s+mean|is\s+defined\s+as|refers?\s+to)'
)

_AMENDMENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?:is\s+hereby\s+(?:amended|deleted|restated|replaced))",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:amended\s+and\s+restated\s+in\s+its\s+entirety)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:shall\s+be\s+(?:amended|deleted|replaced|modified))",
        re.IGNORECASE,
    ),
)

_SENTENCE_RE = re.compile(r"[^.!?]+(?:[.!?]|$)")
_ENTITY_TOKEN_RE = re.compile(
    r"(?:`[^`]{2,80}`|\"[^\"]{2,80}\"|"
    r"[A-Z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*(?:\s+[A-Z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*){0,5}|"
    r"[a-z]+(?:[-_][A-Za-z0-9]+)+|"
    r"[A-Za-z]*[a-z][A-Za-z]*[A-Z][A-Za-z0-9]*|"
    r"[A-Z]{2,})"
)
_RELATION_PATTERNS: tuple[tuple[re.Pattern[str], str, FrameType], ...] = (
    (
        re.compile(
            rf"(?P<subject>{_ENTITY_TOKEN_RE.pattern})\s+"
            r"(?i:(?:is|are|was|were)\s+owned\s+by)\s+"
            rf"(?P<object>{_ENTITY_TOKEN_RE.pattern})",
        ),
        "owned_by",
        FrameType.RELATIONSHIP,
    ),
    (
        re.compile(
            rf"(?P<subject>{_ENTITY_TOKEN_RE.pattern})\s+"
            r"(?i:(?:uses?|using|depends\s+on|stores?|persists?|exposes?|supports?|"
            r"creates?|returns?|includes?|logs?|ingests?|queries|answers?|requires?))\s+"
            r"(?P<object>[^.;]{2,180})",
        ),
        "",
        FrameType.RELATIONSHIP,
    ),
    (
        re.compile(
            rf"(?P<subject>{_ENTITY_TOKEN_RE.pattern})\s+"
            r"(?i:(?:is|are|was|were)\s+(?:a|an|the)?\s*)"
            r"(?P<object>[^.;]{2,180})",
        ),
        "is",
        FrameType.CLASSIFICATION,
    ),
    (
        re.compile(
            rf"(?P<subject>{_ENTITY_TOKEN_RE.pattern})\s+"
            r"(?i:(?:should|must|can)\s+sit\s+in\s+front\s+of)\s+"
            r"(?P<object>[^.;]{2,180})",
        ),
        "sits_in_front_of",
        FrameType.RELATIONSHIP,
    ),
)

_RELATION_VERB_RE = re.compile(
    r"\b(is|are|was|were|uses?|using|depends\s+on|stores?|persists?|exposes?|"
    r"supports?|creates?|returns?|includes?|logs?|ingests?|queries|answers?|"
    r"requires?|should\s+sit\s+in\s+front\s+of|must\s+sit\s+in\s+front\s+of|"
    r"can\s+sit\s+in\s+front\s+of)\b",
    re.IGNORECASE,
)
_OBJECT_CLAUSE_BOUNDARY_RE = re.compile(
    r"\s+(?:before|after|when|while|unless|because|although|where|which|that)\s+",
    re.IGNORECASE,
)
_RELATION_ENTITY_SKIP = frozenset({
    "The",
    "A",
    "An",
    "This",
    "That",
    "These",
    "Those",
    "It",
    "They",
    "We",
    "You",
})


class DateExtractor:
    """Extracts date signals from text. Does not create propositions alone."""

    @property
    def name(self) -> str:
        return "rule_date"

    async def extract(self, ctx: ExtractionContext) -> ExtractorOutput:
        signals: list[ExtractionSignal] = []
        for pattern in _DATE_PATTERNS:
            for match in pattern.finditer(ctx.text):
                parsed_date: datetime | None = None
                with contextlib.suppress(ValueError, OverflowError):
                    parsed_date = dateutil_parser.parse(match.group(), fuzzy=False)
                signals.append(ExtractionSignal(
                    signal_type="date",
                    data={
                        "raw_text": match.group(),
                        "parsed_iso": parsed_date.isoformat() if parsed_date else None,
                    },
                    start_char=ctx.start_char + match.start(),
                    end_char=ctx.start_char + match.end(),
                    source=self.name,
                ))
        return ExtractorOutput(signals=tuple(signals))


class CrossReferenceExtractor:
    """Extracts cross-reference signals and optionally relationship propositions."""

    @property
    def name(self) -> str:
        return "rule_cross_reference"

    async def extract(self, ctx: ExtractionContext) -> ExtractorOutput:
        signals: list[ExtractionSignal] = []
        for match in _CROSS_REF_PATTERN.finditer(ctx.text):
            signals.append(ExtractionSignal(
                signal_type="cross_reference",
                data={
                    "reference": match.group(),
                    "section_id": match.group(1),
                },
                start_char=ctx.start_char + match.start(),
                end_char=ctx.start_char + match.end(),
                source=self.name,
            ))
        return ExtractorOutput(signals=tuple(signals))


class DefinedTermExtractor:
    """Extracts defined term propositions from quoted definitions."""

    @property
    def name(self) -> str:
        return "rule_defined_term"

    async def extract(self, ctx: ExtractionContext) -> ExtractorOutput:
        frames: list[PropositionFrameCandidate] = []
        for match in _DEFINED_TERM_PATTERN.finditer(ctx.text):
            term = match.group(1)
            definition_start = match.end()
            definition_end = _find_sentence_end(ctx.text, definition_start)
            definition_text = ctx.text[definition_start:definition_end].strip()

            subject = EntityMention(
                text=term,
                kind="defined_term",
                start_char=ctx.start_char + match.start(1),
                end_char=ctx.start_char + match.end(1),
                confidence=1.0,
                source=self.name,
            )

            frames.append(PropositionFrameCandidate(
                span_id=ctx.span_id,
                frame_type=FrameType.DEFINITION,
                subject=subject,
                predicate="means",
                object=None,
                value={"definition": definition_text},
                polarity=True,
                modality=None,
                valid_range=None,
                normalized_text=f"{term} means {definition_text}",
                qualifiers={},
                stance=Stance.ASSERTS,
                attestation_strength=AttestationStrength.DIRECT_STATEMENT,
                extraction_method=self.name,
                extraction_confidence=0.95,
            ))
        return ExtractorOutput(frames=tuple(frames))


class LightweightRelationExtractor:
    """Extracts common factual relations without ML or online LLM dependencies."""

    def __init__(self, max_frames_per_span: int = 40) -> None:
        self._max_frames_per_span = max_frames_per_span

    @property
    def name(self) -> str:
        return "rule_lightweight_relation"

    async def extract(self, ctx: ExtractionContext) -> ExtractorOutput:
        frames: list[PropositionFrameCandidate] = []
        seen: set[str] = set()

        for sentence_match in _SENTENCE_RE.finditer(ctx.text):
            sentence = sentence_match.group().strip()
            if not sentence:
                continue
            for pattern, predicate_override, frame_type in _RELATION_PATTERNS:
                for match in pattern.finditer(sentence):
                    if len(frames) >= self._max_frames_per_span:
                        return ExtractorOutput(frames=tuple(frames))
                    subject_text = _clean_relation_entity(match.group("subject"))
                    object_text = _clean_relation_object(match.group("object"))
                    if not subject_text or not object_text:
                        continue
                    if subject_text in _RELATION_ENTITY_SKIP:
                        continue
                    if subject_text.lower() == object_text.lower():
                        continue
                    if predicate_override == "is" and object_text.lower().startswith((
                        "owned by ",
                        "used by ",
                        "created by ",
                        "managed by ",
                    )):
                        continue
                    predicate = predicate_override or _normalize_relation_predicate(
                        match.group(0),
                    )
                    if not predicate:
                        continue
                    normalized = f"{subject_text} {predicate} {object_text}"
                    key = normalized.lower()
                    if key in seen:
                        continue
                    seen.add(key)

                    sentence_start = ctx.start_char + sentence_match.start()
                    subject_start = sentence_start + match.start("subject")
                    object_start = sentence_start + match.start("object")
                    subject = EntityMention(
                        text=subject_text,
                        kind=_guess_relation_entity_kind(subject_text),
                        start_char=subject_start,
                        end_char=subject_start + len(match.group("subject")),
                        confidence=0.9,
                        source=self.name,
                    )
                    obj = EntityMention(
                        text=object_text,
                        kind=_guess_relation_entity_kind(object_text),
                        start_char=object_start,
                        end_char=object_start + len(match.group("object")),
                        confidence=0.85,
                        source=self.name,
                    )
                    frames.append(PropositionFrameCandidate(
                        span_id=ctx.span_id,
                        frame_type=frame_type,
                        subject=subject,
                        predicate=predicate,
                        object=obj,
                        value=None,
                        polarity=True,
                        modality=None,
                        valid_range=None,
                        normalized_text=normalized,
                        qualifiers={},
                        stance=Stance.ASSERTS,
                        attestation_strength=AttestationStrength.DIRECT_STATEMENT,
                        extraction_method=self.name,
                        extraction_confidence=0.88,
                    ))
        return ExtractorOutput(frames=tuple(frames))


class AmendmentExtractor:
    """Extracts amendment/supersession signals and frames."""

    @property
    def name(self) -> str:
        return "rule_amendment"

    async def extract(self, ctx: ExtractionContext) -> ExtractorOutput:
        signals: list[ExtractionSignal] = []
        frames: list[PropositionFrameCandidate] = []

        raw_matches: list[re.Match[str]] = []
        for pattern in _AMENDMENT_PATTERNS:
            raw_matches.extend(pattern.finditer(ctx.text))

        if not raw_matches:
            return ExtractorOutput()

        raw_matches.sort(key=lambda m: m.end() - m.start(), reverse=True)
        covered: list[tuple[int, int]] = []
        deduped: list[re.Match[str]] = []
        for m in raw_matches:
            if any(m.start() < ce and cs < m.end() for cs, ce in covered):
                continue
            covered.append((m.start(), m.end()))
            deduped.append(m)
        deduped.sort(key=lambda m: m.start())

        all_refs = list(_CROSS_REF_PATTERN.finditer(ctx.text))

        for match in deduped:
            ref_match = _nearest_preceding_ref(
                all_refs, match.start(), ctx.text,
            )
            target_ref = ref_match.group() if ref_match else None

            signals.append(ExtractionSignal(
                signal_type="amendment",
                data={
                    "action": match.group().strip().lower(),
                    "target_reference": target_ref,
                },
                start_char=ctx.start_char + match.start(),
                end_char=ctx.start_char + match.end(),
                source=self.name,
            ))

            if target_ref:
                ref_start = ref_match.start() if ref_match else match.start()
                ref_end = ref_match.end() if ref_match else match.end()
                subject = EntityMention(
                    text=target_ref,
                    kind="document_section",
                    start_char=ctx.start_char + ref_start,
                    end_char=ctx.start_char + ref_end,
                    confidence=0.9,
                    source=self.name,
                )
                frames.append(PropositionFrameCandidate(
                    span_id=ctx.span_id,
                    frame_type=FrameType.STATUS,
                    subject=subject,
                    predicate="amended",
                    object=None,
                    value={"action": match.group().strip().lower()},
                    polarity=True,
                    modality=None,
                    valid_range=None,
                    normalized_text=f"{target_ref} {match.group().strip().lower()}",
                    qualifiers={},
                    stance=Stance.ASSERTS,
                    attestation_strength=AttestationStrength.DIRECT_STATEMENT,
                    extraction_method=self.name,
                    extraction_confidence=0.9,
                ))

        return ExtractorOutput(frames=tuple(frames), signals=tuple(signals))


_SUBORDINATE_PREFIX = re.compile(
    r"(?:(?:as\s+)?referenced\s+in|pursuant\s+to|provided\s+in|described\s+in|set\s+forth\s+in|defined\s+in)\s+$",
    re.IGNORECASE,
)


def _nearest_preceding_ref(
    refs: list[re.Match[str]],
    position: int,
    text: str,
) -> re.Match[str] | None:
    sentence_start = _find_sentence_start(text, position)
    for ref in reversed(refs):
        if ref.start() >= position:
            continue
        if ref.start() < sentence_start:
            break
        prefix = text[max(sentence_start, ref.start() - 30):ref.start()]
        if _SUBORDINATE_PREFIX.search(prefix):
            continue
        return ref
    return None


def _is_decimal_period(text: str, i: int) -> bool:
    return (
        i > 0
        and text[i - 1].isdigit()
        and i + 1 < len(text)
        and text[i + 1].isdigit()
    )


def _find_sentence_start(text: str, position: int) -> int:
    for i in range(position - 1, -1, -1):
        if text[i] in "!?\n":
            return i + 1
        if text[i] == "." and not _is_decimal_period(text, i):
            return i + 1
    return 0


def _find_sentence_end(text: str, start: int) -> int:
    for i in range(start, len(text)):
        if text[i] in "!?\n":
            return i + 1
        if text[i] == "." and not _is_decimal_period(text, i):
            return i + 1
    return len(text)


def _clean_relation_entity(raw: str) -> str:
    text = raw.strip().strip("`\"'“”‘’()[]{}")
    text = re.sub(r"^\s*(?:the|a|an)\s+", "", text, flags=re.IGNORECASE)
    return " ".join(text.split()).strip(" ,:;")


def _clean_relation_object(raw: str) -> str:
    text = raw.strip().strip("`\"'“”‘’()[]{}")
    text = _OBJECT_CLAUSE_BOUNDARY_RE.split(text, maxsplit=1)[0]
    text = re.split(r"\s+(?:and|or)\s+(?:then|also)\s+", text, maxsplit=1)[0]
    text = re.sub(r"^\s*(?:the|a|an)\s+", "", text, flags=re.IGNORECASE)
    words = text.split()
    if len(words) > 12:
        text = " ".join(words[:12])
    return " ".join(text.split()).strip(" ,:;")


def _normalize_relation_predicate(text: str) -> str:
    match = _RELATION_VERB_RE.search(text)
    if not match:
        return ""
    verb = " ".join(match.group(1).lower().split())
    mapping = {
        "use": "uses",
        "using": "uses",
        "uses": "uses",
        "depends on": "depends_on",
        "store": "stores",
        "stores": "stores",
        "persist": "persists",
        "persists": "persists",
        "expose": "exposes",
        "exposes": "exposes",
        "support": "supports",
        "supports": "supports",
        "create": "creates",
        "creates": "creates",
        "return": "returns",
        "returns": "returns",
        "include": "includes",
        "includes": "includes",
        "log": "logs",
        "logs": "logs",
        "ingest": "ingests",
        "ingests": "ingests",
        "query": "queries",
        "queries": "queries",
        "answer": "answers",
        "answers": "answers",
        "require": "requires",
        "requires": "requires",
        "is": "is",
        "are": "is",
        "was": "is",
        "were": "is",
        "should sit in front of": "sits_in_front_of",
        "must sit in front of": "sits_in_front_of",
        "can sit in front of": "sits_in_front_of",
    }
    return mapping.get(verb, verb.replace(" ", "_"))


def _guess_relation_entity_kind(text: str) -> str:
    lowered = text.lower()
    words = text.split()
    if words and words[0].lower() in {"project", "system", "service", "api", "cli", "mcp"}:
        return "system"
    if any(token in lowered for token in ("api", "cli", "mcp", "server", "database")):
        return "system"
    if len(words) == 2 and all(part[:1].isupper() for part in words):
        return "person"
    if re.fullmatch(r"[A-Z]{2,}", text) or any(c.isupper() for c in text[1:]):
        return "system"
    return "entity"
