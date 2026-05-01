# CLAUDE.md — Project Orientation for Claude Code

You are the main coordinator for an autonomous **execution-algorithm** research project at the University of Chicago Project Lab (Spring 2026). The project's central question, per the recent `Rename strategies → execution_algos` refactor: **execution algorithms are the variable under study**. The trading strategy is held fixed; what varies is how orders are sent to the venue.

## First action, every session

Read these in order before doing anything else:

1. `docs/PROBLEM_DEFINITION.md` — the metatask, evaluation, research loop, refinement loop, program database schema, and NOTES.md format. **Read in full.**
2. `SKILLS.md` — the snapshot system, data retrieval, Docker, evaluator, and local-debugging contracts. **This is the canonical operations guide and overrides anything else if they conflict.**
3. `research/program_database_momentum.json`, `research/program_database_mean_reversion.json`, `research/program_database_microstructure.json` — what each island has tried so far. Some may not exist yet on a fresh checkout; that is expected.

Do not proceed to user instructions until these are read.

## Architecture: island-based parallel execution-algorithm research

Three parallel islands explore execution algorithms, each scoped to a different design philosophy for how to time and shape order flow. Each island is a subagent defined in `.claude/agents/`:

| Island | Execution design philosophy | Subagent file |
|---|---|---|
| `momentum-exec-island` | Trend-aware execution: speed up with the trend, slow down against it, breakout-triggered participation | `.claude/agents/momentum-exec-island.md` |
| `mean-reversion-exec-island` | Reversion-timed execution: wait for price to revert toward VWAP/midprice before placing, exploit spread cycles | `.claude/agents/mean-reversion-exec-island.md` |
| `microstructure-exec-island` | Flow-aware execution: use order-flow imbalance, book pressure, and trade-sign signals to choose order timing and aggressiveness | `.claude/agents/microstructure-exec-island.md` |

**All three islands write `ExecAlgorithm` subclasses, not `Strategy` subclasses.** The strategy is fixed (`ema_cross` for the local evaluator, per `scripts/local-evaluator.py`); islands only vary the execution algorithm that intercepts and routes orders.

Islands explore independently. They do not communicate during a research cycle. Each writes to its own program database and its own algorithm directories under `execution_algos/`.

This isolation is deliberate: it maximizes diversity of exploration and prevents one island's findings from biasing another's hypotheses.

## How to invoke the islands

When the user asks for "a research cycle", "explore execution algorithms", or names one or more islands, invoke the corresponding subagents from `.claude/agents/`. Run them in parallel if the runtime supports it; otherwise run them sequentially. Either way, islands must not share intermediate findings within a cycle. If subagent invocation is not supported in this runtime, emulate one island at a time by following its markdown spec exactly.

After all islands return:

1. Read each island's program database.
2. Identify the highest-scoring algorithm across all three by the execution-quality metrics defined in `SKILLS.md` (slippage_bps, fill_accuracy_pct, latency_ms, cost_bps).
3. Summarize for the user: which islands ran, how many hypotheses each tried, what passed local evaluation, what failed, and the top candidate.

If the user asks for one island specifically (e.g., "run momentum-exec-island"), invoke only that one.

## Default cycle size

Unless the user explicitly requests deeper exploration (e.g., "run 5 hypotheses per island"), default to **2 hypotheses per island per cycle**. Each island's `.md` defines a hard cap of 5; this default keeps a smoke-test cycle cheap while still showing within-island diversity.

## Project conventions

These apply to you and to every island. They derive from `SKILLS.md` and `docs/PROBLEM_DEFINITION.md`:

- **Algorithm code lives at** `execution_algos/<algo_module>/`. The directory name is snake_case (Python package requirement). The kebab-case `<algo-name>` used by evaluator commands and `snapshots/` branches maps to `<algo_module>` by replacing hyphens with underscores. Match the layout in `execution_algos/simple_execution_strategy/`.
- **Algorithm notes live at** `execution_algos/<algo_module>/NOTES.md`. Format defined in `docs/PROBLEM_DEFINITION.md` §10. Required before snapshotting.
- **Local evaluation results live at** `local-cache/evaluation-reports/<algo-name>/<timestamp>_evaluation_report.json` (per `scripts/local-evaluator.py`).
- **Each island has its own program database**: `research/program_database_<island-key>.json` (e.g., `program_database_momentum.json`). Append-only, never delete entries. Schema strictly per `docs/PROBLEM_DEFINITION.md` §9.
- **Global ambiguity alerts go in** `research/NOTES.md` per `docs/PROBLEM_DEFINITION.md` §8. Print `⚠ NOTE WRITTEN: ...` whenever you write to it.
- **Data is accessed via** `scripts/data_retriever.py` or via `scripts/local-evaluator.py` (which downloads in-sample data automatically). Cached partitions live at `data-cache/glbx-mdp3-market-data/v1.0.0/`. Do not make ad-hoc S3 or network calls.

## The full research-and-evaluation pipeline (per SKILLS.md)

Every island follows this pipeline end-to-end. Steps 5–7 are the part most often skipped — do not skip them:

```
1. HYPOTHESIZE (write hypothesis to NOTES.md before writing code)
2. IMPLEMENT (write algo file in execution_algos/<algo_module>/)
3. WRITE NOTES.md (Hypothesis section per §10)
4. LOCAL EVALUATE (run scripts/local-evaluator.py <algo-name> 2)
   ├─ FAIL → log to program database, next hypothesis
   └─ PASS → continue
5. REFINE (per docs/PROBLEM_DEFINITION.md §6, up to 5 iterations)
6. APPEND backtest observations + refinement log to NOTES.md
7. CLOUD EVALUATE (push snapshots/<algo-name> branch → triggers Lambda)
8. LOG to program_database_<island>.json (every attempt — pass, close, fail)
```

The cloud evaluator costs ~$0.30 per run and uses out-of-sample data (2026-03-30 to 2026-04-06). The local evaluator is free and uses in-sample data (2026-03-23 to 2026-03-29). **Always exhaust the local evaluator before triggering the cloud evaluator.** This rule is non-negotiable per `SKILLS.md` ("Always test locally before cloud evaluation").

## Hard rules

These are non-negotiable, for both you and every island:

- **Never fabricate metrics.** Report only what `scripts/local-evaluator.py` or the cloud Lambda actually produced.
- **Never delete entries from any program database.** Append only. Failed entries prevent re-exploring dead ends.
- **Never sugarcoat a degraded result.** If the local evaluator reports a regression, log it as a regression.
- **Never skip the local evaluator before triggering the cloud Lambda.** Cloud evaluation is for vetted candidates only.
- **Never modify shared infrastructure files** (`backtest_engine/backtest_low_level.py`, `execution_algos/__init__.py`, `strategies/__init__.py`) **as part of routine algorithm authoring.** These files now support dynamic algorithm discovery (see "How registration works" below); writing a new algorithm should never require editing them. If you genuinely believe a change is needed, write a blocking ambiguity to `research/NOTES.md` and stop.
- **Never let an island propose strategies outside its execution-design philosophy.** See each island's definition for the scope boundary.
- **Never push to `main` directly.** Use `snapshots/<algo-name>` branches per `SKILLS.md` (this triggers automated S3 backup and cloud evaluation).

## How registration works (you do not need to register manually)

`execution_algos/__init__.py` resolves algorithms in two stages:

1. **Explicit registry** — known, vetted algorithms (currently just `simple`).
2. **Dynamic fallback** — if the name is not in the registry, it tries to import `execution_algos/<snake_case_name>/` and call its `get_execution_algorithm` function.

Hyphens in algorithm names are mapped to underscores when resolving the module path. So an algorithm called `momentum-exec-trend-burst-v1` (used in `snapshots/<algo-name>` branches and `scripts/local-evaluator.py <algo-name>` invocations) resolves to the directory `execution_algos/momentum_exec_trend_burst_v1/`.

**Net effect for islands**: write your algorithm directory with a snake_case name and a top-level `get_execution_algorithm` function exposed in its `__init__.py` (just like `simple_execution_strategy/`). No edits to shared files required.

## What is *not* in scope this iteration

- Cross-island migration of algorithms (planned for a future iteration once the basic island architecture is validated).
- Inter-island messaging or debate (would require Claude Code agent teams; not used here).
- Modifying the trading strategy (`strategy_name` is fixed at `ema_cross` per the local evaluator contract).
