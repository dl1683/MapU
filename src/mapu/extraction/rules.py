"""Rule-based extractors: dates, cross-references, defined terms, amendments."""

from __future__ import annotations

import contextlib
import re
from datetime import datetime

import dateutil.parser as dateutil_parser  # type: ignore[import-untyped]

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
    r"\s+(\d+(?:\.\d+)*(?:\([a-z]\))?)",
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


class AmendmentExtractor:
    """Extracts amendment/supersession signals and frames."""

    @property
    def name(self) -> str:
        return "rule_amendment"

    async def extract(self, ctx: ExtractionContext) -> ExtractorOutput:
        signals: list[ExtractionSignal] = []
        frames: list[PropositionFrameCandidate] = []

        all_refs = list(_CROSS_REF_PATTERN.finditer(ctx.text))

        for pattern in _AMENDMENT_PATTERNS:
            for match in pattern.finditer(ctx.text):
                ref_match = _nearest_preceding_ref(all_refs, match.start())
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


def _nearest_preceding_ref(
    refs: list[re.Match[str]], position: int
) -> re.Match[str] | None:
    result: re.Match[str] | None = None
    for ref in refs:
        if ref.start() >= position:
            break
        result = ref
    return result


def _find_sentence_end(text: str, start: int) -> int:
    """Find the end of the sentence containing the given position."""
    for i in range(start, len(text)):
        if text[i] in ".!?\n":
            return i + 1
    return len(text)
