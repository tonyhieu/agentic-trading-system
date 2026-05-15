# Algorithm Notes: streak-spread-imbalance

## Hypothesis

**Mechanism**: Three-signal OR conditioned skip. Skip the OPEN leg of an oracle signal
when ANY of three conditions holds:
  (a) current bid-ask spread > 1.1x rolling 60-tick median spread (spread signal),
  (b) both of the last 2 consecutive closed positions had negative estimated PnL (streak signal),
  (c) book imbalance I = (q_bid - q_ask)/(q_bid + q_ask) is adversely aligned with the order
      direction by >= 0.2 (imbalance signal: skip BUY when I < -0.2, skip SELL when I > +0.2).

Reduce-only (close) orders always execute. After any skip, the next open is always
submitted (_position_flat re-entry guarantee, preventing cascade skips).

**Inefficiency exploited**: `streak-spread-tight` (the best full-12-date PASS at +140.52%
vs baseline, Sharpe=2.76) already filters on spread OR streak. However, both signals are
imperfect: spread is a contemporaneous liquidity signal but misses adverse-direction
pressure when spreads are tight; streak is backward-looking and can miss the first few
adverse fills in a new regime. Book imbalance (Lipton et al.) is a short-horizon predictor
of mid-price direction that is uncorrelated with spread or recent loss streak — when the
top of book is heavily skewed against the intended order direction, the fill is likely
adverse even if the spread is normal. Adding imbalance as a third OR leg should filter
additional adverse moments that slip through both existing signals.

**Why it survives costs**: Zero-slippage fill model means there is no execution cost to
skipping. The skip cost is only reduced participation. Since the oracle at sigma=5 has
~33-37% win rate on high-volume days, selectively skipping even a moderate fraction
of additional signals (those that are adverse by imbalance alone but not by spread/streak)
should improve net P&L as long as the imbalance signal is better than random.

**Builds on**: `streak-spread-tight` (PASS, +140.52% vs baseline, Sharpe=2.76, full 12-date
train window, 2026-05-11). ONE targeted change: add book imbalance (threshold=0.2) as a
third OR signal. All spread and streak parameters unchanged: spread_multiplier=1.1,
spread_window=60, min_spread_window=10, streak_lookback=2.

**Alternatives considered**:
- Tighten spread_multiplier to 1.0x (fires on nearly every tick, likely too aggressive)
- Increase streak_lookback to 3 (fewer streak triggers, reduces the streak signal's power)
- AND of all three (too restrictive, AND already shown to underperform OR in streak-spread-and)
- Imbalance threshold tuning to 0.1 (too sensitive, likely filters too many neutral signals)

---

## Implementation Decisions

Extends `streak-spread-tight` by adding `_imbalance_triggered()` from `imbalance-spread-skip`.
The combined skip condition is: `spread_skip OR streak_skip OR imbalance_skip`.

Parameters: imbalance_threshold=0.2 (same as imbalance-spread-skip), all streak/spread
parameters unchanged from streak-spread-tight.

The _position_flat re-entry guarantee is retained: after any skip (regardless of which
signal triggered), the very next OPEN order is always submitted.

**Concerns**:
- Adding a third OR signal will increase skip rate. If the imbalance signal triggers
  on many of the same adverse moments already caught by spread/streak, the incremental
  benefit is small. If it fires on additional moments, benefit may be larger.
- Look-ahead bias risk: book imbalance uses current top-of-book quote, which is observable
  at order decision time (the order arrives, we read the current quote). No forward-looking
  information is used. This is the same pattern as imbalance-spread-skip which passed
  review.
- The imbalance signal is signed and directional (adverse direction relative to the order
  side). This is more precise than the spread signal (which is unsigned) and may improve
  skip precision.

---

## Backtest Observations

**Full 12-date aggregate** (20260308-20260320, same dates as streak-spread-tight):
- streak-spread-imbalance: $5,841.75 / 98,914 trades / sharpe=3.50 / win_rate=38.0% / MaxDD=-0.81%
- baseline (simple): $1,984.00 / 132,536 trades / sharpe=0.91 / MaxDD=-3.77%
- vs_baseline_pnl_pct = +194.44% (well above the +5.0% pass gate)
- vs_baseline_slippage_pct = 0.0 (neutral — zero fill-cost model)
- Skip rate: ~25.4% (33,622 fewer trades than baseline)

**Comparison vs streak-spread-tight (best prior PASS on same 12 dates)**:
- P&L: $5,841.75 vs $4,772.00 (+22.4% improvement)
- Sharpe: 3.50 vs 2.76 (+0.74)
- Max drawdown: -0.81% vs -1.41% (improved by +0.60pp)
- Win rate: 38.0% vs 37.1% (+0.9pp)
- Trade count: 98,914 vs 106,428 (fewer trades = higher skip rate with imbalance signal)

**What drove improvement**: Adding book imbalance as a third OR signal caught additional
adverse entry moments that slipped through the spread-only and streak-only signals. The
extra skip rate (~5.5pp more skips than streak-spread-tight, from 19.7% to ~25.4%)
came with a net P&L gain, meaning the additional skips were net positive (the imbalance
signal successfully identified adversely-aligned entries). Key contributors:
- 20260319: $896.25 (vs baseline $284.75) — imbalance signal particularly effective on high-volume day
- 20260318: $606.25 (vs baseline $272.25) — strong improvement
- 20260320: $737.25 (vs baseline $306.75) — strong improvement

**What underperformed**: The is_weighted_bps increased relative to baseline (14.42 bps
adverse vs baseline), which is worse for the trader by the IS metric. However, since
the backtest fill model is zero-slippage, this metric mainly reflects that we're filling
at slightly worse average arrival prices due to selective timing. The P&L improvement
dominates.

**Hypothesis verdict**: Supported. Adding book imbalance as a third OR signal improved
P&L by +22.4% vs streak-spread-tight, consistent improvement in Sharpe (+0.74) and
drawdown reduction (-0.60pp). The imbalance signal has independent filtering power
beyond spread and streak combined.

**Suggested next attempt**: (1) Tighten imbalance_threshold from 0.2 to 0.1 (more
aggressive imbalance filtering — may help on high-volume days); (2) Combine all three
signals with different weights (continuous score rather than hard OR); (3) Test with
a time-of-day gate (first/last 15 minutes of session often have highest adverse
selection — gate the imbalance signal to those windows only). The most targeted
change would be to tune the imbalance_threshold.
