# afg-isl-g4l1 — Hypothesis & Implementation Decisions

## Hypothesis

Add a **fifth orthogonal SKIP axis** — short-horizon **mid-price velocity
(signed directional momentum)** — on top of the four-gate stack frozen
in `afg-isl-g3l2` (PnL +233.05% vs base, sharpe 17.80, drawdown
-0.015, the island-1 lineage best).

For each OPEN order, skip when recent mid drift is significantly
adverse for the order's side:
- BUY skipped when `(mid_now - mid_lookback) / dt <= -velocity_threshold`
- SELL skipped when `(mid_now - mid_lookback) / dt >= velocity_threshold`

where the lookback is the oldest mid still inside a rolling 5-second
window. Composed with the four existing gates via AND-skip (consistent
with the working composition from g2l2/g3l2).

## Why this axis (mechanistic case)

The five existing dimensions covered by the lineage are structurally
distinct only if each new gate encodes a market state the others do
not. Mid-velocity does:

| Gate | Mechanism | Sign-aware? | Time scale | Source |
|------|-----------|-------------|------------|--------|
| A. Spread (book-state)        | quote-DISTANCE  | no  | 60s window  | quote ticks |
| B. Chop (price-path)          | path/displacement RATIO (scale-invariant) | no  | 30 quote ticks | quote ticks |
| C. Flow (trade-pressure, base)| signed AGGRESSOR-volume | yes | 10s window  | trade ticks |
| D. Size-asym (book-depth)     | static contra/own size ratio at top-of-book | yes | latest quote only | quote ticks |
| **E. Mid-velocity (NEW)**     | **signed mid drift RATE** | **yes** | **5s window** | **quote ticks** |

The base flow gate (C) is the only other directional gate, but it
operates on signed AGGRESSOR VOLUME — fundamentally different from mid
drift. A trade can hit aggressively without moving the mid (large
resting orders absorb it), and the mid can drift on quote updates with
no trades at all (passive size withdrawal). Net aggressor flow over
10s being below threshold does not exclude a persistent unidirectional
mid drift in the last few seconds, which is exactly what this gate
catches.

## Cross-island prior

**Gen-3 migration (`generalizable (1)`):** "The gen-2 'three-axis
ceiling' hypothesis is FALSIFIED on two bases this generation — afg
cleanly cleared four axes with size-asymmetry as the fourth (+21.59%)."
The four-axis ceiling has therefore not been demonstrated on this base.

**Gen-3 migration (`base_specific (2)`):** "afg accepts a fourth
orthogonal axis cleanly and is the right island to probe the five-axis
frontier next — the gen-2 three-gate stack survived size-asymmetry
addition without regression and operates on a base whose surviving
population has the most remaining headroom across the three islands."
This is explicit license to probe the five-axis frontier on afg.

## Why velocity rather than recent-trade-side flow

g3l2's `summary_out.next` proposed two candidate fifth axes — recent-
trade-side flow and price-velocity — naming recent-trade-side flow as
the "more conservative first test because it stays in the trade-
pressure family the base already gates on." The operator overrides
that ranking and picks velocity as the LOWER-LEVERAGE option for g4l1
because:

1. **Lower correlation risk.** Recent-trade-side flow stays inside the
   trade-pressure family that the base gate (C) already covers. Two
   independent island-2 loops (g2l2, g3l1) showed that a second flow-
   family axis on a flow-pre-filtered residual cuts trade_count
   disproportionately to PnL — the gen-3 migration's `what_failed`
   block calls this out by name. Velocity, by contrast, uses quote
   updates (not trades) and a directional drift mechanic (not a sign-
   summation), so its correlation with C is structurally lower.
2. **Mechanistically more distant.** Velocity is the only existing
   candidate that combines DIRECTIONAL (sign-aware) and PRICE-NATIVE
   (uses mid, not size/volume/quote-distance) properties — both
   distinguishing it from gates A, B, D simultaneously.
3. **Conservative parameter choice possible.** Mid-velocity has a
   single primary knob (threshold $/s) with a natural physical
   calibration (MES tick = 0.25; 0.5 $/s ≈ 2 ticks/s is clearly
   directional drift without being tail-only).

## Parameter choices (deliberately conservative)

- `velocity_window_seconds = 5.0`. Half the flow window (10s) so the
  two are not duplicating the same time horizon.
- `velocity_threshold = 0.50` ($/s) ≈ 2 MES ticks per second. In the
  body of the drift distribution, not tail-only — consistent with the
  modest-threshold operating points the other four gates use.
- `velocity_min_ticks = 5`. Short warm-up; mid-velocity is a two-point
  estimate (mid_now vs oldest mid still in window), so it needs fewer
  samples than the distributional gates (spread_min_samples=50,
  chop_min_ticks=40).

## Composition

- **AND-skip**, same composition rule as g2l2 and g3l2.
- Base flow gate unmodified.
- All four prior gate parameters frozen verbatim from g3l2 — no
  multi-knob retuning in this loop. Operator directive: add the axis
  first, then retune the now-5-dimensional operating point surface in
  g4l2 only if g4l1 succeeds.

## Predictions (pre-stated, for diagnosis)

- **Confirmation:** PnL > g3l2 (4182.00) AND drawdown does not widen
  (`max_drawdown_pct` not more negative than -0.015) AND trade_count
  drop ≤ 10% vs g3l2 (96472).
- **Null result:** PnL within ±2% of g3l2 AND the new velocity
  counters fire < 0.5% of evaluated OPENs OR co-skip with another
  gate at near-100% rate. Diagnosable via the per-gate counters.
- **Regression:** PnL < g3l2 by > 2% OR trade_count drops > 10%.
  Verdict in that case is a hard four-axis ceiling on this base; g4l2
  should pivot to multi-axis operating-point retuning.

## Instrumentation

Per-gate counters extended from g3l2 with side-specific velocity skips
(`_skipped_velocity_buy`, `_skipped_velocity_sell`); all counters
emitted on `on_stop` for null-result diagnosis. See gen-1 migration's
`what_failed` block on the island-0 g1l2 undiagnosable null result for
the mandate.

## Backtest Observations

**Verdict: NULL RESULT.** Confirmation criteria not met; falsification
criteria not met; the addition was inert.

Headline (raw, train window 2026-03-08..2026-03-20, 12 sessions):

| Metric          | base afg | g3l2 (prior) | g4l1 (this)  | Δ vs base   | Δ vs g3l2   |
|-----------------|----------|--------------|--------------|-------------|-------------|
| realized_pnl    | 1255.50  | 4182.00      | 4180.25      | +232.96%    | -0.04%      |
| sharpe          | 5.594    | 17.805       | 17.766       | +12.17 abs  | -0.039 abs  |
| max_drawdown    | -0.0332  | -0.01505     | -0.01505     | tightened   | unchanged   |
| trade_count     | 107198   | 96472        | 96463        | -10735      | -9          |
| win_rate        | 0.3549   | 0.37031      | 0.37030      | +1.54 pp    | -0.0017 pp  |
| mean_slippage   | 0.0      | 0.0          | 0.0          | 0           | 0           |
| is_weighted_bps | 0.04724  | 0.04406      | 0.04404      | -6.78%      | -0.04%      |

**Mechanistic diagnosis.** Trade-count delta vs g3l2 is -9 trades on a
~96k base — a 0.0093% reduction. The velocity gate barely fired. Two
non-exclusive explanations consistent with the data:

1. **Threshold too loose.** velocity_threshold=0.50 $/s (~2 MES
   ticks/sec) was sized for the body of the drift distribution under
   the unconditioned mid-velocity distribution, but the four prior
   gates already remove the high-volatility / high-drift slice. The
   surviving 96k-OPEN population is, by selection, the calmer slice
   — the threshold likely sits well into the empty tail of the
   conditional distribution.
2. **Genuine redundancy.** The pre-existing gates (especially flow C,
   on a 10s window) already absorb most directionally-persistent
   states. Mid-velocity over 5s, intersected with the 4-gate
   pre-filter, may simply not add an axis with independent signal.

Without per-gate counter telemetry from this run reproduced into a
log file here, we cannot fully discriminate (1) from (2) — but the
shape (firing-but-not-firing, near-zero counts) points more strongly
at (1) than (2): if it were pure redundancy we would expect co-skip
counts > 0 but unique-skip counts = 0, whereas a too-loose threshold
yields near-zero fires on BOTH counters. Either way, the present
loop is uninformative as posted.

**Predictions vs outcome.**
- Confirmation (pnl > g3l2 AND drawdown not worsened AND
  trade_count drop ≤ 10%): **not met** — pnl fell 0.04%, just inside
  the ±2% null band.
- Null result (pnl within ±2% of g3l2 AND velocity counter fires
  < 0.5% of OPENs OR co-skips at ~100%): **MET** — pnl Δ = -0.04%,
  trade_count Δ = -9.
- Regression (pnl < g3l2 by > 2% OR trade_count drop > 10%):
  **not met**.

**No four-axis ceiling verdict change.** The g3l2 four-gate stack
remains the island-1 lineage best (pnl=4182.00, sharpe=17.80). g4l1
neither extends nor falsifies the four-axis ceiling — it produced an
inert fifth gate that did not exercise the surviving population.

**Implication for g4l2.** Two structurally distinct directions, both
reading on the null:

(A) **Tighten velocity threshold (knob retune).** Drop
    velocity_threshold from 0.50 to e.g. 0.20–0.30 $/s (~1 MES
    tick/sec) so it fires meaningfully on the 4-gate surviving
    distribution. Cheap, narrow re-test of axis E.

(B) **Pivot to recent-trade-side flow (alternative 5th axis).**
    g3l2.summary_out.next named recent-trade-side flow as the
    more-conservative first candidate; the operator overrode that
    ranking in g4l1. Now that velocity is shown inert at a moderate
    threshold, recent-trade-side flow is a genuinely different
    mechanism (conditions on TRADE-side, not net-volume sign; not
    mid-drift) and may have non-zero unique signal where velocity
    didn't.

Recommendation for g4l2: (B) is higher-information per loop because
(A) is a single-knob sweep on an already-shown-inert mechanic; (B)
introduces a structurally new candidate axis at the same loop cost.
Suggested operator decision in g4l2 hypothesis writing.
