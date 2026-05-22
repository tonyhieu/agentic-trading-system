# Algorithm Notes: afg-m-l1

Per-iteration experiment — base_algo `aggressor-flow-gate`, context mode
`metrics-only`, loop 1. Starting point: `aggressor-flow-gate` (base).

## Hypothesis

**Context available (metrics-only, loop 1)**: No prior loops exist. The only
numbers in scope are the base algo's fixed comparison metrics:

    realized_pnl=1255.5  sharpe=5.59  mean_slippage=0.0
    win_rate=0.3549  trade_count=107198  max_drawdown_pct=-0.0332%
    vs_baseline_pnl_pct=+704.8%

**Targeted change**: Replace the base algo's flat-window net aggressor flow
(every trade print in the last 10s weighted equally) with an
**exponentially-decayed signed flow** (half-life 5s). The decayed flow at
order time T is `sum( signed_vol * 0.5 ** (age / half_life) )` over the same
10s window.

**Rationale**: The base algo sums signed aggressor volume uniformly across a
10s window, so a print from 9s ago gates an entry just as strongly as a print
from 0.5s ago. Near-term price impact and directional momentum decay quickly;
the freshest aggressor prints carry the most information about the next 30s
(the oracle's `horizon_seconds`). A flat window therefore (a) reacts slowly to
fresh adverse flow and (b) keeps skipping entries on the strength of stale
flow that has likely already mean-reverted. An exponential decay emphasises
recent aggression while still using the full window, which should improve the
quality of the skip decision: skip on genuinely fresh adverse pressure, submit
once that pressure has aged out.

**Threshold recalibration**: With a 5s half-life the decayed sum is roughly
0.54x the flat sum for uniformly distributed prints. To keep the effective
skip rate near the base algo's ~21% rather than ballooning it, the threshold
is lowered from 2.0 to 1.1 contracts (≈ 2.0 x 0.54).

**Expected effect**: Higher per-entry quality → realized P&L >= base, with
win rate flat-to-up. Trade count expected to stay within a few percent of the
base algo's (skip rate held roughly constant by the threshold recalibration).

**Risk**: If adverse aggressor flow is actually persistent rather than
fast-decaying, down-weighting older prints discards real signal and P&L
could fall short of base.

---

## Implementation Decisions

- **Decayed-sum recomputation per order**: Unlike the base algo's O(1)
  running `net_flow`, an age-dependent decay weight changes continuously, so
  the running-sum trick does not apply directly. The decayed flow is
  recomputed by iterating the (small) in-window deque at each order event.
  Orders fire ~1/s (oracle `signal_interval_seconds=1.0`) and the deque holds
  only ~10s of prints, so the per-order cost is negligible and numerically
  safe (no `exp(+t)` overflow from a rebased running sum).
- **Decay weight**: `0.5 ** (age_ns / half_life_ns)` where
  `age_ns = order.ts_init - tick.ts_event`. Age is always >= 0 because replay
  is strictly chronological and the window prune uses `order.ts_init`.
- **Same window/prune logic** as the base algo (10s, `ts_event < cutoff`).
- **Same gate direction logic**: BUY skips when decayed_flow <= -threshold;
  SELL skips when decayed_flow >= +threshold.
- **Anti-cascade guarantee preserved**: after any skip, `_position_flat=True`
  so the next open submits unconditionally.
- **Quantity invariant preserved**: orders are only skipped or submitted whole;
  `order.quantity` is never modified.
- **Reduce-only orders** always execute (intraday_flat compliance).

---

## Backtest Observations

Train window: 12 dates (2026-03-08 to 2026-03-20). Baseline `simple` read
from cache (`--use-cached-baseline`).

**Results — afg-m-l1 vs base algo `aggressor-flow-gate`:**

| metric             | afg-m-l1   | aggressor-flow-gate | delta        |
|--------------------|------------|---------------------|--------------|
| realized_pnl       | 1163.50    | 1255.50             | -7.33%       |
| mean_slippage      | 0.0        | 0.0                 | 0.0%         |
| sharpe_ratio       | 5.130      | 5.594               | -0.464       |
| max_drawdown_pct   | -0.03395%  | -0.03325%           | -0.0007 pp   |
| win_rate           | 0.35335    | 0.35488             | -0.15 pp     |
| trade_count        | 107623     | 107198              | +0.40%       |

(For reference vs the `simple` baseline the script reported delta_pnl_pct
+645.83% — afg-m-l1 still clears the baseline pass gate comfortably; the
relevant comparison for this experiment is vs the base algo, shown above.)

**Hypothesis verdict: NOT SUPPORTED.** The exponentially-decayed flow signal
underperformed the base algo's flat-window sum on every headline metric:
realized P&L -7.33%, Sharpe -0.46, win rate -0.15 pp. The trade count is
essentially unchanged (+0.40%), which confirms the threshold recalibration
(2.0 -> 1.1) held the effective skip rate close to the base algo's. So the
loss is not a skip-rate effect — it is a signal-quality effect: at a matched
skip rate, the decayed gate skipped a *worse* set of entries than the flat
gate.

**Interpretation.** The premise was that near-term aggressor pressure decays
fast and stale prints are noise. The result suggests the opposite within a
10s window: adverse aggressor flow is fairly *persistent*, so a print from
6-9s ago still carries genuine predictive weight on the oracle's 30s horizon.
Down-weighting those older prints discarded real signal and shifted some skip
decisions onto fresher but noisier flow, slightly degrading per-entry quality.
The flat-window sum is, for this signal and window, the better aggregator.

**Trade count** is high (107623) — no low-sample-size concern.

**Note on metrics.** `mean_slippage` is 0.0 on both sides (zero fill-cost
model), so `vs_base_slippage_pct` is reported as 0.0 and carries no
information this loop.

