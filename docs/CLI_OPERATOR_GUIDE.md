# MapU CLI operator guide

This guide is for running MapU from a terminal in a real agent-memory workflow.
Use `--json` whenever another program is consuming output; human text output is
allowed to change.

## Core continuity loop

Create a corpus, ingest source material, then resume before asking broad
questions:

```powershell
mapu corpus create "agent-memory-demo"
mapu ingest <corpus_uuid> .\handoff.md --document-type markdown --source-uri repo://handoff.md
mapu resume <corpus_uuid> --max-gaps 10 --max-activity 20 --json
mapu query <corpus_uuid> "What should the next agent do first?" --json
mapu activity <corpus_uuid> --limit 20 --json
```

The resume output is the handoff entrypoint. Inspect `open_gaps`,
`recent_activity`, and `priority_next_actions` before rereading the repository or
starting a new investigation.

## CLI inference-cost loop

For coding agents, use MapU as persistent project memory before spending fresh
model context on rediscovery:

```powershell
mapu resume <corpus_uuid> --json
mapu query <corpus_uuid> "What do we already know about this task?" --json
mapu activity <corpus_uuid> --event-type query --json
mapu gaps <corpus_uuid> --json
```

`mapu query --json` includes `metadata.cost_profile` for automation. Direct,
structured, template, and chunk-excerpt answers report `zero_llm_answer=true`;
explicit gap responses still report `zero_llm_response=true`. Online LLM use is
limited to optional synthesis or investigation. Memory storage, retrieval,
handoff, activity, and gap inspection do not require an online LLM. Use
`estimated_context_tokens_reused`, hit counts, and activity history to decide
whether an external CLI should reuse MapU output, ask a targeted follow-up, or
pay for a broader model call.

By default, `mapu ingest` runs local rule extractors plus GLiNER entity
extraction. Online LLM extraction stays disabled unless the operator explicitly
enables it in the extraction settings.

## Command roles

- `mapu corpus create/list/delete/reset`: create and clean local memory corpora.
- `mapu ingest`: persist source-backed evidence into a corpus.
- `mapu resume`: produce a continuity handoff for a resumed agent session.
- `mapu query`: answer from stored memory and return next-step guidance.
- `mapu investigate`: run a deeper multi-document investigation.
- `mapu activity`: audit what memory changed, what was read, and what entity or
  situation each event touched.
- `mapu gaps`: inspect unresolved knowledge gaps.
- `mapu mcp`: expose the same memory workflow to MCP-capable agents.
- `mapu doctor --json`: inspect installed version and MCP tool surface without a
  database connection.
- `mapu serve`: run the REST API.

## Safety and repeatability

Destructive commands require explicit confirmation:

```powershell
mapu corpus delete <corpus_uuid> --yes
mapu corpus reset --yes
```

Run `alembic upgrade head` before relying on delete/reset latency in a large
agent corpus. The current schema includes direct `corpus_id` cleanup indexes for
dependent memory tables so disposable smoke corpora, benchmark corpora, and MCP
test corpora can be removed with set-based SQL instead of slow row-by-row
cleanup.

For repeatable automation, prefer JSON output and store the command, corpus id,
MapU version, and git SHA next to downstream artifacts. For release evidence,
use the audited scripts in the README instead of ad hoc terminal transcripts.
The CLI and MCP smoke reports include `command`, `corpus_id`, `mapu_version`,
and `git_sha` fields for this purpose.

For a cheap installed-surface check that does not touch the database, run:

```powershell
mapu doctor --json
```

Doctor output is useful for install and MCP tool-surface diagnostics. It is not
DB workflow, release hygiene, or benchmark performance evidence.

## Release cleanup

Use the objective audit before making release claims:

```powershell
uv run python tools/verify_objective_completion.py --format text
```

When the blocker is a dirty worktree, export the non-destructive Markdown cleanup
plan:

```powershell
uv run python tools/verify_objective_completion.py --format commit-plan
```

To save that plan as a reusable artifact, add `--out`:

```powershell
uv run python tools/verify_objective_completion.py --format commit-plan --out .tmp/release_cleanup_commit_plan.md
```

That report groups changed paths into release slices such as CLI/MCP surface,
memory runtime quality, benchmark evaluation, release evidence tooling, docs,
tests, and project config. It includes `commit_plan_integrity` to show whether
every changed path is covered exactly once by the generated slices, plus
review-first `git add -- ...` command blocks for each slice. It is a staging aid
only; it does not run `git add`, make commits, or prove release readiness.

To validate that the installed terminal workflow works against a configured
MapU database, run:

```powershell
uv run python tools/cli_e2e_smoke.py --command uv --arg run --arg mapu --json
```

That smoke creates a disposable corpus, ingests a small handoff note, runs
`resume`, `query --json`, and `activity --json`, then deletes the corpus. It
fails if query output is blank, if activity is not written, or if cleanup leaves
the corpus undeleted.

To validate the installed MCP stdio transport against the same configured
database, run:

```powershell
uv run python tools/mcp_stdio_smoke.py --command uv --arg run --arg mapu --arg mcp --json
```

That smoke starts the real MCP server subprocess, creates a disposable corpus,
ingests a small handoff note, contributes and reviews a proposition, queries it,
checks activity, and deletes the corpus. It forces lightweight deterministic
providers by default so this transport smoke is not measuring local ML model
load time. Use `--tool-timeout` to cap each MCP tool call and
`--use-current-ml-env` only when deliberately testing the configured production
providers.

## Benchmark commands

Benchmark smoke commands are operational checks, not public performance claims:

```powershell
uv run mapu eval memory-benchmark-smoke --no-export --out-dir .tmp/benchmark-live-smoke --min-token-f1 0.45
uv run mapu eval benchmark-score-inspect .tmp/benchmark-live-smoke/memoryarena_score.json --top 5
uv run mapu eval benchmark-score-gate --score memoryarena=.tmp/benchmark-live-smoke/memoryarena_score.json:token_f1:0.45 --score ama_bench=.tmp/benchmark-live-smoke/ama_score.json:token_f1:0.45 --out .tmp/benchmark-live-smoke/score_gate.json
```

Use benchmark-agnostic predictors for product-quality evidence. Diagnostic or
template predictors are allowed only for scorer debugging and must not be used
for release, public-claim, or public performance evidence.
