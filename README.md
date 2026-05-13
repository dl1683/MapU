# MapU

Persistent knowledge substrate for document-heavy reasoning.

## What It Is

MapU ingests documents, extracts structured knowledge with provenance, and stores it in a persistent graph-backed system for retrieval and synthesis.

Core properties:
- Source-attributed assertions
- Authority-aware evidence handling
- Temporal validity and repair semantics
- Query + investigation workflows over persistent state

## Architecture

Main pipeline:
1. Ingest source documents
2. Extract entities/claims/relations
3. Ground into assertions with provenance
4. Store + query over Postgres/pgvector
5. Synthesize answers with epistemic metadata

See [ARCHITECTURE.md](ARCHITECTURE.md) for full system detail.

## Surfaces In This Repository

- `MCP server` via `mapu mcp`
- `REST API` via `mapu serve`
- `CLI` via `mapu ...`
- `Python package` via `pip install -e .`

Note: A GitHub Action surface is not currently shipped in this repository and should not be claimed as available.

## Quick Start

Prerequisites:
- Python `3.12+`
- PostgreSQL `15+`
- Docker (recommended for local infra)

```bash
git clone https://github.com/deal1683/MapU.git
cd MapU
pip install -e ".[dev]"
docker compose up -d
cp .env.example .env  # PowerShell: Copy-Item .env.example .env
alembic upgrade head
mapu serve --host 127.0.0.1 --port 8000
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

## Benchmarks And Claims

Benchmark artifacts and status are tracked in:
- [GLOBAL_MEMORY_BENCHMARK_STATUS.md](GLOBAL_MEMORY_BENCHMARK_STATUS.md)
- [GLOBAL_MEMORY_BENCHMARK_EXECUTION_PLAN.md](GLOBAL_MEMORY_BENCHMARK_EXECUTION_PLAN.md)
- `tools/prepublish_benchmark_gate.ps1`
- `tools/report_full_sweep_leaderboard.py`

Claim discipline:
- Distinguish `proxy retrieval` metrics from `full benchmark leaderboard` runs.
- Public claims should cite exact artifact files and timestamps.
- Release artifacts are generated locally by the prepublish gate; large `results/` and `datasets/` directories are not intended to be committed.
- Do not generalize benchmark wins to unrelated domain tasks without direct evidence.
- Benchmark adapters must not inject query-specific gold hints into retrieval outputs.

## Domain Modeling Reference

See [DOMAINS.md](DOMAINS.md) for domain-oriented modeling references.

## License

AGPL-3.0-only. See [LICENSE](LICENSE).
