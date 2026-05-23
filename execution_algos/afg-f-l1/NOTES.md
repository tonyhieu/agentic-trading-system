# Algorithm Notes: afg-f-l1

Per-iteration experiment — base_algo `aggressor-flow-gate`, context mode
`full-trace`, loop 1. Starting point: `aggressor-flow-gate` (base).

## Hypothesis

**Context available (full-trace, loop 1)**: No prior loops exist in this arm.
Only the base algo's fixed comparison metrics are in scope:

    realized_pnl=1255.50   sharpe=5.594   mean_slippage=0.0
    win_rate=0.3549        trade_count=107198
    max_drawdown_pct=-0.0332%   vs_baseline_pnl_pct=+704.8%
    is_weighted_bps=0.0472

The base algo's own NOTES.md flags one specific tension: although net P&L
improves vs the `simple` baseline, the implementation-shortfall metric
(`is_weighted_bps`) deteriorates by ~22% (0.0457 -> 0.0472 in the v2 metric;
the notes' historical figure was ~22% worse). The base author's interpretation
was that the flow gate sometimes holds back entries during transient
adverse-flow spikes that would have offered favorable fill prices. That is,
the gate occasionally fires on *noise* rather than *signal*.

**Targeted change**: Add a **gross-volume gate** in front of the existing
absolute net-flow threshold. The flow-direction gate is only allowed to fire
when total in-window trade volume meets a minimum bar (`min_gross_volume`).
Below that floor, the algo behaves like warm-up: submit unconditionally.

Concretely, define `gross_volume = sum(|size|)` over the same 10 s deque used
for `net_flow`. The on_order decision becomes:

    if gross_volume < min_gross_volume:
        submit (gate disabled — too thin to be reliable)
    elif side == BUY  and net_flow <= -flow_threshold:  SKIP
    elif side == SELL and net_flow >= +flow_threshold:  SKIP
    else:
        submit

`flow_threshold` stays at 2.0 contracts (base's proven value).
`min_gross_volume` defaults to **8.0 contracts** — four times the flow
threshold. At the floor, the gate's effective minimum imbalance ratio is
|2|/8 = 25 %, which is meaningfully one-sided rather than coin-flip noise.
Above the floor, the absolute threshold (proven) takes over.

**Mechanism / why it should improve net P&L vs base**: The base gate fires on
any window where `|net_flow| >= 2.0`. In sparse intervals (only 2-4 contracts
have traded in 10 s), a single 2-lot print is enough to flip the gate to
SKIP, even though one print is poor evidence of directional pressure. Many of
these low-volume skips are exactly the "noise skips" the base NOTES flag as
the source of the IS regression: thin tape, the few prints that did happen
randomly leaned one way, the gate skipped, but the next 30 s of price didn't
follow the implied direction. By requiring a minimum gross volume before
gating, we suppress these low-confidence skips while preserving every
high-confidence skip the base algo made (where gross_volume in a 10 s window
was easily >= 8 contracts in active markets). The retained skips should be
the ones with the strongest predictive content (active tape, clear
directional pressure), and the now-submitted formerly-skipped entries should
on average be at least neutral, lifting net P&L and trade count.

**Why not change the absolute threshold instead**: Raising
`flow_threshold` from 2.0 to e.g. 3.0 would also reduce skips, but it would
*uniformly* dampen the gate — including in liquid periods where the absolute
threshold is well calibrated and the existing skip is real signal. The
volume floor only relaxes the gate where evidence is weakest (low gross
volume), keeping the proven behavior intact everywhere else. That is the
more surgical change.

**Expected effect**:
- realized_pnl >= base (target +1-3 % vs base)
- trade_count slightly higher than base (fewer skips on thin tape)
- sharpe roughly flat-to-up (better signal-to-noise on retained skips)
- max_drawdown should not worsen materially (still gating the
  high-confidence adverse-flow cases that drove most of the base's DD reduction)

**Risk**: If "thin-tape, one-sided 2-lot" actually carries real directional
signal (rare but possible if those few prints are themselves large and
aggressive), disabling the gate there will let some adverse entries through
and P&L will fall short of base. The expected magnitude is small because
those cases are inherently low frequency.

**Builds on**: `aggressor-flow-gate` (base). Anti-cascade
(`_position_flat=True` after any skip), reduce-only-orders-always-execute,
and quantity-invariant guarantees are all preserved unchanged.

---

## Implementation Decisions

- **O(1) gross volume maintenance.** Mirror the base algo's running
  `_net_flow` pattern: add a sibling running sum `_gross_volume` that adds
  `|size|` on append and subtracts `|signed_vol|` on prune. Per-order cost
  stays O(1) plus the prune walk (already amortised across ticks). No
  full-deque scan.
- **NO_AGGRESSOR prints contribute 0 to both `_net_flow` and
  `_gross_volume`** — consistent with the base algo's treatment as neutral.
  This means a stream of NO_AGGRESSOR prints will not be enough by itself to
  satisfy the gross-volume gate (correct: those prints carry no directional
  information).
- **Same deque, same window, same prune logic** as the base algo — only the
  `on_order` decision changes. This keeps the delta minimal and the
  comparison clean.
- **`min_gross_volume` default = 8.0 contracts.** Chosen as
  `4 x flow_threshold`. At the floor, the gate requires at least a 25 %
  imbalance to skip, which feels like a reasonable noise/signal cutoff for
  MES futures. The constant is exposed in the config so it can be tuned in
  later loops if the loop-1 result motivates it.
- **No changes to threshold, window, anti-cascade, or reduce-only logic** —
  preserve everything the base proved out.
- **Quantity invariant preserved**: orders are still only skipped or
  submitted whole; `order.quantity` is never touched.

**Look-ahead check**: identical to base. `on_trade_tick` only appends; only
trade ticks with `ts_event <= order.ts_init` are present at decision time
(replay is strictly chronological; the window prune uses `order.ts_init`,
never a future timestamp). The new `_gross_volume` aggregate is derived from
the same deque and therefore inherits the same property.

---

## Backtest Observations

Train window: 12 dates (2026-03-08 to 2026-03-20). Baseline `simple` read
from cache (`--use-cached-baseline`).

**Results — afg-f-l1 vs base algo `aggressor-flow-gate`:**

| metric             | afg-f-l1   | aggressor-flow-gate | delta            |
|--------------------|------------|---------------------|------------------|
| realized_pnl       |   1140.25  |              1255.50|  **-9.18 %**     |
| mean_slippage      |   0.0      |              0.0    |   0.0  (both 0)  |
| sharpe_ratio       |   4.982    |              5.594  |  -0.611          |
| max_drawdown_pct   |  -0.03577% |             -0.03325% | -0.00252 pp    |
| win_rate           |   0.35541  |              0.35488 |  +0.05 pp       |
| trade_count        | 109054     |           107198    |  +1.73 %         |
| is_weighted_bps    |   0.04390  |              0.04724 |  -7.07 %        |

(vs the `simple` baseline the runner reported delta_pnl_pct = +630.93 %, so
the variant still clears the baseline pass-gate margin comfortably; the
relevant comparison for this experiment is vs the base algo above.)

**Hypothesis verdict: NOT SUPPORTED on the headline metric (P&L), partially
supported on the secondary metric (IS).**

- Realized P&L came in 9.18 % BELOW base, the opposite of the +1-3 %
  expectation set out in the hypothesis. Sharpe also fell (-0.61). The
  gross-volume floor did exactly what was intended at the mechanism level
  (more entries: trade_count +1.73 %; gate fired less often) — but the
  entries it added back averaged adverse. So the "thin-tape, 2-lot
  one-sided" skips the base gate was making were, in aggregate, real
  signal, not noise. The premise was wrong.
- IS confirmation: `is_weighted_bps` improved by 7.07 % vs base, and even
  improved vs the simple baseline (`vs_baseline_is_bps` = 12.9 vs the base's
  21.5 — about 40 % better IS). This is consistent with the secondary
  prediction: many of the thin-tape skips the base algo was making
  *would* have had favorable fills. So fill-quality genuinely improved.
  It just didn't translate to net P&L because the price moves in those
  formerly-skipped windows tended to go against the entry direction over
  the oracle's 30 s horizon.
- Drawdown worsened slightly (-0.0025 pp). Win rate effectively unchanged
  (+0.05 pp). Trade count high (109054) — no low-sample-size concern.

**Interpretation.** The base NOTES.md's "thin-tape one-sided prints are
noise" hypothesis is not supported by these numbers. In MES futures at the
horizons in play here, even a small absolute net flow on a thin tape carries
genuine 30 s-horizon directional information — large enough that disabling
the gate there costs more in adverse-entry P&L than it gains in fill-price
quality. The base algo's flat absolute threshold (no volume floor) is, on
this metric pair (P&L vs IS), the better trade-off — the IS regression is
the price you pay for catching those thin-tape adverse moves.

**Direction for loop 2.** The interesting structural finding is the
*decoupling* of IS and P&L: the volume floor improved IS but hurt P&L,
suggesting these two metrics are picking up different things in this signal.
Future loops shouldn't try to fix the IS regression with anything that
removes thin-tape skips — that's now empirically established to cost net
P&L. Better levers to try: (1) **tighten** the absolute threshold further
(2.0 → 1.5) — base's behaviour suggests the gate is currently a touch under-
sensitive on thin tape, perhaps it should fire on even less evidence; (2)
**asymmetric thresholds** for BUY vs SELL — there may be a day-side / book-
side asymmetry in MES that a single threshold can't capture; (3) **flow
acceleration** — instead of (or in addition to) the level of net flow, gate
on its first-difference (recent flow trend vs older flow), which would
respond faster to fresh aggression. Of these, (1) is the cleanest one-knob
test and would be a natural loop-2 candidate.

**Note on metrics.** `mean_slippage` is 0.0 on both sides (zero fill-cost
model), so `vs_base_slippage_pct` is reported as 0.0 and carries no
information this loop.

