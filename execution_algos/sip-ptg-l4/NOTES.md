# Algorithm Notes: sip-ptg-l4

Method: `prompts/prompt-l1.md` (propose -> empirically verify event-class
non-empty -> commit). The active prompt after the loop-3 revert is the
loop-1-evolved method, which requires a numeric N event-count prediction
and a count from the cheapest verification surface; it does NOT require a
counterfactual probe.

## Hypothesis

**One-line:** OVERRIDE the base skip (submit the same-`ts_init` flip OPEN)
only when the in-flight position being closed is currently UNDERWATER by
more than one MES minimum tick (loss_threshold = $0.25 per contract, i.e.,
realized_pnl < -$0.25 at the moment of the CLOSE). Otherwise preserve the
base skip.

**Conditioning axis:** the sign-and-magnitude of the in-flight position's
unrealized PnL at the flip moment, computed from
`position.avg_px_open` and the current top-of-book mid. This is a
**portfolio-state + market-state hybrid axis** — fundamentally different
from the spread-only axis that loops 2 and 3 attacked.

**Why this axis is fresh:**
- Loop 2 conditioned on **spread at on_order()** (added skips when wide).
- Loop 3 conditioned on **spread at on_order()** (added submits when tight).
- Both attacked the same axis with inverted predicates; loop-3's critic
  flagged this as the failure mode.
- Loop 4 conditions on **direction of the in-flight position's unrealized
  PnL** — a property of the *position being flipped*, not the *book at the
  flip moment*.

## Step 1 — Read the base mechanism

The base `position-tier-gate` conditions on `self.cache.positions_open(
instrument_id)` at `on_order()` invocation. The event class is **same-
`ts_init` flip OPENs**: when the oracle emits CLOSE+OPEN at one timestamp,
the OPEN's `on_order()` fires while the CLOSE has been submitted but the
fill has not propagated through the cache. The cache still shows
`abs(net_qty) = 1`, the OPEN's `is_reduce_only = False`, and the gate
returns without submitting. Reduce-only orders bypass the gate.

## Step 2 — Identify ONE plausible weakness

The base treats ALL flip OPENs identically. Two qualitatively different
flip events are folded together:

1. **Flip after losing position** — the in-flight position is underwater;
   the oracle's reversal is corrective (price has moved against the prior
   direction, the new OPEN is in the direction of recent price travel).
   Plausibly positive EV.
2. **Flip after winning position** — the in-flight position is profitable;
   the oracle's reversal is potentially over-extrapolating noise after a
   small gain. Plausibly negative EV, since taking a fresh position at the
   profit moment is "buy high, sell low" relative to mean reversion.

> "In regime X = 'a base-would-skip OPEN whose paired in-flight position
> is currently underwater by more than 1 MES tick ($0.25)', the base skips
> and forgoes the corrective re-entry. If instead it submitted the OPEN,
> the new position rides the corrective leg. Expected outcome W = a few
> percent realized_pnl uplift if corrective re-entries are net positive."

## Step 3 — Propose ONE concrete modification

Add a **loss-corrective override** layered on top of the base gate. The
new branch fires only on OPEN orders that the base would have skipped:

```
if order.is_reduce_only:
    submit_order(order); return

net_qty = abs sum of cache.positions_open(instrument_id) quantities
if net_qty < position_cap:
    submit_order(order); return                # base submit unchanged

# Base would skip — check loss-corrective override.
quote = self.cache.quote_tick(instrument_id)
positions = self.cache.positions_open(instrument_id)
if quote is not None and positions:
    pos = positions[0]                          # netting OMS: at most one
    mid = (float(quote.ask_price) + float(quote.bid_price)) / 2.0
    entry = float(pos.avg_px_open)
    side_factor = +1.0 if pos.side == BUY else -1.0
    unreal_per_contract = (mid - entry) * side_factor
    if unreal_per_contract < -loss_threshold:   # underwater by > 1 tick
        submit_order(order); return             # OVERRIDE — submit the flip
return                                          # default: preserve base skip
```

Default `loss_threshold = 0.25 USD` per contract = 1 MES tick.

Constraints:
- Quantity invariant: only submit/skip routing, no quantity modification. OK.
- top_of_book_only: no book walking, just submit/skip decision. OK.
- participation_cap: order quantity unchanged from strategy emission. OK.
- intraday_flat: reduce-only orders always submit unconditionally. OK.

## Step 4 — MANDATORY empirical pre-check

### 4a. Prediction N

> "If my hypothesis is non-vacuous, the new override branch will fire
> **at least N = 100 times per day** on average across the 12-date train
> window."

Reasoning: the base skips ~7,500 flip OPENs/day. The in-flight position's
unrealized PnL at the flip moment has some distribution roughly centered
around 0. Conditional on a flip happening (the oracle reversed), the
distribution is somewhat skewed toward losses (the oracle reverses more
when its prior direction was wrong). I expect 10-30% of flip moments to
find the in-flight position underwater by > 1 tick. That gives 750-2,250
fires/day. N = 100 is a conservative floor at ~5% of estimate.

### 4b. Verification surface

Cached `execution_algos/sip-ptg-l2/results/<YYYYMMDD>/positions.csv` for
all 12 train dates. **Caveat:** sip-ptg-l2 skipped ~10,785 wide-spread
OPEN positions, so this surface UNDERCOUNTS the base's positions. The
remaining 81,557 positions are the base's tight-spread subset. The base's
true skipped-flip-OPEN count is closer to 92,000 positions × ~98%
flip-paired = ~91,000 over 12 dates (the base submitted 90,433 trades,
of which most are flip pairs).

Per closed position, `realized_pnl` (in `'X.XX USD'` format) captures the
PnL accumulated from open to close. At the flip moment (= the moment of
CLOSE), unrealized = realized within a microsecond of slippage. So
`realized_pnl < -loss_threshold` proxies "in-flight position underwater
at flip" reliably.

(Why not the BASE's positions.csv directly? It's gitignored and not
preserved across commits; the cached `metrics.json` aggregates lose
per-position detail. sip-ptg-l2's positions.csv is the closest
preserved artifact and is behaviorally a subset of the base's stream.)

### 4c. Count and compare

| threshold (USD/contract) | n positions | per-day | sum_pnl ($) | mean_pnl |
|---|---|---|---|---|
| rpnl < -0.25  | 12,652 | 1,054 | -9,337.00 | -0.738 |
| rpnl < -1.25  |    816 |    68 | -1,526.25 | -1.870 |
| rpnl < -2.50  |     62 |     5 |   -207.00 | -3.339 |
| rpnl < -3.75  |      7 |     1 |    -34.25 | -4.893 |
| rpnl < -5.00  |      2 |     0 |    -10.75 | -5.375 |

With `loss_threshold = 0.25 USD`: 12,652 events across 12 dates → **1,054
fires/day** average. PASS (10.5× the N=100 floor).

Bonus signal: among these 12,652 events, the in-flight positions
collectively realized -$9,337. This means the prior direction was
**demonstrably wrong** on aggregate. The flip-direction OPEN we are
proposing to submit is the OPPOSITE direction, which is (heuristically)
the *corrective* direction. This is the EV-positive setup the hypothesis
relies on.

### 4d. Not invoked

Prediction was estimable.

## Empirical pre-check

- **Prediction:** N = 100 override fires per day.
- **Verification surface:** `execution_algos/sip-ptg-l2/results/
  <YYYYMMDD>/positions.csv` across all 12 train dates, filtered to
  `realized_pnl < -0.25 USD` (in-flight position underwater by > 1 tick at
  flip moment, proxied by the closed position's realized_pnl).
- **Actual:** 12,652 events across 12 dates = 1,054 per day on average.
- **Decision:** PASS (actual >= 10× N floor).
- **Justification:** the targeted event class is highly non-empty, the
  sign of the targeted subset's prior-direction PnL is strongly negative
  (-$9,337 across the subset), and the count is robust to the ~12%
  undercount from using sip-ptg-l2's positions.csv as the surface.

## Step 5 — Direction and magnitude

- **realized_pnl: ↑ vs base, a few percent (likely +3% to +10%).**
  Reasoning: ~1,054 new OPENs/day fire on a conditional set where the
  prior direction was wrong by > 1 tick. If even a modest fraction of
  these capture corrective momentum at ~$0.50 per contract, the isolated
  upside is ~$6,300 over 12 days = ~+150% on base $4,262. But chain
  effects (loop-2/3 lesson) will erode this substantially — possibly to
  the point of reversal. Conservative band: +3% to +10%, with
  acknowledged risk of net negative if chain effects dominate.

- **mean_slippage: unchanged.** No book walking, no quantity modification.
  Submitted orders fill at top-of-book like the base; skipped orders
  contribute 0 to mean slippage.

- **trade_count: ↑ vs base, +5% to +15%.** New OPENs + their paired
  CLOSEs (intraday_flat) ≈ ~2× the OPEN-fire rate in new positions.
  ~25K additional positions on a base of 90,433 = ~+28% upper bound;
  chain disruption likely caps actual at +5% to +15%.

## Step 6 — Implement

See `execution_algorithm.py`. Mirror of step 3 mechanism:
- `position_cap` parameter (default 1) — inherits base behavior.
- `loss_threshold` parameter (default 0.25 USD/contract) — override
  triggers when in-flight unrealized PnL per contract < -loss_threshold.
- Read `self.cache.quote_tick(instrument_id)` for mid; read
  `self.cache.positions_open(instrument_id)[0]` for the in-flight
  position; compute sign-adjusted unrealized PnL per contract using
  `avg_px_open` and the order's side enum (BUY/SELL).
- If quote is missing OR positions list is empty: preserve base skip
  (fail closed on missing data — do not override blindly).

## Honesty notes

- The verification surface (sip-ptg-l2 positions.csv) is the base minus
  ~10,785 wide-spread positions. Wide-spread regimes overlap with
  underwater regimes (fast price moves widen spreads AND drive losses),
  so the TRUE base count of underwater flips is plausibly 15-25% higher
  than the 1,054/day I report. The N=100 PASS is robust to this.
- Loops 2 and 3 falsified the linear-EV assumption that "subset PnL on
  the cached surface = aggregate PnL delta after the change." This
  hypothesis ADDS submits rather than removing them, so the chain effect
  is less destructive (existing orders are unchanged; new orders are
  added) — but it is not zero. I expect the actual aggregate delta to be
  noticeably smaller than the isolated +$6,300 implied by 1,054/day ×
  $0.50 × 12 days, and possibly to flip sign if the corrective-momentum
  heuristic is wrong.
- The `position.avg_px_open` field is the field name used by Nautilus
  per the sip-ptg-l2 positions.csv schema (column name confirmed:
  `avg_px_open`). The order's side enum is `OrderSide.BUY` /
  `OrderSide.SELL`; I read it from `order.side` or the position's
  `pos.side` accordingly.
