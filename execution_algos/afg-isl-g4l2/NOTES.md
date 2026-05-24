# afg-isl-g4l2 — Island-1, Generation 4, Loop 2

## Hypothesis

**Targeted change**: Drop the signed mid-price velocity axis added in
afg-isl-g4l1 (NULL RESULT — PnL inside ±2% null band vs g3l2, only 9
fewer trades on a ~96k base) and instead add **recent-trade-side flow**
as the fifth orthogonal SKIP axis on top of the afg-isl-g3l2 four-gate
stack (spread + chop + base-flow + size-asymmetry; the island-1 lineage
best at PnL +233.05% vs base, sharpe 17.80).

**Why this axis, why now**

g4l1's own `summary_out.next` explicitly preferred this loop's direction
over re-tuning the velocity threshold:

> "(B) PIVOT to recent-trade-side flow (alternative 5th axis) — the
> candidate g3l2 originally named as more conservative, structurally
> different from velocity (conditions on TRADE-side, not mid-drift) and
> from base flow C (TRADE-side, not net-volume sign). … (B) is higher
> information per loop because (A) is a single-knob sweep on an
> already-shown-inert mechanic at moderate threshold, whereas (B)
> introduces a structurally new candidate axis at the same loop cost."

Gen-3 migration's `base_specific` (2) said:

> "afg accepts a fourth orthogonal axis cleanly and is the right island
> to probe the five-axis frontier next — the gen-2 three-gate stack
> survived size-asymmetry addition without regression and operates on a
> base whose surviving population has the most remaining headroom across
> the three islands."

g3l2 confirmed this for axis 4 (size-asymmetry, +21.59% vs g2l2). g4l1
demonstrated the headroom is NOT accessible via a slow-window
quote-derived velocity mechanic at 5s / 0.50 $/s — but that null does
not rule out a DIFFERENT mechanic; it specifically falsifies the
velocity axis.

**Why "recent-trade-side flow" is structurally distinct from base flow C**

The base aggressor-flow gate (axis C, frozen from base afg) uses **signed
net VOLUME over a 10-second window** with an ABSOLUTE contract threshold
(2.0). The new axis E differs along THREE structural dimensions
simultaneously, so the two trade-pressure axes are NOT redundant in the
mechanical sense the gen-3 migration warned about:

1. **Time horizon**: 1.5s rolling window vs base's 10s — captures very
   recent aggressor pressure that is too short-lived to materially
   shift the 10s net-volume calculation. A 1.5s burst of 5 seller-
   aggressor prints (typical 0.5–2 lot each, ~3–8 contracts total)
   will dominate the dominance ratio but barely register in the 10s
   net flow if the prior 8.5s was balanced.
2. **Aggregation mechanic**: COUNT of trade-side dominance (how many of
   the last N trades came in on which side), not NET SIGNED VOLUME.
   Two one-lot seller-aggressor prints contribute the same dominance
   signal as one two-lot seller-aggressor print — the size weighting
   is the base's mechanic, not this one's.
3. **Threshold style**: a RATIO (≥ 70% of informative recent trades on
   the contra side) rather than an absolute volume threshold, so the
   gate is self-normalizing across high- and low-volume periods (the
   base flow gate's 2.0-contract threshold becomes less informative
   when typical short-window prints are sub-contract or burst above 10).

**Operating point (pre-stated)**

  - `recent_window_seconds = 1.5` — middle of g4l1.next's recommended
    "1-2s" band; well below the 10s base flow window.
  - `recent_min_trades = 5` — warm-up: gate only fires when at least 5
    informative trades are in the window (guards against thin-print
    false positives in quiet periods).
  - `recent_dominance_ratio = 0.70` — ≥70% contra-side share to skip
    (informative but not absurdly strict; a 5-trade window at 4-of-5
    contra is the minimum-density firing case at 0.80, so 0.70 admits
    7-of-10, 14-of-20, etc. — meaningful one-sided bursts).

All g3l2 parameters preserved verbatim (no retuning of axes A–D).

**Pre-stated falsification criteria**

  - **Confirmation**: PnL > g3l2 (4182.00) AND drawdown does not widen
    AND trade_count drop ≤ 10%. Strong confirmation: PnL > +2% vs g3l2.
  - **Null** (defined ex-ante): metrics inside the ±2% null band vs
    g3l2 AND the new gate fires <0.5% of OPEN evaluations OR co-skips
    with another gate at near-100% rate. If null fires, the four-axis
    stack is the empirical ceiling for this island AND this combination
    of axes; gen-4 migration should flag whether the five-axis frontier
    is closed or whether a yet-different fifth axis (volume-burst,
    time-of-day) remains.
  - **Regression**: PnL < g3l2 by > 2% OR trade_count drops > 10% —
    the recent-trade-side axis is mechanically redundant with axis C
    (base flow), and the right next direction is operating-point
    retuning of axes A–D, not further fifth-axis exploration.

## Implementation Decisions

- Start from `execution_algos/afg-isl-g3l2/execution_algorithm.py` (the
  4-axis WINNER), NOT from g4l1 (which has the inert velocity axis).
  This drops the inert axis cleanly without re-tuning anything that was
  working.
- Maintain a SEPARATE deque (`_recent_deque`) for the recent-side count
  signal, independent of the base `_flow_deque`. The two structures must
  not share state because (a) they have different window lengths
  (1.5s vs 10s), and (b) the recent-side deque stores side codes
  (+1/-1/0) while the base deque stores signed volumes — keeping them
  separate also keeps the COUNT vs VOLUME mechanic isolation explicit
  in the data layout.
- O(1)-amortized prune: track per-side running counts
  (`_recent_buy_count`, `_recent_sell_count`) and decrement them on
  prune so the gate's dominance check is O(1) per order. The total
  recent-deque entries fit comfortably (1.5s × typical 10–100 trades/s
  ≈ 15–150 entries).
- NO_AGGRESSOR prints are appended to the recent deque so they age out
  correctly, but they do NOT contribute to either side's count — the
  dominance ratio uses (buy_count + sell_count) as the denominator (NOT
  total deque length), so the gate measures dominance among
  *informative* recent trades only.
- Composition: binary AND-skip (consistent with g3l2's working
  four-gate composition); gate E fires after gates A–D have passed,
  preserving the established skip ordering for diagnostic
  interpretability.
- Quantity invariant preserved; anti-cascade contract preserved; per-
  gate instrumentation extended with `_skipped_recent_buy` and
  `_skipped_recent_sell`.

## Backtest Observations

**Raw metrics (12-date train aggregate)**
  - realized_pnl     = 4155.50
  - mean_slippage    = 0.0
  - sharpe_ratio     = 17.6835
  - max_drawdown_pct = -0.015475
  - win_rate         = 0.36991
  - trade_count      = 96,283
  - is_weighted_bps  = 0.04422

**Deltas**
  - vs base afg (1255.50):  pnl +231.00%, slippage +0.0%
  - vs prior g3l2 (4182.00, 4-axis winner):
      pnl    -0.63%  (INSIDE the pre-stated ±2% null band)
      sharpe -0.121 absolute (17.68 vs 17.80)
      trade_count -189 (-0.20%) — gate E DID fire (more than g4l1's -9),
                                 but the trades it removed were
                                 net-neutral-to-slightly-negative EV
      max_dd  -0.015475 vs -0.015050 (drawdown WIDENED by 0.04pp —
                                     pre-stated confirmation criterion
                                     was "drawdown does not widen")
      win_rate unchanged within rounding
  - vs g4l1 (4180.25):  pnl -0.59% — same null band

**Pre-stated falsification outcome: NULL (mostly) / WEAK REGRESSION**
  PnL inside the ±2% null band → null per the pre-stated criterion.
  However, max_dd widened slightly (0.04pp), violating the secondary
  confirmation criterion "drawdown does not widen". This is not a
  PnL regression — it is a null result with a tiny drawdown footprint.
  The recent-trade-side flow axis at (1.5s, 5 min trades, 0.70
  dominance ratio) did fire enough to remove 189 trades, but the
  removed slice carried near-zero net EV — exactly the redundancy
  pattern gen-3 migration warned about between axis E (recent-trade-
  side COUNT) and axis C (base trade-flow VOLUME). The hypothesis
  that the three structural differences (1.5s vs 10s window, COUNT
  vs VOLUME, RATIO vs ABSOLUTE) would yield mechanically orthogonal
  information IS FALSIFIED on the 4-gate-conditioned surviving
  population.

**Combined evidence across g4l1 + g4l2**
  Two structurally distinct 5th-axis candidates have now produced
  null/near-null results on top of the g3l2 4-axis stack:
    g4l1: signed mid-price velocity (5s, 0.50 $/s)
          → pnl -0.04% vs g3l2, 9 fewer trades (gate barely fired)
    g4l2: recent-trade-side flow count (1.5s, 0.70 ratio)
          → pnl -0.63% vs g3l2, 189 fewer trades (gate did fire,
                                                   removed neutral EV)
  These two axes were chosen specifically to be structurally
  orthogonal to each other AND to the existing 4 axes — velocity is
  quote-derived/signed/rate-based, recent-trade-side is trade-
  derived/count-based/ratio-thresholded. The fact that BOTH produced
  null/regression vs g3l2 is strong evidence that the afg island's
  4-axis stack (spread + chop + base-flow + size-asymmetry) is at or
  near the empirical ceiling for fifth-axis ADDITIONS on this base.
  The 4-gate-conditioned surviving population (~96k trades) appears
  to be a slice where additional binary SKIP gates extract diminishing
  to zero marginal EV.

**Honest framing**
  - The g3l2 4-axis stack remains the island-1 lineage best at
    pnl 4182.00 (+233.05% vs base afg, sharpe 17.80).
  - g4l2 does NOT improve on g3l2 and produces a small drawdown
    regression; do not promote g4l2 over g3l2.
  - Two 5th-axis attempts at different mechanic classes both failed
    to clear the +2% confirmation band. This is not proof that NO
    5th axis can work — but it does shift the highest-information
    direction AWAY from continued 5th-axis exploration and TOWARD
    operating-point retuning of the existing 4 axes (which were
    set at single-shot defaults in their respective introduction
    loops and have never been swept).
  - trade_count 96,283 is well above any small-sample concern.
    mean_slippage = 0.0 reflects the deterministic top-of-book
    execution constraint, not an algo property.
