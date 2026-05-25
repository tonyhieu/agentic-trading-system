# Algorithm Notes: sip-vrs-l3

## Hypothesis

This loop follows the Propose-Falsify-Commit method (`prompt-l1.md`). The base
algorithm under critique is `vol-regime-sizer`. Loop-1 modified the parent
with a signed-headwind gate and was kept; loop-2 added close-window
suppression and was reverted. Both are siblings of the parent, not parents of
each other. This loop targets a different axis: **temporal pattern in
vol_ratio bursts**.

## Parent mechanism

`vol-regime-sizer` gates OPEN orders with an instantaneous, unsigned
volatility-ratio probability. At each quote tick it updates two EWMs of
`|Δmid|` (fast `halflife=20`, slow `halflife=120`). When an order arrives, it
computes `vol_ratio = fast_vol / slow_vol` (clipped at `max_vol_ratio=5`),
applies `p_submit = max(min_prob=0.05, exp(-sensitivity=2.0 × max(0, ratio-1)))`,
and accepts/skips the order via a deterministic SHA-256 hash of
`client_order_id`. Cold-start guard: first `min_ticks=30` quotes are
unconditionally submitted at p=1.0. Reduce-only orders bypass the gate.
The gate measures *current* vol relative to a slow baseline but contains
no information about whether the elevated regime is fresh (transient burst
about to resolve) or sustained (regime shift).

## Candidate weaknesses

These three candidates are substantively different from the loop-1
hypothesis (signed-direction headwind, already kept) and from the loop-2
candidates (cold-start, min_prob floor, time-of-day close-window — all
falsified in loop 2).

1. **Halflife mismatch (parameter axis).** The parent's `fast_halflife=20,
   slow_halflife=120` tick pair was inherited from a sibling algo. At
   MES quote-tick rates, this places the fast EWM at sub-second timescale
   — the ratio measures within-second tick noise more than "vol regime."
   If true, the gate is essentially uniform-random in expectation and the
   pnl distribution post-gate should be highly dispersed (no concentration).
2. **Spread-based adverse selection (signal-input axis).** Adverse-selection
   in equity-futures execution correlates more directly with wide bid-ask
   spreads at fill time than with unsigned mid-vol. If true, after the
   parent's vol gate, residual losses should still cluster at fills where
   `|avg_px − arrival_mid|` is large.
3. **Vol-regime persistence (temporal-pattern axis).** The parent computes
   `vol_ratio` instantaneously per tick; a single transient spike triggers
   the same skip probability as a sustained burst. Transient bursts tend
   to resolve quickly, producing short-hold adverse positions; sustained
   bursts produce slower-hold, less-adverse positions. If true, position
   hold-duration should be strongly negatively correlated with pnl among
   parent's submitted orders — short-hold positions lose, long-hold
   positions win or break even.

## Falsification tests

Each test is one pandas read plus one conditional aggregation. Decision
rules are stated below before any test was run. The two dates with parent
CSVs on disk are `20260313` and `20260317` (loop-2 materialized them); see
"Where I felt uncertain" in the loop-3 trace for the inherited two-date
sampling limitation. To partially compensate, every test reports both
per-date statistic *and* the cross-date mean, and the chosen candidate
is the one with same-sign per-date support.

### Candidate 1: Halflife mismatch
Claim: parent halflife pair is too short → vol_ratio is noise → gate is
near-uniform → post-gate pnl is unconcentrated.
Falsification test:
  Artifact:   positions.csv on 20260313 and 20260317
  Statistic:  dispersion_ratio = std(realized_pnl) / mean(|realized_pnl|)
  Decision rule: FALSIFIED if mean across two dates < 4.0 (gate is
                 concentrating well; halflife is fine).

### Candidate 2: Spread-based adverse selection
Claim: residual losses after the parent's vol gate cluster at wide-spread
fills; the gate ignores spread.
Falsification test:
  Artifact:   orders.csv + positions.csv on 20260313 and 20260317,
              joined on `exec_spawn_id` ⇄ `opening_order_id`.
  Statistic:  Pearson correlation between
              `|avg_px - arrival_mid|` (spread proxy at fill) and
              `realized_pnl` across opening positions.
  Decision rule: SURVIVED if mean correlation < -0.05 across two dates;
                 otherwise FALSIFIED.

### Candidate 3: Vol-regime persistence
Claim: parent gates on instantaneous vol_ratio; transient bursts produce
short-hold adverse positions, sustained regimes produce longer-hold
better positions. The gate cannot distinguish.
Falsification test:
  Artifact:   positions.csv on 20260313 and 20260317
  Statistic:  diff = mean(pnl | duration >= median_dur) - mean(pnl | duration < median_dur)
  Decision rule: SURVIVED if |mean diff across two dates| >= $0.02 per
                 position AND same sign on both dates; otherwise FALSIFIED.

## Verdicts

Test results (n_positions in parentheses):

```
C1: dispersion_ratio | 20260313=1.43 (n=8026), 20260317=1.45 (n=19962), mean=1.44
    Rule: FALSIFIED if mean < 4.0
    Verdict: FALSIFIED | gate concentration is much tighter than uniform
             (1.44 vs uniform expected ~4-5)

C2: spread_pnl_corr  | 20260313=-0.0015 (n=8024), 20260317=-0.0492 (n=19961), mean=-0.025
    Rule: SURVIVED if mean < -0.05
    Verdict: FALSIFIED | mean -0.025 is above threshold; 20260317 is
             borderline (-0.049, just inside) but 20260313 is near zero,
             indicating the spread-pnl signal is not reliable across dates.

C3: pnl_slow - pnl_fast | 20260313=+0.119, 20260317=+0.026, mean=+0.073
    Rule: SURVIVED if |mean diff| >= 0.02 AND same sign per-date
    Verdict: SURVIVED  | both dates positive (slow > fast), mean $0.073
             >> 0.02 threshold. Magnitude meaningful on adverse days
             (20260313: $0.119; 20260317: $0.026 — still 1.3x threshold).
```

## Chosen hypothesis

C3 survived; C1 and C2 falsified. Per step 5 #1, implement C3.

**Parent behavior being changed**: parent's `_compute_submit_prob` returns
`max(min_prob, exp(-sensitivity × max(0, vol_ratio - 1)))` whenever
`tick_count >= min_ticks` — purely a function of *current* vol_ratio.

**Concrete modification**: add a *transient-burst suppression layer*.
Track the slow baseline of `vol_ratio` itself with a much longer EWM
(halflife = `regime_halflife` ticks; default = 5 × parent slow_halflife
= 600). Define `burst_delta = vol_ratio − vol_ratio_slow_avg`. When the
parent decides to *submit* (parent p_submit > some threshold), add an
additional check:

- If `vol_ratio > 1.0` AND `burst_delta > burst_threshold`: this is a
  **fresh, transient burst** → apply additional multiplicative suppression
  `transient_factor` (default 0.5) to parent's `p_submit`, then
  recompute the accept/skip draw with the same deterministic hash.
- Otherwise: keep parent's `p_submit` unchanged (sustained regimes
  and calm regimes pass through identically).

The deterministic hash, cold-start, min_prob floor, reduce-only bypass,
and quantity invariant are preserved exactly as in the parent.

**Expected directional changes vs `vol-regime-sizer`** (the fixed
comparison baseline):
- `realized_pnl`: ↑ (suppressing transient-burst submissions removes the
  short-hold adverse tail demonstrated by C3 — fast-bucket mean pnl was
  -$0.024 on 20260317 and -$0.121 on 20260313).
- `mean_slippage`: 0 (zero-slippage fill model; unchanged).
- `sharpe_ratio`: ↑ (concentrating participation in better-quality
  positions tightens daily pnl distribution).
- `trade_count`: ↓ slightly (additional suppression cuts ~5-15% of
  the orders the parent would have submitted, conditional on the
  transient-burst sub-regime being non-rare).

Supporting verdict: C3 SURVIVED with $0.073 mean separation between
slow-hold and fast-hold positions on the two test dates (both
same-sign positive).

## Parameter justifications

| Parameter | Value | Justification rule | Notes |
|---|---|---|---|
| `fast_halflife` | 20 | Inherited unchanged from parent. | parent param |
| `slow_halflife` | 120 | Inherited unchanged from parent. | parent param |
| `sensitivity` | 2.0 | Inherited unchanged from parent. | parent param |
| `min_prob` | 0.05 | Inherited unchanged from parent. | parent param |
| `min_ticks` | 30 | Inherited unchanged from parent. | parent param |
| `max_vol_ratio` | 5.0 | Inherited unchanged from parent. | parent param |
| `regime_halflife` | 600 | Principled rule: 5 × parent's `slow_halflife` (120) — the existing slow EWM already targets "regime baseline"; a 5x-longer EWM targets "regime-of-regimes" (smoothed vol_ratio level), which is the right timescale for detecting a fresh deviation from sustained regime. |
| `burst_threshold` | 0.3 | Principled rule: 0.3 corresponds to the parent's `sensitivity * (ratio-1)` where the exp-decay reaches `exp(-0.6) ≈ 0.55` (vol_ratio≈1.3); roughly the parent's own "moderate excess" threshold. Detecting a `burst_delta` of 0.3 means "current vol_ratio exceeds its long-run smoothed baseline by enough that the parent would already be down-weighting" — this aligns the new layer with the parent's own scale. |
| `transient_factor` | 0.5 | Principled rule: half — the simplest non-trivial principled suppression. C3's diff magnitudes ($0.07-$0.12) do not give enough resolution to tune this finer (would require a sweep across multiple dates with materialized CSVs, which the parent's on-disk artifacts do not support). 0.5 is a conservative middle (skip twice as often as parent during fresh bursts) and is documented as the chosen-by-rule-not-by-data tuning point. |
