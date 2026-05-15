# Claim Evidence Appendix

Last updated: 2026-05-13

## Purpose

Map every public-facing claim category to concrete evidence artifacts or mark it as design intent/research framing.

## PRIORITIES.md claim mapping

1. Kernel-first, domain-invariant strategy
- Type: Strategy claim
- Evidence: `ARCHITECTURE.md` implemented-vs-intent separation and shared abstractions
- Status: Strategic framing (not benchmark metric claim)

2. Priority surfaces (`MCP`, `CLI`, `REST`) are available
- Type: Implemented capability claim
- Evidence:
  - `src/mapu/mcp/server.py`
  - `src/mapu/cli.py`
  - `src/mapu/api/app.py`, `src/mapu/api/controllers.py`
- Status: Implemented

3. Benchmarking and validation-first optimization approach
- Type: Process claim
- Evidence:
  - `GLOBAL_MEMORY_BENCHMARK_STATUS.md`
  - `tools/prepublish_benchmark_gate.ps1`
  - `tools/run_full_leaderboard_sweeps.ps1`
- Status: Implemented process

4. GitHub Action / hosted playground / marketplace expansion
- Type: Roadmap claim
- Evidence: Not shipped in this repository as of 2026-05-13
- Status: Design intent only

5. Two-year repository compatibility and persistent-memory validation lane
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

2. Vector retrieval is single-hop limitation framing
- Type: Conceptual architecture claim
- Evidence:
  - MapU design response in `ARCHITECTURE.md` and query/investigation pipeline modules
- Status: Framing + implemented mitigation path

3. Agentic memory ephemerality framing
- Type: Conceptual problem statement
- Evidence:
  - Persistent corpus model + MCP/CLI/REST surfaces in codebase
- Status: Framing + implemented persistence layer

4. Hard-problem list (HP-1 ... HP-12)
- Type: Problem taxonomy
- Evidence:
  - Some items implemented partially (repair preview, temporal metadata, gap/activity surfaces)
  - Others are ongoing and should not be claimed as fully solved without dedicated benchmarks
- Status: Mixed; treat as research/program scope, not blanket solved claims

## Publication rule

For any outward claim:
1. If it is a performance claim: link exact benchmark artifact file paths and run timestamp.
2. If it is a capability claim: link concrete module paths implementing the capability.
3. If it is roadmap/research framing: mark explicitly as intent/framing, not validated result.
