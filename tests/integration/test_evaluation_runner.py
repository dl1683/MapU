"""Integration tests for the evaluation runner against a real PostgreSQL database."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from mapu.evaluation.cases import LEGAL_CONTRACT_CLAUSE
from mapu.evaluation.runner import BenchmarkRunner
from mapu.evaluation.types import EvalPhase


@pytest.mark.integration
class TestBenchmarkRunnerIntegration:
    async def test_run_single_case_extraction(self, session: AsyncSession) -> None:
        runner = BenchmarkRunner(session=session)
        result = await runner.run_case(LEGAL_CONTRACT_CLAUSE)

        assert result.case_id == "legal_001"
        assert result.domain == "legal"
        assert result.corpus_id is not None

        extraction_phases = [p for p in result.phases if p.phase == EvalPhase.EXTRACTION]
        assert len(extraction_phases) == 1
        phase = extraction_phases[0]
        assert phase.success is True
        assert phase.details["spans"] > 0
        assert phase.details["chunks"] > 0

    async def test_run_suite_multiple_cases(self, session: AsyncSession) -> None:
        from mapu.evaluation.cases import CODE_API_DOC

        runner = BenchmarkRunner(session=session)
        result = await runner.run_suite(
            [LEGAL_CONTRACT_CLAUSE, CODE_API_DOC],
            suite_name="integration_test",
        )

        assert result.suite_name == "integration_test"
        assert len(result.case_results) == 2
        assert result.duration_ms > 0
        assert result.aggregate_metrics.get("total_cases") == 2.0

    async def test_scorecard_output(self, session: AsyncSession, tmp_path: object) -> None:
        from pathlib import Path

        from mapu.evaluation.reporting import write_json_scorecard

        runner = BenchmarkRunner(session=session)
        result = await runner.run_suite(
            [LEGAL_CONTRACT_CLAUSE], suite_name="scorecard_test",
        )

        out_dir = Path(str(tmp_path))
        path = write_json_scorecard(result, out_dir)
        assert path.exists()

        import json
        data = json.loads(path.read_text())
        assert data["suite_name"] == "scorecard_test"
        assert len(data["cases"]) == 1
