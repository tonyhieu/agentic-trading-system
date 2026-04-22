# Agent Skills

Two executable skills available to research agents:

1. **Data Retrieval** — download market data partitions from S3 for backtesting.
2. **Strategy Snapshot** — save a passing strategy (code + results + NOTES) to S3 via GitHub Actions.

For the research task, evaluation gate, and research loop, read [docs/PROBLEM_DEFINITION.md](docs/PROBLEM_DEFINITION.md) first. For error handling, see [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

---

## Environment Setup

Both skills require AWS credentials in the environment:

```bash
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_REGION="us-east-2"
export S3_BUCKET_NAME="agentic-trading-snapshots-uchicago-spring-2026"
```

Inside Docker, these are passed through from the host via `docker-compose`.

---

## Skill 1: Data Retrieval

### Available dataset

| Field | Value |
|---|---|
| Dataset | `glbx-mdp3-market-data` |
| Version | `v1.0.0` |
| Format | DBN (Databento binary) with zstd compression |
| Coverage | 26 trading days, 2026-03-08 to 2026-04-06 |
| Exchange | CME GLBX — Global FX futures |
| Total size | 8.37 GB (~330 MB per date) |
| Record types | `MBP1Msg` (top-of-book), `TradeMsg`, `OHLCVMsg` |

### CLI: `scripts/data_retriever.py`

```bash
# Discover
python scripts/data_retriever.py list-datasets
python scripts/data_retriever.py list-versions glbx-mdp3-market-data

# Inspect
python scripts/data_retriever.py fetch-manifest glbx-mdp3-market-data v1.0.0
python scripts/data_retriever.py fetch-schema   glbx-mdp3-market-data v1.0.0

# Download one date (~330 MB, ~$0.01)
python scripts/data_retriever.py sync-partition glbx-mdp3-market-data v1.0.0 "date=20260308"

# Verify integrity
python scripts/data_retriever.py validate glbx-mdp3-market-data v1.0.0
```

Downloaded files are cached at:

```
data-cache/glbx-mdp3-market-data/v1.0.0/partitions/date=YYYYMMDD/data.dbn.zst
```

Re-running `sync-partition` on a cached date is a no-op — cached data is free to reuse.

### Loading DBN in Python

```python
import databento_dbn as dbn

path = "data-cache/glbx-mdp3-market-data/v1.0.0/partitions/date=20260308/data.dbn.zst"
with open(path, "rb") as f:
    df = dbn.DBNDecoder(f).to_df()

# Key MBP1 fields: ts_event, bid_px, ask_px, bid_sz, ask_sz, symbol
# Key Trade fields: ts_event, price, size, side, action, symbol
```

For a multi-day backtest, concatenate per-date DataFrames with `pd.concat` and sort by `ts_event`.

### Cost

| Scenario | Size | Cost |
|---|---|---|
| Single date | ~330 MB | ~$0.01 |
| 10-day backtest | ~3.3 GB | ~$0.13 |
| Full dataset | 8.37 GB | ~$0.32 |

Cost budget: download at most 10 days per research iteration. Cached data is free.

For the canonical S3 layout and manifest schema, see [docs/DATA_STORAGE_CONTRACT.md](docs/DATA_STORAGE_CONTRACT.md).

For data retrieval errors, see [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md#data-retrieval).

---

## Skill 2: Strategy Snapshot

A snapshot is a timestamped backup of a strategy — code, results, and agent reasoning — uploaded to S3 for 30 days. Snapshots survive force-pushes and branch deletions.

### Strategy directory layout

```
strategies/<strategy-name>/
├── <strategy_file>.py        # Strategy implementation
├── NOTES.md                  # Agent reasoning (required — see PROBLEM_DEFINITION.md §10)
├── requirements.txt          # Optional
└── results/
    ├── backtest-results.json # Required for metric extraction
    ├── trade-history.csv     # Optional
    └── charts.png            # Optional
```

Rules:
- Strategy name is kebab-case (e.g., `ofi-v1`, `mean-reversion-r2`).
- `NOTES.md` is required — it is the primary record of your reasoning and is read by future agents.
- `backtest-results.json` follows the [format below](#backtest-results-format).

### `backtest-results.json` format

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

### Creating a snapshot

**Automatic (preferred):** push to a `snapshots/*` branch. GitHub Actions picks it up and uploads.

```bash
git checkout -b snapshots/<strategy-name>
git add strategies/<strategy-name>/
git commit -m "<strategy-name>: sharpe=X.XX, +X% vs TWAP/VWAP"
git push origin snapshots/<strategy-name>
```

**Manual fallback:** GitHub → Actions → "Create Strategy Snapshot" → Run workflow, with:
- `strategy_name` = `<strategy-name>`
- `strategy_path` = `strategies/<strategy-name>`

Verify success in the Actions tab. The final log line shows the S3 path:

```
s3://<bucket>/strategies/<strategy-name>/2026-04-15T12-30-45Z-abc1234/
```

### Retrieving a snapshot

```bash
# List all snapshots for a strategy
aws s3 ls s3://$S3_BUCKET_NAME/strategies/<strategy-name>/

# Download one
aws s3 sync s3://$S3_BUCKET_NAME/strategies/<strategy-name>/2026-04-15T12-30-45Z-abc1234/ ./local-dir/
```

Snapshot contents:

```
<timestamp>-<commit-sha>/
├── code/                    # .py, requirements.txt
├── results/                 # backtest-results.json, trade-history.csv
├── NOTES.md
└── metadata.json            # timestamp, commit SHA, extracted metrics
```

For snapshot errors, see [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md#snapshots).

---

## Naming conventions

| Component | Format | Example |
|---|---|---|
| Strategy directory | kebab-case | `ofi-v1`, `mean-reversion-r2` |
| Snapshot branch | `snapshots/<strategy-name>` | `snapshots/ofi-v1` |
| Python files | snake_case | `order_flow_imbalance.py` |
| Results files | fixed names | `backtest-results.json`, `trade-history.csv` |

## Do's and don'ts

- **Do** fill in `NOTES.md` before snapshotting — hypothesis, implementation decisions, backtest observations.
- **Do** include `requirements.txt` for reproducibility.
- **Don't** commit files > 100 MB (use the data cache, not git).
- **Don't** include API keys or credentials in strategy code.
- **Don't** rely on snapshots as your only backup — commit to git too.
- **Don't** delete snapshots manually; they auto-expire after 30 days.
