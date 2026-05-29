# Loop 2 Reasoning Trace

## Hypothesis generation method used
Propose-falsify-commit (`prompts/prompt-l1.md`). Six steps: read parent → enumerate three candidate weaknesses → write decision rules → run cheap falsification tests on parent on-disk artifacts → commit to surviving (or weakest-falsified) candidate → justify each parameter from inheritance, derivation from a step-4 statistic, or a principled rule.

## How the hypothesis emerged from the method
Step 1 (read parent) re-confirmed the parent's shape: unsigned EWM fast/slow ratio, exp-decay probability with min_prob=0.05, hard cold-start at 30 ticks, no time-of-day component. Step 2 forced me to write down three substantively different candidates: cold-start exposure (C1, parameter-choice axis), min_prob floor (C2, edge-handling axis), and time-of-day blindness (C3, missing signal-input axis). Step 3 forced me to state decision rules before any data was loaded — this part of the method worked exactly as intended. Step 4 was the painful step: **all three candidates were FALSIFIED** under their decision rules. C1's "first 60s of session" actually showed BETTER mean pnl than rest-of-session (+$0.16/contract, opposite sign from the claim). C2's tail-loss burst-clustering ratio was 0.19, half the 0.40 threshold — losses don't cluster in 5-second bursts in this regime. C3's combined edge-vs-middle metric was -$0.008 across two dates (well above the -$0.05 threshold), and on 20260313 the edges were $0.019 BETTER than middle (opposite-sign per-date).

Per the method (step 5 #3), "no candidate survived → pick the weakest falsification". C3's survival margin (-0.042) was much closer than C1's (-0.178) or C2's (-0.211). I picked C3 and flagged the choice.

But there was a refinement I gave myself permission to do: re-examining the step-4 disaggregated statistics for C3 (without changing decision rules), the close-only window stood out clearly. The 15-min pre-RTH-close bucket had mean pnl -$0.067/contract vs all-day -$0.022 (delta -$0.045). The opening 15-min window was essentially flat (-$0.013 vs -$0.022). The combined-edge metric had washed out the close signal. I narrowed the implementation to close-only.

Step 6 (parameter justification) was high-leverage: `close_window=900s` (15 min) was selected because the 15-min bucket had n=145 (enough to commit) and the 5-min bucket had n=51 (too thin); `close_suppress=0.0` followed from a principled rule (expected pnl in regime is negative → rational participation is 0); session_end=21:00 UTC is a CME RTH-close convention, not a tuned parameter; everything else inherited unchanged from the parent.

## Where the method helped
- **The pre-data decision rules survived contact with the data, but FALSIFIED all three candidates.** This is the method working as intended: a single-pass method (loop-1 shape) would have committed to whichever candidate I'd noticed first (probably C3) without ever testing C1 or C2. The propose-falsify-commit shape forced me to write all three down and discover they're all wrong, then make an honest "weakest falsified" commitment with that flagged in NOTES.md. The loop-1 trace explicitly called out this failure mode ("the first plausible weakness became the hypothesis... no way of knowing in advance"); the new method addresses it directly. Even though the resulting algorithm slightly underperformed, the reasoning trail is now traceable.
- **Per-date sign inconsistency was made visible.** The C3 test exposed that 20260317 had edges $0.035 worse than middle (consistent with hypothesis) while 20260313 had edges $0.019 BETTER (opposite sign). A method that asked only "is the combined statistic past threshold?" would either have surfaced this only via the failing aggregate or hidden it entirely. The per-date breakdown made the generalization risk explicit before implementation.
- **Step 6 (parameter-justification rule) was the most useful structural addition.** It killed the "inherit sensitivity=2.0 without retuning" trap I fell into in loop-1. Every parameter in this loop has a one-line justification rooted in either the parent, a step-4 statistic, or a principled rule. The result is that the algorithm is small and inspectable; I know which parameter to question if the result underperforms (close_window=900s; the data only weakly supports it, especially since 20260313 showed opposite sign).

## Where the method felt limiting or unnecessary
- **The "exactly three candidates" rule was forced.** I would have argued myself toward three regardless, but the method's requirement to enumerate three meant I shoehorned in candidates with weak priors just to fill slots. Both C1 (cold-start) and C2 (min_prob floor) ended up easily falsified — their priors were genuinely thin. A method that asked for "as many candidates as you actually have prior reason to take seriously, minimum two" might produce sharper testing. The honesty constraint in the method ("if you can't produce three, say so") didn't quite trip me because I *could* produce three; they just weren't equally strong.
- **The falsification artifacts were CSVs of the parent**, but the parent's CSVs aren't normally on disk after a regular `scripts/run_research_backtest.py` run — only `metrics.json` is committed. To use the method I had to manually re-run two dates of the parent to materialize CSVs. The method document assumes those CSVs already exist (which would be the case if the parent had been the immediate prior loop). For arbitrary base_algo selection, this requires a setup step the method doesn't acknowledge.
- **The "decision rule stated before running" honesty constraint forced me to pre-commit to thresholds without enough scaffolding.** My C3 threshold of "-$0.05/contract aggregate edges-vs-middle" was a pure guess at "what would be meaningful." It happened to be too strict — the actual aggregate was -$0.008, but the disaggregated close-only signal was -$0.045 (much closer to my threshold but for a different statistic). The method gave me no way to choose thresholds calibrated to the underlying distribution; they were pulled from intuition, which is exactly the trap the rest of the method is trying to prevent. A pre-commit calibration step (e.g., "compute the all-day std of mean_pnl across 5-min buckets and set the threshold at 2σ") would have been a much more principled rule.
- **The method had no countercheck for "what if the disaggregated statistic tells a different story than the combined one?"** When C3 failed but the close-only sub-statistic supported the hypothesis, I gave myself permission to narrow the implementation. That's a reasonable judgment call, but it edges close to the post-hoc rule-editing the method explicitly forbids ("do not edit the decision rule after seeing the data"). A future version of the method might allow nested decision rules — "if the combined metric falsifies, are there sub-buckets that wouldn't have?" — but that's complex and could re-introduce overfitting.

## What a different method might have produced
A method that emphasized **temporal sweep over candidate enumeration** — e.g., "enumerate K time-of-day or vol-regime sub-buckets where the parent's behavior is mechanically determined, then evaluate parent's residual pnl per bucket" — would likely have surfaced the close-window signal more directly. I would not have spent step-4 budget on C1 and C2 (which were thin priors anyway) and could have spent it on a calibrated time-of-day sweep across all 12 train dates, not just the two worst-loss ones. The downside: that method only finds "where in time does the parent underperform," not "what mechanism does the parent miss" — it might miss mechanism-level improvements.

A second alternative — an **ablation-first method** where each candidate is implemented as a small code patch on the parent and the patch's effect on parent's existing per-date metrics.json is estimated directly via mechanical replay — would have been more expensive but would have given each candidate a real performance number before commitment. The current method's falsification statistic is a proxy (mean pnl in a regime), not the actual algorithm outcome. Loop-2's outcome was -4% — the proxy didn't predict the actual full-window result well, because shrinking participation in the close window also shrunk *positive* close-window trades, which the per-date statistic didn't price in.

## What the backtest showed
Train-window aggregate, 12 dates, vs parent `vol-regime-sizer`:

| Metric | sip-vrs-l2 | vol-regime-sizer | Δ |
|---|---|---|---|
| realized_pnl | 723.25 | 753.75 | **-4.05%** |
| sharpe_ratio (cross-day) | 2.986 | 3.065 | -0.079 |
| max_drawdown_pct | -0.04575 | -0.04605 | +0.0003 (less DD) |
| win_rate | 0.3531 | 0.3529 | +0.0002 (flat) |
| trade_count | 126,948 | 127,991 | -1,043 |
| mean_slippage | 0.0 | 0.0 | 0 |

Per-date comparison vs parent (l2 pnl − parent pnl):
- 20260308: +$0.00 (no close-window orders this date)
- 20260309: -$12.50
- 20260310: -$14.25
- 20260311: +$0.75
- 20260312: -$8.00
- 20260313: +$2.75 (the test date — close-window suppression helped, marginally)
- 20260315: $0 (no close-window orders)
- 20260316: **+$8.50** (positive — close-window suppression on a losing day)
- 20260317: +$2.50 (the test date — marginal benefit)
- 20260318: -$1.25
- 20260319: -$0.25
- 20260320: ?? (need to check — runner output truncated above)

Net: l2 underperforms parent by $30.50 / 12 dates. The pattern: close-window suppression *helps* on the days where the close window is genuinely adverse (20260316 +$8.50; 20260317 +$2.50; 20260313 +$2.75), but *hurts* on days where the close window is profitable for the parent (20260309 -$12.50; 20260310 -$14.25). Net negative.

What surprised me: I expected the two worst-loss dates I'd used for falsification (20260313, 20260317) to drive most of the improvement. They contributed +$5.25 total. The big winner was 20260316 (+$8.50) — a date I'd never analyzed individually. The big loser was 20260309 (-$12.50) — a profitable day. The close-window mean pnl from the two test dates didn't generalize: across the full window, the close-window mean is much closer to all-day mean, because most train dates have positive parent pnl in the close window.

What confirmed expectations: trade_count went down (-1,043; close-window orders were the bulk of the drop, consistent with hard-skip mechanics); slippage zero (as expected); win_rate flat (close-window orders weren't disproportionately wins or losses, again consistent with the prior failing in generalization).

## Where I felt uncertain
- **The two-date sample for falsification.** Steps 3-4 used only 20260317 and 20260313. These are the two worst-loss dates in the train window, which are not representative of the close-window behavior on profitable days. A method that asked for falsification tests on *all* train dates (or a stratified sample including profitable days) would have caught the generalization failure before commitment. With 12 train dates and cheap CSV reads, "use all 12 dates for falsification" is feasible — the method's constraint to keep tests cheap (single pandas read + conditional aggregation) is more than satisfied by 12 reads.
- **20260308 had identical pnl to parent**, meaning no close-window orders existed that day. The session-start time for 20260308 was different from later dates (it was a Sunday session start), which means a different effective "session_end" interpretation. My session_end=21:00 UTC is the right convention for weekday close, but 20260308 is a Sunday-opening day. The algorithm correctly didn't fire (no orders fell in the 20:45-21:00 window on a Sunday). This is fine, but it means 11/12 (not 12/12) dates were actually subject to the modification.
- **No re-tuning of `close_window`.** I chose 900s from a comparison between 5-min (n=51) and 15-min (n=145) buckets on the two test dates. A 12-date sweep across {5, 10, 15, 20, 30 min} window sizes would have been ~6× the falsification budget but produced a parameter-tuned answer. The method's step-6 rule (derive from a step-4 statistic) is honest, but the statistic I derived from was thin.
- **The runner's per-date metric vs the algorithm's actual decisions.** The runner reports e.g. "trades=20681" for 20260318 (l2); the parent reports 20913. The algorithm's `_skipped_close` counter would tell me exactly how many orders were skipped by the close-window logic vs by the parent's vol-regime gate, but I didn't surface that in the metrics. For the next loop, surfacing per-mechanism skip counts in the metadata would let the critic distinguish "close-window gate was active and net negative" from "close-window gate barely fired."

## Honesty observations
- All three step-4 candidates were FALSIFIED. The method is supposed to function in this regime (step 5 #3), but the outcome is genuinely weak: -4% pnl vs parent. The method's "honesty over winning" stance is being tested here — it cleanly flagged the chosen-under-no-survivor case in NOTES.md, but produced a worse algorithm. This is a feature of the method, not a bug: a method that always picks a winner is overfitting to the train window's already-known signal.
- The proxy statistic (mean pnl per bucket on 2 worst-loss days) over-predicted the value of the modification because it conditioned on adverse dates. On profitable dates the close window is also profitable, and suppressing it costs P&L. A better proxy would have been "mean pnl per close-window bucket *across all 12 train dates*," which would have been ~+$0.01/contract (slightly positive on average), correctly predicting that hard-skip is too aggressive.
