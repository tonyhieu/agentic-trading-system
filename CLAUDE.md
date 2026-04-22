# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Primary references

This repo has two audience-specific docs that go deeper than this file:

- **`docs/PROBLEM_DEFINITION.md`** — the full agent-facing task: metatask, execution constraints, evaluation gate (net P&L > TWAP and VWAP by ≥10%), research loop, refinement loop, `NOTES.md` format, and the `research/program_database.json` contract. Read this before proposing or editing a strategy.
- **`SKILLS.md`** — the two executable skills (data retrieval + strategy snapshot), their CLIs, cost tables, cache paths, and naming conventions.

When a question falls inside those docs, follow them rather than restating from memory.

## Commands

Python is managed with `uv` (lockfile: `uv.lock`; Python 3.12; deps in `pyproject.toml`).

```bash
uv sync                        # install dependencies
uv run python main.py          # run the default backtest (EMA cross on MESM6, 20260406)
uv run python -m backtest_engine.backtest_low_level   # same, alternate entry
```

`main.py` just calls `backtest_engine.backtest_low_level.run_backtest()` and disposes the engine. To run a different strategy, execution algo, date, or symbol, call `run_backtest(...)` directly with kwargs — there is no CLI wrapper yet.

Data and snapshots (see `SKILLS.md` for full reference):

```bash
# Required environment (load from .env or export manually)
export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... AWS_REGION=us-east-2
export S3_BUCKET_NAME=agentic-trading-snapshots-uchicago-spring-2026

# Data partitions (~330 MB / day, ~$0.01 / day; cached under data-cache/)
uv run python scripts/data_retriever.py fetch-manifest glbx-mdp3-market-data v1.0.0
uv run python scripts/data_retriever.py sync-partition glbx-mdp3-market-data v1.0.0 "date=20260308"

# Snapshot a passing strategy (automatic: push to snapshots/<name>, GH Actions uploads to S3)
git checkout -b snapshots/<strategy-name>
git push origin snapshots/<strategy-name>
```

Docker (`docker-compose.yml`) provides `agent`, `aws`, and `dev` services that bind-mount `./data-cache`, `./scripts`, and `./strategies` and inherit AWS env vars from the host.

There is currently no test suite and no linter configured — do not invent commands for them.

## Architecture

### Three pluggable layers, one orchestrator

```
strategies/            ← signal logic (Nautilus `Strategy` subclasses)
execution_algos/       ← order routing (Nautilus `ExecAlgorithm` subclasses)
backtest_engine/       ← glues them to Nautilus, loads data, persists results
```

Both `strategies/__init__.py` and `execution_algos/__init__.py` expose a **name → factory** registry (`_STRATEGY_FACTORIES`, `_EXEC_ALGORITHM_FACTORIES`). `create_strategy(name, **kw)` and `create_execution_algorithm(name, **kw)` lazily import the module and call its `get_trading_strategy` / `get_execution_algorithm` factory. **To register a new strategy or execution algorithm, add an entry to the registry dict** — nothing else discovers them.

`backtest_engine/backtest_low_level.py::run_backtest` is the single orchestrator. It:

1. Calls `data_loader.load_dbn_partition(date, symbol)` to sync one S3 partition and filter ticks to one contract.
2. Builds a `BacktestEngine` with a `GLBX` venue, USD margin account, $1M starting balance.
3. Instantiates the strategy + execution algorithm via the factories, injecting instrument-specific defaults (e.g. `instrument_id`, `trade_size=Decimal("1")`, `exec_id="MY_GENERIC_ALGO"`).
4. Runs the engine, collects Nautilus `account` / `orders` / `fills` / `positions` reports.
5. Hands reports to `backtest_engine/results.py::compute_metrics` and `persist`, which writes a self-contained run artifact.

### Run artifacts

`results.persist` writes to `strategies/<strategy_dir>/results/{UTC-timestamp}-{git-shortsha}/`:

- `metadata.json` — strategy/exec-algo names, kwargs, date, symbol, dataset, git sha
- `metrics.json` — final equity, return %, realized P&L, max drawdown %, **annualized Sharpe** (1-min resampled equity curve), win rate, fill/order counts, and execution-cost proxies (`total_commissions`, `mean_slippage`, `max_abs_slippage`)
- `account.csv`, `orders.csv`, `fills.csv`, `positions.csv`

Two non-obvious things here:

- **`STRATEGY_DIRS`** (in `backtest_low_level.py`) maps a factory name (e.g. `"ema_cross"`) to its on-disk directory (`"ema_strategy"`). The snapshot CI reads `strategies/<dir>/results/`, so runs must land where the workflow looks. Add an entry when the factory key differs from the directory name.
- **Sharpe is annualized using a 24h futures session** (`MINUTES_PER_TRADING_YEAR = 252 * 24 * 60`). Nautilus only emits account rows on account-changing events, so the forward-filled curve understates mean and stdev; the absolute number is imprecise but comparable across runs using the same machinery.

### Data path

`backtest_engine/data_loader.py` imports `DataRetriever` from `scripts/data_retriever.py` (path-hacked onto `sys.path`). `load_dbn_partition`:

- reads `S3_BUCKET_NAME`, `AWS_REGION`, `DATA_CACHE_DIR` from env
- calls `retriever.sync_partition(DATASET_NAME, DATASET_VERSION, f"date={date}")` — cache-first, free to re-run
- reads the resulting `data-cache/glbx-mdp3-market-data/v1.0.0/partitions/date=YYYYMMDD/data.dbn.zst` with Nautilus's `DatabentoDataLoader`
- synthesizes a `FuturesContract` instrument via `_build_instrument(symbol)`. Activation/expiration are pinned 2020-01-01 / 2100-01-01 so any in-range backtest falls inside the contract's tradable window — it is not a real contract calendar.

Dataset constants (`DATASET_NAME`, `DATASET_VERSION`) live in this module; bump them here when the dataset version changes.

### Snapshot flow

`.github/workflows/snapshot-strategy.yml` triggers on push to `snapshots/**` or manual `workflow_dispatch`. It copies `*.py`, `requirements.txt`, `NOTES.md`, and the `results/` tree from the strategy directory into a timestamped S3 prefix under `s3://$S3_BUCKET_NAME/strategies/<name>/`. The workflow infers the strategy name from the branch (`snapshots/<name>` → `strategies/<name>`) unless overridden via dispatch inputs. Secrets (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `S3_BUCKET_NAME`) must be set at the repo level. Snapshots auto-expire at 30 days via S3 lifecycle policy.

### Strategy conventions

- Strategy directory names on disk are **snake_case** (`ema_strategy`, `sample_momentum_strategy`) because they are Python packages. The external "strategy name" used in `backtest-results.json`, snapshot paths, and `NOTES.md` is **kebab-case** (`ofi-v1`, `mean-reversion-r2`). The `STRATEGY_DIRS` map bridges the two.
- Every strategy directory must ship a `NOTES.md` before snapshot — see `PROBLEM_DEFINITION.md` §10 for the required sections.
- `backtest-results.json` lives at `strategies/<name>/results/backtest-results.json` and follows the schema in `SKILLS.md` — it is what the snapshot workflow extracts metrics from.
