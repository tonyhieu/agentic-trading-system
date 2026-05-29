# Algorithm Notes: sip-ptg-l1

## Hypothesis

**Generated via the seed prompt's 4-step single-pass method.**

**Base mechanism (position-tier-gate, cap=1)**: When the oracle fires its
same-timestamp CLOSE+OPEN pair, the OPEN's `on_order()` sees the cache
still showing the old position (CLOSE not yet filled). With cap=1, the
new OPEN is unconditionally skipped. This serializes entries — one in,
one out, with a forced gap — and produced +204.9% PnL on the train window.

**Identified weakness**: The cap=1 gate is *direction-blind*. It treats two
qualitatively different oracle events as the same:
  1. **Flip re-entry** — old position long, new OPEN sells (or vice versa).
     This is the oracle changing its mind mid-tick. At sigma=6 with
     1-second cadence, many flips are mean-reverting noise; filtering
     them is correct.
  2. **Continuation re-entry** — old position long, new OPEN buys again.
     Same-side re-entry means the oracle's posterior on direction did
     not change; only the position lifecycle forced a round-trip. These
     carry persistence information that the indiscriminate skip discards.

By skipping continuations along with flips, the baseline likely leaves
positive-EV trades on the table — the gate's "filter rate" is too high
in regimes of persistent directional signal.

**Proposed modification (one concrete change)**: Add a directional-
continuation pass-through layer. At `on_order()` for a non-reduce-only
order:
  - If flat / below cap → SUBMIT (unchanged).
  - If at/above cap AND `sign(open_position) == sign(incoming_order)` →
    SUBMIT (continuation).
  - If at/above cap AND opposite signs → SKIP (flip — as base algo).

New gate input: the *signed direction* of the in-flight position
relative to the incoming order's side (BUY vs SELL).

**Why constraints hold**: No order quantity is touched (quantity
invariant preserved). Top-of-book and participation_cap are upstream of
the exec algo and unaffected — we only choose submit vs skip. The
same-timestamp CLOSE has been submitted alongside this OPEN, so the
position will round-trip through flat regardless; net exposure never
exceeds 1 contract by the time the OPEN actually fills.

**Expected directional outcomes vs position-tier-gate**:
  - `trade_count`: ↑ (continuations now pass). Still ≪ baseline `simple`.
  - `realized_pnl`: ↑ if continuation re-entries are positive-EV. The
    sign of the change is the empirical question the backtest answers.
    My prediction is ↑, on the theory that persistence in the oracle's
    signed output is correlated with persistence in true direction —
    flips are noise-driven, continuations are signal-driven.
  - `mean_slippage`: ≈ 0 (unchanged). Both base and this algo only
    decide submit/skip; neither modifies pricing or routing.
  - `sharpe_ratio`, `max_drawdown_pct`, `win_rate`: direction uncertain.
    Adding continuations adds more samples; if they are positive-EV the
    Sharpe should improve; if they are noisy the drawdown could widen
    slightly but the cap=1 invariant still bounds it tightly.

## Implementation Decisions

- `position_cap=1` (same as baseline). The continuation pass-through is
  the only behavioral change; we explicitly keep the trigger threshold
  identical so the comparison isolates the directional cut.
- `cache.positions_open(...)`: in the netting OMS we expect at most one
  position per instrument; we sum signed quantities defensively so the
  algo would behave correctly under a non-netting OMS, but the typical
  call returns 0 or 1 positions.
- Direction encoded as `sign(signed_decimal_qty)` for the position and
  `+1 for OrderSide.BUY / -1 for OrderSide.SELL` for the order.
- No new state. Direction comes from the cache at on_order(); no
  rolling counters or feature buffers — keeps the algo stateless and
  reset-free.

## Reasoning Trace

See `experiments/self_improving_prompt_experiment/position-tier-gate/reasoning-traces/loop-1-trace.md`.
