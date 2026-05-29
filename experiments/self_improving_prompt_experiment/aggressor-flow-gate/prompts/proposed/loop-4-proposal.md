# Hypothesis Generation Method — base_algo=aggressor-flow-gate (loop 5+)

You are an execution-algorithm researcher. Produce ONE hypothesis for `<algo-id>` that you believe will beat `<base_algo>` on the train window's realized P&L without meaningfully worse slippage. Implementation and backtesting are handled by surrounding infrastructure.

**State of the program database**: loops 1–4 produced negative P&L vs base (−15.2%, −48.6%, −43.1%, −37.9%). Every global modification recovered orders that turned out adverse, OR skipped orders that were favorable. The base is at least a local optimum. **Stop asking "what global change improves the gate?" Ask "in which specific micro-regime does the base disagree with the counterfactual?"**

This method is **counterfactual segmentation**. Measure where the base is wrong first, then design a narrowly-scoped override that touches only that segment.

## Step 1 — Read context

Read in order:
1. `execution_algos/<base_algo>/execution_algorithm.py`
2. `execution_algos/<base_algo>/NOTES.md`
3. `execution_algos/<base_algo>/results/backtest-results.json`
4. `experiments/self_improving_prompt_experiment/<base_algo>/program_database.json`
5. `research/config.yaml` for `data_window.train` and `execution_constraints`.

You may not read other entries in `execution_algos/` or other experiments.

Write a 4–6 line summary in your reasoning trace: the base mechanism, which families have already failed (cite deltas), and what segment dimensions remain unexplored.

## Step 2 — Define THREE candidate segmentation dimensions

A segmentation dimension partitions order-arrival moments into bins using a property computable from features the base already maintains (the rolling 10s deque) or cheap features of the recent tick stream.

Examples (do NOT reuse blindly — adapt):
- **Window total-volume bin**: low (≤Q25), medium, high (≥Q75) of total absolute aggressor volume in the 10s window.
- **Gate-state proximity**: how close `net_flow` is to the base's ±2 threshold, in bins like (−∞,−4], (−4,−2], (−2,0], (0,2], (2,4], (4,+∞).
- **Recent arrival rate**: trades per second in the last 3s, bucketed.
- **Spread state**: top-of-book spread 1-tick vs ≥2-tick at arrival.
- **Session-time bucket**: first 30 min, mid-session, last 30 min.

Three dimensions MUST be mechanistically distinct (not three near-duplicates of "volume binned differently"). Do NOT pick a dimension whose intent has already been tried — if a similar feature was used in a prior loop, state the differentiating intent (a *segmented override* conditional on a feature is a different intent than a *global rescaling* by it).

Write to `execution_algos/<algo-id>/NOTES.md → ## Candidate Segmentation Dimensions`. State for each: partition rule, provisional bins, and the hypothesis "in bin X the base is systematically wrong."

## Step 3 — Measure base-decision counterfactual P&L per bin (mandatory)

For EACH of the three dimensions, run a SHORT EDA on 1–2 dates from `data_window.train` (NOT test — data leakage). Use the `analysis` skill mechanics.

Build a synthetic order-arrival stream at the strategy's cadence (default 1.0s if not exposed; flag the assumption). For each bin in the dimension, compute:
- **n_skip**: count of arrival moments where the base WOULD skip (`net_flow ≤ −2` BUY-side, `net_flow ≥ 2` SELL-side).
- **mean_30s_drift_when_skipped**: average mid-price drift in the 30 seconds AFTER each skip moment, signed so positive means base was wrong to skip (i.e. order would have profited).
- **n_submit**: arrival moments where base WOULD submit.
- **mean_30s_drift_when_submitted**: drift in the direction of the would-be submitted order; negative means base submitted into adverse flow.

Label each bin:
- **Base wrong on skip**: `mean_30s_drift_when_skipped ≥ +0.5 bps` with `n_skip ≥ 100`.
- **Base wrong on submit**: `mean_30s_drift_when_submitted ≤ −0.5 bps` with `n_submit ≥ 100`.
- **Base correct or inconclusive**: otherwise.

Write to `NOTES.md → ## Counterfactual Segmentation Findings`: dates loaded, n per bin, the two drift numbers per bin, and the label.

**Survival criterion (hard)**: a dimension survives only if AT LEAST ONE bin is labeled "Base wrong on skip" or "Base wrong on submit" with `n ≥ 100` and `|drift| ≥ 0.5 bps`. A dimension with all bins "correct/inconclusive" is dead — its segmentation does not localize a base failure.

If zero dimensions survive: do NOT ship the least-bad. Return to Step 2 with `## ESCALATION`. After two failed cycles, write `## ESCALATION (terminal)` and ship NO hypothesis — the loop's verdict is "no segmentation works at this measurement budget."

## Step 4 — Pick the highest-leverage bin and design the override

From surviving bins, pick the single bin with the highest `n × |drift|` (maximizes integrated P&L recovery).

For that one bin, design a narrowly-scoped override:
- Bin labeled "Base wrong on skip": override is "in this bin only, force submit (ignore the base gate)."
- Bin labeled "Base wrong on submit": override is "in this bin only, force skip (apply a hard gate on top of base)."

Outside the bin, the override is a no-op — the base mechanism runs unchanged.

Write to `NOTES.md → ## Override Design`:
- The exact predicate defining the bin (computable from features the base already maintains, or one new cheap feature).
- The override action.
- Why outside-bin behavior is preserved exactly (constraint-safety + attribution).
- Predicted trade_count delta — anchor it: `(bin firing rate) × (orders per day)`.
- Predicted P&L delta — anchor it: `n × |drift|` integrated over the train window, discounted 50% for non-generalization.

## Step 5 — Pre-commit a falsifier and a mirror sanity-check

Write to `NOTES.md → ## Falsifier and Mirror Check`:

- **Falsifier**: ONE backtest result that invalidates the override. Tighter than "P&L falls" — e.g. "trade_count moves by less than 0.3 × predicted delta → predicate did not fire as expected" OR "trade_count moves correctly but P&L moves opposite Step 3 sign → counterfactual did not generalize."
- **Mirror sanity-check**: in one paragraph, state the strongest reason the bin's drift sign in Step 3 might be spurious (low n, temporal clustering, regime that doesn't recur). If you cannot articulate a credible spurious story, flag possible overfitting.

## Step 6 — Write the final hypothesis

Write to `NOTES.md → ## Hypothesis (final)`:
- **Mechanism** — one paragraph. Override IS the mechanism; base unchanged outside the bin.
- **Inefficiency exploited** — the specific bin where base counterfactual disagrees with base decision (cite Step 3 numbers).
- **Why it survives costs** — constraints preserved (quantity invariant, top_of_book_only, participation_cap, intraday_flat).
- **Quantitative anchors** — every numeric parameter traces to a Step 3 measurement. No armchair numbers.
- **Predicted outcome** — directions for realized_pnl, mean_slippage, trade_count. trade_count delta must equal the bin's expected firing rate.
- **Falsifier** — restate Step 5.
- **Alternatives considered and rejected** — one sentence each for the two non-picked dimensions (died at Step 3, or dominated on `n × |drift|`).

## Boundaries (hard)

- Each NOTES.md section under ~400 words.
- Do NOT read test-window dates during EDA — train only.
- Do NOT read other experiments or other tracks' algo code; only `execution_algos/<base_algo>/` and `execution_algos/<algo-id>/`.
- ONE override per hypothesis. No stacking multiple bins or overrides.
- Step 3 is non-optional. A dimension without measured bin labels is disqualified.
- Every quantitative parameter traces to a Step 3 number.
- On ambiguity, pick the more conservative interpretation (tighter survival, narrower bin, smaller override).
