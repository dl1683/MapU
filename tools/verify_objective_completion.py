from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from tools.verify_benchmark_isolation import verify_benchmark_isolation
    from tools.verify_full_sweep_progress import verify_full_sweep_progress
    from tools.verify_prepublish_benchmark_evidence import verify_prepublish_benchmark_evidence
    from tools.verify_public_install_audit_evidence import verify_public_install_audit_evidence
    from tools.verify_release_audit_evidence import verify_release_audit_evidence
    from tools.worktree_fingerprint import current_worktree_fingerprint
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from verify_benchmark_isolation import verify_benchmark_isolation
    from verify_full_sweep_progress import verify_full_sweep_progress
    from verify_prepublish_benchmark_evidence import verify_prepublish_benchmark_evidence
    from verify_public_install_audit_evidence import verify_public_install_audit_evidence
    from verify_release_audit_evidence import verify_release_audit_evidence
    from worktree_fingerprint import current_worktree_fingerprint


RunCommand = Callable[[list[str], Path], subprocess.CompletedProcess[str]]
DEFAULT_BENCHMARK_GATE_META = Path("logs/benchmarks/latest/gate_meta.json")
_WORKTREE_SAMPLE_LIMIT = 12
_RELEASE_SLICE_ORDER = (
    "memory_quality_runtime",
    "cli_mcp_surface",
    "benchmark_evaluation",
    "release_evidence_tooling",
    "docs_claims",
    "tests",
    "project_config",
    "other_runtime",
)
_RELEASE_SLICE_MESSAGES = {
    "memory_quality_runtime": "memory runtime quality and continuity contracts",
    "cli_mcp_surface": "CLI and MCP operator surface",
    "benchmark_evaluation": "memory benchmark evaluation adapters and gates",
    "release_evidence_tooling": "release evidence and benchmark audit tooling",
    "docs_claims": "claim discipline and operator documentation",
    "tests": "test coverage for release and memory contracts",
    "project_config": "project configuration and local artifact policy",
    "other_runtime": "supporting runtime plumbing",
}


@dataclass(frozen=True)
class AuditCheck:
    name: str
    status: str
    required: bool
    evidence: str | None = None
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChecklistItem:
    requirement: str
    artifacts: tuple[str, ...]
    verifier: str
    check_names: tuple[str, ...]
    status: str
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class BlockerCategory:
    category: str
    label: str
    next_action: str
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class PublicationDelta:
    status: str
    local_required_tools_present: bool | None
    public_required_tools_present: bool | None
    local_doctor_available: bool | None
    public_doctor_available: bool | None
    local_doctor_required_tools_present: bool | None
    public_doctor_required_tools_present: bool | None
    local_tool_count: int | None
    public_tool_count: int | None
    locally_present_public_missing_tools: tuple[str, ...]
    public_missing_required_tools: tuple[str, ...]
    note: str


def _run_command(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    except OSError as exc:
        return subprocess.CompletedProcess(
            args,
            127,
            stdout="",
            stderr=f"{args[0]} command unavailable: {exc}",
        )


def _load_json(path: Path, label: str) -> tuple[dict[str, Any] | None, list[str]]:
    if not path.exists():
        return None, [f"{label} evidence not found: {path}"]
    text: str | None = None
    encoding_errors: list[str] = []
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            text = path.read_text(encoding=encoding)
            break
        except UnicodeError as exc:
            encoding_errors.append(f"{encoding}: {exc}")
    if text is None:
        return None, [f"{label} evidence could not be decoded: {'; '.join(encoding_errors)}"]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, [f"{label} evidence is invalid JSON: {exc}"]
    if not isinstance(data, dict):
        return None, [f"{label} evidence must be a JSON object"]
    return data, []


def _resolve_repo_path(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _resolve_latest_benchmark_gate_meta(
    repo_root: Path,
    requested: Path,
    full_sweep_progress: Path | None = None,
) -> Path:
    requested_path = requested if requested.is_absolute() else repo_root / requested
    if requested_path.exists():
        return requested

    default_path = repo_root / DEFAULT_BENCHMARK_GATE_META
    if requested_path.resolve() != default_path.resolve():
        return requested

    if full_sweep_progress is not None:
        progress_path = (
            full_sweep_progress
            if full_sweep_progress.is_absolute()
            else repo_root / full_sweep_progress
        )
        progress, errors = _load_json(progress_path, "full-sweep progress")
        if not errors and progress is not None:
            gate_dir = progress.get("gate_dir")
            if isinstance(gate_dir, str) and gate_dir.strip():
                gate_meta = Path(gate_dir) / "gate_meta.json"
                return gate_meta if gate_meta.is_absolute() else repo_root / gate_meta

    benchmark_root = repo_root / "logs" / "benchmarks"
    candidates = sorted(
        benchmark_root.glob("prepublish_gate_*/gate_meta.json"),
        key=lambda path: path.parent.name,
        reverse=True,
    )
    if not candidates:
        return requested
    return candidates[0]


def _check_clean_worktree(repo_root: Path, run_command: RunCommand) -> AuditCheck:
    result = run_command(["git", "status", "--porcelain"], repo_root)
    if result.returncode != 0:
        return AuditCheck(
            name="clean_worktree",
            status="fail",
            required=True,
            errors=(result.stderr.strip() or "git status failed",),
        )
    dirty_lines = [line for line in result.stdout.splitlines() if line.strip()]
    if dirty_lines:
        return AuditCheck(
            name="clean_worktree",
            status="fail",
            required=True,
            errors=(f"worktree has {len(dirty_lines)} changed paths",),
        )
    return AuditCheck(name="clean_worktree", status="ok", required=True)


def _worktree_path_area(path: str) -> str:
    if path.startswith("src/"):
        return "source"
    if path.startswith("tests/"):
        return "tests"
    if path.startswith("tools/"):
        return "tools"
    if path.startswith("docs/"):
        return "docs"
    if path.startswith("logs/") or path.startswith("results/") or path.startswith(".tmp/"):
        return "runtime_artifacts"
    if "/" not in path and path.lower().endswith((".md", ".rst", ".txt")):
        return "root_docs"
    if "/" not in path and path in {"pyproject.toml", ".gitignore", ".gitattributes", "uv.lock"}:
        return "project_config"
    return "other"


def _worktree_release_slice(path: str) -> str:
    if path in {"README.md", "PUBLIC_RELEASE_AUDIT.md", "CLAIM_EVIDENCE_APPENDIX.md"}:
        return "docs_claims"
    if path.startswith("docs/") or path.endswith(".md"):
        return "docs_claims"
    if path.startswith("tests/"):
        return "tests"
    if path.startswith("src/mapu/evaluation/") or path in {
        "tools/ama_bench_harness.py",
        "tools/memoryarena_harness.py",
        "tools/memory_benchmark_score_gate.py",
        "tools/benchmark_memory_relex_compare.py",
        "tools/score_memory_retrieval_proxy.py",
    }:
        return "benchmark_evaluation"
    if path in {
        "src/mapu/cli.py",
        "src/mapu/mcp/server.py",
        "src/mapu/mcp/tool_contract.py",
        "src/mapu/client.py",
        "tools/cli_e2e_smoke.py",
        "tools/mcp_stdio_smoke.py",
        "tools/mcp_relex_smoke.py",
    }:
        return "cli_mcp_surface"
    if (
        path.startswith("src/mapu/query/")
        or path.startswith("src/mapu/investigation/")
        or path.startswith("src/mapu/repair/")
        or path.startswith("src/mapu/repos/")
        or path.startswith("src/mapu/models/")
        or path == "src/mapu/context_learning.py"
        or path.startswith("src/mapu/db/migrations/")
    ):
        return "memory_quality_runtime"
    if path.startswith("tools/") and (
        "audit" in path
        or "verify_" in path
        or "benchmark" in path
        or "sweep" in path
        or "leaderboard" in path
        or "fingerprint" in path
    ):
        return "release_evidence_tooling"
    if path in {".gitignore", ".gitattributes", "pyproject.toml", "uv.lock"}:
        return "project_config"
    return "other_runtime"


def _worktree_status_kind(status: str) -> str:
    if status == "??":
        return "untracked"
    if status == "!!":
        return "ignored"
    if "D" in status:
        return "deleted"
    if "R" in status:
        return "renamed"
    if "A" in status:
        return "added"
    if "M" in status:
        return "modified"
    return "other"


def _parse_porcelain_entry(line: str) -> tuple[str, str] | None:
    if len(line) < 4:
        return None
    status = line[:2]
    path = line[3:].strip()
    if " -> " in path:
        path = path.rsplit(" -> ", 1)[1]
    if not path:
        return None
    return status, path


def _worktree_summary(repo_root: Path, run_command: RunCommand) -> dict[str, Any]:
    result = run_command(["git", "status", "--porcelain=v1", "-uall"], repo_root)
    if result.returncode != 0:
        return {
            "status": "unavailable",
            "errors": [result.stderr.strip() or "git status --porcelain=v1 -uall failed"],
        }
    entries: list[dict[str, str]] = []
    by_area: dict[str, int] = {}
    by_status: dict[str, int] = {}
    release_slices: dict[str, dict[str, Any]] = {}
    changed_paths: list[str] = []
    for line in result.stdout.splitlines():
        parsed = _parse_porcelain_entry(line)
        if parsed is None:
            continue
        status, path = parsed
        changed_paths.append(path)
        area = _worktree_path_area(path)
        kind = _worktree_status_kind(status)
        release_slice = _worktree_release_slice(path)
        by_area[area] = by_area.get(area, 0) + 1
        by_status[kind] = by_status.get(kind, 0) + 1
        slice_data = release_slices.setdefault(
            release_slice,
            {"count": 0, "sample": [], "paths": []},
        )
        slice_data["count"] += 1
        slice_data["paths"].append(path)
        if len(slice_data["sample"]) < 5:
            slice_data["sample"].append(path)
        if len(entries) < _WORKTREE_SAMPLE_LIMIT:
            entries.append(
                {
                    "status": status,
                    "kind": kind,
                    "area": area,
                    "release_slice": release_slice,
                    "path": path,
                }
            )
    suggested_commit_plan = _suggested_commit_plan(release_slices)
    return {
        "status": "ok",
        "expanded_path_count": sum(by_area.values()),
        "by_area": dict(sorted(by_area.items())),
        "by_status": dict(sorted(by_status.items())),
        "release_slices": dict(sorted(release_slices.items())),
        "suggested_commit_plan": suggested_commit_plan,
        "commit_plan_integrity": _commit_plan_integrity(changed_paths, suggested_commit_plan),
        "sample": entries,
        "sample_limit": _WORKTREE_SAMPLE_LIMIT,
    }


def _suggested_commit_plan(release_slices: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    ordered_names = [
        name
        for name in _RELEASE_SLICE_ORDER
        if name in release_slices and int(release_slices[name].get("count", 0)) > 0
    ]
    ordered_names.extend(
        sorted(
            name
            for name, data in release_slices.items()
            if name not in ordered_names and int(data.get("count", 0)) > 0
        )
    )
    plan: list[dict[str, Any]] = []
    for index, name in enumerate(ordered_names, start=1):
        data = release_slices[name]
        paths = sorted(str(path) for path in data.get("paths", []) if isinstance(path, str))
        plan.append(
            {
                "order": index,
                "slice": name,
                "count": len(paths),
                "paths": paths,
                "suggested_commit_message": _RELEASE_SLICE_MESSAGES.get(
                    name,
                    name.replace("_", " "),
                ),
            }
        )
    return plan


def _commit_plan_integrity(
    changed_paths: list[str],
    commit_plan: list[dict[str, Any]],
) -> dict[str, Any]:
    changed = sorted(changed_paths)
    planned: list[str] = []
    for item in commit_plan:
        paths = item.get("paths")
        if not isinstance(paths, list):
            continue
        planned.extend(path for path in paths if isinstance(path, str))
    planned_counts = Counter(planned)
    duplicate_planned = sorted(path for path, count in planned_counts.items() if count > 1)
    missing = sorted(set(changed) - set(planned))
    unexpected = sorted(set(planned) - set(changed))
    ok = not duplicate_planned and not missing and not unexpected
    return {
        "status": "ok" if ok else "fail",
        "changed_path_count": len(changed),
        "planned_path_count": len(planned),
        "unique_planned_path_count": len(planned_counts),
        "slice_count": len(commit_plan),
        "duplicate_planned_paths": duplicate_planned,
        "missing_from_plan": missing,
        "unexpected_in_plan": unexpected,
    }


def _check_docker(repo_root: Path, run_command: RunCommand) -> AuditCheck:
    version = run_command(["docker", "--version"], repo_root)
    compose = run_command(["docker", "compose", "version"], repo_root)
    errors: list[str] = []
    if version.returncode != 0:
        errors.append(version.stderr.strip() or "docker --version failed")
    if compose.returncode != 0:
        errors.append(compose.stderr.strip() or "docker compose version failed")
    if errors:
        return AuditCheck(
            name="docker_available",
            status="fail",
            required=True,
            errors=tuple(errors),
        )
    return AuditCheck(
        name="docker_available",
        status="ok",
        required=True,
        evidence="\n".join(
            item.strip()
            for item in (version.stdout, compose.stdout)
            if item.strip()
        ),
    )


def _check_release_audit(path: Path) -> AuditCheck:
    data, errors = _load_json(path, "release audit")
    if errors or data is None:
        return AuditCheck("release_audit", "fail", True, str(path), tuple(errors))
    ok, verifier_errors = verify_release_audit_evidence(
        data,
        mode="release",
        require_cli_e2e=True,
        require_mcp_e2e=True,
    )
    return AuditCheck(
        "release_audit",
        "ok" if ok else "fail",
        True,
        str(path),
        tuple(verifier_errors),
    )


def _current_worktree_fingerprint(
    repo_root: Path,
    run_command: RunCommand,
) -> tuple[dict[str, Any] | None, list[str]]:
    return current_worktree_fingerprint(repo_root, run_command=run_command)


def _check_local_cli_mcp_audit(
    path: Path,
    repo_root: Path,
    run_command: RunCommand,
) -> AuditCheck:
    data, errors = _load_json(path, "local CLI/MCP audit")
    if errors or data is None:
        return AuditCheck("local_cli_mcp_evidence", "fail", True, str(path), tuple(errors))
    ok, verifier_errors = verify_release_audit_evidence(
        data,
        mode="local-dev",
        require_cli_e2e=True,
        require_mcp_e2e=True,
    )
    all_errors = list(verifier_errors)
    if data.get("allow_dirty_worktree") or data.get("install_from_working_tree"):
        current, current_errors = _current_worktree_fingerprint(repo_root, run_command)
        all_errors.extend(current_errors)
        if current is not None:
            for key in (
                "worktree_status_porcelain",
                "worktree_dirty_path_count",
                "worktree_fingerprint_sha256",
            ):
                if data.get(key) != current[key]:
                    all_errors.append(f"local CLI/MCP audit {key} does not match current worktree")
    ok = ok and not all_errors
    return AuditCheck(
        "local_cli_mcp_evidence",
        "ok" if ok else "fail",
        True,
        str(path),
        tuple(all_errors),
    )


def _check_public_install(path: Path) -> AuditCheck:
    data, errors = _load_json(path, "public install audit")
    if errors or data is None:
        return AuditCheck("public_install_audit", "fail", True, str(path), tuple(errors))
    ok, verifier_errors = verify_public_install_audit_evidence(data)
    return AuditCheck(
        "public_install_audit",
        "ok" if ok else "fail",
        True,
        str(path),
        tuple(verifier_errors),
    )


def _current_head_sha(repo_root: Path, run_command: RunCommand) -> str | None:
    result = run_command(["git", "rev-parse", "HEAD"], repo_root)
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha or None


def _check_release_public_sha_match(
    release_audit: Path,
    public_install: Path,
    repo_root: Path,
    run_command: RunCommand,
) -> AuditCheck:
    release_data, release_errors = _load_json(release_audit, "release audit")
    public_data, public_errors = _load_json(public_install, "public install audit")
    errors = [*release_errors, *public_errors]
    if release_data is not None and public_data is not None:
        release_sha = release_data.get("sha")
        public_sha = public_data.get("sha")
        if not isinstance(release_sha, str) or not release_sha.strip():
            errors.append("release audit sha is missing")
        if not isinstance(public_sha, str) or not public_sha.strip() or public_sha == "unknown":
            errors.append("public install sha is missing or unknown")
        if not errors and release_sha != public_sha:
            errors.append(
                f"release audit sha {release_sha!r} does not match "
                f"public install sha {public_sha!r}"
            )
        current_sha = _current_head_sha(repo_root, run_command)
        if current_sha:
            if isinstance(release_sha, str) and release_sha.strip() and release_sha != current_sha:
                errors.append(
                    f"release audit sha {release_sha!r} does not match current HEAD "
                    f"{current_sha!r}"
                )
            if (
                isinstance(public_sha, str)
                and public_sha.strip()
                and public_sha != "unknown"
                and public_sha != current_sha
            ):
                errors.append(
                    f"public install sha {public_sha!r} does not match current HEAD "
                    f"{current_sha!r}"
                )
    return AuditCheck(
        "release_public_sha_match",
        "ok" if not errors else "fail",
        True,
        f"{release_audit}, {public_install}",
        tuple(errors),
    )


def _check_benchmark_gate(gate_meta_path: Path) -> AuditCheck:
    data, errors = _load_json(gate_meta_path, "benchmark gate")
    if errors or data is None:
        return AuditCheck("public_benchmark_gate", "fail", True, str(gate_meta_path), tuple(errors))
    ok, verifier_errors = verify_prepublish_benchmark_evidence(
        data,
        gate_meta_path=gate_meta_path.resolve(),
        require_clean_worktree=True,
        require_public_evidence_labels=True,
    )
    return AuditCheck(
        "public_benchmark_gate",
        "ok" if ok else "fail",
        True,
        str(gate_meta_path),
        tuple(verifier_errors),
    )


def _check_full_sweep_progress(progress_path: Path) -> AuditCheck:
    data, errors = _load_json(progress_path, "full-sweep progress")
    if errors or data is None:
        return AuditCheck("full_sweep_progress", "fail", True, str(progress_path), tuple(errors))
    ok, verifier_errors = verify_full_sweep_progress(data, require_public_evidence=True)
    return AuditCheck(
        "full_sweep_progress",
        "ok" if ok else "fail",
        True,
        str(progress_path),
        tuple(verifier_errors),
    )


def _check_smoke_boundary(
    smoke_path: Path,
    repo_root: Path,
    run_command: RunCommand,
) -> AuditCheck:
    data, errors = _load_json(smoke_path, "benchmark smoke")
    if errors or data is None:
        return AuditCheck("benchmark_smoke_boundary", "fail", True, str(smoke_path), tuple(errors))
    if data.get("status") != "ok":
        errors.append("smoke status is not ok")
    if data.get("gate_status") not in (None, "ok"):
        errors.append("smoke gate_status is not ok")
    if data.get("smoke_only") is not True:
        errors.append("smoke_only is not true")
    if data.get("public_performance_evidence") is not False:
        errors.append("public_performance_evidence is not false")
    fingerprint_errors = data.get("worktree_fingerprint_errors")
    if fingerprint_errors:
        errors.append(f"benchmark smoke worktree fingerprint errors: {fingerprint_errors}")
    current, current_errors = _current_worktree_fingerprint(repo_root, run_command)
    errors.extend(current_errors)
    if current is not None:
        for key in (
            "worktree_status_porcelain",
            "worktree_dirty_path_count",
            "worktree_fingerprint_sha256",
        ):
            if data.get(key) != current[key]:
                errors.append(f"benchmark smoke {key} does not match current worktree")
    score_summary = data.get("score_summary")
    if not isinstance(score_summary, list) or not score_summary:
        errors.append("score_summary is missing or empty")
    else:
        for index, row in enumerate(score_summary):
            if not isinstance(row, dict):
                errors.append(f"score_summary[{index}] is not an object")
                continue
            if row.get("passed") is not True:
                errors.append(f"score_summary[{index}] did not pass")
            if not isinstance(row.get("metric_value"), (int, float)):
                errors.append(f"score_summary[{index}] missing numeric metric_value")
    return AuditCheck(
        "benchmark_smoke_boundary",
        "ok" if not errors else "fail",
        True,
        str(smoke_path),
        tuple(errors),
    )


def _check_benchmark_isolation(repo_root: Path) -> AuditCheck:
    ok, report = verify_benchmark_isolation(root=repo_root)
    violation_items = [
        *(
            item
            for item in report.get("violations", [])
            if isinstance(item, dict)
        ),
        *(
            item
            for item in report.get("evaluation_shortcut_violations", [])
            if isinstance(item, dict)
        ),
    ]
    errors = tuple(
        f"{item['path']}:{item['line']} matched {item['match']}"
        for item in violation_items
    )
    return AuditCheck(
        "benchmark_isolation",
        "ok" if ok else "fail",
        True,
        "tools/verify_benchmark_isolation.py --json",
        errors,
    )


def _check_continuity_replay_quality(path: Path) -> AuditCheck:
    data, errors = _load_json(path, "continuity replay")
    if errors or data is None:
        return AuditCheck("continuity_response_quality", "fail", True, str(path), tuple(errors))
    handoff_effect = data.get("handoff_effect")
    if not isinstance(handoff_effect, dict):
        errors.append("handoff_effect is missing")
    else:
        quality_gate = handoff_effect.get("response_quality_gate")
        if not isinstance(quality_gate, dict):
            errors.append("response_quality_gate is missing")
        else:
            if quality_gate.get("enabled") is not True:
                errors.append("response_quality_gate is not enabled")
            if quality_gate.get("passed") is not True:
                errors.append("response_quality_gate did not pass")
            required_count = quality_gate.get("required_action_count")
            if not isinstance(required_count, int) or required_count <= 0:
                errors.append("response_quality_gate required_action_count is not positive")
            pass_rate = quality_gate.get("pass_rate")
            min_pass_rate = quality_gate.get("required_min_pass_rate")
            if not isinstance(pass_rate, (int, float)):
                errors.append("response_quality_gate pass_rate is missing")
            if not isinstance(min_pass_rate, (int, float)):
                errors.append("response_quality_gate required_min_pass_rate is missing")
            if (
                isinstance(pass_rate, (int, float))
                and isinstance(min_pass_rate, (int, float))
                and pass_rate < min_pass_rate
            ):
                errors.append(
                    f"response_quality_gate pass_rate {pass_rate} below "
                    f"required_min_pass_rate {min_pass_rate}"
                )
    return AuditCheck(
        "continuity_response_quality",
        "ok" if not errors else "fail",
        True,
        str(path),
        tuple(errors),
    )


def _check_documentation(repo_root: Path) -> AuditCheck:
    required_docs = {
        "README.md": (
            "verify_objective_completion.py",
            "VALIDATION_EVIDENCE_MATRIX.md",
            "verify_validation_evidence_bundle.py",
        ),
        "PUBLIC_RELEASE_AUDIT.md": (
            "verify_release_audit_evidence.py",
            "verify_public_install_audit_evidence.py",
            "verify_prepublish_benchmark_evidence.py",
        ),
        "docs/VALIDATION_EVIDENCE_MATRIX.md": (
            "Objective completion audit",
            "Continuity replay response quality gate",
            "Public install audit",
            "Full public benchmark claim",
        ),
        "docs/CLI_OPERATOR_GUIDE.md": (
            "cli_e2e_smoke.py",
            "mcp_stdio_smoke.py",
        ),
    }
    errors: list[str] = []
    for relative_path, required_texts in required_docs.items():
        path = repo_root / relative_path
        if not path.exists():
            errors.append(f"documentation file missing: {relative_path}")
            continue
        text = path.read_text(encoding="utf-8-sig")
        missing = [value for value in required_texts if value not in text]
        if missing:
            errors.append(f"{relative_path} missing required text: {missing}")
    return AuditCheck(
        "documentation",
        "ok" if not errors else "fail",
        True,
        ", ".join(required_docs),
        tuple(errors),
    )


def _check_by_name(checks: list[AuditCheck]) -> dict[str, AuditCheck]:
    return {check.name: check for check in checks}


def _checklist_status(
    check_lookup: dict[str, AuditCheck],
    check_names: tuple[str, ...],
) -> tuple[str, tuple[str, ...]]:
    errors = tuple(
        error
        for name in check_names
        for error in check_lookup[name].errors
        if check_lookup[name].status != "ok"
    )
    status = "ok" if all(check_lookup[name].status == "ok" for name in check_names) else "fail"
    return status, errors


def _build_prompt_to_artifact_checklist(checks: list[AuditCheck]) -> list[ChecklistItem]:
    check_lookup = _check_by_name(checks)

    def item(
        *,
        requirement: str,
        artifacts: tuple[str, ...],
        verifier: str,
        check_names: tuple[str, ...],
    ) -> ChecklistItem:
        status, errors = _checklist_status(check_lookup, check_names)
        return ChecklistItem(
            requirement=requirement,
            artifacts=artifacts,
            verifier=verifier,
            check_names=check_names,
            status=status,
            errors=errors,
        )

    return [
        item(
            requirement="working flawlessly with actual CLI systems",
            artifacts=(".tmp/release_surface_audit_summary.json", "logs/*_smoke_last.json"),
            verifier=(
                "tools/verify_release_audit_evidence.py --mode local-dev "
                "--require-cli-e2e --require-mcp-e2e"
            ),
            check_names=("local_cli_mcp_evidence",),
        ),
        item(
            requirement="general-purpose agent-memory quality is verified beyond benchmarks",
            artifacts=("results/continuity_replay_harness.json",),
            verifier=(
                "tools/continuity_replay_harness.py --require-response-quality-gate "
                "and objective replay-quality audit"
            ),
            check_names=("continuity_response_quality",),
        ),
        item(
            requirement="public install works from actual released code",
            artifacts=(".tmp/public_github_install_audit_summary.json",),
            verifier="tools/verify_public_install_audit_evidence.py",
            check_names=("public_install_audit", "release_public_sha_match"),
        ),
        item(
            requirement="release hygiene is public-ready",
            artifacts=("git status --porcelain", "docker --version", "docker compose version"),
            verifier="tools/release_surface_audit.ps1 without local-only skip switches",
            check_names=("clean_worktree", "docker_available", "release_audit"),
        ),
        item(
            requirement="public benchmark performance claims are backed by public evidence",
            artifacts=("logs/benchmarks/<gate>/gate_meta.json", ".tmp/full_sweep_progress.json"),
            verifier=(
                "tools/verify_prepublish_benchmark_evidence.py and "
                "tools/verify_full_sweep_progress.py --require-public-evidence"
            ),
            check_names=("public_benchmark_gate", "full_sweep_progress"),
        ),
        item(
            requirement="benchmark performance does not rely on benchmark-specific shortcuts",
            artifacts=(
                ".tmp/benchmark-live-smoke/smoke_report.json",
                "tools/verify_benchmark_isolation.py --json",
            ),
            verifier=(
                "smoke_only/public_performance_evidence boundary and direct "
                "source-isolation audit"
            ),
            check_names=("benchmark_smoke_boundary", "benchmark_isolation"),
        ),
        item(
            requirement="very good documentation",
            artifacts=(
                "README.md",
                "PUBLIC_RELEASE_AUDIT.md",
                "docs/VALIDATION_EVIDENCE_MATRIX.md",
                "docs/CLI_OPERATOR_GUIDE.md",
            ),
            verifier="documentation presence and required-command references",
            check_names=("documentation",),
        ),
    ]


_BLOCKER_CATEGORY_BY_CHECK = {
    "clean_worktree": "worktree_state",
    "docker_available": "local_environment",
    "local_cli_mcp_evidence": "local_evidence_freshness",
    "release_audit": "release_readiness",
    "public_install_audit": "publication_state",
    "release_public_sha_match": "publication_state",
    "public_benchmark_gate": "public_benchmark_evidence",
    "full_sweep_progress": "public_benchmark_evidence",
    "benchmark_smoke_boundary": "anti_overfit_evidence",
    "benchmark_isolation": "anti_overfit_evidence",
    "continuity_response_quality": "general_product_quality",
    "documentation": "documentation",
}

_BLOCKER_CATEGORY_LABELS = {
    "worktree_state": "Working tree state",
    "local_environment": "Local environment",
    "local_evidence_freshness": "Local evidence freshness",
    "release_readiness": "Release readiness",
    "publication_state": "Publication state",
    "public_benchmark_evidence": "Public benchmark evidence",
    "anti_overfit_evidence": "Benchmark isolation and smoke boundaries",
    "general_product_quality": "General-purpose product quality",
    "documentation": "Documentation",
}

_BLOCKER_CATEGORY_ACTIONS = {
    "worktree_state": (
        "Commit, shelve, or intentionally clear the current working tree before release claims."
    ),
    "local_environment": (
        "Rerun Docker-backed checks on a host where Docker and Docker Compose are available."
    ),
    "local_evidence_freshness": (
        "Regenerate local CLI/MCP audit evidence against the current checkout."
    ),
    "release_readiness": (
        "Run the default release-surface audit on a clean checkout with no local-only skips."
    ),
    "publication_state": (
        "Publish the current tool surface, then rerun the public GitHub install audit."
    ),
    "public_benchmark_evidence": (
        "Run and verify the full public benchmark gate on the exact release commit."
    ),
    "anti_overfit_evidence": (
        "Refresh benchmark smoke or source-isolation evidence without adding "
        "benchmark-specific runtime logic."
    ),
    "general_product_quality": (
        "Rerun continuity replay on a real corpus with response-quality gates enabled."
    ),
    "documentation": (
        "Update the operator docs so claim boundaries and verifier commands match the code."
    ),
}


def _blocker_categories(checks: list[AuditCheck]) -> list[BlockerCategory]:
    grouped: dict[str, list[str]] = {}
    for check in checks:
        if not check.required or check.status == "ok":
            continue
        category = _BLOCKER_CATEGORY_BY_CHECK.get(check.name, "uncategorized")
        errors = check.errors or (f"{check.name} failed",)
        grouped.setdefault(category, []).extend(errors)

    return [
        BlockerCategory(
            category=category,
            label=_BLOCKER_CATEGORY_LABELS.get(category, category.replace("_", " ").title()),
            next_action=_BLOCKER_CATEGORY_ACTIONS.get(
                category,
                "Inspect the failed check and regenerate the relevant evidence.",
            ),
            blockers=tuple(blockers),
        )
        for category, blockers in grouped.items()
    ]


def _mcp_e2e_smoke(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if data is None:
        return None
    smoke_evidence = data.get("smoke_evidence")
    if not isinstance(smoke_evidence, list):
        return None
    for item in smoke_evidence:
        if isinstance(item, dict) and item.get("kind") == "MCP stdio e2e":
            return item
    return None


def _string_set(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {item for item in value if isinstance(item, str) and item.strip()}


def _tool_count(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _doctor_required_tools_present(value: object) -> bool | None:
    if not isinstance(value, dict):
        return None
    mcp = value.get("mcp")
    if not isinstance(mcp, dict):
        return None
    present = mcp.get("required_tools_present")
    return present if isinstance(present, bool) else None


def _availability_label(value: object) -> str:
    if value is True:
        return "available"
    if value is False:
        return "missing"
    return "unknown"


def _publication_delta(release_audit: Path, public_install_audit: Path) -> PublicationDelta:
    release_data, release_errors = _load_json(release_audit, "release audit")
    public_data, public_errors = _load_json(public_install_audit, "public install audit")
    if release_errors or public_errors or release_data is None or public_data is None:
        return PublicationDelta(
            status="unknown",
            local_required_tools_present=None,
            public_required_tools_present=None,
            local_doctor_available=None,
            public_doctor_available=None,
            local_doctor_required_tools_present=None,
            public_doctor_required_tools_present=None,
            local_tool_count=None,
            public_tool_count=None,
            locally_present_public_missing_tools=(),
            public_missing_required_tools=(),
            note="release or public install evidence is unavailable",
        )

    local_smoke = _mcp_e2e_smoke(release_data)
    public_smoke = public_data.get("mcp_stdio_smoke")
    if local_smoke is None or not isinstance(public_smoke, dict):
        return PublicationDelta(
            status="unknown",
            local_required_tools_present=None,
            public_required_tools_present=None,
            local_doctor_available=None,
            public_doctor_available=None,
            local_doctor_required_tools_present=None,
            public_doctor_required_tools_present=None,
            local_tool_count=None,
            public_tool_count=None,
            locally_present_public_missing_tools=(),
            public_missing_required_tools=(),
            note="local MCP e2e or public MCP list-only evidence is unavailable",
        )

    local_tools = _string_set(local_smoke.get("tools"))
    public_missing = tuple(sorted(_string_set(public_smoke.get("missing_required_tools"))))
    locally_present_public_missing = tuple(sorted(local_tools.intersection(public_missing)))
    local_doctor = release_data.get("installed_doctor_evidence")
    public_doctor = public_data.get("doctor_evidence")
    local_doctor_available = isinstance(local_doctor, dict)
    public_doctor_available = isinstance(public_doctor, dict)
    local_doctor_required_present = _doctor_required_tools_present(local_doctor)
    public_doctor_required_present = _doctor_required_tools_present(public_doctor)
    drift_reasons = []
    if locally_present_public_missing or public_missing:
        drift_reasons.append("MCP tool surface")
    if local_doctor_available and not public_doctor_available:
        drift_reasons.append("doctor command")
    elif (
        local_doctor_required_present is True
        and public_doctor_required_present is not True
    ):
        drift_reasons.append("doctor MCP tool surface")
    status = "ok" if not drift_reasons else "drift"
    note = "public install matches local install surface"
    if drift_reasons:
        note = "public install is behind the local " + " and ".join(drift_reasons)
        local_evidence_from_worktree = bool(
            release_data.get("allow_dirty_worktree")
            or release_data.get("install_from_working_tree")
        )
        if (
            release_data.get("sha") == public_data.get("sha")
            and local_evidence_from_worktree
        ):
            note += (
                "; public clone is the same committed SHA, while local evidence "
                "includes uncommitted working-tree changes"
            )
    return PublicationDelta(
        status=status,
        local_required_tools_present=local_smoke.get("required_tools_present")
        if isinstance(local_smoke.get("required_tools_present"), bool)
        else None,
        public_required_tools_present=public_smoke.get("required_tools_present")
        if isinstance(public_smoke.get("required_tools_present"), bool)
        else None,
        local_doctor_available=local_doctor_available,
        public_doctor_available=public_doctor_available,
        local_doctor_required_tools_present=local_doctor_required_present,
        public_doctor_required_tools_present=public_doctor_required_present,
        local_tool_count=_tool_count(local_smoke.get("tool_count")),
        public_tool_count=_tool_count(public_smoke.get("tool_count")),
        locally_present_public_missing_tools=locally_present_public_missing,
        public_missing_required_tools=public_missing,
        note=note,
    )


def audit_objective_completion(
    *,
    repo_root: Path,
    release_audit: Path,
    public_install_audit: Path,
    benchmark_gate_meta: Path,
    full_sweep_progress: Path,
    benchmark_smoke: Path,
    continuity_replay: Path = Path("results/continuity_replay_harness.json"),
    run_command: RunCommand = _run_command,
) -> dict[str, Any]:
    release_audit = _resolve_repo_path(repo_root, release_audit)
    public_install_audit = _resolve_repo_path(repo_root, public_install_audit)
    benchmark_gate_meta = _resolve_repo_path(repo_root, benchmark_gate_meta)
    full_sweep_progress = _resolve_repo_path(repo_root, full_sweep_progress)
    benchmark_smoke = _resolve_repo_path(repo_root, benchmark_smoke)
    continuity_replay = _resolve_repo_path(repo_root, continuity_replay)
    checks = [
        _check_clean_worktree(repo_root, run_command),
        _check_docker(repo_root, run_command),
        _check_local_cli_mcp_audit(release_audit, repo_root, run_command),
        _check_release_audit(release_audit),
        _check_public_install(public_install_audit),
        _check_release_public_sha_match(
            release_audit,
            public_install_audit,
            repo_root,
            run_command,
        ),
        _check_benchmark_gate(benchmark_gate_meta),
        _check_full_sweep_progress(full_sweep_progress),
        _check_smoke_boundary(benchmark_smoke, repo_root, run_command),
        _check_benchmark_isolation(repo_root),
        _check_continuity_replay_quality(continuity_replay),
        _check_documentation(repo_root),
    ]
    blockers = [
        error
        for check in checks
        if check.required and check.status != "ok"
        for error in (check.errors or (f"{check.name} failed",))
    ]
    blocker_categories = _blocker_categories(checks)
    publication_delta = _publication_delta(release_audit, public_install_audit)
    worktree_summary = _worktree_summary(repo_root, run_command)
    return {
        "status": "complete" if not blockers else "incomplete",
        "objective": {
            "release_ready": "clean worktree, Docker, release audit, and public install evidence",
            "benchmark_ready": "verified full public benchmark gate and progress evidence",
            "general_quality": (
                "continuity replay quality gate with answer, next-step, "
                "and evidence checks"
            ),
            "claim_discipline": "smoke artifacts remain explicitly non-public evidence",
        },
        "prompt_to_artifact_checklist": [
            item.__dict__ for item in _build_prompt_to_artifact_checklist(checks)
        ],
        "checks": [check.__dict__ for check in checks],
        "blockers": blockers,
        "blocker_categories": [category.__dict__ for category in blocker_categories],
        "worktree_summary": worktree_summary,
        "publication_delta": publication_delta.__dict__,
        "next_unblocking_actions": [
            {
                "category": category.category,
                "next_action": category.next_action,
                "blocker_count": len(category.blockers),
            }
            for category in blocker_categories
        ],
    }


def _format_text_summary(report: dict[str, Any]) -> str:
    lines = [f"MapU objective completion: {report['status']}"]
    checklist = report.get("prompt_to_artifact_checklist", [])
    ok_items = [
        item.get("requirement", "")
        for item in checklist
        if isinstance(item, dict) and item.get("status") == "ok"
    ]
    if ok_items:
        lines.append("")
        lines.append("OK deliverables:")
        lines.extend(f"- {item}" for item in ok_items if item)

    categories = report.get("blocker_categories", [])
    if categories:
        lines.append("")
        lines.append("Blockers by category:")
        for category in categories:
            if not isinstance(category, dict):
                continue
            name = category.get("category", "unknown")
            blockers = category.get("blockers", [])
            blocker_count = len(blockers) if isinstance(blockers, list | tuple) else 0
            next_action = category.get("next_action", "")
            lines.append(f"- {name}: {blocker_count} blocker(s)")
            if next_action:
                lines.append(f"  next: {next_action}")
            if isinstance(blockers, list | tuple):
                for blocker in blockers[:3]:
                    lines.append(f"  - {blocker}")
                if len(blockers) > 3:
                    lines.append(f"  - ... {len(blockers) - 3} more")

    worktree_summary = report.get("worktree_summary")
    if (
        isinstance(worktree_summary, dict)
        and worktree_summary.get("status") == "ok"
        and worktree_summary.get("expanded_path_count")
    ):
        lines.append("")
        lines.append("Worktree cleanup summary:")
        lines.append(f"- expanded paths: {worktree_summary['expanded_path_count']}")
        by_area = worktree_summary.get("by_area")
        if isinstance(by_area, dict) and by_area:
            area_text = ", ".join(f"{name}={count}" for name, count in by_area.items())
            lines.append(f"- by area: {area_text}")
        by_status = worktree_summary.get("by_status")
        if isinstance(by_status, dict) and by_status:
            status_text = ", ".join(f"{name}={count}" for name, count in by_status.items())
            lines.append(f"- by status: {status_text}")
        integrity = worktree_summary.get("commit_plan_integrity")
        if isinstance(integrity, dict):
            lines.append(
                "- commit plan integrity: "
                f"{integrity.get('status', 'unknown')} "
                f"({integrity.get('planned_path_count', 0)}/"
                f"{integrity.get('changed_path_count', 0)} paths planned)"
            )
            for field, label in (
                ("missing_from_plan", "missing"),
                ("unexpected_in_plan", "unexpected"),
                ("duplicate_planned_paths", "duplicates"),
            ):
                values = integrity.get(field)
                if isinstance(values, list) and values:
                    lines.append(f"  - {label}: {', '.join(str(value) for value in values[:5])}")
        release_slices = worktree_summary.get("release_slices")
        if isinstance(release_slices, dict) and release_slices:
            lines.append("- release slices:")
            for name, data in sorted(
                release_slices.items(),
                key=lambda item: (-int(item[1].get("count", 0)), item[0])
                if isinstance(item[1], dict)
                else (0, item[0]),
            )[:8]:
                if not isinstance(data, dict):
                    continue
                sample = data.get("sample")
                sample_text = ""
                if isinstance(sample, list) and sample:
                    sample_text = f" ({', '.join(str(path) for path in sample[:2])})"
                lines.append(f"  - {name}: {data.get('count', 0)}{sample_text}")
        commit_plan = worktree_summary.get("suggested_commit_plan")
        if isinstance(commit_plan, list) and commit_plan:
            lines.append("- suggested commit order:")
            for item in commit_plan[:8]:
                if not isinstance(item, dict):
                    continue
                lines.append(
                    "  - "
                    f"{item.get('order', '?')}. {item.get('slice', 'unknown')} "
                    f"({item.get('count', 0)} paths): "
                    f"{item.get('suggested_commit_message', '')}"
                )
        sample = worktree_summary.get("sample")
        if isinstance(sample, list) and sample:
            lines.append("- sample:")
            for item in sample[:5]:
                if not isinstance(item, dict):
                    continue
                lines.append(
                    f"  - {item.get('kind', 'changed')} "
                    f"{item.get('area', 'other')}: {item.get('path', '')}"
                )

    publication_delta = report.get("publication_delta")
    if isinstance(publication_delta, dict):
        lines.append("")
        lines.append("Publication delta:")
        lines.append(f"- status: {publication_delta.get('status', 'unknown')}")
        local_tool_count = publication_delta.get("local_tool_count")
        public_tool_count = publication_delta.get("public_tool_count")
        lines.append(
            f"- tool_count: local={local_tool_count}, public={public_tool_count}"
        )
        local_doctor = _availability_label(publication_delta.get("local_doctor_available"))
        public_doctor = _availability_label(
            publication_delta.get("public_doctor_available")
        )
        lines.append(f"- doctor: local={local_doctor}, public={public_doctor}")
        local_doctor_tools = publication_delta.get("local_doctor_required_tools_present")
        public_doctor_tools = publication_delta.get("public_doctor_required_tools_present")
        lines.append(
            "- doctor required tools: "
            f"local={local_doctor_tools}, public={public_doctor_tools}"
        )
        missing = publication_delta.get("public_missing_required_tools")
        if isinstance(missing, list | tuple) and missing:
            lines.append(f"- public missing required tools: {', '.join(missing)}")
        note = publication_delta.get("note")
        if note:
            lines.append(f"- note: {note}")

    return "\n".join(lines)


def _format_commit_plan_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# MapU Release Cleanup Commit Plan",
        "",
        f"Objective status: `{report.get('status', 'unknown')}`",
        "",
        "This is a non-destructive staging plan generated from the current "
        "working tree. It is not release evidence by itself.",
    ]
    worktree_summary = report.get("worktree_summary")
    if not isinstance(worktree_summary, dict) or worktree_summary.get("status") != "ok":
        lines.extend(["", "Worktree summary is unavailable."])
        return "\n".join(lines)

    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- Expanded changed paths: `{worktree_summary.get('expanded_path_count', 0)}`",
        ]
    )
    by_status = worktree_summary.get("by_status")
    if isinstance(by_status, dict) and by_status:
        status_text = ", ".join(f"`{name}={count}`" for name, count in by_status.items())
        lines.append(f"- By status: {status_text}")
    by_area = worktree_summary.get("by_area")
    if isinstance(by_area, dict) and by_area:
        area_text = ", ".join(f"`{name}={count}`" for name, count in by_area.items())
        lines.append(f"- By area: {area_text}")
    integrity = worktree_summary.get("commit_plan_integrity")
    if isinstance(integrity, dict):
        lines.append(
            "- Commit plan integrity: "
            f"`{integrity.get('status', 'unknown')}` "
            f"(`{integrity.get('planned_path_count', 0)}`/"
            f"`{integrity.get('changed_path_count', 0)}` paths planned)"
        )
        for field, label in (
            ("missing_from_plan", "Missing"),
            ("unexpected_in_plan", "Unexpected"),
            ("duplicate_planned_paths", "Duplicates"),
        ):
            values = integrity.get(field)
            if isinstance(values, list) and values:
                lines.append(f"  - {label}: {', '.join(f'`{value}`' for value in values[:5])}")

    commit_plan = worktree_summary.get("suggested_commit_plan")
    if not isinstance(commit_plan, list) or not commit_plan:
        lines.extend(["", "No changed paths were found for a suggested commit plan."])
        return "\n".join(lines)

    lines.extend(
        [
            "",
            "## Suggested Order",
            "",
            "Review each slice before staging. Suggested messages are labels, not "
            "mandatory commit titles.",
        ]
    )
    for item in commit_plan:
        if not isinstance(item, dict):
            continue
        paths = item.get("paths")
        path_list = (
            [path for path in paths if isinstance(path, str)]
            if isinstance(paths, list)
            else []
        )
        lines.extend(
            [
                "",
                f"### {item.get('order', '?')}. `{item.get('slice', 'unknown')}`",
                "",
                f"- Paths: `{len(path_list)}`",
                f"- Suggested message: `{item.get('suggested_commit_message', '')}`",
                "",
                "Stage this slice after review:",
                "",
                "```powershell",
                *_format_git_add_block(path_list),
                "```",
                "",
                "```text",
                *path_list,
                "```",
            ]
        )
    return "\n".join(lines)


def _powershell_double_quote(value: str) -> str:
    escaped = value.replace("`", "``").replace('"', '`"')
    return f'"{escaped}"'


def _format_git_add_block(paths: list[str]) -> list[str]:
    if not paths:
        return ["git add --"]
    lines = ["git add -- `"]
    for index, path in enumerate(paths):
        suffix = " `" if index < len(paths) - 1 else ""
        lines.append(f"  {_powershell_double_quote(path)}{suffix}")
    return lines


def _render_report(report: dict[str, Any], output_format: str) -> str:
    if output_format == "text":
        return _format_text_summary(report)
    if output_format == "commit-plan":
        return _format_commit_plan_markdown(report)
    return json.dumps(report, indent=2, ensure_ascii=True)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit MapU objective completion evidence.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--release-audit",
        type=Path,
        default=Path(".tmp/release_surface_audit_summary.json"),
    )
    parser.add_argument(
        "--public-install-audit",
        type=Path,
        default=Path(".tmp/public_github_install_audit_summary.json"),
    )
    parser.add_argument(
        "--benchmark-gate-meta",
        type=Path,
        default=DEFAULT_BENCHMARK_GATE_META,
    )
    parser.add_argument(
        "--full-sweep-progress",
        type=Path,
        default=Path(".tmp/full_sweep_progress.json"),
    )
    parser.add_argument(
        "--benchmark-smoke",
        type=Path,
        default=Path(".tmp/benchmark-live-smoke/smoke_report.json"),
    )
    parser.add_argument(
        "--continuity-replay",
        type=Path,
        default=Path("results/continuity_replay_harness.json"),
    )
    parser.add_argument(
        "--format",
        choices=("json", "text", "commit-plan"),
        default="json",
        help=(
            "Output machine-readable JSON, a concise operator summary, or a "
            "Markdown commit plan."
        ),
    )
    parser.add_argument(
        "--out",
        type=Path,
        help=(
            "Write the rendered report to this path. The command still exits "
            "nonzero when the objective is incomplete."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    benchmark_gate_meta = _resolve_latest_benchmark_gate_meta(
        args.repo_root,
        args.benchmark_gate_meta,
        args.full_sweep_progress,
    )
    report = audit_objective_completion(
        repo_root=args.repo_root,
        release_audit=args.release_audit,
        public_install_audit=args.public_install_audit,
        benchmark_gate_meta=benchmark_gate_meta,
        full_sweep_progress=args.full_sweep_progress,
        benchmark_smoke=args.benchmark_smoke,
        continuity_replay=args.continuity_replay,
    )
    output = _render_report(report, args.format)
    if args.out is not None:
        out_path = args.out if args.out.is_absolute() else args.repo_root / args.out
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
