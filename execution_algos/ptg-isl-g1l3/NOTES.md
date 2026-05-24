# ptg-isl-g1l3 — Adaptive (rolling-quantile) queue-imbalance gate

## Hypothesis

**Diagnosis of g1l2 null result.** ptg-isl-g1l2 produced *bit-for-bit
identical* metrics to ptg-isl-g1l1 (5394.25 PnL, 87319 trades, 23.17
Sharpe, identical drawdown). This is not "imbalance gate fires but is
EV-neutral" — that would shift trade count and PnL by at least a few
units. It is the strong signature of a gate that effectively **never
fired** on any order that wasn't already blocked by an upstream gate.

The most likely cause is that the static thresholds 0.30 / 0.70 are too
extreme for the q distribution actually observed on the slice of orders
that survives the position-cap + rolling-spread gates. After the
spread-quantile gate has already removed the highest-spread (and
typically highest-imbalance) moments, the surviving top-of-book is in
calm conditions where bid_size and ask_size cluster close to 50/50.
`q < 0.30` or `q > 0.70` essentially never occurs on the surviving
slice, so the gate is a no-op.

(Alternative explanations — `on_quote_tick` never firing, side-string
mismatch — are inconsistent with g1l1 working since that gate uses the
same callback path; and with the imbalance-skip log lines being
debug-level, "never fired" and "fired but to no effect" are
indistinguishable in the output.)

**Targeted change for g1l3.** Replace the *static* imbalance thresholds
with an **adaptive, rolling-quantile** imbalance gate calibrated on
the same 60-second window already used by the spread gate:

  - Maintain a rolling deque of `q = bid_size / (bid_size + ask_size)`
    samples, one per quote tick, aligned to the spread window.
  - At `on_order()` (after the spread gate has already passed):
      * BUY  OPEN: skip if latest `q` < rolling p10 of recent q.
      * SELL OPEN: skip if latest `q` > rolling p90 of recent q.
  - Warm-up: require ≥ `min_samples` (50) before the gate can fire.

**Why this is expected to improve g1l1's PnL (not just match it).**

  - The static gate forced absolute thresholds onto a distribution that
    is itself conditional on prior gates having already fired. A
    rolling quantile gate self-calibrates: by construction it will fire
    on ~10% of BUYs and ~10% of SELLs in steady state, regardless of
    whether the natural q distribution sits at [0.45, 0.55] or
    [0.20, 0.80].
  - g1l1's spread filter removes "the book is wide" risk; this gate
    adds an orthogonal "the book is leaning away from you" filter.
    They are mechanistically distinct (width vs. asymmetry), so even
    modest overlap should leave some incremental adverse-selection
    slice for the imbalance gate to catch.
  - Adaptive p10/p90 thresholds also remove the parameter-fragility of
    static cutoffs — the gate adapts if MES top-of-book queue dynamics
    drift from day to day within the train window.

**Expected effect.** Modest incremental lift over g1l1
(+1 to +5% PnL, hopefully +0.5 to +1.5 Sharpe) by removing a small
slice of direction-wrong opens that the spread gate misses. Trade
count should drop by roughly the gate's firing rate × (1 - prior gate
firing rate) — order of 2-4% additional reduction from g1l1's 87319.
A null or negative result would suggest queue imbalance on the
*surviving* slice carries little EV — i.e. spread and imbalance are
not as orthogonal as the mechanistic story suggests on this strategy.

## Implementation Decisions

- Started from `execution_algos/ptg-isl-g1l2/execution_algorithm.py`
  (the prior loop in this island's lineage), preserving its three-gate
  evaluation order (position → spread → imbalance).
- Kept the position-tier-gate and rolling-spread gate fully intact.
- Replaced the static `buy_block_threshold` / `sell_block_threshold`
  config params with `imbalance_lower_quantile` (default 0.10) and
  `imbalance_upper_quantile` (default 0.90), plus a shared rolling
  window equal to `spread_window_seconds` so the two adaptive gates
  share the same memory horizon.
- Added a single rolling deque of `(ts_event_ns, q)` samples maintained
  in `on_quote_tick`, pruned to the same `_spread_window_ns` cutoff at
  read time. Quantiles computed via the same linear-interpolation
  routine used for the spread quantile (no `numpy` dependency).
- Added lightweight counters (`_evaluated_open_orders`,
  `_skipped_position`, `_skipped_spread`, `_skipped_imbalance_buy`,
  `_skipped_imbalance_sell`) that are emitted via `self.log.info` in
  `on_stop`. These resolve g1l2's primary diagnostic gap: future loops
  in this island can read backtest stdout/logs to distinguish
  "gate never fires" from "gate fires but is EV-neutral".
- Reduce-only (CLOSE) orders bypass all gates — intraday_flat compliance.
- No look-ahead: `on_quote_tick` populates the q deque in chronological
  replay order; `on_order` reads only cached values.

## Backtest Observations

**Aggregate metrics (train window, 12 dates, 2026-03-08..2026-03-20).**

| metric | base (position-tier-gate) | ptg-isl-g1l3 | delta |
|---|---|---|---|
| realized_pnl | 4262.50 | 5394.25 | **+26.55%** (+1131.75) |
| sharpe_ratio | 17.62 | 23.17 | +5.55 |
| max_drawdown_pct | -0.01727 | -0.00610 | **-64.7% magnitude** |
| win_rate | 0.3720 | 0.3806 | +0.86 pp |
| trade_count | 90433 | 87319 | -3.4% (-3114) |
| mean_slippage | 0.0 | 0.0 | 0.0% (undefined: top-of-book sim) |
| is_weighted_bps | 0.0389 | 0.0285 | -26.7% |

**Result — null with respect to g1l1, identical to g1l2.** Every reported
metric is bit-for-bit identical to ptg-isl-g1l1 and ptg-isl-g1l2:
realized_pnl 5394.25, trade_count 87319, sharpe 23.17, max_drawdown
-0.006099905451465502, win_rate 0.380592998..., is_weighted_bps 0.02846.
The adaptive rolling-quantile imbalance gate, like the static one in g1l2,
produced **zero incremental effect** on top of the position-cap +
rolling-spread-p75 stack inherited from g1l1.

**Gate skip counters — not recovered.** The per-day `self.log.info` lines
emitted in `on_stop` (containing `evaluated_open_orders`,
`skipped_position`, `skipped_spread`, `skipped_imbalance_buy`,
`skipped_imbalance_sell`) are not persisted by the backtest pipeline —
only `metrics.json` + the four CSVs are written per run dir, and no
stdout/log capture file exists under `results/<date>/`. The counters
were emitted to the Nautilus engine logger during each subprocess but
discarded when the subprocess exited. This is the same diagnostic gap
that prompted adding the counters in g1l3; the lesson for g1l4 is that
counters need to be persisted to a JSON sidecar (e.g.,
`results/<date>/gate-counters.json` written from `on_stop`) rather than
log-line emitted, because subprocess log output is not captured by
`scripts/run_research_backtest.py`.

**Interpretation.** Two independent imbalance-gate designs (static
thresholds in g1l2, adaptive p10/p90 in g1l3) both produced bit-identical
results to the no-imbalance-gate baseline (g1l1). The probability of two
mechanically distinct gates *both* coincidentally producing exactly the
same realized_pnl, trade_count, drawdown, win_rate, AND is_weighted_bps
across 12 train dates if either gate actually fired is effectively zero.
The strong inference is that the imbalance gate **never fires on any
OPEN order that wasn't already skipped by an upstream gate** — i.e., the
position-cap and spread gates together pre-filter the order stream so
aggressively that no surviving OPENs hit the imbalance check, OR
`on_quote_tick` is not populating the q deque in time for `on_order` to
read non-empty values, OR the OPEN side classification used by the gate
mismatches what the strategy actually emits.

**Direction for g1l4.** Highest-leverage next step is **not another
gate**. It is one of two things, in priority order:

1. **Persist gate counters to a JSON sidecar** (one-line write in
   `on_stop`) so we can definitively diagnose whether the imbalance
   gate ever fires. Until this exists, every imbalance/timing/orthogonal
   gate added to this lineage is flying blind — we cannot tell a no-op
   from an EV-neutral hit.
2. **Abandon the imbalance axis entirely** and try a structurally
   different orthogonal axis (short-horizon realized vol, trade-intensity
   bursts, or per-tier position-aware sizing instead of binary gating).
   The two consecutive null results strongly suggest queue imbalance on
   the surviving slice of orders carries no exploitable EV on this
   strategy/base combination.

**Honesty note.** The +26.55% PnL lift vs. position-tier-gate is entirely
inherited from g1l1's rolling-spread gate. g1l2 and g1l3 added zero
incremental value. Reporting this loop as "+26.55% vs base" would be
technically accurate but misleading without the context that g1l3 vs.
g1l1 = 0.00%. The next loop's hypothesis must reckon with the fact that
the imbalance branch of this island has produced two consecutive null
diffs.
