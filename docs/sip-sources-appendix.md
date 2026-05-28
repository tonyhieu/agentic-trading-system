# Source Appendix — SIP Experiment
## Every claim, data point, and result with its file path

All paths are relative to the repository root: `C:\Users\elliotchung\Github\agentic-trading-system\`

---

## 1. System Setup & Infrastructure

| Claim | Source File | Field / Location |
|---|---|---|
| Train window: 2026-03-08 to 2026-03-21 | `research/config.yaml` | `data_window.train` |
| Test window: 2026-03-26 to 2026-04-06 | `research/config.yaml` | `data_window.test` |
| Pass gate: +5% PnL, ≤5% slippage regression | `research/config.yaml` | `pass_gate.min_pnl_improvement_pct`, `pass_gate.max_slippage_regression_pct` |
| Baseline algorithm: `simple` | `research/config.yaml` | `pass_gate.baseline` |
| Oracle strategy: sigma=6, horizon=30s, seed=42, 1Hz cadence | `research/config.yaml` | `strategy.kwargs` |
| Max iterations: 30 | `research/config.yaml` | `loop.max_iterations` |
| Execution constraints (top-of-book, 5% participation cap, intraday flat) | `research/config.yaml` | `execution_constraints` |
| Full research brief and honesty rules | `docs/OBJECTIVE.md` | Full document |
| Agent definition (sip-researcher loop architecture, phases, gate logic) | `.claude/agents/sip-researcher.md` | Full document |
| Algorithm factory registry (all registered algo IDs) | `execution_algos/__init__.py` | `_EXEC_ALGORITHM_FACTORIES` dict |
| Backtest entry point | `backtest_engine/backtest_low_level.py` | `run_backtest()` |
| Metrics computation | `backtest_engine/results.py` | `compute_metrics()`, `persist()` |
| Multi-date train-window runner | `scripts/run_research_backtest.py` | Full script |

---

## 2. Base Algorithm Mechanisms

### position-tier-gate
| Claim | Source File |
|---|---|
| Mechanism: skips opens when position ≥ cap (=1 contract) | `execution_algos/position-tier-gate/execution_algorithm.py` |
| Always submits reduce-only (close) orders | `execution_algos/position-tier-gate/execution_algorithm.py` |
| Original hypothesis and design rationale | `execution_algos/position-tier-gate/NOTES.md` |

### aggressor-flow-gate
| Claim | Source File |
|---|---|
| Mechanism: rolling signed aggressor-flow window, 10s default, threshold=2.0 | `execution_algos/aggressor-flow-gate/execution_algorithm.py` |
| Anti-cascade `_position_flat` flag forces re-entry after any skip | `execution_algos/aggressor-flow-gate/execution_algorithm.py` |
| Original hypothesis and design rationale | `execution_algos/aggressor-flow-gate/NOTES.md` |

### vol-regime-sizer
| Claim | Source File |
|---|---|
| Mechanism: probabilistic skip based on unsigned fast/slow EWM vol ratio | `execution_algos/vol-regime-sizer/execution_algorithm.py` |
| Original hypothesis and design rationale | `execution_algos/vol-regime-sizer/NOTES.md` |

---

## 3. Base Algorithm Performance (Train Window)

All three numbers below come from `performance` object in each file.

| Algo | PnL | Sharpe | Max DD | Trades | Source File |
|---|---|---|---|---|---|
| position-tier-gate | $4,262.50 | 17.619 | -1.73% | 90,433 | `execution_algos/position-tier-gate/results/backtest-results.json` |
| aggressor-flow-gate | $1,255.50 | 5.594 | -3.32% | 107,198 | `execution_algos/aggressor-flow-gate/results/backtest-results.json` |
| vol-regime-sizer | $753.75 | 3.065 | -4.60% | 127,991 | `execution_algos/vol-regime-sizer/results/backtest-results.json` |

---

## 4. Seed Prompt (l0) — All Three Arms

All three arms start from an identical seed prompt. Copies exist at:
- `experiments/self_improving_prompt_experiment/position-tier-gate/prompts/prompt-l0.md`
- `experiments/self_improving_prompt_experiment/aggressor-flow-gate/prompts/prompt-l0.md`
- `experiments/self_improving_prompt_experiment/vol-regime-sizer/prompts/prompt-l0.md`

Content: 4-step single-pass method (read base, identify weakness, propose modification, state expected direction). No empirical validation or multi-candidate step.

---

## 5. Promoted Prompts (Kept by Gate)

These are the prompts that survived the Karpathy gate and became `.current_prompt.md` for the next loop.

| Arm | Prompt File | Loop it was promoted at | Why kept |
|---|---|---|---|
| PTG | `experiments/self_improving_prompt_experiment/position-tier-gate/prompts/prompt-l1.md` | After loop 1 | L1 KEPT; added mandatory empirical pre-check |
| PTG | `experiments/self_improving_prompt_experiment/position-tier-gate/prompts/prompt-l2.md` | After loop 2 | L2 KEPT; added one-date counterfactual probe requirement |
| AFG | `experiments/self_improving_prompt_experiment/aggressor-flow-gate/prompts/prompt-l1.md` | After loop 1 | L1 KEPT; added proposer-EDA-criticizer with 3 candidates |
| AFG | `experiments/self_improving_prompt_experiment/aggressor-flow-gate/prompts/prompt-l5.md` | After loop 5 | L5 KEPT; cascade-policy structural axis method |
| VRS | `experiments/self_improving_prompt_experiment/vol-regime-sizer/prompts/prompt-l1.md` | After loop 1 | L1 KEPT; propose-falsify-commit with 3 candidates |
| VRS | `experiments/self_improving_prompt_experiment/vol-regime-sizer/prompts/prompt-l5.md` | After loop 5 | L5 KEPT; Propose-Audit-Falsify-Commit with per-date regime audit |

---

## 6. Reverted / Proposed-but-not-kept Prompts

These proposals were written but failed the gate. The `.current_prompt.md` reverted to the prior best.

**Position-Tier-Gate:**
- `experiments/self_improving_prompt_experiment/position-tier-gate/prompts/proposed/loop-3-proposal.md` — reverted after L3
- `experiments/self_improving_prompt_experiment/position-tier-gate/prompts/proposed/loop-4-proposal.md` — reverted after L4
- `experiments/self_improving_prompt_experiment/position-tier-gate/prompts/proposed/loop-5-proposal.md` — reverted after L5
- `experiments/self_improving_prompt_experiment/position-tier-gate/prompts/proposed/loop-6-proposal.md` — reverted after L6
- `experiments/self_improving_prompt_experiment/position-tier-gate/prompts/proposed/loop-7-proposal.md` — reverted after L7

**Aggressor-Flow-Gate:**
- `experiments/self_improving_prompt_experiment/aggressor-flow-gate/prompts/proposed/loop-2-proposal.md` — reverted after L2
- `experiments/self_improving_prompt_experiment/aggressor-flow-gate/prompts/proposed/loop-3-proposal.md` — reverted after L3
- `experiments/self_improving_prompt_experiment/aggressor-flow-gate/prompts/proposed/loop-4-proposal.md` — reverted after L4
- `experiments/self_improving_prompt_experiment/aggressor-flow-gate/prompts/proposed/loop-6-proposal.md` — reverted after L6
- `experiments/self_improving_prompt_experiment/aggressor-flow-gate/prompts/proposed/loop-7-proposal.md` — reverted after L7

**Vol-Regime-Sizer:**
- `experiments/self_improving_prompt_experiment/vol-regime-sizer/prompts/proposed/loop-2-proposal.md` — reverted after L2
- `experiments/self_improving_prompt_experiment/vol-regime-sizer/prompts/proposed/loop-3-proposal.md` — reverted after L3
- `experiments/self_improving_prompt_experiment/vol-regime-sizer/prompts/proposed/loop-4-proposal.md` — reverted after L4
- `experiments/self_improving_prompt_experiment/vol-regime-sizer/prompts/proposed/loop-6-proposal.md` — reverted after L6
- `experiments/self_improving_prompt_experiment/vol-regime-sizer/prompts/proposed/loop-7-proposal.md` — reverted after L7
- `experiments/self_improving_prompt_experiment/vol-regime-sizer/prompts/proposed/loop-8-proposal.md` — reverted after L8

---

## 7. Per-Loop Metrics — Complete Source Table

All loop metrics are read from the `metrics` object in each loop JSON file. The `critic_summary`, `prompt_action`, `prompt_in`, and `prompt_out` fields are also in these files.

### Position-Tier-Gate Loop Files

| Loop | Loop JSON | Algorithm Code | NOTES.md | Reasoning Trace |
|---|---|---|---|---|
| 1 | `experiments/self_improving_prompt_experiment/position-tier-gate/per-iteration/loop-1.json` | `execution_algos/sip-ptg-l1/execution_algorithm.py` | `execution_algos/sip-ptg-l1/NOTES.md` | `experiments/self_improving_prompt_experiment/position-tier-gate/reasoning-traces/loop-1-trace.md` |
| 2 | `experiments/self_improving_prompt_experiment/position-tier-gate/per-iteration/loop-2.json` | `execution_algos/sip-ptg-l2/execution_algorithm.py` | `execution_algos/sip-ptg-l2/NOTES.md` | `experiments/self_improving_prompt_experiment/position-tier-gate/reasoning-traces/loop-2-trace.md` |
| 3 | `experiments/self_improving_prompt_experiment/position-tier-gate/per-iteration/loop-3.json` | `execution_algos/sip-ptg-l3/execution_algorithm.py` | `execution_algos/sip-ptg-l3/NOTES.md` | `experiments/self_improving_prompt_experiment/position-tier-gate/reasoning-traces/loop-3-trace.md` |
| 4 | `experiments/self_improving_prompt_experiment/position-tier-gate/per-iteration/loop-4.json` | `execution_algos/sip-ptg-l4/execution_algorithm.py` | `execution_algos/sip-ptg-l4/NOTES.md` | `experiments/self_improving_prompt_experiment/position-tier-gate/reasoning-traces/loop-4-trace.md` |
| 5 | `experiments/self_improving_prompt_experiment/position-tier-gate/per-iteration/loop-5.json` | `execution_algos/sip-ptg-l5/execution_algorithm.py` | `execution_algos/sip-ptg-l5/NOTES.md` | `experiments/self_improving_prompt_experiment/position-tier-gate/reasoning-traces/loop-5-trace.md` |
| 6 | `experiments/self_improving_prompt_experiment/position-tier-gate/per-iteration/loop-6.json` | `execution_algos/sip-ptg-l6/execution_algorithm.py` | `execution_algos/sip-ptg-l6/NOTES.md` | `experiments/self_improving_prompt_experiment/position-tier-gate/reasoning-traces/loop-6-trace.md` |
| 7 | `experiments/self_improving_prompt_experiment/position-tier-gate/per-iteration/loop-7.json` | `execution_algos/sip-ptg-l7/execution_algorithm.py` | `execution_algos/sip-ptg-l7/NOTES.md` | `experiments/self_improving_prompt_experiment/position-tier-gate/reasoning-traces/loop-7-trace.md` |
| 8 | `experiments/self_improving_prompt_experiment/position-tier-gate/per-iteration/loop-8.json` | `execution_algos/sip-ptg-l8/execution_algorithm.py` | `execution_algos/sip-ptg-l8/NOTES.md` | `experiments/self_improving_prompt_experiment/position-tier-gate/reasoning-traces/loop-8-trace.md` |

**Verified PTG metrics (from loop JSON `metrics` field):**

| Loop | PnL | vs_base_pnl_pct | sharpe_ratio | max_drawdown_pct | win_rate | trade_count | prompt_action |
|---|---|---|---|---|---|---|---|
| 1 | 4262.50 | 0.0 | 17.619 | -0.01727 | 0.37204 | 90433 | kept |
| 2 | 3774.00 | -11.460 | 19.215 | -0.00537 | 0.37492 | 81557 | kept |
| 3 | 3131.75 | -26.528 | 12.569 | -0.02272 | 0.35829 | 126678 | reverted |
| 4 | 2825.25 | -33.718 | 12.977 | -0.02175 | 0.36416 | 98270 | reverted |
| 5 | 156.00 | -96.340 | 0.600 | -0.05290 | 0.35064 | 136734 | reverted |
| 6 | 3848.00 | -9.724 | 17.090 | -0.01745 | 0.37133 | 83604 | reverted |
| 7 | 156.00 | -96.340 | 0.600 | -0.05290 | 0.35064 | 136734 | reverted |
| 8 | 4292.75 | +0.710 | 18.808 | -0.01107 | 0.37780 | 75262 | None (no-critique) |

**PTG backtest-results.json files (per-algo):**
- `execution_algos/sip-ptg-l1/results/backtest-results.json`
- `execution_algos/sip-ptg-l2/results/backtest-results.json`
- `execution_algos/sip-ptg-l3/results/backtest-results.json`
- `execution_algos/sip-ptg-l4/results/backtest-results.json`
- `execution_algos/sip-ptg-l5/results/backtest-results.json`
- `execution_algos/sip-ptg-l6/results/backtest-results.json`
- `execution_algos/sip-ptg-l7/results/backtest-results.json`
- `execution_algos/sip-ptg-l8/results/backtest-results.json`

**PTG per-date metrics (all 12 train dates):**
Each subdirectory `execution_algos/sip-ptg-l<N>/results/<YYYYMMDD>/metrics.json` holds single-date metrics.
Dates present: 20260308, 20260309, 20260310, 20260311, 20260312, 20260313, 20260315, 20260316, 20260317, 20260318, 20260319, 20260320.

---

### Aggressor-Flow-Gate Loop Files

| Loop | Loop JSON | Algorithm Code | NOTES.md | Reasoning Trace |
|---|---|---|---|---|
| 1 | `experiments/self_improving_prompt_experiment/aggressor-flow-gate/per-iteration/loop-1.json` | `execution_algos/sip-afg-l1/execution_algorithm.py` | `execution_algos/sip-afg-l1/NOTES.md` | `experiments/self_improving_prompt_experiment/aggressor-flow-gate/reasoning-traces/loop-1-trace.md` |
| 2 | `experiments/self_improving_prompt_experiment/aggressor-flow-gate/per-iteration/loop-2.json` | `execution_algos/sip-afg-l2/execution_algorithm.py` | `execution_algos/sip-afg-l2/NOTES.md` | `experiments/self_improving_prompt_experiment/aggressor-flow-gate/reasoning-traces/loop-2-trace.md` |
| 3 | `experiments/self_improving_prompt_experiment/aggressor-flow-gate/per-iteration/loop-3.json` | `execution_algos/sip-afg-l3/execution_algorithm.py` | `execution_algos/sip-afg-l3/NOTES.md` | `experiments/self_improving_prompt_experiment/aggressor-flow-gate/reasoning-traces/loop-3-trace.md` |
| 4 | `experiments/self_improving_prompt_experiment/aggressor-flow-gate/per-iteration/loop-4.json` | `execution_algos/sip-afg-l4/execution_algorithm.py` | `execution_algos/sip-afg-l4/NOTES.md` | `experiments/self_improving_prompt_experiment/aggressor-flow-gate/reasoning-traces/loop-4-trace.md` |
| 5 | `experiments/self_improving_prompt_experiment/aggressor-flow-gate/per-iteration/loop-5.json` | `execution_algos/sip-afg-l5/execution_algorithm.py` | `execution_algos/sip-afg-l5/NOTES.md` | `experiments/self_improving_prompt_experiment/aggressor-flow-gate/reasoning-traces/loop-5-trace.md` |
| 6 | `experiments/self_improving_prompt_experiment/aggressor-flow-gate/per-iteration/loop-6.json` | `execution_algos/sip-afg-l6/execution_algorithm.py` | `execution_algos/sip-afg-l6/NOTES.md` | `experiments/self_improving_prompt_experiment/aggressor-flow-gate/reasoning-traces/loop-6-trace.md` |
| 7 | `experiments/self_improving_prompt_experiment/aggressor-flow-gate/per-iteration/loop-7.json` | `execution_algos/sip-afg-l7/execution_algorithm.py` | `execution_algos/sip-afg-l7/NOTES.md` | `experiments/self_improving_prompt_experiment/aggressor-flow-gate/reasoning-traces/loop-7-trace.md` |
| 8 | `experiments/self_improving_prompt_experiment/aggressor-flow-gate/per-iteration/loop-8.json` | `execution_algos/sip-afg-l8/execution_algorithm.py` | `execution_algos/sip-afg-l8/NOTES.md` | `experiments/self_improving_prompt_experiment/aggressor-flow-gate/reasoning-traces/loop-8-trace.md` |

**Verified AFG metrics (from loop JSON `metrics` field):**

| Loop | PnL | vs_base_pnl_pct | sharpe_ratio | max_drawdown_pct | win_rate | trade_count | prompt_action |
|---|---|---|---|---|---|---|---|
| 1 | 1064.75 | -15.193 | 4.858 | -0.03372 | 0.35035 | 106967 | kept |
| 2 | 645.00 | -48.626 | 2.765 | -0.04307 | 0.35264 | 120966 | reverted |
| 3 | 714.00 | -43.130 | 3.057 | -0.04135 | 0.35070 | 115099 | reverted |
| 4 | 780.25 | -37.853 | 3.548 | -0.04070 | 0.35234 | 120148 | reverted |
| 5 | 1002.00 | +3.299 | 4.947 | -0.02932 | 0.35383 | 78442 | kept |
| 6 | 984.25 | +1.469 | 4.835 | -0.02957 | 0.35349 | 79165 | reverted |
| 7 | 669.00 | -31.031 | 3.067 | -0.03980 | 0.35327 | 96176 | reverted |
| 8 | 836.50 | -13.763 | 3.896 | -0.03702 | 0.35301 | 88329 | None (no-critique) |

**Note:** AFG l5–l8 ran on 11 dates (20260319 excluded — OOM during backtest). Source for date count: `execution_algos/sip-afg-l5/results/` (no `20260319/` subdirectory present).

**AFG backtest-results.json files:**
- `execution_algos/sip-afg-l1/results/backtest-results.json`
- `execution_algos/sip-afg-l2/results/backtest-results.json`
- `execution_algos/sip-afg-l3/results/backtest-results.json`
- `execution_algos/sip-afg-l4/results/backtest-results.json`
- `execution_algos/sip-afg-l5/results/backtest-results.json`
- `execution_algos/sip-afg-l6/results/backtest-results.json`
- `execution_algos/sip-afg-l7/results/backtest-results.json`
- `execution_algos/sip-afg-l8/results/backtest-results.json`

**AFG EDA calibration artifact (L6 only):**
- `execution_algos/sip-afg-l6/results/eda-calibration.json`

---

### Vol-Regime-Sizer Loop Files

| Loop | Loop JSON | Algorithm Code | NOTES.md | Reasoning Trace |
|---|---|---|---|---|
| 1 | `experiments/self_improving_prompt_experiment/vol-regime-sizer/per-iteration/loop-1.json` | `execution_algos/sip-vrs-l1/execution_algorithm.py` | `execution_algos/sip-vrs-l1/NOTES.md` | `experiments/self_improving_prompt_experiment/vol-regime-sizer/reasoning-traces/loop-1-trace.md` |
| 2 | `experiments/self_improving_prompt_experiment/vol-regime-sizer/per-iteration/loop-2.json` | `execution_algos/sip-vrs-l2/execution_algorithm.py` | `execution_algos/sip-vrs-l2/NOTES.md` | `experiments/self_improving_prompt_experiment/vol-regime-sizer/reasoning-traces/loop-2-trace.md` |
| 3 | `experiments/self_improving_prompt_experiment/vol-regime-sizer/per-iteration/loop-3.json` | `execution_algos/sip-vrs-l3/execution_algorithm.py` | `execution_algos/sip-vrs-l3/NOTES.md` | `experiments/self_improving_prompt_experiment/vol-regime-sizer/reasoning-traces/loop-3-trace.md` |
| 4 | `experiments/self_improving_prompt_experiment/vol-regime-sizer/per-iteration/loop-4.json` | `execution_algos/sip-vrs-l4/execution_algorithm.py` | `execution_algos/sip-vrs-l4/NOTES.md` | `experiments/self_improving_prompt_experiment/vol-regime-sizer/reasoning-traces/loop-4-trace.md` |
| 5 | `experiments/self_improving_prompt_experiment/vol-regime-sizer/per-iteration/loop-5.json` | `execution_algos/sip-vrs-l5/execution_algorithm.py` | `execution_algos/sip-vrs-l5/NOTES.md` | `experiments/self_improving_prompt_experiment/vol-regime-sizer/reasoning-traces/loop-5-trace.md` |
| 6 | `experiments/self_improving_prompt_experiment/vol-regime-sizer/per-iteration/loop-6.json` | `execution_algos/sip-vrs-l6/execution_algorithm.py` | `execution_algos/sip-vrs-l6/NOTES.md` | `experiments/self_improving_prompt_experiment/vol-regime-sizer/reasoning-traces/loop-6-trace.md` |
| 7 | `experiments/self_improving_prompt_experiment/vol-regime-sizer/per-iteration/loop-7.json` | `execution_algos/sip-vrs-l7/execution_algorithm.py` | `execution_algos/sip-vrs-l7/NOTES.md` | `experiments/self_improving_prompt_experiment/vol-regime-sizer/reasoning-traces/loop-7-trace.md` |
| 8 | `experiments/self_improving_prompt_experiment/vol-regime-sizer/per-iteration/loop-8.json` | `execution_algos/sip-vrs-l8/execution_algorithm.py` | `execution_algos/sip-vrs-l8/NOTES.md` | `experiments/self_improving_prompt_experiment/vol-regime-sizer/reasoning-traces/loop-8-trace.md` |

**Verified VRS metrics (from loop JSON `metrics` field):**

| Loop | PnL | vs_base_pnl_pct | sharpe_ratio | max_drawdown_pct | win_rate | trade_count | prompt_action |
|---|---|---|---|---|---|---|---|
| 1 | 1062.25 | +40.929 | 4.185 | -0.04275 | 0.35392 | 127923 | kept |
| 2 | 723.25 | -4.046 | 2.986 | -0.04575 | 0.35306 | 126948 | reverted |
| 3 | 868.75 | +15.257 | 3.536 | -0.04552 | 0.35389 | 125936 | reverted |
| 4 | 439.00 | -41.758 | 1.772 | -0.04855 | 0.35153 | 130227 | reverted |
| 5 | 1471.75 | +95.257 | 13.718 | -0.01637 | 0.35465 | 90582 | kept |
| 6 | 780.50 | +3.549 | 3.386 | -0.03862 | 0.35433 | 97186 | reverted |
| 7 | 1471.75 | +95.257 | 13.718 | -0.01637 | 0.35465 | 90582 | reverted |
| 8 | 377.25 | -49.950 | 2.788 | -0.02697 | 0.35044 | 61816 | reverted |

**Note:** VRS L3 shows +15.257% vs base but was still REVERTED — the gate compares against the running best (sip-vrs-l1 at +40.929%), not against the base itself. L3 did not improve on ≥3 of 5 metrics vs L1.

**Note:** VRS l5–l8 ran on 11 dates (20260319 excluded — OOM). Source: `execution_algos/sip-vrs-l5/results/` (no `20260319/` subdirectory).

**VRS backtest-results.json files:**
- `execution_algos/sip-vrs-l1/results/backtest-results.json`
- `execution_algos/sip-vrs-l2/results/backtest-results.json`
- `execution_algos/sip-vrs-l3/results/backtest-results.json`
- `execution_algos/sip-vrs-l4/results/backtest-results.json`
- `execution_algos/sip-vrs-l5/results/backtest-results.json`
- `execution_algos/sip-vrs-l6/results/backtest-results.json`
- `execution_algos/sip-vrs-l7/results/backtest-results.json`
- `execution_algos/sip-vrs-l8/results/backtest-results.json`

---

## 8. Per-Arm Program Databases

Append-only records written by each critique phase. Include loop, algo_id, status, all metrics, prompt_action, timestamp.

- `experiments/self_improving_prompt_experiment/position-tier-gate/program_database.json`
- `experiments/self_improving_prompt_experiment/aggressor-flow-gate/program_database.json`
- `experiments/self_improving_prompt_experiment/vol-regime-sizer/program_database.json`

---

## 9. Critic Summaries — Source Locations and Quotes

All critic summaries live in the `critic_summary` field of each loop's JSON file. Quotes in the briefing document come from these exact fields.

### Position-Tier-Gate Critic Summaries

| Loop | File | Key phrase |
|---|---|---|
| L1 | `experiments/self_improving_prompt_experiment/position-tier-gate/per-iteration/loop-1.json` | "The seed method had no empirical pre-check step — the researcher reasoned about the oracle's emission process in pure prose..." |
| L2 | `experiments/self_improving_prompt_experiment/position-tier-gate/per-iteration/loop-2.json` | "...it never measures the counterfactual, the actual aggregate consequence of acting on that class..." |
| L3 | `experiments/self_improving_prompt_experiment/position-tier-gate/per-iteration/loop-3.json` | "...single-candidate probe correctly fired FAIL on loop-3's tight-spread override but left the researcher with no escape valve..." |
| L4 | `experiments/self_improving_prompt_experiment/position-tier-gate/per-iteration/loop-4.json` | "...empirical pre-check only validates that the targeted event class is non-empty in cached artifacts — it never measures the aggregate consequence..." |
| L5 | `experiments/self_improving_prompt_experiment/position-tier-gate/per-iteration/loop-5.json` | "...required an empirical pre-check that validated event-class frequency (N=7,535 fires/day for cap=2 paired OPENs — correctly non-vacuous) but had no gate for effect direction..." |
| L6 | `experiments/self_improving_prompt_experiment/position-tier-gate/per-iteration/loop-6.json` | "...required a static artifact count that validated event-class frequency (950/day for post-zero-flip OPENs) but could not capture dynamic cascade effects..." |
| L7 | `experiments/self_improving_prompt_experiment/position-tier-gate/per-iteration/loop-7.json` | "...lets a researcher greenlight a hypothesis on a STUB probe that does not actually execute the proposed mechanism — the loop-7 stub run produced $65.50 == $65.50 (PASS on all 3 conditions)..." |
| L8 | `experiments/self_improving_prompt_experiment/position-tier-gate/per-iteration/loop-8.json` | `critic_summary: null` (no critique run — loop 8 is the final loop) |

### Aggressor-Flow-Gate Critic Summaries

| Loop | File | Key phrase |
|---|---|---|
| L1 | `experiments/self_improving_prompt_experiment/aggressor-flow-gate/per-iteration/loop-1.json` | "...allowed the researcher to commit to a key quantitative parameter (flow_threshold=0.6) derived from an explicitly stated false assumption (uniform trade-arrival density)..." |
| L2 | `experiments/self_improving_prompt_experiment/aggressor-flow-gate/per-iteration/loop-2.json` | "...EDA sampled at TradeTick events where |net_v| >= 2 but never re-sampled at the strategy's order-arrival cadence, so the t=-41 SELL-skip-inversion result was valid at tick cadence but non-transferable..." |
| L3 | `experiments/self_improving_prompt_experiment/aggressor-flow-gate/per-iteration/loop-3.json` | "...permits the researcher to commit to a hypothesis whose central premise about WHICH orders the base over-skips or under-skips is never verified against the actual order stream..." |
| L4 | `experiments/self_improving_prompt_experiment/aggressor-flow-gate/per-iteration/loop-4.json` | "...lets the researcher commit a key quantitative parameter (frac_threshold=0.25) by proportional reasoning without measuring the actual distribution of |net_flow|/total_volume..." |
| L5 | `experiments/self_improving_prompt_experiment/aggressor-flow-gate/per-iteration/loop-5.json` | "...produced a positive-delta winner via structural insight (cascade policy axis instead of decision-function axis), but committed BOTH the relaxation factor AND the streak cap without empirical calibration..." |
| L6 | `experiments/self_improving_prompt_experiment/aggressor-flow-gate/per-iteration/loop-6.json` | "...instructed the researcher to calibrate a parameter from offline DBN replay, but the replay used worst-case assumptions about trade-arrival density at the skip-arrival cadence..." |
| L7 | `experiments/self_improving_prompt_experiment/aggressor-flow-gate/per-iteration/loop-7.json` | "...goalpost misalignment. The seed prompt-l0 method tells the researcher to read base, identify a base weakness, and predict P&L vs base — but the keep/discard gate evaluates vs the running best..." |
| L8 | `experiments/self_improving_prompt_experiment/aggressor-flow-gate/per-iteration/loop-8.json` | `critic_summary: null` (no critique run — loop 8 is the final loop) |

### Vol-Regime-Sizer Critic Summaries

| Loop | File | Key phrase |
|---|---|---|
| L1 | `experiments/self_improving_prompt_experiment/vol-regime-sizer/per-iteration/loop-1.json` | "...seed prompt's single-pass shape rewards confidence over evidence — the first plausible weakness becomes the hypothesis with no empirical check before implementation..." |
| L2 | `experiments/self_improving_prompt_experiment/vol-regime-sizer/per-iteration/loop-2.json` | "...sample selection bias — loop 2 ran falsification on only the two worst-loss train dates, which guaranteed an adverse signal in the sample..." |
| L3 | `experiments/self_improving_prompt_experiment/vol-regime-sizer/per-iteration/loop-3.json` | "...method anchors every candidate to the parent's mechanism only — it has no machinery to use the running-best (champion) as a starting point..." |
| L4 | `experiments/self_improving_prompt_experiment/vol-regime-sizer/per-iteration/loop-4.json` | "...allows a hypothesis to ship without recorded falsification artifacts and without parameters that are empirically tied to the parent's CSVs..." |
| L5 | `experiments/self_improving_prompt_experiment/vol-regime-sizer/per-iteration/loop-5.json` | "...previous method's falsification step calibrates on one or two hand-picked train dates, with no check that the candidate's binding feature has the same distribution on the other dates..." |
| L6 | `experiments/self_improving_prompt_experiment/vol-regime-sizer/per-iteration/loop-6.json` | "...hard 'parent-CSVs only' restriction in step 3 had exhausted the cheap CSV-derivable axes (direction L1, time-of-day L2, regime persistence L3, trendiness L4, spread L5)..." |
| L7 | `experiments/self_improving_prompt_experiment/vol-regime-sizer/per-iteration/loop-7.json` | "...audit and falsification both run on the parent's CSVs, with no machinery to detect that a candidate's binding feature has already been removed by the champion's filter..." |
| L8 | `experiments/self_improving_prompt_experiment/vol-regime-sizer/per-iteration/loop-8.json` | `critic_summary: null` (no critique run — loop 8 is the final loop) |

---

## 10. Compute / Token Usage Sources

Token usage and duration come from the `tokens_used`, `duration_seconds`, `critic_tokens_used`, `critic_duration_seconds` fields in each loop JSON. Tokens were not backfilled for PTG loops 2–8 or VRS loops 1–3 (hook not active for those runs).

**Analysis using this data:** See `docs/sip-experiment-briefing.md` §10 "Compute Cost vs. Performance" for the full Chart 1 (research tokens vs PnL) and Chart 2 (critic tokens vs next-loop PnL) analysis, recommended visualisation approach, and interpretation notes.

| Arm + Loop | Research tokens | Research duration | Critic tokens | Critic duration | Source |
|---|---|---|---|---|---|
| PTG L1 | 84,263 total | 1,100.1s | null | null | `position-tier-gate/per-iteration/loop-1.json` |
| PTG L2–L8 | null | null | null | null | Hook not active; no backfill |
| AFG L1 | 336,480 total | 4,390.3s | 55,497 total | 212.8s | `aggressor-flow-gate/per-iteration/loop-1.json` |
| AFG L2 | 56,657 total | 136.8s | 79,568 total | 319.1s | `aggressor-flow-gate/per-iteration/loop-2.json` |
| AFG L3 | 47,710 total | 123.9s | 77,662 total | 250.5s | `aggressor-flow-gate/per-iteration/loop-3.json` |
| AFG L4 | 43,366 total | 103.5s | 75,782 total | 213.4s | `aggressor-flow-gate/per-iteration/loop-4.json` |
| AFG L5 | 181,033 total | 3,284.3s | 72,565 total | 256.2s | `aggressor-flow-gate/per-iteration/loop-5.json` |
| AFG L6 | 64,861 total | 8,149.9s* | 62,063 total | 214.7s | `aggressor-flow-gate/per-iteration/loop-6.json` |
| AFG L7 | 154,883 total | 3,362.0s | 51,491 total | 247.7s | `aggressor-flow-gate/per-iteration/loop-7.json` |
| AFG L8 | 62,339 total | 200.7s | 24,767 total | 7.7s | `aggressor-flow-gate/per-iteration/loop-8.json` |
| VRS L1–L3 | null | null | null | null | Hook not active; no backfill |
| VRS L4 | 67,351 total | 265.7s | null | null | `vol-regime-sizer/per-iteration/loop-4.json` |
| VRS L5 | 153,084 total | 3,517.7s | 72,818 total | 335.6s | `vol-regime-sizer/per-iteration/loop-5.json` |
| VRS L6 | 209,532 total | 4,282.1s | 97,755 total | 682.7s | `vol-regime-sizer/per-iteration/loop-6.json` |
| VRS L7 | 66,747 total | 267.9s | 118,361 total | 1,229.5s | `vol-regime-sizer/per-iteration/loop-7.json` |
| VRS L8 | 86,574 total | 471.7s | null | null | `vol-regime-sizer/per-iteration/loop-8.json` |

*AFG L6 duration (8,149s) is a backtest-engine outlier — slow dates, not slow LLM thinking.

Token breakdown structure in each JSON: `{"input": N, "output": N, "cache_creation": N, "cache_read": N, "total": N}`

**Chart 2 source pairs** (critic loop N → next-loop PnL, used in briefing §10):

| Critic loop JSON | `critic_tokens_used.total` | Next-loop JSON | `metrics.vs_base_pnl_pct` |
|---|---|---|---|
| `aggressor-flow-gate/per-iteration/loop-1.json` | 55,497 | `loop-2.json` | -48.626 |
| `aggressor-flow-gate/per-iteration/loop-2.json` | 79,568 | `loop-3.json` | -43.130 |
| `aggressor-flow-gate/per-iteration/loop-3.json` | 77,662 | `loop-4.json` | -37.853 |
| `aggressor-flow-gate/per-iteration/loop-4.json` | 75,782 | `loop-5.json` | +3.299 |
| `aggressor-flow-gate/per-iteration/loop-5.json` | 72,565 | `loop-6.json` | +1.469 |
| `aggressor-flow-gate/per-iteration/loop-6.json` | 62,063 | `loop-7.json` | -31.031 |
| `aggressor-flow-gate/per-iteration/loop-7.json` | 51,491 | `loop-8.json` | -13.763 |
| `vol-regime-sizer/per-iteration/loop-5.json` | 72,818 | `loop-6.json` | +3.549 |
| `vol-regime-sizer/per-iteration/loop-6.json` | 97,755 | `loop-7.json` | +95.257 |
| `vol-regime-sizer/per-iteration/loop-7.json` | 118,361 | `loop-8.json` | -49.950 |

---

## 11. Specific Failure Mode Evidence Sources

### FM-1: Empty Event Class (PTG L1)
- **Critic diagnosis:** `experiments/self_improving_prompt_experiment/position-tier-gate/per-iteration/loop-1.json` → `critic_summary`
- **Researcher trace:** `experiments/self_improving_prompt_experiment/position-tier-gate/reasoning-traces/loop-1-trace.md`
- **Algorithm (identity transform):** `execution_algos/sip-ptg-l1/execution_algorithm.py`

### FM-2: Counterfactual Blindness — AFG L2 (EDA t-stat = -41.46)
- **EDA result and t-statistic:** `experiments/self_improving_prompt_experiment/aggressor-flow-gate/reasoning-traces/loop-2-trace.md` (§ "Where the method helped")
- **Critic diagnosis (cadence mismatch):** `experiments/self_improving_prompt_experiment/aggressor-flow-gate/per-iteration/loop-2.json` → `critic_summary`
- **P&L outcome (645.00 vs 1255.50):** `experiments/self_improving_prompt_experiment/aggressor-flow-gate/per-iteration/loop-2.json` → `metrics.realized_pnl` and `execution_algos/aggressor-flow-gate/results/backtest-results.json` → `performance.realized_pnl`
- **Algorithm (SELL-gate disabled):** `execution_algos/sip-afg-l2/execution_algorithm.py`

### FM-2: Counterfactual Blindness — PTG L2 (wide-spread EDA)
- **Researcher trace (wide-spread analysis):** `experiments/self_improving_prompt_experiment/position-tier-gate/reasoning-traces/loop-2-trace.md`
- **Critic diagnosis:** `experiments/self_improving_prompt_experiment/position-tier-gate/per-iteration/loop-2.json` → `critic_summary`
- **Algorithm (spread guard):** `execution_algos/sip-ptg-l2/execution_algorithm.py`

### FM-3: Single-Candidate Myopia (AFG L1–L4 all on decision-function axis)
- **Evidence:** All four algo codes modify `on_order()` decision logic only; see `execution_algos/sip-afg-l1/`, `sip-afg-l2/`, `sip-afg-l3/`, `sip-afg-l4/execution_algorithm.py`
- **Critic diagnosis (loop 3):** `experiments/self_improving_prompt_experiment/aggressor-flow-gate/per-iteration/loop-3.json` → `critic_summary`
- **L5 structural break (cascade-policy):** `execution_algos/sip-afg-l5/execution_algorithm.py` (first algo to modify `_skip_streak` state machine rather than gate condition)

### FM-4: Sampling Bias (VRS L2)
- **Critic diagnosis:** `experiments/self_improving_prompt_experiment/vol-regime-sizer/per-iteration/loop-2.json` → `critic_summary`
- **Researcher trace (worst-date selection):** `experiments/self_improving_prompt_experiment/vol-regime-sizer/reasoning-traces/loop-2-trace.md`

### FM-5: Regime Heterogeneity (VRS L5 critic)
- **Critic diagnosis:** `experiments/self_improving_prompt_experiment/vol-regime-sizer/per-iteration/loop-5.json` → `critic_summary`
- **New method introduced:** `experiments/self_improving_prompt_experiment/vol-regime-sizer/prompts/prompt-l5.md` (Step 3: Binding-feature regime audit)

### FM-6: Champion Redundancy (VRS L3, L7)
- **Critic diagnosis (L3):** `experiments/self_improving_prompt_experiment/vol-regime-sizer/per-iteration/loop-3.json` → `critic_summary`
- **Critic diagnosis (L7):** `experiments/self_improving_prompt_experiment/vol-regime-sizer/per-iteration/loop-7.json` → `critic_summary`

### FM-7: Stub-Mode Degeneration (PTG L7)
- **Critic diagnosis:** `experiments/self_improving_prompt_experiment/position-tier-gate/per-iteration/loop-7.json` → `critic_summary`
- **Quote ("$65.50 == $65.50 PASS"):** `experiments/self_improving_prompt_experiment/position-tier-gate/per-iteration/loop-7.json` → `critic_summary`
- **Researcher trace (stub design):** `experiments/self_improving_prompt_experiment/position-tier-gate/reasoning-traces/loop-7-trace.md`
- **Identical outcome L5 vs L7 ($156, 136,734 trades):** `experiments/self_improving_prompt_experiment/position-tier-gate/per-iteration/loop-5.json` and `loop-7.json` → `metrics`

### FM-8: Uncalibrated Parameters (AFG L1)
- **Critic diagnosis (flow_threshold=0.6, uniform arrival assumption):** `experiments/self_improving_prompt_experiment/aggressor-flow-gate/per-iteration/loop-1.json` → `critic_summary`
- **Researcher trace (tau=3s reasoning):** `experiments/self_improving_prompt_experiment/aggressor-flow-gate/reasoning-traces/loop-1-trace.md`

---

## 12. L5 Inflection Pattern Evidence

| Claim | Source |
|---|---|
| AFG L1–L4 all negative (range -48.6% to -15.2%) | `experiments/self_improving_prompt_experiment/aggressor-flow-gate/per-iteration/loop-{1,2,3,4}.json` → `metrics.vs_base_pnl_pct` |
| AFG L5 first positive (+3.3%) | `experiments/self_improving_prompt_experiment/aggressor-flow-gate/per-iteration/loop-5.json` → `metrics.vs_base_pnl_pct` |
| VRS L1 positive (+40.9%) then L2–L4 regressed, L5 breakthrough (+95.3%) | `experiments/self_improving_prompt_experiment/vol-regime-sizer/per-iteration/loop-{1,2,3,4,5}.json` → `metrics.vs_base_pnl_pct` |
| PTG L5 catastrophic (-96.3%) but critic's L5 diagnosis led to L8's +0.7% | `position-tier-gate/per-iteration/loop-5.json` → `metrics.vs_base_pnl_pct` and `loop-7.json` → `critic_summary` and `loop-8.json` → `metrics.vs_base_pnl_pct` |

---

## 13. Key Algorithm Mechanism Sources

### sip-vrs-l5 (best overall, +95.3%)
- **Layer 1 (signed headwind, from L1):** `execution_algos/sip-vrs-l1/execution_algorithm.py`
- **Layer 2 (wide-spread skip, >1.5 ticks):** `execution_algos/sip-vrs-l5/execution_algorithm.py`
- **Hypothesis:** `execution_algos/sip-vrs-l5/NOTES.md`
- **Reasoning trace:** `experiments/self_improving_prompt_experiment/vol-regime-sizer/reasoning-traces/loop-5-trace.md`
- **Metrics (PnL 1471.75, Sharpe 13.718, MDD -0.01637):** `experiments/self_improving_prompt_experiment/vol-regime-sizer/per-iteration/loop-5.json` → `metrics` / `execution_algos/sip-vrs-l5/results/backtest-results.json`

### sip-ptg-l8 (best risk-adjusted PTG, +0.7%)
- **Mechanism (rolling 20-trade win-rate gate, <35% threshold):** `execution_algos/sip-ptg-l8/execution_algorithm.py`
- **Hypothesis:** `execution_algos/sip-ptg-l8/NOTES.md`
- **Reasoning trace:** `experiments/self_improving_prompt_experiment/position-tier-gate/reasoning-traces/loop-8-trace.md`
- **Metrics (PnL 4292.75, Sharpe 18.808, MDD -0.01107):** `experiments/self_improving_prompt_experiment/position-tier-gate/per-iteration/loop-8.json` → `metrics` / `execution_algos/sip-ptg-l8/results/backtest-results.json`

### sip-afg-l5 (best AFG, +3.3%)
- **Mechanism (graduated skip-streak counter, streak=1 → 3.0x threshold, streak≥2 → unconditional):** `execution_algos/sip-afg-l5/execution_algorithm.py`
- **Hypothesis:** `execution_algos/sip-afg-l5/NOTES.md`
- **Reasoning trace:** `experiments/self_improving_prompt_experiment/aggressor-flow-gate/reasoning-traces/loop-5-trace.md`
- **Metrics (PnL 1002.00, Sharpe 4.947, MDD -0.02932):** `experiments/self_improving_prompt_experiment/aggressor-flow-gate/per-iteration/loop-5.json` → `metrics` / `execution_algos/sip-afg-l5/results/backtest-results.json`

### sip-ptg-l5 and sip-ptg-l7 (identical catastrophic failure, -96.3%)
- **Both:** `execution_algos/sip-ptg-l5/execution_algorithm.py`, `execution_algos/sip-ptg-l7/execution_algorithm.py`
- **Metrics (both: PnL 156.00, trades 136,734):** `position-tier-gate/per-iteration/loop-5.json` and `loop-7.json` → `metrics`

---

## 14. VRS L3 Gate-Revert Nuance

VRS L3 showed +15.3% vs the VRS base algorithm but was still REVERTED. This is because the gate compares against the **running best** (sip-vrs-l1 at +40.9%), not against the base.

- **L3 vs_base_pnl_pct (+15.3%):** `experiments/self_improving_prompt_experiment/vol-regime-sizer/per-iteration/loop-3.json` → `metrics.vs_base_pnl_pct`
- **L1 as running best (40.9%):** `experiments/self_improving_prompt_experiment/vol-regime-sizer/per-iteration/loop-1.json` → `metrics.vs_base_pnl_pct`
- **Gate logic (majority-rules across 5 metrics vs running best):** `.claude/agents/sip-researcher.md` → Critique Procedure §5

---

## 15. File Structure Reference

```
execution_algos/
  position-tier-gate/
    execution_algorithm.py          ← base PTG algorithm
    NOTES.md                        ← base PTG hypothesis
    results/
      backtest-results.json         ← aggregate train-window metrics
      <YYYYMMDD>/
        metrics.json                ← per-date metrics
  aggressor-flow-gate/              ← same structure
  vol-regime-sizer/                 ← same structure
  sip-ptg-l{1..8}/                  ← same structure for each SIP variant
  sip-afg-l{1..8}/
  sip-vrs-l{1..8}/

experiments/self_improving_prompt_experiment/
  position-tier-gate/
    per-iteration/
      loop-{1..8}.json              ← loop metrics + critic_summary + prompt_in/out
    reasoning-traces/
      loop-{1..8}-trace.md          ← researcher self-assessment per loop
    prompts/
      prompt-l0.md                  ← seed prompt (shared starting point)
      prompt-l1.md                  ← promoted after loop 1
      prompt-l2.md                  ← promoted after loop 2 (PTG only)
      proposed/
        loop-{1..7}-proposal.md     ← all proposals (kept and reverted)
    program_database.json           ← per-arm append-only record
  aggressor-flow-gate/              ← same structure; prompt-l5.md also exists
  vol-regime-sizer/                 ← same structure; prompt-l5.md also exists

.claude/agents/
  sip-researcher.md                 ← full agent definition (phases, gate, schema)

research/
  config.yaml                       ← all hyperparameters
  program_database.json             ← global append-only research log

docs/
  OBJECTIVE.md                      ← full research brief
  sip-experiment-briefing.md        ← analysis document (created this session)
  sip-presentation-outline.md       ← slide outline (created this session)
  sip-sources-appendix.md           ← this document
```

---

## 16. OOS Results — Source Locations (Merged)

*OOS results are merged. All pending-OOS placeholders across the three docs are filled.*

### Pipeline (how the data was produced)

```
1. git push origin snapshots/<algo-id>          ← triggers GitHub Actions
2. .github/workflows/snapshot-execution-algo.yml ← packages and uploads to S3
3. Lambda evaluator                              ← runs backtest on test window
4. evaluate skill (.claude/skills/evaluate/SKILL.md) ← fetches report, merges into backtest-results.json
```

Test window dates: 2026-03-26 to 2026-04-06 — **10 trading days** (`sharpe_n_days = 10`), per the `period.test_dates` list in each OOS file and `research/config.yaml` → `data_window.test`.

### OOS Result Files (`evaluation_type: oos_local`)

| Algo | Status | OOS source file | Backtested |
|---|---|---|---|
| sip-vrs-l5 | **MERGED** | `oos-results/sip-vrs-l5.json` | 2026-05-28 |
| sip-ptg-l8 | **MERGED** | `oos-results/sip-ptg-l8.json` | 2026-05-27 |
| sip-afg-l5 | **MERGED** | `oos-results/sip-afg-l5.json` | 2026-05-27 |
| sip-vrs-l7 | **MERGED** (identical to sip-vrs-l5 — rediscovery) | `oos-results/sip-vrs-l7.json` | 2026-05-26 |

**Base-algorithm OOS files** (used to recompute the **vs-own-base** percentages, since each variant file's `vs_baseline_pnl_pct` is measured against `simple`, not the arm base):

| Base algo | OOS source file | OOS PnL | Used as base for |
|---|---|---|---|
| vol-regime-sizer | `oos-results/vol-regime-sizer.json` | $2,052.50 | sip-vrs-l5 (+71.3%) |
| position-tier-gate | `oos-results/position-tier-gate.json` | $4,431.50 | sip-ptg-l8 (−4.0%) |
| aggressor-flow-gate | `oos-results/aggressor-flow-gate.json` | $2,071.75 | sip-afg-l5 (−17.2%) |

### `performance_oos` schema (real values, sip-vrs-l5)

Each OOS file carries a `performance_oos` object. Example (`oos-results/sip-vrs-l5.json`):

```json
{
  "algo_name": "sip-vrs-l5",
  "evaluation_type": "oos_local",
  "baseline": "simple",
  "sharpe_metric_version": "v2",
  "performance_oos": {
    "realized_pnl":            3515.25,
    "sharpe_ratio":            21.34,
    "sharpe_n_days":           10,
    "max_drawdown_pct":        -0.00522,
    "win_rate":                0.36423,
    "trade_count":             157556,
    "mean_slippage":           0.0,
    "vs_baseline_pnl_pct":     129.08,          // vs `simple` baseline
    "vs_baseline_is_bps":      -45.26,
    "vs_baseline_slippage_pct": 0.0
  }
}
```

**Important:** `vs_baseline_pnl_pct` is vs `simple`. The "vs base" numbers in the briefing/outline (+71.3% / −4.0% / −17.2%) are recomputed as `variant_PnL / base_OOS_PnL − 1` from the base files above, to stay comparable with the train `vs_base_pnl_pct` figures.

### Filled-in tracker (verification)

| Marker location | File | Status |
|---|---|---|
| §2 setup table (test window row) | `sip-experiment-briefing.md` | Filled — "10 trading days; results merged" |
| §6 sip-vrs-l5 / sip-ptg-l8 / sip-afg-l5 blocks | `sip-experiment-briefing.md` | Filled with two-baseline OOS tables + verdicts |
| §9 Paper gaps table + strongest claim | `sip-experiment-briefing.md` | Updated to mixed/honest verdict |
| §10 (was update guide) | `sip-experiment-briefing.md` | Converted to results log |
| §13 EHL question 1 | `sip-experiment-briefing.md` | Updated to "OOS is in: [summary]" |
| Slide 9 / 10 / 11 / 8 | `sip-presentation-outline.md` | OOS columns/lines filled |
| Slide 14 "What's missing" + publishable | `sip-presentation-outline.md` | OOS bullet moved/qualified |
| Slide 15 signal assessment | `sip-presentation-outline.md` | Replaced with OOS summary |
| Appendix A6 | `sip-presentation-outline.md` | Verdict table filled |
| This section (§16) | `sip-sources-appendix.md` | Filled |
