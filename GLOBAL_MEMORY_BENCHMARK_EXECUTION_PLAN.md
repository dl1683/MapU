# Global Memory Benchmark Execution Plan

Last updated: 2026-05-12 (America/New_York)

## Objective

Evaluate MapU across the public memory benchmark surface used by memory startups, then classify misses as:
- `system_gap`: MapU retrieval/extraction/synthesis failure
- `benchmark_mismatch`: benchmark expectation does not align with MapU's target memory contract

## Current benchmark surface

Source registry is generated in:
- `results/matrix/global_memory_benchmark_coverage.md`

MapU runnable now:
- `LoCoMo`
- `LongMemEval`
- `BEAM`

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
   - synthesis miss: retrieved support exists but final answer under-specifies nugget(s)
4. Decide root cause class:
   - `system_gap`: one of the four miss buckets above
   - `benchmark_mismatch`: question/rubric asks for behavior outside MapU memory-store scope
5. Apply one fix at a time and rerun only the affected slice.

## Immediate next runs

1. Holdout rerun for existing three:
   - `LoCoMo`: `--conversations 0 --max-questions 40` (or more)
   - `LongMemEval`: `--per-type 2..5`
   - `BEAM`: `--chat-sizes 100K,500K`
2. Target metric:
   - Keep support-hit >= `0.95` on holdout slices
   - Raise BEAM nugget hit from `0.7949` to `>=0.80` without query-specific hint rules
3. Add next adapter:
   - `LifeBench` first (LLM-judged and structurally closest to current harness)

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
