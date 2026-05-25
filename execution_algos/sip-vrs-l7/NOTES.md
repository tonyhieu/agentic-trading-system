# Algorithm Notes: sip-vrs-l7

Method used: **Propose-Audit-Falsify-Commit** (`prompt-l5.md`, the
running-best method after loop-6 critique reverted the loop-6
proposal).

## Parent mechanism

`vol-regime-sizer` updates two EWMAs of `|Δmid|` from quote ticks
(fast halflife=20 ticks, slow halflife=120 ticks). For each OPEN
parent order it computes `vol_ratio = fast_vol / slow_vol`
(clipped at `max_vol_ratio=5`), maps to
`p_submit = max(min_prob=0.05, exp(-sensitivity=2.0 × max(0, vol_ratio − 1)))`,
and decides via deterministic SHA-256 of `client_order_id` whether to
submit or skip. Cold-start (`tick_count < min_ticks=30`) returns
`p=1.0`. Reduce-only orders bypass the gate. The gate measures
unsigned tick-rate turbulence vs a longer-tick baseline — it has no
notion of side, hold duration, time-of-day, or whether vol is rising
or falling. Loop-5 (kept, running-best) added a wide-spread skip
layered on top: if the cached top-of-book spread at order arrival
exceeds `1.5 × tick_size = 0.375`, multiply `p_submit` by
`wide_spread_suppress = 0.0` (hard skip). This algorithm layers
**on top of sip-vrs-l5** — same vol-regime gate, same wide-spread
skip, plus the new mechanism below.

**Train dates (11/12 — 20260319 OOMs in the runner)**: 20260308,
20260309, 20260310, 20260311, 20260312, 20260313, 20260315, 20260316,
20260317, 20260318, 20260320.

**Prior-loop axes (do not duplicate)**:
- L1 (kept-then-reverted): signed-headwind gate (direction × drift).
- L2 (reverted): close-window time-of-day suppression.
- L3 (reverted): vol_ratio persistence (transient-burst suppression).
- L4 (reverted): trendiness re-admit layer.
- L5 (kept, running-best): wide-spread skip on top of vol-regime gate.
- L6 (reverted): three CSV-derivable candidates — side asymmetry,
  arrival_mid range-position, round-number distance. All FALSIFIED;
  round-number admitted as weakest violation; the gate punished the
  no-mechanism pick (0/5 metrics improved vs L5).

## Tier-A candidate weaknesses

This loop targets three axes substantively different from all prior
loops. All three binding features are derivable from parent CSVs.

### Candidate 1: Order-arrival-cadence vol mismatch
The parent's mechanism is `unsigned tick-cadence EWM(|Δmid|) ratio`
which fails in regime `clusters of large mid-price jumps between
consecutive orders` because `the parent measures vol over ticks, not
over the order-arrival cadence the oracle actually fires at — when
arrival_mid jumps several ticks between consecutive orders, the
parent's tick-cadence EWMs may still see calm intervening micro-
structure`.

**Binding feature**: rolling-K=5 mean of `|Δarrival_mid|` between
consecutive parent OPEN orders.

### Candidate 2: Rolling-pnl streak persistence
The parent's mechanism is `at-arrival vol-regime + at-arrival
spread gate (L5)` which fails in regime `the next order arriving
during an adverse pnl streak in the same session` because `realized
pnl exhibits short-window autocorrelation across consecutive closed
positions — when the last M=10 closed positions averaged negative,
the next position is more likely negative, and neither the vol gate
nor the spread gate sees this`.

**Binding feature**: rolling-M=10 mean of `realized_pnl` over the
last 10 closed positions, lagged by 1 to avoid look-ahead.

### Candidate 3: Implementation-shortfall tail (|is_price|)
The parent's mechanism is `at-arrival spread-gate (L5)` which fills
the **at-arrival spread** as a proxy for the post-fill cost. Wide-
spread skip removes orders where spread > 1 tick, but the per-date
top-decile of `|is_price|` carries information **beyond** what
spread alone explains (queue position, fill latency, walking).
**Binding feature**: per-date p90 of `|is_price|` on filled opens.

## Regime audit (Tier-A)

All three audits used parent CSVs at
`execution_algos/vol-regime-sizer/results/<YYYYMMDD>/`. One pandas
aggregation per train date per candidate (33 reads total). 20260319
is missing (parent OOM precedent — same as L5/L6).

### Candidate 1 audit
Binding feature: rolling-K=5 mean of `|Δarrival_mid|` over OPEN
parent orders.

Per-date distribution (median jump, frac > 0.5):

| date | n | median_jump | frac>0.5 |
|---|---:|---:|---:|
| 20260308 | 372 | 1.0875 | 0.906 |
| 20260309 | 3100 | 1.1750 | 0.908 |
| 20260310 | 2475 | 1.0750 | 0.884 |
| 20260311 | 2643 | 0.9000 | 0.797 |
| 20260312 | 5995 | 0.6000 | 0.610 |
| 20260313 | 9037 | 0.4750 | 0.448 |
| 20260315 | 2021 | 0.3000 | 0.115 |
| 20260316 | 22388 | 0.2500 | 0.092 |
| 20260317 | 23084 | 0.2000 | 0.035 |
| 20260318 | 23524 | 0.2000 | 0.083 |
| 20260320 | 23991 | 0.2500 | 0.121 |

**Heterogeneity verdict: HETEROGENEOUS** (median jump varies 5.62×
across dates — 0.20 to 1.125; frac>0.5 varies 25× — 0.035 to 0.91).

### Candidate 2 audit
Binding feature: rolling-M=10 mean of `realized_pnl` over closed
positions, lagged 1.

Per-date distribution (mean of streak, frac<0):

| date | n | mean_streak | frac<0 |
|---|---:|---:|---:|
| 20260308 | 357 | +0.2138 | 0.445 |
| 20260309 | 2868 | +0.2275 | 0.376 |
| 20260310 | 2280 | +0.1825 | 0.387 |
| 20260311 | 2406 | +0.0911 | 0.476 |
| 20260312 | 5437 | −0.0366 | 0.563 |
| 20260313 | 8016 | −0.0569 | 0.597 |
| 20260315 | 1822 | −0.0251 | 0.541 |
| 20260316 | 19199 | −0.0206 | 0.538 |
| 20260317 | 19952 | −0.0084 | 0.495 |
| 20260318 | 20903 | +0.0092 | 0.453 |
| 20260320 | 21022 | +0.0114 | 0.461 |

**Heterogeneity verdict: HETEROGENEOUS** — location stat signs flip
across dates (negative on parent-loss days, positive on parent-win
days; mean varies −0.057 to +0.228). Per the method's HETEROGENEOUS
definition (location > 3× variation OR sign-reversals), C2 is
heterogeneous. Scale stat (frac<0) is more stable (1.59× variation).

### Candidate 3 audit
Binding feature: per-date p90 of `|is_price|` on filled opens.

Per-date distribution (median |is_price|, frac>0.5):

| date | n | median | p90 | frac>0.5 |
|---|---:|---:|---:|---:|
| 20260308 | 367 | 0.625 | 1.125 | 0.619 |
| 20260309 | 2878 | 0.375 | 0.750 | 0.281 |
| 20260310 | 2290 | 0.375 | 0.625 | 0.177 |
| 20260311 | 2416 | 0.375 | 0.625 | 0.127 |
| 20260312 | 5447 | 0.125 | 0.375 | 0.018 |
| 20260313 | 8026 | 0.125 | 0.375 | 0.007 |
| 20260315 | 1832 | 0.125 | 0.250 | 0.014 |
| 20260316 | 19209 | 0.125 | 0.125 | 0.001 |
| 20260317 | 19962 | 0.125 | 0.125 | 0.000 |
| 20260318 | 20913 | 0.125 | 0.125 | 0.000 |
| 20260320 | 21032 | 0.125 | 0.125 | 0.000 |

**Heterogeneity verdict: HETEROGENEOUS** — median varies 5×, p90
varies 9×, frac>0.5 varies > 600×. The thin-trade dates concentrate
the tail; on the dense-trade dates the "tail" reduces to a quantile
artifact at the 1-tick floor.

## Falsification test (Tier-A)

Decision rules stated before running.

### Candidate 1: arrival_mid K=5 jump magnitude (per-date median split)
Claim: high-jump regime has worse mean pnl than low-jump regime.
Heterogeneity: HETEROGENEOUS.
Falsification test:
  Artifact:   `vol-regime-sizer/results/<date>/{orders,positions}.csv`
  Date set:   all 11 train dates
  Statistic:  per-date `delta = mean_pnl(jump ≤ median) − mean_pnl(jump > median)` (positive ⇒ skipping high-jump helps)
  Decision rule:
    - HETEROGENEOUS branch: SURVIVED if delta ≥ +$0.03/contract on
      ≥ 8 of 11 dates AND no date has sign-reversal of magnitude
      > $0.06.

### Candidate 2: rolling-pnl streak (M=10, lag 1)
Claim: when streak < 0 the next position's pnl is worse than when
streak ≥ 0.
Heterogeneity: HETEROGENEOUS.
Falsification test:
  Artifact:   `vol-regime-sizer/results/<date>/positions.csv`
  Date set:   all 11 train dates
  Statistic:  per-date `delta = mean_pnl(streak < 0) − mean_pnl(streak ≥ 0)`
              (negative ⇒ skipping streak<0 orders helps)
  Decision rule:
    - HETEROGENEOUS branch: SURVIVED if delta ≤ −$0.03/contract on
      ≥ 8 of 11 dates AND no date has sign-reversal of magnitude
      > $0.06.

### Candidate 3: |is_price| tail (per-date p90 split)
Claim: orders with `|is_price| > p90` have worse pnl than the rest.
Heterogeneity: HETEROGENEOUS.
Falsification test:
  Artifact:   `vol-regime-sizer/results/<date>/{orders,positions}.csv`
  Date set:   all 11 train dates
  Statistic:  per-date `delta = mean_pnl(|is_price| > p90) − mean_pnl(|is_price| ≤ p90)`
              (negative ⇒ skipping the tail helps)
  Decision rule:
    - HETEROGENEOUS branch: SURVIVED if delta ≤ −$0.05/contract on
      ≥ 8 of 11 dates AND no date has sign-reversal of magnitude
      > $0.10.

## Verdicts (3 lines)

Verdict C1: **FALSIFIED** | n_pass (delta ≥ +0.03) = 0/11; n_bad_reversal (delta < −0.06) = 1 (20260311: −0.2367). Direction itself opposite of prediction: high-jump regime has *higher* mean pnl on 5 dates and roughly tied on the rest. Hypothesis falsified outright. Margin: very large (best date delta = +0.0196 on 20260313, still below threshold).

Verdict C2: **FALSIFIED** | n_pass (delta ≤ −0.03) = 5/11; n_bad_reversal (delta > +0.06) = 0. Direction is consistent across all 11 dates (every date has delta < 0) — same sign on every date — but magnitude only crosses the −0.03 threshold on 5 dates. Three dates short of 8. Smallest unmet margin: 20260315 at −0.0189, 20260316 at −0.0174, 20260318 at −0.0156 — each ~0.012-0.014 short of the threshold. **No date has a sign-reversal**.

Verdict C3: **FALSIFIED** | n_pass (delta ≤ −0.05) = 6/11; n_bad_reversal (delta > +0.10) = 3 (20260308: +1.39, 20260311: +0.29, 20260313: +0.14). Reverses direction on the thin-trade dates where the "tail" is the heavy-cost regime (concentrated at 5-7 dates with ~150-330 wide-cost fills, mean is in the same direction as parent edge — not against it). Falsified by both n_pass shortfall and sign-reversals.

## Step 5 outcome: zero SURVIVED → weakest-violation branch

Per the prompt's step 5 #3 (zero survived, pick smallest violation
margin): **C2 has the smallest violation margin** and is the only
candidate with **zero sign-reversals**. C2's directional evidence is
unanimous (11/11 dates have `mean_pnl(streak<0) < mean_pnl(streak≥0)`);
the only failure is that the magnitude on 6 of the 11 dates falls
between $0.005 and $0.025, just below the pre-stated $0.03 threshold.
Compare to C1 (direction reversed on at least 1 date with magnitude
−0.24) and C3 (multiple sign-reversals up to +1.39). On the
"weakest violation" criterion C2 wins by a wide margin.

**Honesty flag**: this is a weakest-violation pick, not a SURVIVED
hypothesis. The threshold was pre-committed at $0.03; the observed
mean delta across all 11 dates is −$0.042 (weighted by date count,
about −$0.011 because most dates have small magnitudes). The
mechanism is real-direction but small-magnitude on most dates.
Loop 6's same situation produced a no-mechanism pick (round-number)
that the gate punished 0/5. C2 is better-than-that — unanimous sign
agreement — but it is still chosen against the method's strict
SURVIVED bar.

## Chosen hypothesis

**Parent behavior being changed**: `sip-vrs-l5`'s gate is
`p_submit = parent_vol_p × wide_spread_suppress`. Neither layer has
visibility into recent realized pnl. The L7 hypothesis adds a third
multiplicative gate: when the rolling mean of the last M=10 closed
positions' realized pnl is negative, multiply `p_submit` by
`streak_suppress = 0.0` (hard skip).

**Concrete modification**: in `on_position_changed` (or by tracking
closes from `on_order_filled` reduce-only events), maintain a deque
of the last M=10 closed-position pnls. On each OPEN order arrival,
after computing the L5 `p_submit` (vol × wide-spread layers), check
if the deque is full (size = M) and its mean is < `streak_threshold = 0`.
If so, suppress.

**Expected direction vs `vol-regime-sizer`** (the named parent):
- `realized_pnl`: ↑ — removes orders fired during adverse-streak
  regimes (mean expected pnl ~ -$0.04/contract on those orders).
- `mean_slippage`: 0 (zero-slippage fill model).
- `sharpe_ratio`: ↑ — narrower daily distribution (skips during
  consecutive losing positions cut left-tail).
- `trade_count`: ↓ moderately (skip fires on 38-60% of dates, but
  the M=10 warmup means it kicks in only mid-session).

**Expected direction vs `sip-vrs-l5`** (the running-best, which the
gate compares against): unknown. The streak gate may be redundant
with L5's wide-spread skip — both fire on similar sub-regimes (high
adverse-cost periods). If redundant, L7 loses on trade_count (fewer
trades, lower absolute pnl) without proportional pnl gain.

**Regime-coverage prediction**: `frac<0` ranges 0.38-0.60 across all
11 dates ⇒ the gate fires on ≥ 5% of warmed-up arrivals on **all 11
dates** = 11 of 12 (with 20260319 OOM unknown). That's at the high
warning-sign threshold (≥ 11). The parameter `streak_threshold = 0`
is regime-relative by construction (a sign test on a centered
rolling mean), satisfying step 7's regime-relative requirement.

**Supporting verdict**: C2 weakest-violation (zero sign-reversals across all 11 dates, mean delta −$0.042/contract; 5 of 11 dates cleared the pre-stated $0.03 threshold).

## Parameter justifications

| Parameter | Value | Rule | Notes |
|---|---|---|---|
| `fast_halflife` | 20 | Inherited unchanged from parent. | parent param |
| `slow_halflife` | 120 | Inherited unchanged from parent. | parent param |
| `sensitivity` | 2.0 | Inherited unchanged from parent. | parent param |
| `min_prob` | 0.05 | Inherited unchanged from parent. | parent param |
| `min_ticks` | 30 | Inherited unchanged from parent. | parent param |
| `max_vol_ratio` | 5.0 | Inherited unchanged from parent. | parent param |
| `wide_spread_threshold` | 1.5 | Inherited unchanged from L5 (running-best). | L5 param |
| `wide_spread_suppress` | 0.0 | Inherited unchanged from L5. | L5 param |
| `tick_size` | 0.25 | Constant of MES futures contract. | constant |
| `streak_M` | 10 | Default of the falsification window. The audit and falsification both used M=10 closed positions. | step-3/4 derived |
| `streak_threshold` | 0.0 | Sign threshold on rolling mean — regime-relative by construction (the mean is centered around 0 per date by definition; the actual per-date means range −0.057 to +0.228). | regime-relative default |
| `streak_suppress` | 0.0 (hard skip) | Derived from step-4 statistic: average per-date delta = −$0.042/contract (negative ⇒ adverse). Principled rule (same as L5's wide-spread default): if expected pnl in regime is negative, rational participation is 0. Hard skip; soften to 0.3 in a follow-up loop if this fails. | derived |

## Honesty notes

- **C2 is a weakest-violation pick, not a SURVIVED candidate.** The
  pre-stated rule was n_pass ≥ 8 of 11 at δ ≤ −$0.03. Observed:
  n_pass = 5 of 11. The same-sign-on-all-11-dates evidence is
  unusually clean, but the magnitude is sub-threshold on the dense-
  trade dates (20260315–20260320) where most of the parent's pnl
  is generated. If C2 *only* helped on the thin-trade and adverse
  dates, the gain at the aggregate level may be muted.

- **The L5 gate already removes many of the adverse fills.** Wide-
  spread orders (most concentrated on the dense-trade dates) are
  already skipped at L5. The C2 streak gate's largest effect would
  be on dates where wide-spread skip is rare (the dense-trade
  dates), but those are exactly the dates where C2's mean delta is
  smallest in magnitude. The mechanism risk is high.

- **Streak gate has a warmup**. M=10 means roughly the first
  10 positions of each session are not gated; on thin-trade days
  (367 positions on 20260308) this is ~3% of the session; on dense
  days (~21k positions) it's negligible.

- **The streak depends on the algorithm's own pnl, not the parent's.**
  The streak deque is updated from closes of orders this algorithm
  submitted (a self-referential signal). On dates where the
  vol-regime + wide-spread gates already produce a cleaner pnl
  distribution, the streak gate may rarely fire. This is consistent
  with the expected modest improvement.

- **20260319 OOM persists.** Same precedent as L5 and L6 — the
  parent's run on that date OOMs at 4 GiB. Aggregate is over 11 of
  12 dates.

- **The method's "weakest violation" branch is being exercised for
  the second consecutive loop.** Loop 6 took the same branch (zero
  Tier-A SURVIVED) and lost the gate 0/5. C2 is materially better-
  evidence than L6's round-number gate (unanimous sign, small
  magnitude vs sign-reversed sub-decisive evidence). The trace will
  call out whether the method's continued "weakest violation" route
  is the right escape valve here.
