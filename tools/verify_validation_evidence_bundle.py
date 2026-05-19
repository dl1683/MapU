from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

try:
    from tools.verify_full_sweep_progress import verify_full_sweep_progress
    from tools.verify_prepublish_benchmark_evidence import verify_prepublish_benchmark_evidence
    from tools.verify_public_install_audit_evidence import verify_public_install_audit_evidence
    from tools.verify_release_audit_evidence import verify_release_audit_evidence
    from tools.worktree_fingerprint import current_worktree_fingerprint
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from verify_full_sweep_progress import verify_full_sweep_progress
    from verify_prepublish_benchmark_evidence import verify_prepublish_benchmark_evidence
    from verify_public_install_audit_evidence import verify_public_install_audit_evidence
    from verify_release_audit_evidence import verify_release_audit_evidence
    from worktree_fingerprint import current_worktree_fingerprint


RunCommand = Callable[[list[str], Path], subprocess.CompletedProcess[str]]


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise SystemExit(f"{label} evidence not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{label} evidence is invalid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"{label} evidence must be a JSON object: {path}")
    return data


def _record(
    results: list[dict[str, Any]],
    *,
    name: str,
    path: Path | None,
    ok: bool,
    errors: list[str],
    required: bool,
) -> None:
    results.append(
        {
            "name": name,
            "path": str(path) if path is not None else None,
            "required": required,
            "status": "ok" if ok else "fail",
            "errors": errors,
        }
    )


def _scoped_worktree_fingerprint_errors(
    data: dict[str, Any],
    *,
    repo_root: Path,
    run_command: RunCommand | None,
) -> list[str]:
    if not (data.get("allow_dirty_worktree") or data.get("install_from_working_tree")):
        return []

    if run_command is None:
        current, errors = current_worktree_fingerprint(repo_root)
    else:
        current, errors = current_worktree_fingerprint(repo_root, run_command=run_command)
    all_errors = list(errors)
    if current is None:
        return all_errors

    for key in (
        "worktree_status_porcelain",
        "worktree_dirty_path_count",
        "worktree_fingerprint_sha256",
    ):
        if data.get(key) != current[key]:
            all_errors.append(f"release audit {key} does not match current worktree")
    return all_errors


def _release_public_sha_errors(
    release_data: dict[str, Any],
    public_install_data: dict[str, Any],
) -> list[str]:
    release_sha = release_data.get("sha")
    public_sha = public_install_data.get("sha")
    errors: list[str] = []
    if not isinstance(release_sha, str) or not release_sha.strip():
        errors.append("release audit sha is missing")
    if not isinstance(public_sha, str) or not public_sha.strip() or public_sha == "unknown":
        errors.append("public install sha is missing or unknown")
    if not errors and release_sha != public_sha:
        errors.append(
            f"release audit sha {release_sha!r} does not match public install sha {public_sha!r}"
        )
    return errors


def verify_validation_evidence_bundle(
    *,
    mode: str,
    repo_root: Path | None = None,
    release_audit: Path | None = None,
    public_install_audit: Path | None = None,
    benchmark_gate_meta: Path | None = None,
    full_sweep_progress: Path | None = None,
    require_public_benchmark: bool = False,
    run_command: RunCommand | None = None,
) -> tuple[bool, list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    resolved_repo_root = Path.cwd() if repo_root is None else repo_root
    release_data: dict[str, Any] | None = None
    public_install_data: dict[str, Any] | None = None

    if release_audit is None:
        _record(
            results,
            name="release_audit",
            path=None,
            ok=False,
            errors=["release audit evidence path is required"],
            required=True,
        )
    else:
        release_data = _load_json(release_audit, "release audit")
        ok, errors = verify_release_audit_evidence(
            release_data,
            mode="release" if mode == "release" else "local-dev",
            require_cli_e2e=True,
            require_mcp_e2e=True,
        )
        if mode == "local-dev":
            errors.extend(
                _scoped_worktree_fingerprint_errors(
                    release_data,
                    repo_root=resolved_repo_root,
                    run_command=run_command,
                )
            )
            ok = ok and not errors
        _record(
            results,
            name="release_audit",
            path=release_audit,
            ok=ok,
            errors=errors,
            required=True,
        )

    if mode == "release":
        if public_install_audit is None:
            _record(
                results,
                name="public_install_audit",
                path=None,
                ok=False,
                errors=["public install audit evidence path is required for release mode"],
                required=True,
            )
        else:
            public_install_data = _load_json(public_install_audit, "public install audit")
            ok, errors = verify_public_install_audit_evidence(public_install_data)
            _record(
                results,
                name="public_install_audit",
                path=public_install_audit,
                ok=ok,
                errors=errors,
                required=True,
            )
            if release_data is not None:
                sha_errors = _release_public_sha_errors(release_data, public_install_data)
                _record(
                    results,
                    name="release_public_sha_match",
                    path=None,
                    ok=not sha_errors,
                    errors=sha_errors,
                    required=True,
                )
    elif public_install_audit is not None:
        public_install_data = _load_json(public_install_audit, "public install audit")
        ok, errors = verify_public_install_audit_evidence(public_install_data)
        _record(
            results,
            name="public_install_audit",
            path=public_install_audit,
            ok=ok,
            errors=errors,
            required=False,
        )

    if require_public_benchmark:
        if benchmark_gate_meta is None:
            _record(
                results,
                name="benchmark_gate_meta",
                path=None,
                ok=False,
                errors=["benchmark gate metadata path is required"],
                required=True,
            )
        else:
            data = _load_json(benchmark_gate_meta, "benchmark gate")
            ok, errors = verify_prepublish_benchmark_evidence(
                data,
                gate_meta_path=benchmark_gate_meta.resolve(),
                require_clean_worktree=True,
                require_public_evidence_labels=True,
            )
            _record(
                results,
                name="benchmark_gate_meta",
                path=benchmark_gate_meta,
                ok=ok,
                errors=errors,
                required=True,
            )

        if full_sweep_progress is None:
            _record(
                results,
                name="full_sweep_progress",
                path=None,
                ok=False,
                errors=["full-sweep progress evidence path is required"],
                required=True,
            )
        else:
            data = _load_json(full_sweep_progress, "full-sweep progress")
            ok, errors = verify_full_sweep_progress(
                data,
                require_public_evidence=True,
            )
            _record(
                results,
                name="full_sweep_progress",
                path=full_sweep_progress,
                ok=ok,
                errors=errors,
                required=True,
            )
    else:
        for name, path in (
            ("benchmark_gate_meta", benchmark_gate_meta),
            ("full_sweep_progress", full_sweep_progress),
        ):
            if path is None:
                continue
            data = _load_json(
                path,
                "benchmark gate" if name == "benchmark_gate_meta" else "full-sweep progress",
            )
            if name == "benchmark_gate_meta":
                ok, errors = verify_prepublish_benchmark_evidence(
                    data,
                    gate_meta_path=path.resolve(),
                    require_clean_worktree=True,
                    require_public_evidence_labels=True,
                )
            else:
                ok, errors = verify_full_sweep_progress(
                    data,
                    require_public_evidence=True,
                )
            _record(
                results,
                name=name,
                path=path,
                ok=ok,
                errors=errors,
                required=False,
            )

    ok = all(item["status"] == "ok" for item in results if item["required"])
    return ok, results


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify a bundle of MapU validation evidence artifacts.",
    )
    parser.add_argument(
        "--mode",
        choices=("local-dev", "release"),
        default="release",
        help=(
            "local-dev accepts scoped release audit evidence; release requires "
            "release-ready evidence."
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root used to validate scoped local-dev worktree fingerprints.",
    )
    parser.add_argument("--release-audit", type=Path, help="release_surface_audit JSON.")
    parser.add_argument(
        "--public-install-audit",
        type=Path,
        help="public_github_install_audit JSON.",
    )
    parser.add_argument("--benchmark-gate-meta", type=Path, help="prepublish gate_meta.json.")
    parser.add_argument(
        "--full-sweep-progress",
        type=Path,
        help="check_full_sweep_progress.ps1 -Json output.",
    )
    parser.add_argument(
        "--require-public-benchmark",
        action="store_true",
        help="Require full public benchmark gate and progress evidence.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    ok, results = verify_validation_evidence_bundle(
        mode=args.mode,
        repo_root=args.repo_root,
        release_audit=args.release_audit,
        public_install_audit=args.public_install_audit,
        benchmark_gate_meta=args.benchmark_gate_meta,
        full_sweep_progress=args.full_sweep_progress,
        require_public_benchmark=bool(args.require_public_benchmark),
    )
    print(
        json.dumps(
            {
                "status": "ok" if ok else "fail",
                "mode": args.mode,
                "require_public_benchmark": bool(args.require_public_benchmark),
                "results": results,
            },
            ensure_ascii=True,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
