# Loop 8 Reasoning Trace

## Hypothesis generation method used
Seed prompt-l0.md: single-pass — read base mechanism, identify ONE plausible
weakness, propose ONE concrete modification, state expected directional
deltas vs `<base_algo>`.

## How the hypothesis emerged from the method
The method asks Step 1 (read base) then Step 2 (one plausible weakness). I
followed it literally. Step 1: `aggressor-flow-gate` keeps a 10s deque of
`(ts_event, signed_volume)` from trade prints (BUYER → +size, SELLER →
−size), prunes by `window_seconds`, sums to `net_flow`, and skips an open
order if `|net_flow| ≥ flow_threshold = 2.0` and the sign is adverse to the
order side. The anti-cascade flag forces the next post-skip order to
submit unconditionally. Step 2: the input is **unclipped**. A single
print of 50–200 contracts (which happens on session opens and macro
events in MES) dominates the 10-second sum and triggers skips on
*subsequent* oracle signals during a window in which the directional
impulse from that single sweep has very likely already been absorbed.
Step 3: clip each individual print's contribution to ±`max_print_size`
contracts before appending to the deque. The skip then requires
broad-based directional pressure (multiple meaningfully-sized same-side
prints) rather than one big sweep. Step 4: predicted directionally
higher P&L vs base, unchanged slippage, higher trade count.

## Where the method helped
The "identify ONE plausible weakness" framing pushed me toward a single
clean mechanism story — the unclipped-input failure mode — rather than
flailing across multiple axes. The "concrete modification" framing
forced me to write a single-line code change (`size if size <
max_print_size else max_print_size`) rather than a broad refactor.
Implementation was minimal and low-risk: identical scaffolding to base
except for the clipping line. The directional prediction in Step 4
(higher trade count, broadly similar Sharpe/max_dd/win_rate) matched
the per-date results qualitatively in the high-volume regimes I
expected to be affected: per-date stdout shows 20260315 +60.24%,
20260316 +31.16%, 20260317 +21.68%, 20260318 +25.04%, 20260320 +98.81%
in pnl vs base — all the high-print-rate sessions. So the *mechanism
story* was right.

## Where the method felt limiting or unnecessary
The method has no calibration step. I picked `max_print_size = 3.0`
between candidate values 2.0 and 5.0 by armchair reasoning written in
NOTES.md ("1.5x threshold with marginal cushion"), with zero empirical
evidence — no DBN inspection of the trade-print size distribution on
train dates, no measurement of the firing rate of the gate at different
`max_print_size` values, no measurement of what fraction of base skips
were single-print-dominated. The L5-targeting critic in loop 5 already
flagged exactly this pattern — uncalibrated quantitative parameters
chosen by intuition — and proposed a sibling-calibration method, but
that proposal was reverted. So in loop 8 we are back at the seed
prompt and the same flaw reproduced. The aggregate result confirms it
hurt: pnl 836.5 vs base 970 on matched 11 dates = **−13.76%** vs base
on the matched window. The mechanism was right and the parameter value
was wrong, and the method gave me no way to tell.

## What a different method might have produced
A calibration-anchored method (the loop-5 reverted proposal, or its
spiritual cousin) would have me load 2 train dates' raw DBN, compute
the empirical print-size distribution for MES, measure what fraction
of base skips were attributable to a single ≥10-lot print, and either
(a) demonstrate the false-positive failure mode is real before
implementing, and choose `max_print_size` to clip exactly the
outlier-print tail (likely the 95th–99th percentile of print sizes,
not 3.0), or (b) discover the failure mode is rarer than assumed and
escalate to a different hypothesis. The hypothesis I shipped is
plausible but the parameter is unprincipled. A calibrated parameter
might have hit a different point on the firing-rate curve and could
plausibly have produced a positive vs-base delta.

## What the backtest showed
Aggregated across the 11 matched dates (20260319 OOM'd, excluded —
same as L5/L6/L7):
- realized_pnl = **836.5** (base on same 11 dates: 970 → **−13.76%**
  vs base)
- sharpe_ratio = **3.896** (cross-day annualized, ddof=1, ×√252)
- max_drawdown_pct = **−3.70%** (worst date: 20260316)
- win_rate = **0.3530** (winners 31,181 / trade_count 88,329)
- trade_count = **88,329** (vs L5 78,442 → +12.6%; predicted higher,
  confirmed)
- mean_slippage = 0.0
- is_weighted_bps = 0.0528

What surprised me: per-date stdout showed strong positive deltas vs
base on the high-volume sessions (+21–+99% on 20260315/16/17/18/20),
which supports the *mechanism story*. But the aggregate goes negative
because the low-volume sessions (e.g. 20260312, 20260313) and middling
sessions either got slightly worse or neutral, and the dollar drag on
the loser dates was larger than the dollar gain on the winner dates
even though the % moves looked impressive. This is exactly the
sample-size-vs-magnitude trap small-P&L percentage deltas hide.

What confirmed expectations: trade count is up — the gate fires less
often, as designed. Win rate is essentially unchanged — the clipping
doesn't change the *quality* of held entries, only their *count*. So
the directional prediction was right on trade_count, mean_slippage,
win_rate and roughly right on max_dd (within ~25% of base −3.32%); it
was wrong on realized_pnl direction (predicted up, came in down).

## Where I felt uncertain
- The choice of `max_print_size = 3.0` vs 2.0 vs 5.0. NOTES.md
  documents the wobble explicitly. No measurement supported the
  choice.
- Whether the failure mode I targeted (single-print false-positive
  skips) was the **dominant** failure mode of base or just *a* failure
  mode. Per-date results suggest false positives in high-volume
  regimes were a real phenomenon and the modification did help in
  those regimes; the magnitude on lower-volume days, however, was
  small or slightly negative, and on aggregate that dragged total
  pnl below base.
- Whether the anti-cascade flag interaction (force-submit next after
  ANY skip) is still well-tuned at the new lower skip rate; with fewer
  skips, the anti-cascade flag fires less often, but I never measured
  whether the *quality* of forced-resubmissions changes.
- Recoverable tool-call errors: the 20260319 partition OOM'd
  consistently across L5/L6/L7/L8 — I excluded it as my predecessors
  did, but I never tested whether a chunked-load approach could
  recover it; the matched 11-date set is now the de-facto comparison
  window for this entire experiment arm.
- Date 20260319 also represents a real data point being silently
  dropped from EVERY comparison in this arm — flagged here for the
  critique phase.
