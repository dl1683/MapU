from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from mapu.mcp.tool_contract import REQUIRED_MCP_TOOLS

REQUIRED_CHECKS = (
    "benchmark-specific code is isolated from general runtime",
)

REQUIRED_SMOKE_CHECKS_BY_KIND = {
    "CLI e2e": (
        "doctor_ok",
        "doctor_required_tools_present",
        "ingest_ok",
        "resume_has_priority_next_actions",
        "query_answer_nonempty",
        "query_has_next_steps",
        "activity_written",
        "delete_ok",
    ),
    "MCP stdio e2e": (
        "create_ok",
        "ingest_ok",
        "contribute_ok",
        "review_ok",
        "query_answer_nonempty",
        "query_has_next_steps",
        "handoff_has_protocol",
        "handoff_has_priority_actions",
        "learning_feedback_logged",
        "activity_written",
        "delete_ok",
    ),
}
def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise SystemExit(f"release audit evidence not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"release audit evidence is invalid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"release audit evidence must be a JSON object: {path}")
    return data


def _as_list(data: dict[str, Any], key: str) -> list[Any]:
    value = data.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise SystemExit(f"release audit evidence field {key!r} must be a list")
    return value


def _has_smoke_kind(data: dict[str, Any], kind: str) -> bool:
    for item in _as_list(data, "smoke_evidence"):
        if isinstance(item, dict) and item.get("kind") == kind and item.get("status") == "ok":
            return True
    return False


def _smoke_evidence_errors(data: dict[str, Any], kind: str) -> list[str]:
    for item in _as_list(data, "smoke_evidence"):
        if not isinstance(item, dict) or item.get("kind") != kind:
            continue
        if item.get("status") != "ok":
            return [f"{kind} smoke evidence status is not ok"]
        errors: list[str] = []
        command_line = item.get("command_line")
        if not isinstance(command_line, list) or not all(
            isinstance(part, str) and part.strip() for part in command_line
        ):
            errors.append(f"{kind} smoke evidence missing non-empty command_line")
        for field in ("corpus_id", "mapu_version", "git_sha"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                errors.append(f"{kind} smoke evidence missing {field}")
        audit_sha = data.get("sha")
        if (
            isinstance(item.get("git_sha"), str)
            and item["git_sha"].strip()
            and isinstance(audit_sha, str)
            and audit_sha.strip()
            and item["git_sha"] != audit_sha
        ):
            errors.append(f"{kind} smoke evidence git_sha does not match audit sha")
        required_checks = item.get("required_checks")
        if not isinstance(required_checks, dict) or not required_checks:
            errors.append(f"{kind} smoke evidence missing required_checks")
        else:
            missing_required_check_names = [
                check
                for check in REQUIRED_SMOKE_CHECKS_BY_KIND.get(kind, ())
                if check not in required_checks
            ]
            if missing_required_check_names:
                errors.append(
                    f"{kind} smoke evidence missing required check names: "
                    f"{missing_required_check_names}"
                )
            failed_checks = [
                str(name)
                for name, value in required_checks.items()
                if value is not True
            ]
            if failed_checks:
                errors.append(f"{kind} smoke evidence has failed required checks: {failed_checks}")
        if kind == "MCP stdio e2e":
            tool_count = item.get("tool_count")
            if not isinstance(tool_count, int) or tool_count < len(REQUIRED_MCP_TOOLS):
                errors.append(
                    f"{kind} smoke evidence tool_count is below required tool count "
                    f"{len(REQUIRED_MCP_TOOLS)}"
                )
            if item.get("required_tools_present") is not True:
                errors.append(f"{kind} smoke evidence required_tools_present is not true")
            missing_tools = item.get("missing_required_tools")
            if not isinstance(missing_tools, list) or missing_tools:
                errors.append(f"{kind} smoke evidence missing_required_tools is not empty")
            tools = item.get("tools")
            if not isinstance(tools, list) or not all(isinstance(tool, str) for tool in tools):
                errors.append(f"{kind} smoke evidence tools is missing or invalid")
            else:
                absent_tools = [tool for tool in REQUIRED_MCP_TOOLS if tool not in tools]
                if absent_tools:
                    errors.append(
                        f"{kind} smoke evidence tools missing required tools: {absent_tools}"
                    )
        return errors
    return [f"missing passing {kind} smoke evidence"]


def _installed_doctor_errors(data: dict[str, Any]) -> list[str]:
    if data.get("skip_fresh_install") is True:
        return []
    doctor = data.get("installed_doctor_evidence")
    if not isinstance(doctor, dict):
        return ["installed_doctor_evidence is missing"]
    errors: list[str] = []
    if doctor.get("status") != "ok":
        errors.append("installed_doctor_evidence status is not ok")
    mcp = doctor.get("mcp")
    if not isinstance(mcp, dict):
        errors.append("installed_doctor_evidence mcp is missing")
        return errors
    if mcp.get("required_tools_present") is not True:
        errors.append("installed_doctor_evidence required_tools_present is not true")
    missing = mcp.get("missing_required_tools")
    if missing not in ([], None):
        errors.append("installed_doctor_evidence missing_required_tools is not empty")
    tool_count = mcp.get("tool_count")
    if not isinstance(tool_count, int) or tool_count < len(REQUIRED_MCP_TOOLS):
        errors.append("installed_doctor_evidence tool_count is below required MCP tool count")
    tools = mcp.get("tools")
    if not isinstance(tools, list) or not all(isinstance(tool, str) for tool in tools):
        errors.append("installed_doctor_evidence tools is missing or invalid")
    else:
        missing_tools = [tool for tool in REQUIRED_MCP_TOOLS if tool not in tools]
        if missing_tools:
            errors.append(
                f"installed_doctor_evidence tools missing required tools: {missing_tools}"
            )
    return errors


def verify_release_audit_evidence(
    data: dict[str, Any],
    *,
    mode: str,
    require_cli_e2e: bool = False,
    require_mcp_e2e: bool = False,
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    skipped = _as_list(data, "checks_skipped")
    failed = _as_list(data, "checks_failed")
    passed_checks = [str(item) for item in _as_list(data, "checks_passed")]

    if data.get("passed") is not True:
        errors.append("audit did not pass")
    audit_sha = data.get("sha")
    if not isinstance(audit_sha, str) or not audit_sha.strip():
        errors.append("audit sha is missing")
    if failed:
        errors.append(f"audit has failed checks: {failed}")
    missing_checks = [check for check in REQUIRED_CHECKS if check not in passed_checks]
    if missing_checks:
        errors.append(f"audit missing required passed checks: {missing_checks}")

    if mode == "release":
        if data.get("release_ready_evidence") is not True:
            errors.append("release_ready_evidence is not true")
        if data.get("evidence_scope") not in (None, "release"):
            errors.append(f"release evidence has evidence_scope={data.get('evidence_scope')!r}")
        if skipped:
            errors.append(f"release evidence has skipped checks: {skipped}")
        for field in (
            "skip_fresh_install",
            "skip_docker",
            "allow_dirty_worktree",
            "install_from_working_tree",
        ):
            if data.get(field):
                errors.append(f"release evidence has {field}=true")
    elif mode == "local-dev":
        if "checks_skipped" not in data:
            errors.append("local-dev evidence must include checks_skipped")
        if data.get("evidence_scope") == "failed":
            errors.append("local-dev evidence has failed scope")
        if data.get("allow_dirty_worktree") or data.get("install_from_working_tree"):
            status = data.get("worktree_status_porcelain")
            if not isinstance(status, list) or not all(isinstance(item, str) for item in status):
                errors.append(
                    "local-dev dirty/working-tree evidence missing "
                    "worktree_status_porcelain"
                )
            if not isinstance(data.get("worktree_dirty_path_count"), int):
                errors.append(
                    "local-dev dirty/working-tree evidence missing "
                    "worktree_dirty_path_count"
                )
            fingerprint = data.get("worktree_fingerprint_sha256")
            if not isinstance(fingerprint, str) or not fingerprint.strip():
                errors.append(
                    "local-dev dirty/working-tree evidence missing "
                    "worktree_fingerprint_sha256"
                )
    else:
        errors.append(f"unknown mode: {mode}")

    if require_cli_e2e:
        errors.extend(_smoke_evidence_errors(data, "CLI e2e"))
    if require_mcp_e2e:
        errors.extend(_smoke_evidence_errors(data, "MCP stdio e2e"))
    errors.extend(_installed_doctor_errors(data))

    return not errors, errors


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify release-surface audit JSON before using it as evidence.",
    )
    parser.add_argument("path", help="Path to release_surface_audit.ps1 JSON output.")
    parser.add_argument(
        "--mode",
        choices=("release", "local-dev"),
        default="release",
        help=(
            "release requires no skipped checks or local-only switches; local-dev "
            "allows explicit skips but still requires passed=true and no failures."
        ),
    )
    parser.add_argument(
        "--require-cli-e2e",
        action="store_true",
        help="Require a passing CLI e2e smoke_evidence entry.",
    )
    parser.add_argument(
        "--require-mcp-e2e",
        action="store_true",
        help="Require a passing MCP stdio e2e smoke_evidence entry.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    data = _load_json(Path(args.path))
    ok, errors = verify_release_audit_evidence(
        data,
        mode=args.mode,
        require_cli_e2e=bool(args.require_cli_e2e),
        require_mcp_e2e=bool(args.require_mcp_e2e),
    )
    summary = {
        "status": "ok" if ok else "fail",
        "mode": args.mode,
        "path": str(Path(args.path)),
        "errors": errors,
    }
    print(json.dumps(summary, ensure_ascii=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
