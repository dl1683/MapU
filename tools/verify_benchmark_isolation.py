"""Verify benchmark-specific logic stays out of the general MapU runtime."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FORBIDDEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bmemoryarena\b", re.IGNORECASE),
    re.compile(r"\bama[_-]?bench\b", re.IGNORECASE),
    re.compile(r"\blocomo\b", re.IGNORECASE),
    re.compile(r"\blongmemeval\b", re.IGNORECASE),
    re.compile(r"\bbeam[_-]?(100k|500k|1m|10m)?\b", re.IGNORECASE),
    re.compile(r"\bbenchmark[_-]?gold\b", re.IGNORECASE),
    re.compile(r"\bslice[_-]?target\b", re.IGNORECASE),
    re.compile(r"\bground[_-]?truth[_-]?answer\b", re.IGNORECASE),
)

FORBIDDEN_EVALUATION_SHORTCUT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\.startswith\(\s*['\"]question:", re.IGNORECASE),
)

DEFAULT_ALLOWED_PREFIXES = ("src/mapu/evaluation/",)
DEFAULT_ALLOWED_FILES = ("src/mapu/cli.py",)


@dataclass(frozen=True)
class IsolationViolation:
    path: str
    line: int
    match: str
    text: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _relative_posix(path: Path, root: Path) -> str:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        relative = path
    return relative.as_posix()


def _is_allowed(
    relative: str,
    allowed_prefixes: tuple[str, ...],
    allowed_files: tuple[str, ...],
) -> bool:
    return relative in allowed_files or any(
        relative.startswith(prefix) for prefix in allowed_prefixes
    )


def _scan_file(
    path: Path,
    relative: str,
    patterns: tuple[re.Pattern[str], ...] = FORBIDDEN_PATTERNS,
) -> list[IsolationViolation]:
    violations: list[IsolationViolation] = []
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="ignore")
    for line_number, line in enumerate(text.splitlines(), start=1):
        for pattern in patterns:
            match = pattern.search(line)
            if match:
                violations.append(
                    IsolationViolation(
                        path=relative,
                        line=line_number,
                        match=match.group(0),
                        text=line.strip()[:240],
                    )
                )
                break
    return violations


def verify_benchmark_isolation(
    *,
    root: Path | None = None,
    scan_root: Path | None = None,
    allowed_prefixes: tuple[str, ...] = DEFAULT_ALLOWED_PREFIXES,
    allowed_files: tuple[str, ...] = DEFAULT_ALLOWED_FILES,
) -> tuple[bool, dict[str, Any]]:
    root = (root or _repo_root()).resolve()
    scan_root = (scan_root or root / "src" / "mapu").resolve()
    violations: list[IsolationViolation] = []
    evaluation_shortcut_violations: list[IsolationViolation] = []
    scanned_files = 0
    allowed_benchmark_files: set[str] = set()

    for path in sorted(scan_root.rglob("*.py")):
        relative = _relative_posix(path, root)
        scanned_files += 1
        file_violations = _scan_file(path, relative)
        if relative.startswith("src/mapu/evaluation/"):
            evaluation_shortcut_violations.extend(
                _scan_file(
                    path,
                    relative,
                    FORBIDDEN_EVALUATION_SHORTCUT_PATTERNS,
                )
            )
        if not file_violations:
            continue
        if _is_allowed(relative, allowed_prefixes, allowed_files):
            allowed_benchmark_files.add(relative)
            continue
        violations.extend(file_violations)

    all_violations = [*violations, *evaluation_shortcut_violations]
    report = {
        "status": "ok" if not all_violations else "fail",
        "scan_root": _relative_posix(scan_root, root),
        "scanned_files": scanned_files,
        "allowed_prefixes": list(allowed_prefixes),
        "allowed_files": list(allowed_files),
        "allowed_benchmark_files": sorted(allowed_benchmark_files),
        "violation_count": len(all_violations),
        "violations": [violation.__dict__ for violation in violations],
        "evaluation_shortcut_violations": [
            violation.__dict__ for violation in evaluation_shortcut_violations
        ],
        "policy": (
            "Benchmark-specific identifiers may live in evaluation adapters and "
            "the eval CLI surface, but not in general runtime modules. Evaluation "
            "adapters must not branch on benchmark prompt-format prefixes such as "
            "`Question:`."
        ),
    }
    return not all_violations, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=_repo_root())
    parser.add_argument("--scan-root", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    scan_root = args.scan_root
    if scan_root is not None and not scan_root.is_absolute():
        scan_root = args.root / scan_root
    ok, report = verify_benchmark_isolation(root=args.root, scan_root=scan_root)
    output = json.dumps(report, indent=2 if args.json else None, ensure_ascii=True)
    print(output)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
