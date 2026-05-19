import hashlib
import json
import subprocess
from pathlib import Path

from tools.verify_benchmark_isolation import verify_benchmark_isolation
from tools.verify_full_sweep_progress import _load_json as load_full_sweep_progress_json
from tools.verify_full_sweep_progress import verify_full_sweep_progress
from tools.verify_objective_completion import (
    DEFAULT_BENCHMARK_GATE_META,
    _check_benchmark_isolation,
    _format_commit_plan_markdown,
    _format_text_summary,
    _load_json,
    _render_report,
    _resolve_latest_benchmark_gate_meta,
    audit_objective_completion,
)
from tools.verify_prepublish_benchmark_evidence import verify_prepublish_benchmark_evidence
from tools.verify_public_install_audit_evidence import (
    REQUIRED_CHECKS as PUBLIC_INSTALL_REQUIRED_CHECKS,
)
from tools.verify_public_install_audit_evidence import (
    REQUIRED_MCP_TOOLS as PUBLIC_INSTALL_REQUIRED_MCP_TOOLS,
)
from tools.verify_public_install_audit_evidence import (
    verify_public_install_audit_evidence,
)
from tools.verify_release_audit_evidence import (
    REQUIRED_CHECKS as RELEASE_AUDIT_REQUIRED_CHECKS,
)
from tools.verify_release_audit_evidence import (
    REQUIRED_MCP_TOOLS as RELEASE_AUDIT_REQUIRED_MCP_TOOLS,
)
from tools.verify_release_audit_evidence import (
    REQUIRED_SMOKE_CHECKS_BY_KIND as RELEASE_AUDIT_REQUIRED_SMOKE_CHECKS_BY_KIND,
)
from tools.verify_release_audit_evidence import (
    verify_release_audit_evidence,
)
from tools.verify_validation_evidence_bundle import _load_json as load_bundle_json
from tools.verify_validation_evidence_bundle import verify_validation_evidence_bundle


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (_repo_root() / relative_path).read_text(encoding="utf-8")


def _release_smoke(kind: str) -> dict[str, object]:
    command_line = ["uv", "run", "mapu"]
    if kind.startswith("MCP"):
        command_line.append("mcp")
    required_checks = {
        check: True
        for check in RELEASE_AUDIT_REQUIRED_SMOKE_CHECKS_BY_KIND.get(kind, ())
    }
    if not required_checks:
        required_checks = {
            "ingest_ok": True,
            "query_answer_nonempty": True,
            "delete_ok": True,
        }
    data: dict[str, object] = {
        "kind": kind,
        "status": "ok",
        "command_line": command_line,
        "corpus_id": "corpus-123",
        "mapu_version": "0.1.0",
        "git_sha": "abc123",
        "required_checks": required_checks,
    }
    if kind == "MCP stdio e2e":
        data.update(
            {
                "tool_count": len(RELEASE_AUDIT_REQUIRED_MCP_TOOLS),
                "required_tools_present": True,
                "missing_required_tools": [],
                "tools": list(RELEASE_AUDIT_REQUIRED_MCP_TOOLS),
            }
        )
    return data


def _release_doctor_evidence() -> dict[str, object]:
    return {
        "status": "ok",
        "mapu_version": "0.1.0",
        "mcp": {
            "tool_count": len(RELEASE_AUDIT_REQUIRED_MCP_TOOLS),
            "required_tool_count": len(RELEASE_AUDIT_REQUIRED_MCP_TOOLS),
            "required_tools_present": True,
            "missing_required_tools": [],
            "tools": list(RELEASE_AUDIT_REQUIRED_MCP_TOOLS),
        },
        "claim_boundary": "doctor checks installed CLI/MCP surface only",
    }


def _public_install_cli_help_evidence() -> list[dict[str, object]]:
    return [
        {"command": ["mapu", "--help"], "status": "ok", "exit_code": 0},
        {"command": ["mapu", "corpus", "--help"], "status": "ok", "exit_code": 0},
        {"command": ["mapu", "serve", "--help"], "status": "ok", "exit_code": 0},
        {"command": ["mapu", "doctor", "--help"], "status": "ok", "exit_code": 0},
        {"command": ["mapu", "mcp", "--help"], "status": "ok", "exit_code": 0},
    ]


def _public_install_mcp_smoke() -> dict[str, object]:
    return {
        "status": "ok",
        "command": "mapu",
        "args": ["mcp"],
        "mapu_version": "0.1.0",
        "git_sha": "abc123",
        "tool_count": len(PUBLIC_INSTALL_REQUIRED_MCP_TOOLS),
        "tools": list(PUBLIC_INSTALL_REQUIRED_MCP_TOOLS),
        "required_tools_present": True,
        "missing_required_tools": [],
        "workflow_enabled": False,
    }


def _public_install_doctor_evidence() -> dict[str, object]:
    return {
        "status": "ok",
        "mapu_version": "0.1.0",
        "mcp": {
            "tool_count": len(PUBLIC_INSTALL_REQUIRED_MCP_TOOLS),
            "required_tool_count": len(PUBLIC_INSTALL_REQUIRED_MCP_TOOLS),
            "required_tools_present": True,
            "missing_required_tools": [],
            "tools": list(PUBLIC_INSTALL_REQUIRED_MCP_TOOLS),
        },
        "claim_boundary": "doctor checks installed CLI/MCP surface only",
    }


def _continuity_replay_data(*, passed: bool = True) -> dict[str, object]:
    return {
        "handoff_effect": {
            "response_quality_gate": {
                "enabled": True,
                "passed": passed,
                "required_action_count": 1,
                "passed_action_count": 1 if passed else 0,
                "pass_rate": 1.0 if passed else 0.0,
                "required_min_pass_rate": 1.0,
                "failing_actions": []
                if passed
                else [{"action_type": "query", "reason": "answer_nonempty"}],
                "reason": (
                    "passed"
                    if passed
                    else "pass_rate=0.0000 < required_min_pass_rate=1.0000"
                ),
            }
        }
    }


def _worktree_fingerprint(status_lines: list[str]) -> str:
    payload = "\n".join(["[status]", *status_lines, "[files]"])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _benchmark_smoke_data(
    *,
    status_lines: list[str] | None = None,
    include_score_summary: bool = True,
) -> dict[str, object]:
    status_lines = [] if status_lines is None else status_lines
    data: dict[str, object] = {
        "status": "ok",
        "smoke_only": True,
        "public_performance_evidence": False,
        "worktree_status_porcelain": status_lines,
        "worktree_dirty_path_count": len(status_lines),
        "worktree_fingerprint_sha256": _worktree_fingerprint(status_lines),
        "worktree_fingerprint_errors": [],
    }
    if include_score_summary:
        data["score_summary"] = [
            {
                "benchmark": "memoryarena",
                "metric": "token_f1",
                "metric_value": 0.7,
                "passed": True,
            }
        ]
    return data


def _release_audit_data(*, release_ready: bool = True) -> dict[str, object]:
    status_lines = [] if release_ready else [" M README.md"]
    return {
        "sha": "abc123",
        "passed": True,
        "skip_fresh_install": not release_ready,
        "skip_docker": not release_ready,
        "allow_dirty_worktree": not release_ready,
        "install_from_working_tree": False,
        "release_ready_evidence": release_ready,
        "evidence_scope": "release" if release_ready else "scoped",
        "worktree_status_porcelain": status_lines,
        "worktree_dirty_path_count": len(status_lines),
        "worktree_fingerprint_sha256": _worktree_fingerprint(status_lines),
        "checks_passed": list(RELEASE_AUDIT_REQUIRED_CHECKS),
        "checks_failed": [],
        "checks_skipped": [] if release_ready else ["docker command is available"],
        "installed_doctor_evidence": _release_doctor_evidence(),
        "smoke_evidence": [
            _release_smoke("CLI e2e"),
            _release_smoke("MCP stdio e2e"),
        ],
    }


def _public_install_audit_data(*, embedded_evidence: bool = True) -> dict[str, object]:
    data: dict[str, object] = {
        "repo_url": "https://github.com/dl1683/MapU.git",
        "ref": "main",
        "sha": "abc123",
        "passed": True,
        "checks_passed": list(PUBLIC_INSTALL_REQUIRED_CHECKS),
        "checks_failed": [],
    }
    if embedded_evidence:
        data["cli_help_evidence"] = _public_install_cli_help_evidence()
        data["doctor_evidence"] = _public_install_doctor_evidence()
        data["mcp_stdio_smoke"] = _public_install_mcp_smoke()
    return data


def test_benchmark_isolation_verifier_allows_eval_surface_only(tmp_path: Path) -> None:
    runtime = tmp_path / "src" / "mapu" / "query"
    evaluation = tmp_path / "src" / "mapu" / "evaluation"
    runtime.mkdir(parents=True)
    evaluation.mkdir(parents=True)
    (runtime / "service.py").write_text(
        "def query():\n    return 'general memory'\n",
        encoding="utf-8",
    )
    (evaluation / "memoryarena.py").write_text("DATASET = 'memoryarena'\n", encoding="utf-8")
    (tmp_path / "src" / "mapu" / "cli.py").write_text(
        "HELP = 'mapu eval ama-bench'\n",
        encoding="utf-8",
    )

    ok, report = verify_benchmark_isolation(root=tmp_path)

    assert ok is True
    assert report["status"] == "ok"
    assert report["violation_count"] == 0
    assert report["allowed_benchmark_files"] == [
        "src/mapu/cli.py",
        "src/mapu/evaluation/memoryarena.py",
    ]


def test_benchmark_isolation_verifier_rejects_runtime_benchmark_leak(
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "src" / "mapu" / "query"
    runtime.mkdir(parents=True)
    (runtime / "service.py").write_text(
        "def query():\n    return 'memoryarena shortcut'\n",
        encoding="utf-8",
    )

    ok, report = verify_benchmark_isolation(root=tmp_path)

    assert ok is False
    assert report["status"] == "fail"
    assert report["violation_count"] == 1
    assert report["violations"][0]["path"] == "src/mapu/query/service.py"
    assert report["violations"][0]["match"] == "memoryarena"


def test_benchmark_isolation_verifier_rejects_evaluation_prompt_format_shortcut(
    tmp_path: Path,
) -> None:
    evaluation = tmp_path / "src" / "mapu" / "evaluation"
    evaluation.mkdir(parents=True)
    (evaluation / "ama_bench.py").write_text(
        "def predict(q):\n"
        "    if q.strip().startswith('Question:'):\n"
        "        return 'shortcut'\n",
        encoding="utf-8",
    )

    ok, report = verify_benchmark_isolation(root=tmp_path)

    assert ok is False
    assert report["status"] == "fail"
    assert report["violation_count"] == 1
    assert report["evaluation_shortcut_violations"][0]["path"] == (
        "src/mapu/evaluation/ama_bench.py"
    )
    assert report["evaluation_shortcut_violations"][0]["match"] == (
        ".startswith('Question:"
    )


def test_objective_benchmark_isolation_reports_prompt_format_shortcut(
    tmp_path: Path,
) -> None:
    evaluation = tmp_path / "src" / "mapu" / "evaluation"
    evaluation.mkdir(parents=True)
    (evaluation / "memoryarena.py").write_text(
        "def predict(q):\n"
        "    if q.startswith(\"Question:\"):\n"
        "        return 'shortcut'\n",
        encoding="utf-8",
    )

    check = _check_benchmark_isolation(tmp_path)

    assert check.status == "fail"
    assert check.errors == (
        "src/mapu/evaluation/memoryarena.py:2 matched .startswith(\"Question:",
    )


def test_objective_completion_discovers_latest_timestamped_gate_meta(
    tmp_path: Path,
) -> None:
    older = tmp_path / "logs" / "benchmarks" / "prepublish_gate_20260519_010101"
    newer = tmp_path / "logs" / "benchmarks" / "prepublish_gate_20260519_020202"
    older.mkdir(parents=True)
    newer.mkdir(parents=True)
    older_meta = older / "gate_meta.json"
    newer_meta = newer / "gate_meta.json"
    older_meta.write_text("{}", encoding="utf-8")
    newer_meta.write_text("{}", encoding="utf-8")

    resolved = _resolve_latest_benchmark_gate_meta(tmp_path, DEFAULT_BENCHMARK_GATE_META)

    assert resolved == newer_meta


def test_objective_completion_prefers_progress_gate_meta_over_unrelated_latest(
    tmp_path: Path,
) -> None:
    unrelated = tmp_path / "logs" / "benchmarks" / "prepublish_gate_20260519_020202"
    unrelated.mkdir(parents=True)
    (unrelated / "gate_meta.json").write_text("{}", encoding="utf-8")

    selected = tmp_path / "logs" / "benchmarks" / "prepublish_gate_20260519_010101"
    progress = tmp_path / ".tmp" / "full_sweep_progress.json"
    progress.parent.mkdir()
    progress.write_text(
        json.dumps({"gate_dir": str(selected.relative_to(tmp_path))}),
        encoding="utf-8",
    )

    resolved = _resolve_latest_benchmark_gate_meta(
        tmp_path,
        DEFAULT_BENCHMARK_GATE_META,
        progress,
    )

    assert resolved == selected / "gate_meta.json"


def test_prepublish_gate_records_lane_artifact_directory() -> None:
    script = _read("tools/prepublish_benchmark_gate.ps1")

    assert "lane_artifact_dir" in script
    assert "function New-GateMetadata" in script
    assert "code_identity = $codeIdentity" in script
    assert "benchmark_evidence_verifier = $benchmarkVerifierOut" in script
    assert '-Status "running"' in script
    assert "benchmark lanes are running; this is not public performance evidence" in script
    assert '-Status "sweep_complete_unverified"' in script
    assert '$meta["status"] = "passed"' in script
    assert '-Status "failed"' in script
    assert "function Write-TextUtf8NoBom" in script
    assert "function Write-JsonUtf8NoBom" in script
    assert "New-Object System.Text.UTF8Encoding -ArgumentList $false" in script
    assert "Write-TextUtf8NoBom -Path $codeIdentity" in script
    assert "Write-JsonUtf8NoBom -Data $meta -Path $gateMeta" in script
    assert "Set-Content -LiteralPath $gateMeta -Encoding UTF8" not in script
    assert "Set-Content -LiteralPath $codeIdentity -Encoding UTF8" not in script
    assert "public_performance_evidence = $PublicPerformanceEvidence" in script
    assert "benchmark_evidence_verified = $BenchmarkEvidenceVerified" in script
    assert "parallel_{0}" in script
    assert "sweep_{0}" in script


def test_powershell_evidence_writers_use_plain_utf8_without_bom() -> None:
    scripts = [
        "tools/benchmark_smoke_gate.ps1",
        "tools/prepublish_benchmark_gate.ps1",
        "tools/public_github_install_audit.ps1",
        "tools/release_surface_audit.ps1",
        "tools/run_full_leaderboard_sweeps.ps1",
        "tools/run_full_leaderboard_sweeps_parallel.ps1",
    ]

    for relative_path in scripts:
        script = _read(relative_path)
        assert "New-Object System.Text.UTF8Encoding -ArgumentList $false" in script
        assert "[System.IO.File]::WriteAllText" in script
        assert "Set-Content -LiteralPath" not in script
        assert " -Encoding UTF8" not in script


def test_public_install_audit_embeds_cli_and_mcp_evidence() -> None:
    script = _read("tools/public_github_install_audit.ps1")

    assert "cli_help_evidence = @($CliHelpEvidence)" in script
    assert "doctor_evidence = $DoctorEvidence" in script
    assert "mcp_stdio_smoke = $McpSmokeEvidence" in script
    assert "$cliHelpEvidence.Add" in script
    assert 'status = "fail"' in script
    assert "exit_code = $LASTEXITCODE" in script
    assert "exit_code = 0" in script
    assert "installed CLI help check failed: mapu" in script
    assert '@("doctor", "--help")' in script
    assert "mapu_doctor.json" in script
    assert '$checksFailed.Add("installed doctor check failed")' in script
    assert "--list-only" in script
    assert "--cwd $checkout" in script
    assert r'Join-Path $repoRoot "tools\mcp_stdio_smoke.py"' in script
    assert "logs\\mcp_stdio_smoke_last.json" in script
    assert "Public GitHub install audit failed: {0}" in script
    assert "ConvertFrom-Json" in script
    mcp_smoke_script = r'Join-Path $repoRoot "tools\mcp_stdio_smoke.py"'
    assert script.index("mapu_doctor.json") < script.index(mcp_smoke_script)


def test_public_install_audit_evidence_verifier_accepts_complete_audit() -> None:
    data = _public_install_audit_data()

    ok, errors = verify_public_install_audit_evidence(data)

    assert ok is True
    assert errors == []


def test_public_install_audit_evidence_verifier_rejects_partial_audit() -> None:
    data = {
        "repo_url": "https://github.com/dl1683/MapU.git",
        "ref": "main",
        "sha": "unknown",
        "passed": False,
        "checks_passed": ["public git clone completed"],
        "checks_failed": ["pip install failed"],
        "cli_help_evidence": [],
        "mcp_stdio_smoke": None,
    }

    ok, errors = verify_public_install_audit_evidence(data)

    assert ok is False
    assert "passed is not true" in errors
    assert "sha is missing or unknown" in errors
    assert any("checks_failed is not empty" in error for error in errors)
    assert any("missing required checks" in error for error in errors)


def test_public_install_audit_evidence_verifier_rejects_stubbed_checks() -> None:
    data = _public_install_audit_data(embedded_evidence=False)

    ok, errors = verify_public_install_audit_evidence(data)

    assert ok is False
    assert any("missing CLI help evidence" in error for error in errors)
    assert "mcp_stdio_smoke evidence is missing" in errors


def test_public_install_audit_evidence_verifier_requires_mapu_help_command() -> None:
    data = _public_install_audit_data()
    for item in data["cli_help_evidence"]:
        assert isinstance(item, dict)
        command = item["command"]
        assert isinstance(command, list)
        command[0] = "not-mapu"

    ok, errors = verify_public_install_audit_evidence(data)

    assert ok is False
    assert any("missing CLI help evidence" in error for error in errors)


def test_public_install_audit_evidence_verifier_reports_failed_help_evidence() -> None:
    data = _public_install_audit_data()
    assert isinstance(data["cli_help_evidence"], list)
    data["cli_help_evidence"][-2] = {
        "command": ["mapu", "doctor", "--help"],
        "status": "fail",
        "exit_code": 2,
    }

    ok, errors = verify_public_install_audit_evidence(data)

    assert ok is False
    assert "missing CLI help evidence: ['mapu doctor --help']" in errors
    assert "CLI help evidence failed: mapu doctor --help" in errors


def test_public_install_audit_evidence_verifier_requires_mapu_mcp_command() -> None:
    data = _public_install_audit_data()
    assert isinstance(data["mcp_stdio_smoke"], dict)
    data["mcp_stdio_smoke"]["command"] = "not-mapu"

    ok, errors = verify_public_install_audit_evidence(data)

    assert ok is False
    assert "mcp_stdio_smoke command is not installed mapu" in errors


def test_public_install_audit_evidence_verifier_requires_same_mapu_command() -> None:
    data = _public_install_audit_data()
    for item in data["cli_help_evidence"]:
        assert isinstance(item, dict)
        command = item["command"]
        assert isinstance(command, list)
        command[0] = r"C:\audit\venv\Scripts\mapu.exe"
    assert isinstance(data["mcp_stdio_smoke"], dict)
    data["mcp_stdio_smoke"]["command"] = r"C:\other\venv\Scripts\mapu.exe"

    ok, errors = verify_public_install_audit_evidence(data)

    assert ok is False
    assert "mcp_stdio_smoke command does not match CLI help mapu command" in errors


def test_public_install_audit_evidence_verifier_rejects_multiple_mapu_commands() -> None:
    data = _public_install_audit_data()
    assert isinstance(data["cli_help_evidence"], list)
    assert isinstance(data["cli_help_evidence"][0], dict)
    first_command = data["cli_help_evidence"][0]["command"]
    assert isinstance(first_command, list)
    first_command[0] = r"C:\other\venv\Scripts\mapu.exe"

    ok, errors = verify_public_install_audit_evidence(data)

    assert ok is False
    assert "CLI help evidence uses multiple installed mapu commands" in errors


def test_public_install_audit_evidence_verifier_rejects_bad_mcp_list_only() -> None:
    data = {
        "repo_url": "https://github.com/dl1683/MapU.git",
        "ref": "main",
        "sha": "abc123",
        "passed": True,
        "checks_passed": list(PUBLIC_INSTALL_REQUIRED_CHECKS),
        "checks_failed": [],
        "cli_help_evidence": _public_install_cli_help_evidence(),
        "mcp_stdio_smoke": {
            **_public_install_mcp_smoke(),
            "required_tools_present": False,
            "missing_required_tools": ["handoff_context"],
            "workflow_enabled": True,
        },
    }

    ok, errors = verify_public_install_audit_evidence(data)

    assert ok is False
    assert "mcp_stdio_smoke required_tools_present is not true" in errors
    assert "mcp_stdio_smoke missing_required_tools is not empty" in errors
    assert "mcp_stdio_smoke workflow_enabled is not false" in errors


def test_public_install_audit_evidence_verifier_rejects_incomplete_mcp_tool_list() -> None:
    data = _public_install_audit_data()
    assert isinstance(data["mcp_stdio_smoke"], dict)
    smoke = data["mcp_stdio_smoke"]
    tools = smoke["tools"]
    assert isinstance(tools, list)
    smoke["tools"] = [tool for tool in tools if tool != "log_learning_feedback"]
    smoke["tool_count"] = len(smoke["tools"])

    ok, errors = verify_public_install_audit_evidence(data)

    assert ok is False
    assert (
        "mcp_stdio_smoke tool_count is below required tool count "
        f"{len(PUBLIC_INSTALL_REQUIRED_MCP_TOOLS)}"
    ) in errors
    assert (
        "mcp_stdio_smoke tools missing required tools: ['log_learning_feedback']"
        in errors
    )


def test_public_install_audit_evidence_verifier_rejects_mcp_sha_mismatch() -> None:
    data = _public_install_audit_data()
    assert isinstance(data["mcp_stdio_smoke"], dict)
    data["mcp_stdio_smoke"]["git_sha"] = "other-sha"

    ok, errors = verify_public_install_audit_evidence(data)

    assert ok is False
    assert "mcp_stdio_smoke git_sha does not match public install sha" in errors


def test_objective_completion_audit_reports_current_style_blockers(tmp_path: Path) -> None:
    smoke_path = tmp_path / "smoke_report.json"
    release_audit = tmp_path / "release_audit.json"
    release_audit.write_text(
        json.dumps(_release_audit_data(release_ready=False)),
        encoding="utf-8",
    )
    smoke_path.write_text(
        json.dumps(_benchmark_smoke_data(status_lines=[" M README.md"])),
        encoding="utf-8",
    )

    def fake_run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        if args in (
            ["git", "status", "--porcelain"],
            ["git", "status", "--porcelain=v1"],
        ):
            return subprocess.CompletedProcess(args, 0, stdout=" M README.md\n", stderr="")
        if args == ["git", "status", "--porcelain=v1", "-uall"]:
            return subprocess.CompletedProcess(
                args,
                0,
                stdout=(
                    " M README.md\n"
                    "?? docs/CLI_OPERATOR_GUIDE.md\n"
                    "?? src/mapu/evaluation/memoryarena.py\n"
                    "?? .gitattributes\n"
                ),
                stderr="",
            )
        if args in (
            ["git", "diff", "--name-only", "HEAD"],
            ["git", "ls-files", "--others", "--exclude-standard"],
        ):
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="docker unavailable")

    report = audit_objective_completion(
        repo_root=tmp_path,
        release_audit=release_audit,
        public_install_audit=tmp_path / "missing_public.json",
        benchmark_gate_meta=tmp_path / "missing_gate.json",
        full_sweep_progress=tmp_path / "missing_progress.json",
        benchmark_smoke=smoke_path,
        run_command=fake_run,
    )

    assert report["status"] == "incomplete"
    assert "prompt_to_artifact_checklist" in report
    assert {
        item["requirement"] for item in report["prompt_to_artifact_checklist"]
    } >= {
        "working flawlessly with actual CLI systems",
        "general-purpose agent-memory quality is verified beyond benchmarks",
        "public benchmark performance claims are backed by public evidence",
        "very good documentation",
    }
    assert any("worktree has 1 changed paths" in blocker for blocker in report["blockers"])
    assert any("docker unavailable" in blocker for blocker in report["blockers"])
    assert any("release_ready_evidence is not true" in blocker for blocker in report["blockers"])
    categories = {
        item["category"]: item
        for item in report["blocker_categories"]
    }
    assert categories["worktree_state"]["blockers"] == ("worktree has 1 changed paths",)
    assert "docker unavailable" in categories["local_environment"]["blockers"]
    assert "release_ready_evidence is not true" in categories["release_readiness"]["blockers"]
    assert (
        "public install audit evidence not found"
        in categories["publication_state"]["blockers"][0]
    )
    assert (
        "benchmark gate evidence not found"
        in categories["public_benchmark_evidence"]["blockers"][0]
    )
    assert (
        "continuity replay evidence not found"
        in categories["general_product_quality"]["blockers"][0]
    )
    assert report["worktree_summary"]["expanded_path_count"] == 4
    assert report["worktree_summary"]["by_area"] == {
        "docs": 1,
        "project_config": 1,
        "root_docs": 1,
        "source": 1,
    }
    assert report["worktree_summary"]["by_status"] == {
        "modified": 1,
        "untracked": 3,
    }
    assert report["worktree_summary"]["release_slices"] == {
        "benchmark_evaluation": {
            "count": 1,
            "paths": ["src/mapu/evaluation/memoryarena.py"],
            "sample": ["src/mapu/evaluation/memoryarena.py"],
        },
        "docs_claims": {
            "count": 2,
            "paths": ["README.md", "docs/CLI_OPERATOR_GUIDE.md"],
            "sample": ["README.md", "docs/CLI_OPERATOR_GUIDE.md"],
        },
        "project_config": {
            "count": 1,
            "paths": [".gitattributes"],
            "sample": [".gitattributes"],
        },
    }
    assert report["worktree_summary"]["commit_plan_integrity"] == {
        "status": "ok",
        "changed_path_count": 4,
        "planned_path_count": 4,
        "unique_planned_path_count": 4,
        "slice_count": 3,
        "duplicate_planned_paths": [],
        "missing_from_plan": [],
        "unexpected_in_plan": [],
    }
    assert report["worktree_summary"]["suggested_commit_plan"] == [
        {
            "order": 1,
            "slice": "benchmark_evaluation",
            "count": 1,
            "paths": ["src/mapu/evaluation/memoryarena.py"],
            "suggested_commit_message": "memory benchmark evaluation adapters and gates",
        },
        {
            "order": 2,
            "slice": "docs_claims",
            "count": 2,
            "paths": ["README.md", "docs/CLI_OPERATOR_GUIDE.md"],
            "suggested_commit_message": "claim discipline and operator documentation",
        },
        {
            "order": 3,
            "slice": "project_config",
            "count": 1,
            "paths": [".gitattributes"],
            "suggested_commit_message": "project configuration and local artifact policy",
        },
    ]
    next_actions = {
        item["category"]: item["next_action"]
        for item in report["next_unblocking_actions"]
    }
    assert "Docker" in next_actions["local_environment"]
    assert "public GitHub install audit" in next_actions["publication_state"]
    assert "real corpus" in next_actions["general_product_quality"]
    cli_item = next(
        item
        for item in report["prompt_to_artifact_checklist"]
        if item["requirement"] == "working flawlessly with actual CLI systems"
    )
    assert cli_item["status"] == "ok"
    smoke_check = next(
        check for check in report["checks"] if check["name"] == "benchmark_smoke_boundary"
    )
    assert smoke_check["status"] == "ok"
    anti_overfit = next(
        item
        for item in report["prompt_to_artifact_checklist"]
        if item["requirement"]
        == "benchmark performance does not rely on benchmark-specific shortcuts"
    )
    assert anti_overfit["status"] == "ok"
    quality_item = next(
        item
        for item in report["prompt_to_artifact_checklist"]
        if item["requirement"]
        == "general-purpose agent-memory quality is verified beyond benchmarks"
    )
    assert quality_item["status"] == "fail"


def test_objective_completion_audit_requires_continuity_response_quality(
    tmp_path: Path,
) -> None:
    continuity_replay = tmp_path / "continuity_replay.json"
    continuity_replay.write_text(
        json.dumps(_continuity_replay_data(passed=False)),
        encoding="utf-8",
    )

    def fake_run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    report = audit_objective_completion(
        repo_root=tmp_path,
        release_audit=tmp_path / "missing_release.json",
        public_install_audit=tmp_path / "missing_public.json",
        benchmark_gate_meta=tmp_path / "missing_gate.json",
        full_sweep_progress=tmp_path / "missing_progress.json",
        benchmark_smoke=tmp_path / "missing_smoke.json",
        continuity_replay=continuity_replay,
        run_command=fake_run,
    )

    quality_check = next(
        check for check in report["checks"] if check["name"] == "continuity_response_quality"
    )
    assert quality_check["status"] == "fail"
    assert "response_quality_gate did not pass" in quality_check["errors"]
    assert (
        "response_quality_gate pass_rate 0.0 below required_min_pass_rate 1.0"
        in quality_check["errors"]
    )


def test_objective_completion_audit_rejects_stale_dirty_worktree_evidence(
    tmp_path: Path,
) -> None:
    release_audit = tmp_path / "release_audit.json"
    release_audit.write_text(
        json.dumps(_release_audit_data(release_ready=False)),
        encoding="utf-8",
    )
    smoke_path = tmp_path / "smoke_report.json"
    smoke_path.write_text(
        json.dumps(_benchmark_smoke_data(status_lines=[" M README.md"])),
        encoding="utf-8",
    )

    def fake_run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        if args in (
            ["git", "status", "--porcelain"],
            ["git", "status", "--porcelain=v1"],
        ):
            return subprocess.CompletedProcess(args, 0, stdout=" M src/mapu/cli.py\n", stderr="")
        if args in (
            ["git", "diff", "--name-only", "HEAD"],
            ["git", "ls-files", "--others", "--exclude-standard"],
        ):
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="docker unavailable")

    report = audit_objective_completion(
        repo_root=tmp_path,
        release_audit=release_audit,
        public_install_audit=tmp_path / "missing_public.json",
        benchmark_gate_meta=tmp_path / "missing_gate.json",
        full_sweep_progress=tmp_path / "missing_progress.json",
        benchmark_smoke=smoke_path,
        run_command=fake_run,
    )

    local_check = next(
        check for check in report["checks"] if check["name"] == "local_cli_mcp_evidence"
    )
    assert local_check["status"] == "fail"
    assert (
        "local CLI/MCP audit worktree_status_porcelain does not match current worktree"
        in local_check["errors"]
    )
    assert (
        "local CLI/MCP audit worktree_fingerprint_sha256 does not match current worktree"
        in local_check["errors"]
    )


def test_objective_completion_audit_rejects_release_public_sha_mismatch(
    tmp_path: Path,
) -> None:
    release_audit = tmp_path / "release_audit.json"
    public_install = tmp_path / "public_install.json"
    smoke_path = tmp_path / "smoke_report.json"
    release_audit.write_text(json.dumps(_release_audit_data()), encoding="utf-8")
    public_data = _public_install_audit_data()
    public_data["sha"] = "other-sha"
    assert isinstance(public_data["mcp_stdio_smoke"], dict)
    public_data["mcp_stdio_smoke"]["git_sha"] = "other-sha"
    public_install.write_text(json.dumps(public_data), encoding="utf-8")
    smoke_path.write_text(
        json.dumps(_benchmark_smoke_data()),
        encoding="utf-8",
    )

    def fake_run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    report = audit_objective_completion(
        repo_root=tmp_path,
        release_audit=release_audit,
        public_install_audit=public_install,
        benchmark_gate_meta=tmp_path / "missing_gate.json",
        full_sweep_progress=tmp_path / "missing_progress.json",
        benchmark_smoke=smoke_path,
        run_command=fake_run,
    )

    sha_check = next(
        check for check in report["checks"] if check["name"] == "release_public_sha_match"
    )
    assert sha_check["status"] == "fail"
    assert sha_check["errors"] == (
        "release audit sha 'abc123' does not match public install sha 'other-sha'",
    )
    public_item = next(
        item
        for item in report["prompt_to_artifact_checklist"]
        if item["requirement"] == "public install works from actual released code"
    )
    assert public_item["status"] == "fail"


def test_objective_completion_audit_rejects_stale_release_sha(
    tmp_path: Path,
) -> None:
    release_audit = tmp_path / "release_audit.json"
    public_install = tmp_path / "public_install.json"
    smoke_path = tmp_path / "smoke_report.json"
    release_audit.write_text(json.dumps(_release_audit_data()), encoding="utf-8")
    public_install.write_text(json.dumps(_public_install_audit_data()), encoding="utf-8")
    smoke_path.write_text(json.dumps(_benchmark_smoke_data()), encoding="utf-8")

    def fake_run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        if args == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, stdout="new-sha\n", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    report = audit_objective_completion(
        repo_root=tmp_path,
        release_audit=release_audit,
        public_install_audit=public_install,
        benchmark_gate_meta=tmp_path / "missing_gate.json",
        full_sweep_progress=tmp_path / "missing_progress.json",
        benchmark_smoke=smoke_path,
        run_command=fake_run,
    )

    sha_check = next(
        check for check in report["checks"] if check["name"] == "release_public_sha_match"
    )
    assert sha_check["status"] == "fail"
    assert "release audit sha 'abc123' does not match current HEAD 'new-sha'" in sha_check[
        "errors"
    ]
    assert "public install sha 'abc123' does not match current HEAD 'new-sha'" in sha_check[
        "errors"
    ]


def test_objective_completion_rejects_stale_full_sweep_progress_sha(
    tmp_path: Path,
) -> None:
    release_audit = tmp_path / "release_audit.json"
    public_install = tmp_path / "public_install.json"
    smoke_path = tmp_path / "smoke_report.json"
    progress = tmp_path / "full_sweep_progress.json"
    release_audit.write_text(json.dumps(_release_audit_data()), encoding="utf-8")
    public_install.write_text(json.dumps(_public_install_audit_data()), encoding="utf-8")
    smoke_path.write_text(json.dumps(_benchmark_smoke_data()), encoding="utf-8")
    progress.write_text(
        json.dumps(
            {
                "suffix": "prepublish_20260519_054949",
                "gate_dir": "logs/benchmarks/prepublish_gate_20260519_054949",
                "code_sha": "old-sha",
                "worktree": "clean",
                "gate_meta_present": True,
                "gate_pass": True,
                "active_worker_count": 0,
                "public_performance_evidence": True,
                "locomo": {"completed": 1540, "total": 1540},
                "longmemeval": {"completed": 500, "total": 500},
                "beam": [
                    {"project": "beam_100k", "completed": 500, "total": 500},
                    {"project": "beam_500k", "completed": 500, "total": 500},
                    {"project": "beam_1m", "completed": 500, "total": 500},
                    {"project": "beam_10m", "completed": 500, "total": 500},
                ],
                "workers": [],
            }
        ),
        encoding="utf-8",
    )

    def fake_run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        if args == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, stdout="new-sha\n", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    report = audit_objective_completion(
        repo_root=tmp_path,
        release_audit=release_audit,
        public_install_audit=public_install,
        benchmark_gate_meta=tmp_path / "missing_gate.json",
        full_sweep_progress=progress,
        benchmark_smoke=smoke_path,
        run_command=fake_run,
    )

    progress_check = next(
        check for check in report["checks"] if check["name"] == "full_sweep_progress"
    )
    assert progress_check["status"] == "fail"
    assert (
        "full-sweep progress code_sha 'old-sha' does not match current HEAD 'new-sha'"
        in progress_check["errors"]
    )


def test_objective_completion_reports_publication_tool_delta(tmp_path: Path) -> None:
    release_audit = tmp_path / "release_audit.json"
    public_install = tmp_path / "public_install.json"
    smoke_path = tmp_path / "smoke_report.json"
    release_audit.write_text(json.dumps(_release_audit_data()), encoding="utf-8")
    public_data = _public_install_audit_data()
    public_data["passed"] = False
    mcp_smoke = public_data["mcp_stdio_smoke"]
    assert isinstance(mcp_smoke, dict)
    mcp_smoke["tool_count"] = len(PUBLIC_INSTALL_REQUIRED_MCP_TOOLS) - 1
    mcp_smoke["required_tools_present"] = False
    mcp_smoke["missing_required_tools"] = ["handoff_context"]
    mcp_smoke["tools"] = [
        tool for tool in PUBLIC_INSTALL_REQUIRED_MCP_TOOLS if tool != "handoff_context"
    ]
    public_install.write_text(json.dumps(public_data), encoding="utf-8")
    smoke_path.write_text(json.dumps(_benchmark_smoke_data()), encoding="utf-8")

    def fake_run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    report = audit_objective_completion(
        repo_root=tmp_path,
        release_audit=release_audit,
        public_install_audit=public_install,
        benchmark_gate_meta=tmp_path / "missing_gate.json",
        full_sweep_progress=tmp_path / "missing_progress.json",
        benchmark_smoke=smoke_path,
        run_command=fake_run,
    )

    assert report["publication_delta"] == {
        "status": "drift",
        "local_required_tools_present": True,
        "public_required_tools_present": False,
        "local_doctor_available": True,
        "public_doctor_available": True,
        "local_doctor_required_tools_present": True,
        "public_doctor_required_tools_present": True,
        "local_tool_count": len(RELEASE_AUDIT_REQUIRED_MCP_TOOLS),
        "public_tool_count": len(PUBLIC_INSTALL_REQUIRED_MCP_TOOLS) - 1,
        "locally_present_public_missing_tools": ("handoff_context",),
        "public_missing_required_tools": ("handoff_context",),
        "note": "public install is behind the local MCP tool surface",
    }


def test_objective_completion_publication_delta_explains_dirty_same_sha_drift(
    tmp_path: Path,
) -> None:
    release_audit = tmp_path / "release_audit.json"
    public_install = tmp_path / "public_install.json"
    smoke_path = tmp_path / "smoke_report.json"
    release_data = _release_audit_data(release_ready=False)
    release_data["install_from_working_tree"] = True
    release_audit.write_text(json.dumps(release_data), encoding="utf-8")
    public_data = _public_install_audit_data()
    public_data["passed"] = False
    mcp_smoke = public_data["mcp_stdio_smoke"]
    assert isinstance(mcp_smoke, dict)
    mcp_smoke["tool_count"] = len(PUBLIC_INSTALL_REQUIRED_MCP_TOOLS) - 1
    mcp_smoke["required_tools_present"] = False
    mcp_smoke["missing_required_tools"] = ["handoff_context"]
    public_install.write_text(json.dumps(public_data), encoding="utf-8")
    smoke_path.write_text(json.dumps(_benchmark_smoke_data()), encoding="utf-8")

    def fake_run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    report = audit_objective_completion(
        repo_root=tmp_path,
        release_audit=release_audit,
        public_install_audit=public_install,
        benchmark_gate_meta=tmp_path / "missing_gate.json",
        full_sweep_progress=tmp_path / "missing_progress.json",
        benchmark_smoke=smoke_path,
        run_command=fake_run,
    )

    note = report["publication_delta"]["note"]
    assert "public install is behind the local MCP tool surface" in note
    assert "same committed SHA" in note
    assert "uncommitted working-tree changes" in note


def test_objective_completion_text_summary_surfaces_key_status(tmp_path: Path) -> None:
    release_audit = tmp_path / "release_audit.json"
    public_install = tmp_path / "public_install.json"
    smoke_path = tmp_path / "smoke_report.json"
    release_audit.write_text(json.dumps(_release_audit_data()), encoding="utf-8")
    public_data = _public_install_audit_data()
    public_data["passed"] = False
    mcp_smoke = public_data["mcp_stdio_smoke"]
    assert isinstance(mcp_smoke, dict)
    mcp_smoke["required_tools_present"] = False
    mcp_smoke["missing_required_tools"] = ["handoff_context"]
    public_install.write_text(json.dumps(public_data), encoding="utf-8")
    smoke_path.write_text(json.dumps(_benchmark_smoke_data()), encoding="utf-8")

    def fake_run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        if args == ["git", "status", "--porcelain"]:
            return subprocess.CompletedProcess(args, 0, stdout=" M README.md\n", stderr="")
        if args == ["git", "status", "--porcelain=v1", "-uall"]:
            return subprocess.CompletedProcess(
                args,
                0,
                stdout=" M README.md\n?? tools/verify_objective_completion.py\n",
                stderr="",
            )
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    report = audit_objective_completion(
        repo_root=tmp_path,
        release_audit=release_audit,
        public_install_audit=public_install,
        benchmark_gate_meta=tmp_path / "missing_gate.json",
        full_sweep_progress=tmp_path / "missing_progress.json",
        benchmark_smoke=smoke_path,
        run_command=fake_run,
    )

    summary = _format_text_summary(report)

    assert "MapU objective completion: incomplete" in summary
    assert "OK deliverables:" in summary
    assert "working flawlessly with actual CLI systems" in summary
    assert "Blockers by category:" in summary
    assert "worktree_state: 1 blocker(s)" in summary
    assert "Worktree cleanup summary:" in summary
    assert "expanded paths: 2" in summary
    assert "by area: root_docs=1, tools=1" in summary
    assert "by status: modified=1, untracked=1" in summary
    assert "commit plan integrity: ok (2/2 paths planned)" in summary
    assert "release slices:" in summary
    assert "docs_claims: 1" in summary
    assert "release_evidence_tooling: 1" in summary
    assert "suggested commit order:" in summary
    assert (
        "1. release_evidence_tooling (1 paths): release evidence and benchmark audit tooling"
        in summary
    )
    assert "2. docs_claims (1 paths): claim discipline and operator documentation" in summary
    assert "Publication delta:" in summary
    assert "doctor: local=available, public=available" in summary
    assert "doctor required tools: local=True, public=True" in summary
    assert "public missing required tools: handoff_context" in summary
    assert "public install is behind the local MCP tool surface" in summary

    commit_plan = _format_commit_plan_markdown(report)

    assert "# MapU Release Cleanup Commit Plan" in commit_plan
    assert "Objective status: `incomplete`" in commit_plan
    assert "### 1. `release_evidence_tooling`" in commit_plan
    assert "Commit plan integrity: `ok` (`2`/`2` paths planned)" in commit_plan
    assert "Stage this slice after review:" in commit_plan
    assert "git add -- `" in commit_plan
    assert '  "tools/verify_objective_completion.py"' in commit_plan
    assert "tools/verify_objective_completion.py" in commit_plan
    assert "### 2. `docs_claims`" in commit_plan
    assert "README.md" in commit_plan
    assert _render_report(report, "commit-plan") == commit_plan
    assert _render_report(report, "text") == summary
    assert '"status": "incomplete"' in _render_report(report, "json")


def test_objective_completion_reports_publication_doctor_delta(tmp_path: Path) -> None:
    release_audit = tmp_path / "release_audit.json"
    public_install = tmp_path / "public_install.json"
    smoke_path = tmp_path / "smoke_report.json"
    release_audit.write_text(json.dumps(_release_audit_data()), encoding="utf-8")
    public_data = _public_install_audit_data()
    public_data["passed"] = False
    public_data.pop("doctor_evidence")
    public_install.write_text(json.dumps(public_data), encoding="utf-8")
    smoke_path.write_text(json.dumps(_benchmark_smoke_data()), encoding="utf-8")

    def fake_run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    report = audit_objective_completion(
        repo_root=tmp_path,
        release_audit=release_audit,
        public_install_audit=public_install,
        benchmark_gate_meta=tmp_path / "missing_gate.json",
        full_sweep_progress=tmp_path / "missing_progress.json",
        benchmark_smoke=smoke_path,
        run_command=fake_run,
    )

    assert report["publication_delta"]["status"] == "drift"
    assert report["publication_delta"]["local_doctor_available"] is True
    assert report["publication_delta"]["public_doctor_available"] is False
    assert report["publication_delta"]["local_doctor_required_tools_present"] is True
    assert report["publication_delta"]["public_doctor_required_tools_present"] is None
    assert report["publication_delta"]["note"] == (
        "public install is behind the local doctor command"
    )


def test_objective_completion_audit_rejects_label_only_smoke(tmp_path: Path) -> None:
    smoke_path = tmp_path / "smoke_report.json"
    smoke_path.write_text(
        json.dumps(_benchmark_smoke_data(include_score_summary=False)),
        encoding="utf-8",
    )

    def fake_run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    report = audit_objective_completion(
        repo_root=tmp_path,
        release_audit=tmp_path / "missing_release.json",
        public_install_audit=tmp_path / "missing_public.json",
        benchmark_gate_meta=tmp_path / "missing_gate.json",
        full_sweep_progress=tmp_path / "missing_progress.json",
        benchmark_smoke=smoke_path,
        run_command=fake_run,
    )

    smoke_check = next(
        check for check in report["checks"] if check["name"] == "benchmark_smoke_boundary"
    )
    assert smoke_check["status"] == "fail"
    assert smoke_check["errors"] == ("score_summary is missing or empty",)


def test_objective_completion_audit_rejects_stale_benchmark_smoke(
    tmp_path: Path,
) -> None:
    smoke_path = tmp_path / "smoke_report.json"
    smoke_path.write_text(
        json.dumps(_benchmark_smoke_data(status_lines=[" M README.md"])),
        encoding="utf-8",
    )

    def fake_run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        if args == ["git", "status", "--porcelain"]:
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        if args == ["git", "status", "--porcelain=v1"]:
            return subprocess.CompletedProcess(
                args,
                0,
                stdout=" M src/mapu/cli.py\n",
                stderr="",
            )
        if args in (
            ["git", "diff", "--name-only", "HEAD"],
            ["git", "ls-files", "--others", "--exclude-standard"],
        ):
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="docker unavailable")

    report = audit_objective_completion(
        repo_root=tmp_path,
        release_audit=tmp_path / "missing_release.json",
        public_install_audit=tmp_path / "missing_public.json",
        benchmark_gate_meta=tmp_path / "missing_gate.json",
        full_sweep_progress=tmp_path / "missing_progress.json",
        benchmark_smoke=smoke_path,
        run_command=fake_run,
    )

    smoke_check = next(
        check for check in report["checks"] if check["name"] == "benchmark_smoke_boundary"
    )
    assert smoke_check["status"] == "fail"
    assert (
        "benchmark smoke worktree_status_porcelain does not match current worktree"
        in smoke_check["errors"]
    )
    assert (
        "benchmark smoke worktree_fingerprint_sha256 does not match current worktree"
        in smoke_check["errors"]
    )


def test_validation_evidence_bundle_accepts_scoped_local_dev_evidence(tmp_path: Path) -> None:
    release_audit = tmp_path / "release_audit.json"
    release_audit.write_text(
        json.dumps(
                {
                    "sha": "abc123",
                    "passed": True,
                    "skip_fresh_install": True,
                "skip_docker": True,
                "allow_dirty_worktree": True,
                "release_ready_evidence": False,
                "evidence_scope": "scoped",
                "worktree_status_porcelain": [" M README.md"],
                "worktree_dirty_path_count": 1,
                "worktree_fingerprint_sha256": _worktree_fingerprint([" M README.md"]),
                "checks_passed": list(RELEASE_AUDIT_REQUIRED_CHECKS),
                "checks_failed": [],
                "checks_skipped": ["docker command is available"],
                "smoke_evidence": [
                    _release_smoke("CLI e2e"),
                    _release_smoke("MCP stdio e2e"),
                ],
            }
        ),
        encoding="utf-8",
    )

    def fake_run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        if args == ["git", "status", "--porcelain=v1"]:
            return subprocess.CompletedProcess(args, 0, stdout=" M README.md\n", stderr="")
        if args in (
            ["git", "diff", "--name-only", "HEAD"],
            ["git", "ls-files", "--others", "--exclude-standard"],
        ):
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="unexpected command")

    ok, results = verify_validation_evidence_bundle(
        mode="local-dev",
        repo_root=tmp_path,
        release_audit=release_audit,
        run_command=fake_run,
    )

    assert ok is True
    assert results == [
        {
            "name": "release_audit",
            "path": str(release_audit),
            "required": True,
            "status": "ok",
            "errors": [],
        }
    ]


def test_validation_evidence_bundle_rejects_stale_scoped_local_dev_evidence(
    tmp_path: Path,
) -> None:
    release_audit = tmp_path / "release_audit.json"
    release_audit.write_text(
        json.dumps(_release_audit_data(release_ready=False)),
        encoding="utf-8",
    )

    def fake_run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        if args == ["git", "status", "--porcelain=v1"]:
            return subprocess.CompletedProcess(args, 0, stdout=" M src/mapu/cli.py\n", stderr="")
        if args in (
            ["git", "diff", "--name-only", "HEAD"],
            ["git", "ls-files", "--others", "--exclude-standard"],
        ):
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="unexpected command")

    ok, results = verify_validation_evidence_bundle(
        mode="local-dev",
        repo_root=tmp_path,
        release_audit=release_audit,
        run_command=fake_run,
    )

    assert ok is False
    assert results[0]["status"] == "fail"
    assert (
        "release audit worktree_status_porcelain does not match current worktree"
        in results[0]["errors"]
    )
    assert (
        "release audit worktree_fingerprint_sha256 does not match current worktree"
        in results[0]["errors"]
    )


def test_validation_evidence_bundle_release_requires_public_install(
    tmp_path: Path,
) -> None:
    release_audit = tmp_path / "release_audit.json"
    release_audit.write_text(json.dumps(_release_audit_data()), encoding="utf-8")

    ok, results = verify_validation_evidence_bundle(
        mode="release",
        release_audit=release_audit,
    )

    assert ok is False
    assert results[0]["status"] == "ok"
    assert results[1] == {
        "name": "public_install_audit",
        "path": None,
        "required": True,
        "status": "fail",
        "errors": ["public install audit evidence path is required for release mode"],
    }


def test_validation_evidence_bundle_accepts_complete_release_without_benchmark(
    tmp_path: Path,
) -> None:
    release_audit = tmp_path / "release_audit.json"
    public_install = tmp_path / "public_install.json"
    release_audit.write_text(json.dumps(_release_audit_data()), encoding="utf-8")
    public_install.write_text(json.dumps(_public_install_audit_data()), encoding="utf-8")

    ok, results = verify_validation_evidence_bundle(
        mode="release",
        release_audit=release_audit,
        public_install_audit=public_install,
    )

    assert ok is True
    assert [result["status"] for result in results] == ["ok", "ok", "ok"]
    assert results[2]["name"] == "release_public_sha_match"


def test_validation_evidence_bundle_rejects_release_public_sha_mismatch(
    tmp_path: Path,
) -> None:
    release_audit = tmp_path / "release_audit.json"
    public_install = tmp_path / "public_install.json"
    release_audit.write_text(json.dumps(_release_audit_data()), encoding="utf-8")
    public_data = _public_install_audit_data()
    public_data["sha"] = "other-sha"
    assert isinstance(public_data["mcp_stdio_smoke"], dict)
    public_data["mcp_stdio_smoke"]["git_sha"] = "other-sha"
    public_install.write_text(json.dumps(public_data), encoding="utf-8")

    ok, results = verify_validation_evidence_bundle(
        mode="release",
        release_audit=release_audit,
        public_install_audit=public_install,
    )

    assert ok is False
    sha_check = next(result for result in results if result["name"] == "release_public_sha_match")
    assert sha_check["status"] == "fail"
    assert sha_check["errors"] == [
        "release audit sha 'abc123' does not match public install sha 'other-sha'"
    ]


def test_validation_evidence_bundle_rejects_stale_release_sha(tmp_path: Path) -> None:
    release_audit = tmp_path / "release_audit.json"
    public_install = tmp_path / "public_install.json"
    release_audit.write_text(json.dumps(_release_audit_data()), encoding="utf-8")
    public_install.write_text(json.dumps(_public_install_audit_data()), encoding="utf-8")

    def fake_run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        if args == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, stdout="new-sha\n", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    ok, results = verify_validation_evidence_bundle(
        mode="release",
        repo_root=tmp_path,
        release_audit=release_audit,
        public_install_audit=public_install,
        run_command=fake_run,
    )

    assert ok is False
    sha_check = next(result for result in results if result["name"] == "release_public_sha_match")
    assert sha_check["status"] == "fail"
    assert "release audit sha 'abc123' does not match current HEAD 'new-sha'" in sha_check[
        "errors"
    ]
    assert "public install sha 'abc123' does not match current HEAD 'new-sha'" in sha_check[
        "errors"
    ]


def test_validation_evidence_bundle_rejects_stale_benchmark_progress_sha(
    tmp_path: Path,
) -> None:
    release_audit = tmp_path / "release_audit.json"
    public_install = tmp_path / "public_install.json"
    progress = tmp_path / "full_sweep_progress.json"
    gate_meta = tmp_path / "gate_meta.json"
    release_audit.write_text(json.dumps(_release_audit_data()), encoding="utf-8")
    public_install.write_text(json.dumps(_public_install_audit_data()), encoding="utf-8")
    gate_meta.write_text(json.dumps({"git_sha": "old-sha"}), encoding="utf-8")
    progress.write_text(
        json.dumps(
            {
                "suffix": "prepublish_20260519_054949",
                "gate_dir": "logs/benchmarks/prepublish_gate_20260519_054949",
                "code_sha": "old-sha",
                "worktree": "clean",
                "gate_meta_present": True,
                "gate_pass": True,
                "active_worker_count": 0,
                "public_performance_evidence": True,
                "locomo": {"completed": 1540, "total": 1540},
                "longmemeval": {"completed": 500, "total": 500},
                "beam": [
                    {"project": "beam_100k", "completed": 500, "total": 500},
                    {"project": "beam_500k", "completed": 500, "total": 500},
                    {"project": "beam_1m", "completed": 500, "total": 500},
                    {"project": "beam_10m", "completed": 500, "total": 500},
                ],
                "workers": [],
            }
        ),
        encoding="utf-8",
    )

    def fake_run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        if args == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, stdout="new-sha\n", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    ok, results = verify_validation_evidence_bundle(
        mode="release",
        repo_root=tmp_path,
        release_audit=release_audit,
        public_install_audit=public_install,
        benchmark_gate_meta=gate_meta,
        full_sweep_progress=progress,
        require_public_benchmark=True,
        run_command=fake_run,
    )

    assert ok is False
    gate_check = next(result for result in results if result["name"] == "benchmark_gate_meta")
    progress_check = next(result for result in results if result["name"] == "full_sweep_progress")
    assert "benchmark gate git_sha 'old-sha' does not match current HEAD 'new-sha'" in gate_check[
        "errors"
    ]
    assert (
        "full-sweep progress code_sha 'old-sha' does not match current HEAD 'new-sha'"
        in progress_check["errors"]
    )


def test_validation_evidence_bundle_rejects_stubbed_public_install(
    tmp_path: Path,
) -> None:
    release_audit = tmp_path / "release_audit.json"
    public_install = tmp_path / "public_install.json"
    release_audit.write_text(json.dumps(_release_audit_data()), encoding="utf-8")
    public_install.write_text(
        json.dumps(_public_install_audit_data(embedded_evidence=False)),
        encoding="utf-8",
    )

    ok, results = verify_validation_evidence_bundle(
        mode="release",
        release_audit=release_audit,
        public_install_audit=public_install,
    )

    assert ok is False
    assert results[0]["status"] == "ok"
    assert results[1]["status"] == "fail"
    assert any("missing CLI help evidence" in error for error in results[1]["errors"])
    assert "mcp_stdio_smoke evidence is missing" in results[1]["errors"]


def test_full_sweep_progress_json_preserves_empty_worker_array() -> None:
    script = _read("tools/check_full_sweep_progress.ps1")

    assert "workers = @($workerPids)" in script
    assert "if ($null -eq $workerPids)" in script
    assert "$summary | ConvertTo-Json -Depth 6" in script
    assert "current_sha_matches = $currentShaMatches" in script
    assert "gate_status = $gateStatus" in script
    assert "benchmark_evidence_verified = $benchmarkEvidenceVerified" in script
    assert "$gatePublicEvidence -and $benchmarkEvidenceVerified" in script
    assert "resume_command = $resumeCommand" in script


def test_full_sweep_progress_verifier_accepts_monitoring_schema() -> None:
    data = {
        "suffix": "prepublish_20260519_054949",
        "gate_dir": "logs/benchmarks/prepublish_gate_20260519_054949",
        "code_sha": "abc",
        "current_sha": "abc",
        "current_sha_matches": False,
        "worktree": "dirty",
        "gate_status": "running",
        "gate_meta_present": True,
        "gate_pass": False,
        "benchmark_evidence_verified": False,
        "active_worker_count": 0,
        "public_performance_evidence": False,
        "locomo": {"completed": 0, "total": 1540},
        "longmemeval": {"completed": 0, "total": 500},
        "beam": [
            {"project": "beam_100k", "completed": 0, "total": 500},
            {"project": "beam_500k", "completed": 0, "total": 500},
            {"project": "beam_1m", "completed": 0, "total": 500},
            {"project": "beam_10m", "completed": 0, "total": 500},
        ],
        "workers": [],
    }

    ok, errors = verify_full_sweep_progress(data)

    assert ok is True
    assert errors == []


def test_full_sweep_progress_verifier_rejects_incomplete_public_evidence() -> None:
    data = {
        "suffix": "prepublish_20260519_054949",
        "gate_dir": "logs/benchmarks/prepublish_gate_20260519_054949",
        "code_sha": "abc",
        "current_sha": "abc",
        "current_sha_matches": False,
        "worktree": "dirty",
        "gate_status": "failed",
        "gate_meta_present": True,
        "gate_pass": False,
        "benchmark_evidence_verified": False,
        "active_worker_count": 0,
        "public_performance_evidence": False,
        "locomo": {"completed": 0, "total": 1540},
        "longmemeval": {"completed": 0, "total": 500},
        "beam": [
            {"project": "beam_100k", "completed": 0, "total": 500},
            {"project": "beam_500k", "completed": 0, "total": 500},
            {"project": "beam_1m", "completed": 0, "total": 500},
            {"project": "beam_10m", "completed": 0, "total": 500},
        ],
        "workers": [],
    }

    ok, errors = verify_full_sweep_progress(data, require_public_evidence=True)

    assert ok is False
    assert "public_performance_evidence is not true" in errors
    assert "benchmark_evidence_verified is not true" in errors
    assert "gate_pass is not true" in errors
    assert "current_sha_matches is not true" in errors
    assert "worktree is 'dirty', not 'clean'" in errors
    assert "benchmark result counts are incomplete" in errors


def test_objective_audit_loads_windows_powershell_redirected_json(tmp_path: Path) -> None:
    path = tmp_path / "progress.json"
    path.write_text('{"status": "ok"}', encoding="utf-16")

    data, errors = _load_json(path, "full-sweep progress")

    assert errors == []
    assert data == {"status": "ok"}


def test_progress_and_bundle_verifiers_load_windows_powershell_redirected_json(
    tmp_path: Path,
) -> None:
    path = tmp_path / "progress.json"
    path.write_text('{"status": "ok"}', encoding="utf-16")

    assert load_full_sweep_progress_json(str(path)) == {"status": "ok"}
    assert load_bundle_json(path, "full-sweep progress") == {"status": "ok"}


def test_prepublish_gate_preflights_live_benchmark_services() -> None:
    script = _read("tools/prepublish_benchmark_gate.ps1")

    assert "SkipServicePreflight" in script
    assert "PreflightOnly" in script
    assert "PREPUBLISH PREFLIGHT" in script
    assert "http://localhost:11434/v1" in script
    assert "http://localhost:8000" in script
    assert "Test-HttpEndpoint -Name \"model endpoint\"" in script
    assert "Test-MapUDatabase" in script
    assert "mapu database" in script
    assert "skip_service_preflight" in script
    assert "preflight_only" in script
    assert "preflight_status" in script
    assert "preflight_checks" in script
    assert "benchmark_mem0_host_arg" in script
    assert "BenchmarkMem0HostArg" in script
    assert '"-BenchmarkMem0HostArg", $benchmarkMem0HostArg' in script
    assert "PREPUBLISH BENCHMARK GATE: PREFLIGHT ONLY" in script
    assert "gate metadata: $gateMeta" in script


def test_prepublish_gate_self_verifies_before_pass() -> None:
    script = _read("tools/prepublish_benchmark_gate.ps1")

    assert "verify_prepublish_benchmark_evidence.py" in script
    assert "& $python $verifyBenchmarkEvidence $gateMeta 1> $benchmarkVerifierOut" in script
    assert "--require-public-evidence-labels" in script
    assert '$meta["public_performance_evidence"] = $true' in script
    assert '$meta["benchmark_evidence_verified"] = $true' in script
    assert "Benchmark evidence verifier failed" in script
    assert script.index("verify_prepublish_benchmark_evidence.py") < script.index(
        "PREPUBLISH BENCHMARK GATE: PASS"
    )


def test_release_surface_audit_has_explicit_local_dev_skips() -> None:
    script = _read("tools/release_surface_audit.ps1")

    assert "[switch]$SkipDocker" in script
    assert "[switch]$AllowDirtyWorktree" in script
    assert "[switch]$InstallFromWorkingTree" in script
    assert "[int]$McpE2EToolTimeoutSeconds = 60" in script
    assert "--tool-timeout $McpE2EToolTimeoutSeconds" in script
    assert "function Add-Skip" in script
    assert "function Write-JsonUtf8NoBom" in script
    assert "New-Object System.Text.UTF8Encoding -ArgumentList $false" in script
    assert "[System.IO.File]::WriteAllText" in script
    assert "return ,$items" in script
    assert "Set-Content -LiteralPath $OutputJson -Encoding UTF8" not in script
    assert "local development audit only" in script
    assert "skip_docker" in script
    assert "allow_dirty_worktree" in script
    assert "install_from_working_tree" in script
    assert "release_ready_evidence" in script
    assert "evidence_scope" in script
    assert "checks_skipped = @($skips)" in script
    assert "docker command is available for compose verification (-SkipDocker set" in script
    assert "git worktree is clean (-AllowDirtyWorktree set" in script
    assert "Using current working tree as install source" in script
    assert "benchmark-specific code is isolated from general runtime" in script
    assert "tools/verify_benchmark_isolation.py" in script
    assert "benchmark isolation verifier failed" in script
    assert "tools/worktree_fingerprint.py" in script
    assert "installed_doctor_evidence" in script
    assert "mapu doctor --json" in script
    assert "installed doctor status is not ok" in script


def test_release_audit_evidence_verifier_rejects_skipped_release_checks() -> None:
    data = {
        "sha": "abc123",
        "passed": True,
        "skip_fresh_install": True,
        "skip_docker": True,
        "allow_dirty_worktree": True,
        "install_from_working_tree": True,
        "release_ready_evidence": False,
        "evidence_scope": "scoped",
        "checks_passed": list(RELEASE_AUDIT_REQUIRED_CHECKS),
        "checks_failed": [],
        "checks_skipped": ["docker command is available"],
        "smoke_evidence": [
            _release_smoke("CLI e2e"),
            _release_smoke("MCP stdio e2e"),
        ],
    }

    ok, errors = verify_release_audit_evidence(
        data,
        mode="release",
        require_cli_e2e=True,
        require_mcp_e2e=True,
    )

    assert ok is False
    assert any("release_ready_evidence" in error for error in errors)
    assert any("skipped checks" in error for error in errors)
    assert any("skip_docker=true" in error for error in errors)
    assert any("install_from_working_tree=true" in error for error in errors)


def test_release_audit_evidence_verifier_accepts_scoped_local_dev_evidence() -> None:
    data = {
        "sha": "abc123",
        "passed": True,
        "skip_fresh_install": True,
        "skip_docker": True,
        "allow_dirty_worktree": True,
        "release_ready_evidence": False,
        "evidence_scope": "scoped",
        "worktree_status_porcelain": [" M README.md"],
        "worktree_dirty_path_count": 1,
        "worktree_fingerprint_sha256": _worktree_fingerprint([" M README.md"]),
        "checks_passed": list(RELEASE_AUDIT_REQUIRED_CHECKS),
        "checks_failed": [],
        "checks_skipped": ["docker command is available"],
        "smoke_evidence": [
            _release_smoke("CLI e2e"),
            _release_smoke("MCP stdio e2e"),
        ],
    }

    ok, errors = verify_release_audit_evidence(
        data,
        mode="local-dev",
        require_cli_e2e=True,
        require_mcp_e2e=True,
    )

    assert ok is True
    assert errors == []


def test_release_audit_evidence_verifier_requires_benchmark_isolation_check() -> None:
    data = {
        "sha": "abc123",
        "passed": True,
        "release_ready_evidence": True,
        "evidence_scope": "release",
        "checks_passed": [],
        "checks_failed": [],
        "checks_skipped": [],
        "installed_doctor_evidence": _release_doctor_evidence(),
        "smoke_evidence": [
            _release_smoke("CLI e2e"),
            _release_smoke("MCP stdio e2e"),
        ],
    }

    ok, errors = verify_release_audit_evidence(
        data,
        mode="release",
        require_cli_e2e=True,
        require_mcp_e2e=True,
    )

    assert ok is False
    assert errors == [
        "audit missing required passed checks: "
        "['benchmark-specific code is isolated from general runtime']"
    ]


def test_release_audit_evidence_verifier_rejects_missing_required_smoke() -> None:
    data = {
        "sha": "abc123",
        "passed": True,
        "release_ready_evidence": True,
        "evidence_scope": "release",
        "checks_passed": list(RELEASE_AUDIT_REQUIRED_CHECKS),
        "checks_failed": [],
        "checks_skipped": [],
        "installed_doctor_evidence": _release_doctor_evidence(),
        "smoke_evidence": [_release_smoke("CLI e2e")],
    }

    ok, errors = verify_release_audit_evidence(
        data,
        mode="release",
        require_cli_e2e=True,
        require_mcp_e2e=True,
    )

    assert ok is False
    assert errors == ["missing passing MCP stdio e2e smoke evidence"]


def test_release_audit_evidence_verifier_rejects_stubbed_smoke_evidence() -> None:
    data = {
        "sha": "abc123",
        "passed": True,
        "release_ready_evidence": True,
        "evidence_scope": "release",
        "checks_passed": list(RELEASE_AUDIT_REQUIRED_CHECKS),
        "checks_failed": [],
        "checks_skipped": [],
        "installed_doctor_evidence": _release_doctor_evidence(),
        "smoke_evidence": [
            {"kind": "CLI e2e", "status": "ok"},
            _release_smoke("MCP stdio e2e"),
        ],
    }

    ok, errors = verify_release_audit_evidence(
        data,
        mode="release",
        require_cli_e2e=True,
        require_mcp_e2e=True,
    )

    assert ok is False
    assert errors == [
        "CLI e2e smoke evidence missing non-empty command_line",
        "CLI e2e smoke evidence missing corpus_id",
        "CLI e2e smoke evidence missing mapu_version",
        "CLI e2e smoke evidence missing git_sha",
        "CLI e2e smoke evidence missing required_checks",
    ]


def test_release_audit_evidence_verifier_rejects_weak_mcp_workflow_checks() -> None:
    data = _release_audit_data()
    smoke = data["smoke_evidence"]
    assert isinstance(smoke, list)
    assert isinstance(smoke[1], dict)
    smoke[1]["required_checks"] = {
        "ingest_ok": True,
        "query_answer_nonempty": True,
        "delete_ok": True,
    }

    ok, errors = verify_release_audit_evidence(
        data,
        mode="release",
        require_cli_e2e=True,
        require_mcp_e2e=True,
    )

    assert ok is False
    assert (
        "MCP stdio e2e smoke evidence missing required check names: "
        "['create_ok', 'contribute_ok', 'review_ok', 'query_has_next_steps', "
        "'handoff_has_protocol', 'handoff_has_priority_actions', "
        "'learning_feedback_logged', 'activity_written']"
    ) in errors


def test_release_audit_evidence_verifier_rejects_incomplete_mcp_tool_surface() -> None:
    data = _release_audit_data()
    smoke = data["smoke_evidence"]
    assert isinstance(smoke, list)
    assert isinstance(smoke[1], dict)
    mcp_smoke = smoke[1]
    tools = mcp_smoke["tools"]
    assert isinstance(tools, list)
    mcp_smoke["tools"] = [tool for tool in tools if tool != "handoff_context"]
    mcp_smoke["tool_count"] = len(mcp_smoke["tools"])

    ok, errors = verify_release_audit_evidence(
        data,
        mode="release",
        require_cli_e2e=True,
        require_mcp_e2e=True,
    )

    assert ok is False
    assert (
        "MCP stdio e2e smoke evidence tool_count is below required tool count "
        f"{len(RELEASE_AUDIT_REQUIRED_MCP_TOOLS)}"
    ) in errors
    assert (
        "MCP stdio e2e smoke evidence tools missing required tools: ['handoff_context']"
        in errors
    )


def test_release_audit_evidence_verifier_rejects_missing_installed_doctor() -> None:
    data = _release_audit_data()
    del data["installed_doctor_evidence"]

    ok, errors = verify_release_audit_evidence(
        data,
        mode="release",
        require_cli_e2e=True,
        require_mcp_e2e=True,
    )

    assert ok is False
    assert "installed_doctor_evidence is missing" in errors


def test_release_audit_evidence_verifier_rejects_smoke_sha_mismatch() -> None:
    data = _release_audit_data()
    smoke = data["smoke_evidence"]
    assert isinstance(smoke, list)
    assert isinstance(smoke[0], dict)
    smoke[0]["git_sha"] = "other-sha"

    ok, errors = verify_release_audit_evidence(
        data,
        mode="release",
        require_cli_e2e=True,
        require_mcp_e2e=True,
    )

    assert ok is False
    assert "CLI e2e smoke evidence git_sha does not match audit sha" in errors


def test_release_audit_evidence_verifier_requires_audit_sha() -> None:
    data = _release_audit_data()
    del data["sha"]

    ok, errors = verify_release_audit_evidence(
        data,
        mode="release",
        require_cli_e2e=True,
        require_mcp_e2e=True,
    )

    assert ok is False
    assert "audit sha is missing" in errors


def test_prepublish_benchmark_evidence_verifier_accepts_complete_gate(tmp_path: Path) -> None:
    gate_dir = tmp_path / "prepublish_gate"
    gate_dir.mkdir()
    lane_dir = tmp_path / "parallel_prepublish"
    lane_dir.mkdir()
    code_identity = gate_dir / "code_identity.txt"
    code_identity.write_text("sha=abc\nworktree=clean\n", encoding="utf-8")
    leaderboard = gate_dir / "leaderboard.txt"
    leaderboard.write_text(
        "\n".join(
            [
                "=== Full Sweep Leaderboard Comparison ===",
                "LoCoMo ours file: locomo_results.json",
                "LongMemEval ours file: longmemeval_results.json",
                "BEAM 100K ours file: beam_100k_results.json",
                "BEAM 500K ours file: beam_500k_results.json",
                "BEAM 1M ours file: beam_1m_results.json",
                "BEAM 10M ours file: beam_10m_results.json",
            ]
        ),
        encoding="utf-8",
    )
    sweep_out = gate_dir / "sweep.out.log"
    sweep_out.write_text("ok\n", encoding="utf-8")
    sweep_err = gate_dir / "sweep.err.log"
    sweep_err.write_text("", encoding="utf-8")
    gate_meta_path = gate_dir / "gate_meta.json"
    gate_meta = {
        "gate_pass": True,
        "git_sha": "abc",
        "public_performance_evidence": True,
        "benchmark_evidence_verified": True,
        "preflight_only": False,
        "skip_service_preflight": False,
        "preflight_status": "ok",
        "preflight_checks": {
            "model endpoint": {"status": "ok"},
            "mapu database": {"status": "ok"},
        },
        "code_identity": str(code_identity),
        "leaderboard_report": str(leaderboard),
        "lane_artifact_dir": str(lane_dir),
        "sweep_out_log": str(sweep_out),
        "sweep_err_log": str(sweep_err),
    }

    ok, errors = verify_prepublish_benchmark_evidence(
        gate_meta,
        gate_meta_path=gate_meta_path,
        require_public_evidence_labels=True,
    )

    assert ok is True
    assert errors == []


def test_prepublish_benchmark_evidence_verifier_requires_public_labels(
    tmp_path: Path,
) -> None:
    gate_dir = tmp_path / "prepublish_gate"
    gate_dir.mkdir()
    lane_dir = tmp_path / "parallel_prepublish"
    lane_dir.mkdir()
    code_identity = gate_dir / "code_identity.txt"
    code_identity.write_text("sha=abc\nworktree=clean\n", encoding="utf-8")
    leaderboard = gate_dir / "leaderboard.txt"
    leaderboard.write_text(
        "\n".join(
            [
                "=== Full Sweep Leaderboard Comparison ===",
                "LoCoMo ours file: locomo_results.json",
                "LongMemEval ours file: longmemeval_results.json",
                "BEAM 100K ours file: beam_100k_results.json",
                "BEAM 500K ours file: beam_500k_results.json",
                "BEAM 1M ours file: beam_1m_results.json",
                "BEAM 10M ours file: beam_10m_results.json",
            ]
        ),
        encoding="utf-8",
    )
    sweep_out = gate_dir / "sweep.out.log"
    sweep_out.write_text("ok\n", encoding="utf-8")
    sweep_err = gate_dir / "sweep.err.log"
    sweep_err.write_text("", encoding="utf-8")
    gate_meta = {
        "gate_pass": True,
        "git_sha": "abc",
        "public_performance_evidence": False,
        "benchmark_evidence_verified": False,
        "preflight_only": False,
        "skip_service_preflight": False,
        "preflight_status": "ok",
        "preflight_checks": {"model endpoint": {"status": "ok"}},
        "code_identity": str(code_identity),
        "leaderboard_report": str(leaderboard),
        "lane_artifact_dir": str(lane_dir),
        "sweep_out_log": str(sweep_out),
        "sweep_err_log": str(sweep_err),
    }

    ok, errors = verify_prepublish_benchmark_evidence(
        gate_meta,
        gate_meta_path=gate_dir / "gate_meta.json",
        require_public_evidence_labels=True,
    )

    assert ok is False
    assert "public_performance_evidence is not true" in errors
    assert "benchmark_evidence_verified is not true" in errors


def test_prepublish_benchmark_evidence_verifier_rejects_incomplete_leaderboard(
    tmp_path: Path,
) -> None:
    gate_dir = tmp_path / "prepublish_gate"
    gate_dir.mkdir()
    lane_dir = tmp_path / "parallel_prepublish"
    lane_dir.mkdir()
    code_identity = gate_dir / "code_identity.txt"
    code_identity.write_text("sha=abc\nworktree=clean\n", encoding="utf-8")
    leaderboard = gate_dir / "leaderboard.txt"
    leaderboard.write_text(
        "=== Full Sweep Leaderboard Comparison ===\nLoCoMo ours file: MISSING\n",
        encoding="utf-8",
    )
    sweep_out = gate_dir / "sweep.out.log"
    sweep_out.write_text("ok\n", encoding="utf-8")
    sweep_err = gate_dir / "sweep.err.log"
    sweep_err.write_text("", encoding="utf-8")
    gate_meta = {
        "gate_pass": True,
        "git_sha": "different",
        "preflight_only": False,
        "skip_service_preflight": False,
        "preflight_status": "ok",
        "preflight_checks": {"model endpoint": {"status": "ok"}},
        "code_identity": str(code_identity),
        "leaderboard_report": str(leaderboard),
        "lane_artifact_dir": str(lane_dir),
        "sweep_out_log": str(sweep_out),
        "sweep_err_log": str(sweep_err),
    }

    ok, errors = verify_prepublish_benchmark_evidence(
        gate_meta,
        gate_meta_path=gate_dir / "gate_meta.json",
    )

    assert ok is False
    assert "code_identity sha 'abc' does not match gate_meta git_sha 'different'" in errors
    assert "leaderboard_report missing section marker: LongMemEval ours file:" in errors
    assert "leaderboard_report contains MISSING benchmark outputs" in errors


def test_prepublish_benchmark_evidence_verifier_rejects_smoke_or_dirty_gate(
    tmp_path: Path,
) -> None:
    gate_dir = tmp_path / "prepublish_gate"
    gate_dir.mkdir()
    code_identity = gate_dir / "code_identity.txt"
    code_identity.write_text("sha=abc\nworktree=dirty\n", encoding="utf-8")
    leaderboard = tmp_path / "leaderboard.txt"
    leaderboard.write_text("not colocated\n", encoding="utf-8")
    gate_meta = {
        "gate_pass": False,
        "preflight_only": True,
        "skip_service_preflight": True,
        "preflight_status": "skipped",
        "preflight_checks": {},
        "code_identity": str(code_identity),
        "leaderboard_report": str(leaderboard),
        "lane_artifact_dir": str(tmp_path / "missing_lane_dir"),
        "sweep_out_log": str(gate_dir / "missing.out.log"),
        "sweep_err_log": str(gate_dir / "missing.err.log"),
    }

    ok, errors = verify_prepublish_benchmark_evidence(
        gate_meta,
        gate_meta_path=gate_dir / "gate_meta.json",
    )

    assert ok is False
    assert "gate_pass is not true" in errors
    assert "preflight_only is true" in errors
    assert "skip_service_preflight is true" in errors
    assert "code_identity worktree is 'dirty', not 'clean'" in errors
    assert "leaderboard_report is not in the same directory as gate_meta.json" in errors


def test_sequential_full_sweep_keeps_per_lane_logs_and_metadata() -> None:
    script = _read("tools/run_full_leaderboard_sweeps.ps1")

    assert "Lane artifact directory" in script
    assert "Write-LaneMetadata" in script
    assert ".meta.json" in script
    assert ".out.log" in script
    assert ".err.log" in script
    assert "BenchmarkMem0HostArg" in script
    assert '"--mem0-host", $BenchmarkMem0HostArg' in script
    assert '"--mem0-host", "http://localhost:8000"' not in script
    assert "[string]$AnswererModel" in script
    assert "[string]$ModelBaseUrl" in script
    assert "[string]$ModelLabel" in script
    assert "mapu_fullsweep_${ModelLabel}_locomo_$projectSuffix" in script
    assert "GetTempFileName" not in script
    assert "Remove-Item -LiteralPath $tmpOut" not in script


def test_parallel_full_sweep_writes_failure_metadata() -> None:
    script = _read("tools/run_full_leaderboard_sweeps_parallel.ps1")

    assert "Write-LaneMetadata" in script
    assert "last_progress_at" in script
    assert "stdout_bytes" in script
    assert "stderr_bytes" in script
    assert "BenchmarkMem0HostArg" in script
    assert '"--mem0-host", $BenchmarkMem0HostArg' in script
    assert '"--mem0-host", "http://localhost:8000"' not in script
    assert "[string]$AnswererModel" in script
    assert "[string]$ModelBaseUrl" in script
    assert "[string]$ModelLabel" in script
    assert "mapu_fullsweep_${ModelLabel}_longmemeval_$projectSuffix" in script
    assert "exited with code $exitCodeLabel" in script
    assert "exceeded idle timeout" in script
    assert "exceeded lane timeout" in script


def test_full_sweep_runners_support_explicit_resume() -> None:
    sequential = _read("tools/run_full_leaderboard_sweeps.ps1")
    parallel = _read("tools/run_full_leaderboard_sweeps_parallel.ps1")

    for script in (sequential, parallel):
        assert "[switch]$Resume" in script
        assert '"--resume"' in script
        assert '$job.Args = @($job.Args) + "--resume"' in script
        assert "Resume existing benchmark checkpoints" in script


def test_mem0_benchmark_wrapper_requires_nonblank_answer_contract() -> None:
    script = _read("tools/run_mem0_benchmark_with_mapu.py")

    assert "_patch_answer_prompt_contract(run_module)" in script
    assert "_suppress_printed_reasoning(prompt)" in script
    assert "_extract_fact_hints(prompt)" in script
    assert "DIRECT FACT HINTS FROM RETRIEVED MEMORIES" in script
    assert "OUTPUT FORMAT REQUIREMENT" in script
    assert "Use the retrieved memories first." in script
    assert "fact_hint" in script
    assert "do not answer that the " in script
    assert "information is insufficient" in script
    assert "Preserve qualifiers from direct evidence" in script
    assert "unless the question explicitly asks for a" in script
    assert "with the full duration phrase" in script
    assert "Only say the information is insufficient" in script
    assert "Override any earlier instruction to print <mem_thinking> tags." in script
    assert "use these internal checks silently" in script
    assert "ANSWER: <your concise answer>" in script
    assert "Never leave ANSWER blank." in script
    assert "get_answer_generation_prompt" in script
    assert "get_beam_answer_generation_prompt" in script


def test_prepublish_gate_requires_checked_resume_suffix() -> None:
    script = _read("tools/prepublish_benchmark_gate.ps1")
    launcher = _read("tools/start_prepublish_benchmark_gate.ps1")

    assert "[string]$ProjectSuffix" in script
    assert "[switch]$Resume" in script
    assert "ProjectSuffix must be blank or match prepublish_yyyyMMdd_HHmmss" in script
    assert "Resume requires -ProjectSuffix prepublish_yyyyMMdd_HHmmss" in script
    assert "existing code sha" in script
    assert "existing worktree" in script
    assert "$sweepArgs += \"-Resume\"" in script
    assert "-Resume:$($Resume.IsPresent)" not in script
    assert "project_suffix" in script
    assert "answerer_model" in script
    assert "model_api_key_present" in script
    assert "answer_generation_scope" in script
    assert "resume = $Resume.IsPresent" in script

    assert "[string]$ProjectSuffix" in launcher
    assert "[string]$AnswererModel" in launcher
    assert "[string]$ModelBaseUrl" in launcher
    assert "[string]$ModelLabel" in launcher
    assert "[switch]$Resume" in launcher
    assert "$gateProjectSuffix" in launcher
    assert '"-ProjectSuffix", $gateProjectSuffix' in launcher
    assert "prepublish_gate_launcher_${stamp}.json" in launcher
    assert "launcher_metadata" in launcher
    assert "progress_command" in launcher
    assert "-LauncherMetadata $launcherMeta -Json" in launcher
    assert "resume_command" in launcher
    assert "Resume requires -ProjectSuffix prepublish_yyyyMMdd_HHmmss" in launcher
    assert "Write-JsonUtf8NoBom -Data $meta -Path $launcherMeta" in launcher
    assert '$argList += "-Resume"' in launcher

    progress = _read("tools/check_full_sweep_progress.ps1")
    assert "[string]$LauncherMetadata = $env:MAPU_BENCH_LAUNCHER_METADATA" in progress
    assert "[string]$ModelLabel = $env:MAPU_BENCH_MODEL_LABEL" in progress
    assert 'Get-ChildItem "logs/benchmarks" -Filter "prepublish_gate_launcher_*.json"' in progress
    assert "project_suffix" in progress
    assert "model_label" in progress
    assert "launcher_metadata" in progress
    assert "launcher_pid" in progress
    assert "launcher_running" in progress
    assert "does not match launcher metadata project_suffix" in progress
    assert "[string]$launcherMeta.resume_command" in progress
