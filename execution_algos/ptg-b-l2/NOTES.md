# ptg-b-l2 — adverse-move signal-strength override

## Hypothesis

L1 added a 5s position-age override to the base position-tier-gate and was
materially WORSE than the base (-75.33% pnl on the 11 apples-to-apples
dates) because age alone is information-poor — a 5s position is still
mid-forecast on a 30s oracle horizon and flipping it realizes a bad
entry. L1's `next` text identified the highest-leverage direction as a
**signal-strength override**: admit a reversal OPEN only when there is
direct evidence the original entry was wrong, not just that some time
has passed.

The execution algorithm cannot read the oracle's edge magnitude
directly. The cleanest microstructure-side proxy for "signal-strength
change since the original entry" is the **adverse-move on the underlying
mid-price** since the existing position was opened: if the market has
moved against the current position by at least N ticks, the original
entry is empirically losing and reversing it is rational; if the market
has not moved adversely (price still consistent with the original
entry), the flip is far more likely to be noise.

This change drops the time dimension that failed in L1 and replaces it
with a price dimension that directly tests "the original position is
wrong". The same gate skeleton from the base is preserved; only the
override predicate changes.

### One targeted change vs. the base

- BASE (position-tier-gate, position_cap=1):
  - Reduce-only: SUBMIT
  - Open + below cap: SUBMIT
  - Open + at/above cap: SKIP unconditionally

- L2 (this loop):
  - Reduce-only: SUBMIT (unchanged)
  - Open + below cap: SUBMIT (unchanged)
  - Open + at/above cap + order is a REVERSAL (opposite side of current
    position):
      - Compute `adverse_ticks = (current_mid - entry_mid) signed against
        the current position direction`. For a LONG position, adverse =
        price has fallen below entry; for SHORT, price has risen above
        entry.
      - If `adverse_ticks >= adverse_threshold_ticks`: SUBMIT (override —
        original entry is empirically losing, reversal is justified).
      - Else: SKIP (no evidence the original is wrong; treat as noise
        flip-flop, same as base).
  - Open + at/above cap + same-direction add: SKIP (matches the base —
    we are NOT changing this path).

### Why adverse-move and not raw price change

The L1 next text says "signal-strength change is a more direct test of
'genuine reversal' than time". On the execution side, we cannot observe
the oracle signal magnitude; the next best directly-observable thing is
the actual price evidence that the original entry is wrong. If the
oracle just keeps firing the opposite side without the underlying
moving, that's noise. If the oracle fires the opposite side AND the
underlying has moved against the original entry by a meaningful amount
(>= 1 tick / 0.25 in MES), that's signal — the position is sitting on
a loss and reversing realizes the loss while opening a position aligned
with the recent direction.

### Threshold choice

- `position_cap = 1` (unchanged from base)
- `adverse_threshold_ticks = 1` (one MES tick = $1.25 per contract,
  $0.25 in price). One tick is the minimum non-trivial adverse move:
  it means the entire bid-ask spread has displaced against the
  original entry. Smaller thresholds (<1 tick) would admit reversals
  on intra-spread noise; larger thresholds (>=2 ticks) would be too
  conservative and might collapse to the base behavior (almost never
  override). One tick is the natural choice for the first probe of
  this dimension.
- Use the mid-price snapshot at the time of the OPEN fill that
  established the position as the entry reference. Fall back to the
  position's `avg_px_open` if a quote was not recorded at fill time.

### Failure mode I am explicitly betting against

L1 admitted +9,779 extra reversal opens and ALL 11 dates were worse than
the base. The risk for L2 is the same shape — if `adverse_ticks >= 1`
fires too often (low bar, especially when the oracle was right and the
existing position is in profit but the price oscillates by 1 tick),
we'll admit a lot of bad reversals and reproduce L1's failure mode. The
prediction is that requiring "current mid has actually moved against
the existing position" filters out most of the noisy flip-flops L1
admitted, because most flip-flops occur when the price has NOT moved
meaningfully — the oracle is just oscillating around the current
level.

## Implementation Decisions

- Subscribe to quotes via `self.subscribe_quote_ticks(instrument_id)`
  inside an `_ensure_subscribed()` helper called from `on_order`.
  Pattern lifted from `streak-spread-tight` and `aggressor-flow-gate`.
- Record entry mid at fill time using `on_order_filled` is NOT
  available on `ExecAlgorithm` (which only sees orders, not fills).
  Alternative: use the position's `avg_px_open` (filled in by the
  engine after the open fill is processed). At `on_order()` time for a
  later reversal, `self.cache.positions_open()` returns the open
  position with its `avg_px_open` already set.
- Current mid: `quote = self.cache.quote_tick(instrument_id)`;
  `mid = (quote.bid_price + quote.ask_price) / 2`.
- "Reversal" check: `order.side == OrderSide.SELL` while position is
  LONG, or `order.side == OrderSide.BUY` while position is SHORT.
- "Adverse" sign convention: for LONG, adverse means mid has fallen
  below entry, so `adverse = entry_mid - current_mid`. For SHORT,
  adverse means mid has risen above entry, so
  `adverse = current_mid - entry_mid`. The override condition is
  `adverse >= adverse_threshold_ticks * tick_size`.
- Tick size for MES: 0.25.
- Diagnostic counters: `submitted_normal`, `submitted_reversal_override`,
  `skipped_same_dir`, `skipped_reversal_no_adverse`.

## Backtest Observations

### Aggregate (11 apples-to-apples dates; 20260319 OOM-dropped both sides)

| Metric                | ptg-b-l2 | base ptg (same 11 dates) | simple (same 11 dates) |
|-----------------------|----------|--------------------------|------------------------|
| realized_pnl          | $2092.25 | $3564.25                 | $43.25                 |
| trade_count           | 81,034   | 73,802                   | 111,489                |
| sharpe_ratio          | 10.078   | ~4-5                     | ~0                     |
| mean_slippage         | 0.0      | 0.0                      | 0.0                    |
| max_drawdown_pct      | -2.45%   | -                        | -                      |
| win_rate              | 0.3631   | -                        | -                      |

### Versus configured baseline (simple)

- vs_baseline_pnl_pct: **+4737.57%** -- pass_gate is +5.0%, so STATUS = **PASS** per the configured gate.
- vs_baseline_slippage_pct: 0.0 (no regression -- zero fill-cost model).
- vs_baseline_is_bps: -0.7052 (slightly better IS vs simple).

### Versus base_algo position-tier-gate on the same 11 dates

- vs_base pnl_pct: **-41.30%** ($2092.25 vs $3564.25)
- vs_base trade_count: **+9.80%** (+7,232 admitted reversal opens vs base)
- Per-date pnls (l2 vs base):
  - 20260308: 145.00 vs 168.50 (-14.0%)
  - 20260309: 757.75 vs 987.25 (-23.2%)
  - 20260310: 498.00 vs 639.50 (-22.1%)
  - 20260311: 350.00 vs 410.25 (-14.7%)
  - 20260312: 75.00 vs 288.25 (-74.0%)
  - 20260313: **-195.75** vs 65.50 (worst day; admitted reversals drove a loss vs base's small gain)
  - 20260315: 16.25 vs 26.75 (-39.3%)
  - 20260316: **-200.25** vs -37.00 (5.4x worse; second worst day -- high-trade-count day, base already losing)
  - 20260317: **-48.25** vs 42.50 (sign flip)
  - 20260318: 314.75 vs 421.25 (-25.3%)
  - 20260320: 379.75 vs 551.50 (-31.1%)
- All 11 dates underperform the base in absolute dollars; 3 dates flipped from positive to negative under l2.

### Mechanical diff L2 vs L1

L1 admit predicate (cap hit + reversal): `age_ns(position) >= 5s`
L2 admit predicate (cap hit + reversal): `adverse_ticks(position) >= 1 tick` (price moved against entry by >= one MES tick)

L2 also distinguishes reversal vs same-direction-add at/above cap (same-dir is unconditionally skipped, matching base). L1 had no such distinction -- any matured cap-hit OPEN was admitted regardless of direction.

### What drove the jump from L1 to L2

L1: pnl=$879.25, trade_count=83,581, vs_base=-75.33%
L2: pnl=$2092.25, trade_count=81,034, vs_base=-41.30%

L2 recovered $1213 of pnl on 2,547 fewer trades. The adverse-move predicate is materially better than the age predicate: requiring direct price evidence ("the original position is sitting on a loss") filters out a meaningful fraction of the noise flips L1 admitted, and the surviving reversals carry better expected pnl. The signal-strength direction L1's next text recommended was correct in sign; one tick is just not a tight enough bar.

### Sharpe note (honesty)

sharpe_ratio = 10.078 over only 11 days (sharpe_n_days=11) is an unusually high number. With a small N and several modest-pnl days driving low daily variance, the annualized ratio is inflated relative to what longer histories would show. The primary verdict metric is realized_pnl; treat sharpe at this sample size as directional only, not a precision number. The base ptg's sharpe over the same window is in the ~4-5 range, so even taking the inflated number at face value L2's sharpe is roughly 2x base -- consistent with l2 having lower daily variance because the adverse-move predicate damps the worst spike days the base sometimes sees on bad-oracle dates. But realized_pnl is the bottom line, and on that l2 is materially worse than base.

### Hypothesis verdict

PARTIALLY VINDICATED in direction, FAILED in level.

Direction: replacing the L1 age predicate with an adverse-move predicate did recover most of the L1->base gap (-75.3% -> -41.3%, a +34 pp recovery on a single change). The signal-strength axis is the right one.

Level: 1 tick is too low a bar. Per the failure prediction I explicitly bet against in the Hypothesis section above: "if adverse_ticks >= 1 fires too often we'll admit a lot of bad reversals". That is what happened -- 7,232 extra admitted reversals, all 11 dates worse than base, three sign flips on already-marginal days. The base's blanket-skip is still beating any one-tick admit policy.

### Single highest-leverage next change for L3

Raise the adverse threshold. The L2 hypothesis section explicitly said "smaller thresholds admit noise flips; larger thresholds collapse to base behavior" -- L2 is at the noisy end. The natural next probe is **adverse_threshold_ticks = 3** (= $0.75 in price, three full-spread displacements against the original entry). This represents a clearly distinguishable adverse-price regime ("the original entry was wrong by 3 ticks of mid-move"), not bid-ask oscillation. The expected result is fewer admitted reversals (closer to base's trade count of 73,802) with better per-admit pnl, which should narrow or reverse the vs-base gap. If 3 ticks collapses to base behavior with no admitted reversals, L4 can probe 2 ticks; if 3 ticks still underperforms base, the signal-strength axis is exhausted via this proxy and L4 should pivot to a different conditioning variable (spread, recent fill direction). The trade_count delta vs base is the key in-flight diagnostic: if l3 has +trade_count vs base, the override is still admitting too many reversals.
