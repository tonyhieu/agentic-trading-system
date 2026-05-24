# Loop 1 Reasoning Trace

## Hypothesis generation method used
Seed prompt (`prompt-l0.md`): single-pass, four-step recipe — read parent code/NOTES, identify ONE weakness, propose ONE concrete modification, state expected directional effect. No exploration of alternatives, no countercheck step, no requirement to ground the weakness in market data or prior backtest residuals.

## How the hypothesis emerged from the method
Step 1 of the method (read parent) was high-leverage. `vol-regime-sizer` gates OPEN orders on an unsigned fast/slow ratio of `|Δmid|` — a magnitude statistic, no direction. The oracle strategy emits signed BUY/SELL orders. As soon as I noticed that asymmetry, the weakness in step 2 was immediate: "the parent throws the same probability mass at fade-the-burst entries as at ride-the-burst entries." Step 3 then almost wrote itself — replace the unsigned ratio with a signed `headwind = -side_sign * EWM(Δmid) / EWM(|Δmid|)` and only skip when headwind > 0. Step 4 (expected direction) was easy to state: pnl up if losses cluster on fade, neutral on slippage (zero-slippage fill model), Sharpe up.

The method's linear shape *did* produce a hypothesis with a concrete mechanism. But "produce a hypothesis with a concrete mechanism" is a weak bar — the method would have produced the same shape of hypothesis regardless of whether the proposed mechanism mattered.

## Where the method helped
- Step 1 forcing me to read `NOTES.md` and the actual code (not just summaries) is what surfaced the unsigned-vs-signed asymmetry. A method that allowed me to reason from a one-line description ("parent gates on volatility") would have missed this.
- Step 4 (expected direction) made me commit to a falsifiable prediction *before* running the backtest. Sharpe up, slippage zero, pnl up, trade count between simple and parent. All four held.

## Where the method felt limiting or unnecessary
- **No counter-check step.** The method never asked "what would have to be true for this hypothesis to fail?" I noted the failure mode in NOTES.md ("if losses are drift-symmetric, the gate degenerates") but only because I wrote NOTES.md last; the method didn't require it. A pre-implementation step that forced me to spec out the empirical signature of a *null result* — e.g., "I would see no improvement if oracle losses are direction-symmetric in EWM(Δmid)" — could have been answered cheaply by reading a few minutes of `metrics.json`/order CSVs from the parent before writing any code. I didn't do that. The hypothesis happened to be right, but I had no way of knowing in advance.
- **No alternative-considered step.** The first plausible weakness I noticed became the hypothesis. Other candidates I never wrote down: (a) the parent's cold-start (submit-at-p=1 for first 30 ticks) leaks into the highest-volatility opening minutes; (b) the parent's `min_prob=0.05` floor means even in the worst-fade regime we still submit 1-in-20 orders; (c) the parent's halflife pair (20/120) was inherited from a prior algo without retune. Any of these could have been the chosen modification. The method gave no machinery for comparing candidates before committing.
- **The single-pass shape rewards confidence over evidence.** I wrote NOTES.md asserting "oracle losses cluster on entries that fade short-term drift." I never verified this claim against data. The backtest confirmed it (pnl beat parent on 9/12 dates), but the trace would be honest only if I admit: that line in NOTES.md was a *prediction stated as a finding*. A method that distinguished prior beliefs from confirmed facts would have caught the slippage.

## What a different method might have produced
A two-stage proposer-criticizer ("propose three candidate mechanisms, then attack each one with a falsification test that uses only train-window data already on disk") would likely have produced the same final hypothesis but with at least one cheap empirical check before implementation. E.g., before writing the headwind gate I could have grepped the parent's fills.csv on 20260317 (the worst loss day) for losing entries and computed `side_sign × EWM(Δmid)` at fill time. If the distribution were symmetric, the hypothesis was dead. This is ~10 minutes of analysis that the current method does not ask for.

A second alternative — an architecture-first method ("start from the constraint shape, not the parent's mechanism") — might have produced something orthogonal: e.g., a participation-cap-aware sizer (the parent ignores top-of-book qty entirely) or a session-time-of-day gate (oracle losses likely cluster around open/close). I have no idea whether those would have won; the method as written gave me no way to find out without abandoning step 1.

## What the backtest showed
Train-window aggregate, 12 dates, vs parent `vol-regime-sizer`:

| Metric | sip-vrs-l1 | vol-regime-sizer | Δ |
|---|---|---|---|
| realized_pnl | 1062.25 | 753.75 | **+40.93%** |
| sharpe_ratio (cross-day) | 4.185 | 3.065 | **+1.12** |
| max_drawdown_pct | -0.0427 | -0.0460 | +0.003 (less DD) |
| win_rate | 0.3539 | 0.3529 | +0.001 (flat) |
| trade_count | 127,923 | 127,991 | -68 (negligible) |
| mean_slippage | 0.0 | 0.0 | 0 |

Per-date: sip-vrs-l1 strictly beats the parent on 9/12 dates, ties effectively on 1 (20260311 +48.5, mechanical), is within $11 on 1 (20260318), and loses by $13.25 on 1 (20260317, the worst absolute loss day in the window). The 20260317 inversion is interesting: on the largest-loss day, the headwind gate underperformed the parent — which means the parent's unsigned gate skipped *more* losing orders than the signed gate did on that specific day. Hypothesis: 20260317 had high realized volatility (parent skips a lot) but the signed-drift signal was weak/mean-reverting (headwind ~0, skip rate low). Did not investigate further.

What surprised me: the trade_count delta is tiny (-68 / 127991 = 0.05%). The headwind gate barely skips fewer orders than the parent in aggregate. The pnl gain came almost entirely from *which* orders it skipped, not *how many*. This is the strongest piece of evidence that the directional-vs-unsigned distinction mattered — at the same skip volume, signed-gate wins by $308 over the train window.

What confirmed expectations: pnl ↑, sharpe ↑, slippage 0 (as predicted, the zero-slippage fill model made this trivial), trade count between parent and `simple`. All four step-4 directional predictions held.

## Where I felt uncertain
- **`sensitivity=2.0` parameter.** I copied this from the parent without retuning. The headwind statistic has different scale properties from the unsigned ratio (it's signed-normalized, not a ratio of magnitudes), so 2.0 has no principled justification for the new signal. The fact that it worked at all is mild evidence that the gate is robust to sensitivity in this neighborhood, but I have no idea where the optimum sits.
- **`drift_halflife=20` vs `slow_halflife=120`.** Same story — inherited from the parent. The relevant timescale for "drift against side" might be shorter or longer than the parent's "volatility regime." I did not sweep.
- **20260317 inversion.** Did not investigate why the worst-loss day was the one date the headwind gate lost on. If the critique cares about robustness, this is the loose thread.
- **Backtest environment.** The first run of `scripts/run_research_backtest.py` failed because `S3_BUCKET_NAME` was not in the bash environment (the `.env` file uses an invalid bash variable name `AWS-REGION` on line 3, so `set -a; . ./.env` aborts before the later valid lines). Worked around by exporting the four AWS variables manually. Not a hypothesis-quality issue, but it ate ~10 minutes of wall-clock that the method gave me no warning about.
- **Aggregation re-run.** The earlier agent's prior `backtest-results.json` covered only 1 date (20260317). After running the 2 missing dates I had to re-aggregate across all 12 — the runner's `--dates` flag only aggregates over the dates it ran, so I wrote a one-off helper that loaded all 12 per-date `metrics.json` files and called the runner's `aggregate()` / `write_backtest_results()` / `write_metadata()` directly, then deleted the helper. This was correct but inelegant; a future loop that reruns only some dates will hit the same trap.
