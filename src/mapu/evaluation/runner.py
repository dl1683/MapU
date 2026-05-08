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

            extraction_result = await self._run_extraction(
                case, corpus_id, situation.id,
            )
            case_result.phases.append(extraction_result)

            if case.expected_truth:
                truth_result = await self._run_truth(case, corpus_id, situation.id)
                case_result.phases.append(truth_result)

            if case.query_question:
                query_result = await self._run_query(
                    case, corpus_id, situation.id,
                )
                case_result.phases.append(query_result)

            case_result.metrics = _compute_case_metrics(case_result.phases)

        except Exception as exc:
            case_result.errors.append(f"{type(exc).__name__}: {exc}")

        return case_result

    async def _run_extraction(
        self,
        case: BenchmarkCase,
        corpus_id: uuid.UUID,
        situation_id: uuid.UUID,
    ) -> PhaseResult:
        start = time.monotonic()
        phase = PhaseResult(phase=EvalPhase.EXTRACTION, success=False)
        try:
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

            phase.details = {
                "document_id": str(ingest_result.document_id),
                "spans": ingest_result.span_count,
                "chunks": ingest_result.chunk_count,
                "embeddings": ingest_result.embedding_count,
                "propositions_extracted": ingest_result.propositions_extracted,
                "extraction_errors": ingest_result.extraction_errors,
                "extracted_entities": extracted_entities,
                "extracted_propositions": extracted_propositions,
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

            phase.success = True

        except Exception as exc:
            phase.errors.append(f"{type(exc).__name__}: {exc}")

        phase.duration_ms = (time.monotonic() - start) * 1000
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
        for (att_id,) in rows.all():
            self._session.add(AttestationSituation(
                attestation_id=att_id,
                situation_id=situation_id,
                corpus_id=corpus_id,
                assignment_confidence=1.0,
                assignment_basis="benchmark_default",
            ))
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
        start = time.monotonic()
        phase = PhaseResult(phase=EvalPhase.TRUTH, success=False)
        try:
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
            phase.details = {
                "truth_accuracy": accuracy,
                "truth_details": truth_details,
            }
            phase.success = True

        except Exception as exc:
            phase.errors.append(f"{type(exc).__name__}: {exc}")

        phase.duration_ms = (time.monotonic() - start) * 1000
        return phase

    async def _run_query(
        self,
        case: BenchmarkCase,
        corpus_id: uuid.UUID,
        situation_id: uuid.UUID,
    ) -> PhaseResult:
        start = time.monotonic()
        phase = PhaseResult(phase=EvalPhase.QUERY, success=False)
        try:
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
            phase.details = {}

            if case.expected_query_hits:
                expected_texts = [h.proposition_text for h in case.expected_query_hits]
                prf1 = fuzzy_precision_recall_f1(hit_texts, expected_texts, threshold=0.5)
                phase.details["query_precision"] = prf1.precision
                phase.details["query_recall"] = prf1.recall
                phase.details["query_f1"] = prf1.f1
                phase.details["hits_returned"] = len(hit_texts)
                phase.details["expected_hits"] = len(expected_texts)

                rank_violations = 0
                for expected_hit in case.expected_query_hits:
                    if expected_hit.min_rank is not None:
                        found_rank = _find_fuzzy_rank(
                            hit_texts, expected_hit.proposition_text, threshold=0.5,
                        )
                        if found_rank is not None and found_rank > expected_hit.min_rank:
                            rank_violations += 1
                if case.expected_query_hits:
                    phase.details["rank_violation_rate"] = (
                        rank_violations / len(case.expected_query_hits)
                    )

            phase.details["synthesis"] = query_result.synthesis or ""
            phase.details["epistemic_status"] = query_result.epistemic_status.value
            phase.success = True

        except Exception as exc:
            phase.errors.append(f"{type(exc).__name__}: {exc}")

        phase.duration_ms = (time.monotonic() - start) * 1000
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
    all_keys: set[str] = set()
    for r in results:
        all_keys.update(r.metrics.keys())

    aggregated: dict[str, float] = {}
    for key in sorted(all_keys):
        values = [r.metrics[key] for r in results if key in r.metrics]
        if values:
            aggregated[f"mean_{key}"] = sum(values) / len(values)
            aggregated[f"min_{key}"] = min(values)
            aggregated[f"max_{key}"] = max(values)

    aggregated["total_cases"] = float(len(results))
    aggregated["cases_with_errors"] = float(sum(1 for r in results if r.errors))
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
