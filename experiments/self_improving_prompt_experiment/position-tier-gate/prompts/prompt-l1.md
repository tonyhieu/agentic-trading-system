# Hypothesis Generation Method — base_algo=position-tier-gate

You are an execution-algorithm researcher. Produce one concrete hypothesis for a new execution algorithm at `execution_algos/<algo-id>/` that you predict will achieve higher realized P&L than `<base_algo>` on the train window, without making slippage substantially worse.

Execution constraints (the engine does NOT enforce them; your algorithm must):
- **Quantity invariant**: `sum(child_fills) ≤ parent.quantity`. Never inflate.
- **top_of_book_only**: fill at `ask_px` (buys) or `bid_px` (sells). Never walk the book.
- **participation_cap**: per-tick `order_size ≤ floor(participation_cap × top_of_book_qty)`. Read `participation_cap` from `research/config.yaml → execution_constraints`.
- **intraday_flat**: close all positions before session end.

This method is **propose → empirically verify → commit**. The verify step is mandatory and gates implementation.

---

## Step 1 — Read the base mechanism

Read `execution_algos/<base_algo>/execution_algorithm.py` and `execution_algos/<base_algo>/NOTES.md`. Identify in one sentence the specific *event class* in the order stream that the base algo conditions on (e.g., "same-`ts_init` CLOSE+OPEN pairs", "orders arriving when cache shows position ≥ cap", "first order of the session"). Be concrete: which field, which value, which timing.

## Step 2 — Identify ONE plausible weakness

Identify one regime where the base's gate either over-skips good trades or fails to skip bad ones. Pick the weakness with the highest plausible frequency, not the most elegant one. Write it in one sentence as: *"In regime X, the base does Y; if instead it did Z, expected outcome is W."*

## Step 3 — Propose ONE concrete modification

Propose ONE modification — a different gate input, a parameter retune, or a guard layered on top — that addresses the weakness. State it in mechanism terms (what the new `on_order()` branch does, conditioned on what), not in outcome terms ("be smarter about flips"). Verify constraints (quantity invariant, top-of-book, participation_cap, intraday_flat) trivially hold.

## Step 4 — MANDATORY empirical pre-check (this is the gate)

Before writing any algorithm code, you must verify the event class your proposal conditions on is non-empty in the actual data the algorithm will see. Skipping or weakening this step is the canonical failure mode this method is designed to prevent.

**4a. Predict a measurable consequence.** State, as a single numeric prediction:
> "If my hypothesis is non-vacuous, the new branch I am adding will fire **at least N times per day** on average across the train window, where N = ___."
You must commit to a number. "Many" or "often" is not allowed. If you cannot estimate N with reasoning, that itself is a signal — drop to step 4d.

**4b. Find a verification surface.** Choose the cheapest artifact that lets you count the predicted event class:
  - **Cached baseline artifacts** — `execution_algos/<base_algo>/results/<YYYYMMDD>/orders.csv` and `fills.csv` exist for every train date. If your proposal conditions on an order-stream property (side, ts_init coincidence, reduce-only flag, cache state reconstructable from the fill log), count it here. This is the default surface.
  - **Raw DBN ticks** via the `analysis` skill — only if your proposal conditions on a market microstructure property (spread, top-of-book depth, trade aggression) not visible in baseline artifacts. Use one or two train dates, not all twelve.
  - **A minimal one-day probe backtest** — only if no static artifact can resolve the question (e.g., the event class depends on cache state during a counterfactual order flow). Implement a stub that logs the event class without changing submit/skip behavior, run one date, count from the log.

**4c. Count and compare.** Run the count. Record actual events-per-day. Then:
  - If actual ≥ N: hypothesis passes the empirical pre-check. Proceed to step 5.
  - If actual < N but > 0: state how much the prediction was off by. If the gap is more than 5×, treat as a failure and return to step 2 with a different weakness.
  - If actual == 0: the hypothesis is vacuous — the proposed algorithm will be an identity transform on the base. **Do not implement.** Return to step 2 with a different weakness, or to step 1 with a different base mechanism reading.

**4d. Cannot estimate N at all.** If step 4a is genuinely impossible — you have no model of the source process — that is a signal the hypothesis is built on prose, not on the data. Return to step 2 and pick a different weakness whose magnitude you *can* estimate from a static artifact.

Write the empirical pre-check result into `execution_algos/<algo-id>/NOTES.md` under an "Empirical pre-check" section with: the prediction N, the verification surface used, the actual count, the pass/fail decision, and a one-line justification.

## Step 5 — State expected direction AND magnitude

Only after step 4 passes:
  - `realized_pnl`: direction (↑ or ↓ vs base) AND a rough magnitude band ("a few percent", "double-digit percent", "order of magnitude") with one sentence of reasoning tied to the event-class frequency from step 4c.
  - `mean_slippage`: direction with one sentence justifying why book-walking / participation-cap behavior is unchanged.
  - `trade_count`: direction tied to the events-per-day estimate from 4c.

## Step 6 — Implement

Write the algorithm at `execution_algos/<algo-id>/execution_algorithm.py`. Register the factory in `execution_algos/__init__.py`. The implementation must mirror the mechanism described in step 3 — no scope creep beyond what survived the empirical gate.

---

## Boundaries

- **One modification per loop.** No bundling multiple changes ("directional gate AND a parameter retune"). If step 4 disqualifies your proposal, drop it and pick a different weakness — do not patch around the failure by stacking more changes.
- **Replace `<algo-id>` with `sip-ptg-l<N>` and `<base_algo>` with the literal id** in all paths.
- **Do not read `strategies/`** or any execution algo other than `execution_algos/<base_algo>/` and `execution_algos/<algo-id>/`.
- **Train window only.** Use `config.yaml → data_window.train`.
- The honesty rules in `OBJECTIVE.md §8` apply to the trace: report the actual event count from step 4c whether or not it matched your prediction.
