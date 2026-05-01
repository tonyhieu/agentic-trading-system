# Skill: Run a Backtest

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
execution, not signal generation. The strategy is the constant; the
execution algorithm is the only variable under study.

Switching the locked strategy is a human decision (edit `config.yaml`),
not an agent decision.

## 3. Execution algorithms — the variable under study

Registry: `execution_algos/__init__.py → _EXEC_ALGORITHM_FACTORIES`.

To add a new execution algorithm (your job per `OBJECTIVE.md §5 step 4`):

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

`run_backtest()` calls `persist()` (in `backtest_engine/results.py`) which
writes a per-run directory:

```
execution_algos/<algo-id>/results/<YYYY-MM-DDTHH-MM-SSZ>-<short-sha>/
├── metadata.json   # run config: strategy, params, exec algo, params, date, symbol, git sha, dataset
├── metrics.json    # summary stats — see §5
├── account.csv     # equity curve
├── orders.csv      # order log (with commissions, slippage)
├── fills.csv       # fill log
└── positions.csv   # position log (entry, realized_pnl, etc.)
```

The most recent run is the canonical record for the algorithm. The
`<timestamp>-<short-sha>` directory name makes runs comparable and unique.

## 5. Metrics schema (`metrics.json`)

Produced by `compute_metrics()` in `backtest_engine/results.py:153`:

| Field | Meaning |
|---|---|
| `starting_balance` | USD seed |
| `final_equity` | end-of-run equity |
| `total_return_pct` | `(final_equity − starting) / starting × 100` |
| `realized_pnl` | sum of position realized P&L |
| `max_drawdown_pct` | `min((equity − peak) / peak) × 100` |
| `sharpe_ratio` | annualized Sharpe from 1-min equity returns (consistent across runs; absolute value imprecise — see code comment) |
| `trade_count`, `winners`, `losers`, `win_rate` | trade-count breakdown |
| `long_count`, `short_count` | side breakdown |
| `order_count`, `fill_count` | order/fill counts |
| `total_commissions` | sum across orders (account currency) |
| `mean_slippage`, `max_abs_slippage` | execution-quality proxy (price units; multiply by contract multiplier for $) |

## 6. Comparing to the baseline

`research/config.yaml → pass_gate.baseline` names the execution algorithm to
beat (default `simple`). Run both on the same `(date, symbol)` with the
same configured `strategy` block, then read both `metrics.json` files:

```python
import json
from pathlib import Path

def latest_metrics(algo_id: str) -> dict:
    results_dir = Path(f"execution_algos/{algo_id}/results")
    # Filter to dirs only — `backtest-results.json` lives in this folder too
    # (written at snapshot time) and would otherwise sort last and crash.
    runs = sorted(p for p in results_dir.iterdir() if p.is_dir())
    return json.loads((runs[-1] / "metrics.json").read_text())

mine    = latest_metrics("my-algo")
base    = latest_metrics("simple")

delta_pnl_pct  = (mine["realized_pnl"] - base["realized_pnl"]) / abs(base["realized_pnl"]) * 100
delta_slip_pct = (mine["mean_slippage"] - base["mean_slippage"]) / abs(base["mean_slippage"]) * 100
```

Compare against the gate in `config.yaml → pass_gate`.

## 7. Multi-date evaluation (train window only)

`run_backtest()` runs one date per call. The agent backtests over the
**train** window only — the test window is held out for the Lambda
evaluator (`OBJECTIVE.md §5 step 5`, `docs/skills/evaluate.md`). Loop:

```python
train_dates = [d.replace("-", "") for d in pd.date_range(*cfg["data_window"]["train"], freq="B").strftime("%Y-%m-%d")]
shared = dict(
    strategy_name=cfg["strategy"]["name"],
    strategy_kwargs=cfg["strategy"]["kwargs"],
    symbol="MESM6",
)
for date in train_dates:
    run_backtest(**shared, execution_algorithm_name="my-algo", date=date)
    run_backtest(**shared, execution_algorithm_name=cfg["pass_gate"]["baseline"], date=date)
```

Each call appends a fresh run dir under `results/`. Aggregating metrics
(mean Sharpe, sum P&L, win-rate weighted by trades) across per-date
`metrics.json` files is the agent's responsibility. Do **not** add test
dates to this loop — the OOS evaluation runs on Lambda after snapshot.

## 8. Footnote: raw data access

If you need raw DBN data outside the backtest pipeline (exploratory analysis
of market microstructure for execution-algorithm design):

```bash
python scripts/data_retriever.py sync-partition \
  glbx-mdp3-market-data v1.0.0 "date=20260406"
# cached at data-cache/glbx-mdp3-market-data/v1.0.0/partitions/date=20260406/data.dbn.zst
```

Most agents won't need this — `run_backtest()` already handles the sync.
