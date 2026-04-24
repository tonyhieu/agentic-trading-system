# Research Notes — Toy Example

This file is for **ambiguity alerts that require a human decision**.

Do not use it for strategy reasoning (that belongs in `execution_algos/<name>/NOTES.md`).
Write here when something is unclear enough that a human needs to decide.

## Format

Append entries as:

```markdown
## [YYYY-MM-DD HH:MM] <category>: <short title>

**Category**: ASSUMPTION | UNCLEAR | DATA ISSUE | RESULT WARNING

**Detail**: What exactly is unclear or what assumption was made.

**Why**: Why you had to make this assumption.

**Alternatives**: Other interpretations and how they would change the result.

**Impact**: Does this likely affect the outcome significantly?
```

After writing here, print:
```
⚠ NOTE WRITTEN: toy_example/research/NOTES.md — <short title>
```

---

## [2026-04-24 07:20] UNCLEAR: run_research.py does not emit the gate metrics (vs_twap_pct, vs_vwap_pct)

**Category**: UNCLEAR

**Detail**: PROBLEM_DEFINITION.md §4 defines the Pass Gate as "Strategy net P&L must exceed both TWAP and VWAP net P&L by at least 10%", and §5 step 6 instructs "Review the printed metrics. Check vs_twap_pct and vs_vwap_pct." However, `toy_example/run_research.py` — the canonical runner mandated by §5 step 5 — prints **no** TWAP/VWAP benchmark metrics. The `compute_metrics()` in `backtest_engine/results.py` returns `starting_balance`, `final_equity`, `total_return_pct`, `realized_pnl`, `max_drawdown_pct`, `sharpe_ratio`, trade counts, commissions, and slippage — nothing else. A fresh run of `python toy_example/run_research.py --strategy ema_cross --date 20260406` confirms no `vs_twap_pct` / `vs_vwap_pct` keys in the output or in the JSON entry appended to `program_database.json`.

A second, divergent runner exists at `toy_example/run.py` that does reference `vs_twap_pct` / `vs_vwap_pct`, but it imports `strategy.py` and `backtester.py` from `toy_example/`, neither of which exists in the tree. So that path is also non-functional.

A third inconsistency: §5 step 4 says "Write strategy in `execution_algos/<name>/strategy.py`", but `execution_algos/` is the **execution-algorithm** factory directory (`execution_algos/__init__.py` only registers `simple`), while the `--strategy <name>` flag in `run_research.py` dispatches through `strategies/__init__.py` (which currently registers `ema_cross` and `momentum`). Placing new code in `execution_algos/<name>/` would not be discoverable by `--strategy`.

**Why**: The instructions explicitly forbid fabricating metrics ("Never fabricate metrics. Report only what `run_research.py` prints.") and forbid skipping validation. Without a working TWAP/VWAP benchmark, there is no honest way to decide PASS/CLOSE/FAIL against the gate specified in §4. Any attempt to self-compute these numbers would conflict with the "Report only what `run_research.py` prints" rule and create an unaudited pipeline.

**Alternatives**:
1. Extend `backtest_engine/results.py` (or `run_research.py`) to compute TWAP and VWAP benchmark net P&L from the fills.csv / tick data, emit `vs_twap_pct` / `vs_vwap_pct`, and print them. This is a non-trivial infrastructure change that should be code-reviewed before it becomes the source of truth for PASS gates.
2. Complete the `toy_example/run.py` path by adding `toy_example/strategy.py` and `toy_example/backtester.py` with a minimal TWAP/VWAP-aware backtester. Also an infrastructure task.
3. Redefine the gate in terms of metrics that **are** emitted (e.g., realized_pnl > 0 with sharpe_ratio > some threshold). This changes the research question.
4. Clarify whether `execution_algos/<name>/strategy.py` should actually be `strategies/<name>/` (or vice-versa), and confirm the strategy-registration path.

**Impact**: Completely blocking. Without the gate metrics, I cannot run even one full Research Loop iteration (§5 steps 6–7) honestly. The cap was hypothesis=5, but I cannot progress past step 6 for any hypothesis I might try, so I am stopping after zero hypotheses implemented rather than run five blind experiments whose PASS/FAIL cannot be determined from the printed metrics.

---

## [2026-04-24 07:28] RESOLVED + ASSUMPTION: TWAP/VWAP benchmark interpretation

**Category**: ASSUMPTION

**Detail**: Alternative 1 above was implemented in `backtest_engine/benchmarks.py`. `run_research.py` now prints `twap_net_pnl`, `vwap_net_pnl`, `vs_twap_pct`, `vs_vwap_pct`, `benchmark_trade_count`, and `exec_window_seconds`. The spec (§4) is silent on two implementation choices; these are the assumptions baked in:

1. **Holding window → per-position execution window.** §4 says "executes uniformly over the holding window" but the phrase is ambiguous. A literal "entry→exit window" interpretation makes TWAP's entry and exit identical, giving zero P&L, so it was rejected. Instead, each fill (entry and exit separately) gets a fixed T_exec execution window starting at decision time. Both entry and exit are benchmarked.

2. **T_exec = 300 seconds (5 minutes).** Not in the spec. Standard execution-benchmark default. Adjustable via `exec_window_seconds` kwarg.

3. **VWAP weight = displayed book size on the taking side.** MBP-1 has no trade volume; `ask_sz_00` weights buy fills, `bid_sz_00` weights sell fills. If a real volume feed lands later, swap in trade size.

4. **Benchmarks use the same decision times and position sizes as the strategy.** Only fill prices differ. This isolates execution quality (the research question in §1).

**Why**: Each choice required for the benchmark to be computable and honest. Choice 1 was forced by algebra. Choices 2–4 are defaults — swap them if the research question drifts toward pure-alpha evaluation.

**Alternatives**:
- Use a 1-min or 15-min T_exec (try both if results are sensitive).
- Weight VWAP by trade volume from a richer feed when available.
- Re-parameterize the gate in terms of Sharpe improvement vs. benchmarks instead of net P&L.

**Impact**: Unblocks the Research Loop. The gate is now computable. Current ema_cross baseline: strategy_net=-73.2, twap_net=-36.2, vwap_net=-28.0, so `vs_twap_pct=-102%`, `vs_vwap_pct=-162%` — both strongly negative, as expected for a losing baseline.

**Open item** (resolved 2026-04-24): PROBLEM_DEFINITION.md §5 step 4, §6 R2/R3, §7, and §8 updated to use `strategies/<name>_strategy/` and to include the `strategies/__init__.py` factory-registration step. `execution_algos/<exec-algo>/results/` is now documented as the results directory only.

---

## [2026-04-24 15:10] ASSUMPTION: 5% participation cap not enforced end-to-end

**Category**: ASSUMPTION

**Detail**: PROBLEM_DEFINITION.md §3 rule 2 says `order_size ≤ floor(0.05 × bid_sz_00 or ask_sz_00)` per tick. On GCM6 MBP-1, the median top-of-book displayed size is 1 contract, so `floor(0.05 × 1) = 0`, meaning *no* trade of any size would be allowed under a strict reading of the rule at median liquidity. The existing `ema_cross` baseline trades 1 lot and is what the TWAP/VWAP benchmark compares against. The Nautilus simulated exchange and the `compute_execution_benchmarks` function in `backtest_engine/benchmarks.py` do not enforce the cap. I am continuing the `ema_cross` convention — trade 1 lot per signal — so my strategy `ofi-v1` is compared apples-to-apples against the benchmark on identical decision timestamps and sizes.

**Why**: A strict reading of §3 makes the entire research task vacuous (no trades possible). An apples-to-apples comparison with TWAP/VWAP at the same sizes isolates execution quality, which matches §1's stated research question.

**Alternatives**:
- Enforce the cap and require trading only when a side has ≥20 lots displayed. This would reduce signal frequency by >90% on GCM6.
- Treat the cap as "aspirational" and report the number of cap-violating fills alongside metrics.
- Switch the target instrument to one whose top-of-book is routinely ≥20 lots (e.g., MESM6).

**Impact**: Does not change the PASS/FAIL determination against TWAP/VWAP because the benchmark sees the same (capped or uncapped) sizes. Does affect any later realism check against actual venue liquidity.

---

## [2026-04-24 15:40] RESULT WARNING: orb-v1 train-day result driven by a single trade

**Category**: RESULT WARNING

**Detail**: `orb-v1` (Opening Range Breakout, 30-min post-open, 13:30-14:00 UTC) fired exactly one trade on the 2026-04-06 training day (a long breakout that hit the $2.00 trailing stop for -$1.30). The Pass Gate computation is based on n=1 round-trip. The benchmark comparison (TWAP -$0.10, VWAP -$0.30) is also a single-point comparison. `vs_twap_pct = -1170%` is numerically extreme because the denominator |-$0.10| is tiny, not because the strategy is meaningfully worse — the absolute loss differential is only $1.20.

**Why**: Flagging per §8 "Observe results driven by very few trades." A single trade cannot support or refute the ORB hypothesis and cannot inform refinement.

**Alternatives**: Testing on additional days would resolve this, but the spec provides only 1 train day and 1 validation day. Running ORB on the validation day would also likely yield 1 trade. The honest conclusion is "n=1 observation, pass gate fails in absolute terms."

**Impact**: orb-v1 is logged as FAIL (pass gate is mechanical — strategy net < benchmark net in raw dollars). But do not interpret this FAIL as a refutation of opening-range breakout strategies in general; it is a refutation of "this specific parameterization won on this specific day." Refinement is not pursued because further parameter tweaks would be evaluated on the same n=1 evidence.

