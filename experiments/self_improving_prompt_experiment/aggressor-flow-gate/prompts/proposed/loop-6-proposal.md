# Hypothesis Generation Method — base_algo=aggressor-flow-gate (loop 7+)

You are an execution-algorithm researcher. Produce ONE hypothesis for `<algo-id>` that you believe will beat `<base_algo>` on the train window's realized P&L without meaningfully worse slippage.

**Program-database state**: L5 (`sip-afg-l5`, +3.30%) is the running best. It introduced a graduated post-skip cascade (`_skip_streak` with `relaxation_factor=1.5`). L6 attempted single-axis offline calibration of `relaxation_factor` (1.5 → 2.5) using a DBN replay with worst-case adverse side at every arrival. Result: trade_count moved +0.92% (predicted [82k, 86k]); falsifier triggered. The offline EDA used a counterfactual side-assignment; the live algorithm picks oracle-driven sides, so the live firing rate was far below the offline 0.60. **Offline replays of a mechanism in isolation cannot predict live firing rate.**

**The failure mode this method targets**: parameter calibration off offline DBN replays fails when the protocol is structurally biased vs the live execution path. The fix is to measure firing rate the same way the algorithm experiences it — by **instrumenting the live algorithm**, running it as-is on train dates, and reading counter values back.

This method is **live-instrumentation calibration**. You do not invent a new mechanism. You take the kept algorithm's structural axis and calibrate ONE numeric parameter using counters embedded in the algorithm during an actual backtest.

## Step 1 — Read context

Read in order:
1. `experiments/self_improving_prompt_experiment/<base_algo>/program_database.json` — identify `most_recent_kept_loop`; call its algo id `<kept_algo>`.
2. `execution_algos/<base_algo>/execution_algorithm.py` and `NOTES.md`.
3. `execution_algos/<kept_algo>/execution_algorithm.py` and `NOTES.md`.
4. `execution_algos/<base_algo>/results/backtest-results.json` and `execution_algos/<kept_algo>/results/backtest-results.json`.
5. `research/config.yaml` for `data_window.train` and `execution_constraints`.

Do not read other entries in `execution_algos/` or other experiments.

Write a 4–6 line summary: kept algorithm's structural change, parameters it introduced, which were uncalibrated.

## Step 2 — Enumerate uncalibrated parameters and pick ONE

Table every numeric parameter `<kept_algo>` introduced or changed vs `<base_algo>`: name + current value, what it controls, and yes/no — calibrated by a live measurement (not offline EDA, not intuition).

**Selection rule**: pick the parameter whose value most directly governs the per-arrival firing rate of the kept algorithm's new mechanism. If every parameter has been live-calibrated, write `## ESCALATION (terminal): no live-uncalibrated parameter to refine` and stop.

Write the table and your choice to `execution_algos/<algo-id>/NOTES.md → ## Inherited Parameters` and `## Calibration Target`.

## Step 3 — Define live counters

Define counters to embed in the algorithm. Protocol is rigid:

- Counters MUST be incremented inside the actual `on_order` path at the exact branch the parameter controls. No re-implementation of the mechanism elsewhere.
- Count BOTH legs of the firing-rate ratio:
  - **numerator**: number of times the branch fires (e.g. relaxed gate skips at streak==1).
  - **denominator**: number of times the branch is *eligible* (e.g. streak==1 arrivals reached the gate, excluding reduce-only / warm-up).
- Counters MUST be persisted at end-of-run. Use `self.log.info` with a structured prefix (e.g. `LIVE_CAL:`) so they can be grep'd from backtest logs. Verify log structure by reading any prior run dir before instrumenting (do NOT modify the engine).
- Also log the parameter-relevant signal value (e.g. `|net_flow|`) at each eligibility moment so the empirical distribution can be reconstructed from logs.
- No other code paths. Probe MUST be behaviorally identical to `<kept_algo>` — same defaults, same logic, only `+=1` increments and log lines added. Diff the two files side-by-side before running.

Create `execution_algos/<algo-id>-probe/`. Register in `execution_algos/__init__.py`. Write counter definitions to `NOTES.md → ## Live Counters`.

## Step 4 — Measure on train data

Run `python scripts/run_research_backtest.py --algo <algo-id>-probe --use-cached-baseline` over the full train window. Parse logs to extract counter totals across all 12 train dates.

Compute:
- `live_firing_rate_current = numerator / denominator` at the current parameter value.
- Empirical signal-value distribution (median, p25, p75, p90) from logged eligibility moments.
- Calibrated parameter value that would shift `live_firing_rate` to a pre-committed target rate (single number in [0.05, 0.50]; justify in one sentence pre-measurement).

Write to `NOTES.md → ## Live Measurement`: 12-date counter totals, live current firing rate, signal distribution, calibrated value.

**Survival criteria (both hard)**:
1. **Magnitude**: if `|calibrated - current| / current < 10%`, write `## ESCALATION (terminal): parameter already live-calibrated within 10%` and stop.
2. **Counter sanity**: if `denominator < 1000` across all 12 dates, write `## ESCALATION (terminal): branch fires too rarely to calibrate` and stop.

## Step 5 — Write the final hypothesis

The shipped `<algo-id>` is a clean copy of `<kept_algo>` with the new parameter value — NOT the probe (no counter code in the shipped algo).

Write to `NOTES.md → ## Hypothesis (final)`:
- **Mechanism** — "Identical to `<kept_algo>` except parameter X changes from V_old to V_new."
- **Inefficiency exploited** — gap between live current firing rate and target rate, both cited from Step 4.
- **Why it survives costs** — constraints preserved (quantity invariant, top_of_book_only, participation_cap, intraday_flat). No other parameter changes.
- **Quantitative anchor** — new value with Step 4 live-counter number.
- **Predicted outcome** — directions for realized_pnl, mean_slippage, trade_count, sharpe_ratio. The trade_count delta MUST be derived as `(target_firing_rate - live_firing_rate_current) × denominator_total`, using the same denominator the counter recorded. No scaling from subsets.
- **Falsifier** — ONE backtest result. Default: "live trade_count delta vs `<kept_algo>` is less than 0.5× the prediction from `(Δfiring_rate × denominator)` → the parameter change did not move the live firing rate the way the counter-derived projection implied, indicating non-linear cascade feedback the live counter did not isolate."

## Boundaries (hard)

- ONE parameter change. No stacking.
- No new structural mechanisms. Structure IS `<kept_algo>`'s structure.
- New parameter value MUST come from Step 4 live counters — no offline DBN replays, no armchair numbers.
- Probe MUST be behaviorally identical to `<kept_algo>` (same defaults, only counter increments and log lines added). Verify by reading both files before running.
- Each NOTES.md section under ~400 words.
- Do NOT read test-window dates — train only.
- Do NOT read other experiments or other tracks' algo code; only `execution_algos/<base_algo>/`, `execution_algos/<kept_algo>/`, `execution_algos/<algo-id>/`, and `execution_algos/<algo-id>-probe/`.
- If Step 2 or Step 4 hits an escalation branch, STOP — do not invent a structural change.
- On ambiguity, pick the more conservative interpretation (smaller parameter shift, narrower claim).
