# Problem Definition: Autonomous Trading Strategy Research

**Version**: 1.0  
**Date**: 2026-04-15  
**Audience**: Autonomous research agents — read this file first and in full.

**Required reading**: Also read `SKILLS.md` before starting. It documents the two executable skills available to you:
- **Snapshot skill** — how to save a passing strategy to S3 (used in Sections 7 and 6)
- **Data retrieval skill** — how to download, cache, and load market data partitions (used in Section 2)

---

## 1. Metatask

Discover intraday trading strategies on CME GLBX FX futures that outperform TWAP and VWAP execution benchmarks. Use a program database of past attempts to guide each new proposal. Repeat until a passing strategy is found or the iteration budget is exhausted.

---

## 2. Data

**Dataset**: `glbx-mdp3-market-data` / `v1.0.0`  
**Coverage**: 26 trading days, 2026-03-08 to 2026-04-06  
**Exchange**: CME GLBX — Global FX futures  
**Record types per tick**: `MBP1Msg` (top-of-book bid/ask), `TradeMsg` (individual trades), `OHLCVMsg` (candles)

### Set up credentials

```bash
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_REGION="us-east-2"
export S3_BUCKET_NAME="agentic-trading-snapshots-uchicago-spring-2026"
```

### Discover and download data

See **SKILLS.md → "Data Retrieval skill"** for the full command reference, cost table, and loading examples. Quick reference:

```bash
# See all available dates
python scripts/data_retriever.py fetch-manifest glbx-mdp3-market-data v1.0.0

# Download one day (~330 MB, ~$0.01)
python scripts/data_retriever.py sync-partition glbx-mdp3-market-data v1.0.0 "date=20260308"
# Cached at: data-cache/glbx-mdp3-market-data/v1.0.0/partitions/date=20260308/data.dbn.zst
```

**Cost budget**: download at most 10 days per iteration. Cached data is free to reuse.

### Load data in Python

```python
import databento_dbn as dbn

with open("data-cache/glbx-mdp3-market-data/v1.0.0/partitions/date=20260308/data.dbn.zst", "rb") as f:
    df = dbn.DBNDecoder(f).to_df()

# Key MBP1 fields: ts_event, bid_px, ask_px, bid_sz, ask_sz, symbol
# Key Trade fields: ts_event, price, size, side, action, symbol
```

---

## 3. Execution Constraints

1. **Top-of-book only**: fills at `ask_px` (buys) or `bid_px` (sells) — no walking the book.
2. **5% participation cap**: `order_size ≤ floor(0.05 × top_of_book_qty)` per tick.
3. **Intraday flat**: all positions closed by end of each session.

---

## 4. Evaluation

### Metrics

| Metric | Formula |
|---|---|
| **Implementation Shortfall (IS)** | `(fill_price − arrival_mid) × direction` per trade; `arrival_mid = (bid_px + ask_px) / 2` at decision time |
| **Net P&L** | Gross P&L − total IS |
| **Sharpe** | `mean(daily_net_pnl) / std(daily_net_pnl) × sqrt(252)` |

### Benchmarks

Run the same position decisions through two passive baselines:

- **TWAP**: executes uniformly over the holding window
- **VWAP**: executes proportional to market volume over the holding window

### Pass Gate

Strategy net P&L must exceed **both** TWAP and VWAP net P&L by **at least 10%**.

---

## 5. Research Loop

```
1. READ research/program_database.json
   What has been tried? What scored well? What failed and why?

2. READ docs/literature/
   Find a signal or mechanism worth testing. Use it for inspiration but feel free to come up with your own ideas.

3. HYPOTHESIZE
   Write one paragraph: what inefficiency, what signal, why it survives costs.
   Note the parent strategy ID if this is a mutation of a prior attempt.
   Write your reasoning to execution_algos/<name>/NOTES.md — Hypothesis section (see Section 10).

4. IMPLEMENT
   Write strategy in execution_algos/<name>/strategy.py

5. BACKTEST
   Train period: days 1–18.  Test period: days 19–26.
   Download only the dates you need (≤ 10 days).

6. EVALUATE
   Compute IS, net P&L, Sharpe.
   Compare net P&L against TWAP and VWAP.
   Append backtest observations to execution_algos/<name>/NOTES.md (see Section 10).

7. DECIDE
   PASS  — beats both benchmarks by ≥ 10%  → snapshot (see Section 7), then enter Refinement Loop (see Section 6)
   CLOSE — beats one, or within 5% of gate  → refine, max 3 attempts with same parent_id
   FAIL  — does not meet gate               → log reason, new hypothesis

8. LOG to research/program_database.json (every attempt, pass or fail)
   Commit: git add research/program_database.json && git commit -m "log: <id>"
```

**Stop** when: 3 consecutive failures, or iteration budget exhausted.

---

## 6. Refinement Loop (Post-Pass)

Once a strategy passes the gate, do not stop. Use the passing strategy as a baseline and attempt to improve it. Run up to **5 refinement iterations** before declaring the strategy final.

### Refinement targets (improve at least one per iteration)

| Target | Minimum improvement to keep the variant |
|---|---|
| Sharpe | +0.10 absolute |
| Net P&L vs TWAP/VWAP margin | +2 percentage points |
| Max drawdown | −1 percentage point (i.e., less negative) |
| Win rate | +2 percentage points |

### Refinement process

```
R1. IDENTIFY weaknesses
    Re-read the baseline's backtest results and execution_algos/<baseline>/NOTES.md.
    Pinpoint the single biggest drag: time-of-day decay, parameter sensitivity,
    poor IS on large moves, concentrated risk on a few days, etc.

R2. PROPOSE one targeted change
    One change at a time — do not compound multiple edits.
    Examples: add a time-of-day filter, tighten the participation cap during
    high-spread regimes, condition signal on realized vol, adjust holding window.
    Log your reasoning in execution_algos/<name>-r<N>/NOTES.md — Refinement Log section.

R3. IMPLEMENT the variant
    execution_algos/<name>-r<N>/strategy.py
    Set parent_id = <baseline strategy id> in the program database entry.

R4. BACKTEST on full train+test split (same dates as baseline)

R5. COMPARE to baseline (not just to TWAP/VWAP)
    BETTER   — meets at least one refinement target and does not regress others
               → snapshot variant (see Section 7 and SKILLS.md), replace baseline, continue loop
    NEUTRAL  — no measurable improvement → log, try a different change (back to R1)
    WORSE    — any metric regresses meaningfully → discard, log reason, back to R1

R6. LOG every variant to research/program_database.json
    Commit: git add research/program_database.json && git commit -m "refine: <id>"
```

### Stopping the refinement loop

Stop refinement and declare the strategy final when **any** of:

- 5 refinement iterations completed (regardless of outcome)
- 3 consecutive NEUTRAL/WORSE variants
- The last improvement was smaller than the minimum threshold above
- You cannot identify a new targeted change to try

Snapshot the best-scoring variant as the final strategy (see Section 7).

---

## 7. Saving a Passing Strategy

### Step 1 — Write results and notes

Create `execution_algos/<name>/results/backtest-results.json`:

```json
{
  "strategy_name": "your-strategy-name",
  "backtest_date": "2026-04-15T00:00:00Z",
  "performance": {
    "total_return": 15.3,
    "sharpe_ratio": 1.42,
    "max_drawdown": -6.2,
    "win_rate": 58.0,
    "total_trades": 134,
    "net_pnl": 3200.50,
    "avg_IS": 0.000018,
    "vs_twap_pct": 14.2,
    "vs_vwap_pct": 11.8
  },
  "period": { "start_date": "2026-03-08", "end_date": "2026-03-25" }
}
```

Ensure `execution_algos/<name>/NOTES.md` is complete — all three sections filled in (Hypothesis, Implementation Decisions, Backtest Observations). This file is included in the snapshot and is the primary record of your reasoning.

### Step 2 — Snapshot from within Docker

See **SKILLS.md → "Strategy Snapshot skill"** for the full procedure. The automatic method (push to a `snapshots/*` branch) is preferred — GitHub Actions handles the S3 upload:

```bash
git checkout -b snapshots/<strategy-name>
git add execution_algos/<strategy-name>/
git commit -m "<strategy-name>: sharpe=X.XX, +X% vs TWAP/VWAP"
git push origin snapshots/<strategy-name>
# GitHub Actions automatically uploads the snapshot to S3
```

If the branch push fails, use the manual GitHub Actions workflow documented in SKILLS.md.

---

## 8. Assumptions, Unknowns, and Honest Reporting

There are two separate note files with different purposes:

| File | Purpose | Audience |
|---|---|---|
| `execution_algos/<name>/NOTES.md` | Agent reasoning — hypothesis, implementation decisions, backtest observations | Future agents reading the program database |
| `research/NOTES.md` | Ambiguity alerts — things that are unclear and **require a human decision** | The human operator |

Write to `research/NOTES.md` (and print an alert) when something is unclear enough that a human needs to decide. Write to `execution_algos/<name>/NOTES.md` for everything else. See Section 10 for the strategy NOTES.md format.

### When to write a global note

Write a note to `research/NOTES.md` and **print a clear alert** any time you:

- Make an **assumption** because something is not specified (e.g., how to define the holding window for TWAP/VWAP comparison, how to handle missing ticks, what counts as "end of session")
- Encounter something **unclear or ambiguous** in the data or instructions
- Notice a **data quality issue** (gaps, anomalies, unexpected values)
- Observe that a result is **driven by a small number of trades or days** — flag this explicitly
- Are **unsure whether look-ahead bias is present** in your signal construction

### Note format

Append to `research/NOTES.md`:

```markdown
## [YYYY-MM-DD HH:MM] <category>: <short title>

**Category**: ASSUMPTION | UNCLEAR | DATA ISSUE | RESULT WARNING

**Detail**: What exactly is unclear or what assumption was made. Be specific —
name the field, the formula, the edge case.

**Why**: Why you had to make this assumption (missing spec, ambiguous docs, etc.)

**Alternatives**: What other interpretations exist and how they would change the result.

**Impact**: Does this likely affect the outcome significantly? Be honest.
```

### Honesty rules for results

These are non-negotiable:

- **Report raw numbers**. Do not round up Sharpe or round down drawdown.
- **Report the trade count**. A Sharpe of 2.0 on 8 trades is meaningless — say so.
- **Do not cherry-pick date ranges**. Only use the defined train/test split.
- **Report degradation**. If train Sharpe is 1.8 and test Sharpe is 0.3, that is a failure. Write it as a failure.
- **If you do not have enough trades to draw conclusions, say so** — do not speculate about what the results "suggest".

### Alert format

After writing to `research/NOTES.md`, print:

```
⚠ NOTE WRITTEN: research/NOTES.md — <short title>
```

Do this every time, even if the note seems minor.

---

## 9. Program Database

File: `research/program_database.json`

```json
[
  {
    "id": "ofi-v1",
    "parent_id": null,
    "hypothesis": "Order flow imbalance at top of book predicts short-term direction.",
    "strategy_path": "execution_algos/ofi-v1/",
    "scores": {
      "sharpe": 1.42,
      "net_pnl": 3200,
      "vs_twap_pct": 14.2,
      "vs_vwap_pct": 11.8,
      "passed": true
    },
    "notes": "Strong in first 30 min; degrades afternoon. Try time-of-day conditioning.",
    "timestamp": "2026-04-15T14:32:00Z"
  }
]
```

**Rules**: always append, never delete. Failed entries prevent re-exploring dead ends.

---

## 10. Strategy NOTES.md Format

Every strategy directory must contain a `NOTES.md`. Write it incrementally — the Hypothesis section at step 3, the Backtest Observations section after step 6, and Refinement Log entries during the refinement loop.

```markdown
# Strategy Notes: <strategy-name>

## Hypothesis

**Signal**: <what signal or mechanism drives entries/exits>
**Inefficiency exploited**: <what market behaviour makes this profitable>
**Why it survives costs**: <why the edge is large enough after IS and spread>
**Parent strategy**: <parent strategy id, or "none — original hypothesis">
**Alternatives considered**: <other approaches ruled out and why>

---

## Implementation Decisions

<Non-obvious parameter choices, edge-case handling, and design trade-offs.>

**Concerns**: <Any look-ahead bias risks, fragile assumptions, or overfitting risks you noticed.>

---

## Backtest Observations

**What drove performance**:
**What underperformed**:
**Hypothesis verdict**: <Did the backtest support or contradict the original hypothesis?>
**Suggested refinement**: <Single highest-leverage change to try next, if any.>

---

## Refinement Log

### R<N> — [YYYY-MM-DD]
**Identified weakness**:
**Proposed fix**:
**Result**: BETTER | NEUTRAL | WORSE
**Why**:
```

**Rules:**
- Fill in Hypothesis before writing any code.
- Fill in Backtest Observations before deciding PASS/FAIL/CLOSE.
- Append a Refinement Log entry for every refinement iteration, including NEUTRAL and WORSE outcomes.
- This file is included in the S3 snapshot and is read by future agents via `research/program_database.json`.
