# Algorithm Notes: position-tier-vol-regime-gate

## Hypothesis

**Mechanism**: Stack a vol-regime gate on top of iter-2 (`position-tier-imbalance-ema-gate`). On every quote tick, compute a short-window realized volatility (stdev of mid-price log-returns over the last `vol_window` quote ticks). Maintain a long-window baseline median of that short-window vol (last `baseline_window` short-vol observations). For an OPEN-leg order, if the current short-window vol exceeds `vol_multiplier * baseline_median_vol`, SKIP. All other gates inherited verbatim from iter-2: position cap = 1 (cascade protection), EMA-imbalance gate (alpha=0.30, threshold=0.40, min_total_size=2), reduce-only fast-path (intraday_flat).

**Inefficiency exploited**: The oracle's effective forecast horizon is 30 s; its directional accuracy degrades when the mid-price moves more in 30 s than the signal's edge can pay for. Empirically that condition coincides with **bursts of short-window realized vol** — adverse-selection regimes where the market is pricing in news/order flow faster than the oracle's noisy signal can lead. Iter-2's EMA-imbalance gate filters microstructure noise at the *single-tick* level; this gate filters at the *short-horizon regime* level — a structurally different axis, exactly as iter-4 recommended.

**Why it survives costs**: Slippage and commissions are 0.0 in the current fill model (see research/NOTES.md 2026-04-30), so the gate's value lives entirely in P&L attribution: each skipped open is a trade that does not get to lose in a high-vol regime. The two reduce-only flat-out passes (intraday_flat) always execute, so the strategy's risk-flattening behaviour is preserved. Net effect: lower trade count, higher per-trade expectancy in the surviving entries.

**Builds on**: `position-tier-imbalance-ema-gate` (iter-2 best PASS, pnl=$4503.25 / 62220 trades / sharpe=20.79 on 11 train dates). The vol-regime gate is the ONE targeted change vs iter-2; all other components carry over verbatim.

**Alternatives considered**:
- *Time-of-day filter* (skip near session open/close). Rejected for this iteration because UTC↔CME session calendar logic adds an extra dependency that's brittle across DST and the train window straddles the US DST transition (2026-03-08); a pure data-driven vol filter is simpler and more honest.
- *Reduce-only delayed execution*. Rejected because the intraday_flat constraint plus the current zero-slippage fill model means delaying the close has near-zero expected upside but real risk of missing the session boundary.
- *Different vol estimator (Parkinson, Garman-Klass, OFI-based)*. Rejected as overengineering for a first-pass; stdev of mid-log-returns is the simplest realized-vol read.

---

## Implementation Decisions

- **Vol estimator**: stdev of consecutive mid-price log returns over a rolling deque of length `vol_window` (default 60 quote ticks, ≈ ~6-30 seconds of MES top-of-book depending on quote intensity). Mid-price = (bid + ask) / 2 from the same quote tick. Log returns dropped when either side has price ≤ 0 (defensive).
- **Baseline**: rolling median (deque length `baseline_window`, default 300 short-vol observations) of recent short-vol readings — median is robust to vol spikes that we explicitly want to gate against (a mean would self-defeat the gate).
- **Threshold**: `vol_multiplier` = 1.5 (default). A short-window vol that is 1.5× its own rolling baseline median is empirically a "noisy regime" but not so extreme it skips most of the day's trades. This single param can be tuned in a future iteration if it proves too tight/loose.
- **Warm-up**: until `len(vol_history) >= min_baseline_window` (default 30 short-vol observations), the gate does NOT skip — too little data to estimate the baseline. Effect: first ~30 short-vol windows of each day pass through the gate untouched.
- **No look-ahead bias**: `on_quote_tick(tick)` updates the mid history *first*, then computes the short-window stdev *after* the new return is appended. By the time `on_order(order)` reads `_last_short_vol` and `_baseline_median`, both already reflect only quotes the engine has previously dispatched in chronological order. Order's `ts_init` is strictly ≥ the ts_event of the most recent quote already processed.
- **Quantity invariant**: every parent order is either submitted intact or skipped entirely. The algorithm never spawns or resizes children. `sum(child_fills) ≤ parent.quantity` always; strict equality on every submit, strict zero on every skip.
- **Vol pause on thin books**: short-window vol is only updated when both bid and ask exist and quote total size ≥ min_total_size (2.0, same as iter-2 EMA gate). Below that, the quote is too thin to read a reliable mid.

**Concerns**:
- The gate is calibrated to the train window only. A vol regime entirely outside the train range (e.g., a flash event on a test date) would either skip ~everything (if baseline is low) or skip ~nothing (if baseline is also high) — the per-day baseline reset means each new day re-warms, so this is bounded but not zero risk.
- `vol_multiplier=1.5` is a single-train-window guess; it may not generalize. If iter-5 underperforms iter-2, the right next iteration may be a multiplier sweep, not a different mechanism.
- Reproduces the same `subscribe_quote_ticks`-on-2026-03-19 OOM hazard as iter-1/2/3/4 (see research/NOTES.md 2026-05-23). I will exclude 03-19 from aggregation in advance and document it explicitly.

---

## Backtest Observations

Aggregated across 11 of 12 configured train dates (20260308–20260318, 20260320; 2026-03-19 EXCLUDED — reproduces the same 8 GiB Rust OOM hazard documented at research/NOTES.md 2026-05-23 for every `subscribe_quote_ticks` algo in this family). Confirmed by re-running 20260319 in isolation: identical `memory allocation of 8589934592 bytes failed` signal-6 abort.

**Headline (vs baseline `simple`, N=11 dates):**
- `realized_pnl` = $4377.00 / 59258 trades vs `simple` $43.25 / 111489 trades.
- `vs_baseline_pnl_pct` = **+10020.23%**, far above the +5.0% gate.
- `win_rate` = 39.36% vs simple 35.02% (+4.34pp).
- `trade_count` -46.85% vs baseline.
- `sharpe_ratio` (cross-day annualized, N=11) = 20.67 vs simple 0.17.
- `max_drawdown_pct` = -1.22% vs simple -5.29%.
- `mean_slippage` / commissions: both 0.0 (zero-cost fill model — see research/NOTES.md 2026-04-30).

**Verdict vs canonical baseline gate: PASS** (gate is `vs_baseline_pnl_pct >= +5.0` and slippage non-regression; both met by a wide margin even ignoring the missing 03-19 — at any plausible attribution for that day the +5% threshold cannot flip).

**Honest comparison vs the algorithm this builds on (iter-2 `position-tier-imbalance-ema-gate`, the current best PASS):**

| metric             | iter-2     | iter-5 (vol-regime) | delta vs iter-2     | refinement target          | met? |
|--------------------|-----------:|--------------------:|--------------------:|----------------------------|-----:|
| realized_pnl       | 4503.25    | 4377.00             | **-2.80%**          | min_pnl_delta_pct = +2.0   | NO   |
| sharpe (cross-day) | 20.79      | 20.67               | **-0.12**           | min_sharpe_delta = +0.5    | NO   |
| win_rate           | 0.3929     | 0.3936              | +0.07pp             | min_winrate_delta_pp = +2.0| NO   |
| trade_count        | 62220      | 59258               | -4.76%              | (not a target)             | n/a  |
| max_drawdown_pct   | -0.01210   | -0.01218            | **-0.01pp**         | min_mdd_delta_pp = -1.0    | NO   |

**What drove improvement (vs baseline)**: the inherited position_cap=1 + EMA-imbalance gates carry essentially all of the baseline-relative uplift. The vol-regime gate trimmed trade_count by an additional 4.76% on top of iter-2 but produced a near-zero net P&L delta — every refinement axis in `config.yaml -> refinement.targets` is missed (the pnl axis is a small regression).

**What underperformed**: the vol-regime gate, viewed as a standalone improvement mechanism over iter-2, did not deliver. Most of the entries it skipped beyond what iter-2 already gates appear to be roughly net-neutral; the result is fewer trades for almost the same total P&L (and a small per-trade-expectancy uptick offset by lost positive-EV entries).

**Hypothesis verdict**: PARTIALLY SUPPORTED. The vol-regime filter does remove additional trades (-4.76% trade_count) without breaking the positive-EV character of the strategy (win_rate slightly up; pnl essentially flat). But the hypothesis that high short-window realized vol concentrates oracle adverse selection is NOT borne out at the +5% gate level relative to iter-2 on this train window: the gate either fires too late (after the adverse move has already begun and the position is already established) or fires symmetrically on both adverse and favorable vol bursts. The structural axis ("vol-regime" instead of "imbalance") is, on this data, NOT a meaningfully different signal than the EMA-imbalance gate in terms of which entries it filters out — both seem to filter the same ~few-percent slice of marginal trades.

**Suggested next attempt**: two readings from this iteration suggest different next moves —
1. **Directional vol gate**: skip BUY only when vol is high AND mid has *fallen* over the short window (and analogously for SELL). The current symmetric gate fires whether the market is exploding up or down, which kills good trend-following entries on the favorable side.
2. **Time-of-day filter** (the alternative this iteration ruled out): skip opens in the first 30 minutes after the US equity-cash open (≈ 13:30 UTC during EST / 14:30 UTC during EDT) and last 15 minutes before close. This was deferred because of DST complexity, but a single UTC-window param sweep would address that.
3. (Honest fallback) Acknowledge that within the position_cap=1 + reduce-only-fast-path stack, additional symmetric entry gates have diminishing returns; the next high-leverage axis is probably **sizing or scheduling on the reduce-only leg** (e.g., delayed close when EMA imbalance is favorable to the existing position), which has not been explored.

**Honesty / caveats**:
- 03-19 OOM same as prior iterations; aggregate is N=11/12, identical exclusion footprint to iter-1/2/3/4 so the iter-vs-iter comparison is apples-to-apples.
- Trade count HIGH (59k+), not low-trade-count flagged.
- Cross-day Sharpe of 20.67 has the same caveats as iter-2's 20.79 — both N=11, so std-error on that Sharpe is large; I do NOT claim Sharpe parity is a meaningful win.
- I do NOT claim the vol-regime mechanism is a reliable improvement over iter-2. The honest takeaway is the opposite: PASS vs baseline but a small REGRESSION on the primary refinement axis (pnl) vs the prior algorithm. Future iterations should not stack additional symmetric entry filters within this gate stack.
