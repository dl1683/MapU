from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from mapu.mcp.tool_contract import REQUIRED_MCP_TOOLS

REQUIRED_CHECKS = (
    "public git clone completed",
    "venv creation completed",
    "pip install from public clone completed",
    "installed import and metadata checks completed",
    "installed CLI help checks completed",
    "installed doctor check completed",
    "installed MCP stdio smoke completed",
)
REQUIRED_CLI_HELP_SUFFIXES = (
    ("--help",),
    ("corpus", "--help"),
    ("serve", "--help"),
    ("doctor", "--help"),
    ("mcp", "--help"),
)
def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise SystemExit(f"public install audit evidence not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"public install audit evidence is invalid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"public install audit evidence must be a JSON object: {path}")
    return data


def _as_string_list(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise SystemExit(f"public install audit field {key!r} must be a list")
    items: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise SystemExit(f"public install audit field {key}[{index}] must be a string")
        items.append(item)
    return items


def _as_list(data: dict[str, Any], key: str) -> list[Any]:
    value = data.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise SystemExit(f"public install audit field {key!r} must be a list")
    return value


def _is_mapu_command(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    executable = value.replace("\\", "/").rsplit("/", maxsplit=1)[-1].lower()
    return executable in {"mapu", "mapu.exe"}


def _normalized_command_path(value: str) -> str:
    return value.replace("\\", "/").lower()


def _cli_help_mapu_commands(evidence: list[Any]) -> list[str]:
    commands: list[str] = []
    for item in evidence:
        if not isinstance(item, dict) or item.get("status") != "ok":
            continue
        command = item.get("command")
        if not isinstance(command, list) or not command:
            continue
        executable = command[0]
        if _is_mapu_command(executable):
            commands.append(str(executable))
    return commands


def _has_cli_help_suffix(evidence: list[Any], suffix: tuple[str, ...]) -> bool:
    for item in evidence:
        if not isinstance(item, dict) or item.get("status") != "ok":
            continue
        command = item.get("command")
        if not isinstance(command, list) or len(command) < len(suffix) + 1:
            continue
        if not _is_mapu_command(command[0]):
            continue
        if tuple(str(part) for part in command[-len(suffix) :]) == suffix:
            return True
    return False


def _failed_cli_help_errors(evidence: list[Any]) -> list[str]:
    errors: list[str] = []
    for item in evidence:
        if not isinstance(item, dict) or item.get("status") != "fail":
            continue
        command = item.get("command")
        if not isinstance(command, list) or not command:
            errors.append("CLI help evidence has failed entry without command")
            continue
        if not _is_mapu_command(command[0]):
            errors.append("CLI help evidence has failed non-mapu command")
            continue
        suffix = " ".join(str(part) for part in command[1:])
        errors.append(f"CLI help evidence failed: mapu {suffix}".rstrip())
    return errors


def _mcp_smoke_errors(data: dict[str, Any]) -> list[str]:
    smoke = data.get("mcp_stdio_smoke")
    if not isinstance(smoke, dict):
        return ["mcp_stdio_smoke evidence is missing"]
    errors: list[str] = []
    if smoke.get("status") != "ok":
        errors.append("mcp_stdio_smoke status is not ok")
    if not isinstance(smoke.get("command"), str) or not smoke["command"].strip():
        errors.append("mcp_stdio_smoke command is missing")
    elif not _is_mapu_command(smoke["command"]):
        errors.append("mcp_stdio_smoke command is not installed mapu")
    args = smoke.get("args")
    if not isinstance(args, list) or "mcp" not in [str(arg) for arg in args]:
        errors.append("mcp_stdio_smoke args do not include mcp")
    for field in ("mapu_version", "git_sha"):
        if not isinstance(smoke.get(field), str) or not smoke[field].strip():
            errors.append(f"mcp_stdio_smoke {field} is missing")
    if (
        isinstance(smoke.get("git_sha"), str)
        and smoke["git_sha"].strip()
        and isinstance(data.get("sha"), str)
        and data["sha"].strip()
        and smoke["git_sha"] != data["sha"]
    ):
        errors.append("mcp_stdio_smoke git_sha does not match public install sha")
    if not isinstance(smoke.get("tool_count"), int) or smoke["tool_count"] <= 0:
        errors.append("mcp_stdio_smoke tool_count is not positive")
    elif smoke["tool_count"] < len(REQUIRED_MCP_TOOLS):
        errors.append(
            "mcp_stdio_smoke tool_count is below required tool count "
            f"{len(REQUIRED_MCP_TOOLS)}"
        )
    tools = smoke.get("tools")
    if not isinstance(tools, list) or not all(isinstance(tool, str) for tool in tools):
        errors.append("mcp_stdio_smoke tools is missing or invalid")
    else:
        missing_tools = [tool for tool in REQUIRED_MCP_TOOLS if tool not in tools]
        if missing_tools:
            errors.append(f"mcp_stdio_smoke tools missing required tools: {missing_tools}")
    if smoke.get("required_tools_present") is not True:
        errors.append("mcp_stdio_smoke required_tools_present is not true")
    missing = smoke.get("missing_required_tools")
    if not isinstance(missing, list) or missing:
        errors.append("mcp_stdio_smoke missing_required_tools is not empty")
    if smoke.get("workflow_enabled") is not False:
        errors.append("mcp_stdio_smoke workflow_enabled is not false")
    return errors


def _doctor_evidence_errors(data: dict[str, Any]) -> list[str]:
    doctor = data.get("doctor_evidence")
    if not isinstance(doctor, dict):
        return ["doctor_evidence is missing"]
    errors: list[str] = []
    if doctor.get("status") != "ok":
        errors.append("doctor_evidence status is not ok")
    mcp = doctor.get("mcp")
    if not isinstance(mcp, dict):
        errors.append("doctor_evidence mcp is missing")
        return errors
    if mcp.get("required_tools_present") is not True:
        errors.append("doctor_evidence required_tools_present is not true")
    missing = mcp.get("missing_required_tools")
    if missing not in ([], None):
        errors.append("doctor_evidence missing_required_tools is not empty")
    tool_count = mcp.get("tool_count")
    if not isinstance(tool_count, int) or tool_count < len(REQUIRED_MCP_TOOLS):
        errors.append("doctor_evidence tool_count is below required MCP tool count")
    tools = mcp.get("tools")
    if not isinstance(tools, list) or not all(isinstance(tool, str) for tool in tools):
        errors.append("doctor_evidence tools is missing or invalid")
    else:
        missing_tools = [tool for tool in REQUIRED_MCP_TOOLS if tool not in tools]
        if missing_tools:
            errors.append(f"doctor_evidence tools missing required tools: {missing_tools}")
    return errors


def verify_public_install_audit_evidence(data: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []

    if data.get("passed") is not True:
        errors.append("passed is not true")
    repo_url = data.get("repo_url")
    if not isinstance(repo_url, str) or not repo_url.strip():
        errors.append("repo_url is missing")
    ref = data.get("ref")
    if not isinstance(ref, str) or not ref.strip():
        errors.append("ref is missing")
    sha = data.get("sha")
    if not isinstance(sha, str) or not sha.strip() or sha == "unknown":
        errors.append("sha is missing or unknown")

    checks_passed = _as_string_list(data, "checks_passed")
    checks_failed = _as_string_list(data, "checks_failed")
    if checks_failed:
        errors.append(f"checks_failed is not empty: {checks_failed}")
    missing = [check for check in REQUIRED_CHECKS if check not in checks_passed]
    if missing:
        errors.append(f"missing required checks: {missing}")

    cli_help_evidence = _as_list(data, "cli_help_evidence")
    missing_help = [
        "mapu " + " ".join(suffix)
        for suffix in REQUIRED_CLI_HELP_SUFFIXES
        if not _has_cli_help_suffix(cli_help_evidence, suffix)
    ]
    if missing_help:
        errors.append(f"missing CLI help evidence: {missing_help}")
    errors.extend(_failed_cli_help_errors(cli_help_evidence))
    cli_mapu_commands = _cli_help_mapu_commands(cli_help_evidence)
    normalized_cli_commands = {
        _normalized_command_path(command)
        for command in cli_mapu_commands
    }
    if len(normalized_cli_commands) > 1:
        errors.append("CLI help evidence uses multiple installed mapu commands")
    smoke = data.get("mcp_stdio_smoke")
    if (
        isinstance(smoke, dict)
        and isinstance(smoke.get("command"), str)
        and _is_mapu_command(smoke["command"])
        and len(normalized_cli_commands) == 1
        and _normalized_command_path(smoke["command"]) not in normalized_cli_commands
    ):
        errors.append("mcp_stdio_smoke command does not match CLI help mapu command")
    errors.extend(_doctor_evidence_errors(data))
    errors.extend(_mcp_smoke_errors(data))

    return not errors, errors


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify public GitHub install audit JSON before using it as evidence.",
    )
    parser.add_argument("path", help="Path to public_github_install_audit.ps1 JSON output.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    path = Path(args.path)
    data = _load_json(path)
    ok, errors = verify_public_install_audit_evidence(data)
    print(
        json.dumps(
            {
                "status": "ok" if ok else "fail",
                "path": str(path),
                "errors": errors,
            },
            ensure_ascii=True,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
