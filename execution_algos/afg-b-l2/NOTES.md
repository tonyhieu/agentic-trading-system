# afg-b-l2 — aggressor-flow-gate with COMBINED absolute + ratio gate

Brief-summary arm, loop 2. Prior context = only the `summary_out` block from
afg-b-l1 (brief_summary + next, plus its headline metrics). Per the brief-
summary mode boundary I did NOT read L1's full NOTES.md prose or full
reasoning -- only the brief summary + next text in the loop-1.json
`summary_out` block, plus the L1 code as a mechanical reference for the
class structure / file layout.

## Hypothesis

L1's brief_summary established two facts on this oracle:

  1. The base's absolute |net_flow| >= 2.0 gate is, in practice, the
     binding selectivity floor in BUSY windows -- 2 contracts of net
     imbalance against a large abs_vol is implicitly *stricter* than a
     35% ratio of, say, 100 contracts. Replacing the absolute gate with a
     pure-ratio gate RELAXED selectivity in busy windows and admitted
     +13,481 systematically money-losing orders.
  2. On this oracle, every +1k extra admitted orders relative to the base
     destroys ~$47 of pnl. So any change that nets MORE admits than the
     base is strictly dominated.

The brief_summary's "next" direction is explicit: try a COMBINED gate -- require
BOTH |net_flow| >= 2.0 (preserve the base's busy-window absolute floor)
AND |r| = |net_flow| / max(min_abs_baseline, abs_vol_window) >= 0.35 (add
ratio confirmation as a quiet-window denoiser). Mechanically this is a
strict intersection of the L1 gate condition and the base gate condition,
so the admitted-order set is a strict SUBSET of both:

  * Vs base: equal or fewer admits. Some orders the base would admit -- a
    2-contract imbalance against a balanced 100-contract window (r ~= 2%)
    -- now get skipped because the ratio test fails. These are the "weak
    information" admits the base lets through; per L1's per-1k arithmetic,
    skipping them should net positive pnl.
  * Vs L1: equal or fewer admits. L1 admits some orders the base would
    skip (low absolute imbalance but moderate ratio in extremely-quiet
    windows where the 2-contract floor makes the ratio test trivially
    satisfied). The combined gate restores the absolute floor so those
    weak-quiet admits get filtered again.

Expected direction: trade_count <= base, pnl >= base. The intersection
gate cannot regress on either dimension that L1's data showed mattered.
If pnl improves materially over base on the train aggregate, this is the
new high-water mark for the arm. If it merely matches base within noise,
that confirms the base's absolute gate already extracts most of the
selectivity signal and future loops should target a different axis
(window length, asymmetric thresholds by side, regime-conditional
thresholds, etc.).

## Implementation Decisions

  * ONE targeted parametric change vs L1: replace the pure-ratio gate
    `|r| >= ratio_threshold` with a CONJUNCTION
    `(|net_flow| >= flow_threshold) AND (|r| >= ratio_threshold)`.
    Both threshold defaults preserved at base+L1 values (`flow_threshold
    = 2.0` from base, `ratio_threshold = 0.35` from L1). This keeps the
    L1 code as the chassis and makes the gate strictly tighter.
  * `min_abs_baseline = 2.0` retained for the ratio denominator floor --
    same as L1. With the conjunction, the floor matters only when the
    window has very few absolute contracts; the absolute gate already
    handles the "noisy single trade" case independently.
  * Window kept at 10 s -- isolate the gate-form change, do not retune
    the window in the same loop.
  * Direction-side logic carried over from L1 unchanged: for BUY orders
    the adverse condition is `r <= -ratio_threshold AND net_flow <=
    -flow_threshold`; for SELL orders `r >= ratio_threshold AND net_flow
    >= flow_threshold`. Because r and net_flow share the same sign by
    construction (denom is always positive), the two tests can be
    expressed equivalently as
    `abs(net_flow) >= flow_threshold AND abs(r) >= ratio_threshold AND
    sign(net_flow) adverse-to-order-side`. Implementation uses the
    explicit signed form to mirror base + L1 exactly.
  * Anti-cascade semantics (`_position_flat = True` after any skip,
    forcing the next OPEN through unconditionally) preserved exactly
    from base + L1. Reduce-only orders always submit (intraday_flat).
  * Quantity invariant strictly preserved -- orders are skipped or
    submitted unmodified.

## Backtest Observations

Train-window result (11 dates; 20260319 OOM-dropped on both sides, matched
apples-to-apples across base + l1 + l2):

  * Aggregate: realized_pnl = $464.25, sharpe = 2.058, trade_count =
    102,005, win_rate = 35.19%, mean_slippage = 0.0, max_drawdown_pct
    = -4.40%.
  * vs simple baseline (configured pass_gate.baseline): delta_pnl =
    +973.41%, delta_slippage = 0.0%, delta_is_bps = +17.99. STATUS = PASS
    (well above +5.0% pnl gate; 0.0% slippage regression).
  * vs base aggressor-flow-gate on the SAME 11 dates ($970.00 /
    87,760 trades): delta_pnl = -52.14%, trade_count = +14,245
    (+16.2%). The conjunction did NOT reduce admitted-trade count vs
    base -- it expanded it.

The hypothesis was that the conjunction is a strict intersection of the
base condition and the L1 condition, so admitted-orders would be a strict
SUBSET of both. The data shows otherwise: trade_count went UP from base's
87,760 to L2's 102,005 (+14,245). Note also that L2's trade_count
(102,005) is between L1's (101,241) and base's (87,760) -- it is much
closer to L1 than to base. This implies the conjunction skips far fewer
orders than the base does. The asymmetric direction-side test means the
intersection is NOT a strict tightening across both axes simultaneously
the way the hypothesis assumed -- specifically, the base's skip condition
fires on `net_flow >= flow_threshold` for SELLs regardless of how much
total volume sits in the window, while the L2 conjunction additionally
requires `|r| >= 0.35`. That extra ratio requirement is what L1 already
showed RELAXES selectivity in busy windows. The conjunction structure
ANDs an L1 RELAXATION onto base's gate, not a tightening -- so any window
that satisfies the absolute test but has too-low ratio (busy window with
2-contract imbalance against, say, 50 contracts -> r = 0.04) is now
ADMITTED whereas base would skip it. Result: many of the same money-
losing extra admits L1 showed.

Per-1k arithmetic from L1 ($47 destruction per +1k extra admits) roughly
predicts the L2 deficit: +14.2k extra admits vs base ~= -$668 vs the
hypothetical "base-equal" case, observed delta -$505 ($970 -> $464.25)
broadly consistent given variance.

Hypothesis VERDICT: contradicted. The mental model "conjunction must be
strictly tighter than either operand" is wrong for asymmetric gates. The
correct framing is: the base gate (|net_flow| >= 2.0) is a one-sided
absolute filter; ANDing a RATIO filter on top RELAXES it whenever the
ratio condition is the binding one. To get a strictly-tighter-than-base
admitted set, the new condition must DISJOIN with base (skip if base OR
ratio adverse), not CONJOIN.

Single highest-leverage next change: try a DISJUNCTIVE gate -- skip if
EITHER (|net_flow| >= 2.0) OR (|r| >= 0.35 AND abs_vol >= some
moderate floor). The disjunction (with the ratio side gated by a minimum
busyness floor to avoid double-counting the warm-up case) is what
mechanically produces "strict superset of skips, strict subset of
admits" relative to base. Alternative direction also worth holding in
reserve from L1's "next": tighten the BASE's absolute threshold (e.g.,
2 -> 3 contracts) -- L1 + L2 data both suggest base under-skips on this
oracle, so simply raising the absolute floor is a cheap monotone test.
