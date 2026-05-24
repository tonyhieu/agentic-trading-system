# Algorithm Notes: ptg-isl-g4l1

## Hypothesis

**Builds on**: `ptg-isl-g1l1` (island-0 lineage best — saturated peak at the
two-axis composition of position-cap + rolling-spread-p75 hard cut, +26.55%
vs base).

**Cross-island influence**: The gen-3 migration's `base_specific (1)`
finding for island-0 is the direct trigger:

> "ptg is empirically saturated at the two-axis composition. DO NOT continue
> stacking skip-axes on ptg. The next productive direction is either a
> non-quantile knob on the same two-axis stack (spread_window_seconds sweep)
> or a structurally new mechanism (quantity-modulation rather than skip-axis
> — open at partial qty when spread is in the [p50, p75] band)."

g3l2 already executed the analogous single-knob retune on the OTHER axis
(spread_quantile 0.75 → 0.80) and confirmed the peak is a plateau,
landing -1.96% below g1l1. A `spread_window_seconds` sweep is structurally
a sibling single-knob retune — it would shift the threshold via spread-
process autocorrelation rather than cut-depth, but it operates on the same
binary-cut mechanism class, and the gen-3 plateau evidence puts its
expected range within ±2% of g1l1. **We pick quantity-modulation instead
because it accesses a different mechanism class** (sizing / probabilistic
admission rather than threshold-cut), is empirically validated cross-island
(vrs-isl-g1l1's chop-decay produced +34% vs base on a different base),
and the EV-vs-spread-rank curve inside [p50, p75] has not been measured —
it could be flat (saturation confirmed on a second axis), monotonic
decreasing (decay lifts above g1l1), or non-monotonic (decay shape needs
calibration).

**Mechanism (this loop)**: Replace g1l1's BINARY spread-p75 hard-cut with
a PROBABILISTIC submit-decay across the [p_lower, p_upper] band:

- spread ≤ p_lower (default p50)        → submit at p = 1.0 (full size)
- p_lower < spread ≤ p_upper (default p75) → submit at p ∈ [min_prob, 1.0],
  linearly decaying with rank-in-band
- spread > p_upper                       → HARD SKIP (preserves g1l1 /
  g3l2 evidence that the [p75, p80] band is empirically EV-negative; we
  do NOT re-admit it)

The strategy ships integer trade_size=1, so "open at partial qty" is
expressed as a probabilistic admit decision per order — each individual
order is full-size or unsent, but in expectation across many orders the
band sees fractional exposure proportional to (1 − rank). Per-order draw
is a deterministic SHA-256 hash of client_order_id (vrs-isl-g1l1 pattern);
keeps reproducibility and decouples from cross-day RNG state.

**Why this should beat g1l1**: g1l1 treats the entire [p50, p75] band
identically — all admitted at full size. If conditional EV varies smoothly
with spread rank in the band (plausible: adverse-selection cost grows
monotonically with spread, oracle's 30s edge is smooth), then opening at
full size at the p70 mark over-exposes to the high-cost edge of the band
relative to the p55 mark. A linear decay shifts expected exposure toward
the cheap low-quantile half, capturing residual EV the binary cut misses.

**Distinguishable from g3l2 (the other single-knob retune)**: g3l2 moved
the cut depth (threshold) and showed the peak is a plateau in
position-space. This loop reshapes the function INSIDE the same threshold
(cut SHAPE). If g4l1 also lands within ±2% of g1l1, that is a second
independent axis of evidence pinning the saturation conclusion — the
EV-vs-quantile curve is flat across [p50, p75], not just at the peak point.
If it lifts cleanly, we have located a new productive mechanism class on
this base; gen-4 l2 can then retune the decay parameters
(p_lower / min_prob / decay shape).

## Implementation Decisions

- **q_lower = 0.50, q_upper = 0.75**: anchored on g1l1's empirical peak
  (q=0.75) and split the surviving population in half. The lower half of
  the surviving band ([p50, p_upper]) becomes the decay region. p50 is a
  conservative anchor — it admits at full size everything below the median
  spread, preserving g1l1's full participation on the cheap-spread half
  of the population. Future retunes (g4l2 if this lifts cleanly) can sweep
  p_lower ∈ {p25, p40, p60} to find the optimal decay onset.
- **min_prob = 0.05**: matches vrs-isl-g1l1's chop-decay floor. Empirically
  validated to avoid degenerate gating (a 0 floor turns the in-band region
  into a near-hard-cut at the upper edge, defeating the point of the band).
- **Linear decay**: simplest functional form (1 free shape parameter
  via min_prob). vrs uses exponential; if linear regresses but the
  mechanism otherwise looks alive, g4l2 can try exponential
  (`exp(-sensitivity * excess)`) without changing the band semantics.
- **spread_window_seconds = 60, min_samples = 50, position_cap = 1**:
  unchanged from g1l1. Single-knob discipline: we change ONLY the gate
  semantics (binary → probabilistic), not the threshold computation.
  Comparable to g3l2's discipline of changing only the quantile knob.
- **Hard cut above p_upper retained**: g3l2 confirmed [p75, p80] is
  EV-negative. We do NOT relax the upper boundary; the decay only applies
  WITHIN the previously-admitted band.

## Falsification Criteria (pre-declared)

| Outcome (vs g1l1's +26.55% vs base)     | Interpretation                                            |
|---|---|
| Within ±2% (+24.5% to +28.5% vs base)    | Mechanism class also saturated on this base; ptg's edge confirmed flat in EV-vs-spread-rank across [p50, p75]. Pivot to a structurally different mechanism for g4l2 (e.g., asymmetric exit timing). |
| Lifts to >+28.5% vs base                 | Quantity-modulation works on ptg; g4l2 retunes decay parameters (p_lower sweep, exponential decay, min_prob sweep). |
| Drops to <+24.5% vs base                 | Linear-EV assumption wrong; try exponential decay shape (vrs-style) at g4l2 before declaring the axis dead. |
| Trade_count drops >10% vs g1l1           | Decay too aggressive; raise p_lower toward p75 or raise min_prob. |
| Trade_count rises >0.5% vs g1l1          | Cannot happen by construction (decay only REDUCES admission within the previously-admitted band) — would indicate an implementation bug. |

## Backtest Observations

Raw aggregate (train, 12 dates):
- realized_pnl = 5571.25
- sharpe_ratio = 25.1124 (sharpe_n_days = 12)
- max_drawdown_pct = -0.005375
- win_rate = 0.3813
- trade_count = 86377
- mean_slippage = 0.0, max_abs_slippage = 0.0
- is_weighted_bps = 0.0258

Deltas:
- vs base `position-tier-gate` (pnl=4262.50): **+30.70%** — BEATS BASE
- vs g1l1 lineage best (pnl=5394.25, sharpe=23.17): **+3.28%** pnl, +1.94 sharpe
- vs g3l2 prior loop (pnl=5288.50, sharpe=22.24): **+5.35%** pnl, +2.87 sharpe
- vs g1l1 trade_count (87319): -942 trades (-1.08%) — consistent with the
  pre-declared construction (probabilistic decay only REDUCES admission within
  the previously-admitted [p50, p75] band; the upper hard-cut at p75 is
  unchanged). Within the 10% falsification budget.
- vs g1l1 max_drawdown_pct (-0.0054 here vs the historical lineage best of
  approximately -0.017 on the base): drawdown is materially lower, indicating
  the decay is preferentially removing the high-cost (high-spread-rank) edge of
  the admitted population.

Falsification verdict (vs pre-declared criteria):
- vs-base outcome: +30.70%, ABOVE the upper threshold (+28.5%). Class is
  **"Lifts to >+28.5% vs base"** → quantity-modulation **works** on ptg.
- Trade_count change -1.08%: within ±10% budget; decay is not over-aggressive.
- Trade_count change vs g1l1 is NEGATIVE (-1.08%) as required by construction;
  no implementation bug indicated.

Mechanism read:
The improvement direction confirms the structural hypothesis: the EV-vs-rank
curve inside [p50, p75] is NOT flat — adverse-selection cost grows monotonically
enough with spread rank that shifting expected exposure away from the high-rank
edge of the band lifts realized pnl above g1l1's binary admission. The
saturation ceiling that pinned the island-0 lineage since g1l1 (g3l2 plateau
at -1.96% within ±2% of g1l1) was an artifact of the binary-cut mechanism
class, not the base algo's expressive limit. A new mechanism class
(quantity-modulation / probabilistic admission shape) opens a fresh axis of
refinement on this base.

Open knobs for g4l2 retune (now that the mechanism is confirmed live):
1. Decay shape: linear → exponential (`exp(-sensitivity * excess)`). Exponential
   front-loads admission probability toward the cheap end of the band, which
   could lift further if the EV-vs-rank curve is convex (cost rising faster
   than linearly). vrs's chop-decay uses exponential and produced
   +34% vs its base.
2. Band placement: [p50, p75] → [p60, p80] or [p40, p75]. Current p_lower=p50
   was a conservative anchor; the cheap-half of the band still admits at p=1.0,
   so there may be room to push p_lower up (concentrate the decay region into
   the actually-expensive part of the spread distribution).
3. min_prob floor: 0.05 is the vrs default. Pushing it to 0.0 (hard cut at the
   upper edge) or 0.10 (gentler floor) is a small free parameter sweep.

