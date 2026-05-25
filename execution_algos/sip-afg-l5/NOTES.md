# Algorithm Notes: sip-afg-l5

## Hypothesis

**Mechanism**: Identical 10-second rolling signed aggressor-flow gate as
`aggressor-flow-gate` (same input, same uniform weighting, same symmetric
absolute `flow_threshold = 2.0` contracts, same BUY/SELL gate sides). The
single concrete change is to the **post-skip cascade policy**.

Base algorithm: after ANY skip, set `_position_flat = True`, which causes
the immediately-following open order to be submitted **unconditionally**
(no gate evaluation at all), regardless of how adverse the flow happens
to be at that moment.

sip-afg-l5: replace the binary `_position_flat` flag with a **skip-streak
counter** `_skip_streak` and apply graduated relaxation rather than a
hard bypass. Post-skip behavior:

- `_skip_streak == 0` (fresh): evaluate with the base threshold
  (`flow_threshold = 2.0`). Submit or skip per the base rule.
- `_skip_streak == 1` (one skip just happened): re-evaluate with a
  **relaxed** threshold `flow_threshold * 1.5 = 3.0` contracts. The gate
  still fires, but only on strongly-adverse flow. Most orders pass
  through. If we DO skip again, increment to streak=2.
- `_skip_streak >= 2` (two skips in a row): force-submit the next order
  unconditionally (matching the base's hard reset behavior at the cap).
  Reset `_skip_streak = 0`.
- Any submit resets `_skip_streak = 0`.

All other base mechanics preserved verbatim: reduce-only orders always
submit; warm-up (empty deque) submits unconditionally; quantity invariant
holds; `top_of_book_only`, `participation_cap`, `intraday_flat` all
unaffected because the algorithm only decides submit-vs-skip.

**Inefficiency exploited**: The base's anti-cascade is documented as a
safety mechanism ("prevent runaway gating"). Mechanically, after a skip
at order N, the gate is *guaranteed* not to fire at order N+1, regardless
of market state. Given (i) oracle signal cadence is 1 Hz
(`signal_interval_seconds=1.0` from config.yaml) and (ii) the gate's
information window is 10 seconds, adverse aggressor flow that triggered
the skip at order N will almost always still be adverse 1 second later
at order N+1 — the 10s deque has barely turned over. So the base
*systematically* trades adverse-protection on order N for *guaranteed
exposure* on order N+1, and the order at N+1 by selection sits in
exactly the same adverse-flow regime the gate just protected against.

The hypothesis is that this forced re-entry is a structural P&L leak
the base's NOTES.md acknowledges only as "anti-cascade guarantee"
without quantifying its cost. The graduated relaxation lets the gate
*continue* to fire on persistently-strong adverse flow (preserving
genuine skip value across consecutive adverse orders) while still
capping cascade length so the algorithm can never gate indefinitely
on a stuck signal. Cascade is bounded at length 2.

**Why it survives costs**: The change is pure gating logic — no
quantity modification, no fill mechanics, no routing changes. All
constraint compliance arguments from base carry over identically.
`mean_slippage` should remain 0.0 in the zero-fill-cost model.

**Builds on**: `aggressor-flow-gate` (the SIP base algo for this
experiment arm). Single concrete change: replace binary `_position_flat`
with a graduated `_skip_streak` counter applying `flow_threshold * 1.5`
on streak=1 and unconditional submit on streak>=2.

**Orthogonality to l1, l2, l3, l4** (the four prior REVERTED loops):

All four prior loops modified the gate's **decision logic itself** — the
function `_flow_is_adverse(order) -> bool`:

- **l1** changed WEIGHTING inside the window (uniform sum → EWMA recency
  decay).
- **l2** changed SIDE-CONDITIONALITY (disable the SELL gate; asymmetric
  thresholds).
- **l3** changed RULE SHAPE (single-window threshold → two-window AND
  confirmation requiring both 10s AND 3s adverse).
- **l4** changed INPUT TYPE (raw signed contracts → volume-normalized
  signed fraction).

All four kept the **anti-cascade policy** (`_position_flat = True` after
any skip → next open unconditional) verbatim. sip-afg-l5 holds the
gate's signal, weighting, rule shape, and side-conditionality *identical
to the base* and changes only what happens between successive evaluations
— the post-skip state machine. The orthogonal dimension is therefore
"WHEN does the gate apply" rather than "what does the gate decide."

This is also a different category of change from l1-l4 in another sense:
all four prior loops globally altered which orders are gated, but did
not change how the gate interacts with order arrival cadence. sip-afg-l5
explicitly addresses the cadence-vs-window mismatch (1 Hz orders vs 10s
gate memory) that the base ignores. If the underlying base gate is
already at a local optimum (which the loop-4 critic summary suggested:
"the base is at least a local optimum"), then improvement must come from
addressing something the base's gate doesn't touch — and the post-skip
cascade is exactly that.

**Alternatives considered**: None explored — the seed prompt-l0 method
(Steps 1–4) calls for picking ONE weakness and ONE concrete
modification. I have not run EDA on the train data to measure (a) the
empirical fraction of base's skips that are followed by an order in
still-adverse flow, (b) whether `flow_threshold * 1.5` is the right
relaxation factor (could be 1.2, 2.0, or even an EDA-determined value),
or (c) whether the cascade cap should be at length 2, 3, or longer. Per
the experimental boundary I am not allowed to improvise additions to the
method.

---

## Implementation Decisions

- **Skip-streak counter, not time-based cooldown**: Counting *orders* (not
  seconds) sidesteps timing edge cases — every order arrival is a
  decision point, and the relaxation is naturally aligned with the
  oracle's order arrival rate. A time-based cooldown (e.g. "no gate for
  500ms after a skip") would require additional state and a clock
  reference.

- **Relaxation factor 1.5x**: Chosen by intuition, not EDA. The base
  threshold is `flow_threshold = 2.0` contracts; the relaxed threshold
  on streak=1 is `2.0 * 1.5 = 3.0` contracts. The intent is "the gate
  must fire on noticeably stronger evidence to skip a second time in a
  row." A factor of 1.0 would degenerate to no relaxation at all
  (cascade length unbounded, contradicting the safety motivation behind
  the base's anti-cascade). A factor of 2.0+ would be very lenient.
  Flagging this as armchair — the critique phase will see I did not
  calibrate it against the empirical |net_flow| distribution
  conditional on streak=1.

- **Cascade cap at streak=2**: The third order in a row goes through
  unconditionally (matching base's behavior at length 1). This is a
  safety bound: even if persistently-adverse flow is real, we never let
  the algorithm gate indefinitely — eventually we must take exposure.
  A cap of 2 means the maximum *consecutive* skip count is 2 (i.e. up
  to 2 skipped orders before forced submission). At 1 Hz order arrival
  this is at most a 2-second blackout window, well inside the 10s gate
  window. This is also not EDA-calibrated.

- **Reduce-only orders bypass entirely**: Same as base. Reduce-only
  orders never affect `_skip_streak`. They are intraday-flat compliance
  flows and must execute unconditionally.

- **Warm-up handling**: Same as base. If the deque is empty (no trades
  seen yet), submit unconditionally and treat as `_skip_streak = 0`
  (a non-skip submission resets the counter).

- **Symmetric design preserved**: Both BUY and SELL gates apply the
  same threshold and the same relaxation rule. This intentionally
  isolates the cascade-policy change from any side-asymmetric effect
  (which l2 already explored).

- **Implementation in `_flow_is_adverse`**: The streak state is read by
  the main `on_order` handler. The `_flow_is_adverse` evaluator takes a
  threshold parameter (defaulting to base) so the main handler can pass
  either `self._flow_threshold` (fresh) or `self._flow_threshold * 1.5`
  (relaxed) depending on `_skip_streak`.

- **Constraint compliance**: Quantity invariant preserved (only
  submit/skip decisions, never modify order.quantity).
  `top_of_book_only`, `participation_cap`, `intraday_flat` all
  preserved because the change is gate-only.

**Concerns**:
- The 1.5x relaxation factor and the streak cap of 2 are both
  uncalibrated. If real MES adverse-flow regimes typically last 1–3
  oracle ticks (1–3 seconds), the cap=2 setting might over-skip during
  multi-tick adverse runs (forcing exposure exactly when the gate is
  trying to protect). If they last <1 tick, the relaxation doesn't get
  exercised often and the algorithm degenerates to base.
- Look-ahead bias: each evaluation still uses `order.ts_init` as the
  reference time; only ticks with `tick.ts_event <= order.ts_init` are
  present (replay is strictly chronological). No future trades leak in.
- The mechanism's correctness depends on adverse flow *persisting* across
  the 1-second inter-order interval more often than it dissipates. If
  adverse-flow regimes are heavily ephemeral (lasting <1s), the base's
  forced re-entry might actually be correctly timed (the regime is over
  by order N+1 anyway) and the relaxed gate would over-protect by
  refiring on tail-of-regime flow. I have NOT measured this.

---

## Predicted Backtest Outcome

Direction relative to `aggressor-flow-gate` base on the 12-date train
window:

- `realized_pnl`: **expected to rise** (+3% to +10% vs base, broad
  range given the uncalibrated parameters). Mechanism: a fraction of
  base's forced re-entries fire into still-adverse flow and lose money
  on average; the streak-with-relaxation policy gates a portion of
  those, recovering their lost P&L. The relaxation factor 1.5x ensures
  only the strongest still-adverse cases are gated a second time, so
  we don't over-protect.
- `trade_count`: **expected to fall slightly** vs base's 107,198. Some
  base "forced re-entries" become a second skip under the new policy
  (only when flow is strongly adverse at streak=1). Magnitude: order of
  a few percent — bounded above by base's skip rate (~21.6%), bounded
  below by zero (if relaxed threshold never fires on streak=1).
- `mean_slippage`: **unchanged at 0.0**. Gate only affects which orders
  are submitted, not how fills happen.
- `sharpe_ratio`: should rise if the additional skips have on-average
  positive expected value (i.e. they would have lost money) and the
  per-trade variance does not blow up.
- `max_drawdown_pct`: should be unchanged or slightly improved (fewer
  forced-entries into adverse regimes means slightly less equity-curve
  drawdown).
- `win_rate`: should rise modestly if the additional skips are
  genuinely adverse.
- `is_weighted_bps`: directionally ambiguous. The base flagged a +21.9%
  IS regression vs `simple`; the cascade policy doesn't directly
  address arrival-price quality, but additional skips of orders with
  bad arrival prices might marginally improve it.

**Single-result falsifier**: if `trade_count` is within ±0.5% of base
AND `realized_pnl` is flat or negative vs base, the relaxed threshold
at streak=1 almost never fires — meaning post-skip flow is rarely
*strongly* adverse (> 3 contracts) even when it was barely-adverse
(> 2 contracts) on the prior order. That would falsify the calibration
of the 1.5x relaxation factor and the underlying persistence assumption,
not the cascade-policy mechanism itself.
