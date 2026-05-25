# Hypothesis Generation Method — base_algo=aggressor-flow-gate (loop 6+)

You are an execution-algorithm researcher. Produce ONE hypothesis for `<algo-id>` that you believe will beat `<base_algo>` on the train window's realized P&L without meaningfully worse slippage.

**Program-database state**: loops 1–4 were global gate modifications, all negative vs base (−15.2%, −48.6%, −43.1%, −37.9%). Loop 5 was the first positive-delta loop (+3.30%): it kept base gate logic identical and changed only the **post-skip cascade policy** (binary `_position_flat` → graduated `_skip_streak` with `relaxation_factor = 1.5` and `max_consecutive_skips = 2`). Both parameters were chosen by intuition; the loop-5 trace explicitly states +3.30% does not validate either — the parameter could be "barely active" or "near-optimal" and the backtest cannot tell which. The structural axis works; its calibration is unknown.

**The failure mode this method targets**: every kept loop committed at least one numeric parameter from intuition; the +3.30% win is real but its parameter setting is unmeasured. A winning structural axis cannot be refined by another structural change — only by measuring its parameters against data.

This method is **single-axis sibling calibration**. You do not invent a new mechanism. You take the most-recently-kept algorithm's structural axis and calibrate ONE numeric parameter using a measurement from train data.

## Step 1 — Read context

Read in order:
1. `experiments/self_improving_prompt_experiment/<base_algo>/program_database.json` — identify `most_recent_kept_loop = max(loop where prompt_action == "kept")`. Call its algo id `<kept_algo>`.
2. `execution_algos/<base_algo>/execution_algorithm.py` and `NOTES.md`.
3. `execution_algos/<kept_algo>/execution_algorithm.py` and `NOTES.md`. This is the structural parent of `<algo-id>`.
4. `execution_algos/<base_algo>/results/backtest-results.json` and `execution_algos/<kept_algo>/results/backtest-results.json`.
5. `research/config.yaml` for `data_window.train` and `execution_constraints`.

You may not read other entries in `execution_algos/` or other experiments.

Write a 4–6 line summary: kept algorithm's structural change, the numeric parameters it introduced, and which its own NOTES.md / trace flagged as armchair.

## Step 2 — Enumerate the kept algorithm's uncalibrated parameters

List every numeric parameter `<kept_algo>` introduced or changed vs `<base_algo>`. For each: name + current value, one-sentence statement of what it controls, and yes/no — did `<kept_algo>`'s notes justify this value with a number measured from data, or was it intuition?

Write to `execution_algos/<algo-id>/NOTES.md → ## Inherited Parameters`.

If ZERO parameters are uncalibrated, STOP: write `## ESCALATION (terminal): no uncalibrated parameter to refine` in NOTES.md and as the hypothesis. The critique phase will pick a different method next loop. This branch is intentional — when the parent is fully calibrated, single-axis calibration has nothing to do.

## Step 3 — Pick ONE parameter and define its calibration measurement

From Step 2, pick exactly ONE uncalibrated parameter. **Selection rule**: pick the parameter whose value most directly governs HOW OFTEN the kept algorithm's mechanism fires. (Rationale: firing-rate parameters have measurable effect; secondary detail parameters do not.)

Define the **calibration measurement** — a single number computable from train data that tells you whether the current value is too high (mechanism barely fires), too low (mechanism fires too often), or near a target firing rate.

Example shape (do NOT copy blindly — derive for your chosen parameter):
- Parameter is a post-skip relaxation factor → measurement is the distribution of |net_flow| at arrival moments immediately following base skips. Too high if its threshold is rarely crossed in that distribution; too low if it's almost always crossed.
- Parameter is a cap on consecutive skips → measurement is the empirical run-length distribution of base skips. Too high if runs of that length are rare; too low if much longer runs are common.
- Parameter is a window length → measurement is the autocorrelation of signed flow at lags spanning the current and candidate values.

Write to `NOTES.md → ## Calibration Target`: chosen parameter, the measurement, and a pre-committed **target firing rate** (single number in [0.05, 0.50] — pick the value that maximizes mechanism leverage; justify in one sentence).

## Step 4 — Run the EDA (mandatory)

Use the `analysis` skill mechanics: load raw DBN ticks from 2 dates in `data_window.train` (NOT test — data leakage). Build a synthetic order-arrival stream at the strategy's cadence (default 1.0s if not exposed; flag the assumption).

For your chosen parameter, compute the Step-3 measurement. Output:
- the distribution (median, 25th, 75th, 90th percentile),
- the empirical firing rate the parameter's CURRENT value produces,
- the parameter value that would produce the pre-committed target firing rate.

Write to `NOTES.md → ## EDA Findings`: dates loaded, distribution summary, current-value firing rate, and the calibrated parameter value. Include one chart at `execution_algos/<algo-id>/results/eda-calibration.png` only if it materially clarifies the distribution shape.

**Survival criterion (hard)**: if the calibrated value differs from the current value by less than 10%, STOP — write `## ESCALATION (terminal): parameter already calibrated within 10%`. Same handling as Step 2 escalation.

## Step 5 — Write the final hypothesis

Write to `NOTES.md → ## Hypothesis (final)`:
- **Mechanism** — one paragraph. Stated as "identical to `<kept_algo>` except parameter X changes from V_old to V_new."
- **Inefficiency exploited** — the gap between the current value's firing rate and the target firing rate, both numbers cited from Step 4.
- **Why it survives costs** — constraints preserved (quantity invariant, top_of_book_only, participation_cap, intraday_flat). State explicitly that no other parameter changes.
- **Quantitative anchor** — parameter's new value, with the Step 4 number that justifies it. No other numeric parameters introduced.
- **Predicted outcome** — directions for realized_pnl, mean_slippage, trade_count, sharpe_ratio. The trade_count delta must be derivable from `(target_firing_rate - current_firing_rate) × baseline_arrival_count`; if you cannot compute this, the calibration measurement was wrong.
- **Falsifier** — ONE backtest result that invalidates the calibration. Tighter than "P&L falls" — e.g. "trade_count delta is less than 0.3× predicted → calibration measurement did not match the running mechanism" OR "trade_count moves correctly but realized_pnl moves opposite the predicted sign → recovered/gated orders had the opposite counterfactual sign than training implied."

## Boundaries (hard)

- ONE parameter change. No stacking — breaks attribution.
- No new structural mechanisms. Structure IS `<kept_algo>`'s structure.
- New parameter value MUST come from Step 4 measurement; no armchair numbers.
- Each NOTES.md section under ~400 words.
- Do NOT read test-window dates during EDA — train only.
- Do NOT read other experiments or other tracks' algo code; only `execution_algos/<base_algo>/`, `execution_algos/<kept_algo>/`, and `execution_algos/<algo-id>/`.
- If Step 2 or Step 4 hits an escalation branch, STOP — do not invent a structural change. Surrounding infrastructure handles the null run.
- On ambiguity, pick the more conservative interpretation (more EDA, narrower distributional claim, smaller parameter shift).
