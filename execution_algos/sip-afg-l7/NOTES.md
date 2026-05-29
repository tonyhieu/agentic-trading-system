# Algorithm Notes: sip-afg-l7

## Hypothesis

**Method used**: prompt-l0 — the seed 4-step single-pass linear method.
prompt-l0 is the active `.current_prompt.md` because the L6 critique
proposal (live-instrumentation calibration) was reverted by the
keep/discard gate, restoring L5's `prompt_in` = `prompt-l0.md`.

### Step 1 — Base mechanism

`aggressor-flow-gate` (the locked base algorithm):

- Maintains a 10-second rolling deque of `(ts_event, signed_size)` from
  trade ticks. `signed_size = +size` (BUYER aggressor), `-size` (SELLER
  aggressor), `0` (NO_AGGRESSOR).
- At each opening order, prunes the deque to `[order.ts_init - 10s,
  order.ts_init]` and computes `net_flow = sum(signed_size)`.
- BUY order is skipped if `net_flow <= -flow_threshold` (default
  `flow_threshold = 2.0` contracts); SELL order is skipped if `net_flow
  >=  flow_threshold`.
- Anti-cascade: after any skip, `_position_flat = True` forces the next
  opening order to submit unconditionally.

### Step 2 — ONE plausible weakness

The base gate fires on an ABSOLUTE contract count
(`|net_flow| >= 2.0`) regardless of how many trades happened in the
window. The statistical significance of "2 contracts net adverse" is
very different in different volume regimes:

| Regime          | Total |signed| in window | net_flow = +2 means |
|-----------------|--------------------------|---------------------|
| Slow (4 ticks)  | 4 contracts              | 75% buy-side; strong directional signal |
| Fast (100 ticks)| 100 contracts            | 51% buy-side; statistical noise |

In the fast regime the base gate fires on essentially noise — it skips
an order that has no actual directional signal in the tape. These
false-positive skips cost P&L proportional to the noise rate.

This axis is structurally different from the four prior loops on this
arm:

- L1 (EWMA): re-weighted the contributions WITHIN the window. Did not
  add a denominator.
- L2/L3/L4: side-asymmetry / two-window AND / fraction-normalization
  variants (per the program database). None of these added a true
  volume-regime denominator gate.
- L5 (kept, running best): post-skip CASCADE policy. Orthogonal to the
  decision function entirely. Does not normalize anything.

So "volume-regime normalization of the decision gate" is an unexplored
axis on this arm.

### Step 3 — ONE concrete modification

Add a SECOND, conjunctive condition to the gate:

    skip iff
        ( |net_flow| >= flow_threshold )           # count gate (base)
      AND
        ( |net_flow| / max(total_window_vol, 1.0)  # proportion gate (new)
          >= ratio_threshold )

where `total_window_vol = sum_i |signed_size_i|` over the same 10s
deque (a running scalar updated on each tick add/prune; zero extra
O(N) work — `O(1)` per tick, same as base).

Default `ratio_threshold = 0.20` — at least 20% of total window volume
must be one-sided in the adverse direction. Picked as the smallest
round-number that visibly excludes near-balanced regimes (the math:
at 100 contracts total, 20% one-sided = 60/40 split — clearly
directional; at 4 contracts total, ±2 net trivially satisfies 50%
imbalance — strong base regime preserved). Not calibrated against an
empirical distribution. This is the same kind of armchair number the
base mechanism itself uses for `flow_threshold = 2.0`, and consistent
with the single-pass spirit of the seed prompt method.

The condition is strictly tighter than base (conjunction) → skip rate
can only DECREASE. No order is newly skipped; some base skips are now
submitted instead.

All execution constraints preserved:

- Quantity invariant: only submit/skip; never modify `order.quantity`.
- top_of_book_only: no fill mechanics changed.
- participation_cap: no order sizing.
- intraday_flat: reduce-only orders always submit.
- Anti-cascade: post-skip `_position_flat = True` preserved exactly as
  base — semantics inherited from `aggressor-flow-gate`, NOT from L5
  (which is a parallel axis).
- No look-ahead bias: deque pruning uses `order.ts_init`; ticks with
  `ts_event > order.ts_init` are not yet in the deque (chronological
  replay).

### Step 4 — Expected direction

| Metric                | Expected vs base (`aggressor-flow-gate`)             |
|-----------------------|------------------------------------------------------|
| `realized_pnl`        | small positive (eliminate noise-skip false positives in high-volume regimes) |
| `trade_count`         | INCREASE (some base skips become submits — strict subset filter) |
| `sharpe_ratio`        | flat to slight positive (if removed skips were noise) |
| `max_drawdown_pct`    | flat to slight improvement                            |
| `win_rate`            | flat (noise vs noise)                                 |
| `mean_slippage`       | unchanged at 0.0 (gate-only, zero fill-cost model)    |

If the proportion gate filters out skips that were ACTUALLY adverse
(just happened to be on high-volume), realized_pnl will REGRESS — that
is the falsification path. If the proportion gate has near-zero effect
(few base skips were on high-volume regimes), the algorithm collapses
to base behavior and `trade_count ≈ base trade_count, pnl ≈ base pnl`.

---

## Constraints & invariants — explicit check

- Quantity invariant: code path through `on_order` either calls
  `submit_order(order)` once (passing the unchanged order) or does not
  call submit at all. No quantity is ever set.
- top_of_book_only / participation_cap: not touched. Order sizing is
  the strategy's responsibility; the gate is a pure submit/skip
  decision.
- intraday_flat: `is_reduce_only` orders short-circuit the gate and
  submit immediately.
- No look-ahead: `_prune_window(order.ts_init - window_ns)` only
  considers ticks with `ts_event <= order.ts_init` (the backtest
  delivers ticks in chronological order; future ticks are not in the
  deque at decision time).

---

## Implementation Decisions

- `ratio_threshold = 0.20` — armchair (single-pass spirit). Smaller
  values (e.g. 0.05) would barely fire (gate collapses to base);
  larger values (e.g. 0.5) would gate only on already-very-strong
  imbalances, losing much of base's filter effect.
- `total_window_vol = sum |signed_size|` — uses absolute signed
  volume. NO_AGGRESSOR ticks contribute 0 to both numerator and
  denominator (their direction is unknown, so they don't constitute
  directional volume).
- `max(total_window_vol, 1.0)` floor on the denominator — defensive
  against the edge case of an entirely NO_AGGRESSOR deque (abs sum 0).
  With the floor, the ratio becomes 0 and the gate cannot fire —
  correct: no signed directional flow means no directional signal.
- Anti-cascade behavior is inherited from BASE, not L5. The seed
  prompt method targets a base weakness; mixing in L5's cascade policy
  would confound attribution. If the L7 modification works against
  base, a future loop could compose it with L5's cascade policy.

## Concerns (single-pass uncertainties — flagged for the trace)

- `ratio_threshold = 0.20` is not calibrated against any empirical
  distribution. The seed prompt's single-pass method does not include
  a calibration step. I do NOT know what fraction of base skips have
  ratio >= 0.20 vs < 0.20; this is exactly the question a critic
  reading this trace should latch onto.
- The proportion gate is a strict tightening, so worst-case it does
  nothing (collapses to base). It cannot make things newly broken at
  the constraint level — only weaker as a filter.
- The 20260319 OOM concern from L5/L6: my algorithm adds ONE
  additional running scalar (`self._abs_flow`) and one extra add /
  subtract per tick. No extra deque storage. This is strictly less
  state than L5 (which adds `_skip_streak`). I expect 20260319 to
  complete; if it fails, drop it and flag in the trace, per the
  invocation reminder.
