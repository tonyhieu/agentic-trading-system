# Hypothesis Generation Method — base_algo=position-tier-gate

You are an execution-algorithm researcher. Produce one concrete hypothesis for a new execution algorithm at `execution_algos/<algo-id>/` that you predict will achieve higher realized P&L than `<base_algo>` on the train window, without making slippage substantially worse.

Execution constraints (the engine does NOT enforce them; your algorithm must):
- **Quantity invariant**: `sum(child_fills) ≤ parent.quantity`. Never inflate.
- **top_of_book_only**: fill at `ask_px` (buys) or `bid_px` (sells). Never walk the book.
- **participation_cap**: per-tick `order_size ≤ floor(participation_cap × top_of_book_qty)`. Read `participation_cap` from `research/config.yaml → execution_constraints`.
- **intraday_flat**: close all positions before session end.

Method: **breadth → axis-diversity guard → one-date probe tournament → commit-with-escape-valve**. Loops 2, 3, and 4 all failed by serially extending a single conditioning axis with different predicates and committing to 12-date eval on a static event count. The method forces architectural diversity and tests proposed algorithms — not isolated event subsets — on a real backtest before the 12-date eval.

---

## Step 1 — Read base and ban prior axes

Read `execution_algos/<base_algo>/execution_algorithm.py` and `NOTES.md`. Identify in one sentence the *event class* the base conditions on (field, value, timing).

Read every prior `execution_algos/sip-ptg-l<X>/NOTES.md` for X < N. For each, record in a "Prior axes" section of your NOTES.md a one-line *conditioning axis* label = (object, temporal aspect). Examples:
- "quote-book spread at on_order time" (loops 2, 3)
- "in-flight unrealized PnL at on_order time" (loop 4)
- "same-side flag of incoming order vs in-flight position" (loop 1)

These axes are now **banned**. Your candidates must condition on a different *object* or a different *temporal aspect*. A renamed banned axis is the loop-3 anti-pattern.

## Step 2 — Generate FOUR axis-orthogonal candidates

Brainstorm four candidate weaknesses, each on a **distinct conditioning axis** not on the banned list. Pick at most one candidate per axis family from:
- **Time-of-day / session-phase**
- **Trade-tape aggression** (recent aggressor side, signed flow imbalance)
- **Position holding-time** (how long in-flight has been open at flip)
- **Quote-book depth / liquidity** (top-of-book size, not spread)
- **Order pacing** (inter-arrival time of `on_order()`)
- **Self-flip frequency** (flips within last K seconds)

For each candidate, write three sentences in NOTES.md under "Candidate <i>":
1. Conditioning axis = (object, temporal aspect).
2. The new `on_order()` branch — what condition, what action (submit/skip).
3. Why this axis might carry signal the base ignores.

**Diversity check.** If any two candidates share the same (object, temporal aspect), replace one. If three or more depend on the same intermediate variable (e.g., "all three need a rolling trade aggregator"), replace one.

## Step 3 — Adversarial rank

For each candidate, write the **strongest counterargument** — one sentence naming a *mechanism* by which the modification harms aggregate PnL. Specific, not "might be noise." Example: "skipping these OPENs orphans their CLOSEs and the intraday_flat handler force-closes at session end at worse prices."

Rank by **how hard the counterargument is to dismiss** — top = hardest-to-dismiss = most likely to carry real signal given strong skepticism. The top TWO go to the probe tournament.

## Step 4 — MANDATORY one-date probe tournament (the gate)

Implement BOTH top candidates as real algorithms and run each on ONE date.

**4a. Probe date.** Pick the date in `config.yaml → data_window.train` with median `trade_count` in the base's cached per-date `metrics.json`. Median, not max. State date and median rank in NOTES.md.

**4b. Pre-commit six numbers in NOTES.md BEFORE running anything.**
For each of the two candidates (A and B):
  - `N_fire_<x>`: how many times per day the new branch fires.
  - `delta_pnl_isolated_<x>_usd`: in-isolation estimate from cached artifacts.
  - `delta_pnl_counterfactual_<x>_usd`: your prediction of probe-date `algo.realized_pnl − base.realized_pnl`. May equal `delta_pnl_isolated` only if you can give one mechanism sentence for why subsequent orders are unaffected.

"Many", "approximately", "TBD" are not allowed.

**4c. Implement and run.** Create `execution_algos/<algo-id>-probe-a/execution_algorithm.py` and `execution_algos/<algo-id>-probe-b/execution_algorithm.py`. Register both factories. Run:

```
python scripts/run_research_backtest.py --algo <algo-id>-probe-a --use-cached-baseline --dates <YYYYMMDD>
python scripts/run_research_backtest.py --algo <algo-id>-probe-b --use-cached-baseline --dates <YYYYMMDD>
```

For each, record:
  - `actual_fire_<x>`: fires actually executed (via `base_trade_count − algo_trade_count` for 1:1 skip gates, or via log lines).
  - `actual_delta_pnl_<x>_usd`: `algo.realized_pnl − base.realized_pnl` on the probe date.

**4d. Tournament gate.** Winner = strictly larger `actual_delta_pnl_<x>_usd`.
  - `actual_delta_pnl_winner > 0`: **PROCEED-WIN** — promote winner to `<algo-id>`.
  - `actual_delta_pnl_winner ≤ 0` AND `> actual_delta_pnl_loser`: **PROCEED-LESS-BAD** — promote winner anyway. The 12-date aggregate may surprise; the loop always produces gate-comparable metrics rather than aborting.
  - Both `actual_fire == 0`: **ABORT** — both event classes vacuous. Return to step 2 with two new candidates not in the failed families.

For PROCEED-*: copy winner's `execution_algorithm.py` to `execution_algos/<algo-id>/`, register `<algo-id>` in `execution_algos/__init__.py` — this is the factory the 12-date eval will run.

**4e. Variance acknowledgement.** Write in trace: "I am extrapolating from one probe date on the winner. The 12-date aggregate may diverge. A PROCEED-LESS-BAD means I proceed despite a probe loss because no candidate beat base, and the next loop's critic must see those numbers."

NOTES.md "Probe tournament" section records: probe date, both candidates' six pre-committed numbers, both candidates' actual_fire and actual_delta_pnl_usd, the gate decision.

## Step 5 — Direction and magnitude (winner only)

  - `realized_pnl`: direction AND magnitude band, tied to `actual_delta_pnl_winner × 12` AND to your counterfactual. State which you trust and why.
  - `mean_slippage`: direction with one sentence justifying why book-walking / participation-cap behavior is unchanged.
  - `trade_count`: direction tied to `actual_fire_winner × 12`.

## Step 6 — Finalize

Step 4c already produced and registered the winning algorithm. Make no further mechanism changes — if you found a flaw during the probe, drop the candidate and return to step 2, not patch around it. The loser's probe directory remains; do not delete. The 12-date eval runs only on the winner.

---

## Boundaries

- **One modification per loop** (= the tournament winner). The loser is documentation; do not bundle.
- **Replace `<algo-id>` with `sip-ptg-l<N>` and `<base_algo>` with the literal id** in all paths. Probes use `<algo-id>-probe-a` and `<algo-id>-probe-b`.
- **Banned axes are hard.** A renamed banned axis is the loop-3 anti-pattern.
- **Do not read `strategies/`** or any algo other than `execution_algos/<base_algo>/`, `execution_algos/sip-ptg-l<X>/` for X < N, `<algo-id>/`, `<algo-id>-probe-a/`, `<algo-id>-probe-b/`.
- **Train window only.** Use `config.yaml → data_window.train`.
- Honesty rules in `OBJECTIVE.md §8` apply: report every committed and actual number, even when probes embarrass the predictions.
- **Probe is one date, evaluation is twelve.** A passing probe is a green light, not a verdict.
