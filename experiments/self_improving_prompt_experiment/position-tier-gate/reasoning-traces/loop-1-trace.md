# Loop 1 Reasoning Trace

## Hypothesis generation method used

Seed prompt's 4-step single-pass method: (1) read the base algo's code + NOTES.md, (2) identify ONE plausible weakness of its gate, (3) propose ONE concrete modification that addresses the weakness without breaking constraints, (4) state the expected direction of the change in P&L and slippage and why.

## How the hypothesis emerged from the method

Step 1 surfaced the central mechanism of `position-tier-gate`: with `cap=1`, the OPEN leg of the oracle's same-`ts_init` CLOSE+OPEN pair is always skipped because the cache still shows the prior position. The NOTES.md explicitly called the gate "direction-blind" only implicitly (it treated every concurrent OPEN identically regardless of the in-flight position's sign vs the new order's side).

Step 2 latched onto that implicit asymmetry. There are two qualitatively different oracle events that the gate folds together: a flip (old long, new sell) and a continuation (old long, new buy). The flip case is plausibly mean-reverting noise at sigma=6 / 1-second cadence — filtering it is correct. The continuation case carries persistence: the oracle's posterior on direction didn't move, only the position lifecycle forced a round-trip. Letting continuations through while still filtering flips seemed like a clean asymmetric refinement.

Step 3 followed mechanically: read the cache's signed direction, compare to `order.side`, route accordingly. No quantity modification, no book walking — submit/skip only. Constraints trivially preserved.

Step 4 stated expected direction: trade_count ↑ vs base (continuations now pass), realized_pnl ↑ if continuation re-entries are positive-EV. Slippage unchanged. Sharpe direction uncertain.

## Where the method helped

The "read the base mechanism first" step did push me to look at the *concrete* timing detail in the base's NOTES.md — the same-`ts_init` CLOSE+OPEN and the cache lag — rather than treating cap=1 as an abstract knob. Without that, I might have proposed a parameter sweep (cap=2, cap=3) that NOTES.md explicitly shows would do nothing because the oracle never holds more than 1 contract.

The "ONE plausible weakness" constraint forced focus. I considered four directions during step 2 (cap as a function of recent volatility, hysteresis on the cap, signed cap, directional pass-through). The "one weakness only" framing made me commit to the asymmetry case and write it up cleanly rather than diluting across multiple candidates.

## Where the method felt limiting or unnecessary

The method has no countercheck step before committing to implementation. The single critical question I should have answered up front — "does the oracle ever actually emit a same-side OPEN at the same `ts_init` as a CLOSE?" — is exactly the kind of question that determines whether the proposal does anything at all. The method does not require any analysis of the order stream the algorithm would receive. It assumes the proposer's intuition about the source process is good enough.

I generated my hypothesis in pure prose and went straight to implementation. There was no step that said "before you write code, check the empirical distribution of the events you are conditioning on." That gap is exactly what bit me — see the next section.

Step 4 ("state expected direction") is also weak. It asks for direction-of-change predictions but does not ask the proposer to predict the *magnitude* of the trigger rate (how often the new pass-through fires per day). A magnitude prediction would have forced me to estimate "X continuation events per day" and the moment I tried to estimate that I would have realized I had no model of how often the oracle emits same-direction re-entries vs flips.

## What a different method might have produced

A method with a mandatory pre-implementation empirical check would have caught this. For example: "Before writing code, identify a measurable consequence of your proposed change (e.g., 'continuation pass-throughs should fire ≥ N times per day'). Confirm from the existing per-date orders.csv or fills.csv that the consequence is observable, or design a one-day micro-backtest that would produce zero diff if the hypothesis is null." Under that method I would have grep'd the existing `position-tier-gate` orders.csv for cases where the gate skipped an OPEN whose side matched the in-flight position's sign — and found zero such events — and the hypothesis would have been rejected at design time rather than after a 12-day backtest.

A proposer-criticizer method might also have worked: the criticizer's job would be to ask "is the event you are conditioning on actually rare or non-existent under the oracle's design?" — and a half-decent criticizer reading the base NOTES would have flagged that the oracle emits CLOSE+OPEN only at sign-flip moments, which by construction makes the in-flight position and the new order opposite-signed.

## What the backtest showed

Aggregate metrics over 12 train dates: identical to the base `position-tier-gate` to floating-point precision.

| metric | sip-ptg-l1 | position-tier-gate | delta |
|---|---|---|---|
| realized_pnl | 4262.50 | 4262.50 | 0.00 |
| sharpe_ratio | 17.6190 | 17.6190 | 0.0000 |
| max_drawdown_pct | -0.01727 | -0.01727 | 0.0000 |
| win_rate | 0.37204 | 0.37204 | 0.0000 |
| trade_count | 90433 | 90433 | 0 |
| mean_slippage | 0.0 | 0.0 | 0.0 |
| vs_base_pnl_pct | 0.0 | — | — |
| vs_base_slippage_pct | 0.0 | — | — |

Per-date comparison: 9 of 12 dates produced bit-identical metrics.json files. 3 dates differed only in the last decimal digit of `is_mean_bps` / `is_weighted_bps` — floating-point rounding noise from a slightly different code path in `on_order()`. The continuation pass-through fired **zero** times across the full train window.

This is consistent with the oracle's design: it emits a same-`ts_init` CLOSE+OPEN pair only when its target direction flips sign. When the target goes target=1 → target=0 → target=1 (return to the same side after a flat period), the CLOSE and the next OPEN are at *different* `ts_init`, the CLOSE has fully cleared the position by the time the new OPEN's `on_order()` fires, the cache shows flat, and the gate's "if flat: SUBMIT" branch fires — same as the base. The condition the new pass-through gates on — "cache shows an open position AND incoming order is same-side as that position" — never occurs.

What surprised me: I had assumed at least *some* events would arrive in that state. They don't. The asymmetry I built the algorithm around does not exist in the oracle's emission process.

What confirmed expectations: slippage was unchanged (no book walking on either side). Trade count was the same as base, which makes sense post-hoc (no new orders submitted = no new fills counted).

## Where I felt uncertain

Several uncertainties in retrospect that I underweighted at hypothesis time:

1. The empirical question "is the asymmetric event class non-empty?" was never asked. I reasoned about the oracle's behavior at the level of "noisy direction forecaster at 1Hz" without inspecting the actual order stream it produces. That was the load-bearing assumption and I never checked it.

2. The decision to keep `position_cap=1` (same as base) was deliberate — I wanted to isolate the directional cut. But coupled with the empirical reality, this made the algorithm a strict identity transform on the order stream.

3. One subtle constraint edge case: when the cache reports multiple open positions (which shouldn't happen in a netting OMS but I handled defensively), I picked direction from the sign of the summed signed quantity. This branch was never exercised because the netting OMS always has 0 or 1 open positions.

4. A 4 GiB allocation on 20260319 hit the runner's 16 GB RLIMIT_AS cap and crashed the subprocess on the first try. I worked around it by setting `RESEARCH_MEM_CAP_GB=32` for the retry. The 12-date aggregate is intact, but this is a real failure mode of the runner that doesn't show up on lighter algorithms — `sip-ptg-l1` processes the full unfiltered order stream (because the continuation branch passes through identically to the base's submit path) and the busiest day stress-tests the cap. The metrics are still trustworthy; only the path to producing them was rougher.

5. The trade_count for the OOM-day on the first run (before retry) doesn't match the base because OOM truncated the run mid-day; after retry with 32 GB cap the day completed and matched. I used only the completed run.
