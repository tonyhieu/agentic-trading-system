# Algorithm Notes: sip-afg-l3

## Hypothesis

**Mechanism**: Same rolling signed aggressor-flow gate as
`aggressor-flow-gate` (10s window, `flow_threshold = 2.0` contracts),
but require **two-window confirmation** before skipping. Maintain BOTH
the existing 10s deque and a second 3s deque of the same signed-volume
(`+size` BUYER aggressor, `-size` SELLER aggressor, `0` NO_AGGRESSOR)
prints. For BUY orders, skip only when
`net_flow_10s <= -2.0 AND net_flow_3s <= -1.0`. For SELL orders, skip
only when `net_flow_10s >= 2.0 AND net_flow_3s >= 1.0`. If only the 10s
window is adverse but the 3s window is neutral or favorable, submit
unconditionally. Reduce-only orders always submit (intraday_flat). The
anti-cascade `_position_flat = True` reset after any skip is preserved.

**Inefficiency exploited**: The base algo's NOTES.md "What
underperformed" section flags the canonical weakness in its own words:
"the filter holds back entries during adverse-flow periods, but those
exact moments sometimes offer the best fill prices" — manifesting as a
+21.9% IS regression vs `simple`. Mechanically, the 10s single-window
gate fires on the TAIL of a transient flow burst that has already
reversed: an aggressive 10-contract buy sweep at t=-9s leaves
`net_flow_10s = +10` for nearly 10 more seconds, but if no further
buying continues in t = [-3s, 0], the buying pressure is over — the
market has already absorbed it and the offer is no longer being lifted.
The base algo skips SELL orders in this regime even though the adverse
pressure has dissipated. By requiring confirmation from a short
3-second window, the gate fires only when the adverse flow is
*currently active* (recent prints continue in the same direction), not
when it is a stale-but-still-windowed legacy of a burst that has ended.
This addresses over-skipping during transient bursts while preserving
skips during genuinely sustained adverse pressure.

**Why it survives costs**: The change is purely a gate condition — the
algorithm still only decides whether to call `submit_order(order)` or
not. No order quantity is ever modified (quantity invariant). No fill
mechanics change, so `top_of_book_only` and `participation_cap` are
unaffected (the algorithm does not size or route fills). Reduce-only
orders still bypass the gate, so `intraday_flat` is preserved.
`mean_slippage` should remain 0 in the zero-fill-cost model.

**Builds on**: `aggressor-flow-gate` (the SIP base algo for this
experiment arm). Single concrete change: a second 3-second window is
introduced as a confirmation requirement. The 10s gate threshold (2.0
contracts) is held unchanged from base; only the additional 3s/1.0
confirmation is new.

**Alternatives considered**: None explored — the seed prompt-l0
method (Steps 1–4) calls for picking ONE weakness and ONE concrete
modification. I have not run EDA on the 3s/1.0 parameter choice, have
not swept alternatives, and have not compared against a 5s or 2s
confirmation. Per the experimental boundary I am not allowed to
improvise additions to the method (the critique phase needs to see the
method's gaps in the trace).

---

## Implementation Decisions

- **Second window length (3.0s)**: Chosen as roughly one-third of the
  outer window. Short enough that "still active" pressure must be very
  recent; long enough to accumulate at least 2–3 prints under typical
  MES trade arrival rates. Not calibrated against train data — the
  seed prompt does not require it.

- **Confirmation threshold (1.0 contract)**: Chosen by proportional
  reasoning. The 3s window is ~30% of the 10s window; a proportional
  threshold would be 0.6 contracts. Rounded up to 1.0 so a SINGLE
  recent aggressor print of size 1 (the MES modal trade size) is the
  minimum confirmation — i.e. at least one fresh aggressor print in
  the last 3 seconds must agree with the 10s direction. Below 1.0 the
  confirmation would degenerate to "any nonzero 3s flow", which is
  too weak. Not calibrated against train data — flagging here so the
  critique phase can see the armchair choice.

- **Both gates use the same trade-tick stream**: A single
  `on_trade_tick()` callback updates both deques. The 3s deque is
  pruned with `cutoff_ns = order.ts_init - 3_000_000_000` at gate
  evaluation; the 10s deque uses `cutoff_ns = order.ts_init -
  10_000_000_000`. Both running sums (`_net_flow_10s`, `_net_flow_3s`)
  are updated in O(1) per print and re-pruned in O(k) on each gate
  evaluation.

- **AND semantics, not OR**: The two conditions must BOTH be adverse
  for a skip. This is the stricter gate. The hypothesis is that the
  base algo over-skips (fires when only the 10s condition holds while
  the 3s shows the pressure is over). OR semantics would fire MORE
  often, not less — opposite of what the hypothesis predicts.

- **Asymmetric scaling preserved**: Both windows use the same +size /
  -size signing convention as the base algo. NO_AGGRESSOR prints
  contribute 0 to both deques.

- **Warm-up handling**: If EITHER deque is empty at evaluation, skip
  the gate evaluation and submit unconditionally. This matches the
  base algo's warm-up behavior (empty 10s deque → submit) and avoids
  spurious gates during the first few seconds of session.

- **Anti-cascade**: After any skip, `_position_flat = True` so the
  next open is unconditional. Preserved verbatim from base.

- **Constraint compliance**: Quantity invariant preserved (only
  submit/skip decisions, never modify order.quantity).
  `top_of_book_only`, `participation_cap`, `intraday_flat` all
  preserved because the change is gate-only.

**Concerns**:
- The 3s/1.0 choice is uncalibrated. If real MES trade arrival density
  in 3s windows is much higher than I assume, the 1.0 threshold is too
  loose and the confirmation rarely "fails" — meaning the gate fires
  almost as often as the base, and the algo degenerates toward base.
  If arrival density is sparse, the 1.0 threshold is too tight and the
  gate almost never fires — meaning many adverse orders no longer get
  skipped, possibly worsening P&L. I have NOT measured this. Per the
  seed prompt's method I am not running an EDA calibration step.
- Look-ahead bias: each evaluation uses `order.ts_init` as the
  reference time for both deque prunes, and only ticks with
  `tick.ts_event <= order.ts_init` are present (replay is strictly
  chronological). No future trades leak in.
- The mechanism predicts an improvement in IS (the base's flagged
  weakness) but this metric is not on the SIP critique gate. The
  primary metrics that ARE on the gate are realized_pnl, mean_slippage,
  sharpe_ratio, max_drawdown_pct, win_rate. The IS improvement is
  *necessary but not sufficient* for realized_pnl improvement: P&L
  could rise (recovered profitable orders that base skipped) OR fall
  (recovered orders that were genuinely adverse and only looked
  recoverable because the 3s window happened to be neutral).

---

## Predicted Backtest Outcome

Direction relative to `aggressor-flow-gate` base on the 12-date train window:

- `realized_pnl`: **expected to rise** (+5% to +20% vs base). The
  recovered SELL/BUY orders that pass the 10s gate but fail the 3s
  confirmation are by hypothesis the "good fills at temporarily-
  favorable arrival prices" — orders the base skips because the 10s
  window is still adverse, but where the adverse pressure has already
  dissipated.
- `trade_count`: **expected to rise modestly** (+1% to +6% vs base's
  107,198). Fewer skips → more orders pass through. The magnitude is
  bounded by the fraction of base's ~21% skip rate that has stale flow
  but quiet 3s confirmation. I don't have a number for that fraction —
  flagging as uncertain.
- `mean_slippage`: **unchanged at 0.0**. Gate only affects which
  orders are submitted, not how fills happen.
- `sharpe_ratio`: directional uncertainty. If recovered orders are
  positive on average AND not highly variant, sharpe improves. If
  they're noisy, sharpe drops even with rising P&L.
- `max_drawdown_pct`: slightly worse possible (more orders submitted
  during volatile periods means slightly more equity-curve variance).
- `win_rate`: directional uncertainty.
- `is_weighted_bps`: **expected to improve** (decrease). This is the
  metric the base's NOTES.md specifically flagged as regressed.

Single-result falsifier: if `trade_count` is flat (±1% of base) AND
`realized_pnl` is flat or negative, the 3s confirmation almost never
"vetoes" a base-gate skip — meaning the 1.0 threshold is too loose
(any trade in 3s suffices) and the algo has effectively degenerated to
base. That would falsify the uncalibrated 3s/1.0 parameter choice,
though not the underlying mechanism.
