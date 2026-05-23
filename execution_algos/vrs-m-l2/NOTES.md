# vrs-m-l2

Loop 2 of the per-iteration experiment for `vol-regime-sizer` under `metrics-only` context mode.

## Context (metrics-only)

Prior loop metrics (only allowed input under this mode):

```
Loop 1: pnl_vs_base=+24.2% slippage_vs_base=0.0% sharpe=3.91 trade_count=125873
```

Base (`vol-regime-sizer`) reference: pnl=753.75, sharpe=3.06, trade_count=127991, slippage=0.0.

## Hypothesis

Looking strictly at the numbers:

- Loop 1 improved PnL by +24% over the base and improved Sharpe (3.91 vs 3.06) while reducing trade count slightly (125873 vs 127991, ~-1.7%).
- Slippage is 0.0 on both base and loop 1 — top-of-book-only execution apparently always fills at quote, so slippage is not a useful optimization axis here.
- Sharpe improved more than PnL did proportionally, which is consistent with loop 1 cutting down on noisier trades (lower variance per trade). The remaining headroom is likely in continuing that direction: further selectivity reduces low-edge trades and lifts both PnL/trade and Sharpe.

Proposed change for loop 2: tighten the volatility-regime gating one notch more (a more conservative regime threshold and/or smaller sizing in the lowest-edge regime), pushing trade count slightly lower again with the expectation that risk-adjusted PnL continues climbing. If trade_count falls disproportionately while PnL stays flat or rises, we have evidence the selectivity direction is the right one to keep pushing in loop 3.

This is a mechanical extension of the direction loop 1 already showed worked. I have not read loop 1's code or notes; the change is implemented by mechanically copying vrs-m-l1's code and adjusting whichever numeric thresholds it exposes to be one step stricter.

## Backtest Observations

Train window (2026-03-08 through 2026-03-20), 12 dates, oracle strategy on MESM6.

| Metric                | vrs-m-l2  | vol-regime-sizer (base) | vrs-m-l1 |
|-----------------------|-----------|-------------------------|----------|
| realized_pnl          | 1068.25   | 753.75                  | 936.50   |
| sharpe_ratio          | 4.4346    | 3.0647                  | 3.9099   |
| max_drawdown_pct      | -0.0406   | -0.0460                 | -0.0421  |
| win_rate              | 0.3543    | 0.3529                  | 0.3542   |
| trade_count           | 124497    | 127991                  | 125873   |
| mean_slippage         | 0.0000    | 0.0000                  | 0.0000   |

vs base (vol-regime-sizer): pnl +41.72%, slippage 0.0% (both 0), sharpe delta +1.37.
vs loop 1 (vrs-m-l1): pnl +14.07%, sharpe +0.52, trade_count -1.09%.

The metrics-only hypothesis held up: tightening the volatility gating one notch further pushed trade count down a bit more and lifted Sharpe / PnL further, slightly outperforming loop 1 on every headline number. The selectivity direction is still productive at this step; whether a third tightening step keeps paying off or starts cutting into profitable trades is the natural question for the next loop.
