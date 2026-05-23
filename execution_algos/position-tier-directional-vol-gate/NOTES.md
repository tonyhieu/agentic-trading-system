# Algorithm Notes: position-tier-directional-vol-gate

## Hypothesis

**Mechanism**: Asymmetric (directional) vol-regime gate stacked on iter-2's position_cap=1 + EMA-imbalance + reduce-only fast-path. During a high short-window realized-vol burst (current_short_vol > vol_multiplier * baseline_median), block ONLY the orders whose direction is adverse to the simultaneous short-window mid trend: skip BUY when mid is falling, skip SELL when mid is rising; admit same-direction or neutral-trend bursts. Short-vol uses iter-5's O(1) running-sum/sum-of-squares stdev over a 60-tick log-return deque; baseline uses iter-5's sampled deque of length 300; trend uses a bounded deque of the last 20 mids with a 0.25-point eps deadzone for sign(mid_now - mid_20_back).

**Inefficiency exploited**: The oracle's 30 s forecast horizon degrades during vol bursts (iter-5's premise), but iter-5's symmetric gate threw away both the BUYs into upward bursts and the SELLs into downward bursts — exactly the cases where the oracle's directional bet is most likely to remain correct (the burst is in the trade's favour). Iter-5's vs-iter2 reading showed almost zero marginal lift (-2.8% pnl, -0.12 Sharpe), and the iter-5 NOTES.md explicitly recommended an asymmetric directional vol gate as the next structural test. This iteration takes that recommendation.

**Why it survives costs**: Slippage is identically 0 under the current fill model (research/NOTES.md 2026-04-30), so any pnl lift carries through to the gate without commission/slippage drag. The directional gate should skip a strict subset of iter-5's skips (only the adverse-direction half of high-vol bursts), so it admits more trades than iter-5 — those extra trades are precisely the favourable-direction high-vol entries, expected to be net positive in pnl on average. If the trend signal is noise within these bursts the algorithm collapses gracefully to "skip random half" and pnl moves toward iter-5's number; if the trend signal is informative within bursts the algorithm beats iter-5.

**Builds on**: `position-tier-vol-regime-gate` (iter-5) — replaces the symmetric high-vol skip with a directional (side x mid-trend) high-vol skip. All other gates and parameters inherited verbatim from iter-5 (which in turn inherited from iter-2 best `position-tier-imbalance-ema-gate`). Per OBJECTIVE.md §6 this is ONE targeted structural change vs the prior algorithm; the inherited gates are unchanged so attribution stays clean.

**Alternatives considered**:
- Time-of-day filter (skip open/close windows). Reserved for next iteration if directional vol fails — distinct structural axis.
- Reduce-only delayed execution. Would interact with intraday_flat in non-trivial ways; deferred.
- Dropping the EMA-imbalance gate and using only the directional vol gate. Rejected for this iteration: would compound two changes (axis + removal), destroying attribution per §6.
- Asymmetric thresholds (vol_multiplier_long != vol_multiplier_short). Adds a second tunable axis without theoretical basis on this train window; deferred.
- Using OFI sign as the direction instead of mid trend. Iter-3 showed OFI is structurally weaker than imbalance in this gate stack; would conflate two effects.

---

## Implementation Decisions

- **Mid-trend definition**: sign(mid_now - mid_at_(now - 20_ticks)) with abs eps deadzone of 0.25 points. The deadzone prevents tick-by-tick rounding from flipping the trend signal in flat regimes — sign-flip noise would let the gate fire arbitrarily on no real direction. 0.25 points at MES ~5000 ≈ 0.5 bps; small enough to register a real burst (which by definition moves mid more than this in 20 ticks), large enough to ignore noise.
- **Trend window of 20 ticks vs vol window of 60 ticks**: trend is meant to capture the direction of the CURRENT vol burst, not the whole vol-window history. A burst that started recently will have already moved the mid by the time the gate fires; 20 ticks is short enough to be inside one burst.
- **Neutral-trend high-vol case admitted (not skipped)**: this is intentional — when vol is high but direction is unresolved, iter-5 would skip; we admit. Symmetric expected value reasoning: with no directional information, expected pnl of admitting is unchanged from baseline, while iter-5 throws away half the favourable cases.
- **No look-ahead**: both vol and trend reads come from quote ticks the engine has already dispatched. `on_quote_tick` appends in chronological order; `on_order` reads `_vol_history[-1]` and `_mid_history` endpoints after those appends.
- **Thin-book guard inherited**: total < min_total_size ticks neither update EMA nor mid_history nor vol — same as iter-5. Avoids tape-bid/ask flicker around session edges.
- **Statistics.median in `_vol_regime_is_adverse_directional`**: called only on actual order events (not per tick), so O(N log N) over baseline_window=300 is bounded.
- **`subscribe_quote_ticks` hazard**: per research/NOTES.md 2026-05-23, any algo in this family OOMs on 2026-03-19 inside Nautilus. This algo also subscribes to quotes -> expect the same crash; aggregate over 11 of 12 train dates.

**Concerns**:
- The mid_trend_eps and mid_trend_window were chosen by reasoning, not tuned on the training set. They are plausible defaults; an explicit grid would be a separate iteration. Treat the result as informational about the AXIS, not the OPTIMUM parameters on that axis.
- Trend-as-sign-of-difference is a coarse direction signal. A regression-based slope or volume-weighted trend would be more informative but adds parameters and complexity beyond what one targeted iteration should change.
- The directional gate is a strict subset of the symmetric gate in terms of skips, so trade count is expected to RISE vs iter-5 (closer to iter-2's 62220). If pnl falls vs iter-5 anyway, the trend signal is anti-informative within bursts and the AXIS should not be revisited.
- Overfitting risk is low at the algorithm-shape level (the change is theoretically motivated: symmetric -> asymmetric on a vol burst with an obvious direction). Overfitting risk on the eps/window params is moderate and acknowledged.

---

## Backtest Observations

**Aggregated across 11 of 12 configured train dates** (20260308-20260318, 20260320). 2026-03-19 EXCLUDED — reproduces the documented `subscribe_quote_ticks` Rust/Nautilus 8 GiB OOM (research/NOTES.md 2026-05-23) on this algo too, exactly as expected for any algo in this family. The cached `simple` baseline for 20260319 (pnl=112.75, trades=25245) is also dropped from the algo aggregate for like-for-like comparison.

**Headline numbers (11 dates, vs baseline `simple` on the same 11 dates):**
- position-tier-directional-vol-gate: realized_pnl=$4491.75 / 61886 trades / sharpe=21.08 / win_rate=39.34% / max_drawdown=-1.21%
- simple (cached, same 11 dates): realized_pnl=$43.25 / 111489 trades / win_rate=35.02%
- delta_pnl_pct = +10285.55% (far above the +5.0% gate)
- vs_baseline_slippage_pct = 0.0% (zero-cost fill model — research/NOTES.md 2026-04-30)

**Refinement-axis reading vs iter-5 `position-tier-vol-regime-gate`** (the parent — this iteration is iter-5's recommended asymmetric/directional version):
- pnl: $4491.75 vs $4377.00 = **+2.62%** (meets `min_pnl_delta_pct = +2.0` refinement target)
- sharpe: 21.08 vs 20.67 = +0.41 (below `min_sharpe_delta = +0.5` target, but positive and ~at noise floor of cross-day annualized Sharpe on N=11)
- win_rate: 39.34% vs 39.36% = -0.02pp (effectively unchanged; refinement target +2.0pp MISSED)
- trade_count: 61886 vs 59258 = +4.4% (as predicted — directional gate is a strict subset of iter-5's skips, admitting +2628 entries net)
- max_drawdown: -1.21% vs -1.22% = +0.01pp (effectively unchanged; refinement target -1.0pp MISSED)

**Refinement-axis reading vs iter-2 `position-tier-imbalance-ema-gate`** (the family-best on this train window):
- pnl: $4491.75 vs $4503.25 = **-0.26%** (effectively flat; refinement target +2.0pp MISSED)
- sharpe: 21.08 vs 20.79 = +0.29 (positive but below +0.5 target)
- win_rate: 39.34% vs 39.29% = +0.05pp (flat)
- trade_count: 61886 vs 62220 = -0.54% (essentially identical)
- max_drawdown: -1.21% vs -1.21% (identical)

**What drove improvement (vs iter-5)**: Admitting the same-direction high-vol bursts (BUY into rising mid; SELL into falling mid) recovered ~2.6% of pnl that iter-5's symmetric gate threw away. The +4.4% trade-count increase matches the +2628 entries this iteration admits that iter-5 did not, with average pnl per admitted entry positive enough to lift aggregate pnl. The directional hypothesis is qualitatively correct: within a vol burst, the trades aligned with the burst direction are not systematically worse than the regime baseline.

**What underperformed (vs iter-2)**: The directional vol-regime gate essentially collapses back to iter-2's stack: removing the symmetric vol filter while gaining the directional vol filter is a wash within the position_cap=1 + EMA-imbalance pipeline. The marginal directional information at this train window is not large enough to outperform iter-2; it brings the algorithm back to roughly iter-2's number from iter-5's regression. Pnl is within $11.50 of iter-2 (0.26% on $4500), well inside cross-iteration noise on N=11 dates.

**Hypothesis verdict**: PARTIALLY SUPPORTED. The directional vol gate does what was hypothesized — it preferentially blocks adverse-direction bursts and admits favourable-direction bursts (evidenced by the +2.62% pnl lift vs iter-5). But the structural takeaway from iter-3/iter-4/iter-5 stands: within the position_cap=1 + EMA-imbalance + reduce-only stack, no additional vol-axis gate (symmetric or directional) meaningfully beats iter-2. The marginal directional information in vol bursts is real but small at this train window. Per OBJECTIVE.md §6, this PASSES the canonical baseline gate decisively, and is logged as a PARALLEL passing algorithm. Do NOT snapshot as family-best — iter-2 retains the family-best designation on the train window. Snapshot decision: NOT taken this iteration per the task instructions ("Do NOT push, open PR, or snapshot").

**Honesty: cross-day Sharpe interpretation.** Sharpe 21.08 on N=11 carries the same caveats as iter-2/iter-5: cross-day daily Sharpe annualized from a small sample with high standard error (~0.4 units per OBJECTIVE.md §8). Treat the +0.29 / +0.41 deltas as informational, not as primary evidence.

**Suggested next attempt**: The family-internal gradient on gate-axis tweaks is exhausted (iters 2-6 cluster around pnl $4377-4503 on this train window, a $126 / 2.9% spread). Two structurally distinct mechanisms remain unexplored: (a) **time-of-day filter** — skip OPEN-leg orders in the first/last K minutes of the session, where micro-structure regime is qualitatively different (open auction unwind, end-of-day intraday-flat scramble); (b) **conditional partial reduce-only ladder** — when in position, place an additional reduce-only limit order ahead of the natural close to capture mean-reversion within the 30s oracle horizon. (a) is one-line implementation cost; (b) is a more meaningful execution-algorithm restructure. (a) is the higher-leverage cheap test for the next iteration.

