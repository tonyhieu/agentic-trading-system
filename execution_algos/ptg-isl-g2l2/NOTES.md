# Algorithm Notes: ptg-isl-g2l2

## Hypothesis

**Builds on**: `ptg-isl-g2l1` (island-0, generation 2, loop 1) — which composed
position-cap + rolling-spread-p75 with a **boolean** chop-ratio skip
(threshold 2.0). Result on the 12-date train window: pnl 3276.25
(**-23.14% vs base position-tier-gate**, **-39.26% vs prior g1l2** which was
spread+cap only). The boolean port over-pruned: ~15.3k trades cut on top of
g1l2's selection, and the filtered slice contained net-positive-EV trades
(sharpe collapsed 23.17 → 17.86 alongside pnl).

**The specific change for g2l2 (one targeted change)**: Replace the
boolean-skip chop gate with the **probabilistic exponential-decay** form
that island-2 (vrs-isl-g1l1) actually used — keeping the same window and
chop_ratio definition, but mapping ratio → submission probability via:

    excess   = max(0, chop_ratio - chop_neutral)
    p_submit = max(min_prob, exp(-sensitivity * excess))

with `chop_neutral=1.5`, `sensitivity=1.0`, `min_prob=0.05`. Keep
position-cap + rolling-spread-p75 unchanged. Keep instrumentation counters.

Concretely, at OPEN time the third gate (after position-cap and spread-p75)
now computes `p_submit` from chop_ratio and SKIPS only if a deterministic
SHA-256(client_order_id)-derived uniform `u >= p_submit`. Trends
(chop_ratio ≤ 1.5) submit at p=1.0. Heavy whipsaws (chop_ratio ≥ ~4.5)
submit at the 5% floor. Mid-range whipsaws (chop_ratio ~2.0–3.0) submit at
`p_submit ≈ 0.61` and `≈ 0.22` respectively — exactly where g2l1's boolean
threshold (2.0) was throwing them away outright.

**Cross-island influence (cited explicitly)**: g2l1's `summary_out.next`
directly named this move: *"Re-port choppiness as a probabilistic
submission-decay (chop_neutral=1.5 → chop_steep=3.0, exponential decay)
instead of a hard boolean skip — that is island-2's actual semantics and
the threshold port was the gap."* The gen-1 migration report's
`cross_island_insights.generalizable` flagged composing spread+chop as the
single highest-leverage gen-2 direction — but g2l1 falsified the *boolean*
port specifically, not the chop concept. This loop tests whether
probabilistic decay (the gen-1 mechanism that actually worked on island-2)
transfers to ptg.

**Why probabilistic should outperform boolean on this base**:
- Boolean-skip at threshold=2.0 removes 100% of trades with chop_ratio
  just above 2.0 (which g2l1's evidence shows are *positive-EV on average*
  on ptg's signal cadence). The data says the chop axis is real but the
  cutoff is wrong.
- Probabilistic decay attenuates participation smoothly: 39% reduction at
  chop_ratio=2.0, 78% reduction at 3.0, full 95% reduction only above 4.5.
- This **dosage** form lets the gate exploit the worst tail (extreme
  whipsaws — which presumably *are* net-negative-EV) without sacrificing
  the mid-band where ptg's edge lives.
- If the probabilistic form *also* underperforms g1l1 (spread+cap only),
  that is a clean falsification that chop is non-transferable to ptg
  regardless of dosage form, and the next loop should pivot to a
  different orthogonal axis.

**Why we don't drop chop entirely and revert to g1l1**:
- g1l1 (spread+cap) is the current island-0 best at +26.55% pnl vs base.
- Reverting is safe but wastes the chop investigation. g2l1's data is
  insufficient to decide between "chop hurts ptg at any dosage" and
  "boolean port was specifically wrong" — the dosage form is the missing
  experimental cell. Running it makes the next decision (port further vs
  pivot) data-driven rather than guess-based.

**Expected effect**:
- Trade-count: between g1l1's 87319 (no chop gate) and g2l1's 72060
  (boolean chop gate). Probabilistic mid-band ≈ ~80k expected.
- PnL: target is to land between g1l1 (5394) and g2l1 (3276). If pnl ≥
  g1l1 (≥5394), probabilistic chop helps and the next loop tunes
  parameters (steeper decay, lower neutral). If pnl < g1l1 but > g2l1,
  chop has a sweet spot but adds residual cost — flag and pivot. If
  pnl ≤ g2l1, chop is non-transferable to ptg at any dosage — declare
  and pivot to a different orthogonal axis next loop.
- Sharpe: expected to recover most of g2l1's loss (17.86 → ~22) if the
  filtered slice is genuinely whipsaw losers; remain near 17.86 if not.
- Drawdown: should remain tightened vs base (-1.73%); g2l1 hit -0.47%
  even while bleeding pnl, so soft chop should preserve at least some of
  that risk improvement.

**Honesty up-front**: mean_slippage is 0.0 by simulator construction
(top-of-book fills), so `vs_base_slippage_pct` will be 0.0 again. The
real comparison axes here are pnl, sharpe, drawdown, instrumentation
counter ratios, and the comparison against BOTH g1l1 (current island-0
best) and g2l1 (the boolean port being directly replaced).

## Implementation Decisions

- **Probabilistic form mirrors `vrs-isl-g1l1` exactly**:
  `chop_neutral=1.5`, `sensitivity=1.0`, `min_prob=0.05`,
  `chop_window_ticks=30`, `chop_min_ticks=40`. Same constants. This
  isolates the gate-semantics change (boolean vs probabilistic) as the
  ONLY variable changed vs g2l1 — the dosage curve is held fixed at the
  values that produced +34% PnL on island-2.
- **Same chop_ratio definition** as g2l1 (path_length / max(displacement,
  eps), window=30 ticks). The math is unchanged; only the
  ratio→decision mapping changes.
- **Deterministic uniform draw** copied verbatim from vrs-isl-g1l1:
  SHA-256(client_order_id), first 8 bytes as big-endian uint64,
  normalized to [0, 1). Reproducible given the oracle's fixed seed.
- **Gate ordering unchanged**: position-cap → spread-p75 → chop. First
  two gates are still boolean (matching ptg lineage); only the third is
  now probabilistic. This keeps the cheap deterministic skips in front
  and minimizes RNG calls.
- **Instrumentation extended**: existing counters
  (`evaluated`, `skipped_position`, `skipped_spread`, `submitted`) are
  preserved. The `skipped_chop` counter now means "chop p-draw skipped";
  added `chop_p_submit_lt_1_count` to track how often chop fired *at all*
  (p<1, regardless of skip outcome) — distinguishes "chop never fires
  due to cold-start / clean trends" from "chop fires often but rarely
  skips." Both can produce the same `skipped_chop` count and gen-1
  taught us to instrument before guessing.
- **No quantity modification**: SKIP means do not submit. Quantity
  invariant preserved across all three gates.
- **No look-ahead**: chop is computed exclusively from `_mids`
  populated in `on_quote_tick`, strictly in chronological replay order;
  `on_order` reads cached state only.
- **Reduce-only orders bypass all gates** (intraday_flat compliance,
  consistent with ptg lineage).
- **No retuning of position-cap or spread-quantile**: those are the
  proven g1l1 layers, held fixed so any delta is attributable to the
  chop-gate semantics change.

## Backtest Observations

**Raw metrics (12 train dates, MESM6):**
- realized_pnl = 3774.00
- sharpe_ratio = 21.0124
- trade_count = 73800
- mean_slippage = 0.0 (top-of-book sim — uninformative)
- max_drawdown_pct = -0.500%
- win_rate = 0.3737
- is_weighted_bps = 0.0307

**Computed comparisons:**
- vs base `position-tier-gate` (pnl 4262.5): **vs_base_pnl_pct = -11.46%**
- vs base slippage: **vs_base_slippage_pct = 0.0%** (both sides 0 by simulator construction)
- vs prior `ptg-isl-g2l1` (pnl 3276.25): **+15.19%** improvement
- vs island-0 best `ptg-isl-g1l1` (pnl 5394.25): -30.04%

**Trade-count trajectory:**
- g1l1 (spread+cap, no chop): 87319
- g2l1 (boolean chop@2.0): 72060 (-17.5% vs g1l1)
- g2l2 (probabilistic chop): 73800 (+2.4% vs g2l1, -15.5% vs g1l1)

The probabilistic gate barely budged trade count (~1.7k more than boolean).
Expected mid-band reinclusion (~80k) did not materialize — most of the
chop_ratio mass is apparently either ≤1.5 (p=1, submits) or well into the
tail (p ≪ 1, skips), with little mid-band exposure where p ≈ 0.4–0.7. The
dosage curve from vrs-isl-g1l1 (chop_neutral=1.5, sensitivity=1.0) is
*too steep* for ptg's signal cadence.

**Sharpe behavior:**
- base 17.619, g1l1 23.17, g2l1 17.86, g2l2 **21.01**
- Sharpe recovered most of g2l1's loss (17.86 → 21.01, ~75% of the way back
  to g1l1) on smaller trade-count delta than expected. This means the *few*
  trades the probabilistic form re-admitted relative to the boolean port
  were disproportionately good per-unit-risk — consistent with the
  hypothesis that the boolean cutoff at chop_ratio=2.0 was specifically
  clipping a high-quality slice. But the magnitude of the change suggests
  the gate is still over-filtering on the wrong side of neutral.

**PnL verdict against hypothesis:**
- Predicted: pnl between g1l1 (5394) and g2l1 (3276); ideally ≥ g1l1.
- Actual: 3774 — between g1l1 and g2l1 but much closer to g2l1.
- **Honest read**: this is a *partial* recovery, not a refutation of
  probabilistic chop. Chop has a sweet spot but the (1.5, 1.0) parameters
  port too aggressively. The gate still drops ~13.5k trades vs g1l1 for a
  PnL cost of -1620 and a sharpe cost of -2.16. The cost/benefit is real
  but the magnitude says chop adds **net residual cost** at this dosage.

**Drawdown:**
- max_drawdown -0.500% — slightly worse than g2l1 (-0.472%) and much better
  than base (-1.73%). Spread-p75 + soft chop preserves most of the risk
  improvement from the prior loops. Drawdown remains the most reliably
  improved metric in this lineage.

**Honesty:**
- mean_slippage = 0.0 by simulator construction — `vs_base_slippage_pct`
  reported as 0.0; not informative on this engine.
- The improvement is genuine (+15.2% pnl, +3.15 sharpe vs g2l1) but the
  algo **still regresses vs base** (-11.46% pnl). g1l1 (spread+cap, no
  chop) remains the island-0 leader at +26.55% vs base.
- Trade count 73800 is well above the low-count flag threshold; metrics
  are statistically meaningful.
- The probabilistic-decay form transferred but did *not* dominate boolean
  by as much as predicted — the magnitude (only ~1.7k extra trades
  re-admitted) suggests the parameters need retuning before declaring
  any verdict on chop's transferability to ptg.

**Direction implications for g3l1:**
- Path-noise has a sweet spot on ptg but the (1.5, 1.0) dosage is too
  steep. Two viable next moves: (a) widen `chop_neutral` to ~2.0 and
  lower `sensitivity` to ~0.5 to admit more mid-band, or (b) revert chop
  entirely and explore a different orthogonal axis (book-flow / signed
  volume imbalance) that doesn't compete with the spread gate.
- Given island-0's current best (g1l1, +26.55%) is *chop-free*, and g2l2's
  best honest framing is "chop adds residual cost vs spread+cap alone",
  option (b) — pivot to a different orthogonal axis — is the higher-EV
  bet for g3l1. The chop investigation has answered its core question:
  chop is partially transferable but at lower marginal value than expected,
  and continued retuning trades against an already-known better baseline.
