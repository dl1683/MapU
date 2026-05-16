# MapU

Persistent knowledge substrate for document-heavy reasoning, agent memory, and evidence-backed synthesis.

## What It Is

MapU ingests documents, extracts structured knowledge with provenance, and stores it in a persistent graph-backed system for retrieval and synthesis. It is meant to be used as durable memory for coding agents, research assistants, and document-heavy workflows where answers need to point back to source material instead of only relying on chat context.

Core properties:
- Source-attributed assertions
- Authority-aware evidence handling
- Temporal validity and repair semantics
- Query + investigation workflows over persistent state
- Reset/delete flows for clean test corpora and repeatable benchmark runs
- MCP, REST, CLI, and Python package surfaces

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

## Surfaces In This Repository

- `MCP server` via `mapu mcp`
- `REST API` via `mapu serve`
- `CLI` via `mapu ...`
- `Python package` via `pip install -e .`

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
mapu query <corpus_uuid> "What changed in the contract?"
```

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

Minimal smoke workflow:
1. Create a corpus.
2. Ingest a small text document.
3. Query for a fact from that document.
4. Inspect activity/gaps.
5. Delete the test corpus or reset all corpora.

See [INTEGRATIONS.md](INTEGRATIONS.md) for the agent integration and reset workflow.

## Current Release Status

This repository is public and usable for exploration, integration work, and development. It is not currently making a public SOTA or leaderboard performance claim.

Verified before the current pause:
- package wheel build completed successfully
- editable dev install metadata resolved
- CLI help and corpus reset/delete help load
- REST API app import works, and `/health` plus API-key guard behavior are
  covered by request-level tests
- MCP server module imports and exposes the server/run entrypoints; installed
  stdio startup/tool listing is covered by `tools/mcp_stdio_smoke.py`
- focused CLI/API/MCP unit surface passes
- full non-integration suite passed on 2026-05-15 with `566 passed, 55 deselected`
- tracked generated artifacts and heavyweight benchmark outputs are excluded from the public repo

Known limitations before making stronger public claims:
- the full exact-code prepublish benchmark gate has not completed successfully
- Docker was not available in the last active shell, so the documented `docker compose` path needs to be reverified on a host with Docker installed
- only `LoCoMo`, `LongMemEval`, and `BEAM` are currently integrated in the MapU benchmark harness; additional memory benchmarks remain planned

## Two-Year Validation Direction

MapU's longer-term goal is to prove persistent memory inside real existing repositories, not only on standalone memory benchmarks. The validation program should test:

- compatibility with real codebases, docs, tests, issue histories, and agent workflows
- MCP usage from coding agents and IDE assistants
- ingest cost, storage growth, retrieval latency, update cost, and reset/repair cost
- quality of stored entities, claims, relations, temporal facts, provenance, and stale-memory handling
- agent task quality with and without MapU on bug diagnosis, refactor planning, documentation, benchmark triage, and release audits

See [PRIORITIES.md](PRIORITIES.md) for the full two-year validation lane.

## Benchmarks And Claims

Benchmark artifacts and status are tracked in:
- [GLOBAL_MEMORY_BENCHMARK_STATUS.md](GLOBAL_MEMORY_BENCHMARK_STATUS.md)
- [GLOBAL_MEMORY_BENCHMARK_EXECUTION_PLAN.md](GLOBAL_MEMORY_BENCHMARK_EXECUTION_PLAN.md)
- `tools/benchmark_smoke_gate.ps1`
- `tools/prepublish_benchmark_gate.ps1`
- `tools/report_full_sweep_leaderboard.py`

Claim discipline:
- This README intentionally does not publish earlier local benchmark scores. Some earlier runs were useful engineering diagnostics, but they predated hardening changes or used proxy/scaffolded paths and are not acceptable public evidence.
- Distinguish `proxy retrieval` metrics from `full benchmark leaderboard` runs.
- Public claims should cite exact artifact files and timestamps.
- Release artifacts are generated locally by the prepublish gate; large `results/` and `datasets/` directories are not intended to be committed.
- Do not generalize benchmark wins to unrelated domain tasks without direct evidence.
- Benchmark adapters must not inject query-specific gold hints into retrieval outputs.

Before publishing any benchmark number, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\prepublish_benchmark_gate.ps1 -Parallel -MaxParallel 3 -IdleTimeoutMinutes 20
```

On an otherwise free machine, a higher setting such as `-MaxParallel 6` may be reasonable while monitoring host responsiveness. The parallel gate treats null exit codes, lane wall-clock timeouts, and idle lanes as failures instead of letting a stuck benchmark burn compute indefinitely.

For a quick harness sanity check that is explicitly not performance evidence:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\benchmark_smoke_gate.ps1
```

Latest smoke status: the harness smoke gate passed on clean commit
`f22bb3d41631daebadfe8ac7b36f96c9e05a86c6` at
`logs/benchmarks/benchmark_smoke_gate_20260515_221231`, covering tiny LoCoMo,
LongMemEval, and BEAM 100K slices. That confirms the wrapper/local-endpoint path
is functioning, but it is not leaderboard or public performance evidence.

## Domain Modeling Reference

See [DOMAINS.md](DOMAINS.md) for domain-oriented modeling references.

## Development Notes

Useful local checks:

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File tools\release_surface_audit.ps1
python -m mapu.cli --help
python -m pytest
python -m build --wheel
```

For the full release audit state, see [PUBLIC_RELEASE_AUDIT.md](PUBLIC_RELEASE_AUDIT.md).

## License

AGPL-3.0-only. See [LICENSE](LICENSE).
