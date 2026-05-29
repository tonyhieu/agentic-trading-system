# Algorithm Notes: afg-f-l5

Per-iteration experiment — base_algo `aggressor-flow-gate`, context mode
`full-trace`, loop 5. Starting point: `afg-f-l4` (prior loop).

## Hypothesis

**Context available (full-trace, loop 5)**: full prior reasoning + NOTES.md
for `afg-f-l1`, `afg-f-l2`, `afg-f-l3`, and `afg-f-l4`, plus base algo
metrics. Total context_chars_in = 73,257 (~18,314 tokens).

Recap of the four-loop history of this arm:

- **Loop 1 (afg-f-l1)**: added `min_gross_volume = 8.0` floor (theory:
  thin-tape one-sided prints are noise). Result: realized_pnl **-9.18 %**
  vs base, sharpe **-0.61**, IS improved **-7.07 %**. Theory FALSIFIED on
  the P&L axis — thin-tape one-sided prints carry genuine 30 s adverse
  signal. IS/P&L decoupling first documented.
- **Loop 2 (afg-f-l2)**: tightened `flow_threshold` 2.0 → 1.5, reverted
  loop 1's floor. Result: every metric **byte-identical to base** — a
  no-op. Root cause: MES `size` is integer-valued, so `_net_flow` is
  integer-valued; thresholds in (1, 2] all produce the same skip set.
  Methodological lesson: integer-equivalence classes; threshold tests
  must cross integer boundaries.
- **Loop 3 (afg-f-l3)**: tightened `flow_threshold` 1.5 → 1.0
  (crossing into class (0, 1]). Result: realized_pnl **+10.39 %** vs
  base, sharpe **+0.836** (5.594 → 6.430), trade_count **-1.66 %**.
  Validated loop 1's mechanism at the new equivalence class. Loop 3
  flagged that the level-threshold lever is now **saturated**
  (threshold = 0 is degenerate); remaining productive directions are
  structural — asymmetric thresholds, flow acceleration, window length,
  or a hybrid small-floor revisit.
- **Loop 4 (afg-f-l4)**: probed window length, halving `window_seconds`
  10.0 → 5.0 (threshold = 1.0, gross floor = 0.0 carried forward).
  Result: realized_pnl **-0.34 %** vs base, -9.72 % vs loop 3; sharpe
  flat vs base; trade_count -0.68 % vs base (actually MORE trades than
  loop 3 despite the "tighter" window). Root cause: at 5 s the deque
  is often empty (warm-up path fires unconditional submit); when
  non-empty, |net_flow| over 5 s is more dominated by single-print
  noise. The gate becomes mostly a no-op AND the residual skips are
  noisier. **Durability hypothesis won decisively over freshness.** The
  10 s integral is doing real work; halving to 5 s destroys it.
  Methodological lesson: the empty-deque warm-up path is a meaningful
  axis in its own right at short windows.

Loop 4's forward-looking note made the next move clear and prioritised:

> "**Lengthen the window** (the opposite direction from loop 4). Test
> `window_seconds = 15.0` at the same threshold = 1.0. If the 10 s
> integral is doing the work and longer is even better, this should
> improve P&L further (modestly, with diminishing returns). Risk: at
> 20 s+, |net_flow| over 20 s of MES is almost always non-zero ... so
> the gate could become near-degenerate (firing on almost every order).
> 15 s is the next interesting point — meaningfully longer than 10 s
> without entering the degenerate regime."

Loop 4 also explicitly directed: "Loop 5 should also **revert
window_seconds to 10.0** as the starting point — loop 4's 5 s setting
is empirically inferior and should not be carried forward as a default."

That is what afg-f-l5 does, with one combined step.

**Targeted change** (single behavioural knob, after correction):

  1. **Revert `window_seconds` 5.0 → 10.0** (correction of loop 4's
     known-harmful default; not the hypothesis under test). This
     restores the loop-3 operating point as the starting condition.
  2. **Lengthen `window_seconds` 10.0 → 15.0** (the hypothesis under
     test). With `flow_threshold = 1.0` and `min_gross_volume = 0.0`
     both preserved unchanged.

Net behavioural delta vs afg-f-l4: window 5.0 → 15.0. Net delta vs
the loop-3 operating point (the relevant "best so far" reference):
window 10.0 → 15.0. flow_threshold and min_gross_volume identical to
both prior loops in their respective post-revert states.

**Mechanism / what loop 4 predicts for the lengthening direction**:

- Loop 4 established that the 10 s integral does real work — 5 s loses
  it. The mechanism is two-fold: (a) more samples per window → better
  SNR on |net_flow|; (b) the deque is reliably populated at 10 s
  (warm-up path rarely fires). Both factors should *continue* to
  improve at 15 s, with diminishing returns.
- The risk loop 4 flagged is degeneracy at long windows: as the window
  grows, integer running |net_flow| approaches "almost always ≥ 1"
  over MES trading activity, because the running sum rarely returns
  to exactly 0 over many seconds of asymmetric retail/institutional
  flow. If the gate fires on virtually every order, the algo
  collapses to "stand-down on everything" (subject to anti-cascade
  forcing alternating submits via `_position_flat`), which is a
  qualitatively different regime than a selective gate.
- The 15 s mid-point is the methodologically clean test. If it
  improves vs loop 3 (1386.00 pnl, 6.430 sharpe), the durability
  story continues — additional samples help, no degeneracy. If it
  matches loop 3 within noise, we have found the saturation point of
  the durability lever (loop 3's 10 s window was already near-optimal).
  If it under-performs loop 3, degeneracy has begun and the optimum
  sits in (10, 15) — useful information either way.

**Expected effect (concrete, in vs_base_* terms)**:

- realized_pnl: **+8 % to +14 % vs base** if durability continues to
  help (modest improvement on loop 3's +10.39 %); **roughly equal to
  loop 3 (+10 %)** if saturation has been reached; **+0 to +5 % vs
  base** if degeneracy has set in (gate fires too often, anti-cascade
  alternation dilutes selectivity).
- trade_count: probably **slightly lower than loop 3** (-2 to -4 %
  vs base; -0.5 to -2 % vs loop 3). Longer window = more chances for
  |net_flow| ≥ 1 to be hit at any decision instant, so skip set
  modestly expands. The anti-cascade re-entry path then forces an
  unconditional submit on the *next* order, so trade_count cannot
  collapse — the floor is roughly 50 % of the order stream even at
  full degeneracy.
- sharpe: tracks P&L direction.
- max_drawdown_pct: not expected to worsen materially (same
  anti-cascade and quantity-invariant guarantees).
- mean_slippage: 0.0 vs 0.0 (zero-cost fill model).
- is_weighted_bps: likely **worse than loop 3 and base** — more skips
  means more potential favorable-fill entries left on the table. The
  IS/P&L decoupling established across loops 1, 3, and 4 applies
  again in the more-skips direction.

**Risk**: The degeneracy risk loop 4 flagged for 20 s+ may already
appear at 15 s. If |net_flow| ≥ 1 holds on virtually every 15 s
window in MES day-session, the gate effectively skips every order
between forced re-entries — and the anti-cascade then makes
trade_count tend toward "every other order," which is qualitatively
different from a selective gate. If this regime is hit, the algo
will produce a low-trade-count, moderate-P&L result; the diagnostic
will be trade_count well below 100,000 (a ~10 %+ reduction).

**Builds on**: `afg-f-l4` (prior loop) — structurally, the only
behavioural change is `window_seconds` 5.0 → 15.0. All other
invariants (anti-cascade `_position_flat=True` after any skip,
reduce-only-orders-always-execute, quantity-invariant preserved,
O(1) running sums for both `_net_flow` and `_gross_volume`,
`flow_threshold = 1.0`, `min_gross_volume = 0.0`) are preserved
unchanged.

---

## Implementation Decisions

- **`window_seconds` default = 15.0.** Lengthened from afg-f-l4's
  5.0 (loop 4 correction) and from afg-f-l3's 10.0 (the hypothesis
  under test).
- **`flow_threshold` default = 1.0.** Carried forward from
  afg-f-l3 / afg-f-l4. Loop 3 established this as the proven
  operating point; loop 4 did not touch it; loop 5 does not touch it
  either. No methodological risk here: 1.0 is still in equivalence
  class (0, 1] for any window length, since the gate condition is
  evaluated on integer-valued `_net_flow` at a single decision
  instant.
- **`min_gross_volume` default = 0.0.** Carried forward
  (loop 1's harmful feature remains reverted). Loop 4's NOTES.md
  flagged a possible loop-5 alternative of trying a small floor
  (e.g. 2-3) in combination with the longer window, but loop 4
  prioritised window-length testing first; we follow that.
  Re-examining the floor at the new (window=15, threshold=1)
  operating point is the natural loop 6 candidate.
- **No algorithmic structure changes.** Same deque, same O(1) running
  aggregates (`_net_flow`, `_gross_volume`), same prune logic, same
  `_flow_is_adverse` decision, same `on_order` routing, same
  anti-cascade and reduce-only paths. This isolates `window_seconds`
  as the single behavioural variable.
- **The `_gross_volume` tracking code is retained** (no-op at
  default `min_gross_volume = 0.0`) so loop 6 can re-enable a floor
  without code churn. Cost is one running-sum maintenance, O(1).
- **Quantity invariant preserved**: orders are still only skipped or
  submitted whole; `order.quantity` is never touched.

**Look-ahead check**: identical to all prior loops in the arm.
`on_trade_tick` only appends; only trade ticks with
`ts_event <= order.ts_init` are present at decision time (replay is
strictly chronological; the prune uses `order.ts_init`, never a
future timestamp). Lengthening the window widens the look-*back* —
it does not change look-ahead semantics. The `cutoff_ns = ts_init -
window_ns` arithmetic remains correct for any window size.

---

## Backtest Observations

Train window: 12 dates (2026-03-08 to 2026-03-20). Baseline `simple` read
from cache (`--use-cached-baseline`).

**Results — afg-f-l5 vs base algo `aggressor-flow-gate`:**

| metric             | afg-f-l5   | aggressor-flow-gate | delta              |
|--------------------|------------|---------------------|--------------------|
| realized_pnl       |   1421.25  |              1255.50|  **+13.20 %**      |
| mean_slippage      |   0.0      |              0.0    |   0.0 (both 0)     |
| sharpe_ratio       |   6.7321   |              5.5944 |  **+1.1377**       |
| max_drawdown_pct   |  -0.03057% |             -0.03325%|  +0.00267 pp (better) |
| win_rate           |   0.35529  |              0.35488 |  +0.04 pp          |
| trade_count        | 104836     |           107198    |  **-2.20 %**       |
| is_weighted_bps    |   0.04786  |              0.04724 |  +1.30 % (worse)   |

(vs `simple` baseline: `vs_baseline_pnl_pct` = +811.06 %, comfortably
clearing the absolute pass-gate margin; relevant comparison for this
experiment is vs base above.)

**Results — afg-f-l5 vs `afg-f-l3` (loop 3, the prior best-in-arm):**

| metric             | afg-f-l5   | afg-f-l3            | delta              |
|--------------------|------------|---------------------|--------------------|
| realized_pnl       |   1421.25  |              1386.00|  **+2.54 %**       |
| sharpe_ratio       |   6.7321   |              6.4299 |  **+0.3022**       |
| trade_count        | 104836     |           105415    |  -0.55 %           |
| is_weighted_bps    |   0.04786  |              0.04961 |  -3.53 % (better)  |
| max_drawdown_pct   |  -0.03057% |             -0.03235% |  +0.00178 pp (better) |

**Hypothesis verdict: SUPPORTED — durability continues to help.** The
lengthening test produced the strongest result in this arm to date,
modestly extending loop 3's +10.39 % gain to +13.20 % vs base. No sign
of the degeneracy regime loop 4 flagged for long windows.

- **Realized P&L: +13.20 % vs base, +2.54 % vs loop 3** — within the
  predicted "+8 % to +14 % vs base" range (toward the upper end). The
  additional 5 s of look-back (10 s → 15 s) sharpened the gate
  meaningfully without saturation. The durability mechanism loop 4
  documented (more samples → better SNR on |net_flow|) continued to
  improve at 15 s; the gate's per-skip edge rose enough to add +2.54 %
  P&L on top of loop 3.
- **Sharpe: +1.14 vs base, +0.30 vs loop 3** (6.73 vs 5.59 / 6.43).
  Large improvement vs base; meaningful improvement vs loop 3. Both
  the absolute level and the vs-loop-3 delta exceed expectations.
- **Trade count: -2.20 % vs base, -0.55 % vs loop 3** (104836 vs
  107198 / 105415). The skip set expanded modestly vs loop 3, as
  predicted (longer window catches more |net_flow| ≥ 1 readings at
  any decision instant). Magnitude is well within the "selective
  gate" regime — no sign of the near-degeneracy floor loop 4 warned
  about (where anti-cascade alternation would dominate). The
  trade_count would have collapsed toward ~50 % of base if the gate
  were firing on virtually every order; we are at 97.8 % of base
  trades, so the gate remains selective.
- **Drawdown: improved further** (-0.0306 % vs base -0.0333 % vs
  loop 3 -0.0323 %). Best drawdown in the arm so far.
- **Win rate: +0.04 pp vs base** — essentially unchanged, same pattern
  as loop 3 (the edge comes from average outcome on retained vs
  skipped trades, not a win-rate shift).
- **is_weighted_bps: +1.30 % vs base** (slightly worse) but
  **-3.53 % vs loop 3** (notably better). This is an interesting
  shift: the longer window's gate is *more selective per skip* (the
  per-skip evidence quality is higher with more samples) so the
  formerly-skipped favorable-fill entries become a smaller share of
  skipped trades. The IS/P&L decoupling documented in loops 1, 3, 4
  is *partially relieved* here — IS is roughly base-equivalent while
  P&L is the highest in the arm.

**Interpretation.** Three pieces of evidence agree: the durability
hypothesis (10 s integral does real work, more samples help) holds and
extends into the 15 s window. The level-threshold lever (saturated at
loop 3) has now been complemented by a window-length improvement; the
combined operating point (window=15, threshold=1) is the best-in-arm
on P&L, sharpe, and drawdown simultaneously, while bringing IS back to
roughly base-equivalent. The degeneracy risk loop 4 flagged for 20 s+
has not yet materialised at 15 s — trade_count remains in the
selective-gate regime, not the alternating-floor regime.

**Direction for loop 6.** With the level-threshold lever saturated
(loop 3) and the window-length lever now validated for further
lengthening (loop 5), several candidates remain. In priority order:

  1. **Continue lengthening: `window_seconds = 20.0`** at the same
     `flow_threshold = 1.0`, `min_gross_volume = 0.0`. This is the
     natural extrapolation of loop 5's positive result *and*
     the test loop 4 flagged as the degeneracy boundary. Either
     outcome is informative:
       - If P&L improves further, the durability curve is still rising
         at 20 s and loop 7 should push to 25-30 s.
       - If P&L flattens or falls, loop 5's 15 s is at or near the
         optimum, and the loop-4-flagged degeneracy regime has begun.
     Loop 5's trade_count (-2.20 % vs base) gives headroom: the gate
     would have to compress trade_count to roughly 80,000-90,000
     (a ~15-25 % cut) before anti-cascade alternation dominated. So
     20 s is a clean diagnostic test point.

  2. **Hybrid: small gross-volume floor at (window=15, threshold=1).**
     Loop 4's NOTES.md flagged this as a low-priority alternative; with
     loop 5's success on window-lengthening, the natural test is whether
     a *small* floor (min_gross_volume = 2 or 3) can further sharpen the
     gate by filtering single-print-noise windows at the new operating
     point. Loop 1's negative result was strong, but the operating
     point is materially different now (longer window + tighter
     threshold). Lower priority than (1) because (1) is more
     mechanistically clean and directly extends this loop's finding.

  3. **Asymmetric thresholds** (the structural lever from loop 3's
     enumeration that has never been tested). At
     (window=15, threshold=1), test BUY = 1, SELL = 2 or vice versa.
     Less prioritised because the symmetric gate has just produced
     the best result in the arm — the asymmetric variant would have
     to outperform a now-strong baseline.

  4. **Flow acceleration / first-difference** (loop 1 suggestion #3
     never tried). A structural change that escapes the
     level-threshold paradigm entirely. Highest information value but
     also highest implementation risk and most distant from the
     evidence so far. Worth pursuing only if simpler levers stop
     yielding.

**What NOT to try in loop 6**: any further window shortening
(empirically inferior per loop 4); any non-integer-boundary threshold
tweak at threshold = 1 (per loop 2's discretisation lesson, still
applies).

**Methodological note.** This loop closed a clean experiment: loop 4
established the freshness/durability fork and proved freshness loses;
loop 5 ran the orthogonal lengthening test and proved durability
continues to win past 10 s. The two loops together pin down the
direction of the optimum to (10 s, 20 s+) and rule out (< 10 s). Both
loops also depended on the full-trace context channel — loop 5 needed
loop 4's microstructural diagnosis (empty-deque warm-up, per-skip
SNR) to make the lengthening test the obvious next step rather than
abandoning the window lever. A metrics-only mode looking at loop 4's
-0.34 % might have moved to a different lever entirely; the full
trace led directly to the highest-leverage move available.

**Note on metrics.** `mean_slippage` is 0.0 on both sides (zero
fill-cost model), so `vs_base_slippage_pct` is reported as 0.0 by
convention and carries no information this loop.

