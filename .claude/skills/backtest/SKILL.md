---
name: backtest
description: Run a backtest of an execution algorithm via run_backtest(), register a new algorithm in the factory, and aggregate per-date metrics across the train window for baseline comparison.
when_to_use: Use when implementing a new execution algorithm, adding it to the factory registry, running it against the configured strategy, or comparing realized P&L and slippage to the baseline named in pass_gate.baseline.
user-invocable: false
allowed-tools: Read Edit Write Bash Grep Glob
---

# Backtest

Single canonical source for running a backtest of an execution algorithm.

## 1. Entry point

Load the config, then call `run_backtest()`:

```python
import yaml
from backtest_engine.backtest_low_level import run_backtest

with open("research/config.yaml") as f:
    cfg = yaml.safe_load(f)

engine = run_backtest(
    strategy_name=cfg["strategy"]["name"],            # FIXED — from config.yaml
    strategy_kwargs=cfg["strategy"]["kwargs"],        # FIXED — from config.yaml
    execution_algorithm_name="my-algo",               # the variable under study
    execution_algorithm_kwargs={},                    # optional
    date="20260406",                                  # YYYYMMDD
    symbol="MESM6",                                   # Databento raw_symbol
)
engine.dispose()
```

**Strategy is locked by config.** Do not pass a `strategy_name` other than
`cfg["strategy"]["name"]`. The strategy block is opaque — do not vary it,
inspect its implementation, or reason about its mechanics. The execution
algorithm is the only variable under study.

The backtest engine handles data sync internally —
`backtest_engine/data_loader.py:load_dbn_partition()` calls
`DataRetriever.sync_partition` to pull the date partition from S3 and load it
through Nautilus's `DatabentoDataLoader`. You do not call `data_retriever.py`
directly.

## 2. Strategy — opaque, held fixed by config

The `strategy` block in `config.yaml` is opaque to you. Read
`cfg["strategy"]["name"]` and `cfg["strategy"]["kwargs"]` and pass both
through to `run_backtest()` unchanged. Do not inspect strategy
implementation files, registries, or kwargs semantics — your task is
execution, not signal generation.

Switching the locked strategy is a human decision (edit `config.yaml`),
not an agent decision.

## 3. Execution algorithms — the variable under study

Registry: `execution_algos/__init__.py → _EXEC_ALGORITHM_FACTORIES`.

To add a new execution algorithm:

```
execution_algos/<algo-id>/
├── __init__.py              # re-exports get_execution_algorithm
├── execution_algorithm.py   # ExecAlgorithm subclass + factory function
└── results/                 # auto-populated per run
```

**Directory name MUST equal the factory name.** `run_backtest()` resolves
the output directory via `EXECUTION_DIRS.get(name, name)` in
`backtest_engine/backtest_low_level.py:29-31`. With matching names the
fallback finds your dir; otherwise `persist()` writes to the wrong place
and `latest_metrics()` won't find it.

The existing `simple` algo (factory `"simple"` → dir
`simple_execution_strategy/`) is a legacy exception, registered in
`EXECUTION_DIRS` explicitly. **For new algos, use the same kebab-case
name in both places** (e.g., factory `"volatility-aware-twap"` → dir
`execution_algos/volatility-aware-twap/`).

Register in `execution_algos/__init__.py`:

```python
_EXEC_ALGORITHM_FACTORIES: dict[str, tuple[str, str]] = {
    "simple":   ("execution_algos.simple_execution_strategy", "get_execution_algorithm"),
    "<algo-id>": ("execution_algos.<algo-id>",                 "get_execution_algorithm"),
}
```

Minimal pattern (see `execution_algos/simple_execution_strategy/execution_algorithm.py`):

```python
from nautilus_trader.execution.algorithm import ExecAlgorithm
from nautilus_trader.execution.config import ExecAlgorithmConfig
from nautilus_trader.model.identifiers import ExecAlgorithmId

class MyAlgoConfig(ExecAlgorithmConfig):
    pass

class MyAlgo(ExecAlgorithm):
    def on_start(self) -> None: ...
    def on_reset(self) -> None: ...
    def on_order(self, order) -> None:
        # Decide how to execute this order (split, schedule, route, etc.)
        self.submit_order(order)

def get_execution_algorithm(exec_id: str = "MY_GENERIC_ALGO"):
    config = MyAlgoConfig(exec_algorithm_id=ExecAlgorithmId(exec_id))
    return MyAlgo(config=config)
```

## 4. Run artifacts

Full results layout for an algorithm:

```
execution_algos/<algo-id>/results/
├── backtest-results.json                       # committed — aggregate; written by scripts/run_research_backtest.py
├── metadata.json                               # committed — reproduction record (runs[]); written by write_metadata()
└── <YYYYMMDD>-<short-sha>/                     # per-run dir (one per trading date, auto-created by run_backtest() → persist())
    ├── metrics.json                             # committed — summary stats; see metrics-schema.md
    ├── account.csv                              # gitignored — equity curve
    ├── orders.csv                               # gitignored — order log (with commissions, slippage)
    ├── fills.csv                                # gitignored — fill log
    └── positions.csv                            # gitignored — position log (entry, realized_pnl, etc.)
```

Committed files: `backtest-results.json`, `metadata.json`, and each
`<run>/metrics.json`. Everything else is gitignored.

`run_backtest()` → `persist()` writes one per-run directory per invocation
(containing `metrics.json` + the CSV reports). The aggregator
(`scripts/run_research_backtest.py`) then writes the two top-level files:
`backtest-results.json` aggregates per-date metrics across the train window,
and `metadata.json` reconstructs the reproduction record from `cfg` plus
each per-run dir's `<YYYYMMDD>-<short-sha>` name. There is no per-run
metadata sidecar — the dir name itself (trading date + commit short SHA)
is the per-run identity. Rerunning the same trading date at the same
commit raises `FileExistsError` — remove the old directory first.

The top-level `metadata.json` is the canonical reproduction record for the
algorithm.

## 5. Metrics

The `metrics.json` schema and field-by-field meaning are in
[metrics-schema.md](metrics-schema.md). Load that file when you need to
look up a specific field — most iterations only need `realized_pnl`,
`mean_slippage`, `sharpe_ratio`, `max_drawdown_pct`, `win_rate`,
`trade_count`.

## 6. Comparing to the baseline

For the standard PASS/FAIL decision, **use the aggregator output** — the
runner in §7 writes `backtest-results.json` with `performance.vs_baseline_*`
fields already computed against the configured baseline:

```python
import json
from pathlib import Path

perf = json.loads(
    Path(f"execution_algos/{algo_id}/results/backtest-results.json").read_text()
)["performance"]

delta_pnl_pct  = perf["vs_baseline_pnl_pct"]       # realized + unrealized_pnl basis
delta_slip_pct = perf["vs_baseline_slippage_pct"]
delta_is_bps   = perf["vs_baseline_is_bps"]        # canonical execution objective
```

`vs_baseline_pnl_pct` is derived from `realized_pnl + unrealized_pnl` on
both sides — not `realized_pnl` alone. For an `intraday_flat` strategy
`unrealized_pnl` is 0 and the two are identical. Compare against the gate
in `config.yaml → pass_gate`.

**One-off single-date debugging** (only when you need per-date detail the
aggregate doesn't expose):

```python
import json
from pathlib import Path

def latest_run_metrics(algo_id: str) -> dict:
    results_dir = Path(f"execution_algos/{algo_id}/results")
    # Filter to dirs — backtest-results.json and metadata.json also live here.
    runs = sorted(p for p in results_dir.iterdir() if p.is_dir())
    return json.loads((runs[-1] / "metrics.json").read_text())

m = latest_run_metrics("my-algo")
day_total_pnl = m["realized_pnl"] + m["unrealized_pnl"]
```

Do not use single-date numbers for verdicts — the train window is what
counts. Single-date reads are for inspecting which date dragged the
aggregate.

## 7. Multi-date evaluation (train window only)

Use the centralized runner:

    python scripts/run_research_backtest.py --algo <algo-id>

It reads `cfg["data_window"]["train"]`, pairs your algo with the baseline
(`cfg["pass_gate"]["baseline"]`) on each train date in fresh subprocesses,
and aggregates per `snapshot/SKILL.md §3` into
`execution_algos/<algo-id>/results/backtest-results.json`.

Useful flags: `--baseline-only` (refresh the baseline only),
`--dates 20260308,20260309` (override the config train dates for
debugging), `--dry-run` (print the plan and exit). Run with `--help` for
the full list.

Do **not** pass test dates to the runner — the OOS evaluation runs on
Lambda after snapshot. For one-off debugging where you want a single
`run_backtest()` call without going through the paired loop, use the §1
entry point directly.

## 8. Footnote: raw data access

If you need raw DBN data outside the backtest pipeline (exploratory analysis
of market microstructure for execution-algorithm design):

```bash
python scripts/data_retriever.py sync-partition \
  glbx-mdp3-market-data v1.0.0 "date=20260406"
# cached at data-cache/glbx-mdp3-market-data/v1.0.0/partitions/date=20260406/data.dbn.zst
```

Most agents won't need this — `run_backtest()` already handles the sync.
