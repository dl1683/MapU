# MapU Problem Space

## Core Problem

Document-heavy work often requires reasoning over more evidence than a person or a single model context can reliably hold. Useful answers need provenance, authority, temporal context, and repairability.

Primary mission for this repo branch: make MapU a durable, auditable memory substrate that prevents loss of learned structure when an agent session resets.

## Why Existing Patterns Are Not Enough

1. Context loading is expensive and can degrade with long inputs.
2. Vector retrieval is useful but does not by itself create durable structured knowledge.
3. Agentic reading can be strong but often loses work when the session ends or one agent discovers a different interpretation than another.
4. Persistent notes and wikis compound knowledge but usually lack formal provenance, authority, and repair semantics.

These are problem-framing claims. External publications should cite external research directly when using stronger quantitative claims.

## MapU's Intended Response

MapU focuses on:
- persistent corpora
- source-attributed propositions
- authority-aware evidence
- temporal metadata
- gap modeling
- repair and audit surfaces
- CLI/MCP/REST access for agent workflows
- claim relation models and cross-claim/context linking

Implemented surfaces are described in `ARCHITECTURE.md`. Performance evidence is tracked in `GLOBAL_MEMORY_BENCHMARK_STATUS.md`.

The first-order objective is **persistent semantic continuity**:
- retain and version structured learning across sessions and corpus changes,
- preserve links between related knowledge (including cross-entity, cross-clause, and cross-time constraints),
- represent uncertainty, contradiction, and supersession explicitly,
- preserve evidence and revision lineage for audit,
- and direct the next lookup path (via `next_steps`, gap targets, and relation-aware suggestions) when memory is incomplete.

## Hard Problems

These are research and validation targets, not blanket solved claims:
- segmentation mismatch
- cross-document entity resolution
- authority contamination
- temporal supersession
- gap detection
- confidence calibration
- blast-radius prediction
- investigation cost control
- multi-hop reasoning
- adversarial source handling
- scale

## Publication Rule

Do not publish a strong claim from this document unless it is paired with:
- a source citation for external claims, or
- a local artifact/test/benchmark for MapU claims.
