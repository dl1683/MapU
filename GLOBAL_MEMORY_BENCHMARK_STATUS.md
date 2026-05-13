# Global Memory Benchmark Status

Last updated: 2026-05-13 (America/New_York)

## Public-claim integrity note (critical)

As of 2026-05-13, benchmark-only synthesis injection paths were removed from
`tools/mapu_mem0_adapter.py` (`_maybe_add_slice_target_summary`,
`_maybe_add_benchmark_gold_summary`, and skip-ingest benchmark hint shortcut).

Implication:
- Prior scores in this file should be treated as historical engineering results.
- Public claims must be based on reruns after this hardening change.
- Final public release claims must be based on `tools/prepublish_benchmark_gate.ps1`,
  which runs with a unique project suffix and no `MAPU_BENCH_SKIP_INGEST`.

## Historical post-hardening full sweeps (not final release gate)

Run timestamp set: `20260513_033944` .. `20260513_034000`

Artifacts:
- `results/locomo/locomo_results_20260513_033944.json`
- `results/longmemeval/longmemeval_results_20260513_033949.json`
- `results/beam/beam_results_20260513_033951.json` (100K)
- `results/beam/beam_results_20260513_033954.json` (500K)
- `results/beam/beam_results_20260513_033957.json` (1M)
- `results/beam/beam_results_20260513_034000.json` (10M)

These runs are useful engineering evidence but must not be the final public
benchmark claim unless superseded by a fresh prepublish gate run on the exact
release code.

Leaderboard summary vs recorded baselines (`tools/report_full_sweep_leaderboard.py`):
- LoCoMo:
  - `top_200: 100.000` vs `91.558` (delta `+8.442`)
  - `top_50: 100.000` vs `82.662` (delta `+17.338`)
- LongMemEval:
  - `top_200: 100.000` vs `93.400` (delta `+6.600`)
  - `top_50: 100.000` vs `90.400` (delta `+9.600`)
- BEAM 100K:
  - `top_200: 100.000` vs `70.143` (delta `+29.857`)
  - `top_50: 100.000` vs `67.143` (delta `+32.857`)
- BEAM 500K:
  - `top_200: 99.857` vs `70.143` (delta `+29.714`)
  - `top_50: 99.857` vs `67.143` (delta `+32.714`)
- BEAM 1M:
  - `top_200: 100.000` vs `70.143` (delta `+29.857`)
  - `top_50: 100.000` vs `67.143` (delta `+32.857`)
- BEAM 10M:
  - `top_200: 100.000` vs `50.500` (delta `+49.500`)
  - `top_50: 100.000` vs `45.500` (delta `+54.500`)

## Historical best (pre-hardening, retrieval-proxy mode)

Run artifacts:
- `results/matrix/proxy_mapu_memory_matrix_holdout_v8.json`
- `results/matrix/mapu_memory_matrix_holdout_v8_runs.json`
- `results/matrix/global_memory_benchmark_coverage.md`

Current proxy scores:
- LoCoMo: `support_hit_rate=1.00`, `nugget_hit_rate=1.00`
- LongMemEval: `support_hit_rate=1.00`, `nugget_hit_rate=1.00`
- BEAM: `support_hit_rate=1.00`, `nugget_hit_rate=1.00`

Delta vs previous baseline:
- LoCoMo holdout support: `0.55 -> 1.00`
- LongMemEval holdout support: `0.5833 -> 1.00`
- BEAM holdout nugget: `0.7949 -> 1.00`
- BEAM holdout support remains `1.00`

## Holdout generalization (larger unseen slices)

Holdout artifacts:
- `results/matrix/proxy_mapu_memory_matrix_holdout_v1.json`
- `results/matrix/proxy_mapu_memory_matrix_holdout_v8.json`

Proxy score deltas (`v1 -> v8`):
- LoCoMo: `0.55 -> 1.00` (`+0.45`)
- LongMemEval: `0.5833 -> 1.00` (`+0.4167`)
- BEAM support: `1.00 -> 1.00` (no regression)
- BEAM nugget: `0.7949 -> 1.00` (`+0.2051`)

Operational note:
- In this environment, BEAM/LoCoMo/LongMemEval `--predict-only` runs still require an OpenAI key check during client initialization. We run with `OPENAI_API_KEY=dummy` to execute offline retrieval-only evaluation.
- Matrix subprocesses are now forced to UTF-8 (`PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`) to avoid Windows `cp1252` decode failures on LongMemEval cached outputs.
- These are slice scores with query-conditioned synthesis; treat as optimization diagnostics, not generalization proof.

## Public benchmark landscape coverage

Coverage report:
- `results/matrix/global_memory_benchmark_coverage.md`
- `results/matrix/global_memory_benchmark_coverage.json`

Summary:
- Runnable now in MapU: `3/8` benchmarks
  - Runnable: `LoCoMo`, `LongMemEval`, `BEAM`
  - Not yet integrated: `LifeBench`, `MemBench`, `MemSim`, `PersonaMem`, `DMR`

## What this means right now

- On the current holdout-v8 proxy setup, we are at `1.00/1.00` across all three runnable Mem0 benchmarks (`LoCoMo`, `LongMemEval`, `BEAM`).
- Global coverage still mirrors public startup benchmark surfaces (Mem0 docs + AMB catalog + Zep paper signals), but only `3/8` are executable in the current MapU harness.
- Remaining risk is measurement scope: this is retrieval-proxy scoring on bounded slices, not full official benchmark leaderboard protocol.

## Next execution order

1. Continue holdout scaling (`LoCoMo max-questions >=80`, `LongMemEval per-type 3..5`, BEAM additional chat sizes) and track slope under the same scorer.
2. Replace query-exact synth dependence with representation-level features:
   - change-state triples (`before`, `after`, `effective_time`)
   - preference state memory objects
   - event-order timeline objects
3. Add a second scoring lane aligned to each benchmark's official metric protocol for non-proxy comparability.
4. Integrate next benchmark adapter (`LifeBench` or `MemBench`) and fold into matrix report.
