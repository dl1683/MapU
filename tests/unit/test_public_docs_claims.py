from __future__ import annotations

import re
from pathlib import Path


PUBLIC_DOCS = [
    "README.md",
    "PUBLIC_RELEASE_AUDIT.md",
    "GLOBAL_MEMORY_BENCHMARK_STATUS.md",
    "INTEGRATIONS.md",
]


def _read_doc(repo_root: Path, relative_path: str) -> str:
    return (repo_root / relative_path).read_text(encoding="utf-8")


def test_public_docs_do_not_treat_ignored_smoke_logs_as_durable_evidence() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    pattern = re.compile(r"benchmark_smoke_gate_\d{8}_\d{6}")

    offenders = [
        relative_path
        for relative_path in PUBLIC_DOCS
        if pattern.search(_read_doc(repo_root, relative_path))
    ]

    assert offenders == []


def test_public_docs_do_not_hardcode_session_latest_head() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    forbidden = [
        "Latest pushed head checked in this session",
        "Verified before the current pause",
    ]

    offenders = {
        relative_path: phrase
        for relative_path in PUBLIC_DOCS
        for phrase in forbidden
        if phrase in _read_doc(repo_root, relative_path)
    }

    assert offenders == {}
