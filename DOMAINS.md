# Domain Research Reference

## Purpose

This file is a research reference for domain patterns MapU is intended to support.
It is not a claim that every listed workflow is already benchmark-validated in this repository.

Use this as:
- ontology and reasoning-pattern guidance
- stress-case planning for future validation
- coverage checklist for architecture decisions

## Current Validation Scope

Current hard benchmark evidence in this repository is concentrated on long-memory evaluation tracks captured in:
- `GLOBAL_MEMORY_BENCHMARK_STATUS.md`
- `results/` artifacts referenced there

Domain-specific quality claims (legal, finance, biomedical, etc.) should only be made when paired with explicit domain-run artifacts.

## Cross-Domain Invariants

Across domains, the same core abstractions are used:
- assertions/propositions
- entity handles
- provenance/attestations
- temporal context
- gaps and repair operations

## Example Domain Profiles (Research Targets)

1. Legal
- Typical docs: contracts, amendments, filings, motions, orders
- Key patterns: cross-reference resolution, obligations tracking, amendment supersession

2. Finance
- Typical docs: 10-K/10-Q, earnings transcripts, investor decks, credit agreements
- Key patterns: period-over-period comparisons, guidance tracking, covenant checks

3. Code and Security
- Typical docs: source files, dependency manifests, incident notes, advisories
- Key patterns: impact analysis, dependency risk reasoning, incident timeline reconstruction

4. Biomedical
- Typical docs: papers, protocols, trial summaries, regulatory docs
- Key patterns: evidence hierarchy, contradiction handling, temporal evidence updates

5. Investigations / Intelligence
- Typical docs: records, communications, reports, filings
- Key patterns: multi-source corroboration, chain-of-evidence, timeline consistency

## Public Claim Rule

If a domain claim is published, include:
1. exact run artifact paths
2. metric definitions
3. known limitations
