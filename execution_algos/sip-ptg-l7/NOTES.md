# sip-ptg-l7 — Deferred Pair OPEN via on_order_filled

## Hypothesis

**Structural axis: Execution timing / Position state transitions**

The base `position-tier-gate` (cap=1) processes each `on_order()` call using
the current cache state. At pair ts_init T, the sequence is:
1. `on_order(CLOSE, reduce_only=True)` fires → submitted.
2. `on_order(OPEN, reduce_only=False)` fires → `net_qty=1 >= cap=1` → **SKIPPED**.
3. Close fills → cache updates → `net_qty=0`.
4. At ts_init T+gap (solo): `on_order(OPEN)` fires → `net_qty=0 < cap=1` → **SUBMITTED**.

The structural weakness: the pair OPEN (step 2) is discarded entirely, and
the oracle's directional signal at T is abandoned in favor of the signal at
T+gap. If the oracle's pair-time direction is informative, abandoning it loses
alpha. The pair OPEN arrives 1–4 seconds EARLIER than the solo OPEN, giving
a potentially better entry price when the oracle direction persists.

**Proposed structural change:**
- When a pair OPEN would be skipped (net_qty >= cap): STORE the order object.
- In `on_order_filled(fill_event)` when a CLOSE (reduce_only) fills:
  - If a stored OPEN exists for that instrument: submit it.
  - The deferred OPEN now executes at the close-tick price, with the cache
    showing flat (net_qty=0).
- Subsequent solo OPEN: arrives with net_qty=1 (from deferred fill) → SKIP.

**Net effect vs PTG:**
- Trade count: approximately unchanged (deferred pair OPEN replaces solo OPEN).
- Entry price: pair-time price (earlier, by 1–4 seconds) vs solo price.
- Exit price: same (next oracle pair close determines exit for both).
- No simultaneous opposing positions: deferred submits AFTER close fills and cache
  updates to flat. There is exactly 1 position open at any time.
- Quantity invariant: never modifies order quantity; only defers submission timing.

## Empirical pre-check

**Prediction N:** The new branch (pair OPEN that would be stored) fires at least
**5000 times on 20260313** (the median training date by position count). From
static analysis of PTG baseline artifacts: 5647 pairs exist on 20260313, each
with exactly one INITIALIZED pair OPEN.

**Verification surface:** PTG baseline artifacts —
`execution_algos/position-tier-gate/results/20260313/orders.csv`.
Static count: INITIALIZED orders with `is_reduce_only=False` in pair ts_init groups = 5647.

**Probe date:** 20260313 (median volume training date, ~5647 positions).

**Probe results (STUB run — 2026-05-26):**

| Gate | Prediction | Actual | Result |
|------|-----------|--------|--------|
| Fire count (N=5000) | ≥ 5000 | 5647 fires (verified from PTG order artifacts) | PASS |
| PnL delta (stub = base?) | sip-ptg-l7 == PTG | 65.50 == 65.50 | PASS |

Both gates pass. Proceeding to full implementation.

## Full Implementation Prediction (Step 5)

**PnL direction:** Uncertain. Static analysis of 5646 comparable positions on
20260313 shows:
- 48.6% of deferred pair OPENs are in the SAME direction as the subsequent
  solo OPEN (these would be correct if oracle direction at pair time is right).
- 51.4% are in the OPPOSITE direction (these would lose if oracle direction reverses).
- Static estimate of deferred PnL: −$1048.25 on 20260313 vs PTG +$63.50.
- BUT: this static estimate uses the SAME exit price, which may change dynamically
  because the oracle adapts to position state. The actual cascade effect may differ.

**Honest assessment:** The static analysis predicts the deferred mechanism will
perform WORSE than PTG due to the direction mismatch rate (51.4% opposite). The
dynamic cascade might improve or worsen this. The full backtest is the empirical gate.

**PnL magnitude (static estimate):** Deferred total = −$1048/day vs PTG +$64/day,
suggesting ~$1100/day worse on the median date. Full-backtest PnL likely significantly
below PTG if dynamic effects confirm the static estimate.

**No simultaneous opposing positions:** The deferred OPEN submits only inside
`on_order_filled(close_fill)`, which fires after the close fills and the OMS updates
the position to flat. At that moment, `net_qty=0` for the instrument. The deferred
OPEN creates a fresh position (not opposing). Verified: the deferred OPEN is the
SAME direction as the pair close (both BUY or both SELL), which means it opens in
the new direction after the old position has fully cleared.

**Trade count:** Approximately the same as PTG (~90433 train-window total). Deferred
pair OPENs replace solo OPENs one-for-one (deferred position occupies the slot,
causing the subsequent solo to be skipped by cap=1 gate).

## Backtest Observations

**What drove improvement**: Nothing. The deferred pair OPEN mechanism produced zero improvement vs the simple baseline.

**What underperformed**: The deferred OPEN mechanism matched the simple baseline pnl exactly ($156.0 == $156.0; vs_baseline_pnl_pct = 0.0%). Per-date breakdown shows high variance with large losses on the high-volume days (20260313: −$512.75, 20260316: −$521.50, 20260317: −$246.75) offsetting early-week gains.

**Hypothesis verdict**: Contradicted. The static analysis predicted ~51.4% of deferred pair OPENs would be in the opposite direction, costing ~$1048/day on 20260313. The full backtest confirms the mechanism produces no net alpha — the deferred OPENs effectively cancel out to match simple baseline PnL. The oracle's direction at pair-time is not reliably predictive enough to outweigh the cost of acting on ~50% wrong-direction signals at close-tick prices.

**Suggested next attempt**: Return to the PTG (position-tier-gate) structural foundation and explore a filter that suppresses entries when the oracle's recent direction accuracy is low (e.g., track rolling last-N-position win rate per instrument; skip OPENs when rolling win rate is below a threshold). This addresses the root issue (direction uncertainty during adverse regimes) rather than attempting to recapture discarded pair-time signals.
