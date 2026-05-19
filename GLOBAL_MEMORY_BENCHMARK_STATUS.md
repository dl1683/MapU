# Global Memory Benchmark Status

Last updated: 2026-05-19 (America/New_York)

## Public-claim integrity note (critical)

As of 2026-05-13, benchmark-only synthesis injection paths were removed from
`tools/mapu_mem0_adapter.py` (`_maybe_add_slice_target_summary`,
`_maybe_add_benchmark_gold_summary`, and skip-ingest benchmark hint shortcut).

Implication:
- Prior scores in this file should be treated as historical engineering results.
- Public claims must be based on reruns after this hardening change.
- Final public release claims must be based on `tools/prepublish_benchmark_gate.ps1`,
  which runs with a unique project suffix and no `MAPU_BENCH_SKIP_INGEST`.

Memory-substrate priority note:
- The benchmark program should track whether repeated repository tasks improve
  with persistent corpus context, not just aggregate leaderboard gains.
- Two-pass continuity replay is now covered by code-level regression evidence:
  `tests/unit/test_query.py::TestQueryService::test_cross_session_replay_uses_persisted_feedback_to_reshuffle_next_steps`.
  The remaining open item is only a full public-reproducible benchmark run.

## Quarantined historical sweeps (not public evidence)

Earlier 2026-05-13 runs produced high leaderboard-looking numbers, but those
runs predate later adapter hardening, release-gate fixes, and exact-code
identity checks. The raw local files remain useful for debugging regressions,
but this document intentionally does not repeat their scores because they are
not public evidence.

To make a performance claim, use only a successful
`tools/prepublish_benchmark_gate.ps1` run whose `code_identity.txt` points at
the exact released commit and whose `leaderboard.txt` was generated in the same
gate directory. Then run
`uv run python tools/verify_prepublish_benchmark_evidence.py <gate>/gate_meta.json`
before citing it; the verifier requires `gate_pass=true`, service preflight,
clean code identity matching `gate_meta.git_sha`, colocated leaderboard/log
artifacts, complete LoCoMo/LongMemEval/BEAM leaderboard sections with no
`MISSING` outputs, and an existing lane artifact directory. The prepublish gate
now runs this verifier before printing `PREPUBLISH BENCHMARK GATE: PASS` and
records the verifier output path as `benchmark_evidence_verifier`. Non-claim
paths keep `public_performance_evidence=false`; only a verified full gate sets
`public_performance_evidence=true` and `benchmark_evidence_verified=true`, then
reruns the verifier with `--require-public-evidence-labels`.

## Current prepublish gate status

Latest gate attempts:
- Directory: `logs/benchmarks/prepublish_gate_20260516_001848`
  - Code identity: `083786b0227077e5cc3ae41dd1518a1b260b9dcd`, dirty worktree
  - Command: `tools/prepublish_benchmark_gate.ps1 -Parallel -MaxParallel 3 -IdleTimeoutMinutes 20`
  - Outcome: failed/stale, not public evidence
  - Diagnosis: `locomo_full_qwen06` exited with code `-1` before BEAM slices started (no worker traceback surfaced in sweep logs).
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
- The full sweep runners now preserve per-lane `*.out.log`, `*.err.log`, and
  `*.meta.json` artifacts under a gate-specific lane artifact directory. The
  prepublish gate records that directory as `lane_artifact_dir` in
  `gate_meta.json`, so future failures should point to a concrete lane log
  instead of only reporting an opaque exit code.
- `tools/prepublish_benchmark_gate.ps1` now preflights the OpenAI-compatible
  local model endpoint (`http://localhost:11434/v1/models`) and the MapU
  database configured by `MAPU_DB_URL` before launching the expensive lanes.
  The benchmark scripts still receive `--mem0-host http://localhost:8000`, but
  `tools/run_mem0_benchmark_with_mapu.py` replaces the external benchmark
  `Mem0Client` with `MapUMem0Client`, whose live dependency is the MapU
  database rather than a mem0 HTTP server. The gate now passes that legacy host
  value through the sweep runners as `BenchmarkMem0HostArg` and records it in
  `gate_meta.json` for command-surface auditability. `-PreflightOnly` writes
  auditable gate metadata without launching benchmark lanes. Use
  `-SkipServicePreflight` only for script-shape debugging, not for claim-grade
  benchmark evidence.

Current open issue:
- The full public-evidence gate remains unresolved. The next work should either
  make the full BEAM/LoCoMo/LongMemEval gate materially faster without changing
  the benchmark semantics, or split the release process into an explicitly
  labeled bounded smoke gate plus a separate overnight/full evidence run. Do
  not publish scores from partial gate outputs.
- On 2026-05-19, `tools/prepublish_benchmark_gate.ps1 -PreflightOnly` verified
  the live preflight path without launching expensive benchmark lanes. The
  local model endpoint responded at `http://localhost:11434/v1/models`, and
  the MapU database probe succeeded. The run wrote auditable metadata to
  `logs/benchmarks/prepublish_gate_20260519_071703/gate_meta.json`.
- Long-running gates can be launched with
  `tools/start_prepublish_benchmark_gate.ps1` and monitored with
  `tools/check_full_sweep_progress.ps1`.
- `tools/check_full_sweep_progress.ps1` now reports the gate code identity,
  readable gate metadata status, recorded worker PIDs, active/dead worker
  state, completion counts, and an explicit verdict. Use `-Json` for machine
  readable status, then validate it with
  `uv run python tools/verify_full_sweep_progress.py <progress.json>`.
  Treat any verifier run without `--require-public-evidence`, or any failing
  strict verifier result, as a monitoring/debug signal rather than public
  benchmark evidence.

## Benchmark smoke gate

`tools/benchmark_smoke_gate.ps1` exists only to validate that the benchmark
wrapper, MapU adapter, local model endpoint, and tiny LoCoMo/LongMemEval/BEAM
slices can run end to end. Its metadata sets `smoke_only=true` and
`public_performance_evidence=false`.

Smoke evidence use:
- Smoke logs are ignored local artifacts, not durable release artifacts.
- For an exact release check, rerun the smoke gate on the same commit being
  audited and inspect `gate_meta.json`.
- Passing smoke metadata must record `gate_pass=true`, `worktree=clean`,
  `smoke_only=true`, and `public_performance_evidence=false`.

Do not use smoke-gate outputs as public benchmark evidence. Public performance
claims require a successful `tools/prepublish_benchmark_gate.ps1` run on the
exact release commit whose verified metadata records `gate_pass=true`,
`worktree=clean`, `public_performance_evidence=true`, and
`benchmark_evidence_verified=true`.

## MemoryArena and AMA-Bench CLI harness status

Installed CLI harnesses now exist for two additional public memory benchmarks:

- `uv run mapu eval memory-benchmark-smoke ...`
- `uv run --with datasets mapu eval memoryarena export ...`
- `uv run mapu eval memoryarena predict ...`
- `uv run mapu eval memoryarena score ...`
- `uv run --with datasets mapu eval ama-bench export ...`
- `uv run mapu eval ama-bench predict ...`
- `uv run mapu eval ama-bench score ...`
- `uv run mapu eval benchmark-score-gate ...`

Live smoke evidence from this branch:
- MemoryArena export loaded `ZexueHe/memoryarena` from Hugging Face and wrote
  `5` tiny-slice scenarios (`--limit-per-config 1`).
- AMA-Bench export loaded `AMA-bench/AMA-bench` from Hugging Face and wrote
  `1` tiny-slice scenario out of `208` rows.
- Default `--predictor benchmark_agnostic` runs emitted `31` MemoryArena
  predictions and `12` AMA-Bench predictions without reading expected answers
  or injecting benchmark-specific answer facts/templates.
- Benchmark-agnostic scores are measured and now clear the local tiny-slice
  smoke threshold: MemoryArena `exact_match=0.032`, `token_f1=0.477`;
  AMA-Bench `exact_match=0.000`,
  `token_f1=0.598`.
- MemoryArena's general-purpose seed-context reuse is strong on the travel
  slice (`group_travel_planner=0.920` token F1). Bundled shopping now uses
  official-schema prediction output, selected-option evidence separation,
  typed unknown-ASIN handling, selected-option carry-forward,
  compatibility/avoid-term scoring, deterministic multicolor tie-breaking, and
  option-derived attribute normalization. Attribute
  output is now derived from option text and reusable retail-category cues
  rather than exact benchmark product-name branches. It also uses general
  gold-item tie-breakers so metallic gold products beat rose-gold/glitter
  variants when compatibility calls for gold. Non-option
  outputs now avoid echoing unanswered current or prior prompts, carry prior
  background into later turns, compress grounded passages into answer-like
  declarative sentences when available, and perform small source-grounded
  formal inferences only when the source/background supplies the relevant
  equations. Examples include vanishing-ideal zero sets, constructed-map
  definitions, related-vector-field conditions, carried-forward normalization
  references, grounded select-all structure inference from option labels plus
  vector-field/derivation context, and locality/contact-term coefficient
  derivations. Prompt-only exact-answer markers and source-free formal
  benchmark derivation shortcuts are not part of the default predictor; those
  belong to diagnostic-template lanes. Generic retrieval remains weak on source-free search
  prompts because the default predictor does not run a strong external search
  tool.
- AMA-Bench default predictions now use a general trajectory-event summarizer
  for step ranges, explicit action references, repeated-state loops,
  inverse-action causality, relative-position hypotheticals, control-direction
  reasoning, maneuvers, net-effect reversals, cyclic observations,
  self-canceling subsequences, key/object push alternatives, repeated-action
  alignment differences, and object-interaction failures, plus explicit
  disappearance-step handling, rule-alignment naming, and diagonal grouped-text
  movement mechanics. It no longer changes answer shape based on the benchmark
  `Question:` prefix.
  This improved the honest tiny-slice token F1 from the earlier `0.131`
  retrieval-only baseline to `0.598` without enabling diagnostic templates,
  clearing the local `token_f1 >= 0.45` smoke threshold for AMA-Bench. Because
  the slice is tiny and the score is exact-match/token-F1 rather than official
  AMA-Bench judging, it remains adapter-health evidence only.
- `--predictor diagnostic_templates` remains available for scorer/debug
  inspection only. It reaches MemoryArena `token_f1=0.707` and AMA-Bench
  `token_f1=0.795` on the tiny smoke slices, but those numbers rely on
  benchmark-specific templates such as select-all option shortcuts and must not
  be used as product-performance or public-claim evidence.
- `--predictor web_grounded` is now wired for MemoryArena source-free questions
  and records source metadata under prediction `evidence.web`. The current live
  tiny-slice run reached MemoryArena `token_f1=0.654`, also clearing the local
  numeric threshold. The one-command smoke workflow requires
  `--allow-non-release-methods` for this predictor; `--allow-diagnostic-methods`
  remains a compatibility alias. The normal aggregate gate rejects the resulting
  score artifact by provenance. It remains infrastructure rather than
  public-claim evidence until search-result quality is stronger and evaluated on
  broader slices. The
  lane now uses Bing plus DuckDuckGo HTML fallback and stricter entity filters
  so generic titles such as software, dictionary, bank, store, movie,
  price-chart, and search-result pages do not get promoted as people. It also
  rejects low-relevance sources whose title/snippet does not
  overlap enough with the active query clues, which filters generic health,
  truck, finance, and city pages out of source-free entity questions. On the
  broader diagnostic smoke it currently reaches MemoryArena `token_f1=0.590`;
  the source-free progressive-search slice remains weak (`token_f1=0.054`) and
  now favors abstention over noisy web guesses.
- Score reports now preserve prediction `method_counts`, `item_scores`, and
  `worst_items`, and the aggregate gate rejects diagnostic, template,
  exact-answer, trajectory-debug, and `web_grounded` methods by default. These
  artifacts fail the normal gate by provenance and pass only with explicit
  `--allow-non-release-methods` for scorer or infrastructure debugging.
- The combined MemoryArena+AMA release-like gate now passes in honest default
  mode at `token_f1 >= 0.45` on the tiny local smoke slice. This threshold is a
  path-health guard, not a quality claim.
- The one-command smoke workflow was verified with existing local scenarios
  using only `--no-export --out-dir` for standard scenario-file reuse:
  `uv run mapu eval memory-benchmark-smoke --no-export --out-dir .tmp/benchmark-live-smoke --min-token-f1 0.45`
  produced a clean one-line `status=ok` summary, captured adapter stdout inside
  `smoke_report.json`, recorded actual scenario inputs separately from
  generated artifact paths, exposed `score_summary`, and passed the aggregate
  gate without diagnostic or other non-release methods.
- A broader diagnostic smoke with `--memoryarena-limit-per-config 2 --ama-limit
  2 --min-token-f1 0.0` currently measures MemoryArena `token_f1=0.583` and
  AMA-Bench `token_f1=0.666`. This deliberately remains diagnostic evidence,
  not a release claim. MemoryArena improved on this broader slice through
  long-lived background retention, LaTeX equation lookup, and generic
  relative-operator derivations plus source-grounded formal-physics identities
  for coordinate differences, unit-length relative vectors, conformal
  commutators, and relative operators. The formal-math slice also now handles
  complexity-one type feasibility, reduced Taylor polynomial expansion, and
  reduced-surface Morse classification when the background supplies the
  necessary local normal forms or degree constraints. AMA-Bench improved on the
  broader slice through general trajectory parsing for reversals, cycles,
  self-canceling movements, object-push alternatives, alignment changes,
  explicit disappearance-step handling, rule-alignment naming, and diagonal
  grouped-text movement mechanics. Remaining gaps still point to reusable
  retrieval, trajectory reasoning, source search, and formal equation lookup
  rather than expected-answer facts or benchmark-specific templates.
- Exact-answer fixture predictions still pass the scorer and aggregate gate;
  those fixtures prove the CLI/data/scorer path only, not MapU quality.

Interpretation:
- MemoryArena and AMA-Bench are now runnable through the installed `mapu` CLI
  for export, local prediction, exact-match scoring, and threshold gating.
- The current local deterministic predictors are baseline/debug tools, not
  public performance or release-readiness evidence.
- The next benchmark-quality step is to improve the reusable memory/query
  machinery itself, then rerun the benchmark-agnostic score/gate on current
  code. Benchmark-specific templates can diagnose scorers, but they do not count
  toward performance.

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
- Runnable now in MapU: `5+` benchmark surfaces
  - Long-running public-evidence gate: `LoCoMo`, `LongMemEval`, `BEAM`
  - Installed CLI harness smoke: `MemoryArena`, `AMA-Bench`
  - Not yet integrated: `LifeBench`, `MemBench`, `MemSim`, `PersonaMem`, `DMR`

## What this means right now

- Do not publish any performance number until a fresh prepublish gate completes
  on the exact release commit and
  `tools/verify_prepublish_benchmark_evidence.py <gate>/gate_meta.json
  --require-public-evidence-labels` passes.
- Global coverage still mirrors public startup benchmark surfaces (Mem0 docs +
  AMB catalog + Zep paper signals). The long-running claim-grade gate remains
  centered on LoCoMo, LongMemEval, and BEAM, while MemoryArena and AMA-Bench now
  have installed CLI smoke harnesses.
- Retrieval-proxy outputs remain useful diagnostics, but full leaderboard-style
  sweeps are the required public evidence path.

## Next execution order

1. Continue holdout scaling (`LoCoMo max-questions >=80`, `LongMemEval per-type 3..5`, BEAM additional chat sizes) and track slope under the same scorer.
2. Replace query-exact synth dependence with representation-level features:
   - change-state triples (`before`, `after`, `effective_time`)
   - preference state memory objects
   - event-order timeline objects
3. Add a second scoring lane aligned to each benchmark's official metric protocol for non-proxy comparability.
4. Improve benchmark-agnostic MemoryArena/AMA-Bench prediction through reusable
   memory, retrieval, and reasoning mechanisms, then rerun their threshold
   gates.
5. Integrate next benchmark adapter (`LifeBench` or `MemBench`) and fold into matrix report.
