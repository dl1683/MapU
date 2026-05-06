# MapU — Architecture

## Design Principles

1. **The knowledge graph is the product, not the LLM output.** LLM-generated text is ephemeral. The structured knowledge substrate is durable.
2. **Authority is not metadata — it's structure.** A court opinion and a blog post are not the same kind of source. The system enforces this at every layer.
3. **One system, every domain.** The architecture is domain-invariant. The same abstractions — assertions, handles, authority tiers, temporal validity, gaps — work for legal contracts, codebases, financial filings, and research papers without configuration.
4. **Provider-agnostic models.** Bring your own embeddings and LLMs. MapU is infrastructure, not a model wrapper. Works fully offline with local models, scales with cloud APIs.
5. **Gaps are first-class objects.** What's missing from the corpus is as important as what's present.
6. **Repair is safe by default.** No mutation without blast-radius preview. Cascading invalidation propagates through the derivation graph.
7. **Temporal truth, not snapshot truth.** Every assertion has temporal validity. The system can answer "what was believed at time T?" not just "what is believed now?"

## System Architecture

### Layer Model

```
┌────────────────────────────────────────────────────────────┐
│                        API / UI                             │
│         (Litestar controllers, MCP server, CLI)             │
├────────────────────────────────────────────────────────────┤
│                      Synthesis                              │
│       (Answer generation with citations & confidence)       │
├────────────────────────────────────────────────────────────┤
│                    Investigation                            │
│    (Cascade governance, recursive lead-mining, planning)    │
├──────────────────┬─────────────────────────────────────────┤
│     Query        │           Repair                         │
│  (Planning,      │  (Blast-radius preview,                  │
│   executors,     │   cascading invalidation,                │
│   granularity)   │   edit commands)                         │
├──────────────────┴─────────────────────────────────────────┤
│                    Epistemic Control                         │
│   (Authority tiers, contamination, confidence, derivation)  │
├────────────────────────────────────────────────────────────┤
│                    Knowledge Graph                           │
│   (Assertions, handles, evidence, gaps, temporal state)     │
├────────────────────────────────────────────────────────────┤
│     Grounding     │    Extraction    │     Source Ingest     │
│  (Canonicalize,   │ (Entities,       │  (Parse, structure,   │
│   resolve,        │  claims,         │   chunk, embed)       │
│   decide)         │  relations)      │                       │
├────────────────────────────────────────────────────────────┤
│                    Model Layer (Provider-Agnostic)           │
│   Embeddings: OpenAI / Gemini / Cohere / local              │
│   Extraction: GLiNER / spaCy / LLM-backed                   │
│   Synthesis:  Claude / GPT / Gemini / local                  │
└────────────────────────────────────────────────────────────┘
│                    Storage (Postgres + pgvector)             │
│          (Bitemporal, migrations, outbox, activity log)     │
└────────────────────────────────────────────────────────────┘
```

### Data Flow

#### Ingestion Path (Write)

```
Raw Document → Source Ingest → Extract → Ground → Knowledge Graph
```

1. **Source Ingest** (`source/`)
   - Parse document (PDF, DOCX, HTML, plaintext, code)
   - Extract hierarchical structure (sections, paragraphs, clauses)
   - Generate text spans with character offsets
   - Chunk for embeddings (token-aware)
   - Generate embeddings (provider-agnostic)
   - Persist: DocumentWork, DocumentExpression, StructureNode, TextSpan, Chunk

2. **Extraction** (`extract/`)
   - Detect document structure and content type
   - Extract anchors (entity mentions, term references, citations)
   - Extract observations (claims, obligations, definitions, findings, relationships)
   - Route to review queue based on confidence
   - Persist: Anchor, Observation, ObservationSpan

3. **Grounding** (`grounding/`)
   - Resolve handles (canonical referent for each entity)
   - Normalize observations into canonical assertions
   - Propose entity identity decisions (entity resolution)
   - Build support/derivation links
   - Persist: Handle, Assertion, AssertionSupport, StructuralDecision

4. **Epistemic Validation** (`epistemic/`)
   - Infer authority tier from source characteristics
   - Check for contamination (authority mixing)
   - Compute confidence interval
   - Track derivation edges
   - Quarantine working assertions pending review

#### Query Path (Read)

```
User Query → Query Planner → Executors → Epistemic Filter → Synthesis → Answer
```

1. **Query Planning** (`query/`)
   - Classify query intent (identity lookup, cross-reference, opinion survey, timeline, etc.)
   - Determine source policy (authority requirements)
   - Select retrieval granularity (graph-only, span, chunk, full-document, historical)
   - Build executor graph

2. **Execution** (`query/executors`)
   - GraphOnlyExecutor: navigate assertions/handles/decisions
   - SpanExecutor: retrieve exact source text + context
   - ChunkExecutor: semantic nearest-neighbor retrieval
   - DocumentExecutor: full document with structure
   - HistoricalExecutor: bitemporal replay

3. **Epistemic Filter** (`epistemic/`)
   - Apply authority floor per source policy
   - Flag contamination in results
   - Attach confidence metadata
   - Isolate working assertions from canonical

4. **Synthesis** (`synthesis/`)
   - Generate answer with source citations
   - Include confidence and authority metadata

#### Investigation Path (Active Reasoning)

```
Complex Query → Cascade Governor → Investigation Engine → [Read/Extract/Search loop] → Synthesis
```

1. **Cascade Governance** (`investigate/governance.py`)
   - Assess current knowledge state (answerability snapshot)
   - Route to cheapest sufficient path:
     - `query`: direct state lookup (no LLM)
     - `read`: synthesize from existing knowledge (cheap LLM)
     - `investigate`: full recursive lead-mining (expensive LLM)
     - `clarify`: ask user for missing prerequisites (no LLM)

2. **Investigation Engine** (`investigate/engine.py`)
   - Plan: what's known, what's needed, what to search for
   - Execute: fetch documents, read, extract, build evidence
   - Replan: evaluate coverage, identify high-impact leads, iterate
   - Terminate: coverage threshold, budget exhaustion, or unresolvable contradictions

#### Repair Path (Mutation)

```
Edit Command → Blast Radius Preview → [User Confirms] → Execute → Cascade Invalidation
```

1. **Preview** (`repair/preview.py`)
   - Trace derivation graph from target assertion
   - Compute affected assertions, decisions, projections
   - Report blast radius before any change

2. **Execute** (`repair/service.py`)
   - Apply edit command
   - Cascade invalidation through derivation graph
   - Re-trigger affected downstream computations
   - Log in activity ledger

## Data Model

### Core Tables

| Table | Purpose |
|-------|---------|
| `matter` | Top-level grouping (case, project, portfolio, repo) |
| `document_work` | Raw ingested document |
| `document_expression` | Parsed representation of a document |
| `structure_node` | Hierarchical document structure |
| `text_span` | Source text with character offsets |
| `chunk` | Embedding-ready text segment |
| `chunk_embedding` | pgvector embedding |
| `handle` | Stable canonical referent (entity, concept, provision, function, compound — any domain) |
| `anchor` | Local mention of a handle in a document |
| `observation` | Raw extracted claim before grounding |
| `assertion` | Canonical knowledge unit with provenance |
| `assertion_support` | Evidence link (assertion ↔ source span) |
| `derivation_edge` | Provenance chain (assertion derived from assertions) |
| `structural_decision` | Entity identity decision with competing hypotheses |
| `gap` | Modeled absence (missing doc, missing evidence, unresolved contradiction) |
| `activity` | Immutable event log |
| `review_task` | Human review queue item |

### How Domain Invariance Works

The data model uses universal abstractions that naturally accommodate any domain:

- **Handles** are typed by `kind` (free-form string: "party", "gene", "function", "company", "provision"). The system doesn't enumerate kinds — it discovers them from content.
- **Assertions** are predicate-based: `(subject_handle, predicate, object_handle | value, source_span)`. The predicate vocabulary is open, not closed.
- **Authority** is inferred from source characteristics (document type, provenance, cross-references) rather than requiring domain-specific configuration.
- **Temporal validity** is attached to any assertion via bitemporal ranges, regardless of what that assertion describes.

This means a legal contract, a Python codebase, and a clinical trial report all produce the same structural primitives — just with different handle kinds, predicates, and authority signals.

### Bitemporal Model

Every assertion carries two time dimensions:
- **System time** (`system_range`): when the system learned this fact
- **Valid time** (`valid_range`): when this fact is/was true in the real world

This enables:
- "What did we know as of last Tuesday?" (system time query)
- "What was the contract state as of January 1?" (valid time query)
- "What did we believe about January 1's state as of last Tuesday?" (bitemporal query)

### Authority Model

Authority is inferred, not configured. The system determines source credibility from:
- Document structure and metadata (is this a formal filing, a casual email, a published paper?)
- Cross-referencing patterns (is this source cited by other sources?)
- Provenance chain (where did this document come from?)
- Content signals (formal language, citations, methodology sections)

The epistemic layer enforces:
- No silent authority mixing in derivation chains
- Contamination flagging when low-authority sources influence high-authority conclusions
- Authority ceiling propagation (a conclusion can never be more authoritative than its least authoritative input)

### Model Layer (Provider-Agnostic)

```
[models]
# Embeddings: any provider or local
embeddings = "openai:text-embedding-3-small"    # or "gemini:...", "local:all-MiniLM-L6-v2"

# Extraction: local models or LLM-backed
extraction = "local:gliner"                      # or "openai:gpt-4o-mini", "gemini:flash"

# Synthesis: any LLM
synthesis = "anthropic:claude-sonnet-4-6"        # or "openai:gpt-4o", "gemini:pro", "local:..."
```

MapU works at three levels:
1. **Fully local** — sentence-transformers + GLiNER + local LLM. No API keys, no cost, works offline.
2. **Hybrid** — local extraction + cloud LLM for synthesis. Best quality-per-dollar.
3. **Fully cloud** — cloud embeddings + cloud extraction + cloud synthesis. Maximum quality.

## Technology Choices

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Database | PostgreSQL 15+ | Bitemporal ranges, pgvector, JSONB, mature migrations, multi-user |
| Vector store | pgvector | Colocated with structured data, no separate infra |
| Migrations | Alembic | Industry standard, version-controlled schema evolution |
| API framework | Litestar | Async-first, OpenAPI native |
| MCP server | Model Context Protocol | Universal integration with Claude Code, Cursor, Windsurf, Codex, etc. |
| Extraction models | sentence-transformers, GLiNER, spaCy, SetFit | Local, deterministic, no API cost, offline-capable |
| LLM integration | Provider-agnostic | No vendor lock-in; tiered model selection per task |
| Background work | Redis + outbox pattern | Reliable async processing, event-driven |
| Testing | pytest + pytest-asyncio | Async-native, good fixture model |
