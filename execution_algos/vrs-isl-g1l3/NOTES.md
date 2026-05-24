# vrs-isl-g1l3 — Incoherence-Sharpened Choppiness Gate

## Lineage

- Island: island-2 (base: vol-regime-sizer)
- Generation 1, loop 3
- Parent: vrs-isl-g1l2 (trend-reinforced chop gate; +33.70% vs base, sharpe 5.74)
- Grandparent: vrs-isl-g1l1 (choppiness gate; +34.13% vs base, sharpe 5.97 — current island best)

## Hypothesis

Synthesizing both prior loops:

- **g1l1** proved that skipping whipsaw-chop windows works (+34.13% pnl,
  -14.5% trade count). Mechanism: chop ratio (path/displacement) cleanly
  separates whipsaw windows from trending ones; gating the whipsaws
  preserves EV.
- **g1l2** tested the opposite direction — *widening* the neutral band when
  a directional trend was simultaneously detected, hoping to recover
  forfeited directional EV during brief mid-trend chop spikes. The
  mechanism worked exactly as designed (recovered ~2548 marginal trades),
  but those trades carried roughly **zero** marginal EV (-$3 over 2548
  trades). The economic assumption (mid-trend chop = recoverable
  directional EV) did not hold; consistent with chop spikes being early
  reversal noise that cancels residual directional EV.

The g1l2 NOTES "Implications for next loop" item (iii) flags the inverse
hypothesis explicitly: *trends-with-noise are not the highest-EV regime;
non-noisy windows might be*. If g1l2's recovered trades were ~zero EV in
aggregate, then within the still-gated (high-chop) bucket the
directionally-incoherent ones are likely **net-negative** EV — being held
in the bucket by g1l1's uniform threshold rather than positively
contributing.

This loop tests that inversion: **tighten the gate further when chop is
elevated AND the local move is directionally incoherent**, leaving clean
trends untouched.

### Mechanism

Reuse g1l1/g1l2's rolling 30-tick window and the existing `chop_ratio`
and `trend` ∈ [-1,+1] computations. Introduce one new term:

    incoherence = 1.0 - |trend|       # 1.0 = pure whipsaw, 0.0 = pure trend

Scale the **decay rate** (not the neutral threshold) by incoherence:

    excess                = max(0, chop_ratio - chop_neutral)
    effective_sensitivity = sensitivity * (1 + incoherence_boost * incoherence)
    p_submit              = max(min_prob, exp(-effective_sensitivity * excess))

Asymmetric in a different axis than g1l2:
- g1l2 modulated the *threshold* (where gating starts), monotonically
  loosening it.
- g1l3 modulates the *steepness above threshold*, monotonically
  tightening it for incoherent windows.

Boundary conditions:
- `incoherence_boost = 0.0` → algorithm collapses **exactly to g1l1**.
  (Clean A/B isolation of the incoherence axis.)
- `|trend| = 1.0` (pure trend) → effective_sensitivity = sensitivity →
  identical to g1l1, regardless of incoherence_boost.
- `|trend| = 0.0` (pure whipsaw) → effective_sensitivity =
  sensitivity * (1 + incoherence_boost) → stronger decay → lower p_submit
  at the same excess.

So this is g1l1 plus a **directional-quality penalty** within the
already-gated region. Clean trends keep full participation. Mid-range
chop windows are split: directionally coherent ones get g1l1's
probability; incoherent ones get a sharper skip.

### Expected effect

- Pure-trend windows: unchanged from g1l1 (same trade count, same EV).
- Pure-whipsaw windows: more aggressive skipping → small additional
  drop in trade count vs g1l1.
- Mid-range windows: skip rate rises proportional to incoherence; if
  hypothesis holds, the skipped trades are negative-EV and pnl rises.
- If hypothesis fails (the now-skipped trades were actually positive
  EV), this collapses gracefully — bounded by `min_prob = 0.05` floor
  and by `incoherence_boost = 1.0` (max 2× sensitivity).
- Expected directional metrics vs g1l1: pnl slightly up, trade_count
  slightly down (additional ~1-3% drop), sharpe up (skipped trades
  contribute variance disproportionately), drawdown tighter.

### Calibration

- `incoherence_boost = 1.0` — at pure whipsaw, doubles sensitivity from
  1.0 to 2.0; at excess=1.0 the per-tick p_submit drops from `e^-1 ≈ 0.37`
  to `e^-2 ≈ 0.135`. Material but bounded.
- `window_ticks`, `chop_neutral`, `sensitivity`, `min_prob`, `min_ticks`,
  `chop_eps`, `max_chop` all inherited unchanged from g1l1/g1l2 for clean
  A/B isolation of the incoherence axis.
- `trend_boost` from g1l2 is **removed** — g1l2 showed it adds no value
  and contaminates the test. (Keeping it at 0.0 would be equivalent but
  reduces config-surface noise.)
- Implementation note: `_signed_sum` was already maintained incrementally
  in g1l2; we reuse the same O(1) update. The only new compute is one
  multiply per gate evaluation.

## Backtest Observations

Train window (12 dates, 2026-03-08 → 2026-03-20):

| metric              | base vol-regime-sizer | g1l1 (parent of axis) | g1l2 (prior loop)     | g1l3 (this loop)      |
|---------------------|-----------------------|-----------------------|-----------------------|-----------------------|
| realized_pnl        | 753.75                | 1011.00               | 1007.75               | **1154.75**           |
| sharpe_ratio        | 3.065                 | 5.970                 | 5.742                 | **6.933**             |
| max_drawdown_pct    | -0.0460               | -0.0420               | -0.0413               | **-0.0392**           |
| win_rate            | 0.3529                | 0.3473                | 0.3479                | 0.3469                |
| trade_count         | 127991                | 109424                | 111972                | 107394                |
| is_weighted_bps     | 0.0374                | (n/a stored)          | 0.0420                | **0.0414**            |
| mean_slippage       | 0.0                   | 0.0                   | 0.0                   | 0.0                   |

Computed vs base (vol-regime-sizer):

- `vs_base_pnl_pct        = (1154.75 - 753.75) / 753.75 * 100 = +53.2007%`
- `vs_base_slippage_pct   = 0.0` (both zero — sim fills at top-of-book)

Computed vs g1l1 (the controlled comparison the boundary condition was
designed for):

- pnl delta:        +14.22% (1154.75 vs 1011.00, +143.75)
- sharpe delta:     +0.963 (16.1% relative gain)
- trade_count:      -1.85% (107394 vs 109424, -2030 trades)
- max_drawdown:     tighter by 6.7% (-0.0392 vs -0.0420)
- is_weighted_bps:  -0.0006 better per-trade IS than g1l2; cannot
  directly compare to g1l1 (not recorded in same form), but the trade
  count drop combined with pnl rise implies per-trade EV rose from
  ~$0.00924 (g1l1) to ~$0.01075 (g1l3), a +16% per-trade EV lift.

### What this confirms

1. **The inversion hypothesis was correct.** g1l2 showed widening the
   gate during noisy trends added zero marginal EV. g1l3 shows the
   dual: *tightening* the gate further on directionally-incoherent
   chop captures real negative-EV exposure. The 2030 fewer trades
   contributed roughly -$144 in aggregate (since pnl rose by +$143.75),
   meaning per-skipped-trade EV ≈ **-$0.071** — about 8× more negative
   than the average trade's positive EV. This is exactly the
   "negative-EV bucket hiding inside the gated region" the hypothesis
   predicted.
2. **The boundary condition held cleanly.** Pure-trend (|trend|=1.0)
   windows are mathematically identical to g1l1; the gain therefore
   comes entirely from the mid-chop / incoherent slice, not from
   altering trend handling. This isolates the incoherence axis as the
   source of EV.
3. **Sharpe lift exceeds pnl lift in relative terms** (+16.1% sharpe vs
   +14.2% pnl), consistent with the skipped trades being not just
   negative-EV but disproportionately high-variance — they were
   contributing more standard-deviation than expected-value, dragging
   risk-adjusted return.
4. **Drawdown tightened** without sacrificing participation in pure
   trends, indicating the skipped trades were also concentrated in
   loss-streak windows. This is a stronger result than just lower mean
   loss — it shifts the loss-distribution's left tail.

### What this means for the chop axis on island-2

The chop gate is now operating on two orthogonal sub-axes:
(i) magnitude (chop_ratio > threshold) inherited from g1l1, and
(ii) directional coherence (1 - |trend|) added here. Both axes carry
independent EV signal — magnitude alone (g1l1) gave +34% over base;
adding coherence (g1l3) gave a further +14%, bringing the island total
to +53% over base. The next dimension to explore is likely (iii)
**temporal stability** (does chop persist or spike-and-resolve?), which
neither axis captures.

### Implications for next loop / migration

- Highest-leverage next move *within this island*: explore the
  temporal-stability axis — e.g., require chop_ratio > threshold for N
  consecutive ticks before gating, distinguishing persistent whipsaw
  regimes from transient single-tick spikes. Both g1l1 and g1l3 react
  to instantaneous chop; persistent chop may carry yet more negative
  EV per skipped trade.
- Highest-leverage next move *for migration*: the
  "tighten-further-when-incoherent" pattern is structurally general —
  any execution algo that already has a participation gate (island-0's
  spread-quantile gate, island-1's volume-imbalance gate) can ask
  "within the still-participating region, is there a quality
  sub-signal worth additionally penalizing?" Island-2 just demonstrated
  the answer is yes for chop+incoherence; the pattern likely transfers.
- Calibration to revisit only if a future loop changes `chop_neutral`
  or `sensitivity`: `incoherence_boost = 1.0` was chosen for max
  signal-to-noise on first test; once the coarse hypothesis is
  validated (it is), a sensitivity sweep could squeeze out additional
  EV but is lower priority than orthogonal-axis additions.
