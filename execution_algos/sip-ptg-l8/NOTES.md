# sip-ptg-l8: PTG + Rolling Win-Rate Gate

## 1. Structural axis
Participation filter / Oracle quality signal.

## 2. Root cause analysis

**Observation from sip-ptg-l7 (FAIL) per-date breakdown:**

| Date       | PnL       | Trades | Win Rate |
|------------|-----------|--------|----------|
| 2026-03-08 | +$109.50  | 373    | 46.1%    |
| 2026-03-09 | +$621.75  | 2975   | 46.2%    |
| 2026-03-10 | +$403.50  | 2386   | 47.8%    |
| 2026-03-11 | +$188.25  | 2537   | 44.2%    |
| 2026-03-12 | -$240.25  | 5714   | 37.8%    |
| 2026-03-13 | -$512.75  | 8548   | 36.3%    |
| 2026-03-15 | -$41.50   | 1922   | 34.3%    |
| 2026-03-16 | -$521.50  | 20783  | 32.9%    |
| 2026-03-17 | -$246.75  | 21490  | 31.9%    |
| 2026-03-18 | +$156.75  | 22219  | 33.9%    |
| 2026-03-19 | +$112.75  | 25245  | 35.3%    |
| 2026-03-20 | +$126.25  | 22542  | 35.8%    |

**Key patterns:**
- Dates 20260308–20260311 show 44–48% win rate → strongly positive PnL
- Dates 20260315–20260317 show 31–34% win rate → large losses (-$810 combined)
- Dates 20260318–20260320 show 33–36% win rate → modest positive (low per-trade alpha)

The oracle's directional accuracy is NOT constant: it varies across intraday
regimes. The hypothesis from sip-ptg-l7 NOTES.md: "explore filters suppressing
entries when oracle's recent accuracy is low."

## 3. Hypothesis

**Claim**: A rolling win-rate gate — tracking the last 20 estimated round-trip
P&Ls and skipping OPENs when rolling win rate < 35% — will reduce participation
during adverse oracle regimes (the mid-week dates where win rates drop to 31–34%)
while preserving full participation in high-accuracy regimes (44–48% win rate).

**Expected mechanism**:
- On good dates (win_rate ≥ 35%): filter never fires → full participation, same
  alpha as base PTG solo-open entries.
- On bad dates (win_rate drops below 35%): filter fires after the rolling window
  accumulates enough evidence (min 10 trades) → trades skipped until regime
  reverts. The re-entry guarantee (`_position_flat`) fires one forced trade per
  skip-streak to allow the win-rate to recover naturally.

**Combined with PTG cap=1**: pair OPENs are already skipped by the PTG gate;
the win-rate gate adds a second layer that also suppresses solo OPENs in bad
regimes.

## 4. Parameters

| Parameter          | Value | Rationale                                       |
|--------------------|-------|-------------------------------------------------|
| position_cap       | 1     | PTG base: serialize entries                     |
| window             | 20    | ~20 seconds of typical activity; fast adaptation|
| win_rate_threshold | 0.35  | Split point: bad dates below 35%, good above    |
| min_window         | 10    | Half-window warmup; avoids premature filtering  |

## 5. Empirical pre-check

**Predicted fire count**: The win-rate gate fires when rolling_win_rate < 0.35
AND n >= 10. On dates with 20000+ trades and 32–33% aggregate win rate
(20260316–20260317), expect heavy engagement. Even on good dates, short
adverse runs will briefly trigger skips.

**Predicted skip rate**: ~20–35% overall (mix of good and bad dates).
- Good dates: ~5% (brief adverse windows)
- Bad dates (20260316–20260317): ~50–70% (sustained low win-rate)

**Stub run PnL delta**: Running sip-ptg-l8 should produce equal-or-better PnL
vs base PTG (position-tier-gate) on 20260308–20260310 (good dates), and
significantly better PnL on 20260316–20260317 (bad dates) by skipping most of
the losing trades.

**N_predicted fires** (≥ 1000/day total across all dates): PASS threshold is
≥ 1000 total skips across 12 dates to ensure the filter is actually engaging.

## 6. How this differs from streak-spread-tight

- `streak-spread-tight` uses last 2 consecutive losses (very short memory, reactive)
  combined with a spread filter. It runs on the `simple` foundation (no PTG cap).
- `sip-ptg-l8` uses a 20-trade rolling win-rate (longer memory, regime-aware)
  on the PTG foundation (cap=1 serialization). It targets regime-level suppression
  rather than single-trade reactive filtering.
- These are complementary, not redundant.

## 7. Backtest observations

(To be filled in after backtest.)

## 8. Verdict

(To be filled in after backtest.)
