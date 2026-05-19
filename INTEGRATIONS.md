# MapU Integrations

## Goal

Use MapU from external coding agents and IDE assistants through MCP, not only through the local CLI.

Primary contract for this integration: treat MapU as a durable context-memory substrate.
Default integration patterns should favor corpus reuse, evidence inspection, and
`next_steps`-driven follow-up over re-ingesting everything every session.

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

Verify the installed stdio path and DB-backed MCP continuity workflow with:

```bash
uv run python tools/mcp_stdio_smoke.py --command uv --arg run --arg mapu --arg mcp --json
```

For fresh-install checks where no database is configured yet, use `--list-only`
to validate startup and tool discovery without executing the workflow.

Core tools exposed include:
- `create_corpus`
- `list_corpora`
- `ingest_document`
- `contribute_proposition`
- `review_attestation`
- `query`
- `investigate`
- `lookup_entity`
- `list_gaps`
- `list_activity`
- `log_learning_feedback`
- `repair_preview`
- `repair_apply`
- `repair_rollback`
- `delete_corpus`
- `reset_all_corpora`
- `handoff_context`

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
4. `query(corpus_id=..., question="What should I learn next?")`
5. `list_activity(corpus_id=...)`
6. `list_gaps(corpus_id=...)`
7. `delete_corpus(corpus_id=..., confirm=true)` or `reset_all_corpora(confirm=true)`

After the same evidence set is available in MapU, run:

```bash
mapu resume <corpus_uuid> --max-gaps 10 --max-activity 20
```

Use that output as the first-context action list for a fresh Claude subagent.

Expected behavior:
- ingest returns non-zero spans/chunks/embeddings
- query returns `answer` plus the compatibility alias `synthesis`; when only
  source chunks are available, the answer should be a cautious evidence excerpt
  rather than a blank string
- query includes `chunk_hits` so agents can inspect fallback source evidence
  before escalating to broad rereads
- query returns answer text aligned with ingested evidence and `next_steps` guidance
- query and investigation return `structured_next_steps` for executable
  agent follow-up without parsing prose
- next query moves to explicit follow-up paths when memory is incomplete
- activity includes ingestion/query/revision events
- gaps should be discoverable before deciding to ingest new sources
- resumed handoff includes `frontier_completeness`, `continuity_status`,
  structured gap contracts, and actionable `priority_next_actions`

## 5) Session continuity handoff protocol (mandatory for agent sessions)

Start every context reset by running:

```bash
mapu resume <corpus_id> --max-gaps 10 --max-activity 20
```

When context is reset, run this protocol before broad re-ingest:
1. Reopen the intended corpus and validate corpus identity.
2. Run `list_gaps` to recover unresolved uncertainty and missing evidence links.
3. Run `list_activity` to recover repair history, revisions, and supersession edges.
4. Query highest-impact gaps directly and follow `next_steps` to the evidence location with the best expected gain.
5. Only ingest new sources when the handoff surfaces mark a gap as missing or contradicted by current state.

For each open gap, inspect the persisted contract fields before broad reads:
`uncertainty_reason`, `evidence_hypothesis`, `next_action`,
`expected_resolution`, `governance_tier`, and `missing_contract_fields`.
If the contract itself is partial, first repair the memory frontier by adding a
specific evidence hypothesis and action target.

## 6) Notes for agent-first usage

- Keep one long-lived corpus per project/repo, not per chat.
- Use `situation_id` when branching hypotheses in one corpus.
- Use reset only for test sandboxes; for production corpora prefer targeted repair flows.
- On context resets, rely on corpus history (`list_activity`, `list_gaps`) and relation-aware follow-up (`query` + `next_steps`) before reprocessing the repository.

## 7) Terminal agent validation for durable memory

MapU's primary validation surface is real agent continuity, not leaderboard
decoration. When available, use terminal-driven Gemini and Claude Code subagent
runs to independently inspect whether MapU works as durable context memory for
agentic workflows.

Validation target:
- A Codex/Claude Code-style agent can reset context and resume from MapU state.
- Prior learning is recovered from persisted facts, relations, provenance,
  uncertainty, conflict/supersession state, activity, and gaps.
- `next_steps` points the new session toward the highest-value evidence instead
  of forcing broad rediscovery.
- Contradictory or outdated claims are visible and reviewable.

Preferred trial shape:
1. Create or reuse a long-lived project corpus.
2. Ingest project evidence from real files/docs/tasks.
3. Simulate context reset by starting a separate terminal agent session.
4. Ask Gemini through the terminal to inspect the MapU handoff quality.
5. Ask Claude Code subagents through the terminal to inspect the same handoff.
6. Require each agent to use `query`, `list_activity`, `list_gaps`, and
   `next_steps` before re-reading broad source material.
7. Record whether the resumed agent avoided rediscovery, cited provenance, and
   surfaced uncertainty/conflicts/supersession correctly.

Treat these terminal-agent trials as core product validation. Run benchmark gates
only when the question is benchmark evidence or release claims.

## 8) Replay harness for continuity validation

Use this local harness to measure whether a resumed session follows `handoff`
actions versus broad rediscovery:

```bash
python -m tools.continuity_replay_harness.py --corpus-id <uuid> --max-gaps 10 --max-activity 20 --max-actions 8 --out results/continuity_replay.json
```

Use `--no-lifecycle-query` only for dry-run artifact generation.
Use `--require-frontier-completeness-gate` when the handoff itself must fail on
partial gap contracts before any lifecycle queries run.

Review `results/continuity_replay.json` for:

- `continuity_frontier.open_gap_count`
- `continuity_frontier.frontier_completeness`
- `continuity_frontier.missing_gap_contract_count`
- `continuity_frontier.evidence_anchor_count`
- `hand-off` confidence spread
- `session2.handoff_action_count`
- `handoff_effect.estimated_read_delta` (target reduction in repeated read calls for resumed workflow)
- `resumed_with_handoff`

## 9) Continuous hardened benchmark validation

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

## 10) Benchmark gates and public claims

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
Partial counts from stale/ interrupted gates are not public performance evidence.

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
