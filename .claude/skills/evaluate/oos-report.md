# OOS report shape and `performance_oos` merging

The Lambda report's exact field names are produced by the evaluator and may
drift. Treat the block below as a sketch — read the actual JSON before
relying on specific keys.

```json
{
  "algorithm_name": "<algo-id>",
  "evaluation_date": "2026-04-30T14:45:00Z",
  "backtest_period": { "start": "...", "end": "...", "days_oos": ... },
  "execution_metrics": {
    "slippage_bps":             ...,
    "execution_time_ms":        ...,
    "fill_accuracy_pct":        ...,
    "latency_ms":               ...,
    "cost_bps":                 ...,
    "orders_per_second":        ...,
    "execution_time_variance_ms": ...,
    "peak_latency_ms":          ...
  },
  "performance_summary": {
    "total_trades":         ...,
    "successful_fills":     ...,
    "failed_fills":         ...,
    "avg_profit_per_trade": ...,
    "total_pnl":            ...
  },
  "status": "completed",
  "errors": []
}
```

## Format note

The Lambda envelope above (`execution_metrics` / `performance_summary`)
does not share field names with the local `compute_metrics()` output
(see the `backtest` skill metrics-schema.md) used for the `performance`
block. When you populate `performance_oos`, translate what's available:

| `performance` field (local) | Source in Lambda report |
|---|---|
| `realized_pnl`, `total_pnl` | `performance_summary.total_pnl` |
| `trade_count` | `performance_summary.total_trades` |
| `total_commissions` | derive from `execution_metrics.cost_bps × starting_balance / 10000` |
| `mean_slippage` (price units) | not directly available — record `execution_metrics.slippage_bps` separately |
| `sharpe_ratio`, `max_drawdown_pct`, `win_rate` | not present in Lambda report — leave as `null` in `performance_oos` |

Record raw values from the Lambda report. If a field is unavailable in
the OOS report, write `null` rather than estimating — the honesty rules
in `OBJECTIVE.md §8` require an honest gap, not a fabricated number.
