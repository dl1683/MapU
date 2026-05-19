# MapU Priorities

## No. 0 (Primary): Persistent Context Map for Agentic Systems

This is the top-level objective for MapU execution and all roadmap decisions:

- Preserve cross-session learning so context resets do not erase useful discoveries.
- Store factual learning as structured, provenance-bound objects with explicit relations.
- Track revision intent explicitly (`overrides`, `supersedes`, `uncertainty`, `evidence`) with versioned lineage.
- Enforce a continuity handoff step at session boundaries: load persisted uncertainty/conflict state before collecting more evidence.
- Make retrieval gaps actionable by pointing to the highest-likelihood evidence locations.
- Provide auditable trails that show what is known, what changed, what is uncertain, and why it changed.

Everything else is secondary to this memory substrate objective until memory continuity is explicit, versioned, and measurable in resumed sessions.

## Release Principle

MapU should publish only what it can demonstrate. Roadmap items are useful, but public claims must distinguish implemented capability from design intent and include continuity replay evidence where memory behavior is claimed.

## Priority 0: Release Integrity

- Public benchmark claims must pass `tools/prepublish_benchmark_gate.ps1` on the exact release code.
- Public docs must avoid unverified domain-general claims.
- Install, migration, CLI, MCP, REST, reset, and benchmark paths must be reproducible from a clean checkout.

## Priority 1: Implemented Core

Current repository surfaces:
- CLI: `src/mapu/cli.py`
- MCP server: `src/mapu/mcp/server.py`
- REST API: `src/mapu/api/`
- Extraction and grounding: `src/mapu/extraction/`
- Query and synthesis: `src/mapu/query/`
- Persistence/migrations: `src/mapu/models/`, `src/mapu/db/migrations/`

## Priority 2: Validation

Memory benchmark validation currently centers on:
- LoCoMo
- LongMemEval
- BEAM
- MemoryArena and AMA-Bench as installed CLI smoke/diagnostic lanes

Claim-grade release numbers require a fresh prepublish gate run.

## Priority 2b: Dynamic Agent Memory

MapU should be validated as a memory substrate for agentic coding and research systems that repeatedly learn from changing repositories over time.

Implemented foundation:
- durable corpora
- MCP ingest/query/investigation/activity/gap/repair/reset tools
- source-backed propositions and attestations
- situations, truth states, supersession schema, changesets, and activity logs

Unproven public claims:
- autonomous repo-study loops
- reliable stale-memory suppression as repositories change
- measurable agent task improvement from persistent MapU memory
- long-term cost, latency, storage, and repair behavior under repeated use

Near-term validation artifacts should include:
- replay tasks over the same repository at multiple commits
- before/after memory quality audits
- stale fact and supersession test cases
- agent-with-memory versus agent-without-memory task comparisons
- storage and latency curves after repeated ingest/update cycles

External agent validation is mandatory for this lane. When available, use
Gemini through the terminal and Claude Code subagents through the terminal as
independent reviewers of MapU's durable-memory handoff. These trials should ask
whether a resumed agent can recover prior learning, inspect provenance,
uncertainty, conflicts, supersession, activity, and gaps, follow `next_steps`,
and avoid rediscovering the project from scratch. Treat this as primary product
validation, not as a benchmark side quest.

## Priority 3: Domain Expansion

Code, legal, finance, and biomedical workflows are high-value validation targets. They should be treated as benchmark targets until domain-specific artifacts exist.

## Two-Year Goals

MapU's two-year validation target is not only memory benchmark performance. It should prove that a persistent memory architecture works inside real existing repositories and long-lived workflows.

Required validation lanes:
- Repository compatibility: run MapU against existing codebases with real file trees, issue history, docs, tests, and agent workflows.
- Agent integration compatibility: test MCP usage from coding agents and IDE assistants, including Codex-like, terminal Gemini, and Claude Code subagent workflows.
- Memory efficiency: measure ingest cost, storage growth, retrieval latency, update cost, and reset/repair cost as repositories evolve.
- Stored data quality: audit extracted entities, claims, relations, temporal facts, provenance links, and stale/incorrect memory over time.
- Workflow lift: compare agent outcomes with and without MapU memory on repo tasks such as bug diagnosis, refactor planning, documentation, benchmark triage, and release audits.
- Longitudinal robustness: repeatedly revisit the same repositories after code changes to test whether memory improves, contaminates, or drifts.

This lane should produce its own artifacts, not just anecdotes:
- compatibility matrix by repository type and agent surface
- quality scorecards for stored memory
- cost/latency/storage curves
- failure taxonomies for bad extraction, stale facts, and retrieval misses
- repeatable replay tasks that external users can run

## Roadmap Items

These are not shipped claims unless backed by future artifacts:
- GitHub Action
- TypeScript SDK
- hosted playground
- cloud marketplace packaging
- broader domain-specific benchmark suites
