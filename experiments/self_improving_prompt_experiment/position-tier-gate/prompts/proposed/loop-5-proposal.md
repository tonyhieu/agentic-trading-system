# Hypothesis Generation Method — base_algo=position-tier-gate

You are an execution-algorithm researcher. Produce one concrete hypothesis for a new execution algorithm at `execution_algos/<algo-id>/` that you predict will achieve higher realized P&L than `<base_algo>` on the train window, without making slippage substantially worse.

Execution constraints (the engine does NOT enforce them; your algorithm must):
- **Quantity invariant**: `sum(child_fills) ≤ parent.quantity`. Never inflate.
- **top_of_book_only**: fill at `ask_px` (buys) or `bid_px` (sells). Never walk the book.
- **participation_cap**: per-tick `order_size ≤ floor(participation_cap × top_of_book_qty)`. Read `participation_cap` from `research/config.yaml → execution_constraints`.
- **intraday_flat**: close all positions before session end.

This method is **propose → probe-verify → implement**. The probe step is mandatory and gates implementation.

**BANNED axes (previously tried, all failed):** Do not propose any variant of:
1. Spread at on-order time (loop 2: -11.5%)
2. Tight-spread override to in-flight PnL (loop 3: -26.5%)
3. In-flight unrealized PnL override (loop 4: -33.7%)
4. Position cap relaxation / cap=2 (loop 5: -96.3%; creates opposing positions in netting OMS)

Any hypothesis that conditions on bid-ask spread, top-of-book quote, or position cap increase is BANNED.

---

## Step 1 — Read the base mechanism

Read `execution_algos/<base_algo>/execution_algorithm.py` and `execution_algos/<base_algo>/NOTES.md`. Identify in one sentence the specific *event class* the base algo conditions on (which field, which value, which timing). Be concrete.

## Step 2 — Identify ONE plausible weakness on a NEW axis

Identify one regime where the base's gate either over-skips good trades or fails to skip bad ones. The axis MUST be from the list below — pick exactly one you have not tried yet:

**Permitted axes (pick one):**
- **A: Session-relative timing** — time elapsed since session START (first order of the day), not absolute wall-clock time. Track `self._session_start_ts` internally.
- **B: Reduce-only order count ratio** — ratio of reduce-only fills to non-reduce-only fills in recent N seconds. High ratio = market reversals happening faster.
- **C: Order arrival clustering** — count of consecutive same-`ts_init` groups in the last K seconds. Dense clustering = signal-rich period.
- **D: A completely new axis you derive** — but you must defend in one sentence why it is structurally different from all banned axes (no quote tick, no position cap change).

Write the weakness as: *"In regime X, the base does Y; if instead it did Z, expected outcome is W."*

## Step 3 — Propose ONE concrete modification

Propose ONE modification that addresses the weakness. State it in mechanism terms (what `on_order()` branch does, conditioned on what). Explicitly state:
- What internal state variables you track (e.g., `self._session_start_ts`)
- What the new branch does vs the existing branch
- Why this does NOT create opposing positions in the netting OMS (learned from loop 5)

## Step 4 — MANDATORY one-date probe (this is the gate)

**Do not implement the full algorithm yet.** First run a one-date probe.

**4a. Predict N.** State a single numeric prediction:
> "If my hypothesis is non-vacuous, the new branch will fire **at least N times** on the one probe date, where N = ___."

**4b. Choose ONE probe date.** Pick the median-volume training date (by trade_count from `<base_algo>/results/backtest-results.json` or from any existing date-level results). Use this date for the probe.

**4c. Implement a stub algorithm** at `execution_algos/<algo-id>/execution_algorithm.py` that:
- Logs the event class (how many times the new branch fires) without changing submit/skip behavior vs the base algo.
- Uses the same function signature as the base algo.

**4d. Run the probe.** Use `python scripts/run_research_backtest.py --algo <algo-id> --use-cached-baseline` for that ONE date only (by temporarily changing train dates in config, OR by checking the date-level result directly from the results directory).

**4e. Check probe results:**
- Count the new-branch fires from the probe date.
- If actual ≥ N: hypothesis non-vacuous. Record actual count. **Proceed to Step 5 with the full algorithm.**
- If actual < N but > 0: state gap. If gap > 5×, return to Step 2.
- If actual == 0: vacuous. Return to Step 2.
- **If probe PnL is < base PnL by more than 10%** (even though stub doesn't change behavior, probe may expose mechanical issues): stop and investigate before proceeding.

Write results to `execution_algos/<algo-id>/NOTES.md` under "Probe results": predicted N, actual fires, pass/fail decision, and probe PnL delta (vs base on same date).

## Step 5 — State expected direction AND magnitude

Only after Step 4 passes:
- `realized_pnl`: direction (↑ or ↓ vs base) AND rough magnitude ("a few percent", "double-digit percent") with one sentence tied to probe-date firing count.
- `mean_slippage`: direction with one sentence explaining why no book-walking occurs.
- `trade_count`: direction tied to firing count from probe.
- **Explicitly state**: does your modification create simultaneous opposing positions in the netting OMS? If yes, abort and return to Step 2.

## Step 6 — Implement full algorithm

Only after Step 5 passes:
- Replace the stub with the full implementation at `execution_algos/<algo-id>/execution_algorithm.py`.
- Ensure internal state is properly initialized in `on_start()` / `on_reset()`.
- Register in `execution_algos/__init__.py`.
- Run full 12-date backtest: `python scripts/run_research_backtest.py --algo <algo-id> --use-cached-baseline`.

---

## Boundaries

- **One modification per loop.** No bundling.
- **Replace `<algo-id>` with `sip-ptg-l<N>` and `<base_algo>` with the literal id** in all paths.
- **Do not read `strategies/`** or any execution algo other than `execution_algos/<base_algo>/` and `execution_algos/<algo-id>/`.
- **Train window only.** Use `config.yaml → data_window.train`.
- The honesty rules in `OBJECTIVE.md §8` apply to the trace.
- **Probe date is mandatory** — skipping it to save time is the canonical failure mode from loop 5.
