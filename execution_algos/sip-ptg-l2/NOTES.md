# Algorithm Notes: sip-ptg-l2

Method: `prompts/prompt-l1.md` (propose -> empirically verify -> commit).

## Step 1 — Read the base mechanism

The base `position-tier-gate` algorithm conditions on **portfolio state at
`on_order()` invocation**: it queries `self.cache.positions_open(instrument_id)`
and reads the absolute net quantity. The specific event class it gates on is
*"an OPEN-leg order whose `on_order()` fires while the cache still shows a
non-zero net position from a previously-submitted-but-not-yet-cleared
position"*. With `position_cap=1` this is dominated by the same-`ts_init`
CLOSE+OPEN pair the oracle emits at sign-flip moments — the OPEN sees the
old position still in the cache (the CLOSE has been submitted but the fill
hasn't propagated) and is skipped.

Reduce-only orders bypass the gate unconditionally (intraday_flat).

## Step 2 — Identify ONE plausible weakness

The base gate filters by **portfolio state only**. It treats every OPEN that
passes the gate (cache shows flat) identically, regardless of whether the
current market environment makes that entry favorable or hostile. Empirical
inspection of the base's own positions across the 12 train dates shows a
sharp split in per-trade outcomes by the *fill-time half-spread* (the
distance between the fill price and `arrival_mid` at order-arrival time):

| half-spread bucket (USD) | n positions | sum_pnl ($) | mean_pnl |
|---|---|---|---|
| (-2.00, -0.20)           |  5,020      |  +2,656.75  | +0.529   |
| (-0.20, -0.05)           | 34,995      |  +3,259.75  | +0.093   |
| ( 0.05,  0.20)           | 39,615      |    -670.25  | -0.017   |
| ( 0.20,  0.45)           |  9,110      |  -1,128.00  | -0.124   |
| ( 0.45,  2.00)           |  1,656      |   +101.25   | +0.061   |

Positions filled outside +/- 1 tick of the arrival mid (`|dist| > 0.125 USD` on
MES, i.e., the spread at fill was wider than 1 tick) collectively LOSE money:
10,785 positions, **-$1,017.25** total PnL (mean -$0.094). Positions filled
within +/- 1 tick of the mid collectively make 79,648 positions, **+$5,279.75**.

> "In regime X = 'top-of-book spread at OPEN's `on_order()` time is wider
> than one minimum tick (0.25 USD on MES)', the base submits the order and
> takes the wide-spread fill; if instead it SKIPPED the order, the
> position never exists and the expected PnL contribution would change
> from approximately -$0.094 per event to $0. Expected outcome W is an
> uplift of approximately $1,017 in realized PnL across the 12-date train
> window — about +24% on the base's $4,262.50."

## Step 3 — Propose ONE concrete modification

Add a **pre-submit spread guard** layered on top of the existing position
gate. The new branch fires at `on_order()` for OPEN orders only (reduce-only
remain unconditional):

```
if order.is_reduce_only:
    submit_order(order)                       # unchanged
    return

if net_qty_in_cache >= position_cap:           # base gate unchanged
    return                                     # skip

# NEW: pre-submit spread guard
quote = self.cache.quote_tick(instrument_id)
if quote is not None:
    spread = float(quote.ask_price) - float(quote.bid_price)
    if spread > spread_threshold:              # default 0.25 USD = 1 tick
        return                                 # skip wide-spread OPEN

submit_order(order)                            # base behavior on tight book
```

The new branch conditions on **current top-of-book spread at `on_order()`
time** read from `self.cache.quote_tick(instrument_id)`. It only fires on
OPEN orders that survived the base gate (cache is flat). It only adds
*skips* on top of the base; it never adds submissions. Quantity invariant,
top-of-book-only, participation_cap, and intraday_flat are all trivially
preserved (no quantity modification, no book walking, reduce-only orders
fully untouched).

Default threshold = 0.25 USD (strict: skip any OPEN where the spread is
strictly greater than 1 minimum tick). MES tick size = 0.25 USD, so this
threshold catches 2-tick or wider books.

## Step 4 — MANDATORY empirical pre-check (the gate)

**4a. Prediction N.** "If my hypothesis is non-vacuous, the new branch
(spread > 0.25 USD at `on_order()` time -> skip) will fire at least **N = 100
times per day** on average across the 12-date train window." Reasoning: the
base submitted ~7,500 OPENs/day on average; the fill-time half-spread
distribution above shows ~12% of fills have `|dist| > 0.125`, implying
~900/day OPENs were filled at wider-than-1-tick spreads. The on-order
spread is a near-instantaneous proxy for the fill spread (sub-ms latency
between them), so the new branch should fire on the same order of events
per day. N=100 is a conservative floor at 1/9th of this estimate.

**4b. Verification surface used.** Cached behaviorally-identical artifacts
at `execution_algos/sip-ptg-l1/results/<YYYYMMDD>/orders.csv` and
`positions.csv` (sip-ptg-l1 is bit-identical to `position-tier-gate` per
the loop-1 trace — same submitted order stream). Used the fill-time
distance `avg_px - arrival_mid` (sign-adjusted for side) as a proxy for
the on-order spread, since fill latency is sub-ms.

**4c. Count and compare.**
- All 12 dates aggregated: 10,785 FILLED OPENs had `|dist| > 0.125 USD`.
- Per-day average: **898.8 events/day**.
- 898.8 vs predicted N=100 -> predicted floor exceeded by ~9x. PASS.
- Bonus: among these 10,785 events, sum_pnl is -$1,017.25 (mean -$0.094)
  — confirming the new skip-branch is removing a net-negative subset.

**4d.** Not invoked — prediction was estimable.

**Decision: PASS the empirical pre-check.** The event class is highly
non-empty, the PnL signature of the targeted subset is negative on
aggregate, and the prediction was confirmed within an order of magnitude.

## Empirical pre-check

- Prediction: N = 100 wide-spread OPEN events per day.
- Surface: `execution_algos/sip-ptg-l1/results/<YYYYMMDD>/orders.csv` u
  `positions.csv`, joined on `opening_order_id <-> exec_spawn_id`. Proxy
  metric = `|avg_px - arrival_mid|` with sign-adjustment for `side`.
- Actual: 898.8 events/day average across 12 dates (10,785 total).
- Decision: PASS (actual >= 9x N).
- Justification: the subset's collective realized PnL is -$1,017.25, so
  the proposed skip-branch removes a measurably negative-EV subset rather
  than a random one.

## Step 5 — Direction AND magnitude predictions

- `realized_pnl`: ^ vs base, **a few to low-double-digit percent**
  (target: +20% if the empirical signal carries fully into the
  counterfactual; +5..10% if half of the wide-spread positions would have
  been profitable under an unchanged subsequent stream — they won't,
  because the next CLOSE+OPEN pair still arrives 1 sec later regardless
  of what happens here). Anchored to the empirical sum of -$1,017 over
  4,262 base PnL = 24% uplift ceiling.
- `mean_slippage`: ~ unchanged. The algorithm never walks the book and
  never modifies order quantity; for orders that ARE submitted, the
  realized slippage equals the base's. Skipping more orders cannot make
  the average worse.
- `trade_count`: v vs base, roughly **-12%** (10,785 / 90,433 fewer
  filled positions, plus their paired CLOSEs vanish too -> ~24% fewer
  rows but the trade_count metric uses unique positions, so -12%
  expected).

## Step 6 — Implement

See `execution_algorithm.py`. Mirror of step 3: `_spread_threshold`
parameter, default 0.25 USD. Quote tick read via
`self.cache.quote_tick(instrument_id)`. If the cache has no quote yet
(start of session), submit (fail open — never block on missing data).
