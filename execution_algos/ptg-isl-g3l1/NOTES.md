# ptg-isl-g3l1 — NOTES

## Hypothesis

**Lineage decision.** Island-0's best loop remains `ptg-isl-g1l1` (+26.55%
vs base position-tier-gate, sharpe 23.17, chop-free). Generation 2 attempted
two chop variants on top of g1l1 (boolean: g2l1 -23.15%; probabilistic-decay
ported from vrs: g2l2 -11.46%) and both regressed against the chop-free
baseline. The gen-2 migration confirms the verdict: **chop is partially
transferable to ptg but at a worse operating point than the chop-free
baseline**. g3l1 therefore branches from `ptg-isl-g1l1` (position-cap +
rolling-spread-p75), NOT from g2l2.

**Third axis — chosen.** The gen-1 migration's *generalizable* finding named
"a composed spread + chop + (third axis) stack" as the highest-leverage
direction; the gen-2 migration's island-0 summary, gen-2 g2l2's `summary_out.next`,
and the cross-island insight ALL converge on the same recommendation:

> Cross-island insight (gen-2): "drop chop; on ptg's base, try spread+cap +
> book-flow imbalance as the third orthogonal axis."

This loop adds an **aggressor-flow gate** (book-flow / signed-volume
imbalance from trade ticks) as a third orthogonal axis on top of g1l1's
position-cap + rolling-spread-p75 composition. This is the same mechanism
that island-1 used to amplify its base to +173.95% vs base by stacking
`spread + flow + chop` (island-1 gen-2 g2l2). Flow is **structurally distinct**
from both spread (book-state) and the dropped chop axis (price-path):
- Spread = top-of-book width (liquidity vacuum)
- Aggressor flow = signed traded volume (trade-pressure)
These were the two axes whose composition produced island-1's largest gain.

**Composition semantics — chosen.** Three binary OR-skip gates (skip the
OPEN if ANY of position-cap / spread-p75 / aggressor-flow fires). This
matches island-1 g2l2's AND-of-passes semantics (which the gen-2 migration
flagged as a critical sub-finding: "AND-skip across binary gates preserves
orthogonality cleanly"). Close legs (reduce-only) always execute, preserving
intraday_flat compliance and the quantity invariant.

**Operating point — RETUNED.** The gen-2 migration explicitly flagged
verbatim cross-base parameter porting as the dominant g2 failure mode
("the gate's MECHANISM transferred, but its OPERATING POINT was tuned
against a different base's surviving-population distribution"). The
canonical afg defaults are `window_seconds=10.0, flow_threshold=2.0`.
ptg-g1l1's surviving population is **already pre-filtered twice**
(position-cap + spread-p75), so:
- Most of the highest-trade-pressure bursts coincide with wide spreads,
  which are already cut by the spread gate. The marginal adverse-flow
  signal on the surviving population is weaker than on afg's raw base.
- Therefore the operating point should be **less aggressive** to avoid
  cutting positive-EV residual trades (symmetric to island-2 g2l2's
  -30% misfire from over-cutting at afg's default sensitivity).

Chosen operating point:
- `flow_window_seconds = 10.0` (same as afg — short-term pressure window)
- `flow_threshold = 3.0` contracts (50% higher than afg default 2.0;
  fires only on genuine adverse pressure, leaves the body of the
  surviving distribution intact)

If g3l1 underperforms g1l1, two diagnostics are possible from the
instrumentation counters: (a) gate fires rarely (threshold too high — try
2.0 or 1.5 in g3l2); (b) gate fires often but cuts positive-EV trades
(flow is redundant with spread on this base; declare three-axis
saturation, pivot to quantity modulation per gen-2 base_specific finding).

**Cross-island insight cited.** This hypothesis is informed by:
1. Gen-1 migration `generalizable` (spread + chop + third axis composition rule).
2. Gen-2 migration island-0 `island_summary` ("drop chop; try book-flow / signed-volume imbalance").
3. Gen-2 migration `cross_island_insights.what_worked` (island-1's spread+flow+chop +173.95% confirmed flow is orthogonal to spread).
4. Gen-2 migration `cross_island_insights.what_failed` (verbatim parameter porting → retune the threshold).
5. Gen-2 g2l2 `summary_out.next` (explicit recommendation to add book-flow as third axis from g1l1).

**Falsification criteria.**
- PASS-relative goal: realized PnL > ptg-isl-g1l1's 5394.25 (must beat
  the chop-free best, not just the base).
- Gate sanity: `aggressor_flow_skip_count > 0` and drop in trade_count
  relative to g1l1's 87319 is <= ~8% (a much larger drop with no PnL
  gain would indicate over-restriction, mirroring island-2 g2l2).
- If skip count is 0 or near-0: gate is redundant with spread on this
  base (next loop should try lower threshold or pivot away from flow).

## Implementation Decisions

- Branch from `ptg-isl-g1l1/execution_algorithm.py` (chop-free best).
- Subscribe to BOTH quote ticks (for spread) AND trade ticks (for flow).
- Maintain a running `_net_flow` sum updated O(1) per trade tick (mirrors
  afg's pattern); prune the flow deque at order time.
- Quantile threshold for spread gate retained verbatim from g1l1
  (window=60s, q=0.75, min_samples=50).
- Position cap retained verbatim from g1l1 (cap=1).
- Add per-gate instrumentation counters surfaced via `on_stop()` log line
  (per gen-1 migration's `generalizable` finding #3: "Gate additions MUST
  ship with instrumentation counters... or null-effect results are
  undiagnosable"):
  - `position_skip_count`
  - `spread_skip_count`
  - `flow_skip_count`
  - `flow_warm_up_count` (no trade data in window)
  - `submit_count`
  - `evaluated_open_count`
- No quantity modification anywhere; quantity invariant preserved.
- No look-ahead: deque prunes use `order.ts_init`; trade/quote ticks
  arrive in chronological replay order.

## Backtest Observations

**Headline (raw, 12 train dates, 2026-03-08 → 2026-03-20):**

| metric        | base ptg | g1l1 (best) | g2l2     | g3l1     | g3l1 vs base | g3l1 vs g1l1 | g3l1 vs g2l2 |
|---------------|---------:|------------:|---------:|---------:|-------------:|-------------:|-------------:|
| realized_pnl  |   4262.5 |     5394.25 |   3774.0 |  3196.25 |      -25.01% |      -40.75% |      -15.31% |
| sharpe_ratio  |    17.62 |       23.17 |    21.01 |    15.96 |       -1.66Δ |       -7.21Δ |       -5.05Δ |
| trade_count   |    90433 |       87319 |    73800 |    69081 |      -23.6%  |      -20.9%  |       -6.4%  |
| max_dd_pct    | -0.01727 |    (see g1) |    n/a   | -0.00790 |          ——  |          ——  |          —— |
| mean_slippage |      0.0 |         0.0 |      0.0 |      0.0 |       0.0pp  |       0.0pp  |       0.0pp  |

**Verdict: REGRESSION.** g3l1 underperforms the ptg base by -25.01% pnl,
the island-0 best (g1l1) by -40.75%, and even the regressing g2l2 by
-15.31%. Sharpe degraded by 7.2 points vs g1l1.

**Falsification check.** The hypothesis named two diagnostic patterns
(see Hypothesis §"If g3l1 underperforms"):
- (a) gate fires rarely → wouldn't explain the magnitude of the regression
- (b) gate fires often and cuts positive-EV trades → consistent with
  observed -20.9% trade_count drop vs g1l1 AND a proportional PnL
  collapse.
Trade_count dropped from g1l1's 87319 to 69081 (-18238 trades). Even
without the on_stop counter readout (no log file captured), the trade
count decisively rules out (a). The mechanism appears to be (b): the
flow gate fires on a population of trades that, after spread+cap
pre-filtering, was already on average positive-EV. The flow signal is
weakly orthogonal to the surviving population's EV — it cuts EV-positive
trades roughly in proportion to EV-negative trades.

**Pattern across island-0 generation 2 + g3l1.** Every third-axis
addition on top of g1l1 has regressed:
- g2l1 (boolean chop): -23.15% vs base
- g2l2 (probabilistic-decay chop): -11.46% vs base
- g3l1 (aggressor-flow): -25.01% vs base (worst of the three)

The flow axis — which produced the largest gain on island-1 — performs
*worst* on this base. The cross-island insight that "spread + flow"
amplifies afg does NOT transfer to ptg's base, even after retuning the
threshold from 2.0 → 3.0. This is a clean falsification of the gen-2
cross-island `generalizable` claim about spread+flow being a transfer
recipe.

**Mechanistic interpretation.** ptg's surviving population after
position-cap + spread-p75 is structurally different from afg's surviving
population after its single flow gate. On afg's base, spread is the
dominant remaining EV filter (afg's "what worked" axis). On ptg's base,
the spread gate is *already applied*, so a flow gate operating on the
remainder cuts trades that are no longer carrying spread-induced
adverse-selection signal — meaning the flow signal degenerates into
noise on this population. Stacking gates whose discriminative power
depends on different underlying base populations does NOT compose
additively.

**Three-axis saturation.** Two independent third axes (chop, flow) have
now both regressed against g1l1 on ptg's base. This is strong evidence
that the position-cap + spread-p75 composition has already extracted the
gate-additivity gains available on this base. Adding a third orthogonal
binary gate appears to be strictly EV-negative on the residual
population.

**Implication for g3l2.** Given the consistent regression of all
third-axis approaches, g3l2 should NOT add a fourth gate axis. Two
diagnostic-tier alternatives:

1. **Retune g1l1's existing parameters** (highest expected value). The
   gen-2 migration's *generalizable* finding ranked operating-point
   retuning above mechanism porting; g1l1 used `window=60s, q=0.75,
   min_samples=50, position_cap=1` as inherited defaults. Sweep
   (q ∈ {0.70, 0.80, 0.85}) or (window ∈ {30s, 90s, 120s}) to find a
   superior operating point that the original loop never explored.
   This is the *only* axis with empirical evidence of EV-positivity on
   this base.

2. **Switch from skip-axis to quantity-modulation axis** (per gen-2
   migration `base_specific` finding for ptg: "ptg's gate-stacking has
   plateaued; explore quantity tier modulation as orthogonal direction").
   Tier-by-position-size on opens (e.g., reduce qty by 50% when spread
   is in p50–p75 band rather than full skip). Preserves intraday_flat
   and keeps execution surface but converts a binary EV cut into a
   continuous EV haircut, which is structurally different from any
   binary gate.

g3l2 should choose **option 1** (parameter retune of g1l1's spread gate)
as the lower-risk, higher-prior-evidence path. Option 2 is reserved for
g4 if option 1 also fails to beat g1l1.
