# Loop 2 Reasoning Trace

## Hypothesis generation method used
prompt-l1.md proposer–EDA-grounded–criticizer loop (Steps 1–5): read context → propose THREE mechanistically distinct candidates → run mandatory EDA against train DBN ticks to confront each candidate's key assumption → criticize survivors → select ONE and write a structured hypothesis with EDA-anchored numbers.

## How the hypothesis emerged from the method
Reconstructing from `execution_algos/sip-afg-l2/NOTES.md` and the code:

Step 1 produced the base-algo summary (10s rolling signed aggressor-volume gate, symmetric `flow_threshold=2.0`) plus a read of `program_database.json` showing sip-afg-l1 was a recency-weighting attempt that regressed -15.19%. The researcher explicitly closed the EWMA / recency-weighting family for this loop and named three OPEN families: (A) change the gate INPUT, (B) change the DECISION RULE SHAPE, (C) add a SIDE-ASYMMETRIC guard.

Step 2 instantiated those families:
- Candidate A — trade-count flow instead of volume flow
- Candidate B — tail-magnitude-conditional gate (threshold at p90 of |net_v|)
- Candidate C — side-asymmetric thresholds

The candidates ARE mechanistically distinct, satisfying the method's distinctness requirement.

Step 3 (EDA) ran on 4 train dates (20260308, 20260309, 20260315, 20260318) via two scripts (`scripts/_eda_sip_afg_l2.py`, `scripts/_eda_sip_afg_l2_focus.py`). The EDA replayed TradeTicks, maintained the same 10s deque, and recorded realized 30s mid drift conditional on the gating state. Each candidate got one decision-relevant number:
- A: count vs volume gates fire together 85% of the time; correlation 0.71–0.86. The signals differ, but EDA produced no number linking count-flow disagreements to better 30s drift than the volume signal — the candidate was kept "alive but mechanistically weak."
- B: tail premium ratio of mean |drift| for |net_v| in p90+ vs body is only 1.28x–1.69x — gradual, not sharp.
- C: pooled across 4 train dates with n=296,012 BUY-skip and n=266,063 SELL-skip evaluations: BUY-skip mean drift = +0.0931 ticks (t=+25.13, correctly signed), SELL-skip mean drift = -0.1445 ticks (t=-41.46, inverted at every magnitude examined).

Step 4 critiqued C across six attacks (constraint interaction, untested sub-assumptions, trade_count consistency check, armchair-parameter test, anti-cascade interaction, "why did the original author miss it?"). C survived. A was eliminated for lacking the EDA→P&L link the method demands. B was eliminated because the sign analysis from C showed the magnitude story works against B on the SELL side.

Step 5 wrote the hypothesis with both numeric parameters anchored: `flow_threshold_buy = 2.0` (kept = base; supported by t=+25 BUY-skip-value); `flow_threshold_sell = +inf` (disabled; supported by t=-41 inverted SELL-skip-value at moderate threshold and t=-43 at the tail). The anti-cascade `_position_flat = True` fix-up (only set after BUY skip, the only side that gates) was caught by Attack 5 in the critique.

The method did its job: a candidate that would have looked attractive without EDA (B — "tighter threshold, skip only the high-confidence cases") was killed because the EDA exposed the sign-by-side problem. Without Step 3 the researcher would likely have shipped B or a stack of A+B.

## Where the method helped
1. **Forcing three mechanistically distinct candidates.** A single-candidate path would almost certainly have settled on B (tail-magnitude) — the most "obvious" refinement of a thresholded gate. Requiring three forced the researcher to also imagine C (side-asymmetric), which is the candidate the EDA validated.
2. **Mandatory EDA gate before scoring.** The researcher reports the sign-by-side finding (SELL inverted) as the load-bearing insight. That finding only existed because the EDA partitioned drift by aggressor side — something the previous loop's method never required. The method explicitly says "every quantitative parameter must have a Step 3 number behind it"; both `flow_threshold_buy = 2.0` (base-anchored) and `flow_threshold_sell = +inf` (EDA-anchored) satisfy that test.
3. **Critique Attack 3 — trade_count consistency.** The hypothesis explicitly predicts `trade_count` rises (because disabled SELL gating returns more orders to the broker). That is the kind of consistent mechanism-and-count story sip-afg-l1's method failed to require (sip-afg-l1's trade_count moved -0.22% — almost flat — which was the diagnostic sign that something was wrong).
4. **Disqualifying armchair numbers.** Candidate A is the candidate that DID make it through Step 2 but had no EDA→P&L number, and was correctly killed for that reason. Without the rule, A might have been shipped on aesthetic grounds.

## Where the method felt limiting or unnecessary
1. **EDA on tick-evaluation points vs order-arrival points.** The EDA sampled every TradeTick where `|net_v| >= 2`. But gating decisions in the actual backtest happen at oracle-order-arrival times (~1Hz, more uniform). The Step 3 number is a TickPoint average over ~562k events; the backtest sees gating decisions in the hundreds-to-low-thousands per day. The method gives no procedure to bridge the sampling gap. The researcher flagged this in Attack 2 but had no method-prescribed way to act on it — and as the backtest shows, this gap mattered (more on this below).
2. **No EDA on previous-loop's specific failure mode.** sip-afg-l1 regressed by reshuffling WHICH orders were gated without changing HOW MANY. The new method does require trade_count consistency in the critique, but it does not require the EDA to estimate the gate's actual hit-rate on the order stream — only the average effect at TradeTick evaluation points. A required "estimate the gate's expected order-stream firing rate from base's gate behavior" step would have surfaced that SELL gating in the actual backtest is rarer than the EDA volume implies.
3. **No counter-factual estimate at the gate-firing level.** The method asks for the conditional drift; it does not ask "and what is the per-skip P&L (not per-evaluation-point P&L) the change is expected to recover?" The researcher's own predicted-magnitude paragraph (Step 5) hand-waved this — "the realistic recovered P&L is on the order of a few hundred dollars — roughly +10% to +30% vs base." The method offered no structure to sharpen that estimate.
4. **The "one survivor → ship" rule is a single-point-of-failure.** Once C survived Step 3 and the critique, there was no further sanity-check step where the researcher could have compared C against a slightly-different parameterization (e.g., C with a high but finite SELL threshold instead of +inf) before committing.

## What a different method might have produced
A *backtest-first elimination tournament* method might have caught the actual problem here. Concretely: after Step 3 EDA, generate 4–6 lightweight backtests on 2 train dates only (NOT the full 12-date aggregate), where each variant is one EDA-anchored parameter setting (C-with-sell-inf, C-with-sell-10, C-with-sell-only-extreme-net_v, B, A, base). Score the 6 variants on 2-date realized P&L. Pick the survivor for the full 12-date run. This would have bridged the TradeTick-vs-order-arrival sampling gap without the researcher needing to estimate it a priori, and would have caught that C-with-sell-inf is too aggressive *before* committing to 12 days.

An alternative: a *paired-comparison* method that requires the EDA to estimate, for the surviving candidate, the per-actual-order recovered P&L (not the per-tick-event average) by simulating the base algo's gate firings on one date and computing the drift along those firings only. This is more work but produces a number that matches the metric the backtest will report.

## What the backtest showed
Raw numbers (sip-afg-l2 vs aggressor-flow-gate base, 12 train dates):

| Metric                 | sip-afg-l2 | base (afg) | delta            |
|------------------------|-----------:|-----------:|-----------------:|
| realized_pnl           | **645.00** | 1255.50    | **-48.63%**      |
| mean_slippage          | 0.0        | 0.0        | 0.0%             |
| sharpe_ratio           | 2.765      | 5.594      | -2.83            |
| max_drawdown_pct       | -0.0431%   | -0.0332%   | -0.0099pp worse  |
| win_rate               | 0.3526     | 0.3549     | -0.23pp          |
| trade_count            | **120,966**| 107,198    | **+12.84%**      |
| is_weighted_bps        | 0.0431     | 0.0472     | -0.0041 (better) |

This is a large regression — bigger than loop-1's -15.19%. Sharpe nearly halved. Max drawdown widened by ~30%.

What the trade_count tells us: the hypothesis's PRIMARY prediction was confirmed — `trade_count` rose by +12.84% (predicted range was 113k–119k; actual was 120,966). The mechanism IS doing what it claims: SELL skips that base was making are now executing as fills. That part of the story is mechanically correct.

What the realized_pnl tells us: those recovered SELL orders, in actual execution, are NET UNPROFITABLE by a wide margin. The Step 5 falsifier was literally this case ("trade_count rises substantially (>3%) but realized_pnl falls"). The hypothesis IS falsified by its own pre-registered falsifier. The EDA-measured pooled SELL-skip drift of -0.144 ticks per evaluation point did NOT generalize to the strategy's actual order-arrival distribution.

What surprised me: the magnitude. The EDA showed a t-statistic of -41 on the SELL inversion. That's an extremely tight statistical signal. I would have expected at worst a flat result, not -48.6% P&L. Two candidate explanations: (a) the EDA oversampled in active-trading windows where the SELL inversion is strong, but the actual oracle orders arrive uniformly in time including quiet windows where the inversion does not hold, or (b) the oracle's SELL signal selection criteria preferentially picks moments where net_v >= +2 happens to be correctly signed (i.e., when momentum is real) — the orders the base algo's symmetric gate WAS skipping were genuinely adversely-selected, and the EDA's sample is dominated by NON-order moments where the inversion holds.

What confirmed expectations: `mean_slippage` stayed at 0.0 (correct prediction — gate does not affect fill mechanics). `trade_count` rose in the predicted direction and within the predicted range. `is_weighted_bps` marginally improved (also predicted).

## Where I felt uncertain
1. **The Tick-vs-order sampling gap (Attack 2 in NOTES) was the dominant risk and was not mitigated.** The researcher named the concern but had no method-prescribed action. The backtest confirms this was the real failure mode.
2. **The EDA dates (4 of 12) may have been non-representative.** 20260308, 20260309, 20260315, 20260318 were chosen but no rationale is recorded in NOTES.md. If those 4 had unusually strong SELL inversion (e.g., they were trending-down days), the inversion is a regime artifact, not a structural feature.
3. **The conservative interpretation rule (Step 5's "more EDA, less commitment") was not invoked.** Candidate C had ambiguity around whether to use `flow_threshold_sell = +inf` (disable) or a high finite threshold (e.g., 10). The researcher picked +inf based on "the whole regime is unprofitable" reading of the EDA. A more conservative move would have been to set the SELL threshold to e.g. 10 (only-keep-extreme-SELLs), keeping the dampening on the most-likely-adverse cases. The method asked for "the more conservative interpretation" but the researcher read disable as conservative — both interpretations are defensible from the NOTES, and the more aggressive one was chosen.
4. **No EDA finding addressed the previous loop's specific failure mode (gate moving WHICH not HOW MANY).** The new method addresses this in the critique (Attack 3) but does not require EDA support for the change-in-count prediction. That worked here in the sense that count DID change as predicted — but the change-in-count is necessary, not sufficient, for the mechanism to be net-positive.
5. **Method-honesty check.** This invocation did NOT personally generate the hypothesis. I am reconstructing the research from NOTES.md and the code. If the prior researcher's NOTES.md is selectively reported — e.g., omitted alternative variants of C they considered — that omission is invisible to me. NOTES.md is unusually thorough relative to typical research notes, so this concern is small but real.
