# Claim Evidence Appendix

Last updated: 2026-05-16

## Purpose

Map every public-facing claim category to concrete evidence artifacts or mark it as design intent/research framing.

## PRIORITIES.md claim mapping

1. Durable cross-session context memory is the top objective
- Type: Primary strategy claim
- Evidence:
  - `README.md`
  - `PRIORITIES.md`
  - `ARCHITECTURE.md`
  - `INTEGRATIONS.md`
- Status: Strategic + implemented substrate; longitudinal continuity claims require replay artifacts

2. Kernel-first, domain-invariant strategy
- Type: Strategy claim
- Evidence: `ARCHITECTURE.md` implemented-vs-intent separation and shared abstractions
- Status: Strategic framing (not benchmark metric claim)

3. Priority surfaces (`MCP`, `CLI`, `REST`) are available
- Type: Implemented capability claim
- Evidence:
  - `src/mapu/mcp/server.py`
  - `src/mapu/cli.py`
  - `src/mapu/api/app.py`
  - `src/mapu/api/controllers.py`
- Status: Implemented

4. Context-continuity handoff protocol is canonical
- Type: Strategy + process claim
- Evidence:
  - `INTEGRATIONS.md` (section "Session continuity handoff protocol")
  - `SESSION_CONTINUITY_PROTOCOL.md`
  - `README.md` (continuity-first notes)
  - `tests/unit/test_query.py` (next-step behavior coverage)
- Status: Implemented primitives with explicit protocol; continuity lift claim remains to be shown by replay artifacts.

5. Benchmarking and validation-first optimization approach
- Type: Process claim
- Evidence:
  - `GLOBAL_MEMORY_BENCHMARK_STATUS.md`
  - `tools/prepublish_benchmark_gate.ps1`
  - `tools/run_full_leaderboard_sweeps_parallel.ps1`
- Status: Implemented process

6. GitHub Action / hosted playground / marketplace expansion
- Type: Roadmap claim
- Evidence: Not shipped in this repository as of 2026-05-13
- Status: Design intent only

7. Two-year validation program and repository compatibility
- Type: Roadmap / validation-program claim
- Evidence:
  - `PRIORITIES.md` defines the intended validation lanes and required artifact types
  - No broad compatibility matrix or longitudinal repository scorecard is shipped yet
- Status: Design intent and future validation target, not current capability proof

## PROBLEM_SPACE.md claim mapping

1. Context stuffing degradation / long-context issues
- Type: External research framing claim
- Evidence requirement for public material:
  - cite external studies directly in publication channels
  - do not present as internally benchmarked MapU claim unless paired with local runs
- Status: Research framing

2. Agentic memory ephemerality framing
- Type: Conceptual problem statement
- Evidence:
  - Persistent corpus model + MCP/CLI/REST surfaces in codebase
- Status: Framing + implemented persistence layer

3. Gap modeling and next-step guidance
- Type: Strategy + implementation claim
- Evidence:
  - `src/mapu/context_learning.py`
  - `src/mapu/query/service.py`
  - `src/mapu/investigation/service.py`
  - `src/mapu/repos/gap.py`
- Status: Implemented

## Publication rule

For any outward claim:
1. If it is a performance claim: link exact benchmark artifact file paths and run timestamp.
2. If it is a capability claim: link concrete module paths implementing the capability.
3. If it is roadmap/research framing: mark explicitly as intent/framing, not validated result.
