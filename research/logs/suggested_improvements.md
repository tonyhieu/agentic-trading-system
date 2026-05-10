# Research-Pipeline Audit — 2026-05-09

**Source trace**: `research/agent_traces/run_20260509T220530Z.md`
**Source iteration**: `spread-filter`, status=FAIL, +2.25% pnl vs simple, 5510 trades.
**Cost of this single run**: 1.085M tokens (113K cache_creation + 955K cache_read + 17K output), 153.6s wall-clock by the SubagentStop hook, **10 spread-filter run dirs + 9 simple run dirs committed** (~29 MB of CSV bloat into `git`).

The researcher agent completed its iteration. Its self-reported observations are reproduced verbatim in the trace's OBSERVATIONS section. This audit cross-references those with static pipeline analysis to surface what the agent could not see from inside its own run.

---

## 1. Concrete waste in this iteration (evidence-grounded)

| # | What happened | Evidence | Cost |
|---|---|---|---|
| 1.1 | 10 `spread-filter` run dirs created for what should have been 3 backtests (one per train date) | `ls execution_algos/spread-filter/results/` shows runs at 22:16:57, 22:17:15, 22:18:47, 22:19:06, 22:19:38, 22:19:58, 22:20:28, 22:21:55, 22:23:12, 22:24:25 | ~7 wasted backtests on this algo |
| 1.2 | First two runs produced 0 trades | `metrics.json` of 22:16:57 shows `trade_count: 0`, `fill_count: 0`, `realized_pnl: null` | 2 backtests wasted on the `exec_id="MY_GENERIC_ALGO"` footgun (default `exec_id` was `"SPREAD_FILTER"` → orders not routed) |
| 1.3 | OOM crashes on sequential dates forced per-date restarts | Trace OBSERVATIONS #2: "engine.dispose() may not free all native memory" → reliable exit 134 | ~5 wasted backtests on retry |
| 1.4 | All 10 spread-filter runs (including the empty-trade ones) committed to git | `git show 71647ce --stat` lists ~67 files, ~29 MB CSVs | Permanent repo bloat. After 30 iterations the `.git` directory will be ~1 GB just from result CSVs that are 100% reproducible from `metadata.json` + a backtest call. |
| 1.5 | Baseline (`simple`) re-run on the same dates as prior iterations | `simple_execution_strategy/results/` already had per-date runs from the 5 prior iterations | All 3 baseline runs were re-runs of identical compute (same dates, same strategy block — deterministic with `seed=42`). 50% of this iteration's backtest budget was spent re-deriving a known answer. |

**Total**: this iteration intended 6 backtests (3 dates × 2 algos). It actually executed ≥17 (10 algo + ≥7 baseline retries visible in the simple_execution_strategy results dir). Roughly 3× the necessary compute and storage, all of it captured in a single git commit.

---

## 2. Boot-phase redundancy (every iteration)

The agent's first 4 reads are identical across all 6 iterations to date:

| File | Lines | Re-reads |
|---|---|---|
| `docs/OBJECTIVE.md` | 445 | 6/6 |
| `research/config.yaml` | 77 | 6/6 |
| `research/program_database.json` | grows monotonically | 6/6 |
| `research/NOTES.md` | grows monotonically | 6/6 |

This is ~1000 lines of static context re-loaded into a fresh subagent on every invocation. Combined with the four `skills/*/SKILL.md` files (preloaded by frontmatter — but the agent re-read at least one mid-run for the `MY_GENERIC_ALGO` lookup, see trace OBSERVATIONS #3), the boot footprint dominates the 955K `cache_read` figure.

---

## 3. Hidden assumptions and silent regime breaks

### 3.1 Sigma change (`0.5 → 5`) is invisible to the program database

Commit `ab2360b` ("minor fixes") changed `strategy.kwargs.sigma` from 0.5 to 5. Effect: oracle win rate dropped from ~84% (prior 5 entries) to ~48% (this entry). **The program-database schema records `baseline` but no fingerprint of `strategy.kwargs`.** Future agents will read entries 1-5 and entry 6 as if they're comparable; they aren't. The agent's defense relies on prose in NOTES.md, which is easy to skip.

### 3.2 Slippage axis is structurally uninformative

The fill model produces `mean_slippage = 0.0` on every backtest (existing NOTE from 2026-04-30). The pass gate's `max_slippage_regression_pct: 5.0` axis can therefore never fire. Every iteration has carried this no-op as if it were a real constraint. The two-axis gate is effectively single-axis, and the prose in OBJECTIVE.md §4 still describes both axes as live. 6/6 entries record `vs_baseline_slippage_pct: 0.0`.

### 3.3 Loop-cap enforcement is theatre

`stop_after_consecutive_failures: 3` is supposed to stop dead-end exploration. Looking at the database:
- After cap-boost (FAIL #1) — continued
- After twap-defer (FAIL #2) — continued
- After imbalance-skip (FAIL #3) — should have refused; continued
- After momentum-skip (FAIL #4) — should have refused; continued
- After signal-consensus (FAIL #5) — agent self-noted the violation, "research continued per explicit human invocation"
- After spread-filter (FAIL #6) — same override path used in this run

Either the cap is wrong (and should be raised or removed), or its enforcement is purely advisory (and should be promoted to a hard refusal). What's there now is the worst of both worlds: a rule that's mentioned, ignored, and adds reasoning friction every time.

### 3.4 The exec-algo cannot see signal quality

OBJECTIVE.md restricts the agent from inspecting `strategies/`, but `cfg["strategy"]["kwargs"]` exposes `sigma` numerically without semantics. The agent has no documented model of what `sigma=5` means for execution-algorithm design, so it must learn empirically (trace OBSERVATIONS #6: "the exec algo is flying blind with respect to signal quality"). Every prior FAILed approach has been a book-state filter for this reason — there's no other lever the agent can pull.

This is the most important pipeline gap. The research problem ("find an execution edge given an opaque signal") is structurally harder than the research the OBJECTIVE.md describes ("research execution algorithms that better execute a signal"). The signal is not just opaque — it's blackboxed at decision time too.

---

## 4. Missing infrastructure

| Gap | Symptom | Iterations affected |
|---|---|---|
| No `latest_metrics(algo_id)` helper in `backtest_engine` | Every iteration reimplements the sort-result-dirs-read-last-metrics.json pattern. The snapshot skill SKILL.md ships the implementation as boilerplate code. | 6/6 |
| No `aggregate_metrics(...)` helper | Every iteration reimplements the per-date aggregation rules from `snapshot/SKILL.md §3` inline. | 6/6 |
| No baseline cache | The simple baseline runs identically across iterations (deterministic, same data, same kwargs). Each iteration recomputes it from scratch. | 6/6 |
| `exec_id` defaults to `"MY_GENERIC_ALGO"` only inside `run_backtest()` for the `simple` algo | Every new algo author trips on this. The skill mentions it but the default arg is per-algo. | This iteration: 2 wasted runs (entry 1.2). |
| Sequential backtests OOM | Memory not freed between dates in one process; reliably exits 134 on this host. No documented per-date subprocess pattern. | This iteration: ~5 wasted runs. |
| Nautilus log volume | Each backtest emits 15-20 MB of stderr; the env-var override doesn't take effect (trace OBSERVATIONS #5). | 6/6 |
| `cap-boost/results/` has been wiped | Empty directory, no record of the 1 backtest that produced its $42.71 score. | Reproducibility lost for entry #1. |
| No JSON-schema validation of `program_database.json` | Entries 1-4 lack a `meta` block; entries 5-6 have it. Drift goes undetected. | DB integrity. |
| No "snapshot status" tracking | If a future iteration PASSes, the only record of "did we push the snapshot, did we retrieve OOS" lives in S3 + git branches, not in the database. The follow-up `evaluate` invocation has no canonical place to look. | All future PASS iterations. |
| Result CSVs are not in `.gitignore` | 29 MB committed in this iteration alone; `.git/` is already 170 MB. | All iterations forever. |
| No setup self-test | The 2026-04-29 NOTE shows an aborted run because `aws` wasn't installed; the 2026-05-07 NOTE shows another because `simple_execution_strategy` was deleted. Both were silent until `run_backtest()` raised. | 2 aborted iterations on record. |

---

## 5. Over- and under-specified items in OBJECTIVE.md

| Spot | Problem |
|---|---|
| §4 "within `close_margin_pct` of either gate condition" | Ambiguous between "delta within 2pp of 5%" (CLOSE = [3%, 5%)) and "delta within 2pp of passing the gate" (CLOSE = [3%, 7%]). Trace OBSERVATIONS #8 used the first; nothing in the doc disambiguates. |
| Snapshot skill §3 "Sharpe — mean of per-date Sharpe (or recompute…)" | Per-date Sharpe under the zero-slippage fill model is 100-300, dominated by within-day variance not cross-day. The mean is uninformative. No guidance on what to do. |
| OBJECTIVE.md §1 "research execution algorithms that better execute a fixed trading-strategy signal" | The strategy is fully opaque to the exec algo at decision time — the algo can't see signal direction, magnitude, or confidence beyond what `submit_order()` exposes. The framing implies more visibility than the architecture provides. |
| Skill backtest §7 "Do not pre-run the algorithm before the paired loop" | Sensible advice but ignored in practice (multiple smoke runs in this iteration). The cause was the `MY_GENERIC_ALGO` issue, which the skill itself notes only in §3 and not at the §7 anti-pattern. |
| OBJECTIVE.md §3 "execution constraints — read from `config.yaml`, do NOT hardcode them" | None of the 6 algos to date actually read `participation_cap` or `top_of_book_only` from config; the trade engine doesn't enforce them either. They're documented constraints with no test or runtime enforcement. |

---

## 6. Prioritised improvement suggestions

Each item lists: (severity / effort / dependency).

### P0 — eliminates the highest waste in every future iteration

1. **Gitignore result CSVs** (high / 5 min / none). Add `execution_algos/*/results/*/account.csv`, `fills.csv`, `orders.csv`, `positions.csv` to `.gitignore`. Keep `metadata.json` and `metrics.json` (tiny, the durable record). Cuts per-iteration commit size from ~29 MB to ~10 KB and eliminates ~99% of git bloat. CSVs are 100% reproducible from `metadata.json` + a backtest call.

2. **Cache the baseline** (high / 1 hr / none). Add a key `(date, strategy_name, hash(strategy_kwargs), baseline_name)` keyed cache around the baseline run. Halves backtest compute per iteration. Determinism guaranteed by `seed=42` so this is safe.

3. **Default `exec_id` to the algo's directory name** in `run_backtest()` (high / 15 min / none). Eliminates the silent zero-trades footgun that cost 2 backtests this iteration. Add an assertion in `create_execution_algorithm()` that the resolved `exec_algorithm_id` is non-empty when the algo opts in.

4. **One-date-per-subprocess by default** (high / 30 min / none). Wrap `run_backtest()` invocations from the train loop into `subprocess.run(["python", "-c", ...])` so OS-level cleanup releases the ~8 GB of native memory between dates. Eliminates the OOM retry pattern that wasted ~5 backtests this iteration.

5. **Add `strategy_kwargs_hash` to every program_database entry** (high / 30 min / none). Include either the full `strategy.kwargs` dict or its sha256 hash in each entry. The sigma-change disaster (entries 1-5 incomparable to 6) is silent today; this surfaces it immediately. Update OBJECTIVE.md §9 to mandate the field.

### P1 — large quality-of-life improvements

6. **Add `backtest_engine.helpers.{latest_metrics, aggregate_metrics, delta_vs_baseline}`** (med / 1 hr / none). Removes the boilerplate every iteration reimplements. Update `backtest/SKILL.md §6` to point at the helpers instead of inlining the code. Saves ~50 lines of inline Python per iteration.

7. **Replace consecutive-failure cap with a hypothesis-diversity gate** (med / 2 hr / none). The 3-FAIL cap has been overridden 4 times. Replace with: "refuse if the last 3 entries used the same hypothesis family (skip-filter, deferral, sizing)." Track family with a free-form `hypothesis_family` field on entries. Or simply: raise the cap and remove the override pattern.

8. **Pre-staged `research/CONTEXT_SNAPSHOT.md`** (med / 2 hr / none). A 200-line summary of the program DB + NOTES.md + config, regenerated by the SubagentStop hook on every append. The agent reads this first, only loads the full DB if it needs detail. Cuts boot tokens by ~80%.

9. **`scripts/setup_check.sh`** (med / 1 hr / none). Verifies aws CLI, docker, data-cache state, `simple_execution_strategy` module presence, current `strategy.kwargs` against last-recorded entry, results CSV gitignore. Researcher invokes it once before any work. The two NOTE-recorded aborts (data infra missing, baseline module deleted) would both have been caught.

10. **JSON-schema validation on `program_database.json`** (low / 30 min / none). Schema-validate via the SubagentStop hook. Catches drift like the missing-`meta` block on entries 1-4 and forces the new `strategy_kwargs_hash` field.

11. **Quiet Nautilus logging** (med / unclear / nautilus internals). The env-var override didn't work in this run. Likely solution: pass `log_level="ERROR"` directly into `BacktestEngineConfig` (`nautilus_trader.backtest.config`). Cuts 15-20 MB stderr per backtest by ~100×.

### P2 — pipeline-architecture changes

12. **Document strategy.kwargs semantics in a sealed contract** (med / 2 hr / requires operator buy-in). The agent shouldn't read `strategies/`, but it absolutely needs to know "sigma is the noise added to the oracle forecast; sigma=5 means near-random." Currently the agent has to discover this empirically. Write `strategies/CONTRACT.md` describing the *public* meaning of each kwarg without exposing the implementation.

13. **Pass an `OracleSignalView` handle into the execution algorithm** (high / 1 day / requires architecture change). Today exec algos see only book state and `parent_order.qty`. Every prior research attempt has been a book-state filter because that's all the algos can see. Expose the per-decision oracle-signal magnitude/confidence (sigma-weighted) so the agent can write filters keyed on signal quality — the natural execution edge in a noisy-oracle world. This is the highest-leverage change for actually making the pass gate achievable.

14. **Track snapshot/OOS status in `program_database.json`** (low / 1 hr / none). Add `snapshot_pushed_at` and `oos_retrieved_at` (both nullable) to PASS entries. Lets the next agent know whether OOS retrieval is pending without reading S3 or git branches.

15. **Auto-prune wasted result dirs** (low / 30 min / none). A SubagentStop hook can drop result dirs whose `metrics.json` shows `trade_count: 0` or that are not the latest run for a given `(algo, date)`. Removes residue from runs like the two empty spread-filter dirs in this iteration.

16. **Decouple oracle-signal generation from per-algorithm runs** (med / 4 hr / none). `build_oracle_signals(ticks, **oracle_options)` runs on every backtest — twice per date in a paired baseline+algo loop. Cache by `(date, hash(oracle_options))` so each date's signals are computed once per iteration. Saves a few seconds × 6 = small but cumulative.

17. **Disambiguate OBJECTIVE.md §4 close-margin definition** (low / 5 min / none). Adopt one of the two readings explicitly. A single-line edit.

18. **Add a `--dry-run` mode to the researcher** (low / 30 min / none). Runs the full pipeline but skips the program_database append, commit, and push. Useful for instrumented runs like this audit (we had to construct the dry-run by overriding the agent's prompt). Enables cheap CI-style smoke tests of the loop.

---

## 7. Issues the agent self-flagged in OBSERVATIONS that this audit corroborates

The trace's OBSERVATIONS section called out items #1, #2, #3 (wasted backtests), #4 (OOM), #5 (logging), #6 (signal opacity), #7 (sigma change), #10 (latest_metrics helper), #11 (no kwargs hash in DB), #12 (Nautilus log suppression). Every one of those was independently confirmed by reading the artefacts. The agent's introspection on this run is reliable; the structural blockers are the ones I added above (§3, §6 P2 items) — those need pipeline-level decisions, not in-iteration fixes.

---

## 8. Suggested first three commits to land

If the operator wants to act on this audit incrementally, the highest-leverage trio:

1. **`.gitignore` + small helpers** (P0 #1 + P1 #6) — biggest waste reduction, lowest risk.
2. **Default `exec_id` + per-date subprocess** (P0 #3 + P0 #4) — fixes the two reliability footguns this iteration tripped on.
3. **`strategy_kwargs_hash` + schema validation** (P0 #5 + P1 #10) — closes the silent-regime-change failure mode that made entries 1-5 quietly incomparable to entry 6.

Implementing all three would cut per-iteration cost by an estimated 60-70% and eliminate the two failure modes (footgun zero-trade runs, OOM crashes) that consumed most of this run's wasted compute.
