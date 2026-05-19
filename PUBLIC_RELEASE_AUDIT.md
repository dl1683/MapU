# Public Release Audit (MapU)

Last updated: 2026-05-15

## Objective

Prepare this repository for open-source release with claim-backed documentation, reproducible performance evidence, and working user-facing surfaces.

Release-readiness now inherits one top-level constraint: MapU is only considered
ready for external consumption when its durable memory-substrate behavior is
explicitly consistent across context-reset conditions and the evidence trail is
auditable.

## Evidence Model

Audit entries below are tied to the exact commit SHA recorded in each entry.
Doc-only follow-up commits can make prior evidence historical. Before calling a
final public release ready, rerun the release surface audit, public GitHub
install audit, Docker startup check, and full prepublish benchmark gate on the
final release commit.

## Checklist: Requirement -> Evidence -> Status

15. Continuity replay is verified before claiming memory-substrate guarantees
- Evidence:
  - `SESSION_CONTINUITY_PROTOCOL.md`
  - `INTEGRATIONS.md` session handoff section
  - `GLOBAL_MEMORY_BENCHMARK_EXECUTION_PLAN.md`
  - Reused-corpus replay artifacts showing gap reduction and reduced rediscovery
- Status: PARTIAL
- Required fix:
  - Produce a two-pass replay artifact against a real repository task before any release claim that says MapU avoids agent rediscovery.

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
  - 2026-05-15 focused destructive-guard tests cover CLI refusal without
    `--yes` and MCP refusal without `confirm=true`.
  - 2026-05-19 CLI e2e smoke added:
    `uv run python tools/cli_e2e_smoke.py --command uv --arg run --arg mapu --json`
    creates a disposable corpus, ingests a source note, runs resume/query/activity,
    verifies nonblank query output and audit activity, and deletes the corpus.
- Status: PASS

7. MCP integration works end-to-end in real run
- Evidence:
  - Repeated execution of `python tools/mcp_relex_smoke.py` on 2026-05-13
  - Operational path PASS: create corpus -> ingest -> query
  - 2026-05-15 process-level stdio smoke added and 2026-05-19 strengthened:
    `tools/mcp_stdio_smoke.py` launches `mapu mcp`, initializes an MCP client
    session, verifies required tools are present, and can execute a DB-backed
    create -> ingest -> contribute -> review -> query -> activity -> delete workflow.
  - The fresh-clone release audit runs the installed MCP stdio smoke in
    `--list-only` mode after checking `mapu mcp --help`; DB-backed release
    audits can add `-RunMcpE2E`.
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

10b. Benchmark harness has bounded smoke coverage without claim ambiguity
- Evidence:
  - `tools/benchmark_smoke_gate.ps1` runs tiny LoCoMo, LongMemEval, and BEAM
    slices through the same MapU benchmark wrapper and local model endpoint.
  - `mapu eval memory-benchmark-smoke` runs MemoryArena and AMA-Bench
    export/predict/score/gate through the installed CLI with benchmark-agnostic
    predictors by default.
  - `mapu eval memory-benchmark-smoke` prints one top-level JSON summary by
    default, writes adapter stdout into `smoke_report.json`, and exposes
    `--verbose-steps` for debugging only.
  - `smoke_report.json` records actual scenario inputs under `inputs`,
    generated artifacts under `paths`, and gate metrics under `score_summary`;
    non-exact metric gates expose `threshold_metric` and `threshold`.
  - MemoryArena and AMA-Bench score reports include `item_scores` and
    `worst_items` for local failure analysis without changing aggregate gate
    semantics.
  - The smoke gate writes metadata with `smoke_only=true` and
    `public_performance_evidence=false`.
  - The MemoryArena/AMA aggregate gate rejects diagnostic/template prediction
    methods by default and passes them only with explicit
    `--allow-diagnostic-methods` debug opt-in.
  - MemoryArena `web_grounded` predictions preserve web-source metadata under
    `evidence.web`; the current tiny-slice lane clears the local non-diagnostic
    smoke gate but still needs broader evidence before it can support claims.
- Status: PASS for harness smoke coverage; still not benchmark evidence
- Exact-SHA use:
  - Run the smoke gate on the same commit being audited and inspect its
    `gate_meta.json`.
  - A passing smoke gate proves only that the benchmark wrapper/local-endpoint
    path can execute tiny LoCoMo, LongMemEval, and BEAM slices, and that the
    MemoryArena/AMA installed CLI smoke path can execute. It is not leaderboard
    or public performance evidence.
- Required fix:
  - Keep this separate from the full prepublish benchmark gate; smoke output is
    not public performance evidence.

10a. Cheap release-surface audit is repeatable
- Evidence:
  - `tools/release_surface_audit.ps1` checks clean git state, tracked file size,
    license/package metadata consistency, tracked Markdown local links, obvious
    private secret patterns, dummy-only benchmark API key usage,
    `tools/verify_benchmark_isolation.py` benchmark source isolation from
    general runtime modules, Docker availability, checked-in compose/env
    consistency, fresh-clone
    install/import/CLI metadata surfaces, and installed MCP stdio startup/tool
    listing.
  - For local development shells only, the audit supports `-AllowDirtyWorktree`
    and `-SkipDocker`. Those switches record `allow_dirty_worktree=true` and
    `skip_docker=true` in JSON, list skipped checks under `checks_skipped`, set
    `release_ready_evidence=false` with `evidence_scope=scoped`, and must not be
    used as public release evidence.
  - `tools/verify_release_audit_evidence.py` validates audit JSON in
    `--mode release` before public use: it rejects skipped checks, failed
    checks, local-only switches, `release_ready_evidence=false`, scoped
    evidence, missing CLI/MCP smoke evidence, and stale audit JSON that lacks
    the benchmark-isolation check under `checks_passed`. Required CLI/MCP smoke
    entries must include command provenance, corpus id, MapU version, git SHA,
    and passing required checks; `{kind,status}` stubs are not evidence.
  - 2026-05-15 fast run with `-SkipFreshInstall` correctly failed while this
    script was uncommitted and Docker was unavailable; Docker remains the real
    unresolved external-startup blocker on this host.
  - 2026-05-15 clean fast run at `abc29222fb948e62bcf9f19b690847692a8df92c`
    passed clean git, tracked-size, private-secret, and dummy-key checks, then
    failed only because `docker` was not available in the active shell.
  - 2026-05-15 portability hardening: fresh-install audit no longer hardcodes
    the Windows `py -3.13` launcher; it supports `-Python <path>`, falls back to
    `python`, and handles Windows/POSIX virtualenv script paths.
  - 2026-05-15 full run at `72a9d0be1af6cedce2e867da892e55542174a173`
    passed clean git, tracked-size, private-secret, dummy-key, and fresh-clone
    install/import/CLI checks; it failed only because `docker` was unavailable.
  - 2026-05-15 full run at `31d093e907cd1b4f6ed6b6fe1568b443dad10b11`
    passed clean git, tracked-size, private-secret, dummy-key, checked-in
    compose/env consistency, and fresh-clone install/import/CLI checks; it
    failed only because `docker` was unavailable.
  - 2026-05-15 full run at `0cb3482e3595aab902d71203a58c656bb45dd6e7`
    passed clean git, tracked-size, license/package metadata, tracked Markdown
    local-link, private-secret, dummy-key, checked-in compose/env consistency,
    and fresh-clone install/import/CLI checks; it failed only because `docker`
    was unavailable.
  - 2026-05-15 full run at `df77e8b501a870a6494ccf8293fe31fa6c3e55c0`
    passed clean git, tracked-size, license/package metadata, tracked Markdown
    local-link, private-secret, dummy-key, checked-in compose/env consistency,
    and fresh-clone install/import/CLI/MCP stdio checks; it failed only because
    `docker` was unavailable.
  - 2026-05-15 full run at `4adc41a5ecca36201bd2f29b2437a4db7af57631`
    passed clean git, tracked-size, license/package metadata, tracked Markdown
    local-link, private-secret, dummy-key, checked-in compose/env consistency,
    and fresh-clone install/import/CLI/MCP stdio checks; it failed only because
    `docker` was unavailable.
- Status: PARTIAL
- Required fix:
  - Run `powershell -NoProfile -ExecutionPolicy Bypass -File tools\release_surface_audit.ps1`
    successfully on a host with Docker available before calling the repo
    release-ready.
  - Run `python -m pytest -m integration` on a Docker-enabled host to cover the
    PostgreSQL/testcontainers integration suite that default pytest deselects.

11. Clean package build works
- Evidence:
  - Executed `python -m build --wheel`
  - Result: `Successfully built mapu-0.1.0-py3-none-any.whl`
  - 2026-05-15 current environment check found `build` was missing from the
    venv despite the README documenting `python -m build --wheel`; fixed by
    adding `build>=1.3,<2` to both dev dependency declarations.
  - 2026-05-15 verified wheel build with:
    `uv run --with "build>=1.3,<2" python -m build --wheel`
    -> `Successfully built mapu-0.1.0-py3-none-any.whl`
  - 2026-05-15 package metadata check: name `mapu`, version `0.1.0`, license `AGPL-3.0-only`, Python `>=3.12,<3.15`
  - 2026-05-15 release audit now checks that tracked `LICENSE` exists and
    matches the package metadata's `AGPL-3.0-only` declaration.
  - 2026-05-15 wheel inspection verified `License-Expression:
    AGPL-3.0-only`, `License-File: LICENSE`, and packaged license file
    `mapu-0.1.0.dist-info/licenses/LICENSE`.
  - 2026-05-15 external-install audit from ignored fresh clone:
    - `py -3.13 -m venv .tmp/release-audit-install/venv`
    - `python -m pip install .tmp/release-audit-install/checkout`
    - installed wheel: `mapu-0.1.0-py3-none-any.whl`
    - installed imports from site-packages: `mapu`, `mapu.cli`, `mapu.api.app`, `mapu.mcp.server`
    - installed console entry point works: `mapu --help`, `mapu corpus --help`, `mapu serve --help`, `mapu mcp --help`
    - installed metadata emits `License-Expression: AGPL-3.0-only`, `License-File: LICENSE`, and `Requires-Python: <3.15,>=3.12`
  - 2026-05-15 repeatable public GitHub install audit added:
    `tools/public_github_install_audit.ps1`.
  - 2026-05-15 script fix: MCP stdio smoke now runs from the cloned public
    checkout instead of the local working tree.
  - Exact-SHA public-install evidence must come from rerunning
    `tools/public_github_install_audit.ps1` against public `main` after the
    final commit is pushed. A passing run covers public clone, venv creation,
    `pip install`, import/metadata checks, CLI help checks, and installed MCP
    stdio smoke. Its JSON embeds installed CLI help command evidence and the
    MCP list-only smoke report; `tools/verify_public_install_audit_evidence.py`
    rejects check-name-only summaries.
  - Earlier one-off and pre-fix public-install checks also passed, but the
    repeatable script above is the relevant path for final release evidence.
  - 2026-05-15 release audit can now write `-OutputJson <path>` summaries
    containing commit SHA, pass/fail status, skipped fresh-install state, passed
    checks, and failed checks. This is intended for final release evidence.
- Status: PASS

12. Local environment and migrations use documented config
- Evidence:
  - `.env.example` added
  - 2026-05-15 `.env.example` expanded to cover database, embeddings,
    chunking, parser/source policy, extraction, LLM, query synthesis, and
    server auth/CORS settings from `src/mapu/config.py`
  - 2026-05-15 implementation fix: `MAPU_SERVER_CORS_ORIGINS` is now wired into
    Litestar `CORSConfig`; focused API tests cover API-key state and CORS
    parsing.
  - 2026-05-15 REST request-level tests cover `/health`, missing API-key
    rejection, and matching API-key acceptance via Litestar `TestClient`.
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
- Follow-up 2026-05-15 non-integration suite at `d167c7977e8ad4792b730fa477d7c405e4626562`:
  `.venv\Scripts\python.exe -m pytest` -> `557 passed, 55 deselected`
- Follow-up 2026-05-15 non-integration suite after reset/delete guard coverage:
  `.venv\Scripts\python.exe -m pytest` -> `563 passed, 55 deselected`
- Follow-up 2026-05-15 non-integration suite after REST request-level coverage:
  `.venv\Scripts\python.exe -m pytest` -> `566 passed, 55 deselected`
- Follow-up 2026-05-15 non-integration suite after MCP stdio smoke helper coverage:
  `.venv\Scripts\python.exe -m pytest` -> `569 passed, 55 deselected`
- Follow-up 2026-05-15 non-integration suite at `cafce2773bcebbc9939248aceb40628b6f17704c`:
  `.venv\Scripts\python.exe -m pytest` -> `569 passed, 55 deselected`
- Follow-up 2026-05-15 non-integration suite after env-example drift coverage:
  `.venv\Scripts\python.exe -m pytest` -> `570 passed, 55 deselected`
- Status: PASS

14. Generated and heavyweight artifacts are excluded from public release
- Evidence:
  - `.gitignore` excludes `results/`, `datasets/`, `logs/`, `dist/`, `.tmp/`, `.uv-cache/`, `.codex_tmp/`
  - `LOCAL_ARTIFACT_POLICY.md` documents expected ignored local directories and
    why `.tmp/memory-benchmarks` is preserved by cleanup.
  - Measured local generated size before exclusion: `results/` about 1.1GB, `datasets/` about 1.05GB
  - 2026-05-15 tracked-file size scan found no committed files over 1MB
  - 2026-05-15 secret-pattern scan found only dummy benchmark keys, example text, and test fixture references; no real key material detected
  - `tools/clean_local_artifacts.ps1` removes disposable local caches while preserving `.tmp/memory-benchmarks`, which benchmark tools require.
- Status: PASS

## Release Gate

Do not call this repository fully public ready until every PARTIAL item is
closed by exact-release evidence on the final public commit.

Current handoff state:
- Check the current local and public heads with:
  `git rev-parse HEAD`
  `git ls-remote origin refs/heads/main`
- Repository visibility checked before pause: public at
  `https://github.com/dl1683/MapU`.
- Branch note: local branch is `master` tracking remote default branch
  `origin/main`; use `git push origin HEAD:main` unless the local branch is
  renamed.
- Current release-surface audit command with DB-backed CLI and DB-backed MCP stdio e2e smoke:
  `powershell -NoProfile -ExecutionPolicy Bypass -File tools\release_surface_audit.ps1 -RunCliE2E -RunMcpE2E -OutputJson .tmp\release_surface_audit_summary.json`
- Local development CLI/MCP plus working-tree install audit for dirty or no-Docker shells:
  `powershell -NoProfile -ExecutionPolicy Bypass -File tools\release_surface_audit.ps1 -SkipDocker -AllowDirtyWorktree -InstallFromWorkingTree -RunCliE2E -RunMcpE2E -OutputJson .tmp\release_surface_audit_summary.json`
- Current public-install audit command:
  `powershell -NoProfile -ExecutionPolicy Bypass -File tools\public_github_install_audit.ps1 -OutputJson .tmp\public_github_install_audit_summary.json`
- Current public-install audit verifier:
  `uv run python tools\verify_public_install_audit_evidence.py .tmp\public_github_install_audit_summary.json`
- Docker blocker command to rerun on a Docker-enabled host:
  `powershell -NoProfile -ExecutionPolicy Bypass -File tools\release_surface_audit.ps1 -OutputJson .tmp\release_surface_audit_summary.json`
- Full benchmark blocker command:
  `powershell -NoProfile -ExecutionPolicy Bypass -File tools\prepublish_benchmark_gate.ps1 -Parallel -MaxParallel 3 -IdleTimeoutMinutes 20`
- Full benchmark evidence verifier:
  `uv run python tools\verify_prepublish_benchmark_evidence.py logs\benchmarks\<gate>\gate_meta.json --require-public-evidence-labels`
- Detached full benchmark blocker command:
  `powershell -NoProfile -ExecutionPolicy Bypass -File tools\start_prepublish_benchmark_gate.ps1 -Parallel -MaxParallel 3 -IdleTimeoutMinutes 20`
- Full benchmark progress command:
  `powershell -NoProfile -ExecutionPolicy Bypass -File tools\check_full_sweep_progress.ps1`
  This command reports code identity, gate metadata status, active/dead worker
  state, completion counts, and a verdict. Use `-Json` for machine-readable
  status, then validate captured JSON with
  `uv run python tools\verify_full_sweep_progress.py <progress.json>`. Only a
  passing `--require-public-evidence` verifier result can support public
  benchmark evidence; stale, incomplete, or running status is a monitoring aid.
- Smoke-only benchmark command:
  `powershell -NoProfile -ExecutionPolicy Bypass -File tools\benchmark_smoke_gate.ps1 -TimeoutMinutes 45`
- Smoke-only evidence note:
  smoke logs are ignored local artifacts. Rerun the smoke command on the exact
  commit being audited and inspect `gate_meta.json`; it must show
  `gate_pass=true`, `worktree=clean`, `smoke_only=true`, and
  `public_performance_evidence=false`.
- Prior full prepublish gate state:
  `logs/benchmarks/prepublish_gate_20260515_190928` confirmed the child-worker
  idle fix but was manually stopped because the full BEAM 100K lane remained too
  slow for a practical prepublish run on this host/model stack. It is not public
  benchmark evidence.
- 2026-05-15 final local process check found no active benchmark/server process
  left running from this audit session.
- If the machine is otherwise free, `-MaxParallel 6` is reasonable to try while
  monitoring responsiveness.
