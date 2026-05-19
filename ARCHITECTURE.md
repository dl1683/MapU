# MapU Architecture

## Scope

This document separates:
- Implemented system surfaces in this repository
- Design intent and forward architecture direction

Claims in this file should be read as implementation-backed unless explicitly marked as `Design intent`.

## Implemented Surfaces

- CLI: `src/mapu/cli.py`
- MCP server: `src/mapu/mcp/server.py`
- REST API (Litestar): `src/mapu/api/app.py`, `src/mapu/api/controllers.py`
- Core query pipeline: `src/mapu/query/`
- Extraction and grounding pipeline: `src/mapu/extraction/`
- Persistence layer and migrations: `src/mapu/models/`, `src/mapu/db/migrations/`

## Runtime Architecture (Implemented)

1. Ingestion
- Parse source document into expression/spans/chunks
- Generate embeddings
- Run extraction pipeline (rules + configured ML/LLM extractors)
- Ground candidates into propositions/handles/attestations

2. Query
- Classify intent and select tier (direct, structured, synthesis, investigation)
- Execute retrieval over propositions (and chunk fallback when needed)
- Apply question-aware sanitation/reranking where configured
- Synthesize response with template or LLM synthesizer

3. Repair and Traceability
- Blast-radius preview and changeset flows are exposed via API/MCP
- Activity and gap surfaces are queryable through API/MCP/CLI paths

## Memory Continuity Contract (Implemented + In-Progress)

MapU prioritizes context continuity over one-off retrieval:
- Knowledge is persisted as stable propositions plus attestation and activity history inside corpora.
- Relation edges and participant links are stored to preserve cross-document and cross-claim connections (for example: clause A links clause D, condition X refines outcome Y, etc.).
- Supersession and change ordering are explicit through changeset/state objects and timeline-able, versioned surfaces.
- Confidence, uncertainty, and conflict status are inspectable so agents can choose whether to trust, defer, or route for verification.
- Query and investigation responses must emit actionable `next_steps` and gap-aware targets to reduce rediscovery cycles after context resets.
- Query and investigation responses preserve compatibility with string
  `next_steps`, and also emit `structured_next_steps` for terminal agents that
  need executable action type, tool-call text, rationale, uncertainty reason,
  governance tier, and expected uncertainty reduction.
- Gaps are continuity records, not just text notes. Each gap can persist
  `uncertainty_reason`, `evidence_hypothesis`, `next_action`,
  `expected_resolution`, `governance_tier`, `priority_score`, and resolution
  summary state.
- Query and investigation paths persist newly discovered uncertainty as open gap
  records when a gap or insufficient evidence state is observed, so the next
  session can resume from durable obligations instead of response-local prose.
- `resume`/MCP `handoff_context` emits a frontier completeness signal. Partial
  or bootstrap-required frontiers are explicit downgrade states for resumed
  agents.

### Session-Continuity Replay Contract (implemented today)

For resumed agent sessions, the recommended sequence is:
1. Reuse the same corpus.
2. Inspect unresolved uncertainty, open `list_gaps`, and recent `list_activity`.
3. Resolve highest-priority gaps with targeted queries before any broad re-ingest.
4. Re-ingest only when evidence is missing or contradicted.
5. Record repairs/attestations and supersession edges so future sessions inherit the trace.

4. Agent Memory Loop
- Implemented primitives support repeated agent use: create or reuse a corpus,
  ingest new evidence, query accumulated state, inspect activity/gaps, and
  repair bad state.
- Query and investigation responses now include `next_steps` guidance to steer the
  next learning action (e.g., entity-focused passes, relation expansion, budget
  escalation) rather than only returning current evidence.
- The current repository does not yet ship an autonomous scheduler or agent
  policy that decides when to study, refresh, supersede, or prune memory.
- Longitudinal learning quality must be validated by replaying real repository
  work over time, not inferred from one ingestion/query smoke test.

## Data Model (Implemented Core)

Core persisted objects include:
- Corpus
- DocumentWork / DocumentExpression / TextSpan / Chunk / ChunkEmbedding
- Handle / Proposition / PropositionParticipant
- Attestation / AttestationSituation
- Situation / QueryView
- PropositionState / PropositionStateBasis
- SupersessionEdge / Changeset / ChangesetOperation
- Activity / Gap
- GapTarget links can point at propositions, handles, documents, spans, chunks,
  activities, and changesets so next actions can be anchored in actual memory
  objects instead of prose-only descriptions.

See `src/mapu/models/` for exact schema definitions and `src/mapu/db/migrations/` for migration history.

## Claim Discipline

When making public claims, always distinguish:
- `Implemented now`: behavior visible in current code + validated by executable smoke or benchmark artifact
- `Design intent`: planned architecture not fully validated in current release

## Design Intent (Not a current claim)

- Broader domain-wide calibration of authority and confidence policies
- Stronger temporal reconciliation and supersession automation
- Expanded benchmark integration beyond current runnable set
