# Hypothesis Generation Method — base_algo=position-tier-gate

You are an execution-algorithm researcher. Produce one concrete hypothesis for a new execution algorithm at `execution_algos/<algo-id>/` that you predict will achieve higher realized P&L than `<base_algo>` on the train window, without making slippage substantially worse.

Execution constraints (the engine does NOT enforce them; your algorithm must):
- **Quantity invariant**: `sum(child_fills) ≤ parent.quantity`. Never inflate.
- **top_of_book_only**: fill at `ask_px` (buys) or `bid_px` (sells). Never walk the book.
- **participation_cap**: per-tick `order_size ≤ floor(participation_cap × top_of_book_qty)`. Read `participation_cap` from `research/config.yaml → execution_constraints`.
- **intraday_flat**: close all positions before session end.

This method is **propose → counterfactual probe → commit**. The probe is mandatory and gates implementation. Loop 2 lesson: validating the targeted subset is negative-EV *in the base's realized stream* is NOT the same as validating *that skipping it improves aggregate PnL*. Trades you skip change the cache state seen by every subsequent order. The probe must measure the actual aggregate outcome, not the in-isolation outcome.

---

## Step 1 — Read the base mechanism

Read `execution_algos/<base_algo>/execution_algorithm.py` and `execution_algos/<base_algo>/NOTES.md`. Identify in one sentence the *event class* in the order stream that the base conditions on (which field, which value, which timing).

## Step 2 — Identify ONE plausible weakness

Identify one regime where the base's gate either over-skips good trades or fails to skip bad ones. Pick the weakness with the highest plausible frequency, not the most elegant one. Write it in one sentence: *"In regime X, the base does Y; if instead it did Z, expected outcome is W."*

## Step 3 — Propose ONE concrete modification

Propose ONE modification — a different gate input, a parameter retune, or a guard layered on top. State it in mechanism terms (what the new `on_order()` branch does, conditioned on what). Verify constraints (quantity invariant, top-of-book, participation_cap, intraday_flat) trivially hold.

## Step 4 — MANDATORY counterfactual probe (the gate)

The probe is a **one-day backtest with the proposed gate active** on a single train date. Goal: surface the aggregate-vs-isolation gap before you commit to full evaluation.

**4a. Choose one probe date.** Pick the date from `config.yaml → data_window.train` with the highest expected event-class density. If you cannot rank dates, default to the median date by trade volume in the base's cached per-date `metrics.json`. State date and reason in one line.

**4b. Predict three quantities — commit before running the probe.**
  - `N_fire`: how many times per day the new branch will fire (skip an order the base submitted).
  - `delta_pnl_isolated_usd`: sum of `realized_pnl` over the skipped positions, as measured in the base's cached `positions.csv` for the probe date. The "in-isolation" estimate.
  - `delta_pnl_counterfactual_usd`: your prediction of how aggregate PnL on the probe date will change when the gate is active. May equal `delta_pnl_isolated_usd` only if you can give one sentence of mechanism reasoning for why subsequent orders are unaffected. If the modification skips OPENs that pair with later CLOSEs, or changes cache state visible to later `on_order()` invocations, the two should differ — state in which direction and roughly by how much.

"Many" or "approximately" is not allowed. Three numbers.

**4c. Run the probe.** Write `execution_algos/<algo-id>/execution_algorithm.py` with the proposed gate active. Run:

```
python scripts/run_research_backtest.py --algo <algo-id> --use-cached-baseline --dates <YYYYMMDD>
```

Read `execution_algos/<algo-id>/results/<YYYYMMDD>/metrics.json` and `execution_algos/<base_algo>/results/<YYYYMMDD>/metrics.json`. Record:
  - `actual_fire`: number of skips actually performed (count via log line, or by `base_trade_count − algo_trade_count` if your gate skips OPENs 1:1).
  - `actual_delta_pnl_usd`: `algo.realized_pnl − base.realized_pnl` on the probe date.

**4d. Apply the gate.** Compute `counterfactual_error = actual_delta_pnl_usd − delta_pnl_counterfactual_usd` and `isolation_error = actual_delta_pnl_usd − delta_pnl_isolated_usd`.
  - `actual_delta_pnl_usd > 0`: hypothesis supported on the probe date. Proceed to step 5.
  - `actual_delta_pnl_usd ≤ 0` AND `delta_pnl_counterfactual_usd > 0`: your counterfactual prediction was wrong. Do NOT proceed. Return to step 2 with a different weakness, or to step 3 with a modification whose counterfactual you can reason about.
  - `actual_delta_pnl_usd ≤ 0` AND `delta_pnl_counterfactual_usd ≤ 0`: you correctly predicted the modification would not improve PnL. Return to step 3 — the proposal is dead even though your model of it was honest.
  - `actual_fire == 0`: event class is empty in execution context. Identity transform. Return to step 2.

**4e. One-date variance caveat.** A winning probe date does NOT guarantee winning across the 12-date window. Record explicitly in your trace: "Probe date <DATE> was chosen because <reason>. I am extrapolating from one date and accept the 12-date aggregate may diverge." Do NOT run the probe on multiple dates to game this — the probe is a one-date gate, not full evaluation.

Write the probe result into `execution_algos/<algo-id>/NOTES.md` under "Counterfactual probe" with: probe date, the three predictions, `actual_fire`, `actual_delta_pnl_usd`, the two error sizes, and the pass/fail decision.

## Step 5 — State expected direction AND magnitude

Only after step 4 passes:
  - `realized_pnl`: direction (↑ or ↓ vs base) AND magnitude band, tied explicitly to `actual_delta_pnl_usd × 12` (rough extrapolation) and to `delta_pnl_counterfactual_usd × 12`. State which extrapolation you trust more and why.
  - `mean_slippage`: direction with one sentence justifying why book-walking / participation-cap behavior is unchanged.
  - `trade_count`: direction tied to `actual_fire × 12`.

## Step 6 — Finalize

The probe in step 4c already produced the algorithm code. Verify the factory is registered in `execution_algos/__init__.py`. Make no further mechanism changes — if you found a flaw during the probe, the answer is to abort and return to step 2, not to patch around it.

---

## Boundaries

- **One modification per loop.** No bundling. If step 4 disqualifies, drop the proposal and pick a different weakness — do not patch around the failure by stacking changes.
- **Replace `<algo-id>` with `sip-ptg-l<N>` and `<base_algo>` with the literal id** in all paths.
- **Do not read `strategies/`** or any execution algo other than `execution_algos/<base_algo>/` and `execution_algos/<algo-id>/`.
- **Train window only.** Use `config.yaml → data_window.train`.
- The honesty rules in `OBJECTIVE.md §8` apply: report `actual_fire`, `actual_delta_pnl_usd`, and the two error sizes whether or not they match your predictions. The probe's value is in the surprise it produces; suppressing it wastes the loop.
- **Probe is one date, evaluation is twelve.** A passing probe is a green light, not a verdict. The 12-date aggregate may still falsify — and that's fine; the lesson then is about what aspect of the probe date was unrepresentative, not whether the method worked.
