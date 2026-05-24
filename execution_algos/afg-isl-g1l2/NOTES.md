# Algorithm Notes: afg-isl-g1l2 (island-1, generation 1, loop 2)

## Island lineage

- Island: island-1
- Base algo: aggressor-flow-gate
- Prior loop: afg-isl-g1l1 (two-window persistence + reversal). **FAIL** —
  pnl -43.13% vs base, sharpe 3.06 vs 5.59 (-45%), is_weighted_bps +7.4%
  worse. The reversal-exception mechanism (short-window flow-flip used as a
  proxy for price reversal) was decisively falsified: it admitted marginal
  trades that were net P&L destroyers because flow-flip ≠ price reversal.
- Cross-island input: NONE — generation 1, no migration reports exist yet.
  Hypothesis derives purely from g1l1's falsification analysis.

## Hypothesis

**Mechanism**: Revert the entire g1l1 structural change (drop the short
window, drop the reversal exception) and return to the base
aggressor-flow-gate's single-window signed-flow gate. The ONE
modification is a **trade-count minimum** that suppresses the gate when
the rolling window contains fewer than `min_trade_count` prints (default 8).

- Below the minimum print count: SUBMIT unconditionally (thin window —
  gate has insufficient evidence to decide).
- At/above the minimum print count: apply the base gate exactly
  (BUY skip iff `net_flow <= -flow_threshold`; SELL mirror).
- Closing/reduce-only orders: always submit (unchanged).
- After any skip: `_position_flat = True` (anti-cascade — unchanged).

**Inefficiency exploited**: The base aggressor-flow-gate's NOTES.md
documents an IS regression (`is_weighted_bps` rose +21.9% vs simple
baseline) that lives in the entries the gate over-rejects. A 10s window
with `flow_threshold = 2.0` can fire from as few as 1-3 prints — e.g., a
single 2-lot SELLER aggressor in an otherwise quiet 10s period meets the
adverse threshold. Those thin-window prints are statistical artifacts,
not sustained pressure: the next 5-30s is essentially uncorrelated with
that one trade's direction. Gating on them costs us the favorable
arrival-price entries that drive the IS regression.

Requiring ≥8 prints in the window before the gate may fire keeps the
gate active in the genuinely active/contested periods (where many
aggressors are crossing in the same direction) and disables it in the
quiet pockets where the flow signal is dominated by 1-2 events.

**Why this is the "structurally safer first step"** (per g1l1 NOTES.md
explicit recommendation): tightening the base by demanding stronger
evidence is a strictly more conservative change than loosening it with
new exceptions. We expect:
1. **Skip rate goes DOWN** (some prior skips were thin-window false
   positives that now submit).
2. **Of those newly-submitted trades**, a meaningful fraction were the
   IS-favorable entries the base over-rejects → P&L should improve.
3. **The remaining skips** (windows with ≥8 prints AND adverse net flow)
   are the genuinely persistent-pressure cases — those are correctly
   rejected, base's PnL advantage from gating preserved.
4. **trade_count** should rise modestly (fewer skips) but the marginal
   trades admitted are higher quality than g1l1's reversal-exception
   marginals, because price-favorable arrival is more likely in quiet
   pockets than in sustained adverse pressure.

**Builds on**: aggressor-flow-gate (base for island-1). Single-window
structure, single-window threshold — only addition is the `n_prints`
check before the adverse-flow gate. g1l1's two-window logic and reversal
exception are both removed.

**Falsification criteria** (what would make this hypothesis wrong):
- If trade_count rises significantly but PnL drops → newly-admitted
  trades are still net losers; the thin-window-is-noise theory is wrong
  and the base's gate is actually filtering useful signal in those
  pockets too.
- If trade_count rises and PnL improves but `is_weighted_bps` does NOT
  fall → the IS regression source is not thin-window false positives
  and we should look elsewhere (e.g., trade-size weighting, or a real
  price-confirmation rule).
- If `min_trade_count = 8` is too high and the gate effectively never
  fires → behavior collapses to baseline `simple`, which would defeat
  the whole gate concept; in that case, the next loop tunes the
  threshold downward (4? 5?) rather than abandoning the mechanism.

**Alternatives considered (and not chosen for this loop)**:
- Tick-based price-confirmation rule (g1l1 NOTES "next" option b):
  requires accessing the mid/quote at decision time and computing tick
  deltas over a sub-window. More moving parts; the min-count tightener
  is a strictly smaller and more interpretable test of "the base
  over-gates on thin windows."
- Trade-size weighting (divide net_flow by total window volume):
  changes the threshold's units, harder to reason about; defer.
- Slope-based gate (compare first-half vs second-half flow): more
  parameters, similar failure mode to g1l1's short/full split; defer.
- Raising `flow_threshold` (e.g., 2.0 → 3.0): also tightens but in a
  coarser way — it ignores the underlying issue (the prints-per-window
  count is the actual confidence proxy, not the magnitude).

## Implementation Decisions

- **Parameter defaults**:
  - `window_seconds = 10.0` (unchanged from base — known-good value).
  - `flow_threshold = 2.0` (unchanged from base — known-good value).
  - `min_trade_count = 8`. Reasoning: at typical MES futures cadence
    a populated 10s window contains tens to low hundreds of prints; 8
    is well below the median but well above 1-3 (which is the noise
    regime). Round number, easy to tune up or down in a future loop.
- **Empty deque** still returns "do not gate" (preserves base's warm-up
  behavior; only the populated-but-thin case is the new branch).
- **Quantity invariant**: never modify `order.quantity`. Only skip or
  submit. Unchanged from base and g1l1.
- **No look-ahead**: prune using `order.ts_init` as cutoff anchor; deque
  is fed strictly by `on_trade_tick` callbacks in replay order.
  Unchanged from base and g1l1.
- **Subscription**: trade ticks + quote ticks on first encounter
  (matches base and g1l1).
- **Anti-cascade**: `_position_flat = True` after any skip; next open
  submits unconditionally. Unchanged contract.

## Backtest Observations

Train window: 12 dates (2026-03-08 .. 2026-03-20). Baseline for delta math
in the island experiment: `aggressor-flow-gate` (NOT `simple`).

**Headline metrics (afg-isl-g1l2 vs aggressor-flow-gate base):**

| Metric                | afg-isl-g1l2 | base (aggressor-flow-gate) | delta vs base       |
|-----------------------|--------------|----------------------------|---------------------|
| realized_pnl          | 990.0        | 1255.5                     | -21.15%             |
| sharpe_ratio (v2)     | 4.2008       | 5.5944                     | -24.91%             |
| max_drawdown_pct      | -0.0413      | -0.0332                    | -24.3% (worse)      |
| win_rate              | 0.35465      | 0.35488                    | -0.06% (flat)       |
| trade_count           | 111034       | 107198                     | +3.58%              |
| mean_slippage         | 0.0          | 0.0                        | 0.0% (both zero)    |
| is_weighted_bps       | 0.04267      | 0.04724                    | -9.67% (better)     |
| total_return_pct      | 0.099        | 0.126                      | -21.4%              |

Reference vs `simple` baseline (from results JSON):
- vs_baseline_pnl_pct: +534.6% (vs base's +704.8%)
- vs_baseline_is_bps:  +9.74  (vs base's +21.50 — improvement in IS bps)

**Verdict: PARTIAL FALSIFICATION of the headline hypothesis, partial
confirmation of a secondary prediction.**

What the hypothesis said would happen vs what happened:

1. **Skip rate goes DOWN** → CONFIRMED. trade_count rose +3.58%
   (107198 → 111034, ~3836 additional trades admitted), consistent with
   `min_trade_count = 8` suppressing the gate on thin windows.

2. **Newly-admitted trades raise PnL** → FALSIFIED. PnL fell -21.15%.
   The roughly ~3836 trades that the base would have skipped but this
   variant admits are net P&L destroyers in aggregate. The
   "thin-window-is-noise, so admitting those entries should be
   favorable" theory does not hold on the train window.

3. **`is_weighted_bps` falls** → CONFIRMED (and this is the bright
   spot). IS bps dropped from 0.04724 to 0.04267 (-9.67%). The
   `vs_baseline_is_bps` improved from +21.50 to +9.74 — i.e., the
   variant captures roughly half of the base's IS regression, which is
   exactly the failure mode g1l1 NOTES.md targeted. The thin-window
   gate-firing IS contributing to IS slippage; gating only on populated
   windows demonstrably improves arrival-price quality.

**The dissonance is real and informative**: IS quality improved, but
realized PnL fell. This means the trades the gate now admits get
*better entry prices on average* (lower IS bps) but are *net P&L
losers*. Two possible mechanisms, consistent with the data:

- **a)** The base's gate was rejecting trades that had decent
  arrival-price entries but the subsequent intraday path went against
  them. The gate was filtering out "bad path" trades that happen to
  arrive at favorable mids — a signal we're now ignoring by trusting
  population alone.
- **b)** The thin-window prints are noise in flow-direction but the
  base's stricter behavior happened to coincide with risk-off pockets
  whose adverse follow-through was real. Removing the filter in thin
  windows accidentally admitted trades during those same risk-off
  pockets.

In either case, `n_prints` is a confidence proxy for the GATE itself
(do I have enough flow data to decide?), not a confidence proxy for
the TRADE's eventual P&L. The base aggressor-flow-gate's gating
adds value above what the IS bps reads — it captures a path-risk
component invisible to arrival-price metrics.

**Secondary observations:**
- max_drawdown worsened by -24% on a relative basis (-0.0413 vs
  -0.0332). The newly-admitted trades cluster their P&L drag in
  drawdown episodes, not in slow-bleed. Trade-count rose only +3.58%
  but drawdown rose +24% — disproportionate, suggesting the marginal
  trades concentrate in unfavorable regimes.
- sharpe fell -24.9%, which is consistent with PnL down + drawdown up.
- win_rate is essentially flat (-0.06%), so the P&L loss is driven by
  size/magnitude on losing trades among the newly-admitted set, not
  by a hit-rate collapse. The admitted thin-window trades have similar
  hit rate but worse loss-to-win asymmetry than the gated trades.

**Honesty flags (per OBJECTIVE.md §8):**
- trade_count (111034) is high — no flag.
- 12 train dates evaluated — no missing-date gap.
- sharpe_n_days = 12, matching dates evaluated.
- mean_slippage = 0.0 on both sides reflects the deterministic
  arrival-price model in the strategy's order placement; the meaningful
  execution-quality metric here is `is_weighted_bps`, not slippage.
  Reported `vs_base_slippage_pct = 0.0` is structurally true but
  uninformative.
- No date was cherry-picked; aggregate is train-window-wide.
- The IS-bps improvement is real but does NOT redeem the PnL drop:
  the islands experiment ranks loops on `vs_base_pnl_pct`, and on
  that metric this loop is a regression.

**What this tells the next loop (island-1 g1l3) and the migration
synthesis:**

- The min-trade-count tightener as implemented has a measurable
  beneficial effect on arrival-price quality but the wrong sign on
  realized PnL. It should NOT be carried forward in its current form.
- The IS-vs-PnL dissonance is the real finding — it's evidence that
  the base's gating captures path-risk information beyond what IS bps
  exposes. Future loops on this island should treat IS bps as a
  diagnostic, not as the objective.
- Promising next directions:
  - (a) Combine the min-count rule with a stricter (not looser)
    flow_threshold, so the only admitted thin-window trades are ones
    where flow is strongly favorable, not merely sub-threshold-adverse.
    Tests whether the path-risk signal survives when we add a
    favorable-flow positive criterion.
  - (b) Drop the min-count rule entirely and try the path-confirmation
    direction g1l1 NOTES proposed as alternative (b): require mid to
    have moved >= X ticks favorably during a short sub-window before
    admitting an adverse-flow window. This addresses the "IS-good but
    P&L-bad" pattern directly by requiring price confirmation.
  - (c) Investigate whether the admitted trades cluster on specific
    dates (regime concentration). If yes, a volatility-regime gate
    would do more than either flow-based variant.
- Generation-2 migration import: if other islands (e.g.,
  per-iteration-twap or other base lineages) have findings on the
  IS-vs-PnL split, that's the cross-island insight most relevant here.
