# MapU

MapU is a persistent context-memory substrate for document-heavy reasoning, with auditable, structured memory as the primary system purpose.

**Primary system priority (May 2026):** MapU exists first as a durable memory layer for agentic systems (Codex/Claude Code-style workflows), then as a benchmark and tooling platform. The highest-priority objective is persistent context continuity across resets.

## What It Is

MapU ingests documents, extracts structured knowledge with provenance, and stores it in a persistent graph-backed system for retrieval and synthesis. It is meant to be used as durable memory for coding agents, research assistants, and document-heavy workflows where answers need to point back to source material instead of only relying on chat context.

For session continuity with terminal agents, the mandatory start state is:

- run `mapu resume <corpus_id> --max-gaps 10 --max-activity 20` (or MCP
  `handoff_context`) first,
- read `open_gaps`, `recent_activity`, and `priority_next_actions`,
- execute those `next_steps` before broad re-read.

Context-map behavior:
- Each query returns the current answer plus `"next_steps"` guidance.
- Guidance is not just "I don't know"; it is either a direct answer, a
  deeper question, or a recommended follow-up action to inspect specific
  entities/documents/actions.
- This supports agent workflows that need both stored knowledge and a next-study
  path without re-reading the entire corpus.

Core properties:
- Source-attributed assertions
- Relation-aware representation of what facts connect, override, or refine each other
- Corpus-local learning continuity with provenance and conflict-aware supersession
- Authority-aware evidence handling
- Temporal validity and repair semantics
- Query + investigation workflows over persistent state
- Reset/delete flows for clean test corpora and repeatable benchmark runs
- MCP, REST, CLI, and Python package surfaces
- Explicit uncertainty and versioned conflict state (not just latest answer)

## Architecture

Main pipeline:
1. Ingest source documents
2. Extract entities/claims/relations
3. Ground into assertions with provenance
4. Store + query over Postgres/pgvector
5. Synthesize answers with epistemic metadata

See [ARCHITECTURE.md](ARCHITECTURE.md) for full system detail.

## Why It Exists

Long-running agents need a memory layer that survives outside one chat window and stays inspectable. MapU treats memory as a source-backed knowledge base:

- documents are parsed into spans/chunks
- claims and relations are extracted into structured records
- every assertion carries provenance and confidence metadata
- query answers can use retrieval, direct lookup, or investigation workflows
- repair/reset paths make it possible to clean up bad state instead of starting from an opaque transcript

## Dynamic Agent Memory Priority

MapU's current highest-priority product objective is a context map for coding and research agents: a durable memory layer that preserves what was learned across sessions, exposes provenance-rich and versioned learning history, and guides the next study action when memory is incomplete.

The goal is not one-time ingestion. It is persistent, repeatable memory that improves with use:
- Long-lived corpora by project/repo
- Durable propositions, relations, and provenance links
- Explicit conflict handling (supersession, change ordering, and evidence updates)
- Active gap-awareness and next-step guidance from query/investigation responses

What is currently implemented:
- long-lived corpora that can accumulate documents over time
- MCP tools for agent-facing ingest, query, investigation, activity, gaps, repair, delete, and reset workflows
- provenance-backed spans, chunks, propositions, attestations, and activity records
- situations, truth states, gaps, changesets, and repair/rollback surfaces for evolving knowledge

What is not yet proven as a public claim:
- autonomous continuous repo-study loops
- longitudinal improvement across repeated agent sessions
- robust stale-memory detection and supersession in real changing repositories (priority 2 now)
- measured agent task lift from MapU memory versus no persistent memory
- storage, latency, update, and repair cost curves over months of accumulated state

## Surfaces In This Repository

- `MCP server` via `mapu mcp`
- `REST API` via `mapu serve`
- `CLI` via `mapu ...`
- `Python package` via `pip install -e .`

API response contracts include next-step guidance for query and investigation paths:
- `query` returns `answer` plus the compatibility alias `synthesis`.
- `query` returns `next_steps: list[str]` on all tiers.
- `query` returns `chunk_hits` when fallback source evidence is available.
- `investigate` returns `next_steps: list[str]` driven by identified gaps and
  termination state.
- `query` and `investigate` also return `structured_next_steps`, preserving
  action type, executable tool call, rationale, uncertainty reason, governance
  tier, and expected uncertainty reduction for agent schedulers.

Note: A GitHub Action surface is not currently shipped in this repository and should not be claimed as available.

## Quick Start

Prerequisites:
- Python `3.12` through `3.14`
- PostgreSQL `15+`
- Docker (recommended for local infra)

```bash
git clone https://github.com/dl1683/MapU.git
cd MapU
pip install -e .
docker compose up -d
cp .env.example .env  # PowerShell: Copy-Item .env.example .env
alembic upgrade head
mapu serve --host 127.0.0.1 --port 8000
```

For contributor checks and local test work, install the development extras:

```bash
pip install -e ".[dev]"
```

MCP server:

```bash
mapu mcp
```

CLI examples:

```bash
mapu corpus create "demo-corpus"
mapu corpus list
mapu ingest <corpus_uuid> ./example.txt
mapu resume <corpus_uuid> --max-gaps 10 --max-activity 20
mapu query <corpus_uuid> "What changed in the contract?"
```

For terminal workflows, JSON automation, activity auditing, and benchmark smoke
commands, see [docs/CLI_OPERATOR_GUIDE.md](docs/CLI_OPERATOR_GUIDE.md).

Reset a test corpus or clean the local knowledge base:

```bash
mapu corpus delete <corpus_uuid> --yes
mapu corpus reset --yes
```

## MCP Usage

MapU is designed to be used by coding agents and IDE assistants through MCP.

Start the server:

```bash
mapu mcp
```

Core MCP tools include:
- `create_corpus`
- `list_corpora`
- `ingest_document`
- `query`
- `investigate`
- `lookup_entity`
- `list_gaps`
- `list_activity`
- `delete_corpus`
- `reset_all_corpora`

For a context reset, start with `mapu resume <corpus_uuid>` and treat the printed
`Priority next actions` as the first thing your next Claude/agent subagent should run.

Minimal smoke workflow:
1. Create a corpus.
2. Ingest a small text document.
3. Query for a fact from that document.
4. Inspect activity and gaps.
5. Run a continuity handoff check before any new context session: inspect unresolved gaps, recent repairs, and supersession edges.
6. Delete the test corpus or reset all corpora.

See [INTEGRATIONS.md](INTEGRATIONS.md) for the agent integration and reset workflow, and [SESSION_CONTINUITY_PROTOCOL.md](SESSION_CONTINUITY_PROTOCOL.md) for resume-first protocol.
The integration docs also define the agent continuity path:
a resumed Claude-style session should start with `mapu resume` or MCP
`handoff_context`, then execute the returned `next_steps` before broad re-reading.

## Current Release Status

This repository is public and usable for exploration, integration work, and development. It is not currently making a public performance or leaderboard claim.

Current verification commands:
- `powershell -NoProfile -ExecutionPolicy Bypass -File tools\release_surface_audit.ps1`
- `powershell -NoProfile -ExecutionPolicy Bypass -File tools\public_github_install_audit.ps1`
- `uv run python tools\verify_public_install_audit_evidence.py .tmp\public_github_install_audit_summary.json`
- `uv run python tools\verify_validation_evidence_bundle.py --mode release --release-audit .tmp\release_surface_audit_summary.json --public-install-audit .tmp\public_github_install_audit_summary.json`
- `uv run python tools\verify_validation_evidence_bundle.py --mode local-dev --release-audit .tmp\release_surface_audit_summary.json`
- `uv run python tools\verify_objective_completion.py --release-audit .tmp\release_surface_audit_summary.json --public-install-audit .tmp\public_github_install_audit_summary.json --benchmark-gate-meta logs\benchmarks\<gate>\gate_meta.json --full-sweep-progress .tmp\full_sweep_progress.json --continuity-replay results\continuity_replay_harness.json`
- `uv run python tools\verify_objective_completion.py --format text`
- `uv run python tools\verify_objective_completion.py --format commit-plan`
- `uv run python tools\verify_objective_completion.py --format commit-plan --out .tmp\release_cleanup_commit_plan.md`
- `powershell -NoProfile -ExecutionPolicy Bypass -File tools\release_surface_audit.ps1 -SkipDocker -AllowDirtyWorktree -InstallFromWorkingTree -RunCliE2E -RunMcpE2E -OutputJson .tmp\release_surface_audit_summary.json`
- `mapu doctor --json`
- `uv run python tools/cli_e2e_smoke.py --command uv --arg run --arg mapu --json`
- `uv run python tools/mcp_stdio_smoke.py --command uv --arg run --arg mapu --arg mcp --json`
- `python -m pytest`
- `python -m build --wheel`
- `powershell -NoProfile -ExecutionPolicy Bypass -File tools\benchmark_smoke_gate.ps1`

What those checks cover:
- package wheel build and install metadata
- CLI, REST, MCP, and reset/delete surfaces
- real CLI continuity loop: create -> ingest -> resume -> query -> activity -> delete
- request-level `/health` and API-key guard behavior
- real MCP stdio loop: create -> ingest -> contribute -> review -> query -> activity -> delete
- tracked-file artifact hygiene, local-link checks, license metadata, and secret-pattern scans

When a local MapU database is configured, include the DB-backed CLI and MCP
continuity loops in the release surface audit:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\release_surface_audit.ps1 -RunCliE2E -RunMcpE2E -OutputJson .tmp\release_surface_audit_summary.json
```

For dirty/no-Docker development shells, use the explicit local-only switches so
the JSON evidence records `release_ready_evidence=false` with
`evidence_scope=scoped`, proves the current working tree can install into a
temporary venv, and cannot be mistaken for release readiness:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\release_surface_audit.ps1 -SkipDocker -AllowDirtyWorktree -InstallFromWorkingTree -RunCliE2E -RunMcpE2E -OutputJson .tmp\release_surface_audit_summary.json
```

Verify release-audit JSON before treating it as evidence:

```powershell
uv run python tools\verify_release_audit_evidence.py .tmp\release_surface_audit_summary.json --mode release --require-cli-e2e --require-mcp-e2e
```

Known limitations before making stronger public claims:
- full exact-code prepublish benchmark gate still failed on the most recent run (`locomo_full_qwen06` exited `-1` during the full run on `2026-05-16_001848`)
- Docker was not available in the last active shell, so the documented `docker compose` path needs to be reverified on a host with Docker installed
- LoCoMo, LongMemEval, and BEAM remain the long-running public-evidence harnesses; MemoryArena and AMA-Bench are now installed CLI smoke/diagnostic lanes, not public performance evidence
- smoke gate has recently passed on a health-check run for this checkout; this is not public performance evidence and does not replace full benchmark gate.

## Two-Year Validation Direction

MapU's longer-term goal is to prove persistent memory inside real existing repositories, not only on standalone memory benchmarks. The validation program should test:

- compatibility with real codebases, docs, tests, issue histories, and agent workflows
- MCP usage from coding agents and IDE assistants
- ingest cost, storage growth, retrieval latency, update cost, and reset/repair cost
- quality of stored entities, claims, relations, temporal facts, provenance, and stale-memory handling
- agent task quality with and without MapU on bug diagnosis, refactor planning, documentation, benchmark triage, and release audits

See [PRIORITIES.md](PRIORITIES.md) for the full two-year validation lane.
That lane prioritizes terminal-driven Gemini and Claude Code subagent trials for
durable-memory handoff quality over benchmark-only validation.
See [AGENT_MEMORY_VALIDATION.md](AGENT_MEMORY_VALIDATION.md) for the current
agent-memory validation checklist, terminal-review snapshot, and claim boundary.
See [VALIDATION_EVIDENCE_MATRIX.md](docs/VALIDATION_EVIDENCE_MATRIX.md) for the
current prompt-to-artifact checklist that separates CLI/MCP product evidence,
fresh-install checks, smoke benchmarks, and public benchmark evidence.
For non-benchmark agent-memory quality, use the continuity replay harness with
`--require-response-quality-gate`; replayed query/investigation actions must
return answer text, next-step guidance, and evidence signals before the harness
passes.

## Benchmarks And Claims

Benchmark artifacts and status are tracked in:
- [GLOBAL_MEMORY_BENCHMARK_STATUS.md](GLOBAL_MEMORY_BENCHMARK_STATUS.md)
- [GLOBAL_MEMORY_BENCHMARK_EXECUTION_PLAN.md](GLOBAL_MEMORY_BENCHMARK_EXECUTION_PLAN.md)
- [docs/MEMORY_BENCHMARKS.md](docs/MEMORY_BENCHMARKS.md)
- [LOCAL_ARTIFACT_POLICY.md](LOCAL_ARTIFACT_POLICY.md)
- `tools/benchmark_smoke_gate.ps1`
- `tools/prepublish_benchmark_gate.ps1`
- `tools/report_full_sweep_leaderboard.py`
- `mapu eval memory-benchmark-smoke`

Claim discipline:
- This README intentionally does not publish earlier local benchmark scores. Some earlier runs were useful engineering diagnostics, but they predated hardening changes or used proxy/scaffolded paths and are not acceptable public evidence.
- Distinguish `proxy retrieval` metrics from `full benchmark leaderboard` runs.
- Public claims should cite exact artifact files and timestamps.
- Release artifacts are generated locally by the prepublish gate; large `results/` and `datasets/` directories are not intended to be committed.
- Do not generalize benchmark wins to unrelated domain tasks without direct evidence.
- Use `tools/continuity_replay_harness.py --require-response-quality-gate` on
  real corpora before treating benchmark smoke as evidence of general-purpose
  agent-memory quality.
- Benchmark adapters must not inject query-specific gold hints into retrieval outputs.
- Benchmark-specific identifiers must stay out of general runtime modules. Run
  `uv run python tools\verify_benchmark_isolation.py --json` after touching
  benchmark adapters, retrieval, query, or CLI eval code.

Before publishing any benchmark number, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\prepublish_benchmark_gate.ps1 -Parallel -MaxParallel 3 -IdleTimeoutMinutes 20
```

For a long background run, start it through the launcher so the suffix,
progress command, resume command, PID, and logs are captured immediately:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\start_prepublish_benchmark_gate.ps1 -Parallel -MaxParallel 3 -IdleTimeoutMinutes 20
```

The progress checker reads the latest launcher metadata by default, or a pinned
metadata file when supplied:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\check_full_sweep_progress.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File tools\check_full_sweep_progress.ps1 -LauncherMetadata logs\benchmarks\prepublish_gate_launcher_yyyyMMdd_HHmmss.json -Json
```

If a long public gate is interrupted, resume the same exact-code artifact set
instead of starting a fresh suffix:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\prepublish_benchmark_gate.ps1 -Parallel -MaxParallel 3 -IdleTimeoutMinutes 20 -ProjectSuffix prepublish_yyyyMMdd_HHmmss -Resume
```

Resume requires an explicit `-ProjectSuffix` and refuses to reuse existing gate
artifacts when the saved code identity does not match the current commit and
worktree state. This keeps interrupted full sweeps operationally recoverable
without mixing evidence from different code.

Then verify the gate metadata before citing it:

```powershell
uv run python tools\verify_prepublish_benchmark_evidence.py logs\benchmarks\<gate>\gate_meta.json --require-public-evidence-labels
```

The prepublish gate also runs that verifier before printing `PREPUBLISH
BENCHMARK GATE: PASS` and records the verifier output path in `gate_meta.json`
as `benchmark_evidence_verifier`. Non-claim paths keep
`public_performance_evidence=false`; only a verified full gate sets
`public_performance_evidence=true` and `benchmark_evidence_verified=true`.
The gate writes `gate_meta.json` before launching expensive lanes with
`status=running`, so interrupted runs remain auditable and explicitly unfit for
public claims. Later states include `sweep_complete_unverified`, `passed`,
`failed`, and `preflight_only`.

The gate preflights the local OpenAI-compatible model endpoint at
`http://localhost:11434/v1/models` and the MapU database configured by
`MAPU_DB_URL` before launching expensive lanes. The benchmark scripts still
receive `--mem0-host http://localhost:8000`, but the wrapper replaces the
external Mem0 client with MapU's in-process adapter, so the live memory
dependency is the MapU database, not a mem0 HTTP server. The prepublish gate
passes that legacy host value through the sweep runners as
`BenchmarkMem0HostArg` and records it in `gate_meta.json` for command-surface
auditability. On an otherwise free machine, a higher setting such as
`-MaxParallel 6` may be reasonable while
monitoring host responsiveness. The parallel gate treats null exit codes, lane
wall-clock timeouts, and idle lanes as failures instead of letting a stuck
benchmark burn compute indefinitely. Each lane keeps stdout, stderr, and
metadata under the `lane_artifact_dir` recorded in `gate_meta.json`.
Use `-PreflightOnly` to verify local services and write auditable gate metadata
without launching benchmark lanes.

For a quick harness sanity check that is explicitly not performance evidence:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\benchmark_smoke_gate.ps1
uv run --with datasets mapu eval memory-benchmark-smoke --out-dir .tmp/benchmark-live-smoke --memoryarena-limit-per-config 1 --ama-limit 1 --min-token-f1 0.45
```

Smoke logs are ignored local artifacts. The MemoryArena/AMA smoke command keeps
stdout to one JSON summary by default and captures adapter step output in
`smoke_report.json`; use `--verbose-steps` only for debugging. Inspect
`smoke_report.json.inputs` for the actual scenario files, `paths` for generated
artifacts, and `score_summary` for the aggregate gate result; use
`threshold_metric` and `threshold` when reading non-exact metrics. The report
also records `worktree_status_porcelain`, `worktree_dirty_path_count`,
`worktree_fingerprint_sha256`, and `worktree_fingerprint_errors`. Rerun the
smoke after source edits: `verify_objective_completion.py` rejects stale
benchmark smoke whose fingerprint no longer matches the current checkout.
This stale benchmark smoke guard prevents old smoke scores from standing in for
current-code evidence.
MemoryArena also has an experimental `--predictor web_grounded` lane for
source-free questions; it records source metadata but is not release evidence
unless it clears the normal gate on the audited commit without diagnostic
methods. For release evidence, rerun the smoke gate on the exact commit being
audited and inspect its `gate_meta.json`. A passing smoke confirms only the
wrapper/local-endpoint path for tiny LoCoMo, LongMemEval, and BEAM 100K slices,
plus the installed MemoryArena/AMA-Bench CLI export/predict/score/gate path; it
is not leaderboard or public performance evidence.

## Domain Modeling Reference

See [DOMAINS.md](DOMAINS.md) for domain-oriented modeling references.

## Development Notes

Useful local checks:

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File tools\release_surface_audit.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File tools\public_github_install_audit.ps1
python -m mapu.cli --help
python -m pytest
python -m build --wheel
```

The default pytest command excludes Docker-backed integration tests. On a host
with Docker available, run the PostgreSQL/testcontainers suite explicitly:

```bash
python -m pytest -m integration
```

For the full release audit state, see [PUBLIC_RELEASE_AUDIT.md](PUBLIC_RELEASE_AUDIT.md).

## License

AGPL-3.0-only. See [LICENSE](LICENSE).
