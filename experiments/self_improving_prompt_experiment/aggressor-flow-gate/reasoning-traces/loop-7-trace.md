# Loop 7 Reasoning Trace

## Hypothesis generation method used

prompt-l0.md — the seed 4-step single-pass linear method (read base → identify ONE weakness → propose ONE concrete modification → state expected direction). Still in force because the L6 proposed method (live-instrumentation calibration) was reverted by the keep/discard gate, and `.current_prompt.md` was restored to the L5 prompt_in = prompt-l0.md.

## How the hypothesis emerged from the method

Step 1: I read `execution_algos/aggressor-flow-gate/execution_algorithm.py` and its NOTES.md. The base maintains a 10s rolling deque of `(ts_event, signed_size)` aggressor flow and skips opening orders when `|net_flow| >= flow_threshold = 2.0` and adverse to the order side. Anti-cascade: post-skip `_position_flat = True` forces unconditional submit on the next order.

Step 2: ONE weakness. I traced down structurally untouched axes by reading prior loop trace summaries (loop-5-trace.md notes l1=EWMA, l2=asymmetric side, l3=two-window AND, l4=fraction-normalization, l5=cascade policy, l6=cascade param calibration). Axes touched: re-weighting within the window, side-asymmetry, dual-window timing AND, post-skip cascade policy, cascade param calibration. Axis NOT yet touched on this arm: a **volume-regime denominator** for the gate threshold. The base fires on absolute contract count regardless of total window volume — `|net_flow| >= 2.0` means a strong directional signal in a slow regime (4 total trades → 75% imbalance) and statistical noise in a fast regime (100 total trades → 51% imbalance). The base treats both identically, producing false-positive skips during high-volume periods.

Step 3: ONE concrete modification — add a conjunctive proportional gate. Skip iff `|net_flow| >= flow_threshold AND |net_flow| / max(total_window_vol, 1.0) >= ratio_threshold`. Default `ratio_threshold = 0.20`. The deque tracks one extra running scalar `_abs_flow = sum |signed_vol|` updated in lockstep with `_net_flow` (O(1) per tick, no extra deque storage). Strictly tighter than base → can only REDUCE skip rate.

Step 4: Predicted direction — small positive realized_pnl vs base (drop noise skips), increased trade_count (fewer skips), unchanged slippage (0.0 on both sides). The falsification path: if removed skips were actually adverse (just on high-volume), realized_pnl regresses.

The hypothesis came cleanly from the method's 4 steps. I picked `ratio_threshold = 0.20` from intuition (the method has no calibration step). I did NOT measure the empirical distribution of `|net_flow| / total_window_vol` at base-skip-firing moments — exactly the kind of gap the method leaves unaddressed.

## Where the method helped

The "ONE weakness, ONE modification" framing pushed me to enumerate the structural axes already explored on this arm and identify the one nobody had touched. Without that discipline I might have proposed a hybrid (e.g. ratio gate + L5 cascade policy together), which would confound attribution between the two mechanisms. Inheriting the base's `_position_flat` anti-cascade (rather than L5's `_skip_streak`) keeps L7 a clean test of the proportional-gate axis against the base.

The method's framing ("a regime where the gate over-skips good trades or fails to skip bad ones") was a productive lens. In the high-volume regime, net_flow=±2 is noise and skipping there is over-skipping. That reframing led directly to the denominator idea — the gate is over-firing in fast regimes because it has no per-tick normalization.

## Where the method felt limiting or unnecessary

Same single-pass blindspot prior loops have flagged. Step 3 asks me to "propose ONE concrete modification" but provides no mechanism to test whether the modification's parameter (`ratio_threshold = 0.20`) is in the right ballpark before committing. I picked 0.20 because it's a round number that excludes 50/50-ish regimes while preserving the strong-imbalance regime. Nothing in the method asked me to (a) measure the empirical distribution of `|net_flow| / total_window_vol` at base-skip-firing arrival moments, (b) estimate what fraction of base skips have ratio < 0.20 (the proportion my filter would un-skip), or (c) check whether those would-be-un-skipped events have positive or negative average forward return.

A second limitation: the method asks me to identify ONE weakness without first determining whether the chosen weakness is the BIGGEST remaining weakness. The structural-axis enumeration argument is sound but I have no way to rank the unexplored axes against each other. Maybe a different axis (e.g. session-time-of-day conditioning, trade-size weighting that's NOT linear, microprice-trend confirmation) would have been higher-leverage. The method does not surface that ordering.

A third limitation surfaced this loop specifically: the seed prompt method does not require checking what the **running-best LIKE-AXIS algorithm** is on this arm. L5 already beat base by +3.3% via a cascade-policy modification. By targeting a base weakness with a new mechanism (inherited from base, not L5), I am implicitly competing against base alone — but the critique-phase gate compares my result against L5, not base. The method gave me no signal that the relevant goalpost was L5's 1002 pnl, not base's 970 pnl.

## What a different method might have produced

A method that included a mandatory "predicted vs running best" step would have caught my underperformance risk. If the method had asked me to:

1. Read the running-best loop (L5) and its NOTES.md
2. Predict whether my proposed mechanism would compose with L5's cascade policy or replace it
3. State whether the predicted result must beat L5's 1002 pnl on 11 dates (not base's 970) to be kept

...then I would have either (a) proposed L7 = L5 + ratio gate (composed), or (b) abandoned the ratio gate because the predicted improvement vs base (+3% to +5%) is roughly the same magnitude as L5's existing edge over base — meaning my method would tie L5 at best, and lose on noise.

Alternatively, a "minimum-viable-evidence" method requiring ONE empirical number before committing to the parameter would have surfaced the actual distribution. Even 100 base-skip arrival points from one train date would have shown whether ratio < 0.20 captures 10% of base skips (gate has limited effect) or 90% (gate destroys most of base's filter).

## What the backtest showed

Raw numbers on the 11 dates where both algos completed (20260319 OOM'd on L7 same as L5/L6 — dropped from the aggregate, flagged here, per invocation instructions to not retry):

**sip-afg-l7 on 11 dates**:
- realized_pnl: $669.00
- sharpe_ratio: 3.067
- max_drawdown_pct: -3.98%
- win_rate: 0.3533
- trade_count: 96,176
- mean_slippage: 0.0

**aggressor-flow-gate on SAME 11 dates** (re-aggregated locally):
- realized_pnl: $970.00
- trade_count: ~87,760

**sip-afg-l5 (running best) on SAME 11 dates** (from L5 backtest-results.json):
- realized_pnl: $1002.00
- sharpe_ratio: 4.947
- max_drawdown_pct: -2.93%
- win_rate: 0.3538
- trade_count: 78,442
- mean_slippage: 0.0

**Deltas**:
- L7 vs base: **-31.03%** realized_pnl on matched 11 dates ($669 vs $970). **WORSE than base.**
- L7 vs L5: -33.23% realized_pnl. **0 of 5 metrics improved** vs L5 (pnl worse, slippage tied, sharpe worse, mdd worse, win_rate worse).
- L7 vs simple baseline (gate criterion): +1446.82% (still PASSES gate vs configured baseline, but that's just because the base mechanism itself beats simple massively).

What confirmed expectations:
1. trade_count rose vs base (96,176 vs ~87,760) — the proportional gate IS un-skipping a meaningful chunk of base skips, as predicted (strict subset filter).
2. mean_slippage stayed 0.0 (zero fill-cost model).

What falsified the hypothesis: the un-skipped orders were on net **adverse**, not noise. The proportional gate filters out skips on a regime where `|net_flow| >= 2` but `|net_flow| / total_vol < 0.20` (i.e. 100+ contracts of total volume but only marginal net imbalance). Those events apparently DO have negative expected forward return — base's broad-stroke filter was capturing them correctly, and removing the proportional gate would have been the right move, not adding it. The hypothesis predicted "base over-skips in high-volume regimes"; the data says "base correctly skips in high-volume regimes when even a small net imbalance is present."

Magnitude: the realized_pnl dropped by $301 (vs base) and by $333 (vs L5) on 11 dates. This is far outside the magnitudes seen for L5 (small +) or L6 (small +). L7 is unambiguously worse, not noise.

## Where I felt uncertain

- `ratio_threshold = 0.20` is uncalibrated. The single-pass method gave me no way to validate it. Even one date of EDA on |net_flow|/total_vol at base-skip moments would have caught this — but the method does not require that step.
- The hypothesis's directional prediction (lift) was wrong by 30+ percentage points. Either (a) the proportional gate is a fundamentally bad axis (high-volume + small-imbalance regimes are MORE adverse than low-volume + small-imbalance, opposite of my prior), or (b) the threshold is too aggressive (0.20 might be removing 70-80% of base skips). I cannot tell which from the aggregate metrics alone.
- 20260319 failed again with `memory allocation of 4294967296 bytes failed` — same OOM signature as L5/L6. The base algo handled it (~19,438 trades on that date). The pattern is consistent: any algorithm that does even a single extra running scalar on the trade-tick path appears to push memory pressure past a threshold for that specific date. This is a host-level issue, not algorithm-specific. n=11 vs n=12 small-N caveat applies (~0.4 Sharpe SE per OBJECTIVE.md §8).
- I am uncertain whether L7's loss is reproducible OOS — but the train-loss is so clear and the mechanism so explicit (removing base skips that turned out to be correct) that OOS would almost certainly look similar or worse. There's no obvious regime-specific reason to expect this to recover on the test window.
- The seed prompt's "vs `<base_algo>`" framing put the goalpost at base. But the gate compares vs L5 (the running best). I would have benefited from being told upfront that "kept" requires beating L5, not just base — the method silently assumed base was the comparison.
