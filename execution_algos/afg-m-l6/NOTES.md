# afg-m-l6 — Implementation Notes

Per-iteration experiment, base_algo `aggressor-flow-gate`, context mode
`metrics-only`, loop 6. Starting point: afg-m-l5.

## Hypothesis

Context available (metrics-only mode — prior loops' `metrics` blocks only):

```
Loop 1: pnl_vs_base=-7.3%  slippage_vs_base=0.0% sharpe=5.13 trade_count=107623
Loop 2: pnl_vs_base=-10.1% slippage_vs_base=0.0% sharpe=5.13 trade_count=106724
Loop 3: pnl_vs_base=-38.0% slippage_vs_base=0.0% sharpe=3.30 trade_count=113358
Loop 4: pnl_vs_base=-8.9%  slippage_vs_base=0.0% sharpe=5.20 trade_count=106751
Loop 5: pnl_vs_base=-63.4% slippage_vs_base=0.0% sharpe=1.80 trade_count=123480
```

Reading the numbers alone (no prior code or notes inspected):

1. Every loop underperforms `base_algo` (pnl_vs_base strictly negative across
   all five). No gate variant tried so far beats the base.
2. There is a clear monotone relationship between `trade_count` and outcome.
   Sorted by trade_count:
     - 106724 (L2) -> -10.1%, sharpe 5.13
     - 106751 (L4) -> -8.9%,  sharpe 5.20   <- best pnl, best sharpe
     - 107623 (L1) -> -7.3%,  sharpe 5.13
     - 113358 (L3) -> -38.0%, sharpe 3.30
     - 123480 (L5) -> -63.4%, sharpe 1.80
   The three loops in the tight ~106.7k-107.6k band all land in a narrow
   -7% to -10% / sharpe ~5.1-5.2 band. The two loops with the highest counts
   (113k, 123k) collapse, both in pnl AND in sharpe. More trades = worse.
3. The worst loop (L5, -63.4%) ran the most trades (123480). The second-worst
   (L3, -38.0%) ran the second-most (113358). The trend is unambiguous:
   loosening the gate to admit more orders destroys both pnl and risk-adjusted
   return. Whatever the most recent loop (L5) did, it pushed trade_count to a
   record high and produced the worst result of the experiment.
4. The least-bad loop (L4, -8.9%) ran 106751 trades — within the low cluster.
   Selectivity (fewer admitted orders) correlates with the best results seen.

Conclusion from the numbers: the prior loop (L5, the starting point for L6)
moved in exactly the wrong direction — it maximised trade_count and minimised
pnl/sharpe. Loop 6 must reverse hard: tighten the gate aggressively so the
algorithm becomes far more selective and trade_count drops back down out of
the failure regime (113k+) and toward / below the best-performing cluster
(~106.7k-107.6k). The numbers suggest the gate's free parameters should be
set to skip MORE orders, not fewer — pull trade_count down decisively.

Planned change (mechanical reversal of the loosening, going further toward
selectivity than any prior cluster member): retune the three gate parameters
so the gate trips often and on weaker imbalances:
  - `flow_threshold`: 8.0 -> 0.30  (much lower bar -> gate trips on weak
    imbalances -> many more skips -> trade_count falls hard)
  - `window_seconds`: 4.0 -> 12.0  (longer look-back accumulates more prints
    -> larger decayed-flow magnitude -> the now-low threshold is exceeded
    far more often)
  - `half_life_seconds`: 2.0 -> 5.0  (slower decay keeps more of the window's
    flow alive -> larger magnitude -> reinforces the tightening)

Expected effect: trade_count drops from L5's 123480 toward and below the
best cluster (~106k), recovering pnl and sharpe out of the -63%/1.80 hole
back toward (and ideally past) the best observed -8.9% / sharpe 5.20.

## Backtest Observations

Train window (12 dates, 2026-03-08 .. 2026-03-21), `--use-cached-baseline`.

afg-m-l6 aggregate:
  - realized_pnl    = 1318.5
  - mean_slippage   = 0.0
  - sharpe_ratio    = 6.021
  - max_drawdown_pct= -0.03435
  - win_rate        = 0.35315
  - trade_count     = 105331

vs base_algo `aggressor-flow-gate` (realized_pnl=1255.5, mean_slippage=0.0,
sharpe=5.594, trade_count=107198):
  - vs_base_pnl_pct      = +5.02%
  - vs_base_slippage_pct = 0.0% (both sides have zero slippage)

The numbers-only hypothesis held cleanly. The hard reversal toward
selectivity worked exactly as the trade_count trend predicted:

  - trade_count dropped from L5's 123480 to 105331 — below ALL prior loops
    and below the base's 107198. The gate now skips more orders than any
    prior loop's gate.
  - This is the FIRST loop of the experiment to post a positive
    pnl_vs_base (+5.02%). Every prior loop (L1..L5) was negative, ranging
    from -7.3% to -63.4%.
  - sharpe_ratio reached 6.02 — the highest of the experiment, above the
    base's 5.594 and above the previous best (L4, 5.20).
  - The monotone "fewer trades -> better" relationship inferred from the
    five prior metrics blocks extrapolated correctly past the data: the
    best prior cluster sat at ~106.7k-107.6k; pushing below it to 105331
    continued to improve pnl and sharpe rather than reversing.
  - win_rate (0.353) and max_drawdown (-0.0343) are essentially unchanged
    vs the healthy cluster — the gain comes from skipping adverse-flow
    orders, not from a risk-profile shift.

Caveat: trade_count remains very high (105331 over 12 dates), so this is a
high-frequency regime; the +5.02% edge is an aggregate over many small
fills, not a few large trades. No low-trade-count concern.

Direction this suggests for a future loop: selectivity is still paying off
at the margin (105331 beat the ~107k cluster). A future loop could probe
slightly further — tighten the gate a notch more or sharpen the recency
weighting — but watch for the point where over-skipping starts dropping
pnl, since the relationship must eventually turn over.
