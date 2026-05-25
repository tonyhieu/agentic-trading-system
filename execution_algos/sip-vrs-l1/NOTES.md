# Algorithm Notes: sip-vrs-l1

## Hypothesis

**Parent**: `vol-regime-sizer`.

**Single concrete modification — directional-headwind gate.**

The parent algorithm gates OPEN orders on an *unsigned* vol-ratio
(`fast_vol / slow_vol` of `|Δmid|`). This signal is direction-blind:
a 5-tick rip up and a 5-tick crash down produce identical skip
probabilities. But the oracle strategy emits *directional* orders.
A BUY into recent downward drift is "fading the burst" (likely to print
a loss); a BUY into recent upward drift is riding momentum (likely to
print a win). The parent currently throws away both regimes at the
same rate, discarding wins as well as losses during vol spikes.

Replacement gate:

    ewm_drift = EWM(Δmid, drift_halflife)           # SIGNED
    slow_vol  = EWM(|Δmid|, slow_halflife)          # unsigned baseline
    headwind  = -side_sign * ewm_drift / slow_vol
    headwind  = clip(max(0, headwind), 0, max_headwind)
    p_submit  = max(min_prob, exp(-sensitivity * headwind))

- `headwind > 0`  ⇔ recent micro-drift is *against* the order side
  → probabilistic skip.
- `headwind ≤ 0`  ⇔ drift is with the side (or neutral) → submit at p=1.0.

Everything else — deterministic SHA-256(client_order_id) draw,
reduce-only-always-submit, EWM update from `on_quote_tick`, the
`min_ticks` cold-start guard, `min_prob` floor — is inherited unchanged.

**Inefficiency exploited**: oracle losses cluster on entries that
*fade* short-term drift. The unsigned vol-ratio in the parent cannot
distinguish "fade" from "ride," so it skips uniformly across both.
A signed-drift gate skips only on the fade regime, retaining the
ride-regime wins.

**Constraints**: top_of_book_only untouched (no posting changes);
participation_cap untouched (parent orders are 1 contract); intraday_flat
preserved (reduce-only always submits); quantity invariant preserved
(skip ⇒ 0 child fills, submit ⇒ exactly parent quantity).

**Expected direction** vs `vol-regime-sizer`:
- realized_pnl: ↑ (stop discarding momentum-aligned wins).
- mean_slippage: 0 (zero-slippage fill model; no regression).
- trade_count: between `simple` (more) and `vol-regime-sizer` (fewer).
- sharpe: ↑ (lower variance from selective skipping).

**Risk**: if oracle losses are *symmetric* in drift direction (i.e.,
losses happen equally on fade and ride regimes), the headwind gate
degenerates and may underperform the parent by skipping random subsets.
This is the empirical question the backtest answers.
