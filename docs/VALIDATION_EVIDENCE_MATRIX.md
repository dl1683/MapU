# Validation evidence matrix

Last updated: 2026-05-19.

This matrix maps the active MapU objective to evidence that can be inspected
without relying on chat history. It is deliberately strict about the difference
between product validation, smoke checks, and public benchmark evidence.

## Objective criteria

1. General-purpose durable memory works for real agent workflows.
2. Terminal surfaces work with actual installed commands, not only unit mocks.
3. Documentation tells operators what to run and what each check proves.
4. Benchmark work is benchmark-agnostic by default and does not use
   benchmark-specific answer hints for product-quality claims.
5. Public performance claims are blocked until exact-release benchmark evidence
   exists on the audited commit.

## Evidence checklist

| Requirement | Current artifact or command | What it proves | What it does not prove |
| --- | --- | --- | --- |
| CLI continuity loop | `uv run python tools/cli_e2e_smoke.py --command uv --arg run --arg mapu --json` | Installed CLI can report doctor/MCP tool-surface health, create a corpus, ingest a handoff note, resume, query, write activity, and delete cleanup data against the configured database. The release verifier requires `doctor_ok` and `doctor_required_tools_present` inside CLI e2e `required_checks`. | Public benchmark performance, Docker readiness, or production ML-provider latency. |
| MCP stdio continuity loop | `uv run python tools/mcp_stdio_smoke.py --command uv --arg run --arg mapu --arg mcp --json` | Installed MCP subprocess transport can create a corpus, ingest a handoff note, contribute and review a proposition, query, inspect activity, and delete cleanup data. | Production ML-provider latency or public benchmark performance. |
| Continuity replay response quality gate | `uv run python tools/continuity_replay_harness.py --corpus-id <uuid> --require-response-quality-gate --require-frontier-completeness-gate --out results/continuity_replay_harness.json` | A resumed handoff replay executes real query/investigation actions and each response action returns non-empty answer text, next-step guidance, and evidence signals. This is a general-purpose product-quality gate for agent continuity, not a benchmark adapter score. | Public benchmark performance, clean release hygiene, or proof that every future corpus will answer correctly. |
| MCP startup in fresh installs | `tools/mcp_stdio_smoke.py --list-only` as used by release/install audits | Installed MCP server starts and exposes the required tool surface when no database is configured. | DB-backed workflow correctness. Use `-RunMcpE2E` for that. |
| Installed CLI doctor | `mapu doctor --json` | Installed package can report its version and MCP tool surface without a database connection. Public-install evidence records this under `doctor_evidence` and requires all expected MCP tools to be present. | DB-backed workflow correctness, release hygiene, or benchmark performance. |
| Release-surface audit | `powershell -NoProfile -ExecutionPolicy Bypass -File tools\release_surface_audit.ps1 -RunCliE2E -RunMcpE2E -OutputJson .tmp\release_surface_audit_summary.json` | Clean-worktree release hygiene, Docker availability, fresh local clone install, plus DB-backed CLI and MCP loops on the exact checkout. The audit also runs the benchmark isolation source audit, reads the smoke JSON files, checks `status`, `command`, `corpus_id`, `mapu_version`, `git_sha`, and required checks, captures installed `mapu doctor --json` as `installed_doctor_evidence`, then emits verified entries under `smoke_evidence` with a normalized `command_line`. MCP e2e smoke evidence also preserves `tool_count`, `required_tools_present`, `missing_required_tools`, and the full `tools` list. | Public benchmark performance or public GitHub install proof. |
| Local CLI/MCP development audit | `powershell -NoProfile -ExecutionPolicy Bypass -File tools\release_surface_audit.ps1 -SkipDocker -AllowDirtyWorktree -InstallFromWorkingTree -RunCliE2E -RunMcpE2E -OutputJson .tmp\release_surface_audit_summary.json` | The current checkout's DB-backed CLI and MCP loops, non-Docker hygiene checks, and working-tree install can pass in a dirty, no-Docker development shell. The JSON records `skip_docker=true`, `allow_dirty_worktree=true`, `install_from_working_tree=true`, `release_ready_evidence=false`, `evidence_scope=scoped`, explicit skipped checks under `checks_skipped`, and a current worktree fingerprint. | Public release readiness. Rerun the default audit on a clean worktree with Docker installed before release claims. |
| Working-tree install audit | same command as the local CLI/MCP development audit | The current dirty working tree can build/install into a temporary venv, expose Python/CLI/MCP surfaces, and pass DB-backed CLI/MCP loops. The JSON records `install_from_working_tree=true`, `worktree_status_porcelain`, `worktree_dirty_path_count`, and `worktree_fingerprint_sha256`; objective completion rejects stale scoped evidence if these fields no longer match the current worktree. | Public release readiness or public install proof. Fresh-clone and public-GitHub audits still need to pass after commit. |
| Release-audit JSON verifier | `uv run python tools/verify_release_audit_evidence.py .tmp/release_surface_audit_summary.json --mode release --require-cli-e2e --require-mcp-e2e` | A release audit JSON has `passed=true`, top-level `sha`, `release_ready_evidence=true`, `evidence_scope=release`, no failed checks, no skipped checks, no local-only switches, required `installed_doctor_evidence`, required CLI/MCP smoke evidence with non-empty `command_line`, `corpus_id`, `mapu_version`, `git_sha` matching the audit `sha`, and all `required_checks=true`, plus the benchmark-isolation check under `checks_passed`. For MCP e2e and doctor evidence, the verifier also requires the full required MCP tool set in `tools`, `required_tools_present=true`, and `missing_required_tools=[]`. Use `--mode local-dev` only for scoped local evidence with explicit skips. | Running the audit itself. It validates an existing JSON artifact. |
| Public install audit | `powershell -NoProfile -ExecutionPolicy Bypass -File tools\public_github_install_audit.ps1 -OutputJson .tmp\public_github_install_audit_summary.json` plus `uv run python tools\verify_public_install_audit_evidence.py .tmp\public_github_install_audit_summary.json` | Public repository install/import/CLI/MCP startup path from a fresh checkout. The verifier requires a known commit SHA, `passed=true`, no failed checks, all required clone, venv, pip install, import/metadata, CLI help, installed doctor, and MCP list-only checks, plus embedded `cli_help_evidence` for each installed `mapu` help command with command/status/exit-code evidence for both passing and failing help checks, embedded `doctor_evidence` from `mapu doctor --json`, all CLI/MCP command evidence using the same installed `mapu` executable, and embedded `mcp_stdio_smoke` evidence from the installed `mapu` command with the full required MCP tool set in `tools`, `required_tools_present=true`, `missing_required_tools=[]`, `workflow_enabled=false`, and `git_sha` matching the top-level public install `sha`. | DB-backed workflow, because this audit intentionally uses MCP `--list-only` and doctor only checks installed surface metadata. |
| Evidence bundle verifier | Release: `uv run python tools\verify_validation_evidence_bundle.py --mode release --release-audit .tmp/release_surface_audit_summary.json --public-install-audit .tmp/public_github_install_audit_summary.json`; local-dev: `uv run python tools\verify_validation_evidence_bundle.py --mode local-dev --release-audit .tmp\release_surface_audit_summary.json` | The release evidence bundle has both release-ready audit evidence and public fresh-install evidence for the same commit SHA. In `--mode local-dev`, scoped dirty/working-tree audit evidence is also compared against the current `--repo-root` fingerprint so stale local evidence fails. Add `--require-public-benchmark --benchmark-gate-meta logs/benchmarks/<gate>/gate_meta.json --full-sweep-progress .tmp/full_sweep_progress.json` only for benchmark claims. | Generating the artifacts. It only verifies JSON evidence that already exists. |
| Objective completion audit | `uv run python tools\verify_objective_completion.py --release-audit .tmp\release_surface_audit_summary.json --public-install-audit .tmp/public_github_install_audit_summary.json --benchmark-gate-meta logs/benchmarks/<gate>/gate_meta.json --full-sweep-progress .tmp/full_sweep_progress.json --continuity-replay results/continuity_replay_harness.json`; use `--format text` for a concise operator summary, `--format commit-plan` for a Markdown cleanup plan, and `--out <path>` to save the rendered report | A single blocker report and prompt-to-artifact checklist for the active objective: local CLI/MCP evidence, clean worktree, Docker availability, release audit, public install audit, release/public SHA match, full public benchmark gate/progress, continuity replay response-quality evidence, documentation references, and smoke-evidence boundary. It reports local CLI/MCP success separately from public release readiness, rejects stale benchmark smoke if `worktree_fingerprint_sha256`, `worktree_status_porcelain`, or `worktree_dirty_path_count` no longer match the current checkout, emits machine-readable `blocker_categories` plus `next_unblocking_actions` across worktree state, local environment, publication state, public benchmark evidence, anti-overfit evidence, and general-purpose product quality, includes `worktree_summary` with expanded changed-path counts by area/status, logical `release_slices`, a `suggested_commit_plan`, and `commit_plan_integrity` proving whether every changed path is covered exactly once by the review-first `git add -- ...` command blocks, and includes `publication_delta` to compare local MCP e2e tools against the public install MCP tool surface plus installed `mapu doctor --json` evidence against the public install doctor surface. When the public clone has the same committed SHA but local evidence used a dirty/working-tree install, the delta calls out uncommitted working-tree changes as the reason publication still lags. | Replacement for the underlying verifiers. It points at missing or failing evidence; it does not generate that evidence. |
| Unit and integration contract suite | `uv run ruff check` and `uv run pytest -q -p pytest_asyncio.plugin` | Code-level behavior, DTO/CLI/MCP/query contracts, corpus cleanup, benchmark harness mechanics, and docs claim guards. | Live subprocess behavior unless paired with the CLI/MCP e2e smokes. |
| MemoryArena/AMA smoke | `uv run mapu eval memory-benchmark-smoke --no-export --out-dir .tmp/benchmark-live-smoke --min-token-f1 0.45` | Benchmark adapter export/predict/score/gate path can run and clear the local smoke threshold with benchmark-agnostic predictors. The report records `worktree_status_porcelain`, `worktree_dirty_path_count`, `worktree_fingerprint_sha256`, and `worktree_fingerprint_errors`; objective completion compares those fields against the current checkout so stale smoke cannot stand in for current evidence. | Public leaderboard evidence. Output is `smoke_only=true` and `public_performance_evidence=false`. |
| Benchmark isolation source audit | `uv run python tools/verify_benchmark_isolation.py --json` | Benchmark-specific identifiers are confined to `src/mapu/evaluation/` and the eval CLI surface, so general runtime modules do not carry benchmark-name shortcuts. The audit also fails evaluation adapters that branch on benchmark prompt-format prefixes such as `Question:`. | That benchmark-agnostic predictors are broadly capable, or that benchmark smoke scores are public evidence. |
| Full public benchmark claim | `powershell -NoProfile -ExecutionPolicy Bypass -File tools\prepublish_benchmark_gate.ps1 -Parallel -MaxParallel 3 -IdleTimeoutMinutes 20` plus `uv run python tools/verify_prepublish_benchmark_evidence.py logs/benchmarks/<gate>/gate_meta.json --require-public-evidence-labels` | Only a successful exact-code gate with same-directory leaderboard artifacts can support public benchmark numbers. The gate preflights the local model endpoint and MapU database, supports `-PreflightOnly` for auditable service checks without launching lanes, passes the legacy benchmark host argument through `BenchmarkMem0HostArg`, then records `lane_artifact_dir` so each benchmark lane keeps its own stdout, stderr, and metadata for failure diagnosis. The gate runs `verify_prepublish_benchmark_evidence.py` before printing PASS and stores its output path as `benchmark_evidence_verifier`. Only after verifier success does it set `public_performance_evidence=true` and `benchmark_evidence_verified=true`, then it reruns the verifier with `--require-public-evidence-labels`. The verifier requires `gate_pass=true`, `preflight_status=ok`, no skipped service preflight, clean code identity matching `gate_meta.git_sha`, same-directory leaderboard/log artifacts, complete LoCoMo/LongMemEval/BEAM leaderboard sections with no `MISSING` outputs, and an existing lane artifact directory. | Not currently satisfied in this checkout. See `GLOBAL_MEMORY_BENCHMARK_STATUS.md`. |
| Full benchmark progress status | `powershell -NoProfile -ExecutionPolicy Bypass -File tools\check_full_sweep_progress.ps1 -Json > .tmp/full_sweep_progress.json` plus `uv run python tools/verify_full_sweep_progress.py .tmp/full_sweep_progress.json --require-public-evidence` | Machine-readable progress output has a stable schema and, in strict mode, confirms a passing gate, clean worktree, no active workers, complete LoCoMo/LongMemEval/BEAM counts, and `public_performance_evidence=true`. | A substitute for `verify_prepublish_benchmark_evidence.py`; progress JSON is monitoring status unless the strict verifier passes. |
| Benchmark anti-overfit guard | `docs/MEMORY_BENCHMARKS.md`, `GLOBAL_MEMORY_BENCHMARK_STATUS.md`, and tests for diagnostic method rejection | Diagnostic/template predictors are debug-only, benchmark-agnostic is default, and score gates reject diagnostic methods by default. | That the full benchmark suite is already won. |
| Runtime benchmark-leak guard | `tools/verify_benchmark_isolation.py` and `tests/unit/test_benchmark_gate_scripts.py` | Benchmark-specific names such as MemoryArena, AMA-Bench, LoCoMo, LongMemEval, BEAM, gold-answer hints, and slice-target hints fail if they appear outside the evaluation package or eval CLI surface. Prompt-format branches such as `.startswith("Question:")` fail even inside evaluation adapters. | Semantic proof that every benchmark-agnostic heuristic is ideal for every domain. |
| Operator documentation | `README.md`, `INTEGRATIONS.md`, `PUBLIC_RELEASE_AUDIT.md`, `docs/CLI_OPERATOR_GUIDE.md` | Current commands, evidence boundaries, and known blockers are documented for future sessions. | That those commands passed on a different host or after uncommitted changes. |

## Current blockers

- The strict release-surface audit still fails on a dirty worktree until the
  current changes are committed or otherwise cleared. Use `-AllowDirtyWorktree`
  only for local development evidence.
- Docker is not available in the current shell, so Docker Compose startup and
  Docker-backed checks must be rerun on a Docker-enabled host. Use `-SkipDocker`
  only for local development evidence.
- The full public benchmark gate is unresolved. Current MemoryArena/AMA smoke
  evidence is useful regression coverage, not public performance evidence.

## Claim rules

- Treat smoke JSON as the evidence record only when it includes `status`, `command`,
  `corpus_id`, `mapu_version`, and `git_sha`. Missing provenance means rerun the
  smoke before citing it.
- Treat release-audit JSON with non-empty `checks_skipped` as scoped evidence.
  It can prove the checks that ran, but skipped checks remain unverified.
- Treat `release_ready_evidence=false` or `evidence_scope=scoped` as a hard
  boundary against public release claims, even when `passed=true`.
- Before using release-audit JSON for public readiness, run
  `tools/verify_release_audit_evidence.py --mode release --require-cli-e2e
  --require-mcp-e2e` against the artifact.
- Stale release-audit JSON generated before the benchmark-isolation check is not
  sufficient; the verifier requires `benchmark-specific code is isolated from
  general runtime` in `checks_passed`.
- Stubbed CLI/MCP smoke entries are not sufficient; verifier-required smoke
  evidence must include command provenance, corpus id, MapU version, git SHA,
  and passing required checks.
- Do not call the repository fully public-ready unless the release audit passes
  with a clean worktree and Docker verification on the final commit.
- Do not publish benchmark numbers unless `tools/prepublish_benchmark_gate.ps1`
  completes on the exact release commit and writes its leaderboard artifacts in
  the same gate directory.
- Before using prepublish benchmark artifacts for public claims, run
  `tools/verify_prepublish_benchmark_evidence.py` against that gate's
  `gate_meta.json` with `--require-public-evidence-labels`.
- Do not treat CLI/MCP e2e smoke success as benchmark evidence. It proves real
  installed terminal transport behavior and DB cleanup.
- Do not treat local CLI/MCP e2e smoke success as public release readiness. The
  objective completion audit reports `local_cli_mcp_evidence` separately from
  clean-worktree, Docker, fresh public install, and full benchmark evidence.
- Do not treat benchmark smoke success as general product superiority. It proves
  harness health and local regression coverage only.
- Do not reuse benchmark smoke after source edits. Rerun
  `mapu eval memory-benchmark-smoke` when `worktree_fingerprint_sha256`,
  `worktree_status_porcelain`, or `worktree_dirty_path_count` no longer matches
  the current checkout.
- Do not use benchmark smoke as the only general-purpose quality proof. For
  agent-memory continuity claims, run `tools/continuity_replay_harness.py` with
  `--require-response-quality-gate` on a real corpus so replayed
  query/investigation actions must carry answer text, next steps, and evidence.
- Run `uv run python tools/verify_benchmark_isolation.py --json` when touching
  benchmark adapters or runtime retrieval/query code; any violation means a
  benchmark-specific shortcut leaked into the general runtime.
- Use `uv run python tools/verify_objective_completion.py ...` as a final
  blocker report before claiming the active objective is complete.
