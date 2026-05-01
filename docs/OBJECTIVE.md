# Objective: Autonomous Execution-Algorithm Research

**Audience**: Autonomous research agents — read this file first and in full.

All numeric values referenced below (date ranges, gate thresholds, refinement
targets, loop limits) come from **`research/config.yaml`**. When values here
appear to conflict with the config, the config wins. This file describes what
each parameter means and why; the config is the single source of truth for
values.

Skills referenced from the loop steps:
- `docs/skills/backtest.md` — running `run_backtest()`, where artifacts land,
  the metrics schema, and how to register a new execution algorithm
- `docs/skills/analysis.md` — exploratory analysis on training-set market
  data (load only when you need raw-tick inspection before implementing)
- `docs/skills/snapshot.md` — saving a passing execution algorithm to S3
- `docs/skills/evaluate.md` — retrieving the Lambda evaluator's OOS report
  after snapshotting and merging it into `backtest-results.json`

---

## 1. Metatask

Research execution algorithms for CME GLBX FX futures that better execute a
fixed trading-strategy signal than a registered baseline. The trading strategy
is held fixed; the execution algorithm is the variable under study.

- **Strategy** (fixed): `config.yaml → strategy.name` (default `oracle`).
  Strategy kwargs are in `config.yaml → strategy.kwargs`. The agent does not
  vary these.
- **Baseline**: `config.yaml → pass_gate.baseline` (default `simple`). Beat
  it on realized P&L without regressing slippage to PASS the gate.

Use the program database of past attempts to guide each new proposal. Repeat
until a passing algorithm is found or the iteration budget in
`config.yaml → loop.max_iterations` is exhausted.

---

## 1.1 Action sequence (TL;DR — full details in §§3–9)

```
1. READ  research/program_database.json + docs/literature/ for context
2. HYPOTHESIZE → write Hypothesis section in NOTES.md before any code
3. IMPLEMENT execution_algos/<algo-id>/execution_algorithm.py + register in factory
4. BACKTEST your algo AND the baseline on **train** dates only (one run_backtest per date per algo). Test is held out for Lambda.
5. COMPARE metrics.json deltas against pass_gate → PASS / CLOSE / FAIL (decision is train-only)
6. APPEND entry to research/program_database.json + git commit
7. On PASS: git push origin snapshots/<algo-id> — this triggers the Lambda evaluator on test
8. POST-SNAPSHOT (in a follow-up invocation): retrieve the Lambda OOS report and merge into backtest-results.json (docs/skills/evaluate.md)
```

For exploratory data analysis before step 3, see `docs/skills/analysis.md`.

---

## 2. Data

**Dataset**: `glbx-mdp3-market-data` / `v1.0.0` (see `config.yaml → dataset`),
26 trading days from 2026-03-08 to 2026-04-06, CME GLBX FX futures.

Data retrieval is wrapped by `run_backtest()` — you don't call
`data_retriever.py` directly. See `docs/skills/backtest.md` for the entry
point, record-type schema, and run artifacts. See `docs/skills/analysis.md`
if you need to inspect raw ticks for EDA.

**Cost budget**: at most `config.yaml → data_window.max_days_per_iteration`
date partitions per invocation (default 10). Cached partitions are free.

---

## 3. Execution Constraints

The execution algorithm operates under the constraints in
`config.yaml → execution_constraints`. **The Nautilus engine does not
enforce them — your algorithm must.** A backtest that violates a
constraint will still run and produce metrics, but the result is invalid
and any snapshot built from it would mislead future agents.

**Read the constraint values from `config.yaml`; do NOT hardcode them.**
They are tunable. Pass them into your algorithm via
`execution_algorithm_kwargs` or read the file inside your factory.

### Quantity invariant (non-tunable)

The execution algorithm **fragments, defers, or skips** parts of a parent
order — it never increases its quantity. For every parent order the
strategy submits:

```
sum(child_fills) ≤ parent.quantity
```

Strict inequality (`<`) is allowed when liquidity or constraints make a
full fill infeasible (record a `research/NOTES.md` ASSUMPTION/DATA ISSUE
in that case). Strict greater-than (`>`) is **never** allowed.

Sizing is a strategy decision and is held fixed (§1). An algorithm that
submits more contracts than the parent specifies — by spawning extra
child orders, doubling sizes opportunistically, or otherwise inflating —
is doing position sizing, not execution. The result is invalid
regardless of realized P&L, and any snapshot built from it is rejected.

### Tunable constraints

| Field | What it requires |
|---|---|
| `top_of_book_only` | When true, fill at `ask_px` (buys) or `bid_px` (sells); never place orders that would walk the book. |
| `participation_cap` | Per-tick **ceiling**: `order_size_per_tick ≤ floor(participation_cap × top_of_book_qty)`. This is a cap, not a target — never inflate a parent order to use available book capacity. If the cap is 0 (book too thin), defer to a later tick; skipping is allowed under the quantity invariant when no later tick is feasible (e.g., session end). |
| `intraday_flat` | When true, all positions closed by end of each session. Track session boundaries (data timestamps carry session info) and submit closing orders before the final tick. |

Verify your algorithm respects these on every backtest. If you cannot
fully respect a constraint (e.g., book is too thin to fill within
`participation_cap` at session end), write a global note in
`research/NOTES.md` (category: DATA ISSUE or ASSUMPTION) and FAIL the
iteration.

---

## 4. Evaluation

### Metrics

Produced by `compute_metrics()` (`backtest_engine/results.py:153`); full table
in `docs/skills/backtest.md §5`. The metrics relevant to the gate:

| Metric | Source field | Used for |
|---|---|---|
| Realized P&L | `realized_pnl` | Pass gate (primary) |
| Mean slippage | `mean_slippage` | Pass gate (regression check) |
| Sharpe ratio | `sharpe_ratio` | Refinement targets |
| Max drawdown | `max_drawdown_pct` | Refinement targets |
| Win rate | `win_rate` | Refinement targets |

### Pass Gate

Run your execution algorithm and the baseline (in `config.yaml → pass_gate.baseline`)
on the same `(strategy_name, date, symbol)`. The gate requires:

- `realized_pnl` beats the baseline by `pass_gate.min_pnl_improvement_pct`
- `mean_slippage` does not regress by more than `pass_gate.max_slippage_regression_pct`

Algorithms within `pass_gate.close_margin_pct` of either condition count as
CLOSE — an informational status. A future iteration may try a related
approach, but there's no formal retry counter.

---

## 5. Research Loop

Each invocation of the researcher = **one pass** of this loop. The agent does
not loop internally. The human (or a future orchestrator) is the loop driver.

```
1. READ research/program_database.json
   What has been tried? What scored well? What failed and why?
   Check loop caps in config.yaml — refuse if exceeded:
     - max_iterations across all entries
     - stop_after_consecutive_failures (last N FAILs)

2. READ docs/literature/
   Find an execution mechanism worth testing — order splitting, scheduling,
   conditional submission, etc. Use it for inspiration but feel free to come
   up with your own ideas.

3. HYPOTHESIZE
   Write one paragraph: what execution inefficiency, what mechanism, why it
   improves P&L without worsening slippage. If this builds on a prior
   attempt, name it in the Hypothesis prose (no structured lineage field —
   the relationship lives in NOTES.md text).
   Write your reasoning to execution_algos/<algo-id>/NOTES.md — Hypothesis
   section (see §10).

4. IMPLEMENT
   Create execution_algos/<algo-id>/ with:
     - execution_algorithm.py — ExecAlgorithm subclass + get_execution_algorithm factory
     - __init__.py            — re-exports get_execution_algorithm
   Register in execution_algos/__init__.py → _EXEC_ALGORITHM_FACTORIES.
   See docs/skills/backtest.md §3 for the minimal pattern.

5. BACKTEST (train window only)
   For each date in config.yaml → data_window.train, call run_backtest()
   twice: once with your algo, once with the baseline
   (cfg["pass_gate"]["baseline"]). Same strategy on both runs — strategy
   is config.yaml → strategy.name and DOES NOT vary.

   The test window (config.yaml → data_window.test) is HELD OUT. It is
   evaluated only by the Lambda after a successful snapshot push (§7,
   docs/skills/evaluate.md). Do NOT call run_backtest() on test dates —
   doing so leaks the held-out set (analysis.md §4) and invalidates the
   OOS report. The PASS/FAIL decision in step 7 is made on train alone.

   See docs/skills/backtest.md §1 for the call signature and §7 for the
   train-loop pattern.

6. EVALUATE
   Read metrics.json from each run's results/<timestamp>-<sha>/ directory.
   Aggregate across train dates (mean Sharpe, sum P&L, etc. — your call).
   Compute deltas vs baseline:
     delta_pnl_pct  = (mine.realized_pnl - base.realized_pnl) / abs(base.realized_pnl) * 100
     delta_slip_pct = (mine.mean_slippage - base.mean_slippage) / abs(base.mean_slippage) * 100
   Append backtest observations to execution_algos/<algo-id>/NOTES.md (§10).

7. DECIDE
   PASS  — beats baseline by ≥ pass_gate margins  → snapshot (§7)
   CLOSE — within pass_gate.close_margin_pct of the gate → log informationally;
           a future iteration may try a related approach (no formal retry counter)
   FAIL  — does not meet gate                     → log reason

8. LOG to research/program_database.json (every attempt — pass, close, or fail)
   Append the entry, then commit it together with the algorithm code:
     git add execution_algos/<algo-id>/ research/program_database.json
     git commit -m "<algo-id>: <status>, +X.X% pnl vs baseline"
   Failed entries prevent re-exploring dead ends.
```

If a refinement is appropriate after a PASS, the *next* invocation handles it
(see §6).

---

## 6. Improving on a Passing Algorithm

Once an algorithm passes the gate, future iterations may build on it. There
is no formal lineage tracking — each invocation is an independent research
attempt and the agent decides whether to refine an existing passing
algorithm or propose a fresh hypothesis.

### When to refine

After §5 step 1 (READ `program_database.json`), if a passing entry has a
weakness that suggests a targeted improvement, refining is often the
higher-value next move. Otherwise propose a fresh hypothesis.

### Procedure (single invocation)

The same §5 loop applies, with these specifics:

- **Step 3 (HYPOTHESIZE)** — name the prior algorithm in NOTES.md hypothesis
  prose (e.g., "Building on `twap-vol-aware` — its afternoon degradation
  suggests adding a time-of-day filter").
- Make **ONE targeted change** vs the prior algorithm. Don't compound
  multiple edits — that destroys attribution.
- **Step 6 (EVALUATE)** — compare against the prior algorithm's
  `metrics.json` (the one you're improving on) in addition to the gate
  baseline. Use `config.yaml → refinement.targets` as the bar for "is this
  actually better."

### Refinement targets

A refinement variant should improve at least one of these vs the prior
algorithm, without meaningfully regressing the others (values in
`config.yaml → refinement.targets`):

- `min_sharpe_delta` — absolute Sharpe improvement
- `min_pnl_delta_pct` — percentage points of realized P&L
- `max_slippage_delta_pct` — negative = less slippage (improvement)
- `min_winrate_delta_pp` — percentage points
- `min_mdd_delta_pp` — negative = less drawdown

If the variant doesn't meet any target without regression vs the prior
algorithm, but still passes the gate vs the baseline, status=PASS and
snapshot it (it's a parallel passing algorithm). If it doesn't pass the
gate at all, status=FAIL/CLOSE per §5 step 7.

---

## 7. Saving a Passing Algorithm

See **`docs/skills/snapshot.md`** for the full procedure. Quick version:

1. Confirm the latest run dir exists at
   `execution_algos/<algo-id>/results/<timestamp>-<sha>/` (created by
   `run_backtest()`).
2. Ensure `execution_algos/<algo-id>/NOTES.md` has all sections filled in (§10).
3. From inside the project (Docker is fine):
   ```bash
   git checkout -b snapshots/<algo-id>
   git add execution_algos/<algo-id>/ research/program_database.json
   git commit -m "<algo-id>: pnl=+X.X% vs baseline, sharpe=X.XX"
   git push origin snapshots/<algo-id>
   ```
   GitHub Actions packages and uploads to S3.

The S3 upload triggers the `execution-algorithm-evaluator` Lambda, which
runs the algorithm against the held-out test window
(`config.yaml → data_window.test`) and writes a report to
`s3://<bucket>/evaluation-reports/<algo-id>/`. This is the ONLY place the
test window is evaluated — only algorithms that pass on train get the
paid OOS confirmation (~$0.30/run; cost discipline in `evaluate.md §2`).

In a **follow-up invocation**, retrieve the OOS report and merge it into
`results/backtest-results.json` as a parallel `performance_oos` block —
do NOT overwrite the train-window `performance` numbers. Honesty rules
(§8) require reporting OOS regressions raw: a train-pass + test-regress
result is logged as such, not re-run for a more favourable test draw.
See `docs/skills/evaluate.md` for retrieval and the report shape.

---

## 8. Assumptions, Unknowns, and Honest Reporting

Two note files, different purposes:

| File | Purpose |
|---|---|
| `execution_algos/<algo-id>/NOTES.md` | Algorithm reasoning (template in §10). Read by future agents via the program database. |
| `research/NOTES.md` | Ambiguity alerts that require a **human decision**. |

### Honesty rules — non-negotiable

- **Raw numbers only.** Don't round Sharpe up or drawdown down.
- **Always report trade_count.** A Sharpe of 2.0 on 8 trades is meaningless — say so.
- **Never cherry-pick dates.** Only the train/test split in `config.yaml → data_window`.
- **Report degradation.** Train improves but test regresses = FAIL. Write it as FAIL.
- **Don't speculate from too few trades.** Say "insufficient data" instead.

### Global notes (`research/NOTES.md`)

Write a global note + print an alert when you:
- make an **ASSUMPTION** for something unspecified (aggregation rule, edge case)
- encounter something **UNCLEAR** in data or instructions
- spot a **DATA ISSUE** (gaps, anomalies)
- find a result is **driven by a small number of trades/days** (RESULT WARNING)
- are **unsure whether look-ahead bias is present** in your execution logic

Append to `research/NOTES.md`:

```markdown
## [YYYY-MM-DD HH:MM] <CATEGORY>: <short title>
**Detail**: <specific field/formula/edge case>
**Why**: <why the ambiguity exists>
**Alternatives**: <other interpretations and their effect>
**Impact**: <honest assessment of significance>
```

Then print: `⚠ NOTE WRITTEN: research/NOTES.md — <short title>`

---

## 9. Program Database

File: `research/program_database.json` — JSON array, append-only.

```json
{
  "id": "twap-volatility-aware",
  "status": "pass",
  "baseline": "simple",
  "hypothesis": "Slow during high-vol reduces adverse selection.",
  "algorithm_path": "execution_algos/twap-volatility-aware/",
  "scores": {"sharpe": 1.42, "realized_pnl": 3200.50, "mean_slippage": 0.0012,
             "vs_baseline_pnl_pct": 14.2, "vs_baseline_slippage_pct": -3.1,
             "trade_count": 134, "passed": true},
  "notes": "Strong on high-vol; degrades when book is thin.",
  "timestamp": "2026-04-15T14:32:00Z"
}
```

**Rules**:
- Always **append**, never delete or rewrite.
- Every attempt (pass/close/fail) gets an entry — failed entries prevent re-exploring dead ends.
- `status` ∈ {`pass`, `close`, `fail`}, set from the **train** gate. The OOS
  result from the Lambda is recorded separately in
  `execution_algos/<algo-id>/results/backtest-results.json` under
  `performance_oos` — not in this database.
- A train-pass that regresses on OOS is honest research: the original entry
  stays as `pass` (the train decision was real), and the OOS regression is
  visible in `backtest-results.json`. Future agents reading the database
  must also read the algorithm's `backtest-results.json` for the full picture.
- `baseline` records which gate baseline was used (for reproducibility when the config changes).
- No structured lineage between entries — if an algorithm builds on a prior one, that relationship lives in the algorithm's `NOTES.md` Hypothesis prose, not here.
- Write and `git add` together with the algorithm code in one commit (§5 step 8).

---

## 10. Algorithm NOTES.md Format

Every algorithm directory must contain a `NOTES.md`. Write it incrementally —
the Hypothesis section at §5 step 3, the Backtest Observations after §5 step 6.

```markdown
# Algorithm Notes: <algo-id>

## Hypothesis

**Mechanism**: <what execution behaviour drives the improvement — splitting, scheduling, conditional submission, etc.>
**Inefficiency exploited**: <what aspect of baseline execution leaves P&L on the table>
**Why it survives costs**: <why the edge is large enough after commissions and slippage>
**Builds on**: <prior algorithm id if this is an improvement attempt; "none — original hypothesis" otherwise>
**Alternatives considered**: <other approaches ruled out and why>

---

## Implementation Decisions

<Non-obvious parameter choices, edge-case handling, and design trade-offs.>

**Concerns**: <Any look-ahead bias risks, fragile assumptions, or
overfitting risks you noticed.>

---

## Backtest Observations

**What drove improvement**:
**What underperformed**:
**Hypothesis verdict**: <Did the backtest support or contradict the original hypothesis?>
**Suggested next attempt**: <Single highest-leverage change a future iteration could try, if any.>
```

**Rules:**
- Fill in Hypothesis before writing any code.
- Fill in Backtest Observations before deciding PASS/CLOSE/FAIL.
- This file is included in the S3 snapshot and is read by future agents via
  `research/program_database.json`.
