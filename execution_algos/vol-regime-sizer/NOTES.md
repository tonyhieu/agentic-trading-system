# Algorithm Notes: vol-regime-sizer

## Hypothesis

**Mechanism**: Continuous volatility-regime trade-size scaling. For each open-leg
order, estimate short-term realized mid-price volatility from the last N quote ticks.
Map this volatility estimate to a scaling factor in (0, 1] that shrinks the child
order quantity as volatility rises. In calm regimes (vol near zero), submit the full
parent quantity. In high-volatility bursts, submit a fractional quantity (floored at
a configurable minimum). Reduce-only / position-closing orders are always submitted
at full parent quantity — this sizing logic only applies to open legs.

The scale factor uses an exponential decay from 1.0 at low vol down to
`min_size_fraction` at vol >= `high_vol_threshold`. Specifically:

    scale = max(min_size_fraction, exp(-vol_z * sensitivity))

where `vol_z = realized_vol / ewm_vol_baseline` is the ratio of current short-term
vol to a longer-term baseline (z-score proxy), and `sensitivity` controls how
aggressively size scales down. This keeps the scale_factor interpretable and
monotonically decreasing in volatility.

**Inefficiency exploited**: The `simple` baseline and the two prior binary-gating
algorithms (`streak-spread-tight`, `ob-imbalance-gate`) always submit the full
parent quantity, even during microstructure turbulence when adverse selection is
highest. The binary gators skip entire trades, losing even profitable entries.
A continuous sizer is more surgical: it reduces exposure when the market is noisy
while remaining active (capturing alpha) on every signal. This is particularly
valuable when the oracle signal has directional edge but the realized fill quality
degrades during vol spikes.

**Why it survives costs**: The current backtest fill model reports zero slippage
(see research/NOTES.md DATA ISSUE), so slippage is not a lever. The edge must come
through realized P&L. Shrinking size in high-vol regimes means smaller losses on
the trades that would have been adverse, while retaining full-size participation on
clean regimes. With sigma=5 (noisy oracle, ~37% win rate in the train window), even
a small consistent improvement in the loss-to-win ratio per contract compounds into
meaningful P&L over 100k+ trades.

**Builds on**: none — original hypothesis. The two prior passing algorithms are
binary gating algorithms that skip trades entirely; this is a fundamentally
different mechanism (continuous sizing). This is a fresh, independent hypothesis.

**Alternatives considered**:
1. Binary skip at high vol threshold (like ob-imbalance-gate): rejected because
   binary skips lose the entire alpha on moderate-vol trades. Continuous scaling
   preserves participation at reduced size.
2. TWAP scheduling within each order: rejected because the oracle fires 1-second
   signals and the horizon is 30 seconds — there's no sub-second splitting benefit.
3. Participation-cap-based sizing: the existing `participation_cap=0.05` constraint
   already caps at 5% of book depth. This algo operates within that constraint,
   using it as a ceiling rather than a target.
4. Fixed-fraction reduction (e.g., always submit 50%): rejected because it doesn't
   adapt to actual current volatility — would reduce size even in calm regimes.

---

## Implementation Decisions

- **Volatility estimator**: EWM (exponentially weighted moving average) of absolute
  mid-price changes from consecutive quote ticks. Two EWMs: a short-window (fast,
  halflife=20 ticks) and a long-window (slow, halflife=120 ticks). The ratio
  `fast_vol / slow_vol` is the vol-regime signal. A ratio > 1 means current vol
  exceeds the rolling baseline (high-vol regime).

- **Probabilistic submission (1-contract orders)**: The oracle strategy always
  generates 1-contract parent orders. With parent_qty=1, true fractional sizing
  (e.g., "send 0.3 contracts") is not representable. The continuous sizing
  hypothesis is realized as probabilistic submission: the submission probability
  `p = max(min_prob, exp(-sensitivity * max(0, vol_ratio - 1)))` varies smoothly
  with vol. In calm regimes p=1.0 (always submit). In high-vol p→min_prob. This
  is analogous to fractional sizing in expectation: over N trades with p=0.3, the
  algorithm participates in 30% of orders — equivalent to sizing at 30% in a
  fractional-contract world.

- **Deterministic pseudo-randomness**: The accept/reject draw uses
  SHA-256(client_order_id) normalized to [0, 1). This is deterministic given
  the same oracle seed (seed=42), so results are reproducible. No shared mutable
  RNG state is used.

- **Cold-start behavior**: Before `min_ticks=30` observations, submit at p=1.0.
  This prevents excessive skipping during the first few seconds of each session
  before the EWMs have meaningful data.

- **Intraday_flat compliance**: Reduce-only orders are always submitted unconditionally.
  No vol-regime logic is applied to close orders.

- **Quantity invariant**: Every submitted order carries the original parent quantity
  (1 contract). The algorithm never inflates quantity. `child_qty = parent_qty = 1`.

**Concerns**:
- No look-ahead bias: the vol estimator only uses quote ticks received before the
  order arrives. The `on_quote_tick` callback populates EWMs in real time;
  `on_order` reads the current EWM state.
- Probabilistic submission introduces variance compared to a deterministic binary
  gate. With ~130k trades across the train window, the law of large numbers should
  make the expectation stable across similar vol regimes.
- The key empirical assumption is that oracle signal losses cluster during
  high-vol periods. If losses and wins are uniformly distributed in time
  (vol-independent), the algorithm degenerates to uniform subsampling and will
  FAIL (lower P&L without improvement, because we skip wins and losses equally).
  This assumption is not verifiable from the train window without EDA — it's the
  hypothesis to be tested.

---

## Backtest Observations

Train window: 12 dates (20260308–20260320, excluding 20260314 and 20260321 — no data).
Baseline: simple execution strategy.

**Aggregated results (12 dates)**:
- vol-regime-sizer: pnl=$2,618.25, sharpe=1.2985, trade_count=124,002, win_rate=35.92%, max_dd=-0.030%
- simple baseline: pnl=$1,984.00, sharpe=0.9086, trade_count=132,536, win_rate=35.57%, max_dd=-0.038%
- delta_pnl_pct: +31.97% (gate requires +5.0%) → PASS
- vs_baseline_slippage_pct: 0.0% (zero slippage fill model; no regression) → PASS
- is_weighted_bps: 0.0360 vs 0.0375 (-4.09% — slight improvement in execution quality)

**Per-date breakdown** (algo pnl / baseline pnl):
- 20260308: $145.25 / $140.50 (+3.4%)
- 20260309: $908.00 / $867.75 (+4.6%)
- 20260310: $592.00 / $578.50 (+2.3%)
- 20260311: $421.75 / $394.75 (+6.8%)
- 20260312: $56.75 / $-13.25 (baseline losing day → algo profitable)
- 20260313: $-252.75 / $-327.75 (both lose; algo loses less, +22.9%)
- 20260315: $-20.50 / $-31.00 (algo loses less)
- 20260316: $-229.50 / $-355.00 (algo loses less, +35.4%)
- 20260317: $-61.25 / $-134.25 (algo loses less, +54.4%)
- 20260318: $305.25 / $272.25 (+12.1%)
- 20260319: $353.50 / $284.75 (+24.1%)
- 20260320: $399.75 / $306.75 (+30.3%)

**What drove improvement**: The vol-regime sizer consistently reduces losses on
adverse days (20260313–20260317) by skipping orders during high-vol bursts when the
noisy oracle signal fires into adverse momentum. The probabilistic skip at
p=exp(-2*max(0, vol_ratio-1)) concentrates participation in calmer regimes where the
oracle edge is cleanest. The improvement is consistent across all 12 dates — algo
beats or matches baseline on every single date. This is a strong result. Reduction
in trade_count (~6.4%) indicates selective skipping is occurring.

**What underperformed**: The improvement on positive days (20260308-20260311,
20260318-20260320) is smaller than on negative days. The algorithm forgoes some
upside by occasionally skipping profitable oracle signals during vol spikes. The
win_rate improvement is small (+0.35pp) compared to the P&L gain, suggesting the
improvement is more about loss mitigation than win rate.

**Hypothesis verdict**: SUPPORTED. The core assumption — that oracle losses cluster
during high-vol periods — is empirically confirmed. The vol-regime signal derived
from the EWM ratio (fast/slow) effectively identifies periods where the noisy oracle
(sigma=5) makes worse calls, and the probabilistic skip reduces participation there.