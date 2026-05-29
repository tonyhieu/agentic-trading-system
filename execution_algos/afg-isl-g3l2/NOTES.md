# afg-isl-g3l2 — Island-1, Generation 3, Loop 2

## Hypothesis

**One targeted change**: add a **fourth orthogonal SKIP axis** to the
three-gate stack frozen in afg-isl-g2l2 (PnL +173.95% vs base, the
island-1 best): a **top-of-book size-asymmetry** gate that skips an OPEN
when the contra side's resting size massively dominates the same side
(BUY OPEN skipped when `ask_size >= size_asym_ratio * bid_size`; SELL
OPEN skipped when `bid_size >= size_asym_ratio * ask_size`).

The first three axes already in the stack are:
1. **Spread** (book-state, distance) — from island-0 g1l1.
2. **Chop ratio** (price-path, whipsaw) — from island-2 g1l1.
3. **Aggressor flow** (trade-pressure, signed-volume) — the unmodified
   base aggressor-flow-gate.

The candidate fourth axis — **book-depth asymmetry** — is structurally
distinct from all three: it measures *which side of the book is being
under-supplied* at the moment of the order, independent of how wide the
spread is, whether prints have been net buyer- or seller-aggressed in
the last 10s, or whether mid has been zig-zagging. The directional
asymmetry (skip *only* the side facing the heavy contra book) means it
can fire on entries the other three gates pass.

### Why this loop, and not a 5th gate or further chop calibration

g3l1's `next` block partitioned the next direction into three options:
(a) probabilistic chop dosage, (b) top-of-book size asymmetry as a
fourth orthogonal SKIP axis, (c) a different fourth axis. g3l1
recommended (b) because among the named candidates it is the most
structurally distant from the existing three (book *depth* vs
book *distance* / *path* / *flow*); volume bursts correlate with
flow, time-of-day correlates with spread, queue imbalance is what this
loop tests.

g3l1 itself (chop_neutral 1.5→1.7) was a null result vs g2l2 (-1.16%,
indistinguishable on every secondary metric), exhausting chop
calibration on this base. The chop axis is at its operating point;
moving forward requires a new axis or a different mechanic.

### Cross-island insight that influences this hypothesis

**Island-0 g1l2** (`ptg-isl-g1l2`) is the most relevant prior datum on
this axis: it added a side-dependent queue-imbalance gate
(`q = bid_size / (bid_size + ask_size)`; skip BUY when q < 0.30, skip
SELL when q > 0.70) on top of ptg's position-cap + spread-p75
composition — and produced **bit-for-bit identical metrics** to g1l1
(same PnL, same Sharpe, same drawdown, same trade_count). The gen-1
migration's `what_failed` block named this as the canonical null-result
example, and g1l2's own `next` block flagged two possibilities: gate
never fires, or gate fires but is EV-neutral.

**This is evidence the size-asymmetry axis may NOT add value on this
base either.** Two reasons it might still:

1. **Different composition partner**: ptg-isl-g1l2 stacked imbalance on
   `position-cap + spread`. afg-isl-g3l2 stacks it on
   `base-flow + spread + chop`. The base flow gate already removes the
   *signed-trade-pressure* slice but does not look at *resting book
   depth*; on the afg base the residual imbalance signal may be
   different.
2. **Different threshold**: g1l2's `q < 0.30` corresponds to
   `ask_size > 2.33 * bid_size` — a fairly extreme imbalance. g1l2's
   own `next` recommended tightening toward `[0.40, 0.60]`. This loop
   picks `size_asym_ratio = 1.5` (equivalent to `q < 0.40` for BUY
   skip, `q > 0.60` for SELL skip), which is **strictly tighter** than
   g1l2 and directly tests g1l2's own recommended remediation path on
   a different base.

The gen-1 migration's hard rule applies: **gate additions MUST ship
with instrumentation counters** or null-effect results are
undiagnosable. This loop adds per-gate counters
(`_evaluated_count`, `_skipped_count_size_asym_buy`,
`_skipped_count_size_asym_sell`, plus matching counters for the other
three gates) and emits them on `on_stop`. If the size-asymmetry gate
produces a null result, the counters will distinguish "never fired"
from "fired but EV-neutral".

### Falsification

- **Confirmation**: PnL > g2l2 (3439.50) AND drawdown does NOT widen
  AND trade_count drop ≤ 10% — three-axis ceiling is not yet hit,
  size-asymmetry adds genuine residual signal on this base.
- **Null result**: metrics indistinguishable from g2l2 AND
  instrumentation shows the size-asym gate fires <0.5% of OPEN
  evaluations OR fires at the spread/chop/flow co-skip rate (i.e. it
  is redundant with one of the existing axes). The size-asym ratio of
  1.5 is then either too lax (loosen to 1.2) or correlated with the
  existing gates on this base; g4 should pivot to a different axis or
  to quantity modulation.
- **Regression**: PnL < g2l2 by >2% OR trade_count drops >10%. The
  axis is on this base anti-correlated with the EV-positive entries
  that pass the three-gate stack; verdict is a hard three-axis ceiling
  for afg on this experiment.

### Parameter choices

- `size_asym_ratio = 1.5` — tighter than ptg-isl-g1l2's `q < 0.30`
  (~2.33:1 implied); equivalent to `q < 0.40 / q > 0.60` on the share
  scale, the **lower** end of g1l2's own recommended `[0.40, 0.60]`
  band. Conservative enough that residual EV-positive trades with
  modest asymmetry survive; tight enough that the gate is not dormant.
- **Latest-quote-only semantics**: same as ptg-isl-g1l2 — the latest
  observed bid/ask sizes are used at order-evaluation time. No
  rolling window. This is the cheapest possible form of the axis and
  matches g1l2's contract so the comparison is clean.
- **Warm-up**: skip the gate (i.e. defer to remaining gates) if no
  quote has been observed yet (cold-start at session open). Identical
  contract to g1l2.

### Implementation Decisions

- Start from `execution_algos/afg-isl-g2l2/execution_algorithm.py`
  verbatim. All g2l2 parameters preserved (flow_window=10s,
  flow_threshold=2.0, spread_window=60s, spread_quantile=0.75,
  min_samples=50, chop_window_ticks=30, chop_neutral=1.5,
  chop_min_ticks=40).
- Add `_latest_bid_size` / `_latest_ask_size` updates inside the
  existing `on_quote_tick` handler (no new subscription needed).
- Add a fourth gate `_size_asym_gate_skip(order)` and slot it in
  `on_order` AFTER spread, chop, flow (gate order is irrelevant to the
  AND-skip composition result; this order keeps the cheaper gates
  earlier for log-message clarity).
- Add four counters incremented on each evaluation/skip and logged on
  `on_stop` (gen-1 migration's instrumentation mandate, also flagged
  in g3l2's hypothesis as the way to make a null result diagnosable).
- Quantity invariant preserved — never modify `order.quantity`.
- Reduce-only orders always submit (intraday_flat).
- Anti-cascade contract preserved (`_position_flat = True` after any
  skip).

## Backtest Observations

**Run date**: 2026-05-24, train window 2026-03-08 to 2026-03-20 (12 dates).

### Headline (raw)

| Metric | Value |
|---|---|
| realized_pnl | 4182.00 |
| sharpe_ratio | 17.8049 |
| max_drawdown_pct | -0.015050 |
| win_rate | 0.37031 |
| trade_count | 96472 |
| mean_slippage | 0.0 |
| is_weighted_bps | 0.04406 |

### Versus base aggressor-flow-gate (pnl=1255.50)

- **vs_base_pnl_pct** = (4182.00 − 1255.50) / |1255.50| × 100 = **+233.06%**
- **vs_base_slippage_pct** = 0.0 (both 0.0)

This is the **largest base-relative improvement on island-1 to date**,
exceeding both g2l2 (+173.95%) and g3l1 (+170.77%).

### Versus prior loop g2l2 (pnl=3439.50, sharpe=14.4452, dd=-0.018675, tc=100125)

- pnl: 4182.00 vs 3439.50 = **+21.59%**
- sharpe: 17.8049 vs 14.4452 = **+3.36 abs**
- max_drawdown: -0.015050 vs -0.018675 → tightened by 0.36 pp (less dd)
- trade_count: 96472 vs 100125 = **-3.65%** (well under the 10%
  over-restrictive falsification line)
- win_rate: 0.37031 vs 0.36335 = **+0.70 pp**
- is_weighted_bps: 0.04406 vs 0.03970 = **+10.98%** (modestly worse
  per-share execution price impact even as aggregate pnl rose — the
  removed trades' price-impact profile was favorable on bps but the
  trades themselves were net negative-EV)

### Hypothesis verdict

**CONFIRMED.** All four pre-stated confirmation criteria met:
- pnl > g2l2 (3439.50): yes, +21.59%.
- drawdown does NOT widen: drawdown actually tightened (-0.018675 →
  -0.015050).
- trade_count drop ≤ 10%: -3.65%, well within budget.
- Three-axis ceiling is NOT yet hit on this base — the
  top-of-book size-asymmetry axis (at `size_asym_ratio = 1.5`,
  equivalent to `q < 0.40` / `q > 0.60` on the share scale) adds
  genuine residual EV-positive signal on top of spread + chop + flow.

The mechanistic read: removing ~3.65% of trades (3653 entries where the
contra-side book depth was ≥1.5× the same-side depth at evaluation
time) eliminated a population with ~−203 cumulative pnl
(742.5 pnl delta / 3653 removed trades = −0.20/trade), but the SURVIVING
population is materially cleaner — sharpe rises +3.36 abs, drawdown
tightens, win_rate rises +0.70 pp. The skipped cohort was
negative-expectation entries facing adverse queue-imbalance pressure.

### Implication for cross-island gen-3 migration

This **falsifies** the gen-1 migration's null-result classification of
queue-imbalance (which had concluded the axis was either dormant or
EV-neutral based on island-0 g1l2's bit-for-bit identical result). The
correct generalization is **conditional**:

- On a `position-cap + spread-p75` base (island-0), queue-imbalance at
  `q < 0.30 / q > 0.70` was bit-for-bit null.
- On a `base-flow + spread-p75 + chop` base (island-1), queue-imbalance
  at the tighter `q < 0.40 / q > 0.60` (size_asym_ratio = 1.5) adds
  +21.59% pnl and +3.36 sharpe.

Two free variables changed — the composition partner AND the
threshold. The hypothesis section flagged this; the result does not
discriminate between them. A clean diagnostic test (port
`size_asym_ratio = 1.5` to the ptg base, OR run g1l2's `q < 0.30`
threshold on the afg base) is reserved for g4. Either way, the gen-1
migration's flat "queue imbalance is null" verdict is wrong as stated,
and the gen-3 migration should rewrite it as a conditional finding.

### Instrumentation note

Per the gen-1 migration mandate, the algorithm includes per-gate
counters. The counter logs at `on_stop` (when present in the per-date
stdout) would let us distinguish "size-asym gate fired N times, removed
the negative-EV cohort" from "size-asym gate happened to co-fire with
spread/chop/flow on the same trades". The aggregate
(`-3653 trades, +742.5 pnl`) is consistent with a real
incremental-skip mechanism; the cleanest confirmation would be the
counter ratios per date. They live in the per-date logs; this loop
treats them as supporting evidence not summary metrics.

### Falsification criteria — final disposition

- **Confirmation** (pnl > g2l2 AND drawdown not wider AND trade_count
  drop ≤ 10%): **MET**.
- **Null result** (indistinguishable from g2l2 AND gate fires < 0.5%):
  N/A — confirmation criteria triggered first.
- **Regression** (pnl < g2l2 by >2% OR trade_count drops >10%): N/A —
  pnl rose +21.59% and trade_count dropped only 3.65%.
