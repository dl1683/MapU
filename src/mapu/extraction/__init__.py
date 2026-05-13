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
            model_id=settings.gliner_model,
            threshold=settings.gliner_threshold,
            calibration_factor=settings.gliner_calibration,
            device=settings.ml_device,
        ))
    if settings.llm_enabled:
        from mapu.providers.llms import get_default_llm_provider
        llm_provider = get_default_llm_provider()
        if llm_provider is not None:
            from mapu.extraction.llm import LLMExtractor
            extractors.append(LLMExtractor(
                provider=llm_provider,
                max_tokens=settings.llm_max_tokens,
                temperature=settings.llm_temperature,
                min_confidence=settings.llm_min_confidence,
            ))
    if settings.gliner_relex_enabled:
        from mapu.extraction.ml import GLiNERRelexExtractor
        extractors.append(GLiNERRelexExtractor(
            model_id=settings.gliner_relex_model,
            entity_threshold=settings.gliner_relex_entity_threshold,
            relation_threshold=settings.gliner_relex_relation_threshold,
            calibration_factor=settings.gliner_relex_calibration,
            device=settings.ml_device,
        ))
    if settings.setfit_enabled:
        from mapu.extraction.ml import SetFitExtractor
        extractors.append(SetFitExtractor(
            model_id=settings.setfit_model,
            trained_model_path=settings.setfit_trained_path or None,
            confidence_threshold=settings.setfit_threshold,
            device=settings.ml_device,
        ))

    return extractors
