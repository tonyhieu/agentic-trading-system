# Algorithm Notes: afg-f-l4

Per-iteration experiment — base_algo `aggressor-flow-gate`, context mode
`full-trace`, loop 4. Starting point: `afg-f-l3` (prior loop).

## Hypothesis

**Context available (full-trace, loop 4)**: full prior reasoning + NOTES.md
for `afg-f-l1`, `afg-f-l2`, and `afg-f-l3`, plus base algo metrics.

Recap of the three-loop history of this arm:

- **Loop 1 (afg-f-l1)**: added `min_gross_volume = 8.0` floor in front of
  the flow gate (theory: thin-tape one-sided prints are noise).
  Result: realized_pnl **-9.18 %** vs base, sharpe **-0.61**, IS improved
  **-7.07 %**. Theory FALSIFIED on P&L axis — thin-tape one-sided prints
  carry genuine 30 s-horizon adverse signal. IS/P&L decoupling first
  documented.

- **Loop 2 (afg-f-l2)**: tightened `flow_threshold` 2.0 → 1.5, reverted
  loop 1's harmful floor. Result: every metric **byte-identical to base**
  — a behavioural no-op. Root cause: MES `size` is integer-valued, so
  running `_net_flow` is integer-valued; thresholds in (1, 2] all
  produce the same skip set. Methodological lesson: integer-quantised
  gates have integer-equivalence classes; tests must cross integer
  boundaries to actually change behaviour.

- **Loop 3 (afg-f-l3)**: tightened `flow_threshold` 1.5 → 1.0
  (crossing into class (0, 1]). Result: realized_pnl **+10.39 %** vs
  base, sharpe **+0.836** (5.594 → 6.430), trade_count **-1.66 %**,
  IS **+5.02 %** (worse). The tightening hypothesis (loop 1's
  mechanism, loop 2's correction) validated strongly. The base gate
  at threshold = 2 was under-sensitive; |net_flow| = 1 windows over
  10 s carry usable adverse signal at the oracle's 30 s horizon.

Where this leaves loop 4: loop 3 explicitly observed that **the level-
threshold lever is saturated**. Threshold = 0.5 is in the same (0, 1]
equivalence class as 1.0 (per loop 2's rule); threshold = 0 is
degenerate. So further symmetric threshold tightening cannot move
behaviour. The remaining productive directions loop 3 enumerated
(in priority order):

  (2a) Asymmetric thresholds (e.g., BUY = 1, SELL = 2 across the
       integer boundary).
  (2b) Flow acceleration / first-difference of net_flow — escapes the
       integer-quantisation regime entirely.
  (2c) **Window-length variation** — the 10 s window is inherited
       unexamined from base.
  (3)  Hybrid threshold = 1 + small gross-volume floor (e.g., 2-3).
       Lower priority per loop 3 (loop 1's negative result was strong).

**Targeted change for loop 4** (single knob): **`window_seconds` 10.0
→ 5.0 seconds** (halved). All other parameters preserved from loop 3
(`flow_threshold = 1.0`, `min_gross_volume = 0.0`).

Why window length and not asymmetric thresholds / flow acceleration:

- Window length is the **least-explored axis**. Loop 3 noted it was
  "inherited unexamined from the base"; all three prior loops have
  worked the same 10 s deque. Probing it tests an entire dimension
  for the first time.
- It is a **clean one-knob structural change** — same code path, just
  a different constant. Lower implementation risk than flow
  acceleration (which would require new aggregates and a
  first-difference computation).
- It is **mechanistically informative either direction.** A 5 s window
  tests the "freshness-of-aggression matters" hypothesis: that the
  predictive signal in the gate is the *most recent* flow, not the
  10 s integral. If shorter helps, freshness wins; if shorter hurts,
  the signal is durability-based and a longer window may be warranted.
- It interacts with the threshold lever in non-obvious ways: at 5 s
  the integer-quantisation classes are unchanged (still (0, 1]), but
  the relative noise per skip changes because the window contains
  fewer prints. The single-print pattern (gross_volume = 1,
  |net_flow| = 1) becomes a much larger share of skip-eligible
  windows.

**Why halve rather than e.g. 7 s or 8 s**: A 50 % reduction is a
clearly-detectable step above any noise floor in a 12-day train. 7 s
or 8 s would be too subtle for a single-loop test; a 1 s window would
be degenerate (almost every order would be skipped). 5 s is the
canonical "halve it" point.

**Why not lengthen the window (e.g., 20 s) instead**: lengthening would
*also* be a valid test, but the mechanism prediction is less
sharp — at 20 s with threshold = 1, the integer net flow is non-zero
almost always (it rarely cancels to exactly 0 over 20 s of MES
trading), so the gate would fire on virtually every order, collapsing
the algo to "stand-down" semantics. That's not a structural test of
the lever; it's a degenerate operating point. Shortening to 5 s
keeps the gate informative.

**Mechanism / why a shorter window could help OR hurt**:

- *Freshness wins* (P&L up): If the oracle's 30 s adverse moves are
  driven primarily by very recent aggression (last few seconds), then
  a 5 s window captures the operative signal while a 10 s window dilutes
  it with older, already-played-out flow. Skipping based on 5 s flow
  would be more accurate per skip; sharpe up; P&L up.
- *Durability wins* (P&L down): If the predictive signal is the
  10 s flow integral (more samples = better SNR), then halving the
  window doubles the noise per skip decision. Skips become less
  reliable; some skipped windows have "random recent imbalance" that
  doesn't predict an adverse 30 s move. Sharpe could fall; P&L could
  fall.

The loop-3 evidence is *consistent* with either view: a successful
gate at 10 s × threshold = 1 doesn't tell us whether the 10 s integral
or its most-recent component is doing the work. This is the test.

**Expected effect (concrete, in vs_base_* terms)**:

- realized_pnl: **roughly flat to +5 % vs base** if freshness wins;
  **0 to -5 % vs base** if durability wins. Genuinely uncertain
  direction; the magnitude in either direction is bounded by loop 3's
  +10.39 % anchor (a structural change at the same threshold won't
  unilaterally undo a +10 % validated effect, but it could give back
  meaningful portions of it).
- trade_count: **lower than base** (more skips). The 5 s window
  still catches |net_flow| >= 1 readily — most 5 s windows have at
  least one one-sided print. Skip set may be similar or slightly
  larger than loop 3's; trade_count -1 to -3 % vs base.
- sharpe: tracks P&L direction; sensitivity to per-skip quality.
- max_drawdown_pct: not expected to worsen materially (anti-cascade
  preserved, no quantity changes, no new behaviour).
- mean_slippage: 0.0 vs 0.0 (zero-cost fill model unchanged).
- is_weighted_bps: likely worse than loop 3 (more potential
  favorable-fill entries left on the table) — the IS/P&L decoupling
  established across loops 1 and 3 applied again.

**Risk**: As above, the genuinely-bad outcome is the "durability
wins" case where the 5 s window introduces enough decision noise that
we undo loop 3's gain. The downside is bounded by reverting in loop 5
if the result is bad. The upside (freshness wins) gives loop 5 a new
axis to push on (e.g., 3 s, or combinations).

**Builds on**: `afg-f-l3` (prior loop). Structurally, the only
behavioural change is `window_seconds`: 10.0 → 5.0. All other
invariants (anti-cascade `_position_flat=True` after any skip,
reduce-only-orders-always-execute, quantity-invariant, O(1) running
sums, default `flow_threshold = 1.0`, default `min_gross_volume = 0.0`)
are preserved unchanged.

---

## Implementation Decisions

- **`window_seconds` default = 5.0.** Halved from loop 3's 10.0.
  All other defaults carried forward from afg-f-l3 unchanged:
  `flow_threshold = 1.0`, `min_gross_volume = 0.0`.
- **No algorithmic structure changes.** Same deque, same O(1) running
  aggregates, same prune logic, same `_flow_is_adverse` decision,
  same `on_order` routing, same anti-cascade and reduce-only paths.
  This isolates the window-length variable cleanly.
- **The `_gross_volume` tracking code is retained** (no-op at default
  `min_gross_volume = 0.0`) so a future loop can re-enable a floor
  without code churn. Cost is one running-sum maintenance, O(1).
- **Quantity invariant preserved**: orders are still only skipped or
  submitted whole; `order.quantity` is never touched.

**Look-ahead check**: identical to base / afg-f-l1 / afg-f-l2 /
afg-f-l3. `on_trade_tick` only appends; only trade ticks with
`ts_event <= order.ts_init` are present at decision time (replay is
strictly chronological; the prune uses `order.ts_init`, never a
future timestamp). Shortening the window does not change look-ahead
semantics — it just narrows the look-*back*.

---

## Backtest Observations

Train window: 12 dates (2026-03-08 to 2026-03-20). Baseline `simple` read
from cache (`--use-cached-baseline`).

**Results — afg-f-l4 vs base algo `aggressor-flow-gate`:**

| metric             | afg-f-l4   | aggressor-flow-gate | delta             |
|--------------------|------------|---------------------|-------------------|
| realized_pnl       |   1251.25  |              1255.50|  **-0.34 %**      |
| mean_slippage      |   0.0      |              0.0    |   0.0 (both 0)    |
| sharpe_ratio       |   5.6056   |              5.5944 |  +0.0112 (flat)   |
| max_drawdown_pct   |  -0.03492% |             -0.03325%|  -0.0017 pp (worse) |
| win_rate           |   0.35201  |              0.35488 |  -0.29 pp         |
| trade_count        | 106471     |           107198    |  -0.68 %          |
| is_weighted_bps    |   0.05380  |              0.04724 | **+13.87 %** (worse) |

(vs `simple` baseline: `vs_baseline_pnl_pct` = +702.08 %, still clears
the absolute pass-gate margin comfortably; relevant comparison is vs
base above.)

**Results — afg-f-l4 vs `afg-f-l3` (the immediate prior loop):**

| metric             | afg-f-l4   | afg-f-l3            | delta            |
|--------------------|------------|---------------------|------------------|
| realized_pnl       |   1251.25  |              1386.00|  **-9.72 %**     |
| sharpe_ratio       |   5.6056   |              6.4299 |  -0.8243         |
| trade_count        | 106471     |           105415    |  +1.00 %         |
| is_weighted_bps    |   0.05380  |              0.04961 |  +8.45 %         |

**Hypothesis verdict: durability wins (cleanly), freshness loses.** The
5 s window gave back almost all of loop 3's +10.39 % vs-base gain. The
P&L at the shorter window is essentially break-even vs base
(-0.34 %), sharpe is flat (+0.011), and the 10 s window's edge from
loop 3 is mostly *erased* — not just diminished.

- **Realized P&L: -0.34 % vs base** — within statistical noise of
  base, but down -9.72 % vs loop 3. The 5 s look-back skips a
  different (largely overlapping but noisier) set of orders than the
  10 s look-back at the same threshold. The decision noise from fewer
  prints per window appears to roughly cancel the per-skip edge.
- **Sharpe: +0.011 vs base** — also break-even. Consistent with the
  net P&L finding.
- **Trade count: -0.68 % vs base** — slightly fewer trades than base,
  much fewer skips than loop 3 (l3 had -1.66 % vs base; l4 has
  -0.68 %). The 5 s window actually *fires the gate less often* than
  the 10 s window — interesting counter-intuitive result. Reason:
  with a 5 s look-back, many orders see an *empty* deque (`if not
  self._flow_deque: return False`) because the most recent print
  fell outside the window. The 10 s look-back keeps the deque
  populated more reliably. So at threshold = 1 the 10 s window
  produces *more* skip opportunities than 5 s.
- **Drawdown: slightly worse** (-0.0017 pp). Win rate down -0.29 pp.
  Neither material.
- **is_weighted_bps: +13.87 %** vs base, +8.45 % vs loop 3 (both
  worse). Fill quality is worse than loop 3 in absolute terms even
  though there are *more* trades. This suggests the 5 s window's
  per-fill quality is genuinely lower, not just that more trades
  averaged fewer good fills.

**Interpretation.** The signal in the gate is the *10 s flow
integral*, not the *most recent* flow. Halving the look-back to 5 s:

  1. Reduces the deque population (more empty-window cases =>
     unconditional submits => fewer skip decisions).
  2. When the deque is non-empty, |net_flow| over 5 s is more dominated
     by single-print noise (fewer samples per decision).
  3. The skipped orders are a smaller, noisier sub-population than at
     10 s, so the per-skip edge falls.

Net effect: the gate becomes mostly a no-op (-0.68 % trade count) AND
the few skips it does make are net-neutral rather than net-edge. The
durability hypothesis wins decisively at this train window.

**Note on directionality.** The result does *not* mean longer is
always better — only that 5 s is too short. The space {5 s, 10 s, ...}
is non-monotonic in principle: at some point lengthening the window
re-introduces stale flow that has already played out. The empirical
question for loop 5 is where the optimum sits — somewhere in
[10 s, ?].

**Direction for loop 5.** Two clean candidates, with the loop 4
result narrowing the priors:

  1. **Lengthen the window** (the opposite direction from loop 4).
     Test `window_seconds = 15.0` at the same threshold = 1.0. If the
     10 s integral is doing the work and longer is even better, this
     should improve P&L further (modestly, with diminishing returns).
     Risk: at 20 s+, |net_flow| over 20 s of MES is almost always
     non-zero (the integer running sum rarely returns to exactly 0
     over a long window), so the gate could become near-degenerate
     (firing on almost every order). 15 s is the next interesting
     point — meaningfully longer than 10 s without entering the
     degenerate regime. (Note: re-tightening to 7-8 s would also be
     valid, but loop 4 already moved 50 % in the shortening
     direction and got a clear negative; lengthening is the
     orthogonal direction we have no data on.)

  2. **Asymmetric thresholds** (the unexplored structural lever from
     loop 3's enumeration). At `window_seconds = 10` (revert) with
     e.g. BUY = 1, SELL = 2 (or vice versa), test the symmetry
     assumption of the gate. Loop 4 establishes that the level lever
     and the window lever have natural breakpoints (level at 1,
     window at 10); the symmetry assumption is the next-most-
     obviously-arbitrary structural choice. If MES has a day-side
     asymmetry (e.g., aggressive selling tends to be more
     mean-reverting than aggressive buying, or vice versa), a single
     symmetric threshold misses that.

Loop 5 should also **revert window_seconds to 10.0** as the starting
point — loop 4's 5 s setting is empirically inferior and should not
be carried forward as a default. (Same pattern as loop 2's revert of
loop 1's harmful floor.)

**What NOT to try in loop 5**: further window shortening (4 s, 3 s
would be even worse on the same mechanism); any non-integer-boundary
threshold tweak (per loop 2's discretisation lesson, still applies).

**Note on metrics.** `mean_slippage` is 0.0 on both sides (zero
fill-cost model), so `vs_base_slippage_pct` is reported as 0.0 by
convention and carries no information this loop. `is_weighted_bps`
fill-quality is worse than both base and loop 3 — but the headline
P&L is the focus, and that came out essentially neutral.

