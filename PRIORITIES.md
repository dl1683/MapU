# MapU Priorities

## Release Principle

MapU should publish only what it can demonstrate. Roadmap items are useful, but public claims must distinguish implemented capability from design intent.

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

Claim-grade release numbers require a fresh prepublish gate run.

## Priority 3: Domain Expansion

Code, legal, finance, and biomedical workflows are high-value validation targets. They should be treated as benchmark targets until domain-specific artifacts exist.

## Roadmap Items

These are not shipped claims unless backed by future artifacts:
- GitHub Action
- TypeScript SDK
- hosted playground
- cloud marketplace packaging
- broader domain-specific benchmark suites
