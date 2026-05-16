# Public Release Audit (MapU)

Last updated: 2026-05-15

## Objective

Prepare this repository for open-source release with claim-backed documentation, reproducible performance evidence, and working user-facing surfaces.

## Checklist: Requirement -> Evidence -> Status

1. Performance claims are backed by fresh, reproducible artifacts
- Evidence:
  - `tools/report_full_sweep_leaderboard.py` output
  - `GLOBAL_MEMORY_BENCHMARK_STATUS.md` quarantine note for historical runs
  - 2026-05-15 gate attempt `logs/benchmarks/prepublish_gate_20260515_180011`
    restored the benchmark checkout and produced real lane outputs, but did not
    complete and did not generate `leaderboard.txt`.
- Status: PARTIAL
- Required fix:
  - Run `tools/prepublish_benchmark_gate.ps1` on the exact release code until it
    completes successfully and update this item with that passing gate directory.

2. Benchmark adapter does not inject gold answers into retrieval output
- Evidence:
  - `tools/mapu_mem0_adapter.py` no longer injects skip-ingest benchmark hints
  - `_maybe_add_slice_target_summary` and `_maybe_add_benchmark_gold_summary` removed from runtime `search()` path
- Status: PASS

3. README only claims shipped surfaces and has copy-safe wording
- Evidence:
  - `README.md` rewritten with explicit shipped surfaces (`mapu mcp`, `mapu serve`, CLI, package)
  - README explicitly states GitHub Action is not shipped in this repository
  - 2026-05-15 quickstart changed from development extras to runtime install:
    `pip install -e .`; `.[dev]` is documented only for contributor checks.
- Status: PASS

4. Core docs are encoding-clean and publication-ready
- Evidence:
  - `ARCHITECTURE.md` rewritten in clean ASCII-safe form
  - `DOMAINS.md` rewritten in clean ASCII-safe form
- Status: PASS

5. Architecture claims are separated as implemented vs design intent
- Evidence:
  - `ARCHITECTURE.md` now has explicit sections for implemented surfaces and design intent
- Status: PASS

6. User-facing surfaces have reproducible integration/reset instructions
- Evidence:
  - `INTEGRATIONS.md` documents startup, MCP workflow, and reset flows
  - CLI reset/delete added: `mapu corpus reset --yes`, `mapu corpus delete <id> --yes`
  - MCP reset/delete added: `reset_all_corpora(confirm=true)`, `delete_corpus(..., confirm=true)`
  - 2026-05-13 lightweight verification: `python -m mapu.cli corpus reset --help`, `python -m mapu.cli corpus delete --help`
- Status: PASS

7. MCP integration works end-to-end in real run
- Evidence:
  - Repeated execution of `python tools/mcp_relex_smoke.py` on 2026-05-13
  - Operational path PASS: create corpus -> ingest -> query
  - Quality hardening applied and verified:
    - modality normalization (`shall/must/may`)
    - obligation-priority rerank
    - malformed obligation-to-counterparty suppression in user-facing answers
- Status: PASS

8. Claim-to-evidence mapping across all top-level docs is complete
- Evidence:
  - Claim discipline and benchmark evidence mapping present in `README.md` and `GLOBAL_MEMORY_BENCHMARK_STATUS.md`
  - `ARCHITECTURE.md` and `DOMAINS.md` now scoped to implemented-vs-intent and research reference language
  - `CLAIM_EVIDENCE_APPENDIX.md` maps `PRIORITIES.md` and `PROBLEM_SPACE.md` claims to evidence or intent labels
- Status: PASS

9. Continuous hardened benchmark monitoring is available
- Evidence:
  - `tools/run_continuous_hardened_benchmarks.ps1`
  - `tools/start_continuous_hardened_benchmarks.ps1`
  - `INTEGRATIONS.md` section "Continuous hardened benchmark validation"
- Status: PASS

10. Prepublish benchmark claims are gated to current code
- Evidence:
  - `tools/prepublish_benchmark_gate.ps1`
  - `tools/run_full_leaderboard_sweeps_parallel.ps1`
  - `INTEGRATIONS.md` section "Prepublish benchmark gate"
  - 2026-05-15 hardening: parallel gate now has per-lane wall-clock and
    idle-progress timeouts, treats null exit codes as failure, and stops sibling
    lanes after first failure.
  - Follow-up fix: idle-progress detection includes child worker CPU so active
    benchmark workers are not mistaken for stalled parent wrappers.
- Status: PARTIAL
- Required fix:
  - Execute the gate successfully before any public release or benchmark claim update.
  - Conservative resume command:
    `powershell -NoProfile -ExecutionPolicy Bypass -File tools\prepublish_benchmark_gate.ps1 -Parallel -MaxParallel 3 -IdleTimeoutMinutes 20`
  - Higher settings such as `-MaxParallel 6` are valid when the host is otherwise free; avoid combining them with other heavy local processes.

10a. Cheap release-surface audit is repeatable
- Evidence:
  - `tools/release_surface_audit.ps1` checks clean git state, tracked file size,
    obvious private secret patterns, dummy-only benchmark API key usage, Docker
    availability, and fresh-clone install/import/CLI metadata surfaces.
  - 2026-05-15 fast run with `-SkipFreshInstall` correctly failed while this
    script was uncommitted and Docker was unavailable; Docker remains the real
    unresolved external-startup blocker on this host.
  - 2026-05-15 clean fast run at `abc29222fb948e62bcf9f19b690847692a8df92c`
    passed clean git, tracked-size, private-secret, and dummy-key checks, then
    failed only because `docker` was not available in the active shell.
- Status: PARTIAL
- Required fix:
  - Run `powershell -NoProfile -ExecutionPolicy Bypass -File tools\release_surface_audit.ps1`
    successfully on a host with Docker available before calling the repo
    release-ready.

11. Clean package build works
- Evidence:
  - Executed `python -m build --wheel`
  - Result: `Successfully built mapu-0.1.0-py3-none-any.whl`
  - 2026-05-15 package metadata check: name `mapu`, version `0.1.0`, license `AGPL-3.0-only`, Python `>=3.12,<3.15`
  - 2026-05-15 external-install audit from ignored fresh clone:
    - `py -3.13 -m venv .tmp/release-audit-install/venv`
    - `python -m pip install .tmp/release-audit-install/checkout`
    - installed wheel: `mapu-0.1.0-py3-none-any.whl`
    - installed imports from site-packages: `mapu`, `mapu.cli`, `mapu.api.app`, `mapu.mcp.server`
    - installed console entry point works: `mapu --help`, `mapu corpus --help`, `mapu serve --help`, `mapu mcp --help`
    - installed metadata emits `License-Expression: AGPL-3.0-only`, `License-File: LICENSE`, and `Requires-Python: <3.15,>=3.12`
- Status: PASS

12. Local environment and migrations use documented config
- Evidence:
  - `.env.example` added
  - `src/mapu/config.py` reads `.env`
  - `src/mapu/db/migrations/env.py` uses `Settings().database.url`
  - Executed `alembic current`; result: `202605070004 (head)`
- Status: PASS

13. Unit suite is warning-free
- Evidence:
  - Executed `pytest`
- Result: `554 passed, 55 deselected`
- Follow-up 2026-05-13 focused surface check: `python -m pytest tests/unit/test_cli.py tests/unit/test_mcp_server.py tests/unit/test_api.py -q` -> pass
- Follow-up 2026-05-15 focused surface check at `64576196f65c70207cbfe6dff296f4f17a0f37f0`:
  `python -m pytest tests/unit/test_cli.py tests/unit/test_mcp_server.py tests/unit/test_api.py -q` -> pass
- Status: PASS

14. Generated and heavyweight artifacts are excluded from public release
- Evidence:
  - `.gitignore` excludes `results/`, `datasets/`, `logs/`, `dist/`, `.tmp/`, `.uv-cache/`, `.codex_tmp/`
  - Measured local generated size before exclusion: `results/` about 1.1GB, `datasets/` about 1.05GB
  - 2026-05-15 tracked-file size scan found no committed files over 1MB
  - 2026-05-15 secret-pattern scan found only dummy benchmark keys, example text, and test fixture references; no real key material detected
  - `tools/clean_local_artifacts.ps1` removes disposable local caches while preserving `.tmp/memory-benchmarks`, which benchmark tools require.
- Status: PASS

## Release Gate

Do not call this repository fully public ready until all PARTIAL items are closed by a successful prepublish benchmark gate run on the exact release code.

Current pause point:
- Last substantive release-state commit checked before current benchmark attempt: `238cadecb4d45df2542f0c3d9eb86a7337d0db11`
- Worktree state before the `20260515_180011` gate attempt: clean
- Repository visibility checked before pause: public at `https://github.com/dl1683/MapU`
- Branch note: local branch is `master` tracking remote default branch `origin/main`; use `git push origin HEAD:main` unless the local branch is renamed.
- Benchmark gate state: `logs/benchmarks/prepublish_gate_20260515_184056` failed due an over-strict first idle detector; `logs/benchmarks/prepublish_gate_20260515_180011` failed/aborted after BEAM 100K stopped making progress. Neither is public benchmark evidence.
- Latest gate state: `logs/benchmarks/prepublish_gate_20260515_190928` confirmed the child-worker idle fix but was manually stopped because the full BEAM 100K lane remained too slow for a practical prepublish run on this host/model stack. It is not public benchmark evidence.
- Local limitation at pause: Docker was not available in the active shell, so `docker compose config` and full documented infra startup were not reverified from this host.
- Conservative next benchmark command: `powershell -NoProfile -ExecutionPolicy Bypass -File tools\prepublish_benchmark_gate.ps1 -Parallel -MaxParallel 3 -IdleTimeoutMinutes 20`
- If the machine is otherwise free, `-MaxParallel 6` is reasonable to try while monitoring responsiveness.
