# Hypothesis Generation Method — base_algo=position-tier-gate

You are an execution-algorithm researcher. Produce one concrete hypothesis for a new execution algorithm at `execution_algos/<algo-id>/` that you predict will achieve higher realized P&L than `<base_algo>` on the train window, without making slippage substantially worse.

Execution constraints (the engine does NOT enforce them; your algorithm must):
- **Quantity invariant**: `sum(child_fills) ≤ parent.quantity`. Never inflate.
- **top_of_book_only**: fill at `ask_px` (buys) or `bid_px` (sells). Never walk the book.
- **participation_cap**: per-tick `order_size ≤ floor(participation_cap × top_of_book_qty)`. Read `participation_cap` from `research/config.yaml → execution_constraints`.
- **intraday_flat**: close all positions before session end.

This method is **probe-first**: you must run a one-date probe backtest BEFORE committing to full implementation. This is the primary gate change learned from loops 5 and 6, where static analysis produced wrong sign or wrong magnitude estimates.

**BANNED axes (previously tried, all failed):**
1. Spread / bid-ask quote at on-order time (loop 2: -11.5%)
2. Tight-spread override / in-flight unrealized PnL (loops 3-4)
3. Position cap relaxation / cap=2 (loop 5: -96.3%)
4. Zero-PnL-after-flip filter (loop 6: -9.7% with 1/5 metrics improved)
5. Any variant of direction-flip filtering (all dynamic simulations: -48% to -51%)

---

## Step 1 — Read the base mechanism

Read `execution_algos/<base_algo>/execution_algorithm.py`. Identify the specific event class the base algo conditions on. Be concrete: which field, which value, which timing.

## Step 2 — Identify ONE weakness on a STRUCTURAL axis

The weakness must be STRUCTURAL (about how the algorithm handles the order stream mechanics), not a filtering axis (trying to identify good vs bad orders from historical PnL). Structural axes include:
- **Order sequencing**: changing WHEN orders are submitted relative to each other
- **Position state transitions**: how the algo handles flat→open and open→close→flat cycles
- **Execution timing**: submitting at different points within the same ts_init group
- **Order routing**: submitting to a different child order path

If your proposed axis is "skip some OPEN orders based on a signal", stop. That approach has been exhausted across 5 loops. The PTG is near-optimal for filtering; improvement must come from a different structural change.

## Step 3 — Propose ONE concrete modification

State the mechanism exactly: what `on_order()` does differently, conditioned on what structural property. Confirm:
- No filtering of OPEN orders based on historical PnL signals (see banned axes above)
- Does NOT create simultaneous opposing positions in netting OMS (lesson from loop 5)
- Still satisfies all execution constraints

## Step 4 — ONE-DATE PROBE (mandatory gate — do not skip)

**4a. Pick the median-volume training date.** Use positions.csv to find the date with median trade count. For PTG, the median training date by position count is approximately 20260313 (5647 positions).

**4b. Predict N.** State: "The new branch will fire at least N times on the probe date, where N = ___."

**4c. Implement a STUB.** Write `execution_algos/<algo-id>/execution_algorithm.py` that:
- Logs "NEW_BRANCH_FIRE" when the new branch would fire
- Otherwise behaves IDENTICALLY to the base algo (does not change submit/skip decisions)

Register in `execution_algos/__init__.py`.

**4d. Run the stub on ONE date.** Run:
```
python scripts/run_research_backtest.py --algo <algo-id> --use-cached-baseline
```
Check the `<algo-id>/results/<probe_date>/` directory for the stub's output.

**4e. Count fires AND check PnL delta.** Two gates:
- Fire count: if actual ≥ N → event class non-vacuous. If actual == 0 → vacuous, abort. If actual < N/5 → abort.
- PnL delta on probe date: if stub PnL ≠ base PnL (stubs should produce identical results!) → investigate mechanical issue before proceeding.

Write probe results to NOTES.md. **Do not proceed to full implementation until both gates pass.**

## Step 5 — Full implementation gate

After step 4 passes: implement the full algorithm (replacing the stub). In NOTES.md, write:
- Predicted PnL direction AND magnitude (tied to probe-date fire count × estimated per-event gain from a micro-analysis of the base algo's artifact, not a static removal estimate)
- Explicit statement: "No simultaneous opposing positions are created because ___"
- Predicted trade count direction

## Step 6 — Full backtest

Run all 12 training dates. Read `backtest-results.json`. Compare vs base PTG metrics.

---

## Boundaries

- **Structural axis only.** If your proposal is another "skip OPEN orders based on signal X", reject it in Step 2 and try again.
- **Probe is mandatory.** Skipping Step 4 is the primary failure mode from loops 5 and 6.
- **Replace `<algo-id>` with `sip-ptg-l<N>` and `<base_algo>` with the literal id.**
- **Train window only.**
- **Do not read `strategies/`** or other algo dirs besides `<base_algo>/` and `<algo-id>/`.
- The honesty rules in `OBJECTIVE.md §8` apply.
