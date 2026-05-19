from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REQUIRED_LEADERBOARD_MARKERS = (
    "=== Full Sweep Leaderboard Comparison ===",
    "LoCoMo ours file:",
    "LongMemEval ours file:",
    "BEAM 100K ours file:",
    "BEAM 500K ours file:",
    "BEAM 1M ours file:",
    "BEAM 10M ours file:",
)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise SystemExit(f"prepublish gate metadata not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"prepublish gate metadata is invalid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"prepublish gate metadata must be a JSON object: {path}")
    return data


def _path_from_meta(gate_meta_path: Path, raw: object) -> Path | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    path = Path(raw)
    if path.is_absolute():
        return path
    return (gate_meta_path.parent / path).resolve()


def _read_code_identity(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def verify_prepublish_benchmark_evidence(
    gate_meta: dict[str, Any],
    *,
    gate_meta_path: Path,
    require_clean_worktree: bool = True,
    require_public_evidence_labels: bool = False,
) -> tuple[bool, list[str]]:
    errors: list[str] = []

    if gate_meta.get("gate_pass") is not True:
        errors.append("gate_pass is not true")
    if gate_meta.get("preflight_only"):
        errors.append("preflight_only is true")
    if gate_meta.get("skip_service_preflight"):
        errors.append("skip_service_preflight is true")
    if gate_meta.get("preflight_status") != "ok":
        errors.append(f"preflight_status is {gate_meta.get('preflight_status')!r}, not 'ok'")
    if require_public_evidence_labels:
        if gate_meta.get("public_performance_evidence") is not True:
            errors.append("public_performance_evidence is not true")
        if gate_meta.get("benchmark_evidence_verified") is not True:
            errors.append("benchmark_evidence_verified is not true")

    preflight_checks = gate_meta.get("preflight_checks")
    if not isinstance(preflight_checks, dict) or not preflight_checks:
        errors.append("preflight_checks are missing")
    else:
        for name, check in preflight_checks.items():
            if not isinstance(check, dict) or check.get("status") != "ok":
                errors.append(f"preflight check {name!r} did not pass")

    code_identity_path = _path_from_meta(gate_meta_path, gate_meta.get("code_identity"))
    if code_identity_path is None:
        errors.append("code_identity path is missing")
    elif not code_identity_path.exists():
        errors.append(f"code_identity file does not exist: {code_identity_path}")
    code_identity = _read_code_identity(code_identity_path)
    if require_clean_worktree and code_identity.get("worktree") != "clean":
        errors.append(f"code_identity worktree is {code_identity.get('worktree')!r}, not 'clean'")
    if gate_meta.get("git_sha") and code_identity.get("sha") != gate_meta.get("git_sha"):
        errors.append(
            f"code_identity sha {code_identity.get('sha')!r} does not match "
            f"gate_meta git_sha {gate_meta.get('git_sha')!r}"
        )

    leaderboard_path = _path_from_meta(gate_meta_path, gate_meta.get("leaderboard_report"))
    if leaderboard_path is None:
        errors.append("leaderboard_report path is missing")
    elif not leaderboard_path.exists():
        errors.append(f"leaderboard_report does not exist: {leaderboard_path}")
    elif leaderboard_path.parent != gate_meta_path.parent:
        errors.append("leaderboard_report is not in the same directory as gate_meta.json")
    else:
        leaderboard_text = leaderboard_path.read_text(encoding="utf-8-sig")
        if not leaderboard_text.strip():
            errors.append(f"leaderboard_report is empty: {leaderboard_path}")
        for marker in REQUIRED_LEADERBOARD_MARKERS:
            if marker not in leaderboard_text:
                errors.append(f"leaderboard_report missing section marker: {marker}")
        if "MISSING" in leaderboard_text:
            errors.append("leaderboard_report contains MISSING benchmark outputs")

    lane_artifact_dir = _path_from_meta(gate_meta_path, gate_meta.get("lane_artifact_dir"))
    if lane_artifact_dir is None:
        errors.append("lane_artifact_dir path is missing")
    elif not lane_artifact_dir.exists():
        errors.append(f"lane_artifact_dir does not exist: {lane_artifact_dir}")

    for key in ("sweep_out_log", "sweep_err_log"):
        log_path = _path_from_meta(gate_meta_path, gate_meta.get(key))
        if log_path is None:
            errors.append(f"{key} path is missing")
        elif not log_path.exists():
            errors.append(f"{key} does not exist: {log_path}")
        elif log_path.parent != gate_meta_path.parent:
            errors.append(f"{key} is not in the same directory as gate_meta.json")

    return not errors, errors


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify prepublish benchmark gate metadata before using benchmark claims.",
    )
    parser.add_argument("gate_meta", help="Path to prepublish gate_meta.json.")
    parser.add_argument(
        "--allow-dirty-worktree",
        action="store_true",
        help="Debug only. Do not use for public benchmark claims.",
    )
    parser.add_argument(
        "--require-public-evidence-labels",
        action="store_true",
        help=(
            "Require public_performance_evidence=true and "
            "benchmark_evidence_verified=true in gate_meta.json."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    gate_meta_path = Path(args.gate_meta).resolve()
    gate_meta = _load_json(gate_meta_path)
    ok, errors = verify_prepublish_benchmark_evidence(
        gate_meta,
        gate_meta_path=gate_meta_path,
        require_clean_worktree=not bool(args.allow_dirty_worktree),
        require_public_evidence_labels=bool(args.require_public_evidence_labels),
    )
    summary = {
        "status": "ok" if ok else "fail",
        "path": str(gate_meta_path),
        "errors": errors,
    }
    print(json.dumps(summary, ensure_ascii=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
