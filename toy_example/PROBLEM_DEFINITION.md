# Problem Definition: Toy Example Research Loop

**Version**: 1.0  
**Date**: 2026-04-24  
**Audience**: Autonomous research agents — read this file first and in full.

This is a self-contained version of the full research loop that runs **entirely locally** on two pre-cached days of Gold Futures tick data. No S3 credentials or AWS setup is needed.

---

## 1. Metatask

Discover intraday trading strategies on CME GLBX Gold Futures (GCM6) that outperform TWAP and VWAP execution benchmarks. Use a program database of past attempts to guide each new proposal. Repeat until a passing strategy is found or the iteration budget is exhausted.

---

## 2. Data

**Instrument**: GCM6 — Gold Futures, June 2026  
**Exchange**: CME Globex (GLBX)  
**Schema**: MBP-1 (top-of-book bid/ask), MDP3 feed  
**Available days**:

| Role | Date | File |
|---|---|---|
| **Train** | 2026-04-06 | `toy_example/data/glbx-mdp3-20260406.mbp-1.dbn.zst` |
| **Validate** | 2026-04-07 | `toy_example/data/glbx-mdp3-20260407.mbp-1.dbn.zst` |

### No setup required

The data is already local. Do not attempt S3 downloads. `run_research.py` handles symlinking the files into the path the backtest engine expects.

### Load data in Python (for exploration)

```python
from toy_example.loader import load_ticks, TRAIN_FILE, VAL_FILE

train_df = load_ticks(TRAIN_FILE)   # 2026-04-06
val_df   = load_ticks(VAL_FILE)     # 2026-04-07

# Columns: ts_recv, bid_px_00, ask_px_00, bid_sz_00, ask_sz_00, mid, symbol, ...
```

---

## 3. Execution Constraints

1. **Top-of-book only**: fills at `ask_px_00` (buys) or `bid_px_00` (sells).
2. **5% participation cap**: `order_size ≤ floor(0.05 × bid_sz_00 or ask_sz_00)` per tick.
3. **Intraday flat**: all positions closed by end of each session.

---

## 4. Evaluation

### Metrics

| Metric | Formula |
|---|---|
| **Implementation Shortfall (IS)** | `(fill_price − arrival_mid) × direction` per trade |
| **Net P&L** | Gross P&L − total IS |
| **Sharpe** | `mean(daily_net_pnl) / std(daily_net_pnl) × sqrt(252)` |

### Benchmarks

- **TWAP**: executes uniformly over the holding window
- **VWAP**: executes proportional to market volume over the holding window

### Pass Gate

Strategy net P&L must exceed **both** TWAP and VWAP net P&L by **at least 10%**.

---

## 5. Research Loop

```
1. READ toy_example/research/program_database.json
   What has been tried? What scored well? What failed and why?

2. READ docs/literature/
   Find a signal or mechanism worth testing.

3. HYPOTHESIZE
   Write one paragraph: what inefficiency, what signal, why it survives costs.
   Note the parent strategy ID if this is a mutation of a prior attempt.
   Write your reasoning to strategies/<name>_strategy/NOTES.md — Hypothesis section (see Section 10).

4. IMPLEMENT
   a. Create strategies/<name>_strategy/ with an __init__.py and a module
      (e.g., trading_strategy.py) that exports a get_trading_strategy(**kwargs)
      factory returning the Nautilus Strategy instance. See strategies/ema_strategy/
      for the canonical layout.
   b. Register the strategy in strategies/__init__.py by adding an entry to
      _STRATEGY_FACTORIES:
          "<name>": ("strategies.<name>_strategy", "get_trading_strategy"),
      The key is what --strategy <name> will look up.

5. BACKTEST (train day only)
   python toy_example/run_research.py --strategy <name> --date 20260406

6. EVALUATE
   Review the printed metrics. Check vs_twap_pct and vs_vwap_pct.
   Append backtest observations to strategies/<name>_strategy/NOTES.md (see Section 10).

7. DECIDE
   PASS  — beats both benchmarks by ≥ 10%  → run validation (step 7a), then enter Refinement Loop (Section 6)
   CLOSE — beats one, or within 5% of gate  → refine, max 3 attempts with same parent_id
   FAIL  — does not meet gate               → log reason, new hypothesis

   7a. Validation run (only after PASS on train):
       python toy_example/run_research.py --strategy <name> --date 20260407

8. LOG to toy_example/research/program_database.json
   run_research.py appends automatically. Add your own "notes" field by editing the entry.
   Commit: git add toy_example/research/program_database.json && git commit -m "log: <id>"
```

**Stop** when: 3 consecutive failures, or iteration budget exhausted.

---

## 6. Refinement Loop (Post-Pass)

Once a strategy passes the gate, attempt to improve it. Run up to **5 refinement iterations** before declaring the strategy final.

### Refinement targets (improve at least one per iteration)

| Target | Minimum improvement to keep the variant |
|---|---|
| Sharpe | +0.10 absolute |
| Net P&L vs TWAP/VWAP margin | +2 percentage points |
| Max drawdown | −1 percentage point |
| Win rate | +2 percentage points |

### Refinement process

```
R1. IDENTIFY weaknesses
    Re-read the baseline's metrics and strategies/<baseline>_strategy/NOTES.md.

R2. PROPOSE one targeted change
    One change at a time.
    Log your reasoning in strategies/<name>-r<N>_strategy/NOTES.md — Refinement Log section.

R3. IMPLEMENT the variant in strategies/<name>-r<N>_strategy/ (follow the
    step 4 layout: module + get_trading_strategy factory + registration in
    strategies/__init__.py under the key "<name>-r<N>").
    Set parent_id = <baseline strategy id> in the program database entry.

R4. BACKTEST on both days (train then validate)

R5. COMPARE to baseline
    BETTER   → replace baseline, continue loop
    NEUTRAL  → log, try a different change (back to R1)
    WORSE    → discard, log reason, back to R1

R6. LOG every variant to toy_example/research/program_database.json
    Commit: git add toy_example/research/program_database.json && git commit -m "refine: <id>"
```

Stop refinement when: 5 iterations completed, 3 consecutive NEUTRAL/WORSE variants, or no new change to try.

---

## 7. Saving a Passing Strategy

No S3 or snapshot step is needed for the toy example. Save locally:

```bash
git add strategies/<name>_strategy/ strategies/__init__.py
git add toy_example/research/program_database.json
git commit -m "<strategy-name>: sharpe=X.XX, +X% vs TWAP/VWAP"
```

Backtest run artifacts are written under `execution_algos/<exec-algo>/results/` by
the engine (results are tagged to the execution algorithm, not the strategy).
Those are untracked scratch artifacts — do not add them to the commit.

---

## 8. Assumptions, Unknowns, and Honest Reporting

Two separate note files:

| File | Purpose |
|---|---|
| `strategies/<name>_strategy/NOTES.md` | Agent reasoning — hypothesis, decisions, observations |
| `toy_example/research/NOTES.md` | Ambiguity alerts requiring a human decision |

Write to `toy_example/research/NOTES.md` (and print an alert) when you:
- Make an assumption because something is not specified
- Encounter unclear or ambiguous data
- Notice a data quality issue
- Observe results driven by very few trades
- Are unsure whether look-ahead bias is present

After writing, print: `⚠ NOTE WRITTEN: toy_example/research/NOTES.md — <short title>`

### Honesty rules

- Report raw numbers — do not round up Sharpe or round down drawdown.
- Report the trade count — a Sharpe of 2.0 on 8 trades is meaningless.
- Report degradation — if train Sharpe is 1.8 and val Sharpe is 0.3, write it as a failure.
- If you do not have enough trades to draw conclusions, say so.

---

## 9. Program Database

File: `toy_example/research/program_database.json`

`run_research.py` appends a metrics entry automatically after each run. Enrich the entry with:

```json
{
  "id": "ofi-v1",
  "parent_id": null,
  "hypothesis": "Order flow imbalance at top of book predicts short-term direction.",
  "strategy": "ofi-v1",
  "date": "20260406",
  "symbol": "GCM6",
  "metrics": { "sharpe": 1.42, "net_pnl": 3200, "vs_twap_pct": 14.2, "vs_vwap_pct": 11.8 },
  "passed": true,
  "notes": "Strong open; degrades afternoon. Try time-of-day conditioning.",
  "timestamp": "2026-04-24T14:32:00Z"
}
```

**Rules**: always append, never delete. Failed entries prevent re-exploring dead ends.

---

## 10. Strategy NOTES.md Format

Every strategy directory must contain a `NOTES.md`. Write it incrementally.

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

**Concerns**: <Any look-ahead bias risks, fragile assumptions, or overfitting risks.>

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
