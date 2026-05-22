# ptg-m-l6 — per-iteration experiment (position-tier-gate, metrics-only)

## Hypothesis

Context mode is **metrics-only**: the only inputs are the `metrics` blocks of
loop-1 .. loop-5. No prior NOTES.md, no summaries, no reasoning. The
hypothesis below derives solely from these numbers:

```
Loop 1: pnl_vs_base=+0.0%  slippage_vs_base=0.0%  sharpe=17.62  trade_count=90433
Loop 2: pnl_vs_base=-23.1% slippage_vs_base=0.0%  sharpe=15.81  trade_count=47725
Loop 3: pnl_vs_base=-7.0%  slippage_vs_base=0.0%  sharpe=16.95  trade_count=84541
Loop 4: pnl_vs_base=-96.3% slippage_vs_base=0.0%  sharpe=0.60   trade_count=136734
Loop 5: pnl_vs_base=-96.3% slippage_vs_base=0.0%  sharpe=0.60   trade_count=136734
```

Observations from the numbers alone:

1. **Single-peaked trade_count -> pnl_vs_base relationship.** pnl_vs_base is
   highest at loop 1's trade_count (~90433) and falls off in both
   directions: at 47725 (loop 2) pnl is -23%, at 136734 (loops 4-5) pnl
   collapses to -96%. Loop 3 at 84541 sits just *below* the peak count and
   recovers to -7% — the best non-base loop.
2. **Over-trading is catastrophic.** Loops 4 and 5 are byte-identical
   metrics (136734 trades, sharpe 0.60, -96.3%). Whatever they did, they
   landed in the same over-trading regime and destroyed P&L. Sharpe drops
   an order of magnitude (17.6 -> 0.60).
3. **The peak is between loop 3 (84541) and the over-trading regime.**
   The integer knob that loops 3/5 use jumps the trade count from 84541
   straight past the ~90433 peak into the 136734 regime — there is no
   integer setting that lands on the peak.

**Change for loop 6:** keep the safe loop-3 regime (the gate at its
tightest integer setting, which produced 84541 trades and -7%) but add a
*fractional pass-through* on the would-be-skipped open legs. A deterministic
1-in-K admit rule lets a small, controlled fraction of gated opens execute,
nudging trade_count up from 84541 toward the ~90433 peak without crossing
into the loop-4/5 over-trading collapse. ~90433 / 84541 implies roughly a
+7% lift in admitted opens; a 1-in-16 deterministic admit on the gated
opens is the smallest fractional step that moves the count toward the peak
while staying far from 136734.

Expected: trade_count moves from ~84541 toward ~90000, pnl_vs_base improves
from loop 3's -7.0% toward 0%, sharpe recovers toward ~17.

## Implementation Decisions

Starting point: copied `execution_algos/ptg-m-l5/execution_algorithm.py`
mechanically (metrics-only mode forbids analyzing prior code logic).

Change applied:
- `position_cap` set to 1 (the tightest integer gate — the loop-3 safe
  regime by the trade_count evidence).
- New parameter `admit_every` (default 16): when an open leg would be
  skipped by the positional gate, a deterministic counter admits every
  Kth such gated open instead of skipping it. Counter is mutable state,
  reset in `on_reset()`.
- The fractional admit is purely a count throttle; quantity is never
  modified — orders are submitted intact or skipped entirely.
- Reduce-only orders still always execute (intraday_flat preserved).

No look-ahead: the gate reads `self.cache.positions_open()`, which reflects
only already-processed fills. The admit counter is path-dependent on past
gated opens only.

## Backtest Observations

Train window (12 dates, 2026-03-08 .. 2026-03-20). Run against base
`position-tier-gate` (realized_pnl=4262.5).

| metric            | ptg-m-l6   | base (ptg) | delta            |
|-------------------|------------|------------|------------------|
| realized_pnl      | 3906.25    | 4262.5     | vs_base -8.36%   |
| mean_slippage     | 0.0        | 0.0        | vs_base 0.0%     |
| sharpe_ratio      | 16.587     | 17.619     | -1.03            |
| max_drawdown_pct  | -0.01927   | -0.01727   | slightly worse   |
| win_rate          | 0.3693     | 0.3720     | -0.27 pp         |
| trade_count       | 92461      | 90433      | +2028            |

Outcome vs the metrics-only hypothesis:

- The fractional 1-in-16 admit on gated opens lifted trade_count from
  loop 3's 84541 to **92461** — confirming the knob direction: the
  pass-through does nudge the count up, as predicted.
- However it slightly *overshot* the ~90433 peak (92461 > 90433) and
  pnl_vs_base came in at **-8.36%**, marginally worse than loop 3's
  -7.0%. The single-peaked trade_count -> pnl relationship held: being
  ~2000 trades above the peak cost a little P&L, consistent with the
  loop-2-to-loop-4 falloff pattern.
- sharpe (16.59) stayed in the healthy band — far from the loop-4/5
  collapse (0.60) — so the over-trading regime was avoided. The miss is
  a fine-tuning miss, not a regime error.
- Trade count is high (92461) — no low-sample-size concern.

Read of the numbers for a future loop: the admit fraction was a touch too
generous. ~92461 with admit_every=16 vs the ~90433 peak suggests a larger
divisor (admit_every ~24-32, i.e. fewer gated opens admitted) would land
the count closer to the peak and likely recover pnl_vs_base toward 0%.
Alternatively, since loop 1 (the base config) still holds the best P&L,
the throttle may simply not have a setting that beats it — the base
config's natural trade_count is itself near-optimal.
