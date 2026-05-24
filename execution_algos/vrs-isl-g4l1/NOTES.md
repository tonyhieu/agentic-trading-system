# vrs-isl-g4l1 — Hypothesis (written before any code)

**Lineage tip going in:** vrs-isl-g3l2 — PnL 4690.75 (+522.30% vs vol-regime-sizer base 753.75), sharpe 19.11, max_dd -0.40%, win_rate 0.389, trade_count 75,115.
Composition: probabilistic chop gate (window_ticks=30, chop_neutral=1.5, sensitivity=1.0) + rolling-spread-quantile binary gate (60s, q=0.75, min_samples=50) + top-of-book size-asymmetry binary gate (size_asym_ratio=1.5, latest-quote-only, side-aware). AND-skip-on-submit; reduce-only bypasses gates.

## The change

Single-knob retune of the size-asymmetry threshold: `size_asym_ratio: 1.5 -> 2.0`. All other parameters frozen verbatim from g3l2 (chop, spread, composition semantics, instrumentation, reduce-only bypass). The size-asym gate becomes strictly LOOSER — it now fires only when the contra side is at least 2.0x (rather than 1.5x) this side.

This is a one-knob ablation. Nothing else moves.

## Why this change — citing gen-3 migration `base_specific (3)` and island-1 g4l1 null

g3l2's `summary_out.next` named two strong options for g4l1:
- **(a)** Retune size_asym_ratio in [1.25, 2.0] specifically against vrs's chop+spread base.
- **(b)** Add a FOURTH orthogonal axis (e.g., a velocity / persistence / reversion gate).

The gen-3 migration's `base_specific (3)` finding makes this concrete:

> "vrs accepts size-asymmetry strongly but rejects flow mechanically — the chop+spread two-gate base has substantial headroom (the +92.42% jump used a single 1.5-threshold size-asymmetry gate), and the immediate next move is a ratio retune in [1.25, 2.0] on vrs specifically because the threshold was ported from a four-gate composition into a three-gate composition with more headroom; the marginal gate fires harder here."

Direct evidence from a sister island this generation: island-1 g4l1 chose option (b) — added a 5th orthogonal axis (signed mid-velocity gate, 0.50 $/s threshold, 5s window) on top of its already-stacked four-gate composition — and produced a **NULL RESULT**: PnL 4180.25 vs g3l2 parent 4182.00 (−0.04%, inside ±2% null band), trade_count delta −9 on a ~96k base, sharpe and drawdown unchanged. The velocity gate barely fired on the four-gate-conditioned surviving population. This is empirical evidence that adding a yet-more-orthogonal axis on top of a heavy stack tends to inert — the surviving population has been pre-filtered so heavily that the residual distribution has near-zero mass in the new axis's adverse tail.

Option (a) is the higher-leverage move for two reasons that compound:

1. **g3l2 itself is candidly over-restrictive at 1.5.** Trade_count fell 28.25% versus g2l1 (the band declared at <= 10% was busted), and is_weighted_bps deteriorated +88.1% on surviving orders — even though absolute PnL more than doubled. Both signals indicate the 1.5 threshold is firing on lower-EV trades in addition to the high-cost slice it was designed to remove. Loosening (raising the ratio) should give back trade count and bps quality while preserving most of the PnL gain, because the marginal admitted trades — those with contra-side size between 1.5x and 2.0x — sit closer to the body of the distribution than to the tail.
2. **Single-knob ablation has the cleanest falsification surface.** A monotonic, one-dimensional sweep makes the result interpretable regardless of outcome: a PnL increase confirms the over-restriction reading; a PnL decrease confirms 1.5 was on the EV peak (or before it); a null is itself informative because it bounds the curvature of the gate's EV-vs-threshold function. Adding a new axis at this point — given island-1's null evidence — would mostly cost us a loop on a high-prior-failure direction.

The gen-3 migration's generalizable (3) — single-knob retunes on a saturated composition map the operating-point peak with high information per loop — also supports this. island-0 g3l2 (q=0.75 -> 0.80) is the matching cross-island precedent: a small monotonic move that confirmed where the EV peak sits even though it did not beat lineage best.

### Choice within the [1.25, 2.0] band — picking 2.0

g3l2's `next` named three specific test values: 1.25, 1.75, 2.0.
- **1.25 is TIGHTER** (lower ratio = easier to trigger = more skips). Given the trade-count + bps evidence that 1.5 is already over-restrictive, going tighter is the wrong direction.
- **1.75 is the safer mid-band move.** Likely small monotonic delta either way.
- **2.0 is at the loose end of the recommended band.** Maximum information per loop: largest expected effect size, sharpest falsification.

The migration explicitly characterizes vrs's chop+spread base as having "more headroom" and the marginal gate as firing "harder here" — both phrases point toward a value materially looser than 1.5. Going to 2.0 (the top of the recommended band) puts the test at the boldest tested point, which produces the most information regardless of outcome. If 2.0 is too loose (PnL drops vs g3l2), the next loop has a clear interior bracket (1.5, 1.75, 2.0); if 2.0 beats g3l2, the next loop can probe even looser (2.0, 2.5) to find where the gate stops being useful.

## What I expect to see

**Confirmation (axis was over-restrictive at 1.5):**
- PnL > g3l2's 4690.75 by at least the gate threshold (5%) — i.e., > ~4925.
- trade_count recovers materially (back toward the g2l1 ~94-100k band).
- is_weighted_bps drops meaningfully versus g3l2's 0.0585 (closer to g2l1's 0.0311).
- sharpe and max_dd within a hair of g3l2 (loosening should not concentrate risk).

**Null (1.5 was already roughly on the peak):**
- PnL within ±2% of g3l2 — the [1.5, 2.0] band is flat.
- trade_count partial recovery (e.g., +5-15%) but PnL essentially unchanged: marginal admitted trades are EV-neutral. Verdict: 1.5 is on the peak plateau; future loops should add a fourth axis after all.

**Regression (1.5 was on the peak; loosening admits negative-EV trades):**
- PnL drops > 2% vs g3l2.
- The interpretive verdict is the EV-vs-ratio curve has a sharper-than-expected drop on the loose side; g3l2 was the operating point, not over-restricted. Backtrack the next loop to 1.75 or stay at 1.5 and pivot to option (b).

## What is NOT changing

- Chop gate (probabilistic; window_ticks=30, chop_neutral=1.5, sensitivity=1.0, min_prob=0.05, min_ticks=40) — kept verbatim. Gen-3 migration confirmed chop_neutral=1.5 is base-agnostic.
- Spread gate (rolling, 60s window, q=0.75, min_spread_samples=50) — kept verbatim. Island-0 g3l2 confirmed q=0.75 is on the peak plateau.
- Composition: AND-skip-on-submit across all three gates; reduce-only bypass; child_qty == parent_qty == 1.
- Latest-quote-only contract for size-asymmetry (no rolling window). The mechanism is fast-acting on transient depth asymmetries — kept verbatim.
- Instrumentation: per-gate skip counters + multi-gate co-skip counters from g3l2 preserved untouched.

## Pre-declared falsification thresholds

- **Confirmation:** PnL > 4925 (5% above g3l2) AND trade_count > 85,000 (recover at least 25% of the 28% drop g3l2 took vs g2l1) AND is_weighted_bps < g3l2 (any improvement on per-share cost on surviving orders).
- **Null:** PnL in [4596, 4784] (±2% of g3l2) — declare the [1.5, 2.0] band a plateau and pivot to option (b) on g4l2.
- **Regression:** PnL < 4596 (>2% below g3l2) — g3l2 wins; declare 1.5 the operating point and revert.

## Notes pulled forward to g4l2

If this loop CONFIRMS (PnL increases at 2.0): g4l2 should probe even looser (2.5, 3.0) to find where the gate stops adding signal; once the peak is bracketed, the four-axis candidate from option (b) becomes the natural next move with a stable three-axis base under it.

If this loop is NULL: g4l2 should pivot to option (b) — a structurally distant fourth axis. Recommended candidates (per g3l2's next list and island-1's choice of velocity which proved inert): mean-reversion timing (5-15s mid drift sign + magnitude) or directional persistence (a streak-of-favorable-ticks counter). Avoid the velocity axis specifically because island-1 g4l1 just demonstrated it is inert on a heavy stack, and vrs's three-axis stack here is heavier (chop+spread+size-asym) per the same logic.

If this loop REGRESSES: g4l2 should test 1.75 to map the curvature of the ratio-vs-EV function before pivoting; the diagnosis matters more than the next loop's PnL because the regression would suggest the surviving population's adverse-asymmetry mass is concentrated even more sharply in the contra >= 1.5x tail than g3l2 indicated.

---

## Backtest Observations (written after results returned)

**Outcome: REGRESSION inside the pre-declared band.**

### Raw numbers (12 train dates, aggregate)

- realized_pnl: **4454.50** (g4l1) vs **4690.75** (g3l2 lineage parent) vs **753.75** (vrs base)
- sharpe_ratio: **19.6638** vs 19.1094 vs 3.0647
- max_drawdown_pct: **-0.3925%** vs -0.3975% vs -4.6050%
- win_rate: **0.38333** vs 0.38899 vs 0.35287
- trade_count: **80,072** vs 75,115 vs 127,991
- mean_slippage: **0.0** vs 0.0 vs 0.0
- is_weighted_bps: **0.05504** vs 0.05849 vs 0.03737

### Deltas

**vs base (vol-regime-sizer, pnl=753.75):**
- vs_base_pnl_pct = **+490.98%** (g3l2 was +522.30%; g4l1 absolute lift relative to base is still very large)
- vs_base_slippage_pct = 0.0% (both algos run at zero slippage)

**vs g3l2 lineage best (the comparison that matters):**
- PnL delta: **-5.04%** (REGRESSION — outside the ±2% null band, well past the >2% regression threshold)
- trade_count delta: **+6.60%** (4957 more trades on a 75k base; loosening admitted ~5k more orders)
- is_weighted_bps delta: **-5.89%** (per-share cost on surviving orders IMPROVED, as predicted)
- sharpe delta: +0.554 absolute (essentially unchanged; the noise band of sharpe on this many days)
- max_dd delta: +0.005pp (within noise)
- win_rate delta: -0.566pp (small drop, consistent with admitting lower-EV trades)

### Verdict against pre-declared falsification thresholds

| Pre-declared band   | Threshold                        | Outcome                                      |
|---------------------|----------------------------------|----------------------------------------------|
| Confirmation        | PnL > 4925 AND trade_count > 85k AND bps < 0.0585 | NOT MET — PnL fell, trade_count short of 85k |
| Null                | PnL in [4596, 4784]              | NOT MET — PnL of 4454.50 is below 4596       |
| **Regression**      | **PnL < 4596**                   | **MET — PnL 4454.50 sits 141.5 below the band edge** |

Hypothesis: **FALSIFIED.** Loosening size_asym_ratio from 1.5 -> 2.0 did NOT recover EV. The marginal trades admitted by the [1.5, 2.0] asymmetry band — those with contra-side depth between 1.5x and 2.0x this side — carry net-negative EV in this composition.

### Mechanistic reading

Across the 4957 additional trades admitted by loosening, mean per-trade PnL is approximately (4454.50 - 4690.75) / 4957 ≈ **-0.048** ticks (about -$0.24 per trade at $5/tick). The bps regression *narrowed* (the marginal trades are individually cheaper per share — consistent with sitting in less-asymmetric, lower adverse-selection conditions), but the net signal-times-cost balance is still negative.

This is the cleanest possible refutation of the "more headroom" reading from the gen-3 migration: vrs's three-axis stack at 1.5 was NOT over-restrictive. 1.5 sat **at or near the EV peak** for this composition, and the curvature falls off into the loose side — not the tight side — of the ratio axis. The trade_count drop g3l2 took vs g2l1 (−28.25%) was not "over-restriction"; it was the gate doing its job, removing exactly the trades that g4l1 has just re-admitted at a net loss.

The bps improvement is a **red herring** at the single-loop level: lower per-share cost on admitted trades does not imply higher total EV if the admitted trades' signal value is also lower (or negative). This is a useful lesson for future single-knob retunes: bps-vs-trade-count tradeoffs must be read jointly with PnL, not in isolation.

### Cross-island context

Notable: island-1 g4l1 (velocity gate on top of four-gate stack) produced a NULL result (-0.04%). Island-2 g4l1 (loosen size-asym from 1.5 -> 2.0) produced a REGRESSION (-5.04%). Both directions — adding orthogonal axes AND loosening existing thresholds — produced negative information about the local search direction at this generation, on already-well-tuned stacks. The g4 generation so far is mapping a relatively flat ridge: the 1.5 size-asym threshold seems to be on (or very near) the peak, and adding orthogonal axes on top of heavy stacks inerts. Island-0 g4l1's outcome will determine whether this is a general gen-4 phenomenon or specific to the two islands tested so far.

### Implications for g4l2 (per the original pre-declared plan)

Per the pre-declared **regression branch**: "g4l2 should test 1.75 to map the curvature of the ratio-vs-EV function before pivoting." That remains a clean call — 1.75 is the mid-band point between the confirmed working operating point (1.5) and the regressing point (2.0), and a regression at 1.75 too would establish the curvature is steep right at 1.5; a null at 1.75 would establish a plateau peak in [1.5, 1.75].

Alternative direction: pivot to a fourth orthogonal axis with a CALIBRATED threshold (i.e., NOT the same threshold ported from another island). The natural candidate is a flow gate with a stricter threshold than g3l1's 6/4s (which failed). The cross-island migration's `generalizable (2)` finding noted flow gates with weak thresholds tend to fail; but a high-z flow threshold (≥ 9 or 10 imbalance over 4s) is still untested on vrs and is structurally distant from chop/spread/size-asym.

**Recommended primary direction for g4l2:** tighten to 1.25 (opposite direction from g4l1 — the regression at 2.0 plus the EV-peak-near-1.5 reading suggests the more interesting falsification is on the tight side; if 1.25 also regresses, both flanks are mapped). Secondary: 4th axis (flow with threshold ≥ 9/4s, OR a streak-of-favorable-ticks persistence gate).

### Honesty notes

- g4l1 still beats vrs base by ~5.5x absolute. The "regression" is purely versus the lineage parent g3l2 — not versus base, where g4l1 remains a major improvement.
- trade_count (80,072) is well clear of any low-volume concern; the result is not a small-sample artifact.
- PASS gate vs `simple` baseline: g4l1 still passes by very large margin (vs_baseline_pnl_pct = +2755.45%, vs_baseline_is_bps = +41.57 bps). The regression is purely intra-lineage.
