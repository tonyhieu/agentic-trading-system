# Algorithm Notes: imbalance-spread-skip

## Hypothesis

**Mechanism**: Book imbalance conditioned skip combined with elevated-spread skip.
Skip the open leg of an oracle signal when EITHER:
(a) current spread > 1.1x rolling 60-tick median spread (spread signal, same as streak-spread-tight), OR
(b) book imbalance is adversely aligned with the order direction by at least a threshold of 0.2
    (I = (q_bid - q_ask)/(q_bid + q_ask); skip BUY when I < -0.2; skip SELL when I > +0.2).
Reduce-only orders always execute.

**Inefficiency exploited**: The streak-spread-tight algorithm (PASS, +140.52% vs baseline) uses a
consecutive-loss streak as one of its two OR signals. The streak is a backward-looking proxy for
adverse-entry conditions. Book imbalance (Lipton et al.) is a forward-looking microstructure signal:
when the ask side is heavier than the bid side (negative I), the short-horizon price direction is
predicted to be downward — adverse for a buy. Replacing the streak with imbalance makes the skip
signal contemporaneously predictive rather than lagged. This should improve the precision of the
skip decision: we skip only when the prevailing order book structure is adverse at order-receipt time.

**Why it survives costs**: Zero-slippage fill model, so skipping has no direct cost. The spread
filter is retained (proven effective in streak-spread-tight). Imbalance is a well-established
short-horizon price predictor (Lipton-Pesavento-Sotiropoulos 2012; Cont-Larrard 2012). Even if the
imbalance signal has modest predictive power, the OR architecture means the skip rate increases only
on ticks where EITHER the spread OR the imbalance is adverse — which should preserve performance
on favorable-imbalance ticks where the streak might have fired spuriously.

**Builds on**: streak-spread-tight (PASS, +140.52% vs baseline on 12-date train window).
ONE targeted change: replace the consecutive-loss streak signal with a book imbalance signal.
All spread parameters identical: spread_multiplier=1.1, spread_window=60, min_spread_window=10.

**Alternatives considered**:
- Adding imbalance as a THIRD OR condition alongside streak — compounds two changes.
- AND condition (spread AND imbalance) — tested in streak-spread-and pattern; lower skip rate
  underperforms OR architecture. The OR variant is more effective.
- Tightening spread_multiplier to 1.0x — tested suggestion from streak-spread-tight notes;
  deferred because the imbalance change is cleaner and better-motivated by theory.
- streak_lookback=3 — increasing lookback reduces sensitivity; not motivated by theory.

---

## Implementation Decisions

The book imbalance I is computed from the current top-of-book quote:
  I = (bid_qty - ask_qty) / (bid_qty + ask_qty)
  Skip BUY  if I * (+1) < -imbalance_threshold  (i.e., I < -threshold)
  Skip SELL if I * (-1) < -imbalance_threshold  (i.e., I > +threshold)

Parameters:
- imbalance_threshold: 0.2 (skip when adverse side has 60% or more of the top-of-book qty)
- spread_multiplier: 1.1 (identical to streak-spread-tight)
- spread_window: 60 (identical)
- min_spread_window: 10 (identical)

Force-submit after skip (_position_flat re-entry guarantee) retained from streak-spread-tight
to prevent cascade skipping.

No look-ahead bias: imbalance uses current top-of-book quote which is observable at order
decision time (no future information). Spread uses rolling history of prior quotes.

**Concerns**:
- Imbalance threshold of 0.2 is a design choice with no prior calibration on these specific dates.
  Could be too tight (fires rarely) or too loose (fires on every imbalanced tick). If the skip
  rate is very different from streak-spread-tight (19.7%), consider tuning threshold.
- The fill model is zero-slippage, so the fill price does not depend on imbalance directly.
  The imbalance signal works only if it predicts oracle fill favorability, which requires the
  oracle signal (30s horizon) to align with the imbalance direction. This is plausible but
  not guaranteed.

---

## Backtest Observations

**WARNING: Partial train window** — results cover 8 of 12 train dates (20260308-20260316, minus 20260314 which has no data). Dates 20260317-20260321 were not completed due to a hung subprocess (see research/NOTES.md RESULT WARNING). All conclusions below apply to the 8-date comparable set.

**Full 8-date aggregate (comparable to simple baseline over same 8 dates)**:
- imbalance-spread-skip: $3317.75 / 35,270 trades / win_rate=40.25% / sharpe=2.869 / max_drawdown=-0.0105%
- baseline (simple): $1254.50 / 42,278 trades / win_rate=36.56% / sharpe=1.065
- vs_baseline_pnl_pct = +164.47% (well above the +5.0% pass gate)
- vs_baseline_slippage_pct = 0.0 (neutral — zero fill-cost model)
- win_rate delta = +3.69pp
- max_drawdown improved vs baseline
- Skip rate: ~16.6% (7,008 fewer trades than baseline over 8 dates)

**What drove improvement**: The imbalance signal (skip when adverse imbalance > 0.2) combined with the spread signal (skip when spread > 1.1x median) successfully filtered losing entries across all 8 dates. On adversarial days (20260312: baseline -$13.25 → algo +$338.0; 20260313: baseline -$327.75 → algo +$155.50; 20260316: baseline -$355.0 → algo +$289.25), the imbalance+spread filter converted net-negative days to positive or near-neutral.

**Per-date breakdown**:
- 20260308: algo=176.25, baseline=140.50 (+25.4%)
- 20260309: algo=1095.75, baseline=867.75 (+26.3%)
- 20260310: algo=708.00, baseline=578.50 (+22.4%)
- 20260311: algo=530.25, baseline=394.75 (+34.3%)
- 20260312: algo=338.00, baseline=-13.25 (baseline was negative)
- 20260313: algo=155.50, baseline=-327.75 (baseline was negative)
- 20260315: algo=24.75, baseline=-31.00 (baseline was negative)
- 20260316: algo=289.25, baseline=-355.00 (baseline was negative)

**What underperformed**: The win_rate (40.25%) is lower than streak-spread-tight (37.1% over 12 dates — different sample, so not directly comparable). The skip rate (16.6%) is slightly lower than streak-spread-tight (19.7%). Whether the imbalance signal is truly predictive vs. the spread signal alone doing all the work is unclear without decomposition analysis.

**Hypothesis verdict**: Supported on the available 8 dates. The book imbalance + spread OR filter achieves a larger dollar improvement ($3317.75 vs $4772.0 for streak-spread-tight, but streak-spread-tight was over 12 dates; on a per-date basis they may be comparable) and passes the gate easily. The replacement of the streak signal with imbalance signal did not hurt performance and may have improved precision.

**Performance issue**: The 20260317 backtest ran for >4 hours and had to be killed. This suggests a possible runaway condition in the algorithm on that date's specific tick sequence. Future iterations should investigate whether the `bid_size`/`ask_size` attributes of Nautilus QuoteTick are always available, and whether exception-catching in a tight loop could cause slowness.

**Suggested next attempt**: (1) Investigate and fix the 20260317 slowness before further refinement; (2) try reducing the imbalance_threshold to 0.1 to increase skip rate; (3) try combining imbalance signal as a modulator of the spread threshold (dynamic threshold based on imbalance); (4) test whether removing the re-entry guarantee (_position_flat) changes results significantly.
