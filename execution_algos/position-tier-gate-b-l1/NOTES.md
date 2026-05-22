# Algorithm Notes: position-tier-gate-b-l1

Per-iteration experiment — arm: base_algo=position-tier-gate, mode=brief-summary, loop 1.
Starting point: `position-tier-gate` (the base algo).

## Hypothesis

**Observed problem.** Under the current research config (`oracle`, sigma=200 —
a very high-noise signal), the base `position-tier-gate` algo is badly
underwater on the train window:

- base `position-tier-gate`: realized_pnl = -5892.25, sharpe = -27.23,
  trade_count = 101,304
- baseline `simple`:        realized_pnl =  +156.00, sharpe =  +0.60,
  trade_count = 136,734

The base algo's mechanism is "skip the OPEN leg while any position is still
showing in the cache" — i.e. it serializes entries. The base NOTES.md
reports this as a +204.9% PASS, but that was measured under an older config
(sigma=5). With sigma=200 the oracle signal is near-random; serializing
entries no longer concentrates execution on good signals — it just locks the
algo into whichever entry it took and prevents re-entry on a fresher (and
no-worse) signal. The skipped subset of orders is net-negative, so the gate
is actively destroying value relative to the unconditional `simple` baseline.

**Change for this loop.** Replace the *unconditional* serialize gate with a
**portfolio-equity circuit breaker**. Keep the conditioning axis the base
algo established — current portfolio state — but condition on *realized
P&L drawdown* instead of *position-in-flight count*:

- Track cumulative realized P&L of closed positions via `on_position_closed`
  events (the algo maintains its own running tally and running peak).
- An OPEN leg is **submitted** whenever the running realized P&L is within
  `drawdown_halt` dollars of its running peak (i.e. the strategy is at or
  near its high-water mark — let every signal through, capturing the upside
  the base algo throws away).
- An OPEN leg is **skipped** only while running realized P&L is more than
  `drawdown_halt` below its peak — a throttle that engages exclusively
  during losing streaks, when adding fresh exposure on a noisy signal is
  most dangerous.
- Reduce-only / closing orders always submit unconditionally (intraday_flat
  compliance — unchanged from base).

**Why this should beat both the base algo and the baseline.** The base algo
skips opens *all the time*; that blanket throttle is what sinks it under
sigma=200. The circuit breaker only throttles during drawdown, so on the
(many) stretches where the strategy is flat-to-up it behaves like `simple`
and captures that P&L. During genuine losing streaks it cuts new exposure,
which should trim the deep -5892 loss the base algo carries. Net: closer to
`simple` on the good stretches, better than `simple` on the bad stretches.

## Implementation Decisions

- **State tracked**: `_realized_pnl` (running sum of closed-position realized
  P&L) and `_pnl_peak` (running max of `_realized_pnl`). Both reset to 0.0
  in `on_reset` / `on_start` — per-session state, no cross-day leakage.
- **P&L source**: `on_position_closed(position)` → `position.realized_pnl`.
  Read as `float(position.realized_pnl)` defensively (Money object).
  This is a strictly-past event — the position closed before the next
  `on_order` fires. No look-ahead.
- **`drawdown_halt`**: default 150.0 (USD). Chosen as a few times the typical
  per-trade P&L magnitude so the breaker engages on a sustained losing
  streak, not on single-trade noise. A config parameter for later tuning.
- **At session start** (`_pnl_peak == _realized_pnl == 0.0`): drawdown is 0,
  breaker open, all opens submit — behaves like `simple` until the first
  loss accumulates. Correct.
- **Quantity invariant**: orders are submitted or skipped, never modified.
- **No look-ahead**: `on_position_closed` reflects only closes that have
  already happened; `on_order` reads the running tally as of that point in
  the deterministic replay.

## Backtest Observations

**Train window**: 12 dates (20260308–20260320). `--use-cached-baseline`.

| metric          | this algo (b-l1) | base position-tier-gate | baseline simple |
|-----------------|------------------|-------------------------|-----------------|
| realized_pnl    | -1675.25         | -5892.25                | +156.00         |
| sharpe_ratio    | -106.02          | -27.23                  | +0.60           |
| max_drawdown_pct| -0.0155          | -0.0986                 | -0.0529         |
| win_rate        | 0.2966           | 0.3285                  | 0.3506          |
| trade_count     | 32,475           | 101,304                 | 136,734         |
| mean_slippage   | 0.0              | 0.0                     | 0.0             |

**vs base `position-tier-gate`**:
- vs_base_pnl_pct      = (-1675.25 − −5892.25) / 5892.25 × 100 = **+71.57%**
- vs_base_slippage_pct = both slippages 0.0 → **0.0%** (no regression;
  division by zero treated as no change)

**vs baseline `simple`** (config pass gate): vs_baseline_pnl_pct = -1173.88%
— still well below `simple`. Suggested verdict: FAIL.

**What the backtest revealed.** The circuit breaker more than halved the
base algo's loss (-5892 → -1675, a +71.6% improvement vs the base) and cut
max drawdown by ~84% (-0.099% → -0.015%). So the directional hypothesis is
partly supported: throttling new opens during realized-P&L drawdown does cut
the deep loss. BUT it does not get the algo into profit, and it actually
makes things worse than `simple` (+156). Two problems surfaced:

1. **The breaker is sticky.** Once realized P&L falls `drawdown_halt` below
   peak, it stays below — under sigma=200 the strategy rarely recovers a new
   high-water mark, so the breaker latches on early in each session and the
   algo sits flat for most of the day. trade_count collapsed to 32,475 (76%
   below `simple`, 68% below the base algo). The algo never re-arms.

2. **sharpe got worse** (-27 → -106) even though the loss shrank. With so
   few trades and the loss concentrated in the pre-breaker window each day,
   the equity curve is a short steep drop followed by a flat line — low
   denominator, so the rescaled intraday Sharpe blows up negative. This is
   a low-trade-count artifact and should be read with caution, but it does
   flag that the breaker latches too hard.

**Honesty flags.** trade_count 32,475 is low relative to `simple` (136,734)
— the Sharpe figure is distorted by the latched-flat equity curve and should
not be over-weighted. The core, robust readings are realized_pnl and
max_drawdown_pct, both of which improved markedly vs the base.

**Hypothesis verdict**: PARTIALLY SUPPORTED. Drawdown-conditioned throttling
genuinely cuts the loss, but a one-way latching breaker over-throttles. The
fix is a breaker that *re-arms* — e.g. resume submitting opens once realized
P&L recovers part of the drawdown, or use a rolling/decaying drawdown
reference instead of an all-time session peak, or pair the breaker with a
cooldown-then-retry so the algo samples fresh signals after a halt.

