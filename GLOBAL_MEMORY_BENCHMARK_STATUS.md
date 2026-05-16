# Global Memory Benchmark Status

Last updated: 2026-05-15 (America/New_York)

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

## Current prepublish gate status

Latest gate attempts:
- Directory: `logs/benchmarks/prepublish_gate_20260515_190928`
  - Code identity: `f4cd4cc1080452a884827b3030c6349834c22f6a`, clean worktree
  - Command: `tools/prepublish_benchmark_gate.ps1 -Parallel -MaxParallel 3 -IdleTimeoutMinutes 20`
  - Outcome: manually stopped, not public evidence
  - Diagnosis: the child-worker idle detection fix worked and the gate kept
    making progress, but the full BEAM 100K lane was too slow for a practical
    prepublish check on this host/model stack. Partial outputs at stop time:
    BEAM 100K `40` files, LoCoMo `391` files, LongMemEval `594` files.
- Directory: `logs/benchmarks/prepublish_gate_20260515_184056`
  - Code identity: `0c79ed0a95d56168f36d0f6c6c3a24c51eb33825`, clean worktree
  - Command: `tools/prepublish_benchmark_gate.ps1 -Parallel -MaxParallel 3 -IdleTimeoutMinutes 20`
  - Outcome: failed, not public evidence
  - Diagnosis: the first idle-timeout implementation watched the tracked parent
    process but not its child worker process, so it falsely timed out LoCoMo
    even though LoCoMo result files were still being written shortly before the
    timeout.
- Directory: `logs/benchmarks/prepublish_gate_20260515_180011`
  - Code identity: `238cadecb4d45df2542f0c3d9eb86a7337d0db11`, clean worktree
  - Command: `tools/prepublish_benchmark_gate.ps1 -Parallel -MaxParallel 6`
  - Outcome: failed/aborted, not public evidence

What changed:
- Restoring `.tmp/memory-benchmarks` cured the earlier immediate harness
  failure. The wrappers imported and the run produced real LoCoMo,
  LongMemEval, BEAM 100K, BEAM 500K, BEAM 1M, and BEAM 10M output files.
- BEAM 100K then stopped making CPU/log/result progress after
  `100K_0_q2_contradiction_resolution.json`, so the lane was terminated.
- Because this gate did not complete and did not generate a same-directory
  `leaderboard.txt`, it supports only the diagnosis above. It does not support
  publishing any benchmark score.

Follow-up hardening:
- `tools/run_full_leaderboard_sweeps_parallel.ps1` now has per-lane wall-clock
  and idle-progress timeouts, normalizes null exit codes as failures, and stops
  sibling lanes on first failure to avoid burning compute after the gate is
  already invalid.
- The idle-progress detector now includes direct child worker CPU to avoid
  classifying an idle parent wrapper as a stalled benchmark while the worker is
  still active.
- `tools/prepublish_benchmark_gate.ps1` passes those timeout settings through
  and records them in `code_identity.txt` and `gate_meta.json`.

Current open issue:
- The full public-evidence gate remains unresolved. The next work should either
  make the full BEAM/LoCoMo/LongMemEval gate materially faster without changing
  the benchmark semantics, or split the release process into an explicitly
  labeled bounded smoke gate plus a separate overnight/full evidence run. Do
  not publish scores from partial gate outputs.
- Long-running gates can be launched with
  `tools/start_prepublish_benchmark_gate.ps1` and monitored with
  `tools/check_full_sweep_progress.ps1`.
- `tools/check_full_sweep_progress.ps1` now reports the gate code identity,
  readable gate metadata status, recorded worker PIDs, active/dead worker
  state, completion counts, and an explicit verdict. Use `-Json` for machine
  readable status. Treat any verdict other than complete passing full-gate
  evidence as a monitoring/debug signal, not public benchmark evidence.

## Benchmark smoke gate

`tools/benchmark_smoke_gate.ps1` exists only to validate that the benchmark
wrapper, MapU adapter, local model endpoint, and tiny LoCoMo/LongMemEval/BEAM
slices can run end to end. Its metadata sets `smoke_only=true` and
`public_performance_evidence=false`.

Smoke evidence use:
- Smoke logs are ignored local artifacts, not durable release artifacts.
- For an exact release check, rerun the smoke gate on the same commit being
  audited and inspect `gate_meta.json`.
- Passing metadata must record `gate_pass=true`, `worktree=clean`,
  `smoke_only=true`, and `public_performance_evidence=false`.

Do not use smoke-gate outputs as public benchmark evidence. Public performance
claims still require a successful `tools/prepublish_benchmark_gate.ps1` run on
the exact release commit.

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
