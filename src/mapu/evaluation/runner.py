"""Benchmark runner: drives cases through the ingest → extract → truth → query pipeline."""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from mapu.evaluation.metrics import (
    fuzzy_match_score,
    fuzzy_precision_recall_f1,
    truth_accuracy,
)
from mapu.evaluation.types import (
    BenchmarkCase,
    CaseResult,
    EvalPhase,
    PhaseResult,
    SuiteResult,
)


class BenchmarkRunner:
    """Runs benchmark cases through the MapU pipeline and collects metrics."""

    def __init__(
        self,
        session: AsyncSession,
        embedding_provider: object | None = None,
        extractors: list[object] | None = None,
    ) -> None:
        self._session = session
        self._embedding_provider = embedding_provider
        self._extractors = extractors

    async def run_suite(
        self,
        cases: Sequence[BenchmarkCase],
        suite_name: str = "default",
    ) -> SuiteResult:
        start = time.monotonic()
        result = SuiteResult(suite_name=suite_name)
        result.git_commit = _get_git_commit()

        for case in cases:
            case_result = await self.run_case(case)
            result.case_results.append(case_result)

        result.duration_ms = (time.monotonic() - start) * 1000
        result.aggregate_metrics = _aggregate_metrics(result.case_results)
        return result

    async def run_case(self, case: BenchmarkCase) -> CaseResult:
        corpus_id = uuid.uuid4()
        case_result = CaseResult(
            case_id=case.id,
            domain=case.domain.value,
            corpus_id=corpus_id,
        )

        try:
            async with self._session.begin_nested():
                from mapu.models.corpus import Corpus
                corpus = Corpus(id=corpus_id, name=f"bench_{case.id}", description=case.description)
                self._session.add(corpus)
                await self._session.flush()

                from mapu.models.context import Situation
                situation = Situation(
                    corpus_id=corpus_id,
                    kind="benchmark",
                    name=f"bench_{case.id}_default",
                )
                self._session.add(situation)
                await self._session.flush()
        except Exception as exc:
            case_result.errors.append(f"{type(exc).__name__}: {exc}")
            return case_result

        situation_id = situation.id

        extraction_result = await self._run_phase(
            self._run_extraction, EvalPhase.EXTRACTION,
            case, corpus_id, situation_id,
        )
        case_result.phases.append(extraction_result)

        if case.expected_truth and extraction_result.success:
            truth_result = await self._run_phase(
                self._run_truth, EvalPhase.TRUTH,
                case, corpus_id, situation_id,
            )
            case_result.phases.append(truth_result)

        if case.query_question and extraction_result.success:
            query_result = await self._run_phase(
                self._run_query, EvalPhase.QUERY,
                case, corpus_id, situation_id,
            )
            case_result.phases.append(query_result)

        case_result.metrics = _compute_case_metrics(case_result.phases)
        return case_result

    async def _run_phase(
        self,
        phase_fn: object,
        phase: EvalPhase,
        case: BenchmarkCase,
        corpus_id: uuid.UUID,
        situation_id: uuid.UUID,
    ) -> PhaseResult:
        start = time.monotonic()
        try:
            async with self._session.begin_nested():
                result = await phase_fn(case, corpus_id, situation_id)  # type: ignore[operator]
                result.duration_ms = (time.monotonic() - start) * 1000
                return result
        except Exception as exc:
            return PhaseResult(
                phase=phase,
                success=False,
                duration_ms=(time.monotonic() - start) * 1000,
                errors=[f"{type(exc).__name__}: {exc}"],
            )

    async def _run_extraction(
        self,
        case: BenchmarkCase,
        corpus_id: uuid.UUID,
        situation_id: uuid.UUID,
    ) -> PhaseResult:
        from mapu.evidence.chunking import SpanAwareChunker
        from mapu.evidence.ingest import IngestionService
        from mapu.evidence.parsers import ParserRegistry
        from mapu.evidence.types import DocumentBlob

        registry = ParserRegistry.create_default()
        chunker = SpanAwareChunker()

        from mapu.extraction.types import Extractor
        typed_extractors: list[Extractor] | None = None
        if self._extractors is not None:
            typed_extractors = [e for e in self._extractors if isinstance(e, Extractor)]

        svc = IngestionService(
            session=self._session,
            corpus_id=corpus_id,
            parser_registry=registry,
            chunker=chunker,
            embedding_provider=self._embedding_provider,
            extractors=typed_extractors,
        )
        blob = DocumentBlob(
            content=case.source_text.encode("utf-8"),
            mime_type=case.source_mime_type,
            source_uri=f"bench://{case.id}",
            metadata=case.source_metadata,
        )
        ingest_result = await svc.ingest(blob)

        await self._link_attestations_to_situation(corpus_id, situation_id)

        extracted_entities = await self._load_extracted_entities(corpus_id)
        extracted_propositions: list[str] = []
        if ingest_result.propositions_extracted > 0:
            from sqlalchemy import select

            from mapu.models.proposition import Proposition
            stmt = select(Proposition).where(Proposition.corpus_id == corpus_id)
            rows = await self._session.execute(stmt)
            for prop in rows.scalars().all():
                extracted_propositions.append(prop.normalized_text or "")

        phase = PhaseResult(phase=EvalPhase.EXTRACTION, success=True)
        phase.details = {
            "document_id": str(ingest_result.document_id),
            "spans": ingest_result.span_count,
            "chunks": ingest_result.chunk_count,
            "embeddings": ingest_result.embedding_count,
            "propositions_extracted": ingest_result.propositions_extracted,
            "extraction_errors": ingest_result.extraction_errors,
            "entity_count": len(extracted_entities),
            "entity_sample": extracted_entities[:10],
            "proposition_count": len(extracted_propositions),
            "proposition_sample": extracted_propositions[:10],
        }

        if case.expected_propositions:
            expected_texts = [p.normalized_text for p in case.expected_propositions]
            prf1 = fuzzy_precision_recall_f1(
                extracted_propositions, expected_texts, threshold=0.5,
            )
            phase.details["proposition_precision"] = prf1.precision
            phase.details["proposition_recall"] = prf1.recall
            phase.details["proposition_f1"] = prf1.f1

        if case.expected_entities:
            expected_entity_texts = [e.text for e in case.expected_entities]
            entity_prf1 = fuzzy_precision_recall_f1(
                extracted_entities, expected_entity_texts, threshold=0.6,
            )
            phase.details["entity_precision"] = entity_prf1.precision
            phase.details["entity_recall"] = entity_prf1.recall
            phase.details["entity_f1"] = entity_prf1.f1

        return phase

    async def _link_attestations_to_situation(
        self, corpus_id: uuid.UUID, situation_id: uuid.UUID,
    ) -> None:
        from sqlalchemy import select

        from mapu.models.attestation import Attestation, AttestationSituation

        stmt = (
            select(Attestation.id)
            .where(Attestation.corpus_id == corpus_id)
            .where(
                ~Attestation.id.in_(
                    select(AttestationSituation.attestation_id).where(
                        AttestationSituation.corpus_id == corpus_id,
                        AttestationSituation.situation_id == situation_id,
                    )
                )
            )
        )
        rows = await self._session.execute(stmt)
        att_ids = [att_id for (att_id,) in rows.all()]
        if att_ids:
            self._session.add_all([
                AttestationSituation(
                    attestation_id=att_id,
                    situation_id=situation_id,
                    corpus_id=corpus_id,
                    assignment_confidence=1.0,
                    assignment_basis="benchmark_default",
                )
                for att_id in att_ids
            ])
            await self._session.flush()

    async def _load_extracted_entities(self, corpus_id: uuid.UUID) -> list[str]:
        from sqlalchemy import select

        from mapu.models.entity import Handle

        stmt = select(Handle.canonical_name).where(
            Handle.corpus_id == corpus_id,
            Handle.status == "active",
        )
        rows = await self._session.execute(stmt)
        return [name for (name,) in rows.all()]

    async def _run_truth(
        self,
        case: BenchmarkCase,
        corpus_id: uuid.UUID,
        situation_id: uuid.UUID,
    ) -> PhaseResult:
        from sqlalchemy import select

        from mapu.models.proposition import Proposition
        from mapu.truth.policy import TruthPolicyV1
        from mapu.truth.provider import DbTruthEvidenceProvider

        policy = TruthPolicyV1()
        provider = DbTruthEvidenceProvider(self._session, corpus_id)

        stmt = select(Proposition).where(Proposition.corpus_id == corpus_id)
        rows = await self._session.execute(stmt)
        propositions = list(rows.scalars().all())

        predicted_statuses: list[str] = []
        expected_statuses: list[str] = []
        truth_details: list[dict[str, object]] = []

        for expected in case.expected_truth:
            best_match_id: uuid.UUID | None = None
            best_score = 0.0
            for prop in propositions:
                score = fuzzy_match_score(
                    prop.normalized_text or "", expected.proposition_text,
                )
                if score > best_score:
                    best_score = score
                    best_match_id = prop.id

            if best_match_id is not None and best_score >= 0.4:
                truth_result = await policy.compute(
                    best_match_id, situation_id, provider,
                )
                predicted_statuses.append(truth_result.status.value)
                expected_statuses.append(expected.expected_status)
                truth_details.append({
                    "proposition_text": expected.proposition_text,
                    "expected": expected.expected_status,
                    "predicted": truth_result.status.value,
                    "reason": truth_result.reason,
                    "match_score": best_score,
                })
            else:
                predicted_statuses.append("not_found")
                expected_statuses.append(expected.expected_status)
                truth_details.append({
                    "proposition_text": expected.proposition_text,
                    "expected": expected.expected_status,
                    "predicted": "not_found",
                    "reason": "no matching proposition extracted",
                    "match_score": best_score,
                })

        accuracy = truth_accuracy(predicted_statuses, expected_statuses)
        phase = PhaseResult(phase=EvalPhase.TRUTH, success=True)
        phase.details = {
            "truth_accuracy": accuracy,
            "truth_details": truth_details,
        }
        return phase

    async def _run_query(
        self,
        case: BenchmarkCase,
        corpus_id: uuid.UUID,
        situation_id: uuid.UUID,
    ) -> PhaseResult:
        from mapu.query.intent import HeuristicIntentClassifier
        from mapu.query.service import QueryService
        from mapu.query.types import QueryRequest

        classifier = HeuristicIntentClassifier()
        svc = QueryService(
            self._session, classifier,
            embedding_provider=self._embedding_provider,
        )
        request = QueryRequest(
            corpus_id=corpus_id,
            question=case.query_question or "",
            situation_id=situation_id,
        )
        query_result = await svc.query(request)

        hit_texts = [h.normalized_text for h in query_result.hits]
        phase = PhaseResult(phase=EvalPhase.QUERY, success=True)
        phase.details = {}

        if case.expected_query_hits:
            expected_texts = [h.proposition_text for h in case.expected_query_hits]
            prf1 = fuzzy_precision_recall_f1(hit_texts, expected_texts, threshold=0.5)
            phase.details["query_precision"] = prf1.precision
            phase.details["query_recall"] = prf1.recall
            phase.details["query_f1"] = prf1.f1
            phase.details["hits_returned"] = len(hit_texts)
            phase.details["expected_hits"] = len(expected_texts)

            ranked_hits = [
                h for h in case.expected_query_hits if h.min_rank is not None
            ]
            if ranked_hits:
                rank_violations = 0
                for expected_hit in ranked_hits:
                    found_rank = _find_fuzzy_rank(
                        hit_texts, expected_hit.proposition_text, threshold=0.5,
                    )
                    if found_rank is None or found_rank > expected_hit.min_rank:
                        rank_violations += 1
                phase.details["rank_violation_rate"] = (
                    rank_violations / len(ranked_hits)
                )

        phase.details["synthesis"] = query_result.synthesis or ""
        phase.details["epistemic_status"] = query_result.epistemic_status.value
        return phase


def _find_fuzzy_rank(
    hit_texts: list[str], target: str, threshold: float,
) -> int | None:
    for i, text in enumerate(hit_texts):
        if fuzzy_match_score(text, target) >= threshold:
            return i
    return None


def _compute_case_metrics(phases: list[PhaseResult]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for phase in phases:
        prefix = phase.phase.value
        for key, val in phase.details.items():
            if isinstance(val, float):
                metrics[f"{prefix}.{key}"] = val
    return metrics


def _aggregate_metrics(results: list[CaseResult]) -> dict[str, float]:
    accum: dict[str, tuple[float, float, float, int]] = {}  # sum, min, max, count
    error_count = 0
    for r in results:
        if r.errors:
            error_count += 1
        for key, val in r.metrics.items():
            if key in accum:
                s, mn, mx, n = accum[key]
                accum[key] = (s + val, min(mn, val), max(mx, val), n + 1)
            else:
                accum[key] = (val, val, val, 1)

    aggregated: dict[str, float] = {}
    for key in sorted(accum):
        s, mn, mx, n = accum[key]
        aggregated[f"mean_{key}"] = s / n
        aggregated[f"min_{key}"] = mn
        aggregated[f"max_{key}"] = mx

    aggregated["total_cases"] = float(len(results))
    aggregated["cases_with_errors"] = float(error_count)
    return aggregated


def _get_git_commit() -> str:
    import subprocess
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"
