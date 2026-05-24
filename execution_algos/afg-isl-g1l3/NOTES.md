# Algorithm Notes: afg-isl-g1l3

Island-1, generation-1, loop-3. Base = aggressor-flow-gate. Lineage:
afg-isl-g1l1 (two-window flow-flip reversal — FAIL, pnl -43.1%) →
afg-isl-g1l2 (single-window base + min_trade_count=8 — PnL -21.1%,
IS_bps better, PnL worse).

## Hypothesis

**Mechanism**: Keep the base aggressor-flow-gate's single 10s signed-flow
gate exactly as-is. Add ONE narrow override: when the base gate would
SKIP (adverse net flow >= threshold), submit the order anyway IFF the
mid-price has already moved >= `confirm_ticks` in the order's favor
during the last `confirm_window_seconds` (a short sub-window inside the
10s flow window). All other skip decisions stand. Reduce-only orders
always submit; anti-cascade `_position_flat` rule preserved.

For a BUY order, "favorable" means mid has FALLEN by >= confirm_ticks
(better arrival price). For a SELL order, "favorable" means mid has
RISEN by >= confirm_ticks. Mid is computed from the latest cached
quote tick at order time vs. the cached quote tick from
`confirm_window_seconds` ago (maintained via a small quote-mid deque
fed by `on_quote_tick`).

Defaults:
- `window_seconds=10.0`, `flow_threshold=2.0` — match base.
- `confirm_window_seconds=3.0` — short sub-window inside the 10s flow
  window. Long enough to register an actual mid move, short enough that
  the move is still "fresh" at order time.
- `confirm_ticks=1.0` — 1 MES tick = 0.25 index points. A 1-tick mid
  move in the order's favor over 3s is a small but non-noise
  confirmation that, despite adverse aggressor flow, price action has
  already given a better arrival level. Default deliberately
  conservative — admit only the highest-quality overrides.
- No `min_trade_count` (g1l2 showed it's a PnL regression as a
  standalone change; this loop tests the price-confirmation lever in
  isolation).

**Why this addresses the lessons from g1l1 and g1l2:**

1. **g1l1 lesson — flow-flip is NOT price reversal.** g1l1 used
   short-window flow-direction reversal as a proxy for price reversal
   and was decisively falsified: flow direction can flip while mid
   is still mid-adverse. The corrective is to use mid PRICE itself
   as the confirmation signal, not a flow surrogate.

2. **g1l2 lesson — IS-vs-PnL dissonance.** g1l2 found that
   population-based suppression (min_trade_count) improved IS bps but
   regressed PnL — evidence that the base's flow gate captures
   path-risk information invisible to arrival-price quality. The
   conclusion is *don't* broadly loosen the gate; instead, override
   only the *specific* skipped trades where independent evidence
   (favorable price move) suggests the path risk has already played
   out and the entry is being made at a better-than-arrival level.

3. **Targeted, not broad.** Most adverse-flow skips remain in place
   (preserving the path-risk protection g1l2 surfaced). Only the
   narrow subset where price has confirmed favorable mid movement is
   admitted. This is a structurally safer way to "loosen" the gate
   than population-based admission.

**Predictions:**
- PnL: improvement over both g1l1 and g1l2; expected to be in the
  vicinity of base or modestly above. The override should admit
  trades that are net-favorable on arrival price (good entries the
  base gate over-rejects) without flooding in the noise-dominated
  thin-window trades that hurt g1l2.
- IS_weighted_bps: should improve vs base (admits exactly the trades
  with favorable arrival movement — the population that drives the
  base's documented IS regression).
- Slippage: 0.0 on zero-fill-cost model (unchanged).
- Trade count: small uptick vs base (only the override-eligible subset
  is admitted), substantially below g1l2's broad admission.

**Falsification:**
- If PnL is lower than base, the override is admitting trades that
  are favorable on arrival but still path-loss-dominated within the
  oracle's 30s horizon — supports g1l2's path-risk hypothesis at
  even finer granularity.
- If IS bps does NOT improve, the price-confirmation rule is not
  selecting the trades that drive the base's IS regression — the IS
  regression is structurally elsewhere (e.g., baseline-skipped
  rejection asymmetry rather than admitted-trade arrival quality).

## Implementation Decisions

- **Mid-price source**: derived from cached quote ticks. On each
  `on_quote_tick`, append `(ts_event_ns, mid=(bid+ask)/2)` to a
  `_mid_deque`. Prune entries older than `confirm_window_seconds`
  before each evaluation. The mid "now" is the most recent entry;
  the mid "then" is the oldest entry still inside the window. No
  look-ahead: quote ticks are replayed chronologically.

- **Override condition**: only invoked when the base gate would skip.
  If `_mid_deque` has < 2 entries (warm-up / thin quote stream), do
  NOT override — defer to the base skip. This is the conservative
  default: an override requires positive evidence, and absence of
  evidence is not evidence of favorable movement.

- **Direction sign**: BUY override iff `mid_then - mid_now >=
  confirm_ticks * tick_size`. SELL override iff `mid_now - mid_then
  >= confirm_ticks * tick_size`. Tick size hard-coded to 0.25 for MES.

- **Anti-cascade preserved**: same `_position_flat` rule as base and
  g1l2. If the gate ultimately skips (no override fires), set
  `_position_flat = True` so the next open order is unconditional.

- **Quantity invariant**: never modify `order.quantity`. Only skip
  or submit.

- **Subscription**: `subscribe_trade_ticks` AND `subscribe_quote_ticks`
  on first order (base only required trade ticks; we now actively
  consume quotes for the mid-price deque).

## Backtest Observations

Train window: 2026-03-08 .. 2026-03-20 (12 dates). Numbers are raw from
`results/backtest-results.json` (vs `aggressor-flow-gate` base).

| metric             | afg-isl-g1l3 | aggressor-flow-gate (base) | delta            |
|--------------------|--------------|---------------------------|------------------|
| realized_pnl       | 610.5        | 1255.5                    | -645.0 (-51.37%) |
| sharpe_ratio       | 2.6356       | 5.5944                    | -2.96 (-52.89%)  |
| max_drawdown_pct   | -0.04172     | -0.03325                  | -0.00848 (worse) |
| win_rate           | 0.35325      | 0.35488                   | -0.0016 pp       |
| trade_count        | 118,806      | 107,198                   | +11,608 (+10.83%)|
| mean_slippage      | 0.0          | 0.0                       | 0.0              |
| is_weighted_bps    | 0.04560      | 0.04724                   | -0.00165 (-3.48%)|
| vs_baseline_is_bps | +17.267      | +21.503                   | -4.24 (BETTER)   |

**Verdict: FAIL — sharpest regression of the island so far on PnL,
though IS bps is the best (cleanest arrival quality) of the three loops.**

**Read-out vs the hypothesis predictions:**

1. *Predicted: PnL modestly above or near base.* **Falsified.** PnL is
   -51.4% vs base — worse than g1l2 (-21.1%) and worse than g1l1 (-43.1%).
   The price-confirmation override admits ~11.6k additional trades over
   the base, and the marginal admissions are net-loss-dominated despite
   each one having favorable arrival-mid evidence.

2. *Predicted: IS bps improves vs base.* **Confirmed.** is_weighted_bps
   fell from 0.04724 -> 0.04560 (-3.48%), and vs_baseline_is_bps fell from
   +21.50 -> +17.27 — the largest IS improvement of the island. The
   override is precisely identifying trades with strong arrival-price
   quality.

3. *Predicted: trade count small uptick.* **Partially falsified — direction
   right, magnitude underestimated.** +10.83% admissions, not "small."

4. *Predicted: slippage 0.0.* **Confirmed** (zero-cost fill model).

**Mechanistic interpretation — the dissonance is now explicit:**

g1l2 surfaced an IS-vs-PnL dissonance; g1l3 *amplifies* it. The very
trades with the cleanest favorable arrival-mid evidence (>=1 tick mid
move in the order's favor over a 3s sub-window inside an adverse-flow
10s window) are the WORST PnL contributors on the oracle's 30s horizon.

This is the strongest evidence yet for the falsification clause in the
NOTES: **the base aggressor-flow-gate is rejecting these trades for a
reason that is invisible to arrival-mid quality.** The 3s favorable mid
move within an adverse 10s flow window is more likely a *short-term
mean-reversion bounce inside a continuing adverse flow* than the start
of a genuine reversal — by the time the oracle's 30s horizon resolves,
the original adverse flow has often reasserted itself and the price
that looked "favorable on arrival" has been overtaken.

In other words: **adverse flow + a brief favorable mid bounce is
adverse-selection bait, not a good entry.** The price-confirmation
override systematically selects the bait.

**Falsification of the override design itself:** This is decisive
evidence that loosening the base gate via *any* signal-confirmation
rule that fires DURING adverse flow is a structurally bad direction for
this island. The base gate's value lies in the SKIP itself, not in
sub-window selection of which skipped trades to readmit.

**Updated lesson for island-1 (super-set of g1l2's lesson):**
- IS bps is anti-correlated with PnL on this strategy/base. Treating it
  as the objective will systematically destroy PnL. It is a diagnostic
  for arrival quality only.
- Loosening the base gate via *any* mechanism — population (g1l2),
  flow-reversal (g1l1), or price-confirmation (g1l3) — has consistently
  regressed PnL. The base gate is at or near a local optimum for what
  it does (skipping).
- Any g1l4 attempt should pivot away from "loosen the gate" entirely.
  The remaining promising directions are *complementary* to the base
  gate, not modifications of its skip rule: e.g., add a *second*
  independent gate on a different signal that fires INDEPENDENTLY of
  the aggressor-flow gate (cumulative effect: stricter, not looser),
  or modify what happens *after* a fill (e.g., conditional exit
  acceleration) rather than the entry decision.
