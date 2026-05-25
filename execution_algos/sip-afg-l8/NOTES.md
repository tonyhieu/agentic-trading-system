# sip-afg-l8 — Hypothesis

## Hypothesis (per `.current_prompt.md` Step 1-4, base_algo=aggressor-flow-gate)

**Step 1 — base mechanism.** `aggressor-flow-gate` maintains a 10-second
rolling deque of `(ts_event_ns, signed_volume)` from trade ticks. Signed
volume is `+size` for BUYER aggressor prints, `-size` for SELLER aggressor
prints, 0 for NO_AGGRESSOR. At each open order, prune entries older than
`window_seconds`, sum `net_flow` over the surviving deque, and skip the
open if `net_flow` is adverse beyond `flow_threshold = 2.0` contracts.
After any skip, force-submit the next open unconditionally
(`_position_flat = True`).

**Step 2 — one plausible weakness.** The signed-volume input is
*unclipped*: a single very large trade print (e.g. 50–200 contracts on
one tick, which does happen in MES around macro events and at session
opens) dominates `net_flow` for the full 10-second window. In that
case the gate is firing because of ONE big aggressor event that has
already been priced into the tape, not because of *broad-based*
sustained aggressor pressure across many participants. Many of those
single-print-dominated skips are likely false positives: the directional
impulse from one big sweep has typically already been absorbed by the
time the next oracle signal arrives, so skipping subsequent entries
into that "stale" direction sacrifices good trades.

**Step 3 — one concrete modification.** Clip each individual print's
contribution to ±`max_print_size` contracts before appending it to
the deque. With `max_print_size = 5` (default), a 100-lot SELLER print
contributes -5 (not -100) to the rolling sum. The rest of the algorithm
is identical to base: same 10s window, same `flow_threshold = 2.0`,
same anti-cascade flag. The skip decision now requires *at least*
~2 net adverse prints of meaningful (>=5-lot) size in the window —
i.e. evidence of broad-based directional flow rather than a single
sweep.

**Step 4 — expected direction vs base.**
- `realized_pnl`: directionally up vs base. Removing the
  single-print-dominated false positives should let through better
  entries the base skips. Magnitude is hard to pin without
  measurement; rough estimate +2% to +10% vs base ($1255.50) →
  $1280–$1380.
- `mean_slippage`: unchanged (= 0; the slippage model used by the
  backtest engine prices fills at the touched side of the book; no
  fill-mechanics change).
- `trade_count`: directionally higher than base (fewer skips because
  the gate is harder to trigger). Probably +1–4% vs base trade count.
- `sharpe_ratio` / `max_drawdown_pct` / `win_rate`: directionally
  similar to base, slightly better if the false-positive skips were
  marginally losing entries; broadly similar otherwise.

## Implementation Decisions

- Default `max_print_size = 5.0`. Rationale: the base
  `flow_threshold = 2.0` contracts is "tiny" (per base NOTES.md, a
  meaningful but low bar). With `max_print_size = 5`, a single
  maximally-clipped print contributes 5, which is 2.5x the threshold
  — still enough that a string of 2–3 consistent same-side big prints
  would trigger a skip, but a SINGLE big print can no longer
  unilaterally trigger a skip on its own contribution alone (it
  would need another ≥0-sized same-side print to push past 2.0…
  actually a single 5-clipped print of -5 *would* push past
  -threshold of -2.0; see below).

- Reconsideration: with `max_print_size = 5` and `flow_threshold = 2`,
  a single 5-clipped print still triggers a skip. To genuinely
  require broad-based flow, `max_print_size <= flow_threshold = 2`
  would force ≥2 prints. But that is so aggressive it almost makes
  the gate count-based not volume-based. A middle value
  `max_print_size = 3` (1.5x threshold) means a single big print
  contributes 3 (over threshold 2) but with marginal cushion — a
  contrary 1-lot print would already cancel it. I'll go with
  `max_print_size = 3.0` as the default. This is the single
  parameter tweak the modification introduces.

- All else identical: same window_seconds = 10.0, same flow_threshold
  = 2.0, same anti-cascade flag, same reduce-only/warm-up handling.

- Look-ahead: still none. The clipping is purely a function of
  `tick.size`, which is known at `on_trade_tick` time.

- Constraints: quantity invariant (only submit/skip, never modify
  quantity), top-of-book-only (no fill mechanics change),
  participation_cap (no sizing change), intraday_flat (reduce-only
  unchanged) all preserved.
