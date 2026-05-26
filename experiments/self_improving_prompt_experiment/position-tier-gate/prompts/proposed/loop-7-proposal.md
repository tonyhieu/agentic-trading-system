# Hypothesis Generation Method — base_algo=position-tier-gate

You are an execution-algorithm researcher. Produce one concrete hypothesis for a new execution algorithm at `execution_algos/<algo-id>/` that you predict will achieve higher realized P&L than `<base_algo>` on the train window, without making slippage substantially worse.

Execution constraints (your algorithm must enforce them):
- **Quantity invariant**: `sum(child_fills) ≤ parent.quantity`. Never inflate.
- **top_of_book_only**: fill at `ask_px` (buys) or `bid_px` (sells). Never walk the book.
- **participation_cap**: per-tick `order_size ≤ floor(participation_cap × top_of_book_qty)`. Read from `research/config.yaml → execution_constraints`.
- **intraday_flat**: close all positions before session end.

This method is **propose → real-mechanism probe → 12-date commit**. Two gates must pass before the 12-date run: a static event-count gate AND a single-date live-mechanism probe. Static counts alone have failed 6 consecutive loops to predict dynamic outcomes — the live probe is mandatory and non-skippable.

---

## Step 1 — Read the base mechanism

Read `execution_algos/<base_algo>/execution_algorithm.py` and `execution_algos/<base_algo>/NOTES.md`. Identify in one sentence the specific *event class* the base conditions on (e.g., "same-`ts_init` CLOSE+OPEN pairs", "orders arriving when cache shows position ≥ cap"). Concrete: which field, which value, which timing.

## Step 2 — Read the banned-axes list

Read each `execution_algos/sip-ptg-l<X>/NOTES.md` for X in 1..N-1. Extract each loop's conditioning axis (e.g., "spread at on_order tick", "in-flight unrealized PnL", "post-zero-flip OPENs", "cap=2 paired OPENs", "deferred pair OPEN via on_order_filled"). Write the **Banned axes** list at the top of your `execution_algos/<algo-id>/NOTES.md`. You may not re-enter any axis on this list.

## Step 3 — Identify ONE plausible weakness

Identify one regime where the base's gate either over-skips good trades or fails to skip bad ones. Pick the weakness with the highest plausible frequency, not the most elegant one. Write it in one sentence: *"In regime X, the base does Y; if instead it did Z, expected outcome is W."*

## Step 4 — Propose ONE concrete modification

One modification — a different gate input, a parameter retune, or a guard. State it in mechanism terms (what the new `on_order()` branch does, conditioned on what), not in outcome terms. Verify the four execution constraints trivially hold.

## Step 5 — Static event-count gate (cheap)

**5a. Predict N.** "The new branch fires **at least N times per day** on average across the train window, where N = ___."

**5b. Count from cached baseline artifacts** — `execution_algos/<base_algo>/results/<YYYYMMDD>/orders.csv` and `fills.csv` for one median-volume train date. Raw DBN only if the property is not visible there.

**5c. Decide.** actual ≥ N: proceed to step 6. actual < N/5 or == 0: return to step 3.

Record in `NOTES.md` under "Static event-count gate".

## Step 6 — REAL-MECHANISM single-date probe (the gate that actually matters)

Static counts have failed 6 consecutive loops to predict dynamic outcomes. The static count tells you the mechanism fires; it does not tell you whether acting on the firings produces positive net PnL once cache state, position transitions, and order-stream cascading are in the loop. You must now run a REAL backtest of the proposed mechanism on a single date. STUB runs that do not actually execute the proposed mechanism are forbidden — they do not exercise the dynamic state that causes failure.

**6a. Implement the real algorithm.** Write `execution_algos/<algo-id>/execution_algorithm.py` with the FULL proposed mechanism. Register the factory in `execution_algos/__init__.py`. This is the same code you would run on 12 dates — no stubs.

**6b. Predict the single-date PnL delta.** BEFORE running, commit to a number:
> "On 20260313, realized_pnl(`<algo-id>`) − realized_pnl(`<base_algo>`) = ___ USD."

Base this on counterfactual reasoning, not isolation arithmetic. If you cannot confidently predict the sign, write "sign unknown" and pick a different weakness in step 3 — you do not understand the mechanism well enough.

**6c. Run the probe:**
```
python scripts/run_research_backtest.py --algo <algo-id> --use-cached-baseline --dates 20260313
```
Read `execution_algos/<algo-id>/results/20260313/metrics.json` and `execution_algos/<base_algo>/results/20260313/metrics.json` for `realized_pnl`. Compute the actual delta.

**6d. Probe gate (hard) — ALL THREE required:**
  1. `realized_pnl(algo) > realized_pnl(base)` on 20260313, OR within $50 if the mechanism is variance-reducing (state which).
  2. The sign of the actual delta matches your 6b prediction (you may be wrong on magnitude but not direction).
  3. `realized_pnl(algo)` is NOT exactly equal to `realized_pnl(simple)` — read from `execution_algos/simple_execution_strategy/results/20260313/metrics.json`. Exact equality with simple means your mechanism degenerated PTG into simple execution (happened in loops 5 and 7). Abort if equal.

If all three pass: proceed to step 7. If any fail: do not run 12 dates. Write the failed probe to `NOTES.md` under "Probe gate (FAIL)" with: predicted delta, actual delta, which condition failed, and a one-line postmortem. Return to step 3 with a different weakness.

You are allowed at most TWO probe attempts per loop. If both fail, write both to NOTES.md, commit no 12-date run, and write "Loop aborted at probe gate — no 12-date metrics produced." to NOTES.md. The next critique treats this as a deliberate abort and grades the method on its diagnostic value, not on missing 12-date metrics.

## Step 7 — 12-date commit

Only after step 6 passes:
```
python scripts/run_research_backtest.py --algo <algo-id> --use-cached-baseline
```
Read `execution_algos/<algo-id>/results/backtest-results.json`. The 12-date code MUST be byte-identical to the probe code.

## Step 8 — Direction AND magnitude statement

Post-probe, pre-write-up:
  - `realized_pnl`: direction (↑/↓ vs base) AND magnitude band tied to extrapolating the probe delta to 12 dates.
  - `mean_slippage`: direction with one sentence on book-walking / participation-cap behavior.
  - `trade_count`: direction tied to events-per-day from step 5c.

---

## Boundaries

- **One modification per loop.** No bundling.
- **Replace `<algo-id>` with `sip-ptg-l<N>` and `<base_algo>` with the literal id** in all paths.
- **Do not read `strategies/`** or any execution algo other than `execution_algos/<base_algo>/` and `execution_algos/<algo-id>/`.
- **Train window only.** Use `config.yaml → data_window.train`.
- **Probe gate is non-skippable.** Static count alone never proceeds to step 7.
- **Re-using a banned axis aborts the loop.** Write "Loop aborted — banned axis re-entry" to NOTES.md and stop.
- Honesty rules in `OBJECTIVE.md §8` apply: report actual numbers from both gates whether or not they matched prediction.
