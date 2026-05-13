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

## Data Model (Implemented Core)

Core persisted objects include:
- Corpus
- DocumentWork / DocumentExpression / TextSpan / Chunk / ChunkEmbedding
- Handle / Proposition / PropositionParticipant
- Attestation / AttestationSituation
- Activity / Gap

See `src/mapu/models/` for exact schema definitions and `src/mapu/db/migrations/` for migration history.

## Claim Discipline

When making public claims, always distinguish:
- `Implemented now`: behavior visible in current code + validated by executable smoke or benchmark artifact
- `Design intent`: planned architecture not fully validated in current release

## Design Intent (Not a current claim)

- Broader domain-wide calibration of authority and confidence policies
- Stronger temporal reconciliation and supersession automation
- Expanded benchmark integration beyond current runnable set
