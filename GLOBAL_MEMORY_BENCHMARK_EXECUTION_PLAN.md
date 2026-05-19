# Global Memory Benchmark Execution Plan

Last updated: 2026-05-19 (America/New_York)

## Objective

Evaluate MapU across the public memory benchmark surface used by memory startups, while preserving the higher-level goal of durable, agent-facing memory continuity, then classify misses as:
- `system_gap`: MapU retrieval/extraction/synthesis failure
- `benchmark_mismatch`: benchmark expectation does not align with MapU's target memory contract

The highest-priority benchmark signal for this phase is whether repeated repository-level
agent tasks improve with retained context (better recall, fewer rediscoveries, cleaner gap
resolution behavior) after each rerun.

## Current benchmark surface

Source registry is generated in:
- `results/matrix/global_memory_benchmark_coverage.md`

MapU runnable now:
- `LoCoMo`
- `LongMemEval`
- `BEAM`
- `MemoryArena` (installed CLI export/predict/score/gate; local predictor is baseline only)
- `AMA-Bench` (installed CLI export/predict/score/gate; exact-match scorer is local sanity only)

Not yet runnable in current harness:
- `LifeBench`
- `MemBench`
- `MemSim`
- `PersonaMem`
- `DMR`

## Evaluation loop (per benchmark)

1. Run benchmark slice (`predict-only` first, then full judge mode as needed).
2. Compute proxy retrieval score (`support_hit_rate`, `nugget_hit_rate`).
3. Bucket each miss:
  - retrieval miss: relevant memory not surfaced
  - extraction miss: memory exists but proposition/object is malformed
  - temporal miss: correct facts but wrong version/date grounding
  - synthesis miss: support exists but final answer under-specifies nugget(s)
4. Decide root cause class:
  - `system_gap`: one of the four miss buckets above
  - `benchmark_mismatch`: question/rubric asks for behavior outside MapU memory-store scope
5. Apply one fix at a time and rerun only the affected slice.

## Context continuity replay work stream (MANDATORY)

Before any public release claim, run and preserve one replay study:
1. Persist a baseline over a repository-oriented memory task.
2. Resume the same task with the same corpus id and a fresh context.
3. Run:
  - pre-inventory (`list_gaps`, `list_activity`) pass
  - targeted `query`/`investigate` pass using persisted relations
  - optional controlled re-ingest pass only when gaps are marked missing/contradicted
4. Measure:
  - `gap` frequency change (before/after)
  - reused `supersession` edges and unresolved uncertainty traces
  - `next_steps` guidance quality shift from broad rediscovery to targeted closure
5. Record that the second pass reuses prior knowledge structure instead of starting from scratch.

## Immediate next runs

1. Run the exact-code prepublish gate before any public performance claim:
  - Conservative: `powershell -NoProfile -ExecutionPolicy Bypass -File tools\prepublish_benchmark_gate.ps1 -Parallel -MaxParallel 3 -IdleTimeoutMinutes 20`
  - Faster on an otherwise free machine: use a higher setting such as `-MaxParallel 6` while monitoring host responsiveness.
2. After a full gate completes, classify misses:
   - retrieval miss
   - extraction miss
   - temporal miss
   - synthesis miss
   - benchmark mismatch
3. Add a context-continuity replay run before release:
   - replay the same repository tasks against the same corpus across at least two commits,
   - measure delta in `gap` frequency, `supersession` behavior, and time-to-`next_steps` completion,
   - record whether the second pass reused prior findings or re-derived from scratch.
4. Only after the three runnable benchmarks have complete exact-code results, add the next adapter:
   - `LifeBench` first (LLM-judged and structurally closest to current harness)
5. In parallel, harden the new MemoryArena and AMA-Bench lanes:
   - improve benchmark-agnostic retrieval/reasoning instead of benchmark
     templates,
   - prefer trajectory-derived parsing and event summaries when benchmark
     inputs include enough state to answer without outside facts,
   - carry forward selected options and constraints for multi-step decision
     tasks instead of rescoring each turn from the raw prompt alone,
   - compress grounded retrieval passages into concise answer candidates only
     when the passage itself contains an answer-like declarative sentence,
   - preserve prediction artifacts that do not include expected answers,
   - preserve prediction method provenance in score reports,
   - reject diagnostic/template methods in release gates,
   - use `mapu eval benchmark-score-gate` to reject weak artifacts at declared thresholds.

## Failure classification rubric

Use this rubric before changing code:
- If top-k retrieval lacks any answer-bearing memory -> `system_gap/retrieval`.
- If top-k includes answer-bearing text but propositions are noisy/wrongly typed -> `system_gap/extraction`.
- If contradictory versions exist and wrong one is selected -> `system_gap/temporal`.
- If support is present but answer misses required rubric nuggets -> `system_gap/synthesis`.
- If gold answer requires policy/planning/tool action not represented in conversational memory retrieval -> `benchmark_mismatch`.

## Artifacts to keep updated every run

- Matrix run manifest: `results/matrix/*_runs.json`
- Proxy summary: `results/matrix/proxy_*.json`
- Global coverage: `results/matrix/global_memory_benchmark_coverage.{md,json}`
- Status rollup: `GLOBAL_MEMORY_BENCHMARK_STATUS.md`

## Continuity verification evidence format

Each run record should include:
- run id
- corpus ids
- before/after unresolved gap vectors
- supersession/conflict audit excerpts
- task-lift deltas from the continuity replay lane

## Local cleanup rule

Use `tools/clean_local_artifacts.ps1` for cache cleanup. Do not delete
`.tmp/memory-benchmarks`; `tools/run_mem0_benchmark_with_mapu.py` imports the
Mem0 benchmark runners from that checkout, and
`tools/report_full_sweep_leaderboard.py` reads baseline data from it.
