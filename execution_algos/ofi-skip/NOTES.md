# Algorithm Notes: ofi-skip

## Hypothesis

**Mechanism**: At order submission time, compute a rolling EMA of the Order
Flow Imbalance (OFI) from recent quote ticks. OFI measures the directional
pressure in the order book as a FLOW quantity (change in bid depth minus change
in ask depth), rather than a static snapshot. Skip an open order when the EMA
of OFI is adverse to the order direction beyond a threshold. Reduce-only orders
always execute (intraday_flat compliance).

OFI at each quote tick is defined as:

    OFI_t = (bid_qty_t - bid_qty_{t-1}) - (ask_qty_t - ask_qty_{t-1})

Positive OFI: bids expanding (or asks contracting) — buying flow dominant.
Negative OFI: asks expanding (or bids contracting) — selling flow dominant.

Skip condition:
- BUY order: skip if EMA(OFI) < -ofi_skip_threshold (adverse selling flow)
- SELL order: skip if EMA(OFI) > +ofi_skip_threshold (adverse buying flow)

**Inefficiency exploited**: Prior skip approaches used STATIC book state
(snapshot imbalance, snapshot spread). Kolm et al. (2023) showed that
STATIONARY order-flow inputs — changes in book depth, not levels — are
stronger short-horizon price predictors than raw LOB states. Static imbalance
measures the current book state; OFI measures the directional PRESSURE changing
the book state. A BUY oracle signal that arrives during sustained selling flow
(bids shrinking, asks expanding) is entering into adverse execution conditions
even if the current snapshot imbalance looks neutral.

MESM6's near-constant 1-tick spread (identified in prior iterations) limits
spread-based filters. OFI is a FLOW quantity that is non-trivially variable even
when spread is constant — the quantities at the top of book fluctuate actively.
This orthogonality to spread is the key theoretical advantage over prior approaches.

**Why it survives costs**: With sigma=5 oracle (~48% win rate), any skip that
selectively removes losing trades improves P&L. The zero-slippage fill model
means only P&L direction matters. OFI has empirical support (Kolm et al. 2023,
BookImbalance__Lipton in the literature) as a 2-price-change horizon predictor.
If OFI predicts short-term adverse moves, skipping during adverse OFI removes
trades that would lose money AND avoids committing capital to trades the oracle
was already wrong about.

**Builds on**: imbalance-skip (prior iteration — tried STATIC book imbalance,
failed because MESM6 book is near-constant and the signal lacked discriminating
power). OFI-skip uses FLOW rather than levels — a fundamentally different signal
motivated by Kolm et al.'s finding that stationarized flow features beat raw
book state features.

**Alternatives considered**:
- Time-of-session filter: Skipping at session open/close edges. Not tried yet,
  but MESM6 Globex runs nearly 24h which makes session-edge detection complex.
  OFI-skip is simpler and better motivated by literature.
- Loss-streak filter: Track oracle win/loss and skip when on losing streak.
  Requires tracking position PnL in real-time (complex implementation) and has
  no look-behind horizon advantage over OFI.
- Lower-threshold spread filter: Prior iterations showed MESM6 has near-constant
  1-tick spread; lowering threshold (spread-momentum-skip) caused 0% fire rate.
  OFI bypasses the spread-ceiling entirely.
- Directional OFI sign (binary): Using just sign(OFI) rather than an EMA
  threshold would fire on every tick with non-zero flow. An EMA smooths noise.

---

## Implementation Decisions

**EMA alpha = 2/(N+1) with N=20**: A 20-tick EMA balances responsiveness to
recent flow changes against noise reduction. Quote ticks arrive at variable
intervals; a 20-tick window covers roughly 5-20 seconds at typical MESM6 quote
rates, capturing the ~2-price-changes horizon that Kolm et al. found effective.

**ofi_skip_threshold = 0.5**: The OFI per tick is the change in bid qty minus
change in ask qty, in contract lots. For MES (minimum qty of 1 lot), typical
|OFI| per tick is 1-3 lots. An EMA threshold of 0.5 fires when recent net flow
is adverse by about half a lot on average — covers moderate-to-strong adverse
flow. This is a tunable parameter; 0.5 is a reasonable starting point.

**min_quotes_warmup = 5**: Wait for 5 quote ticks before activating the OFI
filter. This allows the EMA to initialize from more than 1 data point. Orders
arriving before the warmup period submit immediately (conservative fallback).

**OFI computation**: Uses the top-of-book bid_size and ask_size from quote ticks.
OFI_t = (bid_size_t - bid_size_{t-1}) - (ask_size_t - ask_size_{t-1}).
The first quote tick initializes prev_bid_size and prev_ask_size; OFI is 0.0
for the very first tick (no meaningful delta to compute).

**EMA update**: ema_ofi = alpha * ofi_t + (1 - alpha) * ema_ofi. Updated in
on_quote_tick() — not in on_order() — to avoid any look-ahead bias. The EMA
only uses data available at the time on_order() fires.

**Concerns**:
- Look-ahead bias check: on_order() reads self._ema_ofi which is updated
  only from past quote ticks (on_quote_tick callback). The OFI EMA is strictly
  causal. No look-ahead.
- The quantity invariant is preserved: skipped orders result in
  sum(child_fills) < parent.quantity, which is explicitly allowed.
- Reduce-only orders always submit — intraday_flat compliance is preserved.
- Cold-start: if on_order fires before any quote tick, submit immediately
  (len(self._prev_bid) == 0 fallback).
- MESM6 minimum quantity is 1 lot, so OFI values are integers. The EMA is
  a float, so threshold of 0.5 is between whole-lot increments.

---

## Backtest Observations

**What drove improvement**: OFI-based skipping fired on 60 trades total across
3 train dates (4 / 31 / 25 on 20260308 / 20260309 / 20260310), a ~1.1% skip
rate. On 20260309 (the largest session, 2863 baseline trades), skipping 31 OFI-
adverse trades improved PnL by +$18 (+2.07%). The OFI EMA signal correctly
identified adverse-flow trades on the busiest day, modestly outperforming
static-imbalance (which fired on ~35 trades total at 0.5 threshold).

**What underperformed**: On 20260310, skipping 25 trades HURT PnL by $3.50
(-0.61%) — those skipped trades would have been winners. On 20260308 (Sunday
overnight session, only 351 baseline trades), the filter fired 4 times for
+$0.75. Aggregate delta: +$15.25 / +0.96% — well below the 5.0% gate.

Root cause: The fundamental problem persists — MESM6 with sigma=5 generates
oracle signals with ~48-49% win rate. The OFI signal (flow-based, not static)
provides slightly better discrimination than prior approaches but still cannot
reliably identify the ~52% losing trades because:
(a) The OFI values are dominated by integer-lot changes (1-2 lots per tick)
    and the EMA threshold of 0.5 only catches when net flow is persistently
    adverse across 20 ticks — which is rarer than individual tick events.
(b) The zero-slippage fill model means even adversely-timed executions cost
    nothing extra in market-impact, so OFI only helps when it predicts
    DIRECTIONAL price movement over the 30s oracle horizon — a harder task.
(c) With only 60 skipped trades out of 5522, the effect on aggregate PnL is
    inherently bounded below 2% unless the skipped trades have extreme P&L
    concentration.

**Hypothesis verdict**: PARTIALLY SUPPORTED. OFI is a superior signal to
static imbalance (0.96% vs 0.10% delta) and the directional improvement on
20260309 (+2.07%) provides some support for the Kolm et al. finding that flow
features beat levels. But the discriminating power is insufficient at sigma=5.

**Suggested next attempt**: The research consistently shows that skip-based
approaches top out at +2-4% against a sigma=5 oracle because they cannot identify
enough losing trades without also removing winners. A fundamentally different
architecture is needed. Based on the prior research dead-ends (microstructure
signals, oracle-direction signals, spread signals, OFI):

(1) DIRECTIONAL MOMENTUM EXECUTION: Instead of skipping orders, adjust which
    SIDE of the spread to use. If the oracle says BUY but recent momentum is
    strongly upward (price already moved), submit at a limit price slightly
    below ask (inside spread) to get a better fill — or skip if no fill comes.
    This changes the execution price rather than the skip decision, but the
    zero-slippage fill model may make this moot.

(2) REDUCE-ONLY ORDER OPTIMIZATION: The simple baseline closes positions
    immediately. A smarter closing strategy — waiting N ticks for a favorable
    close price — could improve the close leg. For a LONG position, if mid-price
    rises in the next 1-2 seconds, the close at that higher bid would be better.
    This improves realized PnL without changing open-order selection.
    RISK: With intraday_flat, holding a close too long could trap the algo.

(3) ABANDON SIGMA=5 ANGLE: The fundamental research constraint — all signals
    (microstructure, momentum, flow, consensus, spread) produce +0-2% against
    a ~48% win-rate oracle — suggests the human operator should verify whether
    sigma=5 is the intended research setting or a misconfiguration. A human note
    flagging this was written in research/NOTES.md.

**Status**: FAIL — aggregated over 3 train dates (20260308, 20260309, 20260310):
ofi-skip $1602.00 / 5462 trades vs simple $1586.75 / 5522 trades;
delta_pnl = +0.96%, below both the 5.0% gate and the 3.0% CLOSE threshold.
Slippage: 0.0 for both (zero-slippage fill model). Mean Sharpe: ofi-skip
100.84, simple 99.78. The OFI filter skipped 60 trades (1.1% skip rate), a
slightly higher fire rate than imbalance-skip (~35 trades, ~1.5%) but lower
than spread-relative-skip (~85 trades, ~1.8%).
