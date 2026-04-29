# Skill: Algorithm Snapshot

How a research agent saves a passing execution algorithm to S3.

## 1. When to snapshot

Only when the algorithm's `status` is **PASS** (§5 step 7) — i.e., realized
P&L beats the baseline (`config.yaml → pass_gate.baseline`) by the required
margin without regressing slippage. Do not snapshot CLOSE or FAIL outcomes.

For refinement variants, snapshot only the variant that BEAT the parent
baseline by the targets in `config.yaml → refinement.targets` (§6 step R5).

## 2. Required directory shape

```
execution_algos/<algo-id>/
├── __init__.py                                 # re-exports get_execution_algorithm
├── execution_algorithm.py                       # ExecAlgorithm subclass + factory
├── NOTES.md                                     # agent reasoning (OBJECTIVE.md §10)
├── requirements.txt                             # optional, if non-default deps
└── results/
    ├── backtest-results.json                    # canonical summary — see §3 below
    └── <YYYY-MM-DDTHH-MM-SSZ>-<short-sha>/      # per-run dirs (auto-created by run_backtest())
        ├── metadata.json
        ├── metrics.json
        ├── account.csv, orders.csv, fills.csv, positions.csv
```

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
  "strategy_used": "oracle",
  "symbol": "MESM6",
  "performance": {
    "realized_pnl":            3200.50,
    "sharpe_ratio":            1.42,
    "max_drawdown_pct":       -6.2,
    "win_rate":                0.58,
    "trade_count":             134,
    "mean_slippage":           0.0012,
    "max_abs_slippage":        0.05,
    "total_commissions":       87.40,
    "total_return_pct":        15.3,
    "vs_baseline_pnl_pct":     14.2,
    "vs_baseline_slippage_pct": -3.1
  },
  "period": {
    "train_dates": ["2026-03-08", "..."],
    "test_dates":  ["2026-03-26", "..."]
  },
  "run_dirs": [
    "results/2026-04-29T14-12-00Z-abc1234/",
    "results/2026-04-29T14-15-30Z-abc1234/"
  ]
}
```

Aggregation rules (apply to your algorithm AND the baseline, then compute
the `vs_baseline_*` deltas):

- `realized_pnl`, `total_commissions`, `trade_count`, `winners`, `losers`,
  `order_count`, `fill_count` — **sum** across run dirs
- `sharpe_ratio` — **mean** of per-date Sharpe (or recompute from a stitched
  equity curve if you want to be more rigorous; flag the choice in NOTES.md)
- `max_drawdown_pct` — **min** (most negative) across run dirs
- `win_rate` — `winners / trade_count` from the summed counts
- `mean_slippage`, `max_abs_slippage` — **trade-count-weighted mean** /
  **max** across run dirs
- `total_return_pct` — recompute from summed `realized_pnl` and a single
  `starting_balance` (no compounding across separate runs)

Report raw numbers — see `OBJECTIVE.md §8` honesty rules.

## 4. Snapshot procedure (automatic, recommended)

```bash
# Branch
git checkout -b snapshots/<algo-id>

# Stage everything for the algorithm + the program DB append
git add execution_algos/<algo-id>/ research/program_database.json

# Commit message: "<algo-id>: pnl=+X.X% vs baseline, sharpe=X.XX"
git commit -m "twap-volatility-aware: pnl=+14.2% vs simple, sharpe=1.42"

# Push — GitHub Actions auto-uploads to S3 on snapshots/* branches
git push origin snapshots/<algo-id>
```

The workflow at `.github/workflows/snapshot-execution-algo.yml` packages the
directory (code, results/, NOTES.md, generated metadata) and uploads to:

```
s3://<bucket>/execution_algos/<algo-id>/<timestamp>-<commit>/
```

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
