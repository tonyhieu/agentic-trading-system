# Loop 5 Reasoning Trace

## Hypothesis generation method used

Propose → empirically verify → commit (prompt-l1.md): Read base mechanism, identify ONE weakness, propose ONE modification, mandatory empirical pre-check (predict N fires/day, count from cheapest artifact, abort if actual < N/5 or == 0), then implement.

## How the hypothesis emerged from the method

Step 1 identified the PTG mechanism: skip OPEN leg of CLOSE+OPEN pairs when cache shows net_qty ≥ 1 (cap). Step 2 identified the weakness: ALL paired OPENs are currently skipped (even those with positive expected PnL from historical data). Step 3 proposed cap=2 as the minimal modification to allow paired OPENs to fire. Step 4 empirically verified the event class is non-empty (7,535 fires/day average across 12 training dates). The method shaped the hypothesis directly.

However, the analysis in Step 2 was flawed: I computed the PnL of "direction-flip positions" from positions.csv and estimated +$667 gain from submitting them. This was a static removal estimate that failed to account for the dynamics in a netting OMS when two opposing positions coexist. The method's empirical pre-check validated that the event class is non-vacuous but did not validate the DIRECTION of the effect.

## Where the method helped

Step 4 correctly required a non-vacuous event count before proceeding. The count from orders.csv (INITIALIZED, non-reduce-only orders) was easy to compute and clearly confirmed N=7,535/day ≥ N_predicted=7,000. This caught several dead-end hypotheses earlier (time-of-day gate showed inconsistent regime behavior across partial vs full-day dates; cooldown gate showed rapid positions are MORE profitable; direction-flip gate showed NEGATIVE static estimate). The method forced abandonment of at least 5 candidate hypotheses before reaching cap=2.

## Where the method felt limiting or unnecessary

The method's empirical pre-check validates that a branch FIRES, but not that it fires with the correct sign. The cap=2 hypothesis passed pre-check (7,535 fires/day — clearly non-vacuous) yet produced -96.3% PnL vs base. The method has no gate for "does the proposed modification improve PnL DIRECTION, not just firing frequency?" A probe backtest on 1 training date should be mandatory when the static estimate is based on removable PnL (which depends heavily on OMS dynamics).

Additionally, 5+ iterations of hypothesis exploration were required before finding an empirically-verifiable non-trivial axis. The method doesn't provide guidance on HOW to explore the hypothesis space when all obvious axes are either regime-dependent, already implemented by PTG, or produce negative static estimates.

## What a different method might have produced

A method that required a single-date probe backtest BEFORE full implementation would have caught the cap=2 failure immediately (running on 1 date takes minutes and would have shown -96% on that date). The current prompt only requires a static artifact count, which misses OMS-dynamic interactions. A probe-first approach — even just checking 1 training date with the algo — would prevent wasting full 12-date backtest cycles on mis-signed hypotheses.

Alternatively, a method requiring "specify the OMS interaction model for your proposed change" would have caught the netting-OMS issue with cap=2: when LONG and SHORT positions coexist, they don't compound alpha — they partially cancel it.

## What the backtest showed

Raw numbers:
- sip-ptg-l5: realized_pnl=$156.0, sharpe=0.60, trade_count=136,734, max_drawdown=-5.3%, win_rate=35.1%
- base PTG: realized_pnl=$4,262.5, sharpe=17.62, trade_count=90,433
- vs_base_pnl_pct: -96.34% (catastrophic underperformance)

Per-date comparison showed cap=2 was worse on 10 of 12 training dates. On high-volume dates (20260316-20260320), the algo accumulated massive positions (20,000-25,000/day vs 13,000-16,000 for base) with strongly negative PnL (e.g., 20260313: -$512.75 vs base +$65.50).

Surprised by: the magnitude of the reversal. Static analysis estimated +15.65% improvement; actual was -96.34%. The netting OMS with simultaneously opposing positions creates a strongly negative dynamic not visible in static position-PnL analysis.

## Where I felt uncertain

1. The static analysis of "flip positions" PnL was treated as additive, but it ignores that cap=2 fundamentally changes position state and the sequence of future events. I was uncertain whether the netting OMS would handle simultaneously-open opposing positions correctly, but proceeded anyway.

2. Multiple candidate axes (time-of-day, cooldown, direction-continuation) all had negative static estimates. Cap=2 was the ONLY one with a positive static estimate, but I should have verified this on a single date before committing to full implementation.

3. The "direction-flip" analysis was fundamentally confusing: the positions.csv "direction flips" are the standalone OPENs that PTG fills (when flat), not the paired OPENs that PTG skips. This confusion led to incorrect PnL attribution in the static estimate.
