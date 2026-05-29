# Algorithm Notes: sip-vrs-l6

Method: Propose-Audit-Falsify-Commit (prompt-l5.md).

## Parent mechanism

The parent `vol-regime-sizer` gates OPEN orders by an unsigned realized-vol
ratio. On every quote tick it updates two EWMs of `|delta_mid|`: a fast
EWM (`fast_halflife=20 ticks`) and a slow EWM (`slow_halflife=120 ticks`).
At order arrival it computes
`p = max(min_prob=0.05, exp(-sensitivity=2 * max(0, fast/slow - 1)))` and
accepts/skips via a deterministic SHA-256 hash of `client_order_id`.
Reduce-only orders bypass the gate. Cold-start (first 30 quotes) submits
at p=1.0. **In which regime it submits**: calm regimes where current
volatility is close to or below the slow baseline (`fast/slow <= 1`) get
p=1.0. **In which regime it skips/shrinks**: elevated-vol regimes
(`fast/slow > 1`) get probabilistic skip with rate
`1 - exp(-2*(ratio-1))`, floored at 5%. The parent has no notion of
side direction, time-of-day, spread, queue position, hold duration,
trade rate, order-direction history, or price level.

Full audit and falsification universe (train dates from
`research/config.yaml -> data_window.train`):
20260308, 20260309, 20260310, 20260311, 20260312, 20260313, 20260315,
20260316, 20260317, 20260318, 20260319, 20260320 (12 dates). 20260319's
parent CSV cannot be materialized (Rust allocator OOM on 4 GiB cap;
documented in loop-5 trace as a runner-level issue), so per-date audit
and falsification cover 11 of 12 train dates. The 11-date sample is
flagged as a limitation in step 5 below.

## Candidate weaknesses

Prior loops already exercised these axes (do not duplicate):
- L1 (kept): signed-direction headwind gate
- L2 (reverted): time-of-day close-window suppression
- L3 (reverted): regime-persistence (transient vs sustained burst) gate
- L4 (reverted): trendiness re-admit multiplier
- L5 (kept): wide top-of-book spread skip layer

This loop targets three substantively different axes.

### Candidate 1: Side-asymmetric oracle edge
"The parent's mechanism is *direction-symmetric gating on unsigned
vol_ratio* which fails in regime *one-sided drift days where the oracle's
BUY edge and SELL edge differ in sign or magnitude* because *the unsigned
gate skips both sides equally even when only one side carries adverse
selection.*"
Binding feature: per-order side (BUY vs SELL) at order arrival.
Per-date binding distribution: `buy_share` (fraction of opening orders
that are BUY).

### Candidate 2: Entry mid-price near top/bottom of a rolling intraday range
"The parent's mechanism is *vol-only gating without reference to price
level* which fails in regime *order arrivals at the extremes of a recent
mid-price range* because *oracle BUYs near the top of a 60-second range
are likely fading a finished move (adverse selection) and oracle SELLs
near the bottom are likely fading a finished dip.*"
Binding feature: signed `adverse_score` at order arrival, defined as
`pos_in_range_60s` for BUY orders and `1 - pos_in_range_60s` for SELL
orders, where `pos_in_range_60s = (mid - min_60s) / (max_60s - min_60s)`.
Range [0, 1]. Per-date binding distribution: `frac(adverse_score > 0.80)`.

### Candidate 3: Round-number price proximity (psychological levels)
"The parent's mechanism is *price-agnostic gating* which fails in regime
*arrivals where the mid sits within 1 tick of a 5-point round level
(multiples of 5 in MES)* because *stop runs / liquidity sweeps around
round numbers introduce adverse selection the unsigned vol-ratio cannot
see.*"
Binding feature: `round_dist_ticks = |mid - round(mid/5)*5| / 0.25`.
Per-date binding distribution: `frac(round_dist_ticks < 1)`.

## Regime audit

Stats below are computed from parent on-disk CSVs at
`execution_algos/vol-regime-sizer/results/<YYYYMMDD>/{orders.csv, positions.csv}`,
one pandas aggregation per train date per candidate. 11 of 12 dates
covered (20260319 missing due to OOM).

### Candidate 1 audit
Binding feature: order side (BUY vs SELL); distribution stat = buy_share.
Per-date distribution:

| date | n_open_positions | buy_share | mean_pnl_buy | mean_pnl_sell | pnl_gap_buy_minus_sell |
|------|------:|------:|------:|------:|------:|
| 20260308 | 367 | 0.504 | +0.116 | +0.478 | -0.362 |
| 20260309 | 2878 | 0.501 | +0.261 | +0.193 | +0.068 |
| 20260310 | 2290 | 0.498 | +0.186 | +0.175 | +0.010 |
| 20260311 | 2416 | 0.499 | +0.058 | +0.121 | -0.063 |
| 20260312 | 5447 | 0.501 | -0.044 | -0.029 | -0.014 |
| 20260313 | 8026 | 0.504 | -0.067 | -0.046 | -0.021 |
| 20260315 | 1832 | 0.499 | +0.009 | -0.046 | +0.055 |
| 20260316 | 19209 | 0.500 | -0.018 | -0.023 | +0.005 |
| 20260317 | 19962 | 0.499 | -0.008 | -0.009 | +0.000 |
| 20260318 | 20913 | 0.500 | +0.006 | +0.013 | -0.007 |
| 20260320 | 21032 | 0.500 | +0.007 | +0.016 | -0.009 |

Heterogeneity verdict: HOMOGENEOUS (buy_share ratio_max/min = 1.01, every
date within tight cross-date IQR). Order side is split ~50/50 on every
date — the binding distribution itself is highly stable.

### Candidate 2 audit
Binding feature: `adverse_score` ∈ [0, 1]; distribution stat =
`frac(adverse_score > 0.80)` per date.
Per-date distribution:

| date | n_opens | mean_adv | median_adv | p10 | p90 | frac>0.80 | frac<0.20 |
|------|------:|------:|------:|------:|------:|------:|------:|
| 20260308 | 377 | 0.488 | 0.50 | 0.0 | 1.0 | 0.361 | 0.385 |
| 20260309 | 3105 | 0.474 | 0.50 | 0.0 | 1.0 | 0.326 | 0.380 |
| 20260310 | 2480 | 0.470 | 0.50 | 0.0 | 1.0 | 0.314 | 0.375 |
| 20260311 | 2648 | 0.490 | 0.50 | 0.0 | 1.0 | 0.329 | 0.348 |
| 20260312 | 6000 | 0.486 | 0.50 | 0.0 | 1.0 | 0.339 | 0.372 |
| 20260313 | 9042 | 0.490 | 0.50 | 0.0 | 1.0 | 0.314 | 0.340 |
| 20260315 | 2026 | 0.497 | 0.50 | 0.0 | 1.0 | 0.317 | 0.329 |
| 20260316 | 22393 | 0.497 | 0.50 | 0.0 | 1.0 | 0.288 | 0.301 |
| 20260317 | 23089 | 0.497 | 0.50 | 0.0 | 1.0 | 0.291 | 0.305 |
| 20260318 | 23529 | 0.497 | 0.50 | 0.0 | 1.0 | 0.294 | 0.308 |
| 20260320 | 23996 | 0.495 | 0.50 | 0.0 | 1.0 | 0.288 | 0.307 |

Heterogeneity verdict: HOMOGENEOUS (frac>0.80 ratio_max/min = 1.25,
max_iqr_excess = 0.95). Adverse_score distribution is essentially
identical across all 11 dates — mean ~ 0.49, with ~29-36% of orders
in the top quintile of recent range.

### Candidate 3 audit
Binding feature: `round_dist_ticks ∈ [0, 10]` (since round levels are
5 points = 20 ticks apart; max distance from nearest is 10 ticks).
Distribution stat = `frac(round_dist_ticks < 1)`.
Per-date distribution:

| date | n_opens | mean_dist | median_dist | p10 | p90 | frac<1tick |
|------|------:|------:|------:|------:|------:|------:|
| 20260308 | 377 | 5.22 | 5.5 | 1.0 | 9.5 | 0.048 |
| 20260309 | 3105 | 5.00 | 5.0 | 1.0 | 9.0 | 0.068 |
| 20260310 | 2480 | 4.86 | 5.0 | 1.0 | 9.0 | 0.070 |
| 20260311 | 2648 | 4.99 | 5.0 | 1.0 | 9.0 | 0.067 |
| 20260312 | 6000 | 4.96 | 5.0 | 1.0 | 9.0 | 0.077 |
| 20260313 | 9042 | 4.97 | 5.0 | 1.0 | 9.0 | 0.092 |
| 20260315 | 2026 | 4.82 | 4.5 | 0.5 | 8.5 | 0.102 |
| 20260316 | 22393 | 5.01 | 5.0 | 1.0 | 9.0 | 0.100 |
| 20260317 | 23089 | 4.98 | 5.0 | 0.5 | 9.0 | 0.101 |
| 20260318 | 23529 | 5.01 | 5.0 | 1.0 | 9.0 | 0.095 |
| 20260320 | 23996 | 5.08 | 5.5 | 1.5 | 9.0 | 0.087 |

Heterogeneity verdict: HOMOGENEOUS (frac<1tick ratio_max/min = 2.13,
max_iqr_excess = 0.74). Distance distribution is approximately uniform
on [0, 10] ticks on every date — the binding-feature regime is stable.

## Falsification test

All three candidates have HOMOGENEOUS binding distributions, so each uses
the **HOMOGENEOUS aggregate rule** from step 4 of the method.

### Candidate 1: Side asymmetry
Claim: per-side mean realized_pnl differs systematically; the parent's
unsigned gate skips both sides equally.
Heterogeneity (binding feature): HOMOGENEOUS.
Falsification test:
  Artifact:   positions.csv + orders.csv joined per date.
  Date set:   all 11 train dates with on-disk parent CSVs.
  Statistic:  per-date `mean_pnl(BUY) - mean_pnl(SELL)` (USD/contract).
  Decision rule (HOMOGENEOUS aggregate):
    SURVIVED if mean of per-date gap across dates >= 0.03 AND
    sign-consistent (same sign) on >= 9 of 11 dates.

### Candidate 2: Range-position adverse score
Claim: opens with `adverse_score > 0.80` (BUY near 60s high or SELL near
60s low) have worse realized_pnl than opens with `adverse_score < 0.20`.
Heterogeneity (binding feature): HOMOGENEOUS.
Falsification test:
  Artifact:   positions.csv + orders.csv joined; arrival_mid as the
              per-order mid (rolling 60s by ts_init).
  Date set:   all 11 train dates with on-disk parent CSVs.
  Statistic:  per-date `mean_pnl(adverse_score<0.20) - mean_pnl(adverse_score>0.80)`.
  Decision rule (HOMOGENEOUS aggregate):
    SURVIVED if mean of per-date gap across dates >= 0.04 AND
    sign-positive on >= 9 of 11 dates.

### Candidate 3: Round-number proximity
Claim: opens with `round_dist_ticks < 1` (mid within 1 tick of a 5-point
round level) have worse realized_pnl than opens with `round_dist_ticks >= 1`.
Heterogeneity (binding feature): HOMOGENEOUS.
Falsification test:
  Artifact:   orders.csv joined to positions.csv per date.
  Date set:   all 11 train dates with on-disk parent CSVs.
  Statistic:  per-date `mean_pnl(round_dist >= 1tick) - mean_pnl(round_dist < 1tick)`.
  Decision rule (HOMOGENEOUS aggregate):
    SURVIVED if mean of per-date gap across dates >= 0.04 AND
    sign-positive on >= 9 of 11 dates.

## Verdicts

```
Verdict C1: FALSIFIED  | mean_gap=-0.0308, n_pos=5/11 (need >=9), median|gap|=0.0143. The signed
                         per-date gap flips sign across dates (5 positive, 6 negative). One
                         outlier date (20260308, gap=-0.362, n=367) drives the mean; the
                         remaining 10 dates have |gap| ≤ 0.07. Side asymmetry is not
                         directionally stable.
Verdict C2: FALSIFIED  | mean_gap=-0.0394, n_pos=5/11 (need >=9), median|gap|=0.0154. The
                         per-date gap is sign-inconsistent. On the 4 highest-volume dates
                         (20260316/17/18/20) the gap is in [-0.020, +0.015] — essentially zero.
                         The 20260308 outlier (gap=-0.285, n_low=141, n_high=131) is small
                         sample but heavily negative, consistent with "adverse_score" being
                         in the wrong direction or unrelated to oracle accuracy on a thin day.
Verdict C3: FALSIFIED  | mean_gap=+0.0131, n_pos=7/11 (need >=9), median|gap|=0.0054. On the
                         4 highest-volume dates (n_near>1800) the gap is in [-0.005, +0.005]
                         — essentially zero. On the 4 lowest-volume dates (n_near<200) the
                         gap is in [-0.367, +0.171] with mixed signs — dominated by sample
                         noise. The "effect" disappears entirely on the dense dates that
                         carry the parent's pnl.
```

## Chosen hypothesis

**All three candidates were FALSIFIED.** Per step 5 #3 (zero survived,
pick weakest violation): C3 has the smallest violation margin of the
three:
- C1: mean -0.061 short of rule, n_pos 4 short (5/11 vs needed 9/11).
- C2: mean -0.079 short of rule, n_pos 4 short.
- C3: mean -0.027 short of rule, n_pos 2 short (7/11 vs needed 9/11) —
       smallest gap on both axes.

I implement C3 as **"weakest falsification chosen; no candidate survived."**
**Honesty flag**: this loop's hypothesis is statistically thin. The
falsification data show the effect is concentrated on low-volume dates
where sample sizes are <200 per bucket; on the 4 highest-volume dates
the effect is essentially zero. The expected lift from a round-number
gate is small at best and likely near-neutral.

**Parent behavior being changed**: the parent's `_compute_submit_prob`
returns `max(min_prob, exp(-sensitivity * max(0, vol_ratio - 1)))`
regardless of where the order's mid price sits relative to nearby
round levels.

**Concrete modification — round-number guard layered on top of the
parent**: at order arrival, compute
`round_dist_ticks = |last_mid - round(last_mid / 5) * 5| / 0.25`. If
`round_dist_ticks < round_threshold_ticks` (default 1.0), multiply the
parent's `p_submit` by `round_suppress` (default 0.0, hard skip). Else
leave `p_submit` unchanged.

Cold-start, reduce-only bypass, the parent's vol-regime formula,
`min_prob` floor, and the deterministic SHA-256 accept/skip draw are
preserved exactly.

**Expected direction vs `vol-regime-sizer`**:
- realized_pnl: ~0 (mean gap is +0.013 across dates, but with a
  significant outlier in the wrong direction). Most likely slightly
  positive on thin dates and zero on dense dates.
- mean_slippage: 0 (zero-slippage fill model).
- sharpe_ratio: ambiguous — could tighten on thin dates if the gate
  removes a few small losers; could widen if it removes winners.
- trade_count: ↓ by ~7-10% (frac<1tick across dates).
- win_rate: ambiguous; the median per-date gap is +0.005, suggesting
  near-zero impact on per-position pnl distribution.

**Regime-coverage prediction**: the binding feature fires on
`frac(round_dist_ticks < 1)`. From the audit table, on the 11 train
dates this fraction is **0.048 to 0.102 per date** — all 11 dates have
at least 4.8% binding-feature arrivals AND none exceeds 11%. So the
gate will fire on >= 5% of arrivals on **9 of 11 dates** (20260308 at
4.8% and 20260309 at 6.8% — 20260308 marginal at 4.8% slightly below
5%, 20260309 clearly above). Rounded prediction: **9-10 of 12 train
dates fire on >= 5%**. Neither extreme (<= 1 or >= 11) — the
binding-feature distribution is well-behaved across the train window.

**Supporting falsification verdict**: C3 falsified with the smallest
violation margin among the three (mean +0.013 vs 0.04 threshold).

## Parameter justifications

| Parameter | Value | Justification rule | Notes |
|---|---|---|---|
| `fast_halflife` | 20 | Inherited unchanged from parent. | parent param |
| `slow_halflife` | 120 | Inherited unchanged from parent. | parent param |
| `sensitivity` | 2.0 | Inherited unchanged from parent. | parent param |
| `min_prob` | 0.05 | Inherited unchanged from parent. | parent param |
| `min_ticks` | 30 | Inherited unchanged from parent. | parent param |
| `max_vol_ratio` | 5.0 | Inherited unchanged from parent. | parent param |
| `round_level_points` | 5.0 | Principled rule: the most prominent round-number grid in MES quote prices is the 5-point level (e.g., 5800.00, 5805.00). 1-point levels are pervasive; 10/25-point levels are too sparse to fire on more than a handful of orders per date. 5-point chosen as the median-density level. |
| `round_threshold_ticks` | 1.0 | Derived from step-4 statistic: the falsification bucket boundary `round_dist < 1 tick` was chosen at audit time before falsification; the binding-feature distribution (audit table) shows `frac<1tick` ∈ [0.048, 0.102] across the 11 train dates — a 7% median activation rate, well-bounded and matching the regime-coverage prediction. |
| `round_suppress` | 0.0 (hard skip) | Principled rule: the falsification verdict was directionally positive (mean +0.013) but below threshold; a partial-suppress value (e.g., 0.5) would be a free parameter not derivable from the data. Hard skip removes the binding-feature regime entirely; this matches the parent's L5 pattern (`wide_spread_suppress=0.0`). The expected per-date pnl impact is small either way. |
| `tick_size` | 0.25 | Constant of the MES futures contract; not a free parameter. |

**Regime-aware parameter rule (Step 6, additional)**: the binding feature
(`round_dist_ticks`) is HOMOGENEOUS across train dates per the audit, so
an **absolute** threshold (1 tick) is permitted by the method. A
regime-relative threshold (e.g., `1 tick × rolling_median_dist`) is not
required because the binding-feature distribution is essentially
identical on every train date.

## Honesty notes

- All three candidates FALSIFIED — this is a weakest-violation pick, not
  a SURVIVED hypothesis. The expected lift is small to near-zero.
- 11-of-12 train date coverage in the audit and falsification (20260319
  OOM'd as in L5; documented as a runner-level limitation).
- The C3 binding-feature distribution is stable across dates
  (HOMOGENEOUS verdict supported by audit), so the gate's *firing rate*
  is predictable — but the *effect* on pnl is essentially noise on the
  highest-volume dates.
- No new free parameters introduced from intuition. `round_level_points=5`,
  `round_threshold_ticks=1`, `round_suppress=0.0` all derive from step-3
  audit data, step-4 falsification, or the parent's L5-pattern principle
  (hard-skip when the rational-participation expectation is unclear).
- Skepticism: the only large positive gaps in C3 come from low-sample
  dates (n_near < 200 on 5 of 11 dates). The "signal" disappears on the
  4 highest-volume dates that carry most of the parent's pnl. This is
  exactly the kind of regime artifact prompt-l5's step-3 audit was
  designed to surface — and it does, before commitment. The method is
  working; the *data* simply lacks signal on the three axes considered.
