# MapU — Problem Space

## Core Problem

Professionals across every document-heavy domain face the same fundamental challenge: reasoning over corpora too large for any human to hold in working memory, where answers require synthesizing facts scattered across many documents, and where the provenance, authority, and temporal validity of each fact matters.

Current AI approaches fail at different points:

### 1. Context Stuffing Fails at Scale

Transformer attention is quadratic. Context rot — measurable performance degradation as input length increases — affects every frontier model. Chroma's 2025 research showed all 18 tested models (GPT-4.1, Claude Opus 4, Gemini 2.5) degrade significantly well before reaching their stated context limits. The lost-in-the-middle effect causes 30%+ accuracy drops for information positioned in the middle of long contexts.

This is an architectural property of attention, not a training gap.

### 2. Vector Search Cannot Follow Reasoning Chains

Vector similarity is mathematically single-hop. Each chunk is scored independently against the query. There is no mechanism to jointly reason across chunks or follow conditional logic ("if X then Y, unless Z"). Chunking strategy is a hidden hyperparameter that silently dominates retrieval quality — split a clause across two chunks and you may never retrieve the complete thought.

### 3. Agentic Retrieval is Ephemeral

Agentic systems achieve the highest reasoning quality for complex questions, but all understanding evaporates when context resets. An agent that reads an entire codebase and builds a deep mental model loses that model permanently when the session ends. This makes every investigation pay full cost from scratch.

### 4. Persistent Wikis Lack Epistemic Structure

Karpathy's LLM Wiki pattern demonstrates that persistent, compounding knowledge outperforms RAG at scale. But wikis have no formal authority model, no provenance tracking, no confidence calibration, no contamination control, and no blast-radius-safe repair.

## The Gap

No existing system provides all of:
- Persistent, compounding knowledge (not ephemeral)
- Source-attributed assertions with authority tiers (not flat text)
- Cross-document reasoning (not single-document retrieval)
- Domain-parameterized extraction and reasoning (not one-size-fits-all)
- Temporal truth maintenance (facts evolve, get superseded, expire)
- Explicit gap and contradiction modeling (not just what's known, but what's missing)
- Safe repair with predictable blast radius (not brittle knowledge graphs)
- Cost-efficient investigation (local models where possible, LLMs where needed)

## Hard Problems

### HP-1: Segmentation Mismatch
Documents don't come pre-segmented into extractable units. A single paragraph may contain three assertions about two entities with different authority levels. Chunking for embeddings, chunking for extraction, and chunking for display are three different problems.

### HP-2: Cross-Document Entity Resolution
The same entity appears differently across documents: "Acme Corp", "Acme Corporation", "the Company", "Defendant", "the Borrower". Resolving these without false positives is hard and domain-dependent.

### HP-3: Authority Contamination
A high-authority assertion (court ruling) should not be influenced by a low-authority source (blog post) in the same reasoning chain. When authority levels mix, the system must track which conclusions depend on which authority tiers and flag contamination.

### HP-4: Temporal Supersession
Facts change. Contracts get amended. Statutes get revised. Papers get retracted. Security advisories expire. The system must track which version of truth is current and maintain history for audit.

### HP-5: Gap Detection is Harder Than Fact Extraction
Extracting what a document says is tractable. Determining what a corpus does NOT say — what's missing, what should be there but isn't, what questions remain unanswered — requires reasoning about the shape of complete knowledge for the domain.

### HP-6: Confidence Calibration Across Domains
"90% confident" means different things in different domains. A 90% confidence drug efficacy claim requires different evidence than a 90% confidence code coverage claim. Confidence must be calibrated per-domain, per-extraction-method, and ideally validated against holdout data.

### HP-7: Blast Radius Prediction
When a human corrects an assertion, which other assertions, decisions, and projections are invalidated? The system must trace the derivation graph and predict the full impact before executing any mutation.

### HP-8: Investigation Cost Optimization
Full investigation (read every document, extract everything) is correct but expensive. The system must decide when existing knowledge is sufficient, when targeted retrieval is enough, and when full investigation is warranted — based on the current knowledge state, not just the query.

### HP-9: Multi-Hop Reasoning Across Documents
The most valuable insights connect facts from different documents that were never intended to be read together. "The CEO's employment agreement (Document A) grants acceleration on change of control, and the merger agreement (Document B) triggers change of control, therefore the CEO's equity vests" requires reasoning across two documents.

### HP-10: Domain Profile Extensibility
Adding a new domain (say, "environmental compliance") should require defining a profile (document families, entity types, authority tiers, temporal semantics, reasoning patterns) — not writing new extraction code or modifying the kernel.

### HP-11: Adversarial Source Handling
In intelligence, journalism, and litigation, sources may actively deceive. The system must support corroboration requirements, track single-source vs. multi-source claims, and flag confirmation bias risk.

### HP-12: Scale
A single matter may involve 10,000+ documents, 100,000+ assertions, and millions of cross-references. The system must handle this without degradation.

## Constraints

### Tier 1: Non-Negotiable
- Every assertion traces to a source span
- Authority levels never mix silently
- Temporal validity is tracked for all assertions
- Repair blast radius is computable before execution
- The system knows what it doesn't know (gaps are modeled)

### Tier 2: Strong Preference
- Local models for extraction (deterministic, cost-free, offline-capable)
- LLMs for synthesis and investigation (powerful, flexible)
- Postgres for storage (bitemporal, multi-user, pgvector colocated)
- Domain profiles are declarative, not imperative
- All outputs carry epistemic metadata (confidence, authority, provenance)
