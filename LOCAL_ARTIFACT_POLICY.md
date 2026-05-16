# Local Artifact Policy

MapU keeps generated benchmark, dataset, cache, and private environment state
out of git. These paths are expected to appear in `git status --ignored` on a
working machine:

- `.env`
- `.venv/`
- `.tmp/`
- `datasets/`
- `logs/`
- `results/`
- `.claude/`
- `.process/`

Do not commit those paths. `tools/clean_local_artifacts.ps1` removes disposable
caches and temporary audit folders while preserving `.tmp/memory-benchmarks`,
which benchmark runners import at runtime.

Large benchmark outputs and datasets should stay local. Public performance
claims must cite exact gate metadata and summaries, not raw local directories.
