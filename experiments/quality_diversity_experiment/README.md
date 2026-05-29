# Quality-Diversity Experiment (MAP-Elites illumination search)

Driven by the `quality-diversity-researcher` agent
(`.claude/agents/quality-diversity-researcher.md`). Controlled variables live
in `research/config.yaml → quality_diversity`.

## What this experiment is

Every other experiment in this repo (`per_iteration`, `proposer_criticizer`,
`self_improving_prompt`, `island`, `BFS`) collapses each run to a single scalar
(`vs_base_pnl_pct`) and keeps **one champion**. This one does not.

It runs **MAP-Elites**: a 2-D grid over a *behavior space* of the execution
phenotype, holding the highest-P&L algorithm discovered in **each cell**. Each
loop targets an empty or improvable cell and applies one behavior-targeted
mutation to a parent elite. The output is a *repertoire* (an illumination map)
plus a Pareto surface — never a single winner.

The thesis under test: **does behavioral diversity find higher peaks than
direct P&L-maximization?** Diverse stepping-stones are how MAP-Elites escapes
the local optima that greedy single-champion refinement falls into.

## Behavior space (map axes)

Both descriptors come from the train-aggregated `performance` block, so they
match how `vs_base_pnl_pct` is aggregated — no backtest-engine change needed.

| Axis | Definition | Default bins / range |
|---|---|---|
| selectivity | `algo.trade_count / simple.trade_count`, clamped [0,1] | 5 / [0.0, 1.0] |
| win_rate    | `performance.win_rate`                                 | 5 / [0.30, 0.70] |

**Fitness per cell** = `realized_pnl`. **Secondary objectives** (for the Pareto
front, not cell competition): `max_drawdown_pct`, `sharpe_ratio`, `trade_count`.

`mean_slippage` is excluded as fitness, descriptor, and Pareto axis — the
current fill model reports zero slippage on every backtest (`research/NOTES.md`).

## Layout

```
experiments/quality_diversity_experiment/
  <base_algo>/
    archive.json              # cell_key -> elite entry (the MAP-Elites grid)
    loops/loop-<N>.json       # one record per loop (added | replaced | rejected)
    program_database.json     # lightweight manifest, one row per loop
  reports/<base_algo>-illumination.json   # written by action=report
  .current_loop.json          # machine-local pointer; git-ignored
```

## Running it

```bash
# one loop (repeat to the budget in config, default 24):
#   invoke quality-diversity-researcher  →  base_algo=aggressor-flow-gate
#   ... × budget   (loop 1 seeds the archive; 2+ illuminate it)
# then render the map:
#   invoke quality-diversity-researcher  →  base_algo=aggressor-flow-gate action=report
# repeat for position-tier-gate and vol-regime-sizer.
```

Base algos: `aggressor-flow-gate` (afg), `position-tier-gate` (ptg),
`vol-regime-sizer` (vrs). Train window only; the test window is held out.

## Report metrics

- **coverage** — filled cells / total
- **qd_score** — Σ `max(0, realized_pnl)` over filled cells
- **qd_score_vs_base** — Σ `max(0, realized_pnl − base_pnl)` over filled cells
- **best_cell** — highest-fitness elite
- **axis_marginals** — best fitness at each selectivity / win_rate bin
- **pareto_front** — non-dominated elites over {pnl ↑, max_drawdown_pct ↑, sharpe ↑}
- **insertion_tally** — added / replaced / rejected counts

The head-to-head ("does the QD peak beat per-iteration's best-of-8 at matched
budget?") is an **operator analysis step**, kept outside the agent so its
hypotheses stay isolated (same cross-experiment isolation `pc-researcher` uses).
