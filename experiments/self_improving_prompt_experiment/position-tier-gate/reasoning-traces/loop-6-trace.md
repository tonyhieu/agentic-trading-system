# Loop 6 Reasoning Trace

## Hypothesis generation method used

Propose → empirically verify → commit (prompt-l1.md): Read base mechanism, identify ONE weakness, propose ONE modification, mandatory empirical pre-check (predict N fires/day, count from cached artifacts, abort if actual < N/5 or == 0), then implement.

## How the hypothesis emerged from the method

Step 1 re-read the base PTG mechanism. Step 2 searched extensively for a weakness by analyzing: time-of-day patterns, cooldown gates, direction-flip gates, consecutive loss/win streaks, session-elapsed time, arrival_mid changes, and zero-PnL position patterns. After ruling out all other axes (either regime-inconsistent or positive-PnL subsets that hurt when skipped), I settled on the "post-zero-flip" gate: skip direction-flip OPEN orders following zero-PnL closed positions.

Step 4 empirically pre-checked: 11,406 events across 12 dates = 950/day average (predicted N=500). PASS. Static PnL estimate: +22.50 improvement (+0.53%).

## Where the method helped

The empirical pre-check step correctly verified event-class frequency. The systematic artifact analysis exposed many dead-end hypotheses (direction flips, consecutive loss/win patterns, cooldown gates all showed negative static estimates). The method forced enumeration of the hypothesis space before committing.

The method also correctly prevented me from exploring banned axes (spread, in-flight PnL, position cap).

## Where the method felt limiting or unnecessary

The static estimate was wildly wrong: +0.53% predicted, actual = -9.72% vs base. The zero-flip gate removed 6,829 positions/12 days with total PnL of -22.50 (mean -0.0033). But the dynamic cascade effect was DIFFERENT from the static removal estimate. When we skip zero-flip OPENs, we stay flat and wait for the next signal, which changes the subsequent position sequence. The next positions that fill have different properties from what the static analysis predicted.

The method has no mechanism to check whether the dynamic cascade will amplify or reverse the static estimate. A one-date probe backtest (as suggested by loop-5's proposal) would have validated this before full implementation.

## What a different method might have produced

A method requiring a mandatory one-date probe before full implementation (as in loop-5-proposal.md) would have run on 20260316 (median volume date) and showed: l6 PnL = -X vs base -37 for that date, allowing judgment of whether the cascade helps before committing to 12-date backtest.

## What the backtest showed

Raw numbers:
- sip-ptg-l6: realized_pnl=$3,848.0, sharpe=17.09, trade_count=83,604, max_drawdown=-1.74%, win_rate=37.13%
- vs_base_pnl_pct: -9.72% vs base PTG
- vs_base (loop 2, running best): pnl improved (+74, +2.0%), sharpe worse (17.09 vs 19.21), max_dd worse (-1.74% vs -0.54%), win_rate worse (37.13% vs 37.49%)

Surprised by: the static estimate predicted +22.50 gain but the actual is -414.50 (4262.50 - 3848.0). The zero-flip gate removed substantially more value than expected from the static analysis. The positions that followed the skipped zero-flip OPENs were also less profitable than those that the gate replaced them with.

The trade count dropped by 6,829 (7.55%), meaning the gate removed ~570 positions/day. This is close to the predicted 950/day, suggesting the gate fired but removed positions that were actually more profitable in the dynamic execution than the static PnL of those positions suggested.

## Where I felt uncertain

1. The static PnL estimate (+22.50) was very small and I noted it might not survive dynamic cascade effects. This warning was correct - the cascade went strongly negative.

2. The mechanism for accessing last closed position's realized_pnl via `cache.positions_closed()` seemed correct but the interpretation may differ. The zero realized PnL in positions.csv might correspond to cases where the oracle's signal was exactly at the price boundary, and these positions are followed by OTHER oracle signals (not just one) that the static analysis didn't account for.

3. I explored many axes before settling on this one, which suggests the PTG is near-optimal for this oracle configuration. The search was exhaustive but all positive signals from static analysis turned out to be weak or wrong.
