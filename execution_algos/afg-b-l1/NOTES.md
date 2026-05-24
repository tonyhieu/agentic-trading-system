# afg-b-l1 — aggressor-flow-gate with volume-normalized adaptive threshold

Brief-summary arm, loop 1. Prior-loop context is empty (no prior brief-summary
afg loops). Hypothesis derives from inspecting the base algo.

## Hypothesis

The base `aggressor-flow-gate` gates OPEN orders on `|net_flow| >=
flow_threshold` over a 10-second rolling window, with `flow_threshold = 2.0`
contracts. A single absolute threshold means the gate has a fundamentally
different sensitivity in quiet vs busy regimes:

  * In quiet windows (a few contracts total), 2 net contracts represents a
    near-fully one-sided trade flow — strong directional info. The gate
    correctly fires here.
  * Also in quiet windows, 2 net contracts of imbalance arising from one or
    two random crosses is statistically weak signal — the gate fires when
    it probably shouldn't.
  * In busy windows (hundreds of contracts), 2 net contracts is statistical
    noise — the gate fires on essentially random fluctuations of an
    otherwise-balanced flow, skipping orders that have no real adverse
    selection.

The standard fix in microstructure work is to normalize signed flow by
total absolute flow over the same window. The resulting imbalance ratio
`r = net_flow / abs_vol_window` is unit-free and scale-invariant: a 35%
imbalance means the same thing whether the window contains 5 or 500
contracts. Replacing the absolute-threshold gate with a ratio gate should:

  1. Reduce false-positive skips in busy windows (where 2 contracts is
     noise), recovering participation on orders that have no real adverse
     pressure.
  2. Increase the precision of skips in quiet windows (where the same
     2 contracts now correctly registers as a high-imbalance event).

Expected direction: similar or slightly higher trade count vs base, with
similar or improved pnl, because skip selectivity is better-calibrated to
local information content.

## Implementation Decisions

  * Window kept at 10 s (same as base) — the goal is to isolate the
    threshold-form change, not to retune the window.
  * Default `ratio_threshold = 0.35`. This is a "moderately one-sided"
    cutoff in standard trade-flow imbalance work: 35% net imbalance means
    the dominant side accounts for ~67% of one-sided volume in the
    window. Not so loose that it fires on everything; not so tight that
    only fully one-sided windows trigger.
  * `min_abs_baseline = 2.0` contracts floors the denominator. Without
    it, a window with a single 1-contract trade would produce
    `r = ±1.0`, forcing a gate on essentially no information. The floor
    matches the base's prior absolute threshold so that in the
    very-quiet limit the gate behaves similarly to the base.
  * Anti-cascade semantics (`_position_flat = True` after any skip,
    forcing the next OPEN through unconditionally) preserved exactly
    from base. Reduce-only orders always submit (intraday_flat).
  * Quantity invariant strictly preserved — orders are skipped or
    submitted unmodified.

## Backtest Observations

Train aggregate over 11 apples-to-apples dates (Sun-Fri 2026-03-08..2026-03-20,
with 20260319 OOM-killed during DBN decode and dropped from both sides by the
runner — same handling as ptg-b-l1 / vrs-b-l1):

  * Vs `simple` baseline gate: PASS.
    afg-b-l1 $453.50 / 101,241 trades vs simple $43.25 / 111,489 trades;
    `vs_baseline_pnl_pct = +948.55%` (well above the +5.0% PASS gate).
    Sharpe 2.091 vs simple 0.17 over the same window.
    Slippage 0.0 / 0.0 (zero fill-cost model; no regression).
    Max DD -4.41%. Win rate 35.13%.
    `is_weighted_bps = 0.0531` vs simple 0.673; delta_is_bps = +24.42 in
    afg-b-l1's favor (better arrival-mid capture per traded contract).

  * Vs `aggressor-flow-gate` base on the same 11 dates: WORSE.
    Base afg over these 11 dates: $970.00 / 87,760 trades.
    afg-b-l1: $453.50 / 101,241 trades.
    `vs_base_pnl_pct = -53.25%`, `trade_count delta = +15.4%` (+13,481
    extra trades). Per-date pnl is worse on 10 of 11 dates (only 20260308
    is marginally better, +$7); the largest single-date drags are 20260320
    (-$118.25) and 20260316 (-$108.75).

Drivers:
  * The volume-normalized ratio gate (`r = net_flow / max(abs_vol_window,
    min_abs_baseline)`, threshold 0.35, baseline 2.0 contracts) admits
    substantially more orders than the base's absolute `|net_flow| >= 2.0`
    gate in noisy/busy windows: when abs_vol_window is large, the absolute
    gate fires easily (any 2-contract imbalance counts) but the ratio gate
    requires 35% imbalance, which is rare in balanced busy regimes.
    Conversely in quiet windows the floor (min_abs_baseline=2.0) makes the
    ratio gate behave similarly to the base. Net effect: the algorithm
    fires for MORE orders in busy windows than the base does, not fewer.
    Inspection of the per-date trade counts confirms this: afg-b-l1
    consistently runs +1k to +2k trades per date vs base.
  * Those extra admitted orders are the ones the base correctly gated out:
    busy-window orders with weak directional flow but enough absolute
    imbalance to clear the absolute threshold and (separately) enough
    ratio to clear 0.35. They drag pnl by ~$47 per 1k extra trades.
  * Slippage is identical (0.0 model on both sides) so the gate change
    only shows up in pnl.

Hypothesis verdict: CONTRADICTED. The ratio gate did not improve
false-positive skip selectivity; it materially RELAXED the gate in busy
regimes (where the base correctly skips on weak ratios despite large
absolute imbalance) and the extra admitted orders are systematically
money-losing on this oracle. The base's absolute threshold is, in
practice, encoding a "minimum information content per skip decision"
floor that the ratio reformulation removes. PASS vs `simple` is preserved
only because afg-b-l1 still inherits the base's anti-cascade and
reduce-only-always-submit semantics — both of which dominate the
vs-simple delta. The refinement vs the actual base is negative.

Single highest-leverage next-loop change: replace the pure-ratio gate with
a COMBINED gate — require BOTH (a) `|net_flow| >= 2.0` (the base's
absolute floor) AND (b) `|r| >= 0.35` (ratio confirmation). This keeps the
base's busy-window selectivity (absolute floor handles "is there enough
flow at all?") while adding the ratio test as a quiet-window denoising
filter. Expected: trade_count slightly below base (extra skips on quiet
windows where 2 contracts happens to be balanced), pnl >= base.

