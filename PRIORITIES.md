# MapU — Priorities

## Build Philosophy

Build invariant first. The kernel should work across every domain without domain-specific code. Then optimize performance for high-value domains through better extraction quality, benchmarking, and validation — not through architectural branching.

## Priority 0: Invariant Kernel

Everything else depends on this. No domain-specific work starts until the kernel is solid.

| Component | What it does | Why it's foundational |
|-----------|-------------|----------------------|
| **Document ingestion** | Parse PDF, DOCX, HTML, plaintext, code; extract structure; generate spans and chunks | Every domain needs documents in |
| **Embedding layer** | Provider-agnostic embeddings stored in pgvector | Every domain needs semantic search |
| **Extraction framework** | Entity mentions, claims, relationships, references from any document type | Every domain needs structured knowledge out of unstructured text |
| **Handle resolution** | Canonical referent for entities that appear under different names across documents | Every domain has entity resolution problems |
| **Assertion model** | Predicate-based canonical knowledge units with provenance links to source spans | The core data structure everything else builds on |
| **Authority inference** | Determine source credibility from document characteristics, not configuration | Every domain has authoritative and non-authoritative sources |
| **Temporal model** | Bitemporal storage — system time + valid time on every assertion | Every domain has facts that evolve |
| **Epistemic control** | Contamination detection, confidence computation, derivation tracking | Trust and provenance are universal requirements |
| **Gap modeling** | Track missing documents, missing evidence, unresolved contradictions | Knowing what you don't know is as important as what you know |
| **Query planning** | Intent classification, retrieval granularity selection, executor dispatch | Every domain needs different query strategies |
| **Repair framework** | Blast-radius preview, cascading invalidation, edit commands | Every domain needs safe correction of errors |
| **Investigation engine** | Cascade governance, recursive lead-mining, active reasoning | The differentiator — MapU doesn't just store, it investigates |
| **Synthesis** | Answer generation with citations and epistemic metadata | Every query needs a well-formed answer |
| **Model layer** | Provider-agnostic abstraction for embeddings, extraction, and synthesis models | No vendor lock-in; works local or cloud |

## Priority 1: Performance Domains

Once the kernel works, optimize performance for these four domains. "Optimize" means better extraction quality, benchmarks against real-world corpora, and validated results — not domain-specific architecture.

| Domain | Why high priority | Validation approach |
|--------|------------------|-------------------|
| **Code** | Dogfooding. Developer community is the open source entry point. Every AI tool maker needs this. Easiest to benchmark objectively. | Run against real open-source repos. Measure: entity resolution accuracy, cross-file reasoning, impact analysis correctness. |
| **Legal** | Proven demand. Highest willingness to pay. Most complex cross-reference patterns (amendment chains, defined term resolution, multi-document obligation tracking). | Run against real contract sets and case files. Measure: assertion extraction precision/recall, cross-reference resolution accuracy, gap detection quality. |
| **Finance** | Massive market. Document-heavy. Enterprise buyers with budget. Quantitative reasoning required (financial metrics, covenant calculations). | Run against SEC filings, earnings transcripts, credit agreements. Measure: metric extraction accuracy, management-said-vs-actual tracking, covenant compliance detection. |
| **Biomedical** | Highest complexity validates the architecture. Multi-modal evidence (literature + data + regulatory). Strict authority hierarchies (RCT > cohort > case report). | Run against published papers + clinical trial reports. Measure: PICO extraction, claim-contradiction detection, evidence hierarchy correctness. |

## Priority 2: Surfaces

These run in parallel with Priority 1. The kernel needs to be accessible everywhere AI agents work.

| Surface | Priority | Rationale |
|---------|----------|-----------|
| **MCP Server** | Highest | One integration = Claude Code, Cursor, Windsurf, Zed, JetBrains, OpenAI Agents SDK, Vercel AI SDK. 10K+ servers in registry, 97M monthly SDK downloads. Universal plug. |
| **Python SDK** | High | `pip install mapu`. Programmatic interface for developers building custom apps. |
| **CLI** | High | `mapu ingest`, `mapu query`. Terminal-native workflows, scripting, CI/CD. |
| **REST API / Docker** | High | Self-hosted. Language-agnostic. Any backend can call it. |
| **GitHub Action** | Medium | Auto-index repo on push. "Add MapU in one YAML file." Virality vector for code domain. |
| **npm/TypeScript SDK** | Medium | JS ecosystem. MCP servers are often TypeScript. |
| **Hosted playground** | Medium | Web demo. Try-before-install. |
| **Cloud marketplaces** | Later | AWS/Azure/GCP. Enterprise procurement. When there's demand. |

## Priority 3: Remaining Domains

After the kernel is proven on Priority 1 domains, validate and optimize for:

| Tier | Domains | Reasoning |
|------|---------|-----------|
| **3a** | Intelligence (OSINT, fraud, threat intel), Academic (literature review, grant analysis) | Intelligence is high-value niche. Academic has large user base for community growth. |
| **3b** | Engineering (construction, aerospace, manufacturing) | Specific verticals, high per-seat value, longer sales cycles. |
| **3c** | Government (legislative, procurement, regulatory impact) | Long procurement cycles, compliance requirements. |
| **3d** | Healthcare operations, supply chain risk | Regulatory burden, slow adoption curves. |

## What "Optimize Performance" Means (Not Domain-Specific Code)

When we say "optimize for code/legal/finance/biomedical," we mean:

1. **Benchmarks** — build or adopt evaluation suites for each domain. Measure extraction precision/recall, reasoning accuracy, gap detection quality.
2. **Extraction quality** — tune the extraction pipeline (prompts, local model selection, chunking strategy) to perform well on that domain's document types.
3. **Validation corpora** — run against real-world document sets and publish results.
4. **Edge case handling** — identify and fix the hardest reasoning patterns for each domain (amendment chains for legal, multi-hop citations for academic, call graph traversal for code).
5. **Output quality** — ensure synthesized answers meet the expectations of domain practitioners.

None of this requires domain-specific architecture. It requires domain-specific testing and tuning of the universal pipeline.
