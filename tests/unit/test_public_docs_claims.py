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


def test_public_docs_do_not_make_unverified_superlative_performance_claims() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    public_claim_docs = [
        *PUBLIC_DOCS,
        "docs/CLI_OPERATOR_GUIDE.md",
        "docs/MEMORY_BENCHMARKS.md",
        "docs/VALIDATION_EVIDENCE_MATRIX.md",
        "ARCHITECTURE.md",
        "CLAIM_EVIDENCE_APPENDIX.md",
    ]
    forbidden = re.compile(
        r"\b(SOTA|state-of-the-art|supremacy|benchmark-supremacy|fantastic)\b",
        flags=re.IGNORECASE,
    )

    offenders = {
        relative_path: sorted(set(forbidden.findall(_read_doc(repo_root, relative_path))))
        for relative_path in public_claim_docs
        if forbidden.search(_read_doc(repo_root, relative_path))
    }

    assert offenders == {}


def test_public_docs_separate_mcp_list_only_from_db_backed_e2e() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    readme = _read_doc(repo_root, "README.md")
    integrations = _read_doc(repo_root, "INTEGRATIONS.md")
    audit = _read_doc(repo_root, "PUBLIC_RELEASE_AUDIT.md")

    assert "-RunMcpE2E" in readme
    assert "-RunMcpE2E" in audit
    assert "--list-only" in integrations
    assert "DB-backed MCP stdio" in audit
    assert "fresh-clone release audit runs the installed MCP stdio smoke in" in audit


def test_readme_links_validation_evidence_matrix() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    readme = _read_doc(repo_root, "README.md")
    matrix = _read_doc(repo_root, "docs/VALIDATION_EVIDENCE_MATRIX.md")

    assert "VALIDATION_EVIDENCE_MATRIX.md" in readme
    assert "tools/cli_e2e_smoke.py" in matrix
    assert "doctor_ok" in matrix
    assert "doctor_required_tools_present" in matrix
    assert "tools/mcp_stdio_smoke.py" in matrix
    assert "tools/continuity_replay_harness.py" in matrix
    assert "--require-response-quality-gate" in readme
    assert "--require-response-quality-gate" in matrix
    assert "answer text, next-step guidance, and evidence signals" in readme
    assert "general-purpose product-quality gate" in matrix
    assert "ingest a handoff note" in matrix
    assert "status" in matrix
    assert "mapu_version" in matrix
    assert "git_sha" in matrix
    assert "tool_count" in matrix
    assert "required_tools_present" in matrix
    assert "missing_required_tools" in matrix
    assert "full `tools` list" in matrix
    assert "required checks" in matrix
    assert "smoke_evidence" in matrix
    assert "command_line" in matrix
    assert "lane_artifact_dir" in matrix
    assert "smoke_only=true" in matrix
    assert "public_performance_evidence=false" in matrix
    assert "prepublish_benchmark_gate.ps1" in matrix
    assert "verify_prepublish_benchmark_evidence.py" in matrix
    assert "verify_benchmark_isolation.py" in matrix
    assert "Benchmark isolation source audit" in matrix


def test_public_docs_describe_benchmark_smoke_freshness_guard() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    readme = _read_doc(repo_root, "README.md")
    matrix = _read_doc(repo_root, "docs/VALIDATION_EVIDENCE_MATRIX.md")

    for doc in (readme, matrix):
        assert "worktree_status_porcelain" in doc
        assert "worktree_dirty_path_count" in doc
        assert "worktree_fingerprint_sha256" in doc
        assert "stale benchmark smoke" in doc

    assert "worktree_fingerprint_errors" in readme
    assert "worktree_fingerprint_errors" in matrix
    assert "Rerun" in matrix
    assert "verify_objective_completion.py` rejects stale" in readme
    assert "current checkout" in matrix


def test_public_docs_include_benchmark_isolation_guard() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    readme = _read_doc(repo_root, "README.md")
    matrix = _read_doc(repo_root, "docs/VALIDATION_EVIDENCE_MATRIX.md")
    audit = _read_doc(repo_root, "PUBLIC_RELEASE_AUDIT.md")

    for doc in (readme, matrix, audit):
        assert "verify_benchmark_isolation.py" in doc

    assert "Benchmark-specific identifiers must stay out of general runtime modules" in readme
    assert "Runtime benchmark-leak guard" in matrix
    assert "benchmark source isolation" in audit
    assert "general runtime modules" in audit
    assert "benchmark-isolation check under `checks_passed`" in audit
    assert "benchmark-specific code is isolated from" in matrix
    assert "src/mapu/evaluation/" in matrix


def test_public_docs_require_release_audit_evidence_verifier() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    readme = _read_doc(repo_root, "README.md")
    audit = _read_doc(repo_root, "PUBLIC_RELEASE_AUDIT.md")
    matrix = _read_doc(repo_root, "docs/VALIDATION_EVIDENCE_MATRIX.md")

    for doc in (readme, audit, matrix):
        assert "verify_release_audit_evidence.py" in doc
        assert "release_ready_evidence" in doc
        assert "evidence_scope" in doc

    assert "--mode release" in readme
    assert "--require-cli-e2e" in readme
    assert "--require-mcp-e2e" in readme
    assert "release_ready_evidence=true" in matrix
    assert "evidence_scope=release" in matrix
    assert "release_ready_evidence=false" in matrix
    assert "evidence_scope=scoped" in matrix
    assert "top-level `sha`" in matrix
    assert "git_sha` matching the audit `sha" in matrix
    assert "command provenance" in audit
    assert "`{kind,status}` stubs are not evidence" in audit
    assert "all `required_checks=true`" in matrix


def test_public_docs_require_public_install_audit_evidence_verifier() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    readme = _read_doc(repo_root, "README.md")
    audit = _read_doc(repo_root, "PUBLIC_RELEASE_AUDIT.md")
    matrix = _read_doc(repo_root, "docs/VALIDATION_EVIDENCE_MATRIX.md")

    for doc in (readme, audit, matrix):
        assert "verify_public_install_audit_evidence.py" in doc

    assert "public_github_install_audit_summary.json" in readme
    assert "public_github_install_audit_summary.json" in audit
    assert "known commit SHA" in matrix
    assert "MCP list-only checks" in matrix
    assert "installed `mapu` help command" in matrix
    assert "same installed `mapu` executable" in matrix
    assert "evidence from the installed `mapu` command" in matrix
    assert "full required MCP tool set" in matrix
    assert "required_tools_present=true" in matrix
    assert "missing_required_tools=[]" in matrix
    assert "git_sha` matching the top-level public install `sha" in matrix
    assert "cli_help_evidence" in matrix
    assert "command/status/exit-code evidence" in matrix
    assert "mcp_stdio_smoke" in matrix
    assert "check-name-only summaries" in audit


def test_public_docs_require_validation_evidence_bundle_verifier() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    readme = _read_doc(repo_root, "README.md")
    matrix = _read_doc(repo_root, "docs/VALIDATION_EVIDENCE_MATRIX.md")
    guide = _read_doc(repo_root, "docs/CLI_OPERATOR_GUIDE.md")

    assert "verify_validation_evidence_bundle.py" in readme
    assert "verify_validation_evidence_bundle.py" in matrix
    assert "verify_validation_evidence_bundle.py --mode local-dev" in readme
    assert "--mode release" in matrix
    assert "--mode local-dev" in matrix
    assert "current `--repo-root` fingerprint" in matrix
    assert "same commit SHA" in matrix
    assert "--require-public-benchmark" in matrix
    assert "verify_objective_completion.py" in readme
    assert "verify_objective_completion.py" in matrix
    assert "--format text" in readme
    assert "--format text" in matrix
    assert "--format commit-plan" in readme
    assert "--format commit-plan" in matrix
    assert "--format commit-plan" in guide
    assert "--out .tmp\\release_cleanup_commit_plan.md" in readme
    assert "--out .tmp/release_cleanup_commit_plan.md" in guide
    assert "--out <path>" in matrix
    assert "non-destructive Markdown cleanup" in guide
    assert "git add -- ..." in guide
    assert "git add -- ..." in matrix
    assert "mapu doctor --json" in readme
    assert "mapu doctor --json" in matrix
    assert "installed_doctor_evidence" in matrix
    assert "doctor_evidence" in matrix
    assert "--continuity-replay" in readme
    assert "--continuity-replay" in matrix
    assert "Objective completion audit" in matrix
    assert "prompt-to-artifact checklist" in matrix
    assert "continuity replay response-quality evidence" in matrix
    assert "local_cli_mcp_evidence" in matrix
    assert "release/public SHA match" in matrix
    assert "separately from public release readiness" in matrix
    assert "blocker_categories" in matrix
    assert "next_unblocking_actions" in matrix
    assert "worktree_summary" in matrix
    assert "release_slices" in matrix
    assert "suggested_commit_plan" in matrix
    assert "commit_plan_integrity" in matrix
    assert "covered exactly once" in matrix
    assert "covered exactly once" in guide
    assert "publication_delta" in matrix
    assert "same committed SHA" in matrix
    assert "uncommitted working-tree changes" in matrix
    assert "public install MCP tool surface" in matrix
    assert "general-purpose product quality" in matrix


def test_public_docs_describe_working_tree_install_audit_as_scoped() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    readme = _read_doc(repo_root, "README.md")
    matrix = _read_doc(repo_root, "docs/VALIDATION_EVIDENCE_MATRIX.md")
    audit = _read_doc(repo_root, "PUBLIC_RELEASE_AUDIT.md")

    assert "-InstallFromWorkingTree" in readme
    assert "-InstallFromWorkingTree" in matrix
    assert "-InstallFromWorkingTree" in audit
    assert "worktree_fingerprint_sha256" in matrix
    assert "install_from_working_tree=true" in matrix
    assert "evidence_scope=scoped" in matrix
    assert (
        "tools\\release_surface_audit.ps1 -SkipFreshInstall -RunCliE2E -RunMcpE2E"
        not in readme
    )
    assert "release_surface_audit_worktree_install_probe.json" not in readme
    assert "release_surface_audit_cli_mcp_probe.json" not in readme


def test_public_docs_require_prepublish_benchmark_evidence_verifier() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    readme = _read_doc(repo_root, "README.md")
    audit = _read_doc(repo_root, "PUBLIC_RELEASE_AUDIT.md")
    status = _read_doc(repo_root, "GLOBAL_MEMORY_BENCHMARK_STATUS.md")
    matrix = _read_doc(repo_root, "docs/VALIDATION_EVIDENCE_MATRIX.md")

    for doc in (readme, audit, status, matrix):
        assert "verify_prepublish_benchmark_evidence.py" in doc

    assert "benchmark_evidence_verifier" in readme
    assert "benchmark_evidence_verifier" in status
    assert "benchmark_evidence_verifier" in matrix
    assert "--require-public-evidence-labels" in readme
    assert "--require-public-evidence-labels" in audit
    assert "--require-public-evidence-labels" in status
    assert "--require-public-evidence-labels" in matrix
    assert "public_performance_evidence=true" in readme
    assert "benchmark_evidence_verified=true" in readme
    assert "Passing smoke metadata" in status
    assert "verified metadata records `gate_pass=true`" in status
    assert "`public_performance_evidence=true`" in status
    assert "`benchmark_evidence_verified=true`" in status
    assert "Passing metadata must record `gate_pass=true`, `worktree=clean`" not in status
    assert "gate_pass=true" in status
    assert "service preflight" in status
    assert "clean code identity" in status
    assert "colocated leaderboard/log" in status
    assert "artifacts" in status
    assert "complete LoCoMo/LongMemEval/BEAM leaderboard sections" in status
    assert "`MISSING` outputs" in status
    assert "lane artifact directory" in status
