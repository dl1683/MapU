# MapU AMA-Bench leaderboard result

Status date: 2026-05-18.

MapU has a clean official-protocol AMA-Bench run that would rank first on the
AMA-Bench memory-agent leaderboard if submitted as an agent-memory system.

This file is a public-facing pointer from the main MapU repository. The full
harness and method-card materials are published separately at:

https://github.com/dl1683/memory-benchmark-harness

## Result

- Benchmark: AMA-Bench.
- Category: Agent.
- System: MapU memory backend plus Gemini 3.1 Flash-Lite solver and judge.
- Episodes: 208.
- Judged answers: 2,496.
- Official macro accuracy: `0.626577255143205`.
- Export warnings: none.
- API status during completion audit: `/health` returned `status: ok`,
  `version: 0.1.0`.

Live leaderboard comparison at audit time:

- Memory-agent leaderboard leader: `AMA-agent`, `0.557925`.
- MapU candidate score: `0.626577255143205`.
- Candidate rank on memory-agent board: `#1`.
- Model-only leaderboard leader: `gpt 5.2`, `0.6982833333333334`.
- Candidate rank on model-only board: `#3`.

The correct public claim is therefore: MapU clears the AMA-Bench memory-agent
leaderboard bar. It should not be described as the top raw model-only result.

## Domain breakdown

| Domain | Score |
| --- | ---: |
| GAME | 0.8035 |
| WEB | 0.6814 |
| TEXT2SQL | 0.6580 |
| OPENWORLD_QA | 0.6288 |
| EMBODIED_AI | 0.5109 |
| SOFTWARE | 0.4768 |

Capability breakdown:

| Domain | A | B | C | D |
| --- | ---: | ---: | ---: | ---: |
| TEXT2SQL | 0.8296 | 0.7712 | 0.7761 | 0.2549 |
| SOFTWARE | 0.3632 | 0.4800 | 0.3836 | 0.6806 |
| WEB | 0.6240 | 0.7957 | 0.6667 | 0.6393 |
| GAME | 0.7750 | 0.8000 | 0.8222 | 0.8167 |
| EMBODIED_AI | 0.5246 | 0.8000 | 0.5667 | 0.1525 |
| OPENWORLD_QA | 0.5714 | 0.6632 | 0.5140 | 0.7667 |

## Reproduction path

The published harness repo contains the runnable benchmark harness, official
submission exporter, leaderboard comparator, chunked run scripts, and method
card.

Canonical command from the harness repo:

```powershell
$env:GEMINI_API_KEY = "<key>"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_mapu_ama_official_chunked.ps1 `
  -RunId gemini_official_full_20260518 `
  -ChunkSize 8 `
  -Concurrency 4 `
  -Solver gemini `
  -SolverModel gemini-3.1-flash-lite `
  -Judge gemini `
  -JudgeModel gemini-3.1-flash-lite `
  -SolverMaxTokens 2048 `
  -JudgeMaxTokens 512 `
  -Resume
```

The chunked runner now also supports `-ChunkWorkers` for parallel chunk
execution.

## Claim discipline

This result should be used as evidence that MapU is competitive as a memory
agent substrate. It is not proof that MapU has solved general memory, and it
does not replace longer-horizon continuity validation in real coding/research
workflows.

Anti-overfitting constraints used for this run:

- No oracle flags.
- No benchmark-cue flags.
- No expected-answer leakage into adapter answer calls.
- No answer tables.
- No scenario-specific branches keyed to episode IDs or prompt identities.
- Generic structural memory improvements only: event relations, retrieval,
  provenance, state transitions, and synthesis support.

## Publication status

The GitHub evidence is now public through the MapU repository and the standalone
harness repository. The official AMA-Bench Hugging Face leaderboard submission
has not yet been uploaded.

To submit officially, the remaining owner-provided fields are:

- Display name.
- Organization/name.
- Contact email.
- Confirmation that the submission should be uploaded as `Agent`.
