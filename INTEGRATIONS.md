# MapU Integrations

## Goal

Use MapU from external coding agents and IDE assistants through MCP, not only through the local CLI.

## 1) Start MapU backend

```bash
docker compose up -d
alembic upgrade head
```

Docker-backed integration tests are deselected from the default pytest command.
After Docker is available, run:

```bash
python -m pytest -m integration
```

## 2) MCP surface (primary integration path)

MapU exposes MCP over stdio via:

```bash
mapu mcp
```

Core tools exposed include:
- `create_corpus`
- `list_corpora`
- `query`
- `ingest_document`
- `investigate`
- `lookup_entity`
- `list_gaps`
- `list_activity`
- `delete_corpus`
- `reset_all_corpora`

## 3) Clean start / reset flows

CLI:

```bash
mapu corpus reset --yes
mapu corpus delete <corpus_id> --yes
```

MCP:
- `reset_all_corpora(confirm=true)`
- `delete_corpus(corpus_id=<uuid>, confirm=true)`

Both are destructive by design and require explicit confirmation flags.

## 4) Minimal smoke workflow for any MCP client

1. `create_corpus(name="smoke", description="integration smoke")`
2. `ingest_document(corpus_id=..., content="Alice joined Acme in 2022.", mime_type="text/plain")`
3. `query(corpus_id=..., question="When did Alice join Acme?")`
4. `list_activity(corpus_id=...)`
5. `delete_corpus(corpus_id=..., confirm=true)` or `reset_all_corpora(confirm=true)`

Expected behavior:
- ingest returns non-zero spans/chunks/embeddings
- query returns synthesis or hits aligned with ingested fact
- activity includes ingestion/query events

## 5) Notes for agent-first usage

- Keep one long-lived corpus per project/repo, not per chat.
- Use `situation_id` when branching hypotheses in one corpus.
- Use reset only for test sandboxes; for production corpora prefer targeted repair flows.

## 6) Continuous hardened benchmark validation

Start background continuous loop:

```bash
powershell -ExecutionPolicy Bypass -File tools/start_continuous_hardened_benchmarks.ps1
```

Behavior:
- runs full hardened leaderboard sweeps in a loop
- writes per-cycle logs under `logs/benchmarks/`
- writes leaderboard snapshots per cycle
- appends pass/fail cycle state to `logs/benchmarks/continuous_hardened_status.log`

Default interval is 30 minutes. Override with:
- `MAPU_CONTINUOUS_BENCH_INTERVAL_MINUTES=<n>`

## 7) Benchmark gates and public claims

Run this full gate immediately before public release or benchmark claim updates:

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File tools/prepublish_benchmark_gate.ps1
```

For a conservative bounded parallel run:

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File tools/prepublish_benchmark_gate.ps1 -Parallel -MaxParallel 3 -IdleTimeoutMinutes 20
```

For a detached long run that writes launcher logs under `logs/benchmarks/`:

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File tools/start_prepublish_benchmark_gate.ps1 -Parallel -MaxParallel 3 -IdleTimeoutMinutes 20
```

Monitor the latest full/prepublish sweep:

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File tools/check_full_sweep_progress.ps1
```

For machine-readable status:

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File tools/check_full_sweep_progress.ps1 -Json
```

The progress checker reports code identity, gate metadata status, recorded
worker PIDs, active/dead worker state, result counts, and an explicit verdict.
Partial counts from a stale or interrupted gate are not public performance
evidence.

Successful full-gate evidence includes:
- benchmarks are run on the current code state
- code identity is recorded (`git sha`, dirty/clean state)
- leaderboard snapshot is generated in the same run
- pass/fail metadata is written to a timestamped gate folder under `logs/benchmarks/`
- null exit codes, lane wall-clock timeouts, and idle lanes fail the gate

For a fast harness sanity check that is explicitly not public performance
evidence:

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File tools/benchmark_smoke_gate.ps1
```

The smoke gate runs tiny LoCoMo, LongMemEval, and BEAM slices through the same
wrapper/local-endpoint path and records `smoke_only=true` plus
`public_performance_evidence=false`.

Operational note:
- `-MaxParallel 6` can be useful on a free machine, but on 2026-05-13 it made the host difficult to control while other heavy processes were running. Match `MaxParallel` to current host load and monitor responsiveness.
