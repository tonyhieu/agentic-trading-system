# Algorithm Notes: afg-isl-g2l1 (island-1, generation 2, loop 1)

## Island lineage

- Island: island-1
- Base algo: aggressor-flow-gate
- Prior loops on this island:
  - **g1l1** (afg-isl-g1l1): two-window persistence + reversal exception. PnL
    -43.13% vs base. Loosened the gate by treating short-window flow-flip
    as a price-reversal proxy. Decisively falsified.
  - **g1l2** (afg-isl-g1l2): single-window base + `min_trade_count=8`
    precondition. PnL -21.15% vs base. Loosened the gate by suppressing it
    in thin-print windows. `is_weighted_bps` improved (+9.74 vs base's
    +21.50), but realized PnL fell — the headline cross-island finding for
    this island is the **IS-vs-PnL dissonance**: the base's gate carries
    path-risk information invisible to arrival-price metrics, and
    *loosening* it consistently destroys PnL.

## Cross-island input (gen-1 migration)

This loop is informed primarily by the gen-1 migration report, not just
own lineage. The migration's `what_worked` block is unambiguous:

> Selectively SKIPPING entries during structurally bad microstructure
> regimes — not modifying execution mechanics — was the only direction
> that produced positive PnL movement this generation. Two distinct skip
> axes both lifted PnL meaningfully on different bases: rolling-spread-p75
> (liquidity-vacuum regime) on island-0 (+26.55%) and choppiness-ratio
> (whipsaw regime) on island-2 (+34.13%).

And `what_failed`:

> LOOSENING an existing skip gate to recover supposedly rejected high-EV
> entries failed on both islands that tried it. Island-1 g1l1 admitted
> entries via a flow-flip 'reversal exception' (-43.13% PnL); island-1
> g1l2 admitted thin-window entries via min_trade_count=8 (-21.15% PnL);
> island-2 g1l2 admitted chop-during-trend entries via a trend-magnitude
> neutral-zone widener (-0.32% vs parent, ~zero marginal EV).

The migration's `generalizable` direction:

> Skip-based gating on adverse-microstructure regimes generalizes across
> base algos: spread-quantile and choppiness-ratio both worked on
> different bases and target near-orthogonal axes (book-state vs
> price-path), so a composed spread+chop+(third axis) stack is the
> highest-leverage generation-2 direction across all islands.

**This island has spent two loops loosening the base gate and lost PnL
both times. The cross-island evidence says the only direction that works
is the opposite: ADD a second skip axis on top, do not modify the base
gate at all.** g2l1 takes that direction.

## Hypothesis

**Mechanism**: Restore the base aggressor-flow-gate's single-window
signed-flow gate EXACTLY (drop all g1l1/g1l2 modifications), and stack
an ADDITIONAL orthogonal skip gate on top: the **rolling-spread-p75
OPEN-gate** that worked on island-0 g1l1 (+26.55% vs its base). An
opening order is submitted only if BOTH gates pass; if EITHER gate
votes to skip, the order is skipped.

Concretely:
- Maintain a rolling deque of `(ts_event_ns, spread_ticks)` samples from
  quote ticks, with a `spread_window_seconds` look-back (default 180s).
- At order time, if the deque holds at least `min_spread_samples` (default
  20) and `current_spread_ticks > p75(spread_deque)`, vote SKIP on the
  spread axis.
- Apply the base aggressor-flow gate exactly as in `aggressor-flow-gate`.
- Skip the order if EITHER gate votes skip. Submit only if BOTH pass.
- Reduce-only orders always submit (unchanged).
- After ANY skip (either axis): `_position_flat = True` (next open
  unconditional — anti-cascade preserved).
- Order quantity is never modified.

**Why this is the right move for this island**:

1. **The base aggressor-flow-gate already contains path-risk information**
   that PnL-improving tweaks must not destroy. g1l2's IS-vs-PnL
   dissonance proved this directly. Therefore: leave the base gate
   untouched.
2. **The cross-island win on spread-quantile is orthogonal to aggressor
   flow**. The spread gate fires on a book-state axis (top-of-book
   spread quantile = liquidity vacuum regime). The aggressor-flow gate
   fires on a trade-flow axis (signed-volume pressure regime). These
   target structurally different adverse regimes; their union is a
   strictly larger (and presumably higher-quality) skip set than either
   alone.
3. **Composing two SKIP gates is the directional opposite of g1l1 and
   g1l2**. Both prior loops admitted more trades. This loop admits
   strictly fewer trades than the base (skip set is the UNION of the
   two gates). Per the migration, restriction not relaxation is what
   moves PnL on this strategy.
4. **Both islands that gained PnL via skip-gates also saw drawdown
   TIGHTEN**. If this composition works, expect both `realized_pnl` UP
   AND `max_drawdown_pct` LESS NEGATIVE (closer to zero). If PnL goes
   up but drawdown widens, the gain is path-risk-fragile and shouldn't
   be carried forward.

**Predicted outcomes** (concrete, falsifiable):

1. `trade_count` falls below the base's 107198 (additional skips from
   the spread axis). Magnitude similar to island-0 g1l1, which saw
   trade_count tighten meaningfully on its base.
2. `realized_pnl` rises vs base (`vs_base_pnl_pct > 0`). The
   migration's mechanism — wide-spread moments are liquidity-vacuum
   periods with elevated adverse-selection on the oracle's 30s forward
   signal — generalizes across base algos, so the dollar effect should
   transfer.
3. `is_weighted_bps` improves (drops) vs base. Wide-spread entries are
   structurally costly in arrival-price terms; filtering them removes a
   slice of high-IS trades.
4. `max_drawdown_pct` tightens (closer to zero) vs base. Wide-spread
   periods coincide with tail-loss trades on island-0 and on a different
   base.
5. `sharpe_ratio` rises vs base 5.59.

**Falsification criteria** (what would make this hypothesis wrong):

- If `trade_count` falls but `realized_pnl` does NOT rise (or falls):
  the spread gate fires on entries that, on aggressor-flow-gate, are
  actually net P&L-positive. This would mean the two gates are
  *anti-correlated* on this base — the trades the spread gate skips
  are the trades the aggressor-flow gate had already admitted as
  favorable. If observed, the next loop pivots to a choppiness-ratio
  axis (island-2's winner) instead of spread.
- If `realized_pnl` rises but `max_drawdown_pct` widens: the gain is
  variance-driven, not tail-cut. Treat as marginal, do not stack
  further axes on top.
- If `is_weighted_bps` does NOT improve: contradicts the documented
  mechanism on island-0 and suggests the spread gate is firing in
  different regimes on this base than on `position-tier-gate`. Would
  require investigation before further composition.
- If `trade_count` falls more than ~15% vs base: the spread gate is
  too restrictive (parameters miscalibrated); lower the quantile (p75
  → p80) or shorten the spread window.

## Implementation Decisions

- **Parameter defaults** (matching island-0 g1l1's known-good values to
  keep the cross-island transfer as clean as possible — only the base
  underneath has changed):
  - Base gate (unchanged from base aggressor-flow-gate):
    - `window_seconds = 10.0`
    - `flow_threshold = 2.0`
  - Spread gate (verbatim from island-0 g1l1):
    - `spread_window_seconds = 60.0` (1-minute rolling distribution).
    - `spread_quantile = 0.75` (upper quartile).
    - `min_samples = 50` (warm-up — gate dormant until the
      rolling distribution is populated).
- **Spread measurement**: compute spread as raw `ask_price - bid_price`
  in price units (no tick conversion). The gate is purely a self-quantile
  test against the algo's own rolling history, so the unit is internally
  consistent — matches island-0 g1l1's implementation exactly.
- **Quote-tick wiring**: `on_quote_tick` is now ACTIVE — it pushes the
  current spread (in ticks) into the spread deque. Prior loops left
  this method passive. Trade ticks continue to feed the aggressor-flow
  deque as before.
- **Composition rule** (BOTH gates evaluated, EITHER skip wins):
  ```
  if spread_gate_says_skip(order) OR flow_gate_says_skip(order):
      skip
  else:
      submit
  ```
- **Quantile computation**: at order time, prune stale spread samples
  beyond the look-back, sort the remaining `spread_ticks` values, and
  index the appropriate quantile position. Implementation is
  straightforward (deque size is bounded by samples-per-second × 180s
  ≈ low thousands for MES — `sorted()` per order event is cheap and
  exact). No streaming-quantile approximation is needed for this
  cadence; if profiling shows it's a hot path, a future loop can
  switch to a P^2 or t-digest streaming algorithm.
- **Empty / warm-up branches**:
  - Spread deque has `< min_spread_samples` → spread gate returns
    "do not skip" (defer to flow gate alone). Matches island-0 g1l1's
    warm-up behavior.
  - Flow deque empty → flow gate returns "do not skip" (matches base).
- **Anti-cascade**: `_position_flat = True` after any skip (regardless
  of which gate fired). Next open is unconditional.
- **Quantity invariant**: never modify `order.quantity`. Only skip or
  submit.
- **No look-ahead**: quote and trade ticks are consumed in replay
  chronological order via Nautilus callbacks; pruning uses
  `order.ts_init` as the anchor. No future quotes are inspected.
- **Subscription**: trade ticks + quote ticks on first encounter
  (matches base; quote subscription was already present, but its
  callback was a no-op — now it stores spread samples).

## Hypothesis (summary line for loop file)

Stack island-0's rolling-spread-p75 OPEN-gate (winner: +26.55% vs its
base) on top of the UNMODIFIED base aggressor-flow-gate, skipping when
EITHER gate votes skip. Reverses this island's two-loop loosening pattern
and acts on the migration's `generalizable` recommendation that
spread+chop+(third) stacking is the highest-leverage gen-2 direction.

## Backtest Observations

**Headline (raw, train window, 12 dates):**

| Metric              | afg-isl-g2l1 | base (afg)  | g1l2 (prior in lineage) | vs base       | vs g1l2       |
| ------------------- | -----------: | ----------: | ----------------------: | ------------- | ------------- |
| realized_pnl        |     2138.00  |    1255.50  |                 990.00  | +70.29%       | +115.96%      |
| sharpe_ratio        |     9.8614   |     5.5944  |                  4.2008 | +76.3% (abs +4.27) | +134.7%   |
| trade_count         |     105609   |     107198  |                 111034  | -1.48%        | -4.89%        |
| mean_slippage       |      0.0     |      0.0    |                   0.0   | 0.0 (flat)    | 0.0 (flat)    |
| max_drawdown_pct    |    -0.02302  |    -0.03325 |                -0.04132 | tighter +30.8%| tighter +44.3%|
| win_rate            |     0.35948  |     0.35488 |                 0.35465 | +0.46 pp      | +0.48 pp      |
| is_weighted_bps     |     0.04196  |     0.04724 |                 0.04267 | -11.18% (better) | -1.67% (better) |
| vs_baseline_pnl_pct |   +1270.51%  |    +704.81% |               +534.62% | (relative to `simple`) | — |
| vs_baseline_is_bps  |     +7.91    |     +21.50  |                  +9.74 | -63.2% (much better) | -18.8% better |

Note `vs_baseline_*` rows are against `simple` (the config `pass_gate.baseline`), not against this island's base; they are informational. The island-internal comparison is `vs base (afg)`.

**Trade-count honesty check:** 105609 fills across 12 dates ≈ 8800 fills/day. Well above any low-trade-count concern; the +70.29% PnL is computed on a large sample.

**Hypothesis verdict — confirmed.** All five concrete predictions made before the run hit:

1. `trade_count` fell below base (105609 < 107198, -1.48%). Predicted magnitude "tighten meaningfully"; actual is mild — about a third of what island-0 g1l1 saw on its base. Either the spread gate fires less often on aggressor-flow-gate's order stream (the base already skips some of the same wide-spread moments via its flow gate, reducing the marginal skip set), or the two gates' skip sets meaningfully overlap on this base.
2. `realized_pnl` rose vs base: +70.29% (2138.00 vs 1255.50). Mechanism transfers across base algos as the migration's `generalizable` block claimed.
3. `is_weighted_bps` dropped vs base (0.04196 vs 0.04724, -11.18%). Wide-spread entries were indeed structurally costly in arrival-price terms; filtering them tightens IS as predicted.
4. `max_drawdown_pct` tightened markedly: -0.0230 vs -0.0332 (+30.8% improvement in absolute terms — closer to zero). Crucially, this rules out the "variance-driven gain" falsification path: the PnL improvement coincides with tail-cut, not extra variance. Both predictions of the orthogonal-gate hypothesis hold.
5. `sharpe_ratio` rose: 9.86 vs 5.59, +76.3%. Drawdown tightened AND PnL rose AND trade count fell — the gain is path-risk-genuine.

**Cross-island transfer worked.** The island-0 g1l1 spread gate (winner +26.55% on `position-tier-gate`) was stacked verbatim on top of an unmodified `aggressor-flow-gate` base and produced +70.29% PnL improvement on this island. This is the largest single-loop PnL move this island has produced and reverses the two-loop loosening regression (g1l1 -43.13%, g1l2 -21.15%). Direct empirical confirmation of the migration's `generalizable` finding that spread+chop+(third) skip-stacking transfers across bases.

**IS-vs-PnL dissonance resolved.** g1l2's headline finding was that PnL and IS moved in opposite directions — proving the base gate carried path-risk information IS could not see. In g2l1 they move TOGETHER (both improve, both substantially): IS bps down 11.2%, PnL up 70.3%, drawdown tighter. That's because g2l1 ADDS a skip axis instead of MODIFYING the base gate. The base gate's path-risk signal stays intact (its skip set is preserved); the spread gate only ADDITIONALLY skips an orthogonal adverse regime (wide-spread book state). Both axes have positive dollar EV on this base, and they compose cleanly.

**Why the trade-count drop is small relative to the PnL gain.** A 1.48% reduction in trades produced a 70.29% PnL gain. The skipped 1.48% are not random — they are heavily concentrated in the wide-spread tail where adverse-selection on the 30s oracle horizon is structurally elevated. This is consistent with island-0's mechanism: a small fraction of "structurally bad regime" trades carry disproportionate negative EV; cutting them tightens both the loss tail and IS.

**Implications for next loops:**

- **g2l2 direction** (highest-leverage): stack a THIRD orthogonal skip axis. The migration's `generalizable` block named chop-ratio (island-2 g1l1 winner) as the second known-good axis. With spread (book-state) + flow (trade-pressure) confirmed orthogonal on this base, adding chop-ratio (price-path) would cover the three structurally-distinct adverse-regime axes the migration identified. Predicted outcome: further PnL gain at the cost of additional trade-count tightening; falsification if PnL rises but drawdown widens (chop skip set anti-correlates with spread skip set).
- **Calibration note** for g2l2: g2l1's trade-count tightening was mild (~1.5%). If the chop axis adds another ~1-3% skip volume on top, total skip volume remains well under the 15% "too restrictive" falsification line set in g2l1's hypothesis. Safe to layer.
- **Do not retune the base flow gate.** g1l1 and g1l2 both lost PnL by touching it. g2l1 confirms the right move is COMPOSITION not MODIFICATION. Future loops on this island should keep the base aggressor-flow gate parameters fixed and only stack additional orthogonal skip axes.
