from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

RunCommand = Callable[[list[str], Path], subprocess.CompletedProcess[str]]


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


def current_worktree_fingerprint(
    repo_root: Path,
    run_command: RunCommand = _run_command,
) -> tuple[dict[str, Any] | None, list[str]]:
    status_result = run_command(["git", "status", "--porcelain=v1"], repo_root)
    changed_result = run_command(["git", "diff", "--name-only", "HEAD"], repo_root)
    untracked_result = run_command(
        ["git", "ls-files", "--others", "--exclude-standard"],
        repo_root,
    )
    errors: list[str] = []
    if status_result.returncode != 0:
        errors.append(status_result.stderr.strip() or "git status --porcelain=v1 failed")
    if changed_result.returncode != 0:
        errors.append(changed_result.stderr.strip() or "git diff --name-only HEAD failed")
    if untracked_result.returncode != 0:
        errors.append(
            untracked_result.stderr.strip()
            or "git ls-files --others --exclude-standard failed"
        )
    if errors:
        return None, errors

    status_lines = [line for line in status_result.stdout.splitlines() if line.strip()]
    changed_files = {
        line
        for source in (changed_result.stdout, untracked_result.stdout)
        for line in source.splitlines()
        if line.strip()
    }
    payload_parts = ["[status]", *status_lines, "[files]"]
    for relative in sorted(changed_files):
        path = repo_root / relative
        if path.is_file():
            file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            payload_parts.append(f"{relative}\t{file_hash}")
        else:
            payload_parts.append(f"{relative}\t<missing-or-directory>")
    payload = "\n".join(payload_parts)
    return {
        "worktree_status_porcelain": status_lines,
        "worktree_dirty_path_count": len(status_lines),
        "worktree_fingerprint_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }, []


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emit a stable fingerprint for the current Git worktree.",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root to fingerprint. Defaults to the current directory.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    repo_root = Path(args.repo_root).resolve()
    fingerprint, errors = current_worktree_fingerprint(repo_root)
    if fingerprint is None:
        summary = {"status": "fail", "errors": errors}
        print(json.dumps(summary, ensure_ascii=True))
        return 1
    summary = {"status": "ok", **fingerprint}
    if args.json:
        print(json.dumps(summary, ensure_ascii=True))
    else:
        print(summary["worktree_fingerprint_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
