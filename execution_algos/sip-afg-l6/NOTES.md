# Algorithm Notes: sip-afg-l6

## Step 1 — Context Summary

Most-recently-kept loop is L5 (`sip-afg-l5`, +3.30% vs base). Its
structural change: replaced binary `_position_flat` (forced
unconditional submit after any skip) with graduated `_skip_streak`
counter that applies `flow_threshold * relaxation_factor` on
`_skip_streak == 1` and force-submits at `_skip_streak >= 2`. Two
NEW numeric parameters introduced: `relaxation_factor = 1.5` and
`max_consecutive_skips = 2`. Both flagged by the L5 NOTES.md
(Implementation Decisions and Concerns) as armchair / not
EDA-calibrated; the L5 "Suggested next attempt" even explicitly
proposes measuring |net_flow| at the next opening order's evaluation
time following a base skip to inform `relaxation_factor`.

---

## Inherited Parameters

Parameters NEW or CHANGED in `sip-afg-l5` vs the base
`aggressor-flow-gate`:

| name                    | current value | controls                                                                                          | calibrated by data? |
|-------------------------|---------------|---------------------------------------------------------------------------------------------------|---------------------|
| `relaxation_factor`     | 1.5           | Multiplier on `flow_threshold` (=2.0) at `_skip_streak == 1`. Effective threshold = 3.0 contracts. | NO (intuition; L5 NOTES.md → Implementation Decisions explicitly flags as armchair) |
| `max_consecutive_skips` | 2             | Hard cap on consecutive skips before force-submit.                                                | NO (intuition; L5 NOTES.md → Implementation Decisions explicitly flags as not EDA-calibrated) |

Parameters inherited UNCHANGED from base (NOT eligible for this loop's
calibration since the method targets parameters *introduced* by the
kept algorithm — its structural axis):

- `window_seconds = 10.0` (inherited from base)
- `flow_threshold = 2.0` (inherited from base)

Two uncalibrated parameters → proceed to Step 3.

---

## Calibration Target

**Chosen parameter**: `relaxation_factor`.

**Selection rationale**: between the two new parameters,
`relaxation_factor` directly governs the firing rate of the *new*
mechanism (streak==1 re-evaluation). `max_consecutive_skips` only
kicks in *after* `relaxation_factor` has already gated two in a row,
so its activation rate is a strictly smaller subset of
`relaxation_factor`'s firing rate. The firing-rate parameter is
`relaxation_factor`.

**Measurement**: For each "base skip" event on a train date, capture
the `|net_flow|` at the next oracle-cadence order arrival moment
(1 second later by `signal_interval_seconds = 1.0`). The distribution
of those values directly tells us what threshold (= `flow_threshold *
relaxation_factor` = `2.0 * relaxation_factor`) sits at what
percentile.

- Current value `relaxation_factor = 1.5` → effective threshold = 3.0.
  Current firing rate = empirical Pr(|next_net_flow| >= 3.0 | prior
  skip).
- Calibrated value = the `relaxation_factor` such that the effective
  threshold (`2.0 * relaxation_factor`) sits at the pre-committed
  target firing-rate percentile of the |next_net_flow| distribution.

**Pre-committed target firing rate** (in [0.05, 0.50]): **0.30**.

Justification (one sentence, pre-EDA): the cascade-policy axis
demonstrably works at +3.30% under untuned firing, and the mechanism's
value comes from selective binding — too-low (~0.10) reduces it back
toward the base's `_position_flat` regime (re-entries always submit),
while too-high (~0.60) approaches the opposite extreme of disabling
re-entry; 0.30 keeps the gate firing on roughly the adverse third of
post-skip cases while letting the borderline two-thirds through.

---

## EDA Findings

**Dates loaded**: 20260309, 20260311 (both inside `data_window.train`;
no test data touched).

**Mechanics replayed**: 1Hz synthetic arrival stream; signed
aggressor-flow deque over the trailing 10s window matching the base
algorithm exactly; worst-case adverse side at each evaluation;
forced re-entry after each base skip (`_position_flat = True`)
matching base.

**Volumes**:

| date     | trade ticks | synthetic arrivals | non-forced evaluations | base skips | post-skip next-arrival samples |
|----------|------------:|-------------------:|-----------------------:|-----------:|-------------------------------:|
| 20260309 |      12,663 |             86,372 |                 75,855 |     10,516 |                         10,516 |
| 20260311 |       9,818 |             86,349 |                 77,369 |      8,979 |                          8,979 |
| **total**|             |                    |                        |   **19,495** |                       **19,495** |

Base-skip rate of evaluated orders: ~12-14% per date (matches the
documented ~22% global skip rate after accounting for forced re-entry
arrivals being excluded from the "evaluated" denominator).

**Distribution of |next_net_flow| (one-second-later) conditional on a
base skip** (units: contracts of net signed aggressor flow over a
trailing 10s window):

| percentile | value |
|------------|------:|
| mean       | 6.12  |
| p10        | 2.0   |
| p25        | 2.0   |
| p50        | 3.0   |
| p70        | 5.0   |
| p75        | 6.0   |
| p80        | 7.0   |
| p90        | 12.0  |
| p95        | 21.0  |

**Current value's firing rate** (effective threshold = 3.0):
`Pr(|next_net_flow| >= 3.0) = 0.6043` — the streak==1 relaxed gate
fires on **60.4%** of post-skip arrivals at `relaxation_factor = 1.5`.
This is far above the 0.30 target.

**Calibrated value**:
- target firing rate 0.30 → 70th percentile of |next_net_flow| = 5.0.
- calibrated effective threshold = 5.0 contracts.
- **calibrated `relaxation_factor = 5.0 / 2.0 = 2.5`** (vs current 1.5).

**Survival criterion**: `|2.5 - 1.5| / 1.5 = 66.7%` ≫ 10% → PASS,
proceed to Step 5.

**Interpretation of the L5 outcome through this lens**: the L5
`relaxation_factor = 1.5` was firing the relaxed gate on ~60% of
post-skip orders. That means the L5 mechanism is closer to "always
gate post-skip arrivals" than to "selectively gate the worst ones."
The +3.30% pnl gain from L5 came from the cascade-policy axis being
active at all (vs base's forced re-entry), not from any careful
selection — the gate was always binding when given the chance. Moving
to `relaxation_factor = 2.5` shifts the algorithm toward selective
binding: only the strongly-adverse 30% of post-skip arrivals continue
to be gated, while the borderline 70% are submitted. This is the
calibrated form of the same mechanism.

---

## Hypothesis (final)

**Mechanism**: Identical to `sip-afg-l5` except parameter
`relaxation_factor` changes from `1.5` to `2.5`. The graduated
`_skip_streak` counter remains; `flow_threshold = 2.0` and
`max_consecutive_skips = 2` are unchanged. At `_skip_streak == 1`
the effective threshold becomes `2.0 * 2.5 = 5.0` (was 3.0). At
`_skip_streak == 0` and reduce-only and warm-up, behavior is
identical to L5.

**Inefficiency exploited**: The L5 `relaxation_factor = 1.5`
effective threshold (3.0 contracts) fires on **60.4%** of post-skip
arrivals (Step 4 EDA). The L5 cascade policy was designed for
*selective* re-firing on the worst post-skip cases but is in fact
binding on the majority of them — closer to "always gate" than
"selectively gate." Moving the effective threshold to 5.0 contracts
lands the firing rate at the pre-committed 30% target — the gate now
binds only on the strongly-adverse top-third of post-skip arrivals
and submits the borderline two-thirds.

**Why it survives costs**: Quantity invariant preserved (only
submit/skip; never modify quantity). `top_of_book_only`,
`participation_cap`, `intraday_flat` all preserved because the
change is purely gate-internal. No new structural mechanism; only
one numeric parameter changes; no other parameters touched.
`mean_slippage` should remain 0.0 in the zero-fill-cost model.

**Quantitative anchor**: `relaxation_factor = 2.5`, derived as
`effective_threshold_at_p70 / flow_threshold = 5.0 / 2.0`, where
p70 is the 70th percentile of the empirical |next_net_flow|
distribution over 19,495 post-skip samples across two train dates
(20260309, 20260311). No other numeric parameter changes.

**Predicted outcome** (directions, anchored to the firing-rate shift
from 0.6043 → 0.30):

- `trade_count`: **expected to rise** vs `sip-afg-l5`. Mechanism:
  L5's relaxed gate currently fires at 60.4% of post-skip arrivals;
  the calibrated gate fires at 30%, so ~30 pp more post-skip
  arrivals submit. Estimate: L5 had ~78,442 trades on the comparable
  11-date subset vs base's 87,760 (=9,318 trade gap). The post-skip
  population per the EDA is ~19,495 across 2 dates → ~120k across
  12 dates. Reducing the relaxed-gate firing rate from 0.60 to 0.30
  recovers roughly `(0.60 - 0.30) * (post-skip arrivals) ≈ 36k`
  arrivals scaled crudely to 12 dates, but most "would-be skipped"
  orders feed back into the streak counter (some become future
  post-skip arrivals), so the realised increase is bounded by the
  L5↔base gap (9,318). Predict `trade_count` in roughly
  `[82,000, 86,000]` — between L5 and base.
- `realized_pnl`: **direction ambiguous; expected slight rise** if
  the L5 gate's firing on borderline post-skip cases was net
  P&L-positive (selecting too aggressively, losing recoverable
  profits), **expected slight fall** if those borderline cases were
  P&L-negative on average (L5 was selecting them correctly and we
  are now over-submitting). The EDA cannot tell us this directly
  — it only validates that the gate is too aggressive *relative to
  the pre-committed target*. The pre-committed target (0.30) is
  itself an unverified normative choice. **Best-estimate direction:
  slight rise** (the L5 NOTES.md "Suggested next attempt" explicitly
  hypothesised this).
- `mean_slippage`: **unchanged at 0.0** (zero-fill-cost model;
  routing unchanged).
- `sharpe_ratio`: **direction tied to pnl**. If pnl rises and
  per-trade variance does not blow up (more trades → more
  diversification denominator), sharpe should rise modestly.
- `max_drawdown_pct`: **roughly unchanged or slightly worse** —
  more borderline post-skip submits means more exposure during
  adverse-flow moments, potentially deepening intraday drawdowns
  marginally.

**Falsifier** (ONE backtest result that invalidates the
calibration): if `trade_count` is within ±2% of `sip-afg-l5`'s
78,442 — i.e. < 80,000 — then the relaxed gate at threshold=5.0
either rarely fires the new "submit instead of skip" path (the
firing-rate prediction is empirically off by an order of magnitude
in the live mechanism vs the EDA) OR the streak-state interaction
in the live algorithm differs from the offline simulation in a way
the EDA missed. Either way the calibration measurement did not
match the running mechanism. (Tighter falsifier than "P&L falls":
P&L-direction is conjectural and noise-prone at the +/-3% scale
the L5 mechanism operates on; trade_count is a clean function of
the gate firing rate.)

---

## Implementation Decisions

- **Only `relaxation_factor` changes**: `flow_threshold`,
  `window_seconds`, `max_consecutive_skips` all unchanged from L5.
  This keeps attribution clean — any backtest delta is attributable
  to the firing-rate shift on the streak==1 re-evaluation alone.
- **Code: structural copy of L5 with the parameter default
  changed**. Class names mirror L5 (`SipAfgL6Algorithm` /
  `SipAfgL6Config`). All other logic — deque maintenance, reduce-only
  bypass, force-submit at streak >= max, warm-up handling, look-ahead
  guarantees — copied verbatim from L5.
- **EDA artifact retained**: `eda_calibrate_relaxation.py` and
  `results/eda-calibration.json` committed so the next critic can
  re-derive (and the next loop can extend the measurement to
  additional dates without re-deriving the protocol).
- **Symmetric design preserved**: both BUY and SELL gates apply the
  same threshold and relaxation rule (no side-asymmetry introduced).
- **Constraint compliance**: quantity invariant preserved;
  `top_of_book_only`, `participation_cap`, `intraday_flat` all
  preserved because the change is purely gate-internal.

**Concerns**:
- The EDA used the *worst-case adverse side* at each arrival
  (BUY-gate fires on net <= -2.0; SELL-gate fires on net >= 2.0).
  This is the maximum possible base-skip rate. The live algorithm's
  oracle-driven order side may not always pick the worst-case side,
  so the live post-skip-arrival count may be lower than the EDA's
  19,495 figure. This does NOT change the *conditional* distribution
  (the calibrated threshold), but it does mean the trade_count
  prediction's magnitude could be smaller than the [82k, 86k] band.
- 2 dates is the spec minimum. The |next_net_flow| distribution
  may have date-to-date variability; the calibrated value is the
  pooled p70 estimate, which is a reasonable choice but not the only
  valid one.
- The pre-committed target firing rate (0.30) is a normative choice.
  If the optimal firing rate is actually 0.15 or 0.45, the live
  realized_pnl could move opposite the predicted direction. The
  method's value is that it makes this choice *explicit and
  measurable* rather than burying it in an unjustified parameter.
