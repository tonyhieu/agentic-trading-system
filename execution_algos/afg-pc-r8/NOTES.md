# Algorithm Notes: afg-pc-r8

## Hypothesis

**Mechanism**: Raised-Threshold AFG (single-variable ablation vs base). Identical to base aggressor-flow-gate in every respect: single 10s rolling trade-tick deque, signed_vol = +size (BUYER) / -size (SELLER) / 0 (NO_AGGRESSOR), O(1) long_net maintained, look-ahead-free pruning by ts_event, reduce-only short-circuit, warm-up unconditional submit, post-skip _position_flat=True anti-cascade. ONLY CHANGE: flow_threshold raised from 2.0 to 5.0. Skip BUY when long_net <= -5.0; skip SELL when long_net >= +5.0.

**Inefficiency exploited**: Base AFG with threshold=2.0 over-gates: it skips marginally-adverse signals where the flow magnitude (2-5 contracts in 10s, ~0.2-0.5 contracts/sec) is not statistically distinct from noise. Empirical: all 7 pc-experiment runs that added skips underperformed base AFG; r3 (lowered threshold to 1.0) FAILED at -0.3%. The marginal gradient at threshold=2.0 appears to point UP (toward less gating, higher threshold). Raising to 5.0 retains only structurally adverse skips (>=2.5x base threshold).

**Why it survives costs**: Zero commission, zero slippage. Edge accrues purely as realized_pnl. Pre-committed falsifiable prediction: realized_pnl on the 12-day train window exceeds base AFG's $1255.5 by at least 5% (PASS gate); skip rate drops from base's 21.6% to roughly 5-10%. Failure mode: if base AFG's 2.0 threshold is near-optimal, raising hurts and realized_pnl < $1255.5 — hypothesis falsified, confirming r3's evidence as a symmetric over-shoot.

**Builds on**: aggressor-flow-gate (base, $1255.5, +704.8% vs simple, sharpe 5.59, skip rate 21.6%). Diverges from ALL 7 prior pc-r1..r7 attempts, which uniformly extended skipping via chains, multi-windows, or lower thresholds.

**Alternatives considered**: (a) Threshold = 3.0 or 4.0: smaller steps; 5.0 chosen for material separation and clearer ablation signal. (b) Multi-variable confluence (round 1 proposal): rejected per Criticizer — confounds the experiment. (c) Threshold = 10.0: too aggressive; would essentially disable gating. (d) Lower threshold (r3 territory): empirically falsified. (e) Drop _position_flat anti-cascade: all passing AFG variants rely on it; not the change under test.

**Debate summary**: 2 round(s), outcome=CONVERGED. Key objections resolved: round 1's two-variable-confounding MAJOR objection was directly addressed by dropping the confluence layer and adopting the Criticizer's single-variable suggestion (threshold 2.0 -> 5.0).

---

## Implementation Decisions

- Code is a verbatim copy of base aggressor-flow-gate with `flow_threshold` default raised from 2.0 to 5.0. No structural change.
- Class names changed to `AFGPCR8Config` / `AFGPCR8Algorithm` to avoid collision with the base classes in the Nautilus registry.
- All other defaults (`window_seconds=10.0`) preserved.

**Concerns**: 
- Single empirical data point (r3) anchors the gradient-direction inference; r3's surface might be non-monotonic with a local optimum at threshold=2.0. The backtest will either confirm the raised-threshold direction or falsify the hypothesis symmetrically with r3.
- If threshold=5.0 fires too rarely (say <5% skip rate), behavior collapses to nearly the `simple` baseline and most of the base AFG edge is lost — clear failure signature.

---

## Backtest Observations

**Results (train window, 12 dates 2026-03-08 to 2026-03-20)**:
- afg-pc-r8 (threshold=5.0):    realized_pnl=$938.00,  sharpe=4.00, trade_count=111,015, win_rate=35.4%
- aggressor-flow-gate (base, threshold=2.0): realized_pnl=$1255.50, sharpe=5.59, trade_count=107,198, win_rate=35.5%
- simple baseline:              realized_pnl=$156.00, sharpe=0.60, trade_count=136,734
- vs_base_pnl_pct       = (938.00 - 1255.50) / 1255.50 * 100 = -25.29%
- vs_base_slippage_pct  = 0% (zero-slippage model both sides)
- vs_simple_pnl_pct     = +501.28% (still strongly beats simple baseline)
- skip rate vs simple   ≈ (136,734 - 111,015) / 136,734 = 18.8% (base AFG: 21.6%)

**What drove improvement**: Nothing improved vs base. r8 still drastically beats the `simple` baseline (+501%) but loses to base AFG by 25.3% on realized P&L and by 1.59 Sharpe points. The retained edge confirms the aggressor-flow concept itself is sound; the threshold is the sensitivity dial.

**What underperformed**: Raising the threshold from 2.0 to 5.0 caused the skip rate to fall only modestly (21.6% -> 18.8% — only 2.8pp less skipping; 3,817 more trades retained). Those marginal retained entries were on average loss-making (or low-quality) — they dragged $317.50 of P&L away. This indicates base AFG's threshold=2.0 skips include a meaningful precision-positive band in the (2.0, 5.0) flow range — those skips were not noise but were filtering real adverse selection.

**Hypothesis verdict**: FALSIFIED. The empirical gradient at threshold=2.0 does NOT point UP. Combined with r3 (threshold=1.0 also lost vs base), this strongly suggests base AFG's threshold=2.0 is at or very near a local optimum on the threshold dimension — both increases AND decreases hurt. The "all prior pc runs underperformed base" pattern was not because they over-gated in a direction that should be reversed; it was because the base's parameter choice and post-skip semantics are already near-optimal on this oracle/data combination.

**Suggested next attempt**: The threshold dimension appears saturated in both directions. A productive next direction would be to attack the *post-skip* behavior under a different lens than chains — e.g., gate the SKIP itself on a confirming microstructure feature (book-imbalance at order time, or microprice momentum) so only the highest-conviction subset of base AFG's threshold=2.0 skips actually fire — keeping the threshold but pruning skips, rather than tuning the threshold itself.

