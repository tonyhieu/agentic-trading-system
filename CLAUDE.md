# Agentic Trading System — Agent Bootstrap

This repository runs autonomous execution-algorithm research. The trading
strategy is held fixed; the execution algorithm is the variable under study.
A research agent reads a brief, runs one iteration of a research loop,
backtests an execution algorithm against a registered baseline, and logs
the outcome.

## If you are a research agent

Your full instruction set is **`docs/OBJECTIVE.md`**. Read it in full before
doing anything else.

- **Hyperparameters**: `research/config.yaml` — single source of truth for
  numeric values (dates, gate thresholds, refinement targets, loop limits).
  When values here conflict with prose in OBJECTIVE.md, this file wins.
- **Skills** (preloaded into the researcher subagent via its `skills:` frontmatter; live at `.claude/skills/<name>/SKILL.md`):
  - `backtest` — running `run_backtest()`, metrics, registering a new execution algorithm
  - `analysis` — exploratory analysis of training-set market data (raw DBN inspection)
  - `snapshot` — saving a passing execution algorithm to S3
  - `evaluate` — retrieving the Lambda evaluator's out-of-sample report after snapshotting
- **Runtime state**: `research/`
  - `CONTEXT_SNAPSHOT.md` — auto-regenerated boot summary (recent DB entries, live gate thresholds, recent NOTES.md, cross-window comparability flag). Read first; fall back to the full files only for detail.
  - `program_database.json` — append-only log of every attempt (read on entry, write on exit)
  - `NOTES.md` — assumption alerts for the human operator (§8)
- **Algorithm code**: `execution_algos/<algo-id>/` — kebab-case IDs

### Restrictions

- You are not allowed to read the `strategies/` folder. DO NOT READ THIS FOLDER.

## Conventions

- Algorithm IDs are kebab-case and match `execution_algos/<algo-id>/` directory names
- New algorithms must be registered in `execution_algos/__init__.py →
  _EXEC_ALGORITHM_FACTORIES` before `run_backtest()` will find them
- One invocation = one research iteration. The agent does not loop internally
- The agent appends to `program_database.json` and commits it in the same git
  commit as the algorithm code (single-writer, append-only)
- Honesty rules in `OBJECTIVE.md §8` are non-negotiable — raw numbers, flagged
  trade counts, no cherry-picked date ranges
