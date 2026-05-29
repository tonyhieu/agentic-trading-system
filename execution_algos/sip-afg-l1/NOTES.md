# Algorithm Notes: sip-afg-l1

## Hypothesis

**Mechanism**: Same rolling 10-second aggressor-flow gate as
`aggressor-flow-gate`, but replace the uniform sum of signed trade
volumes with an **exponentially-weighted** signed flow. Each trade tick
in the 10s window contributes
`signed_vol * exp(-(order.ts_init - tick.ts_event) / tau_ns)`, with
`tau = 3.0` seconds. Skip BUY entries when `ewma_flow <= -ewma_threshold`,
skip SELL entries when `ewma_flow >= ewma_threshold`. Threshold is
re-scaled to `0.6` (≈ uniform_threshold × tau/W ≈ 2.0 × 3.0/10.0 × 0.964)
so the steady-state skip pressure approximately matches the base algo,
while bursts of fresh aggressor activity trip the gate more readily and
stale flow from ~10s ago contributes only marginally.

**Inefficiency exploited**: The base algo's NOTES.md flags that the
uniform 10s window weights a trade from 9.9s ago equally with a trade
from 50ms ago. Recent aggressor flow is the more predictive of the two
because the oracle's 30s horizon means the next 30s of price action is
what matters; flow 10s ago has had 10s to be priced in already.
Exponential decay concentrates the gate's information weight on the
freshest prints, which should both:
  (a) increase skip selectivity during true momentum bursts that
      coincide with adverse oracle entries, and
  (b) reduce false skips when an old flow signal has stalled but the
      uniform-window gate is still tripped by stale tail-of-window prints.

**Why it survives costs**: The gate operates only on whether to submit
an order, not on quantity or price. There is no additional fill cost
introduced — the same `top_of_book_only` execution applies on every
submitted order, so `mean_slippage` should remain at 0 in the
zero-fill-cost backtest. The gate's value lives entirely in choosing
which oracle entries to take. If exponential weighting truly is a
better encoding of "is the current trade tape adverse to my direction,"
realized P&L should rise.

**Builds on**: `aggressor-flow-gate` (base algo for this experiment
arm). Single concrete change: uniform sum → exponentially-weighted sum
of signed aggressor volumes over the same 10s outer window. All other
mechanics (reduce-only handling, anti-cascade _position_flat reset
after a skip, warm-up unconditional submit, no-quantity-modification)
are preserved verbatim.

**Alternatives considered**: None explored — the seed prompt's method
(steps 1–4) calls for picking ONE weakness and ONE concrete
modification, and I have followed it literally.

---

## Implementation Decisions

- **Tau choice (3.0s)**: A 3-second half-life puts roughly 95% of the
  exponential weight inside the first ~9s, so the 10s outer cutoff is
  a soft fence rather than a hard one — but is still preserved as a
  safety bound so the deque never grows unbounded.

- **Threshold rescaling (2.0 → 0.6)**: For a uniformly-distributed
  stream of unit-signed prints in [0, 10] seconds, the EWMA average
  weight per print is
  `(tau/W) * (1 - exp(-W/tau)) = 0.3 * (1 - 0.0357) ≈ 0.289`.
  So uniform-sum-2.0 ≈ ewma-sum-0.58. I round to 0.6.

- **Outer window kept at 10s**: Pruning still happens at the 10s
  boundary. This is partly for parity (so any P&L delta cleanly
  attributes to the weighting change, not the window change), and
  partly because beyond 10s the exponential weight is <0.04 anyway —
  cheap to discard.

- **Recompute EWMA on every evaluation**: O(deque size) per order. The
  base algo uses an O(1) running sum. With ~100 trades/sec typical and
  ~13 orders/sec from the oracle, this is a few thousand multiplies
  per second — negligible compared to backtest I/O.

- **Constraint compliance**: Quantity invariant preserved (never modify
  order.quantity, only skip or submit). top_of_book_only and
  participation_cap are not touched (parent-order gating only).
  intraday_flat preserved (reduce-only orders always submit).

**Concerns**:
- The threshold-rescaling assumes a uniform distribution of trades in
  the window, which is wrong — actual trade arrivals cluster. If real
  futures trade arrivals are heavily front-loaded (more recent trades
  more dense), the effective EWMA per print will be higher than 0.289,
  meaning my 0.6 threshold is too low and the algo will over-skip.
  Conversely, if arrivals are sparse and uniform, 0.6 is approximately
  right. I did not measure actual trade arrival density on the train
  window before fixing this number — the seed prompt does not require
  a calibration step, and per the experiment's boundary I have not
  improvised one.
- Look-ahead bias: each evaluation uses `order.ts_init` as the
  reference time, and only deque entries with `tick.ts_event <=
  order.ts_init` are present (replay is strictly chronological). No
  future trades leak in.

---

## Backtest Observations

Train window: 12 dates (2026-03-08 to 2026-03-20, excluding 14 and 21
— no data, consistent with the base algo).

**Results summary (sip-afg-l1 vs aggressor-flow-gate base, all 12 dates)**:

| Metric              | sip-afg-l1   | aggressor-flow-gate | delta            |
|---------------------|--------------|---------------------|------------------|
| realized_pnl        | $1,064.75    | $1,255.50           | -$190.75 (-15.19%) |
| sharpe_ratio        | 4.858        | 5.594               | -0.736           |
| mean_slippage       | 0.0          | 0.0                 | 0.0              |
| max_drawdown_pct    | -0.0337%     | -0.0332%            | -0.0005pp (worse) |
| win_rate            | 0.3504       | 0.3549              | -0.0045 (-0.45pp) |
| trade_count         | 106,967      | 107,198             | -231 (-0.22%)    |
| is_weighted_bps     | 0.0591       | 0.0472              | +0.0119 (worse)  |

vs the `simple` baseline (config.yaml pass_gate.baseline):
- vs_baseline_pnl_pct = +582.5% (well above gate)
- vs_baseline_slippage_pct = 0.0%
- gate status against `simple` = PASS

But vs the SIP base_algo (aggressor-flow-gate) — the comparison that
matters for this experiment:
- vs_base_pnl_pct = -15.19%
- vs_base_slippage_pct = 0.0%

**What drove the regression**: EWMA weighting made the gate more
responsive to short-term bursts than the uniform sum, which means it
fired more aggressively on transient flow spikes that turn out to be
noise rather than signal. The 21.6% skip rate in the base algo
included many entries that, in retrospect, looked adverse but were
actually fine. Recency-biasing the flow signal made the gate fire on
those marginal cases more often, costing P&L.

The threshold rescaling (2.0 → 0.6 based on assumed uniform arrival
density) was probably also wrong. NOTES.md flagged this as a concern.
If real futures trade arrivals are heavily front-loaded inside the
10s window (more recent prints denser), the effective EWMA-per-print
is higher than my 0.289 calibration assumes, meaning my 0.6 threshold
is too low and the algo over-skips. The drop in trade_count is small
(-0.22%), so the gate doesn't fire much more often in absolute terms —
but the prints it *does* now block are presumably the more profitable
ones at the boundary.

**What underperformed**: Per-date pattern (sip-afg-l1 vs aggressor-flow-gate):
- 20260308: $101.75 vs $96.00 (+6 best date for sip)
- 20260309: $652.25 (large win — but I didn't compare to base's 20260309)
- 20260313: -$320 (largest single-date loss)
- 20260316: -$326.5 (also a big drag)
- 20260319: $292.5 (also a win)

Total: $1064.75. The wins on a couple dates were not enough to offset
the losses on the two large-volume drag days (313 and 316).

**Hypothesis verdict**: REFUTED. Exponentially-weighted aggressor flow
does NOT outperform the uniform-window version on this train set.
Either (a) the uniform window already captures the relevant signal and
recency-biasing throws away useful information about persistence of
flow, or (b) the threshold rescaling I chose without market-data
calibration is wrong, or (c) both. The seed prompt's method led me to
commit to one mechanism without exploring alternatives or validating
the threshold against actual trade arrival density — and the backtest
demonstrates that this single-pass approach failed.

**Status vs `aggressor-flow-gate`**: FAIL (vs_base_pnl_pct = -15.19%
< 0%). Note that vs the configured `simple` baseline this passes
easily (+582.5%) because both the base algo and this variant inherit
most of their performance from the underlying flow-gating idea, but
the question this experiment asks is whether the SIP arm produces a
better algo than the base, not whether it beats `simple`.

