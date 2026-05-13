# Public Release Audit (MapU)

Last updated: 2026-05-13

## Objective

Prepare this repository for open-source release with claim-backed documentation, reproducible performance evidence, and working user-facing surfaces.

## Checklist: Requirement -> Evidence -> Status

1. Performance claims are backed by fresh, reproducible artifacts
- Evidence:
  - `tools/report_full_sweep_leaderboard.py` output
  - `GLOBAL_MEMORY_BENCHMARK_STATUS.md` quarantine note for historical runs
- Status: PARTIAL
- Required fix:
  - Run `tools/prepublish_benchmark_gate.ps1` on the exact release code and update this item with that gate directory.

2. Benchmark adapter does not inject gold answers into retrieval output
- Evidence:
  - `tools/mapu_mem0_adapter.py` no longer injects skip-ingest benchmark hints
  - `_maybe_add_slice_target_summary` and `_maybe_add_benchmark_gold_summary` removed from runtime `search()` path
- Status: PASS

3. README only claims shipped surfaces and has copy-safe wording
- Evidence:
  - `README.md` rewritten with explicit shipped surfaces (`mapu mcp`, `mapu serve`, CLI, package)
  - README explicitly states GitHub Action is not shipped in this repository
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
- Status: PARTIAL
- Required fix:
  - Execute the gate successfully before any public release or benchmark claim update.

11. Clean package build works
- Evidence:
  - Executed `python -m build --wheel`
  - Result: `Successfully built mapu-0.1.0-py3-none-any.whl`
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
- Status: PASS

14. Generated and heavyweight artifacts are excluded from public release
- Evidence:
  - `.gitignore` excludes `results/`, `datasets/`, `logs/`, `dist/`, `.tmp/`, `.uv-cache/`, `.codex_tmp/`
  - Measured local generated size before exclusion: `results/` about 1.1GB, `datasets/` about 1.05GB
- Status: PASS

## Release Gate

Do not call this repository fully public ready until all PARTIAL items are closed by a successful prepublish benchmark gate run on the exact release code.
