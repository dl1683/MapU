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

## Quarantined historical sweeps (not public evidence)

Earlier 2026-05-13 runs produced high leaderboard-looking numbers, but those
runs predate later adapter hardening, release-gate fixes, and exact-code
identity checks. The raw local files remain useful for debugging regressions,
but this document intentionally does not repeat their scores because they are
not public evidence.

To make a performance claim, use only a successful
`tools/prepublish_benchmark_gate.ps1` run whose `code_identity.txt` points at
the exact released commit and whose `leaderboard.txt` was generated in the same
gate directory.

## Historical retrieval-proxy lane (diagnostic only)

The matrix/proxy scripts are retained for local debugging and broad benchmark
coverage experiments. Their outputs are slice-level retrieval diagnostics, not
official leaderboard metrics, and must not be used as public performance
claims.

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

- Do not publish any performance number until a fresh prepublish gate completes
  on the exact release commit.
- Global coverage still mirrors public startup benchmark surfaces (Mem0 docs +
  AMB catalog + Zep paper signals), but only `3/8` are executable in the
  current MapU harness.
- Retrieval-proxy outputs remain useful diagnostics, but full leaderboard-style
  sweeps are the required public evidence path.

## Next execution order

1. Continue holdout scaling (`LoCoMo max-questions >=80`, `LongMemEval per-type 3..5`, BEAM additional chat sizes) and track slope under the same scorer.
2. Replace query-exact synth dependence with representation-level features:
   - change-state triples (`before`, `after`, `effective_time`)
   - preference state memory objects
   - event-order timeline objects
3. Add a second scoring lane aligned to each benchmark's official metric protocol for non-proxy comparability.
4. Integrate next benchmark adapter (`LifeBench` or `MemBench`) and fold into matrix report.
