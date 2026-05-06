# MapU

A general-purpose persistent knowledge substrate for long-context reasoning across document-heavy domains.

## The Problem

Current approaches to reasoning over large document corpora each have fundamental limitations:

| Approach | Strength | Limitation |
|----------|----------|------------|
| **Full context loading** | Strong reasoning when context fits | Context rot degrades accuracy at ~25% of window. Expensive. Lost-in-the-middle effect drops accuracy 30%+ for mid-positioned facts. |
| **RAG / vector search** | Fast, cheap retrieval of similar content | Mathematically single-hop. Cannot follow conditionals, cross-references, or multi-step reasoning chains. Chunking strategy silently dominates quality. |
| **Agentic retrieval** | Highest reasoning quality for complex questions | Ephemeral — all understanding evaporates when context resets. Expensive. Non-deterministic. Minutes, not milliseconds. |
| **Persistent wikis** | Knowledge compounds over time | Write-amplification. Staleness risk. No formal provenance or authority model. |

None of these solve the core problem: **building durable, structured, source-attributed understanding that compounds over time and works across any domain.**

## What MapU Does

MapU ingests documents, extracts structured knowledge with full provenance, and builds a persistent graph of assertions, entities, evidence, and relationships that works across any document-heavy domain without domain-specific configuration.

The result is a knowledge substrate that:

- **Compounds** — every document ingested makes the system smarter, permanently
- **Attributes** — every claim traces to a source span, with authority weight and confidence
- **Reasons across documents** — connects facts that no single document contains
- **Knows what it doesn't know** — gaps, contradictions, and absent evidence are first-class objects
- **Repairs safely** — any error is fixable with predictable blast radius
- **Works across domains** — the same system handles legal contracts, codebases, financial filings, research papers, and more — no configuration needed

## Architecture

```
Documents (any format)
    │
    ▼
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Source     │────▶│  Extraction  │────▶│   Grounding     │
│   Ingest     │     │  (entities,  │     │   (handles,     │
│              │     │   claims,    │     │    assertions)  │
│              │     │   relations) │     │                 │
└─────────────┘     └──────────────┘     └────────┬────────┘
                                                   │
                                                   ▼
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Query     │◀────│  Epistemic   │◀────│   Knowledge     │
│   Engine    │     │  Control     │     │   Graph         │
│             │     │  (authority, │     │   (Postgres +   │
│             │     │   contam.)   │     │    pgvector)    │
└──────┬──────┘     └──────────────┘     └────────┬────────┘
       │                                          │
       ▼                                          ▼
┌─────────────┐                          ┌─────────────────┐
│  Synthesis  │                          │   Repair        │
│  (answers   │                          │   (blast radius │
│   w/ cite)  │                          │    preview)     │
└─────────────┘                          └─────────────────┘
```

### Core Layers

| Layer | Purpose |
|-------|---------|
| **Source** | Document ingestion, parsing, structure extraction, chunking, embedding |
| **Extract** | Observation extraction — entities, claims, relationships, references |
| **Grounding** | Handle resolution, canonicalization, assertion generation with provenance |
| **Epistemic** | Authority tracking, contamination control, confidence propagation, derivation chains |
| **Query** | Multi-stage planning, adaptive retrieval granularity, typed executors |
| **Investigate** | Active reasoning — plans searches, reads documents, identifies gaps, replans |
| **Repair** | Mutation with blast-radius preview, cascading invalidation, edit commands |
| **Synthesis** | Answer generation with source citations, confidence, and epistemic metadata |

### Key Design Decisions

1. **Postgres + pgvector** — bitemporal storage, multi-user, proper migrations, vector search colocated with structured data
2. **Provider-agnostic models** — bring your own embeddings (OpenAI, Gemini, Cohere, local sentence-transformers) and LLMs (Claude, GPT, Gemini, local). MapU is infrastructure, not a model wrapper.
3. **Domain-invariant architecture** — one system that handles legal, finance, biomedical, code, and everything else. The abstractions (assertions, handles, authority, temporal validity) are universal. No domain configuration required.
4. **Authority is not optional** — every assertion carries an authority tier derived from its source. No mixing of authority levels without explicit contamination tracking.
5. **Repair is a first-class operation** — preview blast radius before any mutation. Cascading invalidation propagates through the derivation graph.
6. **Local extraction, remote synthesis** — deterministic local models for structure extraction. LLMs for reasoning, planning, and natural language synthesis. Works fully offline with local models.

## Tested Across Domains

MapU's architecture is designed and validated against the reasoning patterns of 37 distinct use cases across 9 macro-domains:

| Domain | Use Cases |
|--------|-----------|
| **Legal** | Litigation, regulatory compliance, contract analysis, IP/patent, immigration, tax |
| **Finance** | M&A due diligence, equity research, credit analysis, insurance, audit, SEC compliance, ESG |
| **Biomedical** | Drug discovery, clinical trials, systematic reviews, genomics, pharmacovigilance |
| **Code** | Codebase understanding, security audit, compliance-as-code, incident post-mortem |
| **Intelligence** | OSINT, corporate investigations, investigative journalism, threat intelligence |
| **Engineering** | Construction, aerospace requirements traceability, manufacturing quality |
| **Government** | Legislative analysis, procurement, regulatory impact assessment |
| **Academic** | Literature review, grant analysis, standards development |
| **Healthcare/Supply Chain** | Clinical case management, supply chain risk |

See [DOMAINS.md](DOMAINS.md) for the complete research reference with document types, entity ontologies, authority models, and reasoning patterns per use case.

## Surfaces

MapU is available as:

| Surface | Description |
|---------|-------------|
| **MCP Server** | Model Context Protocol — works natively with Claude Code, Cursor, Windsurf, Zed, JetBrains, OpenAI Agents SDK |
| **Python SDK** | `pip install mapu` — programmatic interface for custom applications |
| **CLI** | `mapu ingest`, `mapu query` — terminal-native workflows |
| **REST API** | Self-hosted via Docker — language-agnostic HTTP interface |
| **GitHub Action** | Auto-index your repo on every push — persistent codebase knowledge |

## Quick Start

```bash
# Prerequisites: Python 3.12+, PostgreSQL 15+

# Clone and install
git clone https://github.com/deal1683/MapU.git
cd MapU
pip install -e ".[dev]"

# Start infrastructure
docker compose up -d

# Run migrations
alembic upgrade head

# Start the server
python -m mapu.server
```

## Research Directions

Active areas of investigation:

- **Cross-document reasoning quality** — benchmarking MapU against RAG, context stuffing, and agentic retrieval on real-world multi-hop reasoning tasks
- **Confidence calibration** — moving from heuristic confidence to calibrated confidence validated against holdout data
- **Investigation cost optimization** — adaptive model selection based on query complexity and existing knowledge state
- **Temporal reasoning** — amendment chains, retractions, supersession, and indicator decay as a unified temporal algebra
- **Authority inference** — automatically determining source authority from document structure and content without manual annotation

## License

AGPL-3.0 — see [LICENSE](LICENSE)

---

Built by [iqidis.ai](https://iqidis.ai)
