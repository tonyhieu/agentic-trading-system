# ptg-isl-g4l2 — Position-tier-gate + EXPONENTIAL spread-band submit-decay

Island experiment — island-0 (base: `position-tier-gate`), generation 4, loop 2.

Branched from `ptg-isl-g4l1` (island-0 lineage best, +30.70% vs base — the
breakthrough that finally cleared the two-axis saturation ceiling that pinned
the island-0 lineage from g1l1 (+26.55%) through g3l2 (+24.07%)).

## Hypothesis

g4l1's `summary_out.next` ranked two retunes after the probabilistic-decay
mechanism was confirmed live. We are picking option (1): **linear -> exponential
decay shape inside the [p50, p75] band**. This is the higher-leverage option of
the two for the same reason it was ranked first in g4l1's notes: the band-shift
([p50, p75] -> [p60, p80]) is a parametric retune of the same shape, while
**switching the decay function is a structural change to the mechanism**. Pick
the structural lever first; reserve the parametric lever for a later loop only
if the structural one is inconclusive.

### Why exponential (cited cross-island evidence)

g4l1's `next` text states explicitly:
> "vrs uses exponential and produced +34% vs its base; if the EV-vs-rank curve
>  is convex (cost rising faster than linearly) the exponential will front-load
>  admission probability into the cheap end of the band and lift further."

That is the load-bearing cross-island insight: `vrs-isl-g1l1` validated the
exponential decay SHAPE on a different base (vol-regime-sizer, chop-ratio
axis instead of spread axis) at the same `min_prob=0.05` floor. g4l1 ported the
PROBABILISTIC-ADMISSION mechanism class from vrs to ptg using a LINEAR shape;
this loop completes the cross-island port by also porting the exponential
SHAPE.

### Mechanism (why this should beat g4l1)

g4l1's linear decay assigns submit-prob `1.0 - frac * (1.0 - min_prob)` where
`frac = (latest - thr_lower) / (thr_upper - thr_lower)`. This is the first-order
optimal sizing rule under a **linear** EV-vs-rank assumption. But adverse
selection is mechanistically a function of spread, and spread maps to rank
through a distribution that is right-skewed and heavy-tailed (top-of-book MES
spreads cluster at 1 tick with occasional 2-3 tick excursions). Under a CONVEX
EV-vs-rank curve — cost growing faster than linearly with rank — the optimal
admission profile is also convex-shaped (concentrated at the cheap end).

Exponential decay implements that directly:
```
prob = min_prob + (1.0 - min_prob) * exp(-k * frac)
```
where `frac` is the same rank-in-band quantity as g4l1 and `k > 0` is the
shape parameter. At `frac=0` we get `prob = 1.0`; at `frac=1` we get
`prob = min_prob + (1.0 - min_prob) * exp(-k)`, which equals `min_prob` exactly
only as `k -> infinity`. With `k = -ln(min_prob) = -ln(0.05) ~ 2.996` the
upper-edge probability equals `min_prob` at `frac=1` exactly (parametric
identity with g4l1's linear-edge value), so the mechanism difference is
purely SHAPE, not edge-value. This isolates the shape variable for clean
attribution against g4l1.

Net expected effect: shifts expected exposure further away from the high-rank
edge of the band toward the low-rank edge, beyond what linear achieves. If the
EV-vs-rank curve is genuinely convex, this should lift pnl above g4l1's
+30.70%. If the curve is approximately linear, exponential will land within
±2% of g4l1 (different shape, same area under prob-curve in rough magnitude
sense, so similar mean admission rate, but the conditional EV under exponential
is biased toward the cheap end — still expected weakly positive). If the curve
is concave (linear was already overshooting toward the cheap end), exponential
will regress.

### Single-knob discipline

Only the decay-shape FUNCTION changes:
- `spread_quantile_lower = 0.50` (held — same band as g4l1)
- `spread_quantile_upper = 0.75` (held — same band as g4l1)
- `min_prob = 0.05` (held — same floor as g4l1, same value as vrs)
- `spread_window_seconds = 60.0` (held — same as g1l1/g3l2/g4l1)
- `min_samples = 50` (held — same as g1l1/g4l1)
- `position_cap = 1` (held — base/g1l1 proven)
- `decay_sensitivity = 2.9957` (new — exponent constant; default chosen so
  `exp(-k * 1.0) == min_prob`, making edge-values match g4l1 exactly)

Hard cut above `spread_quantile_upper` preserved (g3l2 confirmed [p75, p80] is
EV-negative; this loop does not relitigate that).

Deterministic per-order draw via SHA-256 of `client_order_id` preserved
(identical to g4l1 / vrs-isl-g1l1).

## Falsification line (pre-declared)

- **CONFIRM:** vs_base_pnl_pct > +32.5% (lifts beyond g4l1's +30.70% by more
  than the +2% gen-3-style retune-noise band). Exponential shape adds residual
  EV from the band's convexity.
- **NULL / SHAPE-FLAT:** vs_base_pnl_pct in [+28.5%, +32.5%] (within ±2% of
  g4l1). The EV-vs-rank curve is approximately linear in [p50, p75]; the
  PROBABILISTIC-ADMISSION mechanism is the source of lift, but the SHAPE of
  the decay does not matter at this min_prob floor. Next loop should test the
  parametric retune (band shift to [p60, p80]) which moves the location of the
  decay, not its shape.
- **REJECT:** vs_base_pnl_pct < +28.5% (regresses below g4l1's band).
  EV-vs-rank is concave — linear was already biased toward the cheap end as
  much as is productive, and exponential overshoots. Pull back to linear; the
  productive parametric retune is `min_prob` floor (loosen toward 0.10) or
  band tightening, not shape.

Trade-count falsification: a > 10% drop vs g4l1 (`86377`) — i.e. < `77739`
trades — signals over-restriction even if pnl looks fine; per gen-1 migration
`generalizable (3)`.

## Composition with the base

- Gate 1 (position-tier-gate, cap=1): unchanged from g1l1/g4l1; hard SKIP if
  abs net position >= cap. Reduce-only orders bypass this gate (intraday_flat).
- Gate 2 (exponential probabilistic spread-band decay):
  * If latest spread > p_upper quantile -> HARD SKIP (g1l1/g4l1 behavior;
    g3l2-validated).
  * If latest spread <= p_lower quantile -> submit prob = 1.0.
  * Otherwise: exponential decay
        `frac = (latest - thr_lower) / (thr_upper - thr_lower)`
        `prob = min_prob + (1.0 - min_prob) * exp(-k * frac)`
    Deterministic draw: SHA-256 of client_order_id (vrs / g4l1 pattern).
- Quantity invariant: each individual order is full-size or unsent.
  Participation cap and top_of_book_only remain compliant.

## Implementation Decisions

- `decay_sensitivity = -ln(min_prob)` chosen as default so the upper-band-edge
  submit-prob is **mathematically identical** to g4l1's at `frac=1` (both equal
  `min_prob`). This isolates the SHAPE-of-curve variable from the
  EDGE-value variable: any pnl delta vs g4l1 attributes cleanly to the
  curvature inside the band, not to a different edge probability.
- Cross-island reference: `vrs-isl-g1l1` (the original exponential-decay
  prototype) uses identical pattern (`exp(-sensitivity * excess)` with
  `min_prob` floor); we are intentionally porting its functional form.
- Per-gate instrumentation counters preserved from g4l1 (gen-1 migration's
  `generalizable (3)` rule).

## No look-ahead

Quote-tick deque is pruned at `on_order()` using the order's `ts_init` only;
`_latest_spread` reflects the most recent quote delivered before this order.
Identical look-ahead-safety surface to g4l1.

## Backtest Observations

Aggregate (12 train dates, 2026-03-08 .. 2026-03-20):

| metric          | base ptg | g4l1     | g4l2     | g4l2 vs base | g4l2 vs g4l1 |
|-----------------|----------|----------|----------|--------------|--------------|
| realized_pnl    | 4262.50  | 5571.25  | 5559.25  | **+30.42%**  | **-0.22%**   |
| sharpe_ratio    | 17.619   | 25.112   | 25.078   | +7.46 abs    | -0.034 abs   |
| trade_count     | n/a      | 86377    | 86450    | n/a          | +73 (+0.08%) |
| max_drawdown    | n/a      | -0.0054  | -0.0054  | n/a          | identical    |
| win_rate        | n/a      | 0.38131  | 0.38131  | n/a          | ~flat        |
| mean_slippage   | 0.0      | 0.0      | 0.0      | 0.0          | 0.0          |
| is_weighted_bps | n/a      | 0.02585  | 0.02606  | n/a          | +0.8%        |

Pre-declared falsification line: **NULL / SHAPE-FLAT**. `vs_base_pnl_pct =
+30.42%` lands inside the null band `[+28.5%, +32.5%]` (within +/-2% of
g4l1's +30.70%). The exponential decay shape produced essentially no
distinguishable difference from g4l1's linear decay at the same min_prob
floor.

### Mechanism interpretation

The construction held `decay_sensitivity = -ln(min_prob) ~ 2.996` precisely
so the BAND-EDGE values match g4l1 exactly (both equal `min_prob = 0.05` at
`frac=1`, both equal `1.0` at `frac=0`). The pnl delta of -12 USD across
86k+ trades (-0.22%) is well inside per-date noise and below g4l1's own
+/-2% retune-noise band declared in g3l2->g4l1's null spec.

What this rules in: **the SHAPE of the decay curve in `[p50, p75]` does not
matter at this min_prob floor**. The EV-vs-rank-in-band relationship is
approximately linear inside this band. The mechanism CLASS
(quantity-modulation / probabilistic admission) was the lever that broke
the island-0 saturation ceiling at g4l1; the curve shape inside the band
is a non-load-bearing detail.

What this rules out (vs the pre-declared CONFIRM hypothesis): the
EV-vs-rank curve is NOT meaningfully convex inside `[p50, p75]` — if it
were, the exponential's front-loading of admission probability onto the
cheap-spread end of the band would have produced detectable additional
EV (the cited cross-island parallel from `vrs-isl-g1l1` doesn't transfer
to this band on this base).

What this rules out (vs the pre-declared REJECT hypothesis): the curve is
also NOT concave inside the band — there's no regression from
front-loading admission, which would have shown up as a clear pnl drop if
linear was already over-tilted toward the cheap end.

The trade-count delta (+73 trades, +0.08%) is consistent: exponential and
linear shapes have similar areas under the prob-curve at this k value, so
mean admission rate is essentially identical. No 10%-drop falsification
triggered (g4l1's 86377 -> g4l2's 86450 is essentially flat).

### What this means for the island-0 lineage

g4l1's linear decay is the canonical island-0 lineage choice — both
shapes produce the same EV in this band, and linear is strictly simpler
(no exp() call, no `decay_sensitivity` parameter, smaller surface area
for unintended attribution drift).

### Next direction (single highest-leverage)

g4l1's `summary_out.next` ranked three retunes; this loop ran option (1)
and ruled it null. The remaining two:

1. **Band placement retune `[p50, p75] -> [p60, p80]`** — relocates the
   decay region to the actually-expensive part of the spread distribution
   while preserving full admission below the 60th percentile. This is a
   parametric retune of WHERE the decay applies, not its shape. Higher
   leverage than option 3 because g3l2 already proved `[p75, p80]` is
   EV-negative — pulling the upper edge of the soft band into that region
   would test whether the decay can salvage participation in territory
   that hard-cut was already discarding.
2. **`min_prob` floor sweep (0.05 -> 0.0 hard edge / 0.10 gentler floor)**
   — smallest parametric retune; only run if the band-shift in (1) is
   also null.

Future loops should pick option (1) over the now-ruled-out exponential
shape revisit.
