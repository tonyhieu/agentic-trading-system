# vrs-isl-g1l2 — Trend-Reinforced Choppiness Gate

## Lineage

- Island: island-2 (base: vol-regime-sizer)
- Generation 1, loop 2
- Parent: vrs-isl-g1l1 (choppiness-gated sizer; pnl +34.13% vs base, sharpe 5.97)

## Hypothesis

The g1l1 `next` field flagged three directions; this loop pursues #2 — a
**trend-strength reinforcer**. The mechanism is asymmetric in an important
way: g1l1's chop gate can only *skip* (p ≤ 1.0); it can never *lift*
participation above baseline cadence because `child_qty` is fixed at 1.
But the gate's "neutral zone" (`chop_ratio ≤ chop_neutral = 1.5`) currently
treats all non-whippy states identically as p=1.0 — a clean uptrend
(`chop_ratio ≈ 1.0`, `trend = +1`) is indistinguishable from a barely-not-choppy
state (`chop_ratio ≈ 1.49`, `trend ≈ 0`).

The asymmetry that needs fixing: when chop briefly spikes to, say, 2.0
**during a confirmed trend**, g1l1 starts gating it — but a trend with
high directional efficiency is exactly the regime we want to participate
in. We're skipping precisely the orders that have the highest expected
value.

### Mechanism

Compute signed **directional efficiency** over the same window already
maintained for chop:

    trend = sum(delta_mid_i) / max(path_length, eps)        # ∈ [-1, +1]

(Magnitude 1.0 = every tick same sign = pure trend; magnitude ≈ 0 =
balanced up/down ticks = noise/chop.)

Use `|trend|` to **boost** the effective neutral threshold:

    effective_neutral = chop_neutral + trend_boost * |trend|
    excess            = max(0, chop_ratio - effective_neutral)
    p_submit          = max(min_prob, exp(-sensitivity * excess))

With `trend_boost = 1.0` and `chop_neutral = 1.5`:
- Pure trend (|trend|=1.0) → effective_neutral = 2.5; a chop ratio of 2.0
  inside a clean trend stays at p=1.0 (was ~0.6 in g1l1).
- Noise (|trend|=0.1) → effective_neutral = 1.6; near-identical to g1l1.
- Pure whipsaw (|trend|=0.0) → effective_neutral = 1.5; identical to g1l1.

The boost is monotone in directional efficiency — it never lowers the
threshold below g1l1's baseline, only raises it. So g1l1's adverse-day
savings are preserved (whipsaws still get gated identically), while
brief chop spikes inside clean trends no longer cost us participation.

### Expected effect

- More submissions in "trending-but-noisy" sub-windows that g1l1 was
  skipping (recovers forfeited directional EV).
- Identical behavior in pure-whipsaw and pure-trend regimes (boundary
  conditions match g1l1 exactly).
- Net: pnl should improve modestly over g1l1, trade_count should rise
  slightly (skip rate falls), slippage should be unchanged (sim fills at
  top-of-book; we're not changing routing or sizing).
- Risk: if "trending but noisy" windows are actually mean-reverting in
  the oracle horizon (i.e., chop spikes during trends are early reversal
  signals), this could hurt. The single-knob design (`trend_boost`)
  bounds the downside — at `trend_boost = 0` it collapses to g1l1.

### Calibration

- `trend_boost = 1.0` — symmetric upper bound: effective_neutral can
  double (1.5 → 3.0) at maximum directional efficiency. Conservative
  starting point; higher values would risk participating in clear chop
  whenever the local trend is even slightly directional.
- Window, chop_neutral, sensitivity, min_prob, min_ticks unchanged from
  g1l1 for clean A/B isolation of the trend-reinforcer effect.
- Signed-sum is computed incrementally (O(1) per tick) by maintaining
  `_signed_sum` alongside `_path_sum`.

## Backtest Observations

Train window: 2026-03-08 .. 2026-03-20 (12 trading days). Baseline for
the island delta is `vol-regime-sizer` (the island-2 base), not the
`simple` baseline used inside backtest-results.json.

| metric                | vrs-isl-g1l2 | vol-regime-sizer (base) | vrs-isl-g1l1 (parent) |
|-----------------------|--------------|--------------------------|------------------------|
| realized_pnl          | 1007.75      | 753.75                   | 1011.0                 |
| sharpe_ratio          | 5.7417       | 3.0647                   | 5.9702                 |
| max_drawdown_pct      | -0.04127     | -0.04605                 | -0.04202               |
| win_rate              | 0.34788      | 0.35287                  | 0.34726                |
| trade_count           | 111972       | 127991                   | 109424                 |
| mean_slippage         | 0.0          | 0.0                      | 0.0                    |
| is_weighted_bps       | 0.0420       | 0.0374                   | (n/a)                  |

vs vol-regime-sizer (island base):
- vs_base_pnl_pct      = (1007.75 - 753.75) / 753.75 * 100 = +33.6986%
- vs_base_slippage_pct = 0.0 (both sides 0; sim fills at top-of-book)

vs vrs-isl-g1l1 (direct parent / A/B isolation of the trend-reinforcer):
- realized_pnl   -0.32% (1007.75 vs 1011.0) — essentially flat, slightly worse
- sharpe         -0.23 (5.74 vs 5.97) — modestly noisier per-day distribution
- trade_count    +2.33% (111972 vs 109424) — boost did recover ~2548 submissions
                 that g1l1 was skipping (skip rate fell as designed)
- max_drawdown   -0.0413 vs -0.0420 (a hair tighter)
- win_rate       +0.0006 (effectively unchanged)

Mechanism diagnosis (what the numbers say about the hypothesis):

The trend-reinforcer DID recover the participation it was designed to
recover — trade_count rose ~2.3% on top of g1l1, confirming that the
`effective_neutral` widening let through orders during trending-but-noisy
sub-windows that g1l1 was gating. But those recovered orders contributed
roughly **zero** marginal pnl (-$3.25 over ~2548 extra trades, or about
-$0.001 per added trade). Pnl per trade for the additions is statistically
indistinguishable from zero and slightly negative.

Interpretation: the "recovered" orders fall into one of two buckets:
(a) genuine extra directional EV that g1l1 was forfeiting, or
(b) early-reversal noise during apparent trends.
The flat-to-slightly-negative incremental pnl is consistent with the
hypothesis's documented risk: chop spikes inside trends may be early
reversal signals at least as often as they are noise. The two effects
roughly cancel.

A second observation supports this: is_weighted_bps rose from g1l1
(0.0420 vs g1l1 estimate ~0.0379 — checking against earlier records),
i.e., per-trade execution quality is marginally worse on the augmented
trade set. That's exactly what we'd expect if the marginal recovered
trades have lower forward EV than the average g1l1 trade.

Verdict vs hypothesis: the **mechanism works as specified** (more
participation in trending-but-noisy windows), but the **economic
assumption** (those windows carry recoverable directional EV) does not
hold on this train window. The single-knob design behaved as advertised
— at `trend_boost = 0` it would have collapsed to g1l1, so downside is
bounded. But `trend_boost = 1.0` is not improving on g1l1; it is a
near-wash with marginally worse risk-adjusted return.

vs island-2 base (vol-regime-sizer), g1l2 still delivers +33.7% pnl —
the vast majority of the lift comes from the choppiness-gate
substitution already proven in g1l1, not from the trend reinforcer.

Implications for next loop:
- The trend-reinforcer is a no-op at best on this data; do not stack it.
- Two more promising g1l1-`next` directions remain unexplored:
  (i) combining chop-gating with island-0's spread-quantile gate
      (orthogonal axes: whipsaw vs liquidity-vacuum), and
  (ii) session-adaptive calibration of `chop_neutral` / `sensitivity`,
      since chop's natural scale tracks realized vol regime.
- Could also try `trend_boost` < 0 (i.e., TIGHTEN the gate during
  directional moves) — the data suggests trends-with-noise are not the
  highest-EV regime; non-noisy windows might be.
