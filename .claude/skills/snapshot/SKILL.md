---
name: snapshot
description: Save a passing execution algorithm to S3 by pushing a snapshots/<algo-id> branch, which triggers the GitHub Actions upload and the Lambda OOS evaluator.
when_to_use: Use only when status is PASS — the algorithm beats the baseline by the configured pass_gate margins on the train window without slippage regression. Do not snapshot CLOSE or FAIL outcomes.
user-invocable: false
allowed-tools: Bash Read Write Edit
---

# Algorithm Snapshot

How a research agent saves a passing execution algorithm to S3.

## 1. When to snapshot

Only when the algorithm's `status` is **PASS** — i.e., realized P&L beats
the baseline (`config.yaml → pass_gate.baseline`) by the required margin
without regressing slippage. Do not snapshot CLOSE or FAIL outcomes.

For refinement variants, snapshot only the variant that beat the parent
algorithm by the targets in `config.yaml → refinement.targets` (see
`OBJECTIVE.md §6`).

## 2. Required directory shape

```
execution_algos/<algo-id>/
├── __init__.py                                 # re-exports get_execution_algorithm
├── execution_algorithm.py                       # ExecAlgorithm subclass + factory
├── NOTES.md                                     # agent reasoning (OBJECTIVE.md §10)
├── requirements.txt                             # optional, if non-default deps
└── results/
    ├── backtest-results.json                    # canonical aggregate — see §3
    ├── metadata.json                            # consolidated reproduction record (runs[])
    └── <YYYYMMDD>-<short-sha>/                  # per-run dirs (one per trading date, auto-created by run_backtest())
        ├── metrics.json                          # committed: per-date metrics
        └── account.csv, orders.csv, fills.csv, positions.csv  # gitignored
```

Committed: `backtest-results.json`, `metadata.json`, and each
`<run>/metrics.json`.

`<algo-id>` is kebab-case and must match the directory name everywhere
the algorithm is referenced (program database, snapshot branch, S3 key).

The algorithm must also be registered in `execution_algos/__init__.py →
_EXEC_ALGORITHM_FACTORIES` for `run_backtest()` to find it.

## 3. `results/backtest-results.json` schema

This file is the canonical summary the agent writes at snapshot time. It
aggregates the per-date `metrics.json` files (in the run subdirs) into one
record and adds the baseline comparison.

```json
{
  "algo_name": "twap-volatility-aware",
  "backtest_date": "2026-04-29T14:32:00Z",
  "baseline": "simple",
  "strategy_used": "<value of cfg['strategy']['name']>",
  "symbol": "MESM6",
  "performance": {
    "realized_pnl":             3200.50,
    "unrealized_pnl":       0.0,
    "sharpe_ratio":              1.42,
    "max_drawdown_pct":         -6.2,
    "win_rate":                  0.58,
    "trade_count":               134,
    "mean_slippage":             0.0012,
    "max_abs_slippage":          0.05,
    "total_commissions":         87.40,
    "total_return_pct":          15.3,
    "is_weighted_bps":           0.85,
    "is_total_price":            42.10,
    "vs_baseline_pnl_pct":       14.2,
    "vs_baseline_slippage_pct": -3.1,
    "vs_baseline_is_bps":       -12.4
  },
  "performance_oos": null,
  "period": {
    "train_dates": ["2026-03-08", "..."],
    "test_dates":  []
  },
  "run_dirs": [
    "results/20260308-abc1234/",
    "results/20260310-abc1234/"
  ]
}
```

The `performance` block and `period.train_dates` are populated **at
snapshot time** from local `metrics.json` files. The `performance_oos`
block and `period.test_dates` are populated **post-snapshot**, in a
follow-up invocation, after the Lambda evaluator has produced the OOS
report (see the `evaluate` skill). Initialize `performance_oos` to
`null` and `test_dates` to `[]` at snapshot time; merging them is a
later commit. Do not run `run_backtest()` on test dates locally to
populate them — that is data leakage (see the `analysis` skill).

Notes on individual fields:

- `sharpe_ratio` is a **daily Sharpe** — per-minute returns scaled by
  `sqrt(390)` (RTH minutes per day), so one trading day produces one
  interpretable risk-adjusted number. Mean across train dates.
- `is_weighted_bps` is the **canonical execution-algo objective**:
  qty-weighted mean implementation shortfall against arrival mid, in
  basis points. Sign: positive = adverse for the trader.
- `is_total_price` is the dollar-denominated total shortfall (sum across
  orders/dates), complementing `is_weighted_bps`'s per-order view.
- `unrealized_pnl` is a mark-to-mid valuation of positions still open
  at session end (no synthetic fill, no slippage assumed). For an
  intraday-flat strategy this should be `0.0`; a non-zero value means the
  `execution_constraints.intraday_flat: true` contract was violated and
  must be flagged in NOTES.md.
- The headline "honest day's P&L" is `realized_pnl + unrealized_pnl`.
  This sum drives `total_return_pct` and `vs_baseline_pnl_pct` — it is
  **not** stored as its own field; consumers derive it inline.

Aggregation rules (apply to your algorithm AND the baseline, then compute
the `vs_baseline_*` deltas):

- `realized_pnl`, `unrealized_pnl`, `total_commissions`, `trade_count`,
  `winners`, `losers`, `order_count`, `fill_count`, `is_total_price` —
  **sum** across run dirs
- `sharpe_ratio` — **mean** of per-date daily Sharpe
- `max_drawdown_pct` — **min** (most negative) across run dirs
- `win_rate` — `winners / trade_count` from the summed counts
- `mean_slippage`, `max_abs_slippage` — **trade-count-weighted mean** /
  **max** across run dirs
- `is_weighted_bps` — **captured-order-count-weighted mean** across run
  dirs (skip dates where IS is null because no quotes were available)
- `total_return_pct` — recompute from
  `(summed_realized + summed_unrealized) / starting_balance` (no
  compounding across separate runs)
- `vs_baseline_pnl_pct` — derived from `realized + unrealized` totals
  on both sides (not from `realized_pnl` alone)

Report raw numbers — see `OBJECTIVE.md §8` honesty rules.

## 4. Snapshot procedure (automatic, recommended)

By the time you reach this skill, the iteration commit has already been
made on the `iter/<algo-id>-<timestamp>` branch (researcher agent §5
step 8). The snapshot is a re-pointed branch off that commit.

```bash
# Fork the snapshot branch from the current (iter) branch — the algorithm
# code and program DB append are already committed here.
git checkout -b snapshots/<algo-id>

# Push — GitHub Actions auto-uploads to S3 on snapshots/* branches
git push origin snapshots/<algo-id>
```

The existence of `refs/heads/snapshots/<algo-id>` on origin is the durable
"snapshot pushed" signal; the program-database entry's `status: pass` plus
that ref together answer "did we snapshot?" Leave `oos_retrieved_at` as
`null` in the appended program-database entry — the `evaluate` skill sets
it in a follow-up invocation, treating it exactly like the SubagentStop
`meta` backfill (single-field edit on an already-appended entry).

If you arrive at this skill on a branch where the iteration commit has
*not* yet been made (e.g., manual snapshotting), stage and commit first:

```bash
git checkout -b snapshots/<algo-id>
git add execution_algos/<algo-id>/ research/program_database.json
git commit -m "<algo-id>: pnl=+X.X% vs baseline, sharpe=X.XX"
git push origin snapshots/<algo-id>
```

The workflow at `.github/workflows/snapshot-execution-algo.yml` packages the
directory (code, results/, NOTES.md, generated metadata) and uploads to:

```
s3://<bucket>/execution_algos/<algo-id>/<timestamp>-<commit>/
```

This same upload triggers the `execution-algorithm-evaluator` Lambda, which
runs the algorithm against the test window in `config.yaml → data_window.test`
and writes a report to `s3://<bucket>/evaluation-reports/<algo-id>/`. See
the `evaluate` skill for retrieving and interpreting that report.

## 5. Manual snapshot (fallback)

If the branch push fails or the workflow is disabled:

1. Go to **GitHub → Actions → "Create Execution Algorithm Snapshot"**
2. Click **Run workflow**
3. Inputs: `algo_name = <algo-id>`, `algo_path = execution_algos/<algo-id>`

## 6. Verify upload

```bash
aws s3 ls "s3://$S3_BUCKET_NAME/execution_algos/<algo-id>/" --recursive
```

Look for a `<timestamp>-<commit>/metadata.json` entry. If missing, check the
GitHub Actions run logs.

## 7. Retention

S3 lifecycle policy auto-deletes snapshots after 30 days. The git history of
`snapshots/*` branches and `execution_algos/<id>/` is the durable record.

## 8. Known limitation

The current workflow's copy step (`find … -exec cp {} "$ROOT/results/"`)
flattens the results tree, so files with the same name across run subdirs
overwrite each other in the snapshot — only the alphabetically-last run's
CSVs survive. The top-level `results/backtest-results.json` is what the
snapshot reliably captures, which is why §3 requires it.
