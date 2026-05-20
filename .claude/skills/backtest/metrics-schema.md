# `metrics.json` schema

Produced by `compute_metrics()` in `backtest_engine/results.py:153`.

| Field | Meaning |
|---|---|
| `starting_balance` | USD seed |
| `final_equity` | end-of-run equity |
| `total_return_pct` | `(final_equity − starting) / starting × 100` |
| `realized_pnl` | sum of position realized P&L |
| `max_drawdown_pct` | `min((equity − peak) / peak) × 100` |
| `sharpe_ratio_intraday` | rescaled intraday Sharpe from 1-min equity returns (consistent across runs; absolute value imprecise — see code comment) |
| `trade_count`, `winners`, `losers`, `win_rate` | trade-count breakdown |
| `long_count`, `short_count` | side breakdown |
| `order_count`, `fill_count` | order/fill counts |
| `total_commissions` | sum across orders (account currency) |
| `mean_slippage`, `max_abs_slippage` | execution-quality proxy (price units; multiply by contract multiplier for $) |
