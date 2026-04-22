# Architecture & Design

**Audience**: humans — researchers, infrastructure maintainers, project leads.

This document explains the design decisions, architecture, and operational economics of the data retrieval and snapshot system. For setup instructions see [AWS_SETUP.md](AWS_SETUP.md). For the canonical S3 layout see [DATA_STORAGE_CONTRACT.md](DATA_STORAGE_CONTRACT.md).

## Overview

A scalable, cost-efficient data retrieval system on AWS S3 that lets autonomous trading agents:

- Download only the data they need via selective date-based partitioning
- Reduce AWS costs by ~62% vs. full-dataset downloads
- Integrate cleanly into Docker-based backtesting workflows
- Retrieve data through a single CLI tool

## Problem and solution

**Problem:** 8.37 GB raw dataset from CME GLBX. Storing in git was expensive and slow. Agents needed a way to pull subsets on demand without paying for the full set each time.

**Solution:** split data by trading date (26 files, ~330 MB each) and download on demand. A 10-day backtest costs ~$0.13 instead of $0.32 for the full set. Each date is an atomic unit containing all symbols for that day.

## Architecture

```
┌─────────────────────────────────────────────┐
│  Autonomous Trading Agents (in Docker)      │
│  - Load data via data_retriever.py          │
│  - Run backtests                            │
│  - Save strategy snapshots                  │
└────────────────┬────────────────────────────┘
                 │
                 │ sync-partition (CLI)
                 ↓
        ┌──────────────────┐
        │  data_retriever  │
        │  Python CLI Tool │
        └────────┬─────────┘
                 │
                 │ AWS S3 API
                 ↓
    ┌────────────────────────────────┐
    │  AWS S3 Bucket                 │
    │  /datasets/glbx-mdp3/v1.0.0/   │
    │  ├─ manifest.json              │
    │  ├─ schema.json                │
    │  ├─ checksums.txt              │
    │  └─ partitions/                │
    │     ├─ date=20260308/          │
    │     ├─ date=20260309/          │
    │     └─ ... (26 dates total)    │
    └────────────────────────────────┘
```

## Key design decisions

### 1. DBN format (not Parquet)

Databento binary with zstd compression.

- Already compressed (better than Parquet for this data)
- Industry standard for market microstructure data
- No conversion step needed
- One atomic file per date, all symbols inside

### 2. Date-only partitioning (not date × symbol)

- Real trading data partitions naturally by date (26 files)
- Agents typically backtest date ranges, not fixed symbol lists
- Simpler mental model
- ~330 MB per date on average

**Rejected:** date × symbol would produce ~125,000 partitions with no backtest-workflow benefit.

### 3. S3 as primary storage (not git)

- Scales past the 8.37 GB we have today without architectural change
- Pay-per-use (~$0.21/month storage)
- Built-in lifecycle policies for retention
- Industry standard for ML/trading data pipelines

### 4. CLI tool for access (not direct S3)

`scripts/data_retriever.py` is an abstraction layer over S3. It provides:

- Automatic local caching (avoid re-downloads)
- Integrity verification via SHA256 checksums
- Manifest-based discovery so agents learn what's available dynamically
- A single point to swap in a different storage backend later

## Dataset overview

**CME GLBX Global FX Futures**
- Date range: 2026-03-08 to 2026-04-06 (26 trading days)
- Records: ~125,000,000 market data points
- Format: DBN + zstd
- Size: 8.37 GB total, ~330 MB per day

Record types:
- `MBP1Msg` — market-by-price (top-of-book bid/ask)
- `TradeMsg` — individual trades with action/side
- `OHLCVMsg` — OHLCV candles

## Cost analysis

This is the canonical cost table for the project — other docs reference it rather than restating numbers.

### Storage

| Item | Amount | Cost |
|---|---|---|
| Full dataset in S3 | 8.37 GB | ~$0.21/month |
| Metadata requests (manifest, schema) | ~50/month | ~$0.0002 |
| Snapshot storage (rolling 30-day) | 10–100 GB | $2–5/month |

### Data retrieval

| Scenario | Size | Cost |
|---|---|---|
| Single date | 0.33 GB | ~$0.01 |
| 10-day backtest | 3.3 GB | ~$0.13 |
| Full dataset | 8.37 GB | ~$0.32 |

### Monthly total

For moderate usage (50–100 retrievals + snapshot storage): **$5–10/month**. Well under the $10–50 project budget.

Why it stays cheap:
- Date partitioning means small, targeted downloads
- Agents only pay for data they actually use
- S3 transfer pricing ($0.09/GB) applies to downloads only; uploads are free
- Snapshot lifecycle policy auto-expires old data at 30 days

## Infrastructure requirements

- S3 bucket: `agentic-trading-snapshots-uchicago-spring-2026`
- IAM user with minimal permissions (PutObject, GetObject, ListBucket on this bucket only)
- No database, no persistent compute — agents do their own work in Docker

Credentials live in `.env` (never committed). Docker mounts them at runtime. GitHub Actions reads them from repository secrets.

## Operational considerations

**Monitoring.** AWS billing alerts catch runaway costs. Periodic `aws s3 ls --summarize` on the bucket confirms size is healthy. `data_retriever.py` calls are logged locally for audit.

**Retention.** Snapshots auto-expire at 30 days via S3 lifecycle policy. Dataset partitions have no automatic deletion — all data is immutable.

**Scaling.** Current design handles 8.37 GB without issue. Date partitioning remains efficient well past 100 GB. Adding a new dataset is additive — no changes to core tooling.

**EC2 access.** Once an EC2 instance is provisioned, SSH in with:

```
ssh -i your_key_pair.pem ubuntu@your_ip
```

For infrastructure or retrieval errors, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
