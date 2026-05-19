from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load_json(path_text: str) -> dict[str, Any]:
    try:
        if path_text == "-":
            raw = sys.stdin.read()
        else:
            raw = Path(path_text).read_text(encoding="utf-8-sig")
        data = json.loads(raw)
    except FileNotFoundError as exc:
        raise SystemExit(f"full-sweep progress JSON not found: {path_text}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"full-sweep progress JSON is invalid: {path_text}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"full-sweep progress JSON must be an object: {path_text}")
    return data


def _require_int(errors: list[str], data: dict[str, Any], key: str) -> int | None:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        errors.append(f"{key} must be an integer")
        return None
    return value


def _require_nested_int(
    errors: list[str],
    data: dict[str, Any],
    key: str,
    display_key: str,
) -> int | None:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        errors.append(f"{display_key} must be an integer")
        return None
    return value


def _validate_count_bucket(
    errors: list[str],
    data: dict[str, Any],
    key: str,
) -> tuple[int | None, int | None]:
    bucket = data.get(key)
    if not isinstance(bucket, dict):
        errors.append(f"{key} must be an object")
        return None, None
    completed = _require_nested_int(errors, bucket, "completed", f"{key}.completed")
    total = _require_nested_int(errors, bucket, "total", f"{key}.total")
    if completed is not None and completed < 0:
        errors.append(f"{key}.completed must be non-negative")
    if total is not None and total <= 0:
        errors.append(f"{key}.total must be positive")
    if completed is not None and total is not None and completed > total:
        errors.append(f"{key}.completed exceeds {key}.total")
    return completed, total


def _counts_complete(data: dict[str, Any], errors: list[str]) -> bool:
    complete = True
    for key in ("locomo", "longmemeval"):
        completed, total = _validate_count_bucket(errors, data, key)
        bucket_complete = (
            completed is not None
            and total is not None
            and completed >= total
        )
        complete = bool(complete and bucket_complete)

    beam = data.get("beam")
    if not isinstance(beam, list):
        errors.append("beam must be a list")
        return False
    if len(beam) != 4:
        errors.append("beam must contain four sweep buckets")
        complete = False
    for index, bucket in enumerate(beam):
        if not isinstance(bucket, dict):
            errors.append(f"beam[{index}] must be an object")
            complete = False
            continue
        if not isinstance(bucket.get("project"), str) or not bucket.get("project"):
            errors.append(f"beam[{index}].project must be a non-empty string")
        completed = _require_nested_int(
            errors,
            bucket,
            "completed",
            f"beam[{index}].completed",
        )
        total = _require_nested_int(errors, bucket, "total", f"beam[{index}].total")
        if completed is not None and completed < 0:
            errors.append(f"beam[{index}].completed must be non-negative")
        if total is not None and total <= 0:
            errors.append(f"beam[{index}].total must be positive")
        if completed is not None and total is not None:
            if completed > total:
                errors.append(f"beam[{index}].completed exceeds beam[{index}].total")
            complete = bool(complete and completed >= total)
        else:
            complete = False
    return complete


def verify_full_sweep_progress(
    data: dict[str, Any],
    *,
    require_public_evidence: bool = False,
) -> tuple[bool, list[str]]:
    errors: list[str] = []

    for key in ("suffix", "gate_dir", "code_sha", "worktree"):
        value = data.get(key)
        if value is not None and not isinstance(value, str):
            errors.append(f"{key} must be a string or null")
    for key in ("gate_meta_present", "gate_pass", "public_performance_evidence"):
        if not isinstance(data.get(key), bool):
            errors.append(f"{key} must be a boolean")
    active_worker_count = _require_int(errors, data, "active_worker_count")
    if active_worker_count is not None and active_worker_count < 0:
        errors.append("active_worker_count must be non-negative")

    workers = data.get("workers")
    if not isinstance(workers, list):
        errors.append("workers must be a list")
    else:
        for index, worker in enumerate(workers):
            if not isinstance(worker, dict):
                errors.append(f"workers[{index}] must be an object")
                continue
            if not isinstance(worker.get("lane"), str) or not worker.get("lane"):
                errors.append(f"workers[{index}].lane must be a non-empty string")
            if not isinstance(worker.get("pid"), int) or isinstance(worker.get("pid"), bool):
                errors.append(f"workers[{index}].pid must be an integer")
            if not isinstance(worker.get("running"), bool):
                errors.append(f"workers[{index}].running must be a boolean")

    complete = _counts_complete(data, errors)

    if require_public_evidence:
        if data.get("public_performance_evidence") is not True:
            errors.append("public_performance_evidence is not true")
        if data.get("gate_pass") is not True:
            errors.append("gate_pass is not true")
        if data.get("gate_meta_present") is not True:
            errors.append("gate_meta_present is not true")
        if data.get("worktree") != "clean":
            errors.append(f"worktree is {data.get('worktree')!r}, not 'clean'")
        if active_worker_count not in (0, None):
            errors.append("active_worker_count is not zero")
        if not complete:
            errors.append("benchmark result counts are incomplete")

    return not errors, errors


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate check_full_sweep_progress.ps1 -Json output.",
    )
    parser.add_argument(
        "path",
        help="Path to progress JSON, or '-' to read JSON from stdin.",
    )
    parser.add_argument(
        "--require-public-evidence",
        action="store_true",
        help="Reject monitoring-only, incomplete, dirty, running, or non-passing progress output.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    data = _load_json(args.path)
    ok, errors = verify_full_sweep_progress(
        data,
        require_public_evidence=bool(args.require_public_evidence),
    )
    print(
        json.dumps(
            {
                "status": "ok" if ok else "fail",
                "path": args.path,
                "errors": errors,
            },
            ensure_ascii=True,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
