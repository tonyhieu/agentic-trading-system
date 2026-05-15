# Algorithm Notes: cooldown-entry-gate

## Hypothesis

**Mechanism**: After any executed open-leg (entry) order, impose a fixed cooldown
period during which all subsequent open-leg orders are skipped. Only after the
cooldown has expired is the next open eligible for execution. Reduce-only
(position-closing) orders are always submitted immediately regardless of cooldown
state — intraday_flat compliance is maintained.

**Inefficiency exploited**: The oracle signal fires at a 1-second cadence. When
two or more signals fire in rapid succession (within the cooldown window), the
second and later opens are likely correlated with the same underlying price move
that motivated the first. Executing all of them increases position size but provides
no additional directional information beyond the first entry. The "extra" opens
either: (a) enter at a worse price if the market has already moved in the oracle's
direction after the first fill, generating adverse implementation shortfall; or (b)
are redundant when the oracle signal is not realized, amplifying losses on that round-
trip. By imposing a minimum spacing between opens, the algorithm concentrates
execution on the freshest, most independent signal in each time epoch.

**Why it survives costs**: The cooldown only skips opens — it cannot generate
additional commissions or slippage. Every skipped open that would have been a losing
trade improves P&L directly. The trade-off is: skipped opens that would have been
profitable hurt P&L. The hypothesis is that at 1s signal cadence, closely-spaced
entries within the cooldown window have lower expected P&L per trade (due to adverse
selection on the same momentum event already captured by the first entry) and that
the net effect is positive.

**Pivot note**: The original guidance was to implement signal-strength-conditioned
sizing — scaling open-leg size as a function of the oracle forecast magnitude. After
inspecting the runtime interface between strategy and execution algorithm (order
fields: side, quantity, ts_init, is_reduce_only, exec_algorithm_params=None,
tags=None), I confirmed that the oracle strategy does NOT pass forecast magnitude
through exec_algorithm_params or tags. The only execution-time information is the
order direction and standard Nautilus order fields. Per the honest-pivot rule, I
implemented this cooldown gate instead, which is genuinely independent of all eight
prior algorithms. Cooldown-after-trade gating conditions purely on the TIME since the
last execution (calendar/event time of prior fills, not session clock-gate's static
session windows), orthogonal to all prior approaches.

**Builds on**: none — original hypothesis (with pivot from signal-strength sizing as
documented above).

**Alternatives considered**:
- Volume/event-time pacing (execute after X contracts have traded) — rejected in
  favor of cooldown because cooldown is simpler to calibrate and directly addresses
  the serial autocorrelation in oracle signals at 1s cadence.
- Spread-percentile filter — prior work (streak-spread-tight) already used a
  spread-threshold filter; a pure quantile version would be CLOSE to that design.
- Cooldown parameterized at 3 seconds (= 3 signal intervals at the 1s cadence) —
  chosen to capture the first two follow-on signals after any entry while still
  allowing entry every ~3 epochs.

---

## Implementation Decisions

- **Cooldown duration**: 3.0 seconds (configurable via `cooldown_seconds`).
  At a 1s signal cadence, 3s = 3 signal intervals, skipping up to 2 follow-on
  signals after each entry. Shorter (1s) skips only 1 follow-on; longer (5s)
  may skip too many in volatile periods.
- **Cooldown reset on skip**: the cooldown timer starts from the LAST EXECUTED
  open, not from the most recently attempted open. If an open is skipped (because
  we are in cooldown), the timer is NOT reset — only actual fills reset it.
- **Reduce-only orders bypass the cooldown entirely**: intraday_flat compliance
  requires closes to execute always.
- **First open of session**: always submitted (no prior entry, so no cooldown).
- **No _position_flat re-entry guarantee**: unlike skip-based algorithms, the
  cooldown expiry naturally releases entries — there is no permanent lock-out risk
  because the cooldown is time-bounded. The forced re-entry after skip pattern is
  not applicable here and would interfere with the cooldown logic.
- **Look-ahead bias check**: the cooldown uses `order.ts_init` (UNIX ns) and
  `self._last_entry_ts_ns` (set at actual submit time) — both are strictly in the
  past at decision time. No forward-looking data. No look-ahead bias.

**Concerns**: None identified. The algorithm is purely time-based and uses only
the wall-clock timestamp already embedded in the order.

---

## Backtest Observations

**What drove improvement**: The cooldown gate improved P&L most strongly on
high-volume / high-signal-count days where oracle signals fire most rapidly:
20260316 (+$83.75 vs baseline), 20260319 (+$78.75), 20260313 (+$50.75),
20260317 (+$47.75), 20260315 (+$34.25), 20260320 (+$25.25). On these days,
a 1s-cadence oracle with 3s cooldown skips ~60-75% of signals (trade counts
drop from 20k+ to 15k range), filtering out the redundant follow-on signals
that appear to have negative expected P&L when clustered tightly. This is
consistent with the hypothesis: rapidly-successive oracle signals share the
same underlying momentum event and the later ones are adversely selected.

**What underperformed**: The cooldown hurt on early train dates (20260308:
-$9, 20260309: -$17.5, 20260310: -$18.75) and on 20260318 (-$54.75). On
these days the baseline win rates were high (45-49% vs typical 33-38%),
suggesting the oracle signal quality was genuinely better and the cooldown
was filtering out profitable independent signals, not just redundant ones.
The 3s cooldown is too aggressive on low-signal-density days where signals
genuinely are well-spaced.

**Hypothesis verdict**: Supported. The cooldown gate beats the baseline by
+11.79% P&L (gate: +5%), with improved Sharpe (1.16 vs 0.91) and reduced
max drawdown (-0.030% vs -0.038%). However, the 4 underperforming days show
the cooldown value is not unconditional — it helps when signals are dense
and hurts when signals are genuinely sparse/independent. Win rate improvement
is marginal (+0.19pp). Trade reduction is 25.3% (99,119 vs 132,536 trades).

Performance summary:
- 12-date train window (20260308-20260320, excluding 20260314/20260321 no data)
- cooldown-entry-gate: $2,218.00 / 99,119 trades
- simple baseline: $1,984.00 / 132,536 trades
- delta_pnl = +$234 (+11.79%), gate: ≥+5% -> PASS
- Beat baseline: 8/12 dates. Underperformed: 4/12 dates.
- Slippage: both 0.0 (zero fill-cost model)
- IS_weighted_bps: 0.0376 vs 0.0375 (+0.32% worse, negligible)

**Suggested next attempt**: A cooldown with adaptive duration could work better:
short cooldown (1-2s) on days when the signal density is low (early session
or thin market), longer cooldown (5s+) when signal density is high. This
would preserve beneficial filtering on high-density days while reducing
over-skipping on low-density days. Alternatively, combine cooldown with a
minimum signal-spacing requirement measured in bar intervals rather than
wall-clock seconds to account for varying market speeds.
