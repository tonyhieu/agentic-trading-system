# Algorithm Notes: vrs-f-l1

Loop 1 of the per-iteration experiment, full-trace arm, base = `vol-regime-sizer`.

## Hypothesis

**Starting point**: `vol-regime-sizer` (the base algo). Its core mechanism is
probabilistic skip on open-leg orders, where the skip probability rises
smoothly with `vol_ratio = fast_vol / slow_vol`. Reduce-only orders are always
submitted.

**Observation driving this loop** (from `execution_algos/vol-regime-sizer/NOTES.md`
"Backtest Observations"): the base algo's improvement is asymmetric — it
"consistently reduces losses on adverse days" but "the improvement on positive
days is smaller" because "the algorithm forgoes some upside by occasionally
skipping profitable oracle signals during vol spikes". In other words, the
current vol-only gate skips uniformly with respect to the order's direction. It
treats *all* high-vol moments as bad-for-execution, but a high-vol moment that
is *aligned* with the order direction (e.g. a long order during a strong
upward burst) is actually trend-favorable, not adverse.

**Targeted change for vrs-f-l1**: condition the vol-skip on directional
alignment between the order side and recent mid-price drift.

  - Maintain a short EWM of *signed* mid-price changes — call it `drift`.
    Positive drift means recent up-movement; negative means recent down.
  - When deciding whether to skip an open-leg order in a high-vol regime:
    - Compute the existing vol-based skip probability `p_vol`.
    - Compute an "alignment" indicator: order side is BUY and drift > 0, or
      order side is SELL and drift < 0 → "aligned" (trend-favorable).
      Otherwise → "adverse" (we are buying into a downturn / selling into a
      rally).
    - In the "aligned" case, **soften** the skip: blend `p_vol` toward 1.0 by
      factor `align_boost` (default 0.7) — i.e. `p_eff = p_vol + align_boost *
      (1.0 - p_vol)`. This keeps full participation in trend-aligned high-vol
      bursts.
    - In the "adverse" case, **keep** the original `p_vol` (or optionally
      tighten further — see implementation; default leaves it unchanged).
  - In calm regimes (`p_vol = 1.0`), both branches collapse to full
    participation — no behavior change vs base.
  - Cold-start (`tick_count < min_ticks`) still submits at p=1.0.
  - Drift uses a separate EWM half-life (`drift_halflife = 30`) — short enough
    to capture short-term directional momentum on the 30s oracle horizon but
    long enough to be stable.
  - When `|drift|` is below a noise floor (`drift_noise_floor`), the alignment
    test is undefined and we fall back to the base vol-only behavior (use
    `p_vol` unchanged). This guards against random sign flips when the market
    is genuinely directionless.

**Mechanism / inefficiency exploited**: high realized volatility has two
distinct causes — adverse microstructure (which hurts execution) and trend
bursts (which can help when aligned). The base algo conflates these. By
splitting on `sign(drift) == sign(order)`, we keep the protective skip on
adverse-drift moments while preserving participation in trend-aligned bursts.
Net effect: same loss-reduction on adverse days as the base, plus better
upside capture on positive days. This directly addresses the asymmetry the
base algo's NOTES flagged.

**Why it survives costs**: zero-slippage fill model means execution quality
is not a slippage lever; the edge must come through realized P&L. We are
*relaxing* the skip in a specific subset of high-vol moments (aligned-drift
ones). If those are net-positive for the oracle signal, P&L rises. If they
are no better than random, we degrade toward base behavior — bounded
downside.

**Builds on**: `vol-regime-sizer` (the base algo for this arm).

**Alternatives considered**:
1. Always submit when `align`, regardless of vol — too aggressive; loses the
   loss-mitigation property if alignment is a weak signal.
2. Tighten skip further when `adverse` — possible follow-up. Holding it at
   base in this loop keeps the change incremental and isolates the
   align-boost effect.
3. Use book imbalance or trade aggressor as the directional signal instead
   of mid-drift — drift is the simplest, most direct measure of "what way
   is the market actually moving in the recent past". Other signals can be
   tried in later loops.
4. Replace probabilistic submission with deterministic skip when adverse,
   submit when aligned — discards the smooth vol scaling. Keep the
   probabilistic structure to preserve the base's calibrated decay curve.

---

## Implementation Decisions

- **Drift EWM**: separate EWM of *signed* mid deltas with halflife =
  `drift_halflife = 30` ticks. Initialized lazily on first delta observation.
- **Noise floor**: `drift_noise_floor = 1e-7` in raw mid-price units. Below
  this, alignment is undefined and we use `p_vol` unchanged.
- **Align boost**: `p_eff = p_vol + align_boost * (1.0 - p_vol)`, with
  `align_boost = 0.7`. At `p_vol = 0.05`, `p_eff = 0.05 + 0.7 * 0.95 = 0.715`
  — substantial recovery of participation when drift agrees. At `p_vol = 0.5`,
  `p_eff = 0.5 + 0.7 * 0.5 = 0.85` — modest recovery. At `p_vol = 1.0`,
  `p_eff = 1.0` — no-op.
- **Order side detection**: read `order.side` (BUY / SELL) via the Nautilus
  enum. SELL → expects falling price (drift < 0 is aligned).
- **Reduce-only handling**: unchanged from base — always submitted.
- **Cold start**: unchanged — `tick_count < min_ticks` submits at p=1.0.
- **Determinism preserved**: same SHA-256(client_order_id) uniform draw is
  used for the accept/reject decision. The only change is the value of `p`
  fed into the comparison.
- **Quantity invariant**: unchanged — child_qty = parent_qty = 1.

**Concerns**:
- If oracle losses are not actually correlated with adverse drift (i.e. the
  oracle "errors" are uncorrelated with the local price trend), then
  alignment is uninformative and the boost will recover both wins and losses
  proportionally — degrading toward base behavior with slightly more trades
  and higher variance, not better P&L.
- Drift estimation is noisy on a per-tick basis. The halflife=30 EWM should
  smooth this but may lag fast reversals; the noise floor mitigates the
  zero-drift case.
- Order side enum access (`order.side`) — using `OrderSide.BUY` and
  `OrderSide.SELL` from `nautilus_trader.model.enums`. Comparing
  `order.side == OrderSide.BUY` is standard.
- No look-ahead: drift is updated in `on_quote_tick` from the latest tick
  state at the time the order arrives.

---

## Backtest Observations

Train window: 12 dates (20260308-20260320).
Comparison point: base algo `vol-regime-sizer` (this is the per-iteration
experiment, full-trace arm loop 1).

**Aggregated results, vrs-f-l1 (12 dates)**:
- realized_pnl  = $495.75
- sharpe_ratio  = 1.984 (n_days=12)
- trade_count   = 131,029
- win_rate      = 35.17%
- max_dd_pct    = -0.0463%
- mean_slippage = 0.0 (zero-slippage fill model)
- is_weighted_bps = 0.0367

**Aggregated results, base `vol-regime-sizer` (12 dates, from
execution_algos/vol-regime-sizer/results/backtest-results.json)**:
- realized_pnl  = $753.75
- sharpe_ratio  = 3.065
- trade_count   = 127,991
- win_rate      = 35.29%
- max_dd_pct    = -0.0460%
- mean_slippage = 0.0
- is_weighted_bps = 0.0374

**Deltas vs base_algo (vol-regime-sizer)**:
- vs_base_pnl_pct       = (495.75 - 753.75) / 753.75 * 100 = **-34.23%**
- vs_base_slippage_pct  = 0.0% (both zero — undefined ratio, reported as 0)
- sharpe delta           = 1.984 - 3.065 = -1.081 (large regression)
- trade_count delta     = +3,038 trades (+2.37%) — the alignment-boost
  recovered participation as expected
- win_rate delta         = -0.12pp (barely changed)

**Vs the configured baseline `simple`** (informational, for context only —
the experiment uses base_algo as the comparison point):
- delta_pnl_pct = +217.79% (algo still beats simple, but by far less than
  the base vol-regime-sizer's +383.17%)
- is_weighted_bps = 0.0367 vs 0.0389 baseline (-5.50% — slight improvement)

**What drove the underperformance vs base_algo**: the directional-alignment
boost recovered participation in ~3,000 additional trades (vs base) inside
elevated-vol regimes where `sign(drift) == sign(order)`. Those extra trades
were on net unprofitable. Sharpe dropped sharply (3.07 -> 1.98) and P&L
fell by $258, even though win_rate stayed essentially flat (-0.12pp).
Mathematically, similar win_rate + lower total P&L on more trades means
the *average win shrank or average loss grew* on the marginal aligned-drift
trades — i.e. the trades the boost re-introduced had a worse
expected-value profile than the trades the base skipped.

**Hypothesis verdict**: REFUTED. The premise that "high vol with
order-aligned drift is trend-favorable, hence safer to participate in" is
not supported on this dataset/strategy. Two likely explanations, neither
verified here:

1. *Mean-reversion in MES microstructure*: an order-aligned-with-drift
   moment in a high-vol burst may actually be the *tail* of a move that is
   about to reverse — i.e. you are buying at a local top into a vol burst.
   The base's vol-only skip avoids this regardless of drift sign; the
   alignment relaxation re-introduces this exposure.
2. *Oracle signal already lags drift*: the oracle (sigma=6 in config) has
   a 30s horizon. If its signal tends to fire in the same direction as
   recent drift, then "aligned drift" is essentially the same information
   as "the signal direction" — it's not an independent confirming signal,
   it's a near-tautology, and so it adds no edge while it does re-introduce
   adverse-selection trades.

**What underperformed**: the alignment-boost mechanism itself. The fact
that win_rate did not move while P&L dropped indicates the additional
trades had similar hit-rate but worse magnitude profile (smaller wins or
larger losses), consistent with adverse selection on aligned-drift entries
in volatile regimes.

**What worked / kept**: the base vol-skip structure (cold-start guard,
fast/slow EWM ratio, exp decay) is unchanged and still functions. The
algorithm beats the `simple` baseline by +217.79% on realized_pnl — it is
not broken; it is just worse than its base.

**Implications for next loops**:
- *Do not use mid-drift alignment as a relaxation signal.* The simple
  vol-only skip from the base is robust; relaxing it via drift alignment
  is harmful.
- Promising directions to try instead:
  - Tighten skip further when drift is *adverse* (the opposite of what
    this loop did) — use drift as an additional adverse-selection filter,
    not a participation-recovery filter.
  - Use book imbalance, trade aggressor flow, or spread state instead of
    mid-drift as the directional/regime signal — these may decorrelate
    from the oracle signal direction better than mid-drift does.
  - Try parameter tweaks on the base vol-skip itself (e.g. lower
    `min_prob`, higher `sensitivity`) before adding new mechanisms — the
    base may already be near-optimal at moderate vol but under-skipping
    at extreme vol.
  - Investigate per-date variance — if the loss came from one or two
    specific days, the alignment-boost may be a small-sample artifact
    rather than a robust signal.
