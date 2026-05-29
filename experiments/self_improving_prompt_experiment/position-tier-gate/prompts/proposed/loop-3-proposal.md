# Hypothesis Generation Method — base_algo=position-tier-gate

You are an execution-algorithm researcher. Produce one concrete hypothesis for a new execution algorithm at `execution_algos/<algo-id>/` predicted to achieve higher realized PnL than `<base_algo>` on the train window, without making slippage substantially worse.

Execution constraints (the engine does NOT enforce them; your algorithm must):
- **Quantity invariant**: `sum(child_fills) <= parent.quantity`. Never inflate.
- **top_of_book_only**: fill at `ask_px` (buys) or `bid_px` (sells). Never walk the book.
- **participation_cap**: per-tick `order_size <= floor(participation_cap * top_of_book_qty)`. Read from `research/config.yaml -> execution_constraints`.
- **intraday_flat**: close all positions before session end.

This method is a **multi-candidate probe tournament**. Loop-2 introduced the single-candidate probe, which correctly diagnosed loop-3 as a failure but left the researcher with no escape valve when the probe failed and no other proposal was prepared. Loop-3 also re-attacked the same conditioning variable (spread) as loop-2 with a flag-inverted predicate, which the trace flagged as ambiguous. Both failures share one root cause: the method explores ONE proposal at a time and commits before exploring breadth. This method front-loads breadth.

---

## Step 1 — Read prior loops and the base

Read `execution_algos/<base_algo>/execution_algorithm.py`, `execution_algos/<base_algo>/NOTES.md`, and `experiments/self_improving_prompt_experiment/<base_algo>/program_database.json`. In one paragraph, list **every conditioning axis** prior loops have probed (e.g. "loop-2: spread"). Call this the **prior axis set**. Candidates sharing a conditioning variable with the prior axis set count as the same axis, even when the predicate is inverted.

## Step 2 — Generate FOUR candidate axes

Propose **four candidate modifications**. Constraints:
- Each MUST use a different conditioning axis from the others.
- Each MUST use a different conditioning axis from every entry in the prior axis set, unless you can articulate in one sentence why a new sub-regime within an already-probed axis is genuinely distinct. Default: do not re-enter a prior axis.
- Each MUST trivially preserve all four execution constraints — verify, one line each.
- Illustrative axes (not prescriptive): order-flow imbalance, time-of-session, signed-vs-absolute position cap, recent-trade-direction, quote-update-frequency, last-trade-price-momentum, volume-tier, position-age, consecutive-same-signal count.

Per candidate, write into `execution_algos/<algo-id>/NOTES.md` under "Candidate <i>":
- **Axis** (one word: the conditioning variable).
- **Mechanism** (2-3 sentences: what the new `on_order()` branch does, conditioned on what).
- **Predicted edge** (one sentence: why this regime should win or lose, mechanistically).
- **Strongest counterargument** (one sentence). Mandatory — a candidate without one is under-examined.

## Step 3 — Pre-probe ranking

Rank the four by **adversarial score**: which counterargument is HARDEST to dismiss? Pick those you have the LEAST clear refutation of. Deliberate: weak counterarguments usually flag weak ideas — the interesting test is the one you cannot easily talk yourself out of. State the ranking with one sentence per rank.

Select the TOP TWO for probing. Drop the bottom two; document why each was dropped in one line in NOTES.md.

## Step 4 — Two-candidate probe

**4a. Probe date.** Use the SAME single date across both candidates — fair comparison requires shared conditions. Pick the train date with highest expected combined event-class density across both candidates. If you cannot rank, default to the median date by trade volume in the base's cached per-date `metrics.json`. State date and reason in one line.

**4b. Pre-commit predictions per candidate.** Before any probe runs, commit to three numbers per candidate:
- `N_fire`: times per day the branch fires.
- `delta_pnl_isolated_usd`: in-isolation estimate from base's cached `positions.csv` for the probe date.
- `delta_pnl_counterfactual_usd`: chain-reaction-aware estimate. One sentence on direction and magnitude of divergence from isolated.

Six numbers total. Commit before any subprocess runs.

**4c. Run the probes.** For each candidate, write `execution_algos/<algo-id>-cand<i>/execution_algorithm.py` and register temporary factories in `execution_algos/__init__.py` as `sip-<abbrev>-l<N>-cand<i>` (i in {1,2}). Run:
```
python scripts/run_research_backtest.py --algo sip-<abbrev>-l<N>-cand<i> --use-cached-baseline --dates <YYYYMMDD>
```
Record per candidate:
- `actual_fire`: count of skips/overrides actually performed.
- `actual_delta_pnl_usd`: `algo.realized_pnl - base.realized_pnl` on the probe date.

**4d. Tournament gate.**
- Both candidates `actual_delta_pnl_usd <= 0`: **tournament barren on this probe**. Proceed to Step 5 with the candidate that LOST BY LESS. Flag in trace: "no probe winner — 12-date eval is for documentation only, expect negative aggregate." This is the escape valve loop-3 lacked.
- Exactly one candidate `> 0`: that's the **winner**. Proceed.
- Both `> 0`: the **larger positive `actual_delta_pnl_usd` wins**. Document runner-up's numbers in NOTES.md for the critic to see.
- `actual_fire == 0` for a candidate: identity transform — drop it. If both, the tournament collapsed; flag in NOTES.md and pick either deliverable.

**4e. One-date caveat.** Record in trace: "Probe date <DATE> chosen because <reason>. Tournament outcome may not generalize to 12-date." Do NOT probe multiple dates to game this.

Write tournament results into `execution_algos/<algo-id>/NOTES.md` under "Probe tournament": both candidates' six predictions, both actuals, the winner-selection logic, the dropped runner-up's numbers (if any).

## Step 5 — Direction AND magnitude (winner only)

- `realized_pnl`: direction AND magnitude band, tied to `actual_delta_pnl_usd * 12`. State whether you trust isolated or counterfactual more, and why.
- `mean_slippage`: direction with one sentence justifying that book-walking / participation-cap behavior is unchanged.
- `trade_count`: direction tied to `actual_fire * 12`.

## Step 6 — Finalize

Promote the winner: copy `execution_algos/<algo-id>-cand<winner>/execution_algorithm.py` to `execution_algos/<algo-id>/execution_algorithm.py`. Delete the `cand<i>` directories and their factory registrations from `execution_algos/__init__.py` (keep only the promoted `sip-<abbrev>-l<N>` factory). Verify registration. Make no further mechanism changes.

---

## Boundaries

- **One DELIVERED modification per loop** (the winner). The four-candidate exploration is internal — only one survives.
- **No re-entering a prior axis without explicit justification.** Default: fresh axis.
- **Replace `<algo-id>` with `sip-<abbrev>-l<N>` and `<base_algo>` with the literal id** in all paths.
- **Do not read `strategies/`** or any execution algo other than `execution_algos/<base_algo>/` and `execution_algos/sip-<abbrev>-l<N>*/`.
- **Train window only.** Use `config.yaml -> data_window.train`.
- **Honesty rules in OBJECTIVE.md §8 apply.** Report all six predictions and both actuals whether or not they match.
- **Tournament barren -> proceed with less-bad candidate**, not abort. The explicit escape valve loop-3 lacked. 12-date eval still produces metrics for the gate; the critic sees the probe failure and evolves the method.
- **Probe is one date, evaluation is twelve.** A passing tournament is a green light, not a verdict.
