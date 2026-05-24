# Algorithm Notes: vrs-b-l1

Experiment arm: `per_iteration_experiment` / base `vol-regime-sizer` /
context mode `brief-summary` / loop 1.

## Context loaded for this loop

None. Loop 1 of the brief-summary arm has no prior loops to summarize, so
`context_chars_in = 0`. Hypothesis derived from the base algo
(`vol-regime-sizer`) directly.

## Hypothesis

The base `vol-regime-sizer` skips a fraction of OPEN orders any time the
fast/slow vol ratio exceeds 1, regardless of price direction. That treats
all high-vol regimes as equally adverse. But adverse selection at high
vol is directional: a BUY arriving while the mid is drifting down has
high adverse-selection cost; the same BUY arriving while the mid is
drifting up at the same vol may actually be a good fill (we are joining
a move with us).

**Change:** add a signed drift EWM. Apply the base vol-skip ONLY when the
drift is "against" the order side. When drift aligns with the order side
(or is below threshold), force p = 1.0.

Expected effect:
* trade_count: drops less than base — skips now require two conditions.
* realized P&L: should improve if adverse-selection losses cluster on the
  high-vol-AND-adverse-drift subset of orders.
* slippage: zero-fill model, so no slippage effect either way.

Risk: if drift is uncorrelated with realized fill outcome (vol alone is
the dominant signal), this conditions skips on noise and effectively
under-skips, dragging pnl toward the unfiltered baseline rather than
above the base algo.

## Implementation Decisions

* Drift EWM half-life = 40 ticks — chosen between the fast (20) and slow
  (120) vol windows to be reactive but not noisy.
* Drift threshold = 0.05 (~2 MES ticks of 0.25 each). Below threshold,
  drift is treated as neutral and the vol skip is bypassed (full
  participation).
* Drift gate uses `OrderSide.BUY` / `OrderSide.SELL` from
  `nautilus_trader.model.enums`.
* Reduce-only orders: always submit unconditionally, same as base
  (intraday_flat compliance).
* Deterministic SHA-256(client_order_id) draw retained from base —
  reproducible.
* Cold-start guard: during `tick_count < min_ticks`, treat drift as
  not adverse (return False) so the cold-start window submits at p=1.0
  just like the base.

## Backtest Observations

Train window: 2026-03-08 .. 2026-03-20 (Sun-Fri). The aggregator dropped
**20260319** from both sides (algo subprocess OOM-killed with SIGKILL on the
690 MB DBN partition — the largest of the 12 dates). The vrs-b-l1 vs simple
comparison is therefore strictly apples-to-apples over **11 dates** (both
sides excluded the same date).

### Aggregate vs `simple` (gate baseline), 11 dates

| metric            | vrs-b-l1   | simple     | delta      |
|-------------------|------------|------------|------------|
| realized_pnl      | $42.50     | $43.25     | -1.73%     |
| sharpe_ratio      | 0.1704     | 0.1736     | -1.88%     |
| trade_count       | 111,488    | 111,489    | -1 trade   |
| win_rate          | 0.3502     | 0.3502     | +0.00 pp   |
| mean_slippage     | 0.0        | 0.0        | +0.00      |
| max_drawdown_pct  | -0.0529    | -0.0529    | +0.00      |
| is_weighted_bps   | 0.0427     | 0.0427     | -0.04      |

Verdict against `pass_gate` (min_pnl_improvement_pct=5.0,
close_margin_pct=2.0, max_slippage_regression_pct=5.0):
**FAIL** — delta_pnl_pct=-1.73 is far below the +5.0 PASS threshold and
also outside the CLOSE band (the CLOSE band sits within 2 pp of the gate,
so +3.0% .. +5.0%). Slippage shows no regression (0.0 on both sides under
the zero fill-cost model — see research/NOTES.md).

### Per-date deltas (algo - baseline)

| date     | trades (algo / base) | pnl_algo  | pnl_base  | delta_pnl |
|----------|----------------------|-----------|-----------|-----------|
| 20260308 | 373 / 373            | 109.50    | 109.50    | 0.00      |
| 20260309 | 2975 / 2975          | 621.75    | 621.75    | 0.00      |
| 20260310 | 2386 / 2386          | 403.50    | 403.50    | 0.00      |
| 20260311 | 2537 / 2537          | 192.25    | 188.25    | +4.00     |
| 20260312 | 5713 / 5714          | -245.00   | -240.25   | -4.75     |
| 20260313 | 8548 / 8548          | -512.75   | -512.75   | 0.00      |
| 20260315 | 1922 / 1922          | -41.50    | -41.50    | 0.00      |
| 20260316 | 20783 / 20783        | -521.50   | -521.50   | 0.00      |
| 20260317 | 21490 / 21490        | -246.75   | -246.75   | 0.00      |
| 20260318 | 22219 / 22219        | 156.75    | 156.75    | 0.00      |
| 20260320 | 22542 / 22542        | 126.25    | 126.25    | 0.00      |

The drift gate fired on **exactly one order** across 111,488 orders
(20260312: vrs-b-l1 skipped one BUY that the baseline submitted,
contributing the -4.75 delta on that date and the +4.00 delta on
20260311 — but the 20260311 delta of +4.00 cannot be the same skip event
since the trade counts on 20260311 are equal). The net direct effect was
-0.75 across 11 dates.

### Aggregate vs `vol-regime-sizer` (base_algo), 11 dates

I also re-aggregated the base_algo `vol-regime-sizer` over the same 11
dates for an apples-to-apples comparison to the algorithm vrs-b-l1
derives from:

| metric        | vrs-b-l1   | vol-regime-sizer | delta              |
|---------------|------------|------------------|--------------------|
| realized_pnl  | $42.50     | $579.50          | **-92.67%**        |
| trade_count   | 111,488    | 104,372          | +7,116 (+6.82%)    |

The base algo's straight vol_ratio skip filters ~7,100 adverse-vol-regime
trades and gains ~$580 over these 11 dates. vrs-b-l1 conditions that
skip on directional drift adversity, but the threshold I picked
(drift_threshold=0.05 with drift_halflife=40) almost never triggers —
the algo collapses to the simple unfiltered baseline.

### Hypothesis verdict

**Falsified, with the caveat that the hypothesis was never meaningfully
tested.** The intent was to PRESERVE the base's vol skips on the
"adverse-drift" subset and RELAX them on the aligned subset. What
actually happened is the drift-adversity condition is so rarely true
that the algo bypasses the vol skip on essentially every order, giving
up the base's entire ~$580 gain over baseline. The drift threshold and
half-life I chose were calibrated for "noticeably directional moves on
MES" (5 cents over a ~40-tick window), but on a tick-by-tick EWM of
signed mid-increments where most ticks are ±0 (no quote change) or ±0.25
(one tick), the EWM rarely reaches |drift| > 0.05.

I cannot conclude anything about the directional-adverse-selection
hypothesis itself from this run. To actually test the hypothesis a
future loop would need either (a) a much smaller drift_threshold (e.g.
0.005-0.01) so the gate fires on a meaningful fraction of orders, or
(b) a different drift signal (e.g. signed trade flow rather than
signed mid-increment), or (c) flip the gate semantics so the default
is to apply the vol skip and the override is to bypass only when drift
strongly aligns.

### Known data-coverage issue

20260319 (the 690 MB partition) consistently OOM-kills inside the
docker container's memory limit during the DBN load step
(`from_dbn_file` is single-pass and decodes the full file before the
instrument filter applies). The runner correctly dropped it from both
sides of the aggregate, so the comparison is fair, but the train
window evaluated is effectively 11 of 12 configured days. Reported
metrics reflect 11 days. This is an infrastructure constraint, not a
property of the algorithm.
