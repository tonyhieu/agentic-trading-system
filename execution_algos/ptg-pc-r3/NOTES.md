# Algorithm Notes: ptg-pc-r3

## Hypothesis

**Mechanism**: WINNERS-RUN gate: skip the oracle's CLOSE order when the position is currently profitable and has been held less than max_extend_seconds. Concretely, on each on_order(CLOSE) with is_reduce_only=True: (1) find the matching open Position via cache.positions_open(instrument_id); (2) compute unrealized_pnl from current quote (cache.quote_tick(instrument_id).bid_price for LONG exit valuation, ask for SHORT) minus avg_px_open; (3) compute hold_duration_ns = clock.timestamp_ns() - position.ts_opened; (4) if unrealized_pnl > 0 AND hold_duration_ns < max_extend_ns (default 1800s = 30min), SKIP this CLOSE - do NOT submit. Otherwise SUBMIT the CLOSE normally. The position remains open; subsequent oracle OPENs at later ticks are blocked by the existing position-tier-gate cap=1 mechanism (verbatim retained), so the algorithm holds the winner until either (a) the next oracle CLOSE arrives with the position now at break-even or red (CLOSE submits, exits), or (b) the hold duration exceeds max_extend_ns (force-exit at the first eligible CLOSE), or (c) end-of-session intraday_flat forces a close. CLOSE orders on losing or stale positions submit unchanged. OPEN orders go through the unmodified cap=1 gate.

**Inefficiency exploited**: Empirically measured (via analysis of positions.csv across all 12 train dates): position duration is strongly correlated with profitability. Positions held 1-2s yield -$0.024/trade avg (30.8% win rate), 5-10s yield +$0.058/trade (41.2% win), 30-60s yield +$0.817/trade (58.7% win), 60-600s yield +$0.922/trade (59.5% win). Position duration of 30+ seconds accounts for $2,157 of total $4,262 base PnL (51%) while being only 2.8% of trades. The mechanism: oracle short-holds are mostly the choppy flip-flop noise; oracle long-holds are sustained directional signals where the oracle is actually confident. By skipping the first CLOSE on a profitable short-hold, we attempt to convert short noisy positions into longer-hold profitable ones. Critically, we condition on CURRENT profitability (unrealized_pnl > 0 at the CLOSE moment), so we only extend trades that the path-evolution has already validated as 'going our way'. The break-even-stop dynamic (exit when goes red) caps the risk of converted winners reverting to losers - they exit at break-even when the next oracle CLOSE fires on a position no longer in the green.

**Why it survives costs**: Mean slippage stays 0 and commissions stay 0 in this simulator (verified from base backtest-results.json). The mechanism only changes the FILTERING of CLOSE submissions and adds no new orders - no execution-cost surface change. The only economic risk is missed reversals: when we skip a CLOSE on a profitable position, the oracle was signaling that the position should be closed (likely because oracle now thinks direction will reverse). If the oracle is right at that moment, the position drifts back into the red and exits at break-even on the next CLOSE - small loss of the original unrealized gain but no negative realized PnL. If the oracle was wrong (false flip signal in a sustained-direction regime), we capture additional drift in our favor. The asymmetry: oracle R^2 ~14% means most individual signals are noise; sustained-direction regimes are where the real edge lives, and they are exactly the regimes where 'flip' signals are most likely to be false alarms.

**Builds on**: position-tier-gate (cap=1 retained verbatim as the OPEN gate). Pivots from r1 (signal-consensus filter, inert) and r2 (loss-cooldown, -6.1% PnL) which both filtered OPENs symmetrically; this filters CLOSEs ASYMMETRICALLY conditional on path-evolution evidence (unrealized_pnl > 0). Different axis entirely.

**Alternatives considered**: (1) Protective stop on losers (round 1 proposal): empirical analysis of positions.csv shows 99% of losers are <=2 ticks, ideal 2-tick stop saves only +4.5% (under gate), and the IDEAL is an upper bound since stops fire on intratrade adverse drift not just ultimate losers. Dropped. (2) Wider stop (5+ ticks): saves <0.1% (essentially no losers exceed 5 ticks). Dropped. (3) Synthetic stop via on_quote_tick monitoring: same problem - loss distribution is too tight. (4) Time-based forced extension (always hold N seconds): blind to current-profitability evidence; would hold losers too. (5) UNREALIZED_PNL >= K_ticks threshold: risks missing long-tail winners that start small. >0 is cleanest. (6) hold_duration >= MIN_HOLD: contradicts the goal of extending SHORT positions. (7) Take-profit at +K_ticks: caps the right tail (winners >5t generate $809), opposite of what we want. (8) Hybrid window: reserved for tuning if base mechanism passes.

**Debate summary**: 2 round(s), outcome=CONVERGED. Key objections resolved: (round 1 BLOCKING on StopMarketOrder API spec) abandoned the protective-stop framing entirely; (round 1 MAJOR on uncalibrated stop threshold) used the analysis skill to measure empirical loss and duration distributions, pivoting to the duration-PnL correlation as the dominant inefficiency; (round 2 MAJOR on max_extend cap truncating long-hold tail) widened cap to 1800s (30min).

---

## Implementation Decisions

**Class structure**: Subclass of `ExecAlgorithm`, named `PtgPcR3Algorithm`. Inherits the position-cap=1 logic from position-tier-gate verbatim, then adds the winners-run skip-close gate on top.

**Subscribe to quote ticks in on_start()**: Need real-time quote tick updates so cache.quote_tick(instrument_id) returns fresh prices for unrealized_pnl computation. Without subscribe_quote_ticks(), cache may be stale.

**Tracking which instrument**: The exec algo doesn't know the instrument_id at on_start time (orders arrive in on_order). Solution: subscribe lazily — on the FIRST on_order call, if not yet subscribed, call subscribe_quote_ticks(order.instrument_id). Track subscribed_instruments as a set to avoid double-subscription.

**Unrealized PnL computation**: For a LONG position (side=LONG): unrealized_pnl_per_unit = current_bid - avg_px_open. For a SHORT position (side=SHORT): unrealized_pnl_per_unit = avg_px_open - current_ask. We need the CONSERVATIVE valuation (where could we actually close to) - bid for selling, ask for buying. If position.side enum is LONG, we'd sell to close (use bid). If position.side is SHORT, we'd buy to close (use ask).

**Quote staleness fallback**: If cache.quote_tick(instrument_id) returns None or quote.ts_event is significantly older than current ts, treat as "no quote available" — SUBMIT the CLOSE unchanged (safe default: don't skip when we can't measure profitability).

**Position lookup**: cache.positions_open(instrument_id=order.instrument_id) returns a list. Empty = flat (should not occur for a CLOSE since strategy only emits CLOSE when position exists). Take the first/only one (netting OMS).

**Max extend seconds default**: 1800s = 30min. Wide enough to capture the empirical 60-600s tail. Final safety: when the strategy issues a close at end-of-session intraday-flat, that CLOSE arrives via on_order; if the position is still in green at that moment, we'd skip it, which is BAD (would leave position open overnight). Mitigation: max_extend_ns acts as the safety here. Set to 1800s which is well within a 6.5-hour session. If a position has been held 30min and is still in green, force-close it.

**Reduce-only semantics**: CLOSE orders have is_reduce_only=True. We use this exact field to detect closes vs opens.

**No new orders**: The mechanism only SKIPS (does not submit) or SUBMITS. No spawn_*, no manual order construction, no contingent stops. Simplest possible implementation.

**Concerns**:
- **Selection bias**: the duration-PnL correlation in base data is conditional on oracle-confirmed direction (long-hold positions are oracle-validated by sustained direction). Force-extending a position where oracle just SIGNALED reversal is a different population. We mitigate via conditioning on unrealized_pnl > 0 (path evidence) but this is the dominant scientific risk.
- **Missed reversal opportunity cost**: when we skip a CLOSE, the oracle's same-ts_init OPEN gets blocked by cap=1 — we don't take the reversal bet. If the oracle is right about the reversal, we forgo that gain.
- **Quote staleness**: if quote_tick subscription doesn't deliver real-time updates in the deterministic replay, the unrealized_pnl computation is stale. Fallback: don't skip when quote unavailable.
- **End-of-session**: relies on strategy issuing a CLOSE within max_extend_ns of any held position; otherwise position could linger. The 1800s cap provides safety.

---

## Backtest Observations

**Metrics (train window, 12 dates)**:

| Metric | ptg-pc-r3 | position-tier-gate (base) | Delta |
|---|---|---|---|
| realized_pnl | $764.25 | $4,262.50 | **-82.07%** |
| mean_slippage | 0.0 | 0.0 | 0.00% |
| sharpe_ratio | 16.82 | 17.62 | -0.80 |
| max_drawdown_pct | -0.74% | -1.73% | -0.99pp (improved) |
| win_rate | 20.63% | 37.20% | -16.57pp |
| trade_count | 10,422 | 90,433 | -88.5% |

**Per-date PnL deltas vs base**: -121.00 (3/8), -789.75 (3/9), -537.75 (3/10), -314.25 (3/11), -240.25 (3/12), -33.00 (3/13), -0.75 (3/15), +31.50 (3/16), -45.00 (3/17), -306.75 (3/18), -711.25 (3/19), -430.00 (3/20). Loses on 11/12 dates.

**What drove improvement**: Nothing drove an improvement vs base. The only positives are (a) lower drawdown (mechanical: with 88% fewer trades and 82% less PnL exposure, there is just less to draw down), and (b) Sharpe stayed near base only because both numerator (mean) and denominator (std) shrank proportionally. The +$31.50 day (3/16) on an otherwise-losing date was incidental — the skip-close happened to dodge a few losers.

**What underperformed**: Everything. The trade_count collapse from 90,433 to 10,422 is the signature: when a CLOSE is in-the-green and held, the cap=1 OPEN gate then blocks every subsequent oracle signal until either (a) the position drifts red and the next CLOSE fires, (b) max_extend (30min) trips, or (c) end-of-session forced flat. Empirically (a) takes a long time — minutes per held winner — and during that hold window the algorithm is **deaf to oracle signals**. The base oracle generates many fast small-PnL trades; the hypothesis traded that volume for a much smaller number of held positions that, on net, did NOT capture the duration-PnL tail the hypothesis predicted.

**Hypothesis verdict**: **FAILED, decisively.** The hypothesis predicted that conditioning on `unrealized_pnl > 0 at the CLOSE moment` would convert short noisy positions into longer-hold profitable ones, exploiting the empirically measured duration-PnL correlation in base data. The backtest contradicts this prediction. The Criticizer's Round 1 warning about **selection bias** (duration-PnL correlation in base data was conditional on oracle-confirmed direction, not on arbitrary path-evolution evidence) was the dominant unresolved risk and it was correct. The path-evolution proxy (`unrealized_pnl > 0`) does not stand in for oracle confirmation. The oracle's CLOSE signal IS the oracle's information — overriding it with a mechanical path-evolution filter discards exactly the signal the strategy relies on. The mechanism converted a high-Sharpe many-trades strategy into a low-volume strategy that underperforms on net P&L by 82%.

**Suggested next attempt**: The duration-PnL correlation in base data is real but **caused by** oracle confidence, not by holding duration per se. A future run should target the oracle's REVERSAL signal directly: instead of overriding CLOSE on profitable positions, only override CLOSE when there is independent evidence (orderflow imbalance, recent micro-trend in same direction as the position) that the current move has momentum the oracle's 30-second forecast is under-weighting. The mechanism should be FRACTIONAL (e.g. close half the position on the CLOSE signal, hold the rest with a trailing condition) rather than binary skip/submit — this preserves capture of the oracle's directional signal while letting a portion ride the tail. Alternatively, pivot to OPEN-side filtering with a strict bar (e.g. only OPEN when oracle signal AND a confirming microstructure feature align), which retains the cap=1 framework but raises selectivity on entry rather than gating exit.
