# Seed Prompt — base_algo=aggressor-flow-gate

You are an execution-algorithm researcher. Your task: starting from the execution algorithm at `execution_algos/aggressor-flow-gate/`, produce a new execution algorithm at `execution_algos/<algo-id>/` that achieves a higher realized P&L than `aggressor-flow-gate` on the train window, without making slippage substantially worse.

You must respect these execution constraints (the Nautilus engine does NOT enforce them; your algorithm must):
- **Quantity invariant**: `sum(child_fills) ≤ parent.quantity`. Never inflate.
- **top_of_book_only**: fill at `ask_px` (buys) or `bid_px` (sells). Never walk the book.
- **participation_cap**: per-tick `order_size ≤ floor(participation_cap × top_of_book_qty)`. Read `participation_cap` from `research/config.yaml → execution_constraints`.
- **intraday_flat**: close all positions before session end.

Procedure:
1. Copy the contents of `execution_algos/aggressor-flow-gate/` to `execution_algos/<algo-id>/`.
2. Modify the copied `execution_algorithm.py` to implement your improvement idea.
3. Register `<algo-id>` in `execution_algos/__init__.py → _EXEC_ALGORITHM_FACTORIES`.
4. Run: `python scripts/run_research_backtest.py --algo <algo-id> --use-cached-baseline`.
5. Read `execution_algos/<algo-id>/results/backtest-results.json` and verify the result.
6. Report: `realized_pnl`, `sharpe_ratio`, `mean_slippage`, `trade_count`, `vs_base_pnl_pct`.
