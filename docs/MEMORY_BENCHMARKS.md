# Memory benchmark plan

MapU should be evaluated as an agent-memory substrate, not just as a storage API.
The useful external benchmarks are the ones that force memory to affect later
actions across sessions.

## Benchmark priority

### 1. MemoryArena

Source: https://memoryarena.github.io/

Why it matters:

- Multi-session agentic tasks.
- Memory is used to guide future actions, not only answer recall questions.
- Public Hugging Face dataset is directly loadable.
- No Docker service is required for dataset export.

Runnable locally now:

```powershell
uv run --with datasets mapu eval memoryarena catalog
uv run --with datasets mapu eval memoryarena export --limit-per-config 5
uv run mapu eval memoryarena predict --scenarios data/benchmarks/memoryarena/scenarios.jsonl --out results/memoryarena_predictions.jsonl
uv run mapu eval memoryarena score --scenarios data/benchmarks/memoryarena/scenarios.jsonl --predictions results/memoryarena_predictions.jsonl --min-exact-match 0.80
```

Observed online dataset configs:

- `bundled_shopping`
- `progressive_search`
- `group_travel_planner`
- `formal_reasoning_math`
- `formal_reasoning_phys`

All use the `test` split.

### 2. AgentMemoryBench

Source: https://github.com/s010m00n/AgentMemoryBench

Why it matters:

- Evaluates continual agent memory across offline, online, replay, transfer, and
  repair modes.
- Separates system memory from personal memory.
- Covers code-grounded, embodied, web-grounded, and dialogue-grounded tasks.

Blocked locally right now:

- Requires Docker backend task services.
- This Windows environment currently has no Docker CLI/daemon available.

MapU integration shape:

- Implement a benchmark-side `MemoryMechanism` wrapper.
- `use_memory(task, messages)` should call MapU resume/query/gap APIs and inject
  the retrieved continuity context into the agent prompt.
- `update_memory(task, history, result)` should persist trajectory summaries,
  gaps, outcomes, and repair feedback into MapU.

### 3. AMA-Bench

Source: https://github.com/AMA-Bench/AMA-Bench
Dataset: https://huggingface.co/datasets/AMA-bench/AMA-bench

Why it matters:

- Evaluates long-horizon memory built from agent trajectories.
- Has a clean two-stage interface:
  `memory_construction(traj_text, task)` and `memory_retrieve(memory, question)`.

Runnable locally for dataset export:

```powershell
uv run --with datasets mapu eval ama-bench catalog
uv run --with datasets mapu eval ama-bench export --limit 5
uv run mapu eval ama-bench predict --scenarios data/benchmarks/ama_bench/scenarios.sample.jsonl --out results/ama_bench_predictions.jsonl
uv run mapu eval ama-bench score --scenarios data/benchmarks/ama_bench/scenarios.sample.jsonl --predictions results/ama_bench_predictions.jsonl --min-exact-match 0.80
```

Official scoring requirements:

- Hugging Face dataset.
- LLM judge/model configuration for official scoring.
- Linux/GPU recommended by the project.

MapU integration shape:

- `memory_construction` stores the trajectory into a MapU corpus and returns the
  corpus id plus constructed evidence/gap summary.
- `memory_retrieve` queries MapU and returns evidence-grounded context.

### 4. MemoryAgentBench

Source: https://github.com/hust-ai-hyz/MemoryAgentBench

Why it matters:

- Tests accurate retrieval, test-time learning, long-range understanding, and
  conflict resolution.
- Incremental multi-turn design is relevant to MapU.

Why it is lower priority than MemoryArena:

- Heavier benchmark environment.
- Public README says the framework is still being improved for custom memory
  agents.

## MapU-specific success criteria

External benchmark score is not enough. A useful MapU run should report:

- task success or answer accuracy
- resume/handoff quality
- number of persisted gaps
- number of stale or missing gap contracts
- evidence-anchor coverage
- whether later sessions reused prior memory
- token/read reduction versus no-memory baseline
- whether contradiction/repair feedback updated memory correctly

The local `score` commands are intentionally gate-capable: they return nonzero
when no predictions match exported scenario keys and can enforce
`--min-exact-match`. Do not treat a score artifact as release evidence unless
it was produced from the current code state and a declared threshold.

After producing score artifacts, run the aggregate gate:

```powershell
uv run mapu eval benchmark-score-gate --score memoryarena=results/memoryarena_score.json:0.80 --score ama_bench=results/ama_bench_score.json:0.80 --out results/memory_benchmark_score_gate.json
```

For free-form answer lanes, the gate can target a non-exact numeric metric from
the score file:

```powershell
uv run mapu eval benchmark-score-gate --score ama_bench=results/ama_bench_score.json:token_f1:0.65 --out results/memory_benchmark_score_gate.json
```

Gate rows expose metric-neutral `threshold` and `threshold_metric` fields.
Older reports also include `min_exact_match` as a compatibility alias; prefer
the neutral fields when inspecting non-exact metrics such as `token_f1`.
The CLI summary also includes `failure_details` on failure, with benchmark,
metric, actual metric value, threshold, and failure reason, so operators do not
need to open the gate JSON just to see why a gate failed.
MemoryArena and AMA-Bench score reports also include `item_scores` and
`worst_items` so benchmark misses can be inspected without manually joining the
scenario and prediction JSONL files. These fields are diagnostic only; gates
still use the declared aggregate metric and threshold.

To inspect the worst scored items from any score report:

```powershell
uv run mapu eval benchmark-score-inspect .tmp/benchmark-live-smoke/memoryarena_score.json --top 5
```

The inspect output includes aggregate metrics, `method_counts`, `by_config` or
`by_type` bucket summaries when present, and the selected `worst_items`, so an
operator can see both provenance and the weakest slice without opening the raw
JSON by hand.

The legacy script entrypoint is kept for repo automation and calls the same
packaged implementation:

```powershell
uv run python tools/memory_benchmark_score_gate.py --score memoryarena=results/memoryarena_score.json:0.80 --score ama_bench=results/ama_bench_score.json:0.80 --out results/memory_benchmark_score_gate.json
```

Use `--require-clean-git` only for release evidence runs. During active
development, the gate still records git SHA and dirty state so score artifacts
are auditable without pretending the working tree was release-clean.

## CLI harness smoke

The benchmark CLI surface can be smoke-tested without claiming MapU task
performance by exporting tiny live slices and scoring exact-answer predictions:

The preferred one-command smoke path is:

```powershell
uv run --with datasets mapu eval memory-benchmark-smoke --out-dir .tmp/benchmark-live-smoke --memoryarena-limit-per-config 1 --ama-limit 1 --min-token-f1 0.45
```

That command runs MemoryArena and AMA-Bench export, benchmark-agnostic
prediction, score, and aggregate gate. It should return nonzero until the honest
default predictors clear the declared threshold. By default, stdout is a single
JSON summary with `status`, `gate_status`, `failed`, `score_summary`,
`smoke_only`, and `public_performance_evidence`. Inner export/predict/score
stdout is captured in `smoke_report.json` under `steps`; add `--verbose-steps`
only when debugging the individual adapters. The report also records actual
scenario inputs under `inputs`, generated artifacts under `paths`, and a compact
gate view under `score_summary`. To reuse existing scenario JSONL files without
downloading datasets:

```powershell
uv run mapu eval memory-benchmark-smoke --no-export --out-dir .tmp/benchmark-live-smoke --min-token-f1 0.45
```

With `--no-export`, the smoke command defaults to
`.tmp/benchmark-live-smoke/memoryarena_scenarios.jsonl` and
`.tmp/benchmark-live-smoke/ama_scenarios.jsonl`. Use explicit
`--memoryarena-scenarios` and `--ama-scenarios` only when reusing scenario files
from a different directory.

The expanded manual equivalent is:

```powershell
uv run --with datasets mapu eval memoryarena export --limit-per-config 1 --out .tmp/benchmark-live-smoke/memoryarena_scenarios.jsonl
uv run --with datasets mapu eval ama-bench export --limit 1 --out .tmp/benchmark-live-smoke/ama_scenarios.jsonl
uv run mapu eval memoryarena predict --scenarios .tmp/benchmark-live-smoke/memoryarena_scenarios.jsonl --out .tmp/benchmark-live-smoke/memoryarena_predictions_mapu_local.jsonl
uv run mapu eval ama-bench predict --scenarios .tmp/benchmark-live-smoke/ama_scenarios.jsonl --out .tmp/benchmark-live-smoke/ama_predictions_mapu_local.jsonl
uv run mapu eval memoryarena score --scenarios .tmp/benchmark-live-smoke/memoryarena_scenarios.jsonl --predictions .tmp/benchmark-live-smoke/memoryarena_predictions_mapu_local.jsonl --out .tmp/benchmark-live-smoke/memoryarena_score_mapu_local.json
uv run mapu eval ama-bench score --scenarios .tmp/benchmark-live-smoke/ama_scenarios.jsonl --predictions .tmp/benchmark-live-smoke/ama_predictions_mapu_local.jsonl --out .tmp/benchmark-live-smoke/ama_score_mapu_local.json
uv run mapu eval memoryarena score --scenarios .tmp/benchmark-live-smoke/memoryarena_scenarios.jsonl --predictions .tmp/benchmark-live-smoke/memoryarena_predictions_exact.jsonl --out .tmp/benchmark-live-smoke/memoryarena_score_exact.json --min-exact-match 1.0
uv run mapu eval ama-bench score --scenarios .tmp/benchmark-live-smoke/ama_scenarios.jsonl --predictions .tmp/benchmark-live-smoke/ama_predictions_exact.jsonl --out .tmp/benchmark-live-smoke/ama_score_exact.json --min-exact-match 1.0
uv run mapu eval benchmark-score-gate --score memoryarena=.tmp/benchmark-live-smoke/memoryarena_score_exact.json:1.0 --score ama_bench=.tmp/benchmark-live-smoke/ama_score_exact.json:1.0 --out .tmp/benchmark-live-smoke/score_gate_exact.json
```

The default `predict` commands use `--predictor benchmark_agnostic`. That mode
can use exported scenario inputs such as seed context and trajectory text, but
it must not inject benchmark-specific answer facts, product rules, or
domain-specific benchmark templates. The `*_exact.jsonl` predictions are
optional scorer sanity fixtures derived from expected answers; they prove the
installed CLI, dataset loading, JSONL shape, scorer, threshold, and aggregate
gate, but they are not release evidence for MapU retrieval quality.

Current benchmark-agnostic tiny-slice scores:
- MemoryArena: `31` predictions, `exact_match=0.032`, `token_f1=0.635`.
  The strongest general-purpose signal is exported seed-context travel-plan
  reuse (`group_travel_planner=0.920` token F1). Bundled shopping improved to
  `0.910` token F1 through official-schema prediction output, selected-option
  evidence separation, typed unknown-ASIN handling, compatibility/avoid-term
  scoring, deterministic multicolor tie-breaking, and option-derived attribute
  normalization. Attribute output is now derived from option text and reusable
  retail-category cues rather than exact benchmark product-name branches. Color
  and material tie-breakers are generic parser behavior, not product-specific
  answer facts.
  Non-option outputs now avoid echoing unanswered current or prior prompts,
  carry recent prior background into later turns, and compress grounded
  passages into answer-like declarative sentences when available. The default
  path can quote exact-answer markers and equations from supplied source or
  background text, but it ignores exact-answer markers embedded in prompts.
  Prompt-only formal math/physics shortcuts are deliberately excluded from the
  default predictor so the smoke path does not depend on benchmark-known
  derivations. The default predictor can apply source-grounded formal synthesis
  when the supplied background contains the needed definitions or local normal
  forms. Generic retrieval remains weak on source-free search prompts because
  the default predictor does not run a strong external search tool.
- AMA-Bench: `12` generic trajectory-event predictions, `exact_match=0.167`,
  `token_f1=0.716`. The default output now derives step-range, explicit
  action-reference, inverse-action causality, loop, relative-position,
  control-direction, maneuver, object-interaction, disappearance-step,
  rule-alignment, and grouped-text movement summaries from the supplied
  trajectory and question text rather than using diagnostic benchmark
  templates or changing answer shape based on the benchmark `Question:` prefix.
  This tiny-slice lane now clears the local `token_f1 >= 0.45` path-health
  threshold in honest default mode.

A broader benchmark-agnostic smoke with
`--memoryarena-limit-per-config 2 --ama-limit 2` is intentionally not a release
gate, but now clears the same local path-health threshold: MemoryArena
`token_f1=0.582` and AMA-Bench `token_f1=0.671`. The broader MemoryArena slice
improved after moving source-evidence-gated formal synthesis into the default
predictor while keeping prompt-only shortcuts in diagnostic mode. It now uses
long-lived background retention, LaTeX equation lookup, source-grounded
coordinate-difference and relative-operator derivations, unit-length relative
vectors, conformal commutators, relative Casimir and Hamiltonian forms,
similarity-invariant $D/K$ forms, log-Vandermonde derivative identities, and
$N=3$ angular similarity forms, plus formal-math derivations for complexity-one
type feasibility, reduced Taylor polynomial expansion, reduced-surface Morse
classification, explicit map construction, and vanishing-ideal zero sets when
the prompt or background supplies the relevant definitions, local normal forms,
or equations. The broader AMA slice improved after adding general trajectory parsing for
net-effect reversals, cyclic observations, self-canceling subsequences,
key/object push alternatives, repeated-action alignment differences, explicit
disappearance-step handling, rule-alignment naming, and diagonal grouped-text
movement mechanics, plus concise direct-cause and loop-breaking answer shaping
when the question asks for a short causal result. Remaining broader failures are dominated by source-free
progressive search, so future work should improve reusable retrieval and source
search rather than adding benchmark-answer facts.

`--predictor diagnostic_templates` is available only as a scorer/debug lane. On
the same tiny slices it reaches MemoryArena `token_f1=0.707` and AMA-Bench
`token_f1=0.795`, but those numbers rely on benchmark-specific templates such
as select-all option shortcuts and must not be used as product-performance or
public-claim evidence.

`--predictor web_grounded` is a separate MemoryArena retrieval lane for
source-free questions. It uses live web search snippets and records source
metadata under each prediction's `evidence.web` field. The current implementation
abstains when source relevance is weak; on the tiny smoke slice it reached
MemoryArena `token_f1=0.654`, also clearing the former local numeric threshold. The
one-command smoke workflow requires the preferred `--allow-non-release-methods`
flag for this predictor; `--allow-diagnostic-methods` remains a compatibility
alias. The normal aggregate gate rejects the resulting score artifact by provenance.
Treat it as runnable infrastructure for external-evidence
experiments; it still needs stronger search-result quality before it should
support public claims. The
web lane now uses Bing plus DuckDuckGo HTML fallback and stricter entity filters
so generic titles such as software, dictionary, bank, store, movie,
price-chart, and search-result pages do not get promoted as people. It also
rejects low-relevance sources whose title/snippet
does not overlap enough with the active query clues, which filters generic
health, truck, finance, and city pages out of source-free entity questions. On
the broader diagnostic smoke it currently reaches MemoryArena `token_f1=0.590`;
the source-free progressive-search slice remains weak (`token_f1=0.054`) and
favors abstention over noisy web guesses.

The aggregate score gate enforces that boundary. Score reports now carry
`method_counts`, and `mapu eval benchmark-score-gate` rejects diagnostic,
template, exact-answer, trajectory-debug, and `web_grounded` prediction methods
by default even if their numeric score clears the threshold. Use the preferred
`--allow-non-release-methods` flag only for scorer or infrastructure debugging,
never for release or public-claim gates. `--allow-diagnostic-methods` remains a
compatibility alias. Public-performance gates should use the default
`benchmark_agnostic` predictors and should not rely on benchmark-known answer
facts, templates, or live web lookup for source-free items.

The runtime isolation check is also part of this boundary:

```powershell
uv run python tools/verify_benchmark_isolation.py
```

It allows benchmark identifiers only in evaluation adapters and the eval CLI
surface, and it rejects benchmark prompt-format shortcuts such as branching on
`Question:` prefixes.

The release-like local gate now passes the tiny MemoryArena+AMA smoke artifacts
at `token_f1 >= 0.45`:

```powershell
uv run mapu eval benchmark-score-gate --score memoryarena=.tmp/benchmark-live-smoke/memoryarena_score.json:token_f1:0.45 --score ama_bench=.tmp/benchmark-live-smoke/ama_score.json:token_f1:0.45 --out .tmp/benchmark-live-smoke/score_gate.json
```

The exact local command verified on this branch was:

```powershell
uv run mapu eval memory-benchmark-smoke --no-export --out-dir .tmp/benchmark-live-smoke --min-token-f1 0.45
```

## Immediate path

Start with MemoryArena export. It gives us online benchmark sessions now, without
waiting on Docker. Then run paired MapU-vs-baseline agent loops over those
scenarios.

AMA-Bench should be the second export because it directly tests long-horizon
trajectory memory and question answering.
