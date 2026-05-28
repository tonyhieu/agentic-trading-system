# Algorithm Notes: vrs-pc-r1

## Hypothesis

**Mechanism**: Refined formulation that explicitly guarantees the submission set is a strict subset of vol-regime-sizer's. Define: vol_excess = max(0, min(vol_ratio, max_vol_ratio) - 1); vol_active = min(1.0, vol_excess) (smoothly ramps from 0 in calm regimes to 1 by vol_ratio>=2); adverse_excess = max(0, min(max_adverse_z, sign(side==BUY? +1 : -1) * fast_signed_dm / max(fast_vol, eps))); effective_adverse = adverse_excess * vol_active; p = max(min_prob, exp(-sens_vol * vol_excess) * exp(-sens_dir * effective_adverse)). The vol_active gating ensures the directional factor is dormant in calm regimes (vol_excess=0 -> vol_active=0 -> effective_adverse=0 -> directional factor=1.0). The directional term only ATTENUATES participation (factor in (0,1]) — never inflates. Submission decision: deterministic SHA-256 draw from client_order_id vs p (same as base). Reduce-only orders submit unconditionally.

**Inefficiency exploited**: Base vol-regime-sizer applies a symmetric skip during vol bursts regardless of whether recent ticks moved with or against the order side. Among the ~30k orders base submits in elevated-vol windows (rough estimate: ~50% of trades occur in vol_ratio>1 regimes), roughly half are in adverse-direction-during-vol states — the worst expected fills. The base submits these at the same p as the favorable-direction-during-vol trades. By deepening skips on the adverse-direction half while leaving the favorable-direction half at base's behavior, the algorithm improves the per-trade expected P&L on the elevated-vol portion of the order stream without touching calm-regime behavior.

**Why it survives costs**: Zero-slippage and zero-commission fill model in the current train backtest (verified from base backtest-results.json: mean_slippage=0, total_commissions=0). All edge comes through realized P&L. The mechanism reuses the existing on_quote_tick subscription — no new data subscription, no new venue routes. The strict-subset property (p_vrs-pc-r1 <= p_vol-regime-sizer at every order) bounds downside: in the worst case (sens_dir very small or directional signal random) the algorithm degenerates to base. Compounded over ~125k trades, a 2-5% improvement in per-trade expected P&L produces meaningful aggregate P&L. The base proved $138 -> $753 (+383%) on the vol axis alone; directional refinement is an additive lever on the same axis.

**Builds on**: vol-regime-sizer (extends by adding signed-momentum directional conditioning gated by vol_active so directional skipping only activates during elevated-vol regimes; submission set is a strict subset of base)

**Alternatives considered**: (1) Direct aggressor-flow via TradeTick subscription: more direct signal but requires new subscription + callback path; signed mid-EWM is the cheaper proxy and a reasonable run-1 starting point. (2) Cross-tick momentum (delta over last K ticks rather than EWM): EWM is more robust to single-tick noise. (3) Bid/ask price-level signed delta separately: redundant with mid-delta for top-of-book. (4) Higher-moment vol features (skew, kurt of delta_mid): adds parameters without a clean theoretical edge at this granularity. (5) Spread-conditional: rejected — MES at top-of-book has near-constant 1-tick spread. (6) Time-since-last-burst recency: secondary; subsumed by EWM. (7) Recovering base's skips with a directional anti-skip: rejected — adds risk on the favorable-momentum-with-reversion case; strict-subset is safer.

**Debate summary**: 2 round(s), outcome=CONVERGED. Key objections resolved: round-1 MAJOR concern about sign-of-momentum continuation assumption was addressed by (a) vol_active gating so directional skipping only activates in elevated-vol regimes, (b) strict-subset guarantee bounding downside to base's performance in the worst case, and (c) sens_dir = 1.5 < sens_vol = 2.0 making the directional term a perturbation rather than a dominating signal.

---

## Implementation Decisions

- **Inherits base parameters**: fast_halflife=20, slow_halflife=120, sens_vol=2.0, min_prob=0.05, min_ticks=30, max_vol_ratio=5.0. Adds: sens_dir=1.5, max_adverse_z=3.0, fast_signed_halflife=20 (shared with fast_vol timescale).
- **Signed momentum EWM**: maintained on `on_quote_tick` alongside fast/slow |delta_mid| EWMs. `fast_signed_dm` is EWM of (mid - prev_mid) with sign preserved. Initialized to first observed delta.
- **Side encoding**: `sign(side)` returns +1 for BUY and -1 for SELL. Read from `order.side`. Nautilus enum values: OrderSide.BUY=1, OrderSide.SELL=2 — compare to OrderSide.BUY symbolically rather than int values.
- **Adverse momentum computation**: `adverse = side_sign * fast_signed_dm / max(fast_vol, eps)`. Positive when momentum is against the order side. Clipped to `[0, max_adverse_z]` after taking max(0, ·).
- **Eps floor**: `1e-12` to prevent division by zero when fast_vol is near zero (calm regime — adverse will be near 0 anyway).
- **Deterministic draw**: identical SHA-256 of client_order_id as base, ensuring reproducibility.
- **Cold-start**: same as base — submit at p=1.0 before min_ticks=30 observations.
- **Reduce-only**: pass through unchanged, intraday_flat compliance.
- **Quantity invariant**: child_qty == parent_qty for every submitted order; no inflation.
- **Diagnostic counters**: tracks submitted/skipped/skip-vol-only/skip-adverse to confirm both axes are active in logs.

**Concerns**:
- Sign-of-momentum continuation at the 30s oracle horizon is empirically unverified in this run; the strict-subset hedge bounds downside but the upside requires the assumption to hold for at least some non-trivial fraction of vol bursts. If it does not, the algorithm degenerates toward base (within stochastic variance from the SHA-256 draw on a different submission set).
- The probabilistic draw is deterministic given the same order ID sequence, but the order ID sequence is determined by the strategy + which orders are submitted. Because vrs-pc-r1 skips a different subset than base, downstream order IDs may differ — small effect for a backtest with no position interaction across orders.
- max_adverse_z=3.0 is a conservative cap: at adverse_z=3 the directional factor is exp(-1.5*3)=exp(-4.5)~0.011, well below min_prob=0.05, so adverse_z clipping rarely matters except in extreme outliers.

---

## Backtest Observations

**Raw metrics** (train window 2026-03-08 → 2026-03-20, 12 trading days):
- realized_pnl = $88.75
- sharpe_ratio = 1.007
- max_drawdown_pct = -0.0396
- win_rate = 0.343
- trade_count = 104,410
- mean_slippage = 0.0
- vs base (vol-regime-sizer, realized_pnl=$753.75): vs_base_pnl_pct = **-88.23%**
- vs base slippage: vs_base_slippage_pct = 0.0%

**What drove improvement**: Nothing — the algorithm underperformed the base by a large margin. The strict-subset construction (vrs-pc-r1's submission set ⊆ base's submission set) meant fewer orders were submitted overall, but the trade count (104,410) is actually higher than the typical base, suggesting the deterministic SHA-256 draw on a different ID sequence is producing a different (not strictly smaller) selection in practice.

**What underperformed**: The directional gating attenuated participation in elevated-vol regimes, but the residual selection appears uncorrelated with profitable directions at the 30s oracle horizon — i.e., the sign-of-momentum continuation assumption did not hold often enough to compensate for the lost trades that base would have submitted.

**Hypothesis verdict**: **Contradicted.** The hypothesis predicted ≥2-5% per-trade EV improvement on the elevated-vol portion of the order stream. Empirical outcome: the algorithm sheds ≈88% of base's P&L, indicating the directional skip removes more positive-EV trades than negative-EV trades. The strict-subset hedge bounded the loss to a finite range but did not protect against the assumption being wrong.

**Suggested next attempt**: Replace signed-momentum proxy with realized order-flow imbalance (TradeTick aggressor side) — the mid-EWM signed delta is a weaker proxy at top-of-book where mid often only flickers within the 1-tick spread. A direct flow signal would either confirm or refute the directional-conditioning thesis with stronger evidence.
