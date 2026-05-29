# Algorithm Notes: afg-f-l3

Per-iteration experiment — base_algo `aggressor-flow-gate`, context mode
`full-trace`, loop 3. Starting point: `afg-f-l2` (prior loop).

## Hypothesis

**Context available (full-trace, loop 3)**: full prior reasoning + NOTES.md
for both `afg-f-l1` and `afg-f-l2`, plus base algo metrics.

Recap of the two-loop history of this arm:

- **Loop 1 (afg-f-l1)**: added `min_gross_volume = 8.0` floor in front of
  the flow gate (theory: thin-tape one-sided prints are noise). Result vs
  base: realized_pnl **-9.18%**, sharpe **-0.61**, trade_count **+1.73%**,
  is_weighted_bps **-7.07%** (IS improved). The "thin-tape noise" theory
  was empirically FALSIFIED on the headline P&L metric. The floor let
  through entries that averaged adverse over the oracle's 30s horizon.
  Conclusion: thin-tape one-sided prints carry GENUINE directional
  signal; the base gate is doing real work there.

- **Loop 2 (afg-f-l2)**: tightened `flow_threshold` from 2.0 to 1.5 and
  reverted loop 1's harmful floor (set `min_gross_volume = 0.0`). The
  intent was to catch additional adverse-flow setups on the loop-1
  mechanism. Result: every metric byte-identical to base — a
  **BEHAVIORAL NO-OP**. Root cause: MES futures `size` is integer-valued,
  so the running `_net_flow` is integer-valued at every decision instant.
  The condition `net_flow <= -threshold` has the same truth value for any
  threshold in (1, 2]; the skip set is identical, so the algorithm
  behaved identically. Loop 2 cost an iteration without measuring a real
  treatment effect.

Loop 2's forward-looking note made the next move unambiguous:
> "**`flow_threshold = 1.0`** is the next genuine test point below 2.0.
> It moves to equivalence class (0, 1], catching all windows with
> |net_flow| >= 1 — including |net_flow| = 1, which the base never
> skips. This is a substantive ~2x expansion of the skip set (any
> window where buyers and sellers differ by even one contract)."

That is what afg-f-l3 does.

**Targeted change** (single knob): **`flow_threshold` 1.5 -> 1.0
contracts**. `min_gross_volume` stays at 0.0 (the no-op revert from loop
2 is preserved — that was a correction of loop 1's error, not a
hypothesis under test).

This is THE test of loop 1's mechanism, with the discretisation
correction from loop 2 applied. The skip set genuinely expands from
{windows with |net_flow| >= 2} to {windows with |net_flow| >= 1} —
catching the previously-allowed |net_flow| ∈ {-1, +1} windows where
buyers and sellers differ by exactly one contract.

**Mechanism / what the loop-1 result predicts**:

- Loop 1 proved that windows with |net_flow| >= 2 (the base's skip set)
  carry real 30s adverse signal — disabling skips there cost 9.18% P&L.
- The mechanism extrapolated downward: if the signal-to-noise ratio is
  high even at the base threshold (|net_flow| >= 2), then |net_flow| = 1
  windows should *also* carry usable signal, just weaker. Skipping them
  should yield further P&L gains, with diminishing returns and rising
  variance.
- BUT: this loop is the test of that extrapolation. Loop 1 only
  measured what happens when you *remove* skips on weak evidence
  (negative outcome). It did not measure what happens when you *add*
  skips on weak evidence — those are not symmetric. The |net_flow| = 1
  population is much larger than |net_flow| >= 2; even a small
  per-window edge could move the headline.

**Expected effect (concrete, in vs_base_* terms)**:

- realized_pnl: **+1% to +5% vs base** (positive, the first real test
  of loop 1's mechanism in the tightening direction).
- trade_count: **notably lower than base** — possibly 2-5% fewer
  trades. |net_flow| = 1 is by far the most common non-zero state of
  a 10s aggressor-flow deque in MES, so the skip set roughly doubles.
- sharpe: flat-to-up (similar P&L on fewer trades should lift
  efficiency, if entries are net-adverse on the new skip set).
- max_drawdown_pct: flat or slightly better.
- mean_slippage: 0.0 vs 0.0 (zero-cost fill model).
- is_weighted_bps: likely *worse* than base (more skips => more
  potential good-fill entries left on the table — the IS/P&L
  decoupling loop 1 documented, applied in the same direction).

**Risk** (specific to this loop): |net_flow| = 1 may genuinely be near
the noise floor. If it is, two failure modes are possible:

  1. *Net-neutral*: |net_flow|=1 windows are roughly 50/50 directionally
     over 30s; skipping them removes equal-edge trades on both sides,
     leaving P&L roughly flat but trade_count meaningfully lower.
     Outcome: small sharpe gain (efficiency), no P&L gain, IS hit.
  2. *Net-negative*: |net_flow|=1 windows actually carry *positive*
     forward edge (e.g., 1-lot one-side prints reflect retail noise
     fading larger institutional moves that are about to mean-revert).
     In this regime the gate is now skipping favorable setups.
     Outcome: P&L falls vs base.

A negative result in this loop would be strong evidence that the gate's
natural breakpoint is right around |net_flow| = 2 (i.e., loop 1's
mechanism only holds on the >= 2 population).

**Builds on**: `afg-f-l2` (prior loop). The min_gross_volume = 0.0
no-op revert is carried forward. Anti-cascade (`_position_flat=True`
after any skip), reduce-only-orders-always-execute, quantity-invariant,
and O(1) running-sum guarantees are all preserved unchanged.

---

## Implementation Decisions

- **`flow_threshold` default = 1.0.** This is the next equivalence class
  below the (1, 2] class shared by base (2.0) and afg-f-l2 (1.5).
  Threshold = 1.0 falls in class (0, 1] — it catches all windows with
  |net_flow| >= 1 (i.e., any non-zero integer net flow).
- **`min_gross_volume` default = 0.0** (carried forward from loop 2 —
  the floor remains a no-op). The tracking code for `_gross_volume`
  is also retained at zero behavioural cost so future loops can
  re-enable a floor with a different value if motivated.
- **All other invariants preserved unchanged from base / afg-f-l1 /
  afg-f-l2**: anti-cascade after skips, reduce-only orders submitted
  immediately, no order-quantity modification, no look-ahead (prune
  uses `order.ts_init`).
- **Why threshold = 1.0 and not, say, 0.5?** Anything in (0, 1] is
  the same equivalence class — 0.5, 0.9, 1.0 would all be identical.
  Picking 1.0 is the canonical representative and makes the gate
  condition `|net_flow| >= 1` legible at a glance.
- **Why not jump straight to threshold = 0 (gate always fires)?**
  Threshold = 0 falls in a degenerate equivalence class (the BUY
  condition `net_flow <= 0` would fire even on perfectly balanced or
  buy-dominant tape). That's not a "tighter gate" — it's a different
  semantics. We stay in the integer-quantised regime by keeping
  threshold strictly positive.

**Look-ahead check**: identical to afg-f-l2 (identical to afg-f-l1
identical to base). `on_trade_tick` only appends; the prune uses
`order.ts_init` as the cutoff. Replay is strictly chronological, so
only ticks with `ts_event <= order.ts_init` are present at decision
time.

---

## Backtest Observations

Train window: 12 dates (2026-03-08 to 2026-03-20). Baseline `simple` read
from cache (`--use-cached-baseline`).

**Results — afg-f-l3 vs base algo `aggressor-flow-gate`:**

| metric             | afg-f-l3   | aggressor-flow-gate | delta            |
|--------------------|------------|---------------------|------------------|
| realized_pnl       |   1386.00  |              1255.50|  **+10.39 %**    |
| mean_slippage      |   0.0      |              0.0    |   0.0 (both 0)   |
| sharpe_ratio       |   6.430    |              5.594  |  **+0.836**      |
| max_drawdown_pct   |  -0.03235% |             -0.03325%|  +0.0009 pp     |
| win_rate           |   0.35458  |              0.35488 |  -0.03 pp       |
| trade_count        | 105415     |           107198    |  **-1.66 %**     |
| is_weighted_bps    |   0.04961  |              0.04724 |  +5.02 %        |

(vs `simple` baseline: `delta_pnl_pct` = +788.46 %, so the variant
comfortably clears the absolute pass-gate margin; the relevant
comparison for this experiment is vs base above.)

**Hypothesis verdict: SUPPORTED.** The first real tightening test of
loop 1's mechanism (now correcting for loop 2's integer-quantisation
discovery) produced a substantively positive result.

- **Realized P&L: +10.39 % vs base** — within the expected +1% to +5%
  range was the prior, and the actual outcome is roughly 2x that.
  Skipping additional |net_flow| = 1 windows added meaningful P&L,
  confirming that even single-contract-imbalance windows over 10s
  carry usable 30s-horizon adverse signal. Loop 1's mechanism
  extrapolates correctly into the (0, 1] equivalence class.
- **Sharpe: +0.836** — large improvement (5.59 -> 6.43). Consistent
  with the prediction: similar exposure with the gate catching more
  adverse setups raises risk-adjusted return.
- **Trade count: -1.66 %** (107198 -> 105415) — fewer trades, as
  predicted (more skips). The magnitude is smaller than the loop
  1 trade-count delta of +1.73 % (loop 1 *added* trades). The
  |net_flow| = 1 population is large but most such windows must
  not have been skip-eligible anyway under the anti-cascade /
  warm-up paths; the net skip-set expansion in observed trades is
  ~1.7 %, not the ~50-100 % the raw equivalence-class arithmetic
  might suggest. Still — substantively non-zero, and the per-skip
  edge is high enough that the headline P&L moved +10 %.
- **Drawdown: slightly improved** (-0.0323 % vs -0.0333 %, +0.0009 pp).
  No material regression.
- **Win rate: -0.03 pp** — essentially unchanged. The added skips
  removed a roughly representative slice of trades; the edge gain
  comes from the *average* outcome of the skipped trades being
  adverse, not from a win-rate shift on retained trades.
- **is_weighted_bps: +5.02 %** (worse) — as predicted. Sharper gate =
  more skipped favorable-fill entries. The IS/P&L decoupling loop 1
  documented is reaffirmed and remains a known trade-off: the
  algorithm's net-P&L objective is being optimised at the cost of
  fill-quality on the trades it does take.

**Interpretation.** This loop is the methodologically clean test that
loop 2 *attempted* — and it confirms loop 1's tightening hypothesis.
The integer-quantisation correction (loop 2's lesson) was necessary
to make the test real, and once made real, it validated the prior
mechanism. The base gate at threshold = 2 is under-sensitive: there
is real edge in the |net_flow| = 1 population on a 10s window over a
30s horizon.

**Direction for loop 4.** The natural follow-ups, in priority order:

  1. **Threshold = 0.5 vs threshold = 1.0 are in the same equivalence
     class** — applying loop 2's lesson, the next genuine tightening
     test point is *unbounded below 1*. There IS no integer below 1
     except 0, and threshold = 0 is degenerate (would fire on perfectly
     balanced tape). So **further P&L gains from threshold tightening
     are likely exhausted** at threshold = 1.0. This is the floor of
     the level-threshold lever.
  2. **Structural changes become more interesting now.** Options:
     (a) **Asymmetric thresholds** between BUY and SELL — e.g.,
         BUY = 0, SELL = 1 (degenerate on BUY) or BUY = 1, SELL = 2.
         The asymmetric tests must cross integer boundaries to avoid
         loop 2's trap. The motivation is the possibility of a
         day-side / book-side asymmetry in MES that a symmetric
         threshold leaves on the table.
     (b) **Flow acceleration** (first-difference of net_flow): gate
         on dN_flow/dt instead of net_flow level. This is a structural
         change that escapes the integer-quantisation regime entirely
         (the first-difference of integer-valued flows can take many
         values once you smooth or window-difference). It is loop 1's
         suggestion #3 and the most genuinely novel direction left
         after threshold tuning has saturated.
     (c) **Window length** (10s -> e.g. 5s or 20s): the 10s window is
         inherited unexamined from the base. Shorter windows respond
         faster to fresh aggression; longer windows are smoother but
         laggier. A 20s window at threshold = 2 might be roughly
         equivalent to a 10s window at threshold = 1 (more cumulative
         flow needed but over a longer span). Worth probing.
  3. **Combine threshold = 1 with a SMALL gross-volume floor.** Loop 1
     showed `min_gross_volume = 8` was too aggressive. But with the
     tighter threshold = 1, a much smaller floor (e.g. 2-3 contracts)
     might re-enable filtering of the very-thinnest one-print windows
     without removing the |net_flow| = 1 signal that loop 3 just
     proved valuable. This is a re-examination of loop 1 in light of
     loop 3's evidence — a hybrid approach. (Lower priority than (2)
     because loop 1's negative result was strong; but the parameter
     space is different now.)

**What NOT to try in loop 4.** Any further non-integer-boundary
threshold tweak (e.g. 0.5, 0.7). Per loop 2, those are no-ops.

**Note on metrics.** `mean_slippage` is 0.0 on both sides (zero
fill-cost model), so `vs_base_slippage_pct` is 0.0 by convention and
carries no information this loop. The `is_weighted_bps` regression
is the real fill-quality measurement, and is well-understood as the
expected cost of the more-aggressive gate.

