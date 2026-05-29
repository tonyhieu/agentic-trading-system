# Seed Prompt — base_algo=aggressor-flow-gate

You are an execution-algorithm researcher. Produce a hypothesis for a new execution algorithm at `execution_algos/<algo-id>/` that you predict will achieve a higher realized P&L than `<base_algo>` on the train window, without making slippage substantially worse.

You must respect these execution constraints (the Nautilus engine does NOT enforce them; your algorithm must):
- **Quantity invariant**: `sum(child_fills) ≤ parent.quantity`. Never inflate.
- **top_of_book_only**: fill at `ask_px` (buys) or `bid_px` (sells). Never walk the book.
- **participation_cap**: per-tick `order_size ≤ floor(participation_cap × top_of_book_qty)`. Read `participation_cap` from `research/config.yaml → execution_constraints`.
- **intraday_flat**: close all positions before session end.

Hypothesis generation method (single-pass):
1. Read `execution_algos/<base_algo>/execution_algorithm.py` and `execution_algos/<base_algo>/NOTES.md` to understand the current mechanism and the inefficiency it exploits.
2. Identify ONE plausible weakness of that mechanism (a regime where its gate either over-skips good trades or fails to skip bad ones).
3. Propose ONE concrete modification — a different gate input, a parameter retune, or a guard layered on top — that you expect would address that weakness while preserving the constraints above.
4. State the expected direction of the change in P&L and slippage relative to `<base_algo>`, and why.
