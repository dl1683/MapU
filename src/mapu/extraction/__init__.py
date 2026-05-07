"""Extraction pipeline: spans → propositions via rule-based and ML extractors."""

from __future__ import annotations

from mapu.extraction.rules import (
    AmendmentExtractor,
    CrossReferenceExtractor,
    DateExtractor,
    DefinedTermExtractor,
)
from mapu.extraction.types import Extractor


def get_default_extractors() -> list[Extractor]:
    """Return the standard set of rule-based extractors."""
    return [
        DateExtractor(),
        CrossReferenceExtractor(),
        DefinedTermExtractor(),
        AmendmentExtractor(),
    ]
