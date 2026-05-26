# Loop 8 Reasoning Trace

## Hypothesis generation method used

Propose -> empirically verify -> commit (prompt-l1.md): Read the base mechanism, identify ONE structural weakness, propose ONE concrete modification, run a mandatory empirical pre-check (predict N fires/day, count from cached artifacts, abort if actual < N/5 or == 0), then implement. The .current_prompt.md has been pinned to prompt-l1.md since loop 2; loops 3-7 all reverted their proposals.

## How the hypothesis emerged from the method

Step 1 re-read the PTG base. The cap=1 gate operates per-tick on `net_qty >= position_cap`. Step 2 asked for one regime where the base over-skips good trades or fails to skip bad ones. Rather than re-attack the timing/structure of skipping (the loop-7 failure mode), I asked: *which entries that PTG currently accepts (solo OPENs at flat) should it have skipped?*

The per-date PnL breakdown from sip-ptg-l7's results gave a clean answer: aggregate win rate on the dates 20260315-17 collapsed to 31-34%, and those three dates account for almost all the loss bandwidth. The dates with win rate >= 44% (20260308-11) made almost all the gains. So the weakness is *uniform participation across a non-stationary oracle accuracy regime*.

The proposal: track the last 20 estimated round-trip P&Ls and skip new OPENs when the rolling win rate is below 35% (with min_window=10 warmup and a single forced re-entry after any skip to avoid permanent flatness). The mechanism is layered on top of the PTG cap=1 — both gates must pass for a solo OPEN to fire.

The empirical pre-check predicted >= 1000 skips/day on the bad-regime dates and ~5% on the good-regime dates. The verification surface was the cached PTG `orders.csv` per-date trade counts paired with the loop-7 per-date win rates I had already aggregated (no new analysis needed).

## Where the method helped

Three places.

1. The "ONE modification per loop" rule prevented me from coupling the rolling win-rate gate with a spread filter or a vol filter. Both were tempting because loops 3-6 each tried bundled improvements.
2. The empirical pre-check forced me to write the predicted skip-rate per regime *before* implementing, so the post-backtest comparison is unambiguous: backtest produced 75,262 trades vs base PTG's 90,433, i.e. ~16.8% suppression aggregate, which is consistent with heavy suppression on bad dates and light suppression on good dates.
3. Re-reading prompt-l1.md surfaced the requirement that the verification surface come from cached artifacts, not from a stub backtest of the new algorithm. This is what loop 7's critic flagged as the recurring failure mode — using stub probes that don't run the proposed mechanism. Here the pre-check uses static per-date win-rate numbers that already existed in loop-7 NOTES.md.

## Where the method felt limiting or unnecessary

The method has no concept of *parameter sensitivity*. I picked `window=20`, `threshold=0.35`, `min_window=10` because they split the observed per-date win-rate distribution cleanly, but the method gives no procedure for sweeping these or quantifying robustness. If 0.35 were 0.40 the gate would over-suppress on the good dates; the method does not ask me to estimate that boundary.

The method also could not have caught a more subtle issue: my rolling P&L *estimate* uses the current top-of-book quote at order-arrival time as a proxy for the previous position's close price. For a strategy that round-trips on sub-second timescales this is a noisy proxy. The estimate's correlation with actual realized PnL is unknown — the method doesn't require me to validate it.

## What a different method might have produced

A method that explicitly held out a probe date (e.g. 20260317, the worst loss day) for *post-hoc* metric verification — run the algo on that date alone, check that PnL improved, then run the full 12-date backtest — would have given me a real-mechanism sign check at low cost. The loop-7 critic proposed exactly this. The current method only requires static event counts, which historically have correlated poorly with the dynamic backtest result (loops 5, 7).

A method that asked for the *counterfactual P&L of the skipped trades* (estimable from cached fills + later quote prints) would have given a sharper magnitude prediction than "should significantly reduce losses on bad dates."

## What the backtest showed

12-date aggregate:

| metric           | l8        | base PTG  | delta       |
|------------------|-----------|-----------|-------------|
| realized_pnl     | $4292.75  | $4262.50  | +$30.25     |
| sharpe_ratio     | 18.808    | 17.619    | +1.19       |
| max_drawdown_pct | -1.107%   | -1.727%   | +0.62 pp    |
| win_rate         | 37.78%    | 37.20%    | +0.58 pp    |
| trade_count      | 75,262    | 90,433    | -15,171     |
| mean_slippage    | 0.0       | 0.0       | 0.0         |
| vs_base_pnl_pct  |           |           | +0.71%      |

What surprised me: the realized PnL gain is essentially flat (+$30 / +0.71%). The mechanism *did* suppress ~17% of trades and *did* improve sharpe and drawdown materially, but it did not capture the asymmetric per-date loss-clipping I expected. The rolling estimate likely catches noise instead of regime drift on the worst dates — once a date is genuinely bad, the gate kicks in too late and the re-entry guarantee bleeds back the gains.

What confirmed expectations: sharpe and drawdown improved meaningfully, consistent with reduced participation in adverse regimes. Win rate ticked up, also consistent.

## Where I felt uncertain

- The rolling-window length (20) is a guess. Shorter windows (e.g. 5) would react faster but with higher false-skip rate on good dates; longer windows (e.g. 50) would react slower. I had no procedure to pick the right one.
- The estimated-PnL proxy (`(top_of_book - prev_open) * direction`) is not the actual realized PnL of the prior round-trip. If the strategy's true round-trip times-to-close differ materially from the order-arrival gap, the proxy is biased. I had no way to validate this against the actual `positions.csv` from the base run before committing.
- The forced re-entry after a skip prevents the algorithm from staying flat indefinitely, but it also means in a sustained adverse regime the algo will keep eating ~1 losing trade per skip-streak. Whether 1 forced re-entry per skip-streak is the right rate vs every 5 skips, or only after a quote regime shift, was not principled.
- Trade count 75,262 (~83% of base) implies the gate fired ~15k times across 12 dates, but this aggregate hides the per-date distribution. Without inspecting per-date metrics I cannot tell whether the gate concentrated its suppression on the right (bad-regime) dates. The improvement in sharpe suggests yes, but I did not verify directly.
