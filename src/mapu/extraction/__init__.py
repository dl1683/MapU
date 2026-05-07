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
    """Return extractors based on configuration. ML extractors are domain-invariant."""
    from mapu.config import ExtractionSettings

    settings = ExtractionSettings()
    extractors: list[Extractor] = [
        DateExtractor(),
        CrossReferenceExtractor(),
        DefinedTermExtractor(),
        AmendmentExtractor(),
    ]

    if settings.gliner_enabled:
        from mapu.extraction.ml import GLiNERExtractor
        extractors.append(GLiNERExtractor(
            model_name=settings.gliner_model,
            threshold=settings.gliner_threshold,
            calibration_weight=settings.gliner_calibration,
            device=settings.ml_device,
        ))
    if settings.rebel_enabled:
        from mapu.extraction.ml import REBELExtractor
        extractors.append(REBELExtractor(
            model_name=settings.rebel_model,
            calibration_weight=settings.rebel_calibration,
            device=settings.ml_device,
        ))
    if settings.setfit_enabled:
        from mapu.extraction.ml import SetFitExtractor
        extractors.append(SetFitExtractor(
            model_name=settings.setfit_model,
            trained_path=settings.setfit_trained_path or None,
            threshold=settings.setfit_threshold,
            device=settings.ml_device,
        ))

    return extractors
