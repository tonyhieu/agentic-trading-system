# Algorithm Notes: sip-vrs-l5

Parent: `vol-regime-sizer`. Method used: propose-falsify-commit (`prompt-l1.md`).

## Parent mechanism

`vol-regime-sizer` updates two exponential moving averages of `|Δmid|` on every
quote tick — a fast EWM (halflife=20 ticks) and a slow EWM (halflife=120 ticks).
For each OPEN parent order it computes `vol_ratio = fast_vol / slow_vol`
(clipped at `max_vol_ratio=5`), maps to `p_submit = max(min_prob=0.05,
exp(-sensitivity=2.0 * max(0, vol_ratio - 1)))`, and decides via deterministic
SHA-256 of the `client_order_id` whether to submit or skip. Cold start
(`tick_count < min_ticks=30`) and undefined-baseline branches return `p=1.0`.
Reduce-only orders bypass the gate. The gate measures unsigned tick-rate
turbulence vs a longer-tick baseline; it has no notion of order side, hold
duration, intraday time-of-day, or whether vol is rising or falling.

## Candidate weaknesses

These three are substantively different from prior loops:
- **Loop 1 (kept)**: signed-headwind gate — replaced unsigned `vol_ratio` with
  `headwind = -side·drift / slow_vol`. Already covers signed-direction axis.
- **Loop 2 (reverted)**: close-window suppression — time-of-day axis.
- **Loop 3 (reverted)**: vol_ratio persistence — transient-burst suppression
  using a slow EWM of `vol_ratio` itself.
- **Loop 4 (reverted)**: trendiness re-admit — re-admitting parent skips on
  trending windows.

This loop avoids time-of-day, signed direction, persistence/transience, and
re-admit. The three new candidates target axes the prior loops have not
exercised: trade volume regime, per-date trade frequency, and `is_mean_bps`
heterogeneity.

### Candidate 1: Trade-count-regime mismatch
Claim: the parent's halflife pair `(20, 120)` is anchored to *tick count*,
not wall-clock time. On days with very different trade densities (e.g.
20260308 has 367 trades, 20260319 has 23,619 trades — a ~64× spread), the
*same* `(20, 120)` window covers ~30s on a thin day vs ~0.5s on a thick day.
This means the gate's notion of "fast vs slow vol" is internally inconsistent
across the train window: on thin days the gate measures regime over half a
minute (matching oracle horizon); on thick days the gate measures sub-second
microstructure noise. If true, the parent should perform *worst* on the
thickest-trade dates and the gate's pnl signal should track trade density.

Falsification artifact will be **per-date aggregate metrics**, not CSVs — this
candidate is about cross-date heterogeneity.

### Candidate 2: Position-hold-duration blindness
Claim: the parent decides submit/skip at order-arrival time using only quote
ticks observed *up to that moment* — it never accounts for the duration the
position will be held. For the oracle (30s horizon), positions that close
quickly via stop-out or contra-signal carry a different pnl distribution than
positions that ride the full horizon. If short-hold positions dominate the
losing tail, the parent's gate is failing on a specific sub-regime (held only
through the noisy front of the horizon) that vol_ratio at order-arrival
cannot detect.

### Candidate 3: Implementation-shortfall asymmetry
Claim: the parent's submit/skip decision ignores the spread/queue state at
order-arrival, but execution shortfall (`is_mean_bps`) varies by ~10× across
train dates (0.013 on 20260318 to 0.174 on 20260308). High-`is_bps` dates
have execution penalties baked into every fill that the parent never sees in
its `|Δmid|` signal. If true, the parent's losses should correlate with
per-fill implementation shortfall *within* a date — not just with vol_ratio.

## Falsification tests

Decision rules stated before running any test. Each test is one pandas read +
one conditional aggregation.

### Candidate 1 test: Trade-count-regime mismatch
Artifact:  per-date `metrics.json` under `execution_algos/vol-regime-sizer/results/<YYYYMMDD>/`,
           all 12 train dates.
Statistic: Spearman correlation between `trade_count` (per date) and
           `(parent_pnl - simple_pnl)` (per date, parent edge). If the parent's
           gate becomes counterproductive on high-trade-count dates because
           its halflife is mis-anchored to ticks rather than time, the edge
           should shrink (or invert) on thick dates → negative correlation.
Decision rule: SURVIVED if Spearman ρ ≤ -0.40 (strong negative association
               between trade density and parent's edge over simple) AND
               parent edge is < 0 on at least 2 of the top-4 thickest dates.
               Otherwise FALSIFIED.

### Candidate 2 test: Position-hold-duration blindness
Artifact:  `positions.csv` on 20260316 + 20260318 (one loss day + one win day,
           both regenerated for this loop).
Statistic: split parent's submitted positions by hold duration
           `(ts_closed - ts_opened)`. Define short-hold = duration <
           median(duration). Compute
           `delta = mean_pnl(short_hold) − mean_pnl(long_hold)`.
Decision rule: SURVIVED if mean across the two dates of |delta| ≥ $0.05 per
               contract AND same sign on both dates. Otherwise FALSIFIED.

Note: this is *different* from loop 3's C3, which compared the fast vs slow
*pnl bucket by duration*. Here the rule is hard $0.05/contract per-side
threshold *and* same-sign — a stricter and clearer test.

### Candidate 3 test: Implementation-shortfall asymmetry
Artifact:  `orders.csv` on 20260316 + 20260318. Each order row carries an
           `is_bps` column (per-fill implementation shortfall).
Statistic: Among submitted OPEN orders, compute Pearson correlation between
           `is_bps` (per order) and the realized fill pnl (signed by side and
           computed against mid 30s after fill, approximated by joining to
           `positions.csv` on `opening_order_id`).
Decision rule: SURVIVED if correlation is ≤ -0.10 on at least one date and
               same-sign (negative) on both dates — i.e., higher-cost
               executions consistently produce worse pnl, supporting an
               `is_bps`-aware gate. Otherwise FALSIFIED.

## Verdicts (3 lines)

Run script outputs reproduced verbatim under `## Test results` below.

Verdict C1: **FALSIFIED** | Spearman rho(trade_count, parent_edge_over_simple) = **+0.918** on n=11 train dates available. Hypothesis predicted negative correlation; observed strongly positive (parent's edge over `simple` is LARGER on thick-trade dates, not smaller). Among the top-4 thickest dates, 0/4 have edge<0. Margin: −1.318 (rho is +0.918, threshold was −0.40; the direction itself is reversed).

Verdict C2: **FALSIFIED** | Mean |delta(short_hold − long_hold pnl)| across two dates = **$0.040/contract** (20260316: −$0.0361, 20260318: −$0.0439). Same-sign on both dates (both negative), but mean magnitude is below the $0.05 threshold. Margin: −$0.010 (closest to surviving among the three).

Verdict C3: **SURVIVED** | Pearson corr(is_bps, fill_pnl) = **−0.153** on 20260316 (n=19,209) and **−0.171** on 20260318 (n=20,913). Both dates ≤ −0.10. Same-sign (negative) on both. Margin: +$0.053 (corr on the closer-to-rule date is 0.053 past the threshold).

## Test results

```
C1: Spearman ρ(trade_count, parent_edge) over 11 train dates
    parent_edge = parent.realized_pnl − simple.realized_pnl
    ρ = +0.918 (n=11)
    Top-4 thickest dates (trade_count, edge):
      20260319: 23,619 +61.50
      20260320: 21,032 +112.25
      20260317: 19,962 +79.50
      20260316: 19,209 +128.75
    Edge<0 among top-4: 0
    Rule: SURVIVED if ρ ≤ −0.40 AND ≥2 of top-4 have edge<0 → FALSIFIED.

C2: short-hold vs long-hold pnl, parent FLAT positions, split at per-date median
    20260316: median_dur=2.63s, short n=9,604 mean=−$0.0385, long n=9,605 mean=−$0.0024, delta=−$0.0361
    20260318: median_dur=2.40s, short n=10,456 mean=−$0.0126, long n=10,457 mean=+$0.0313, delta=−$0.0439
    mean|delta| = $0.040
    Rule: SURVIVED if mean|delta| ≥ $0.05 AND same sign → FALSIFIED (magnitude below threshold; signs aligned).

C3: Pearson corr(is_bps, realized_pnl) over parent FLAT positions joined to
    their FILLED opening order rows
    20260316: corr = −0.1528 (n=19,209)
    20260318: corr = −0.1711 (n=20,913)
    Rule: SURVIVED if either date ≤ −0.10 AND both same-sign negative → SURVIVED.

C3 supporting bucket analysis (mean pnl by half-spread bin, parent FLAT
positions joined to their FILLED opening orders):

20260316 (parent_pnl = −$392.75):
  half_spread (0.0, 0.125] (1-tick spread, ~92% of orders, n=17,590): mean pnl = −$0.010
  half_spread (0.125, 0.25] (n=1,165):                                  mean pnl = −$0.125
  half_spread (0.25, 0.40]  (n=433):                                    mean pnl = −$0.159
  half_spread (0.40, 1.00]  (n=20):                                     mean pnl = +$0.050

20260318 (parent_pnl = +$196.25):
  half_spread (0.0, 0.125] (1-tick, ~95% of orders, n=19,944): mean pnl = +$0.012
  half_spread (0.125, 0.25] (n=718):                            mean pnl = −$0.049
  half_spread (0.25, 0.40]  (n=246):                            mean pnl = −$0.065
  half_spread (0.40, 1.00]  (n=5):                              mean pnl = +$0.250 (too thin)

The corr is driven by the wide-spread (half_spread > 0.125) buckets. They
are ~5−8% of submitted opens but carry mean pnl 5−10× more negative than
the 1-tick bucket. On 20260316, the wide-spread buckets contribute about
1,618 × −$0.131 = −$212 of pnl — over half the day's loss.

## Chosen hypothesis

C3 survived; C1 and C2 falsified. Per step 5 #1, implement C3.

**Parent behavior being changed**: parent's `_compute_submit_prob` returns
`max(min_prob, exp(−sensitivity × max(0, vol_ratio − 1)))` with no
visibility into the bid-ask spread at order-arrival time. Because
`is_bps` is a *post-fill* property, the at-arrival proxy must be the
top-of-book spread observed in the live tick stream.

**Concrete modification**: layer a **wide-spread skip** on top of the
parent's existing vol-regime gate. The execution algorithm subscribes
to the same `on_quote_tick` stream the parent uses; on every tick it
caches the most recent `(bid, ask)`. When an OPEN parent order arrives:

1. Compute `parent_p_submit` using the parent's exact formula (unchanged).
2. Look up the cached `(bid, ask)`. If `ask − bid` exceeds
   `wide_spread_threshold * tick_size`, multiply `parent_p_submit` by
   `wide_spread_suppress` (default 0.0 = hard skip).
3. Otherwise, leave `parent_p_submit` unchanged.
4. Run the parent's deterministic SHA-256 accept/skip draw.

The deterministic hash, cold-start (`tick_count < min_ticks`),
`min_prob` floor, reduce-only bypass, and quantity invariant are
preserved exactly as in the parent. The new gate is a guard *layered
on top of* the parent — it only further suppresses; it never
re-admits an order the parent would skip. This matches the loop-2
critique structure (`close_suppress` was a similar layered guard) and
deliberately avoids the loop-4 pattern (re-admit layer competing with
the parent's skip).

**Expected direction vs `vol-regime-sizer`**:
- `realized_pnl`: ↑ — skipping wide-spread fills removes the per-fill
  expected-loss contribution observed in the step-4 buckets
  (~5−8% of opens carrying −$0.05 to −$0.16 mean pnl).
- `mean_slippage`: 0 — zero-slippage fill model, no walking the book.
- `sharpe_ratio`: ↑ — narrower daily pnl distribution from removing
  the wide-spread loss tail.
- `trade_count`: ↓ slightly — additional skips on top of parent's gate
  (roughly the 5−8% wide-spread fraction on parent-submitted orders).
- `win_rate`: ↑ slightly — removed fills have win rates below the
  population (loss-heavy tail).

Supporting verdict: C3 SURVIVED with corr −0.153 / −0.171 across the
two test dates (same-sign on both) and a per-bucket separation of
mean pnl by half-spread of $0.10 − $0.15/contract between 1-tick
and wider-spread populations.

## Parameter justifications

| Parameter | Value | Justification rule | Notes |
|---|---|---|---|
| `fast_halflife` | 20 | Inherited unchanged from parent. | parent param |
| `slow_halflife` | 120 | Inherited unchanged from parent. | parent param |
| `sensitivity` | 2.0 | Inherited unchanged from parent. | parent param |
| `min_prob` | 0.05 | Inherited unchanged from parent. | parent param |
| `min_ticks` | 30 | Inherited unchanged from parent. | parent param |
| `max_vol_ratio` | 5.0 | Inherited unchanged from parent. | parent param |
| `wide_spread_threshold` | 1.5 (× tick_size) | Derived from step-4 statistic. The 1-tick-spread bucket (half_spread ≤ 0.125, i.e. full spread ≤ 0.25) had mean pnl −$0.010 (20260316) and +$0.012 (20260318) — near break-even. The (0.125, 0.25] half-spread bucket (full spread in (0.25, 0.50], i.e. 2-tick wide) had mean pnl −$0.125 / −$0.049 — strongly negative on both dates. Threshold is set above the 1-tick equilibrium and below the 2-tick wide regime: `1.5 × tick_size = 0.375`. Orders see "wide" when `ask − bid > 0.375` (i.e. spread strictly wider than 1 tick). | derived |
| `wide_spread_suppress` | 0.0 (hard skip) | Derived from step-4 statistic. In wide-spread regimes the expected pnl per fill is negative on both test dates. Principled rule (mirroring loop 2's close-window logic, which was reverted on the gate but had a defensible per-statistic origin): if expected pnl in a regime is negative, the rational participation rate is 0. Hard skip is more aggressive than fractional; the fallback if the loop fails is to soften this to 0.3 in a follow-up. | derived |
| `tick_size` | 0.25 | Principled rule: MES has a quarter-point tick. Constant of the futures contract; not a free parameter. | constant |

## Honesty notes

- **C2 was very close to surviving** (mean |delta| = $0.040 vs $0.050 threshold). I am not relaxing the rule post-hoc to re-survive C2 — that is the exact failure mode propose-falsify-commit exists to prevent. If C3's algorithm regresses vs parent in the backtest, C2 + duration-aware gating is the natural next loop's candidate.
- **C3's mechanism (`is_bps`) is post-fill; the implementation uses the *spread at arrival* as a proxy.** The corr test was on `is_bps`, but the actual gate uses `bid - ask` at the tick immediately preceding the order. These are tightly related for taker fills (a taker fill at the inside crosses half the spread, so `|is_bps|` is dominated by `half_spread / mid`), but they are not identical. The step-4 per-bucket pnl analysis was redone on `half_spread = avg_px - arrival_mid` to confirm the proxy carries the same signal — bucket means by half_spread reproduce the same pattern as bucket means by `is_bps`. This is an explicit limitation: I am betting that the spread-at-arrival captures the wide-cost regime nearly as well as the post-fill `is_bps`. If the bet is wrong, the gate will under-fire (the predictive signal is in spread *change* between arrival and fill, which the at-arrival snapshot misses).
- **Only 2 of 12 train dates were used for step-4 falsification.** The C3 corr is consistently negative on both, and bucket-pnl shows the same shape on both. Generalization to the other 10 dates is the main risk; I report the same per-bucket statistic on the remaining dates if backtest results call it into question.
- **The "wide-spread" regime is ~5−8% of opens.** Aggregate-pnl impact is bounded: on 20260316, hard-skipping all wide-spread opens would have moved that day's pnl by roughly +$212 (recovery of the wide-spread loss). On 20260318, the analogous impact is about +$50. These per-date estimates assume independence — i.e., the orders that are skipped do not bear costs (margin/opportunity cost) elsewhere; in a 1-contract intraday-flat strategy with zero-slippage fills that assumption holds.
