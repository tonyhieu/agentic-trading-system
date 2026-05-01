# Skill: Data Analysis (EDA)

For exploratory analysis of training-set market data — inspecting raw ticks
directly, separate from the `run_backtest()` pipeline.

**What questions to ask is your decision.** Derive them from your
hypothesis. This skill covers only the mechanics: loading data, where to
put outputs, and one hard boundary. It does not prescribe analyses.

## 1. When to use

Use this skill whenever a step in your reasoning depends on something you
can only learn from the raw market data. If your hypothesis is purely
procedural and rests on no microstructure assumption, you may not need it.

You do NOT need this skill for iteration that just runs `run_backtest()`
and reads `metrics.json`.

## 2. Load raw DBN data

```python
import subprocess
from pathlib import Path
import databento_dbn as dbn
import pandas as pd

# Sync if not cached (idempotent)
date = "20260308"
subprocess.run(
    ["python", "scripts/data_retriever.py", "sync-partition",
     "glbx-mdp3-market-data", "v1.0.0", f"date={date}"],
    check=True,
)

dbn_file = Path(
    f"data-cache/glbx-mdp3-market-data/v1.0.0/partitions/date={date}/data.dbn.zst"
)
with open(dbn_file, "rb") as f:
    df = dbn.DBNDecoder(f).to_df()
```

**Filter:**
- By record type: `df[df["rtype"] == "MBP1Msg"]`, `"TradeMsg"`, `"OHLCVMsg"`
- By symbol: `df[df["symbol"] == "MESM6"]`

**Format gotchas:**
- Prices are int64 in 1e-9 USD — divide by `1e9` for dollars.
- Timestamps (`ts_event`, `ts_recv`) are nanoseconds — convert with
  `pd.to_datetime(df["ts_event"], unit="ns")`.

The available record types and full field list come back from
`python scripts/data_retriever.py fetch-schema glbx-mdp3-market-data v1.0.0`.

## 3. Where to put outputs

- **Findings** that shape your algorithm design → `execution_algos/<algo-id>/NOTES.md`
  under "Implementation Decisions". Note which dates you analyzed and which
  questions you asked.
- **Charts** that materially support a hypothesis → `execution_algos/<algo-id>/results/eda-<short-title>.png`.
- **Don't** commit raw DataFrames or large CSVs.

## 4. Hard boundary: do not analyze test dates

The split in `config.yaml → data_window` is held out for one reason: test
metrics must reflect performance on data your design has never seen. Loading
test-window dates during EDA is **data leakage** — it pollutes the train/test
boundary and inflates final metrics.

If you need more analysis breadth, use additional dates from
`config.yaml → data_window.train`. If train is exhausted, write a global
note in `research/NOTES.md` (category: ASSUMPTION) and stop — do not
silently reach into test.
