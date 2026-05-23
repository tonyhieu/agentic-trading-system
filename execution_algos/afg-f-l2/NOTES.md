# Algorithm Notes: afg-f-l2

Per-iteration experiment — base_algo `aggressor-flow-gate`, context mode
`full-trace`, loop 2. Starting point: `afg-f-l1` (prior loop).

## Hypothesis

**Context available (full-trace, loop 2)**: full prior reasoning + NOTES.md
from loop 1 (`afg-f-l1`) plus base algo metrics.

Recap of loop 1's empirical finding (verbatim, since this is what the next
change has to be reconciled with):

- `afg-f-l1` added a `min_gross_volume = 8.0` floor in front of the
  flow gate (gate stands down when in-window |size|-sum is below the
  floor, on the theory that thin-tape one-sided prints are noise, not
  signal).
- Result vs base `aggressor-flow-gate`: realized_pnl **-9.18 %**, sharpe
  **-0.61**, max_drawdown **-0.0025 pp**, trade_count **+1.73 %**,
  is_weighted_bps **-7.07 %** (i.e., IS improved).
- Mechanism worked as designed (fewer skips, more trades). But the added
  trades averaged *adverse*. Conclusion: thin-tape one-sided prints
  carry GENUINE 30 s-horizon directional information. The base gate was
  doing real work there, and disabling it cost net P&L. IS and net P&L
  decoupled: gate-skips improve fill-quality but skip-removals don't
  improve net P&L because the skipped windows actually do go against
  you over 30 s.

Loop 1's own forward-looking note explicitly recommended this loop's
direction: "tighten the absolute threshold (2.0 → 1.5). This loop showed
that the base gate is, if anything, slightly under-sensitive — the
formerly-skipped thin-tape entries it was preventing ARE costing P&L. A
lower threshold would skip more, including in thin-tape regimes, instead
of fewer." That is what afg-f-l2 does.

**Targeted change**: two coupled changes, both motivated by the loop-1
result:

  1. **Tighten `flow_threshold` from 2.0 → 1.5 contracts.** Loop 1's
     finding implies the base gate is slightly under-sensitive. With a
     lower threshold the gate fires on smaller absolute net-flow
     readings, including in thin-tape windows where loop 1 confirmed
     the signal is real. The 1.5 step is small (25 % drop) — large
     enough to be detectable above the noise of a 12-day train, small
     enough to be a one-knob test rather than a wholesale recalibration.
  2. **Revert loop 1's gross-volume floor by setting
     `min_gross_volume = 0.0`.** Loop 1's floor was identified as the
     direct cause of the 9.18 % P&L regression. Setting the floor to
     0.0 makes the check a no-op (gross_volume >= 0 always), so the
     gate evaluates purely on the absolute net-flow threshold — i.e.,
     the same gate structure as the base algo, but at threshold=1.5.
     The tracking infrastructure for `_gross_volume` is retained at
     zero runtime cost so a future loop can re-enable a floor at a
     different value without code changes.

**Why both changes in one loop**: Loop 1 conclusively established the
gross-volume floor is harmful at this strategy/horizon. Carrying it
forward would (a) confound the threshold-tightening signal, (b)
preserve a known-harmful feature. Removing it is not exploring a
hypothesis; it is correcting an identified error. The hypothesis under
test in this loop is *only* the threshold change.

**Mechanism / why threshold 2.0 → 1.5 should help net P&L vs base**:

- Base gate skips entries when |net_flow| in the last 10 s is ≥ 2
  contracts in the adverse direction. Loop 1 showed that this skip
  catches real signal — the skipped windows do go against the entry.
- At threshold 1.5, the gate additionally catches windows with net flow
  in the range [1.5, 2.0). On loop 1's mechanism, those windows
  *should* also tend to go against the entry over 30 s — the only
  question is whether the marginal predictive content at 1.5 is strong
  enough to outweigh the cost of false-positive skips it adds.
- Expected effect: more skips (trade_count *down* vs base, contrary to
  loop 1 which had trade_count up); marginal skips on average adverse;
  net P&L modestly *higher* than base; sharpe up; drawdown not worse.

**Expected effect (concrete, in vs_base_* terms)**:
- realized_pnl: +1 to +4 % vs base (positive sign — opposite of loop 1).
- mean_slippage: 0.0 vs 0.0 (still 0/0 under the zero-cost fill model).
- sharpe: roughly flat to +0.3 vs base.
- max_drawdown_pct: flat to slightly better (-0.005 to 0 pp).
- trade_count: slightly *lower* than base (fewer entries, more skips).
- is_weighted_bps: likely *worse* than base (more skips means more
  potential good-fill entries left on the table — the same IS/P&L
  decoupling loop 1 found, just in the opposite direction).

**Risk**: If 1.5 is below the noise floor of the signal — i.e., if the
predictive content of the [1.5, 2.0) window is too weak to outweigh the
P&L cost of skipping legitimate-edge entries — net P&L will fall vs
base. Loop 1's mechanism suggests this is unlikely (the signal was strong
even in *thin* tape), but it is a possibility. A negative result in this
direction would constitute meaningful evidence that the gate's natural
breakpoint is right around 2.0.

**Builds on**: `afg-f-l1` (prior loop) — structurally a near-revert of
loop 1 + a 25 % threshold tightening. The anti-cascade
(`_position_flat=True` after any skip), reduce-only-orders-always-
execute, quantity-invariant, and O(1) running-sum guarantees are all
preserved unchanged.

---

## Implementation Decisions

- **`flow_threshold` default = 1.5.** Loop 1's recommendation. The next
  test point down (1.0) would be a 50 % reduction from base — too large
  a step for a one-knob loop. 1.5 is the smallest meaningful step that
  cleanly probes loop 1's recommendation.
- **`min_gross_volume` default = 0.0.** Effectively disables the
  loop-1 floor (gross_volume >= 0 always). Retains the tracking code
  and config knob so future loops can re-enable with a non-zero value
  without re-introducing the data structure. No runtime cost beyond
  what loop 1 already paid.
- **`_gross_volume` running sum retained.** Cheap to maintain (O(1)
  on append, O(1) per pruned entry). Worth keeping for diagnostic
  logging and future-loop optionality. At default config it does not
  influence gate decisions.
- **All other invariants preserved unchanged from base / afg-f-l1**:
  anti-cascade after skips, reduce-only orders submitted immediately,
  no order-quantity modification, no look-ahead (prune uses
  `order.ts_init`).

**Look-ahead check**: identical to afg-f-l1 (which was identical to
base). `on_trade_tick` only appends; the prune uses `order.ts_init` as
the cutoff. Replay is strictly chronological, so only ticks with
`ts_event <= order.ts_init` are present at decision time.

---

## Backtest Observations

Train window: 12 dates (2026-03-08 to 2026-03-20). Baseline `simple` read
from cache (`--use-cached-baseline`).

**Results — afg-f-l2 vs base algo `aggressor-flow-gate`:**

| metric             | afg-f-l2   | aggressor-flow-gate | delta            |
|--------------------|------------|---------------------|------------------|
| realized_pnl       |   1255.50  |              1255.50|  **0.00 %**      |
| mean_slippage      |   0.0      |              0.0    |   0.0 (both 0)   |
| sharpe_ratio       |   5.59444…|              5.59444…|   0.000          |
| max_drawdown_pct   |  -0.03325% |             -0.03325% |  0.0 pp        |
| win_rate           |   0.35488  |              0.35488 |  0.0 pp          |
| trade_count        | 107198     |           107198    |  0.00 %          |
| is_weighted_bps    |   0.04724… |              0.04724…|  0.00 %         |

Every metric is byte-identical, down to the floating-point representation
(verified by reading per-date `metrics.json` files: e.g., 20260312 sharpe
= -0.4338288071198671 on both algos). The `vs_baseline_is_bps` field is
also identical (21.50 on both).

**Hypothesis verdict: BEHAVIORAL NO-OP — the threshold change was
inert.** Not a partial success or partial failure; it changed nothing.

**Why** (root cause): MES futures tick `size` is always an integer
(whole contracts). Therefore signed_vol = ±size ∈ ℤ for every aggressor
print, NO_AGGRESSOR contributes 0, and the running sum `_net_flow` is
always integer-valued at any decision instant. The skip condition
`net_flow <= -flow_threshold` then has the same truth value for any
threshold in the half-open interval (1.0, 2.0]:

    net_flow <= -1.5   ⇔   net_flow <= -2   ⇔   net_flow <= -2.0

Both 1.5 and 2.0 catch every window where net_flow ≤ -2 (and reject
every window where net_flow ∈ {-1, 0, 1, …}). The skip set is identical;
behaviour is identical; results are identical. The same reasoning
applies to the symmetric BUY-side condition.

The integer-equivalence classes of this gate, given integer signed_vol,
are:

    threshold ∈ (k-1, k]  ⇒  skip-set = {net_flow with |net_flow| ≥ k}

For the base threshold = 2.0, the class is (1, 2] — any threshold in
that range produces identical behaviour. Loop 1's recommendation of
"tighten 2.0 → 1.5" missed this discretisation; the proper next
test point down is 1.0 (which falls in class (0, 1] and would catch all
net_flow ∈ {±1, ±2, ±3, …} — a genuinely tighter gate).

**Interpretation.** This is a methodological lesson, not an empirical
one about the strategy: the loop did not actually probe a different
configuration. It cost the experiment one loop's worth of context-mode
data (loop 2 of 8 in this arm) without measuring a real treatment
effect on the algorithm side. The honest reading: we still don't know
whether tightening the gate helps net P&L.

**Direction for loop 3.** Re-run the tightening hypothesis at a
threshold that actually crosses an integer boundary:

  - **`flow_threshold = 1.0`** is the next genuine test point below 2.0.
    It moves to equivalence class (0, 1], catching all windows with
    |net_flow| ≥ 1 — including |net_flow| = 1, which the base never
    skips. This is a substantive ~2× expansion of the skip set (any
    window where buyers and sellers differ by even one contract). The
    hypothesis from loop 1 predicts net P&L improvement; the risk is
    that |net_flow|=1 windows are too noisy to carry signal — but the
    test is now real.
  - Threshold 3.0 (or any value in (2, 3]) would be the analogous
    *loosening* test. Less interesting given loop 1's mechanism, but
    a clean control if loop 3 wants symmetric coverage.

Alternative direction if loop 3 prefers a different lever:
  - **Asymmetric thresholds** (loop 1's suggestion #2): BUY-side
    threshold differs from SELL-side. With integer signed_vol the
    same equivalence-class trap applies; any asymmetric test must
    also cross integer boundaries (e.g., BUY=1, SELL=2).
  - **Flow acceleration** (loop 1's suggestion #3): first-difference
    of net_flow. This is a more structural change; useful if loop 3
    wants to step away from level-threshold tuning entirely.

What NOT to try in loop 3: any non-integer threshold change within the
same equivalence class as the current setting. Future threshold tests
should always cross an integer boundary, or change the structure of
the gate.

**Note on metrics.** `mean_slippage` is 0.0 on both sides (zero fill-
cost model), so `vs_base_slippage_pct` is reported as 0.0 by convention
and carries no information this loop. `is_weighted_bps` is also
identical to base for the same reason behaviour is identical — every
fill is on the same tick at the same price.

