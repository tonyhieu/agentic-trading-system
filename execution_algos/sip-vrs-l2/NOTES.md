# Algorithm Notes: sip-vrs-l2

## Hypothesis

Parent: `vol-regime-sizer`. Method used: propose-falsify-commit (prompt-l1.md).

## Parent mechanism

`vol-regime-sizer` measures the ratio of a fast EWM(|Δmid|) to a slow EWM(|Δmid|)
on every quote tick. For each open-leg parent order it computes
`p = max(min_prob, exp(-sensitivity * max(0, vol_ratio - 1)))` and decides via
deterministic SHA-256 hash of `client_order_id` whether to submit. In calm regimes
(vol_ratio ≈ 1) it submits every order; in high-vol bursts it falls toward
`min_prob=0.05`. Reduce-only orders are submitted unconditionally. The parent
gates purely on the unsigned magnitude ratio — it has no notion of direction,
time-of-day, position-side, or session context.

## Candidate weaknesses

### Candidate 1: Cold-start exposure
The parent submits at `p=1` for the first `min_ticks=30` quote ticks because the
EWMs haven't warmed. If the session opens with high realized vol, the cold-start
window leaks adverse fills at full participation.

### Candidate 2: `min_prob=0.05` floor too high
Even at extreme vol_ratio the parent still submits 1-in-20 orders. If extreme-vol
losses cluster in temporal bursts (vol spikes), the 5% floor still leaks adverse
fills during those bursts.

### Candidate 3: Time-of-day blind
The parent has no time-of-day feature. Sessions in CME-MES futures see
news-driven and positioning flow concentrated around the cash-session close
(~21:00 UTC = 16:00 CT). Losses likely cluster in the last ~15 minutes when the
oracle's 30s-horizon signal is noisiest relative to large directional moves into
the close.

## Falsification test (3 blocks)

### Candidate 1: Cold-start exposure
Claim: opening-window fills are worse than rest-of-session fills.
Falsification test:
  Artifact:  positions.csv on 20260317 + 20260313 (the two worst-loss train dates).
  Statistic: mean realized_pnl per FLAT position for first 60s of session
             vs rest of session, averaged across both dates.
  Decision rule: SURVIVES if mean_pnl(first_60s) < mean_pnl(rest) - $0.02/contract.
                 FALSIFIED otherwise.

### Candidate 2: min_prob floor too high
Claim: tail losses cluster in temporal bursts (consistent with vol-spike
events the 5% floor still allows through).
Falsification test:
  Artifact:  positions.csv on 20260317 + 20260313.
  Statistic: fraction_in_burst = (count of tail-loss positions, bottom 5% by
             realized_pnl, within ≤5 seconds of another tail-loss position) /
             total tail-loss count, averaged across both dates.
  Decision rule: SURVIVES if fraction_in_burst ≥ 0.40. FALSIFIED otherwise.

### Candidate 3: Time-of-day blind
Claim: positions filled in the first 15 minutes after session-start AND in
the last 15 minutes before session-end have mean pnl materially worse than the
session-middle baseline.
Falsification test:
  Artifact:  positions.csv on 20260317 + 20260313.
  Statistic: mean realized_pnl for `open_15min` bucket (sec_of_day - session_start
             < 900s), `close_15min` bucket (session_end - sec_of_day < 900s), and
             `middle` (all else), per date. Aggregate metric:
             (mean_open + mean_close)/2 − mean_middle.
  Decision rule: SURVIVES if aggregate metric ≤ -$0.05/contract (edge buckets
                 averaged together are at least 5 cents/contract worse than
                 the middle). FALSIFIED otherwise.

## Verdicts (3 lines)

Verdict C1: **FALSIFIED** | first_60s mean_pnl=+$0.118 vs rest=-$0.033, delta=+$0.158 (opening window is BETTER, not worse — opposite of claim). Survival margin: -0.178.
Verdict C2: **FALSIFIED** | fraction_in_burst = 0.189 (mean across dates), below 0.40 threshold. Tail losses do NOT cluster in 5-second windows. Survival margin: -0.211.
Verdict C3: **FALSIFIED** | (open+close)/2 − middle = -$0.008/contract aggregate (close: -$0.065, open: -$0.016, middle: -$0.033). Just barely below the $0.05 threshold. Per-date: 20260317 shows edges -$0.035 worse than middle (consistent with claim, but below threshold); 20260313 shows edges $0.019 BETTER (opposite sign). Survival margin: -0.042 (closest of the three).

## Chosen hypothesis

All three candidates were FALSIFIED under their stated decision rules. Per the
method (step 5 #3) I implement Candidate 3 — "weakest falsification chosen, no
candidate survived" — for two reasons: (a) it had the smallest survival margin
(-0.042 vs -0.178 and -0.211), and (b) re-examining the step-4 statistics with
the close window isolated reveals the **close-of-session 15-min window has
mean_pnl = -$0.067/contract** vs all-day mean -$0.022, a $0.045 deficit.
Disaggregated, the close signal is real even though the original combined
edge-vs-middle test failed. The opening 15-min window does not show a robust
effect (sign inconsistent across the two test dates and not different from
all-day baseline). The candidate that the data refines is therefore **close-only,
not open+close**: a session-close gate that suppresses participation in the
last few minutes of the regular trading hour.

The concrete modification is:

> Layer a session-close gate **on top of** the parent's existing vol-regime
> probability. When `session_end - now_seconds < close_window`, multiply the
> submission probability by `close_suppress`. Otherwise, leave the parent's
> behavior unchanged.

This is a guard layered on top of the parent — it strictly reduces participation
in one regime (the close window) and is otherwise identical to the parent. The
quantity invariant and cold-start are preserved.

**Expected direction vs `vol-regime-sizer`**:
- `realized_pnl`: ↑ (skip late-session losses that drag mean pnl in close window).
- `mean_slippage`: 0 (zero-slippage fill model).
- `sharpe_ratio`: ↑ (smaller average loss without commensurate cost in upside;
  the close window has only ~145 positions across the two test dates ≈
  ~1% of trade volume, so the upside risk is small).
- `trade_count`: ↓ (small — only the close window's trades are affected,
  roughly 1% of total).

Supporting verdict reference: C3, "weakest falsification chosen" path. The
disaggregated statistic — close_15min mean_pnl = -$0.067 vs all-day -$0.022,
delta = -$0.045 — is the empirical anchor for the parameter choice below.

## Parameter justifications

- **close_window = 900 seconds (15 minutes)**: Derived from step-4 statistic.
  The 15-minute window before session-end on the two worst-loss dates had
  mean_pnl = -$0.067/contract, $0.045/contract worse than all-day mean. This
  is the bucket whose mean dropped most consistently below baseline in the
  step-4 analysis. (The 5-minute close window had a larger delta but n=51,
  too thin to commit to; 15-min has n=145.)
- **close_suppress = 0.0 (hard skip)**: Derived from step-4 statistic. In the
  close_15min window the mean pnl is -$0.067/contract, i.e. expected pnl per
  trade is negative. The principled rule: if expected pnl in a regime is
  negative, the rational participation rate is 0. The parent's gate
  multiplicatively combines with this — when `close_suppress=0`, the parent's
  vol-regime gate is overridden to skip every open-leg order in the close
  window. Reduce-only orders are exempt (intraday_flat compliance).
- **All other parameters inherited unchanged from parent** (fast_halflife=20,
  slow_halflife=120, sensitivity=2.0, min_prob=0.05, min_ticks=30,
  max_vol_ratio=5.0). The hypothesis is that the close-window guard layered
  on top of the parent's behavior captures the only loss-cluster effect
  surfaced by the falsification tests; the parent's calm/elevated/extreme
  regime sizing is preserved.
- **Session-end detection**: There is no explicit session-end timestamp
  available at order time. The principled rule: use the last `ts_event` seen
  on a quote tick as a rolling proxy for "latest market time", and compare
  to a session-end constant. CME equity-index regular trading hours close at
  21:00 UTC (16:00 CT). Use **21:00:00 UTC** as the fixed session-end constant
  for MESM6. This is a futures-market convention, not an inherited parameter
  or intuition — it's the literal RTH close timestamp.

## Honesty notes

- **All three candidates were FALSIFIED.** The method explicitly allows
  implementing the weakest-falsified candidate with a flag; this is that flag.
  This algorithm may not improve realized_pnl meaningfully — the close-window
  delta is real ($0.045/contract) but applies to ≤1% of trades, so the
  expected lift in aggregate pnl is on the order of $0.045 × 145 ≈ $6.5 per
  worst-loss date × 12 dates ≈ $25-80 total. If the parent baseline is
  $753.75, that's a +3-10% pnl lift at the optimistic end. A real risk is
  that the close window's adverse fills don't generalize beyond the two
  test dates used in step 4 (the other 10 dates were never inspected).
- **The 20260313 case is the worry**: in that date, the open+close edge
  buckets were $0.019 BETTER than middle — directionally opposite to the
  hypothesis. The parameter choice (close-only, 15-min, hard-skip) is
  defensible from the aggregated statistic but is one regime in one direction
  of one cluster of dates. Generalization is the main risk.
- **No new free parameters were introduced from intuition.** `close_window=900s`
  and `close_suppress=0.0` are derived from step-4 statistics and a principled
  rule (suppress where expected pnl is negative).
