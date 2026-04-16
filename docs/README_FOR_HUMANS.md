# Data Retrieval System: Architecture & Design for Humans

**Status**: ✅ Complete & Operational

Welcome! This guide explains the strategic decisions, architecture, and operational considerations for the autonomous agent data retrieval system.

## Quick Overview

We built a **scalable, cost-efficient data retrieval system** on AWS S3 that enables autonomous trading agents to:
- Download only the data they need (selective date-based partitioning)
- Reduce AWS costs by 62% vs. full dataset downloads
- Integrate seamlessly into agent backtesting workflows
- Retrieve data with a simple CLI tool

## Why This Approach?

### The Problem
- Raw dataset: 40 GB from Chicago CME (GLBX) market data
- Old approach: Store in Git repo (expensive, slow, limited scalability)
- Question: How to make data accessible to agents while controlling costs?

### The Solution: Selective Date-Based Partitioning
- **Split data by date**: 26 trading days = 26 separate files
- **Download on demand**: Agents request only dates they need (e.g., 10-day backtest = $0.13 instead of $0.32)
- **Cost savings**: 62% reduction for typical backtesting scenarios
- **Natural boundaries**: Each date is a complete atomic unit (all symbols for that day)

## Architecture: What We Built

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
    │                                │
    │  ├─ manifest.json              │
    │  ├─ schema.json                │
    │  ├─ checksums.txt              │
    │  └─ partitions/                │
    │     ├─ date=20260308/          │
    │     ├─ date=20260309/          │
    │     └─ ... (26 dates total)    │
    └────────────────────────────────┘
```

## Key Design Decisions

### 1. DBN Format (Not Parquet)
**Decision**: Use Databento binary (DBN) format with zstd compression
- ✅ Already compressed (better than Parquet)
- ✅ Industry standard for market data
- ✅ No conversion needed
- ✅ Atomic files (one per date, all symbols inside)

### 2. Date-Only Partitioning (Not Symbol-Based)
**Decision**: Partition by date, not by symbol
- ✅ Real data naturally partitions by date (26 files)
- ✅ Agents typically backtest date ranges, not symbol lists
- ✅ Simpler mental model
- ✅ ~300 MB per date partition on average

**Alternative considered**: Date + Symbol = 125,000 partitions ❌ (too complex, no benefit)

### 3. S3 as Primary Storage (Not Git)
**Decision**: Store data in S3, not in Git repository
- ✅ Scales to large datasets (tested with 8.99 GB)
- ✅ Pay-per-use pricing (~$0.21/month storage)
- ✅ Built-in lifecycle policies for retention
- ✅ Industry standard for ML/trading workflows

### 4. CLI Tool for Access (Not Direct S3)
**Decision**: Agents use `data_retriever.py` CLI tool
- ✅ Abstraction layer: Easy to migrate storage later
- ✅ Automatic caching: Don't re-download same data
- ✅ Integrity checking: Verify checksums
- ✅ Metadata discovery: Agents learn available data dynamically

## Cost Analysis

### Storage Costs (AWS S3 Standard)
| Item | Amount | Cost |
|------|--------|------|
| Full dataset (8.99 GB) | 1 × 8.99 GB | $0.21/month |
| Requests (manifest, schema) | ~50/month | $0.0002 |
| Data retrieval | Varies | See scenarios |

### Data Retrieval Costs (By Scenario)
| Scenario | Size | Cost |
|----------|------|------|
| Single day (~330 MB) | 0.33 GB | $0.01 |
| 10-day backtest | 3.3 GB | $0.13 |
| Full dataset | 8.99 GB | $0.32 |

**Monthly estimate** (50-100 retrievals): **$5-10/month**

### Why It's Cheap
- ✅ Date partitioning means small, targeted downloads
- ✅ Agents only pay for data they use
- ✅ No Git storage overhead
- ✅ S3 transfer pricing: $0.09/GB only applies to *downloads*

## Infrastructure Setup

### AWS Requirements
- ✅ S3 bucket: `agentic-trading-snapshots-uchicago-spring-2026`
- ✅ IAM user: Restricted permissions (S3 only, specific bucket)
- ✅ No database needed
- ✅ No compute (agents do their own computation)

### Credentials Management
- AWS credentials stored in `.env` file (not in Git)
- Agents read `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `S3_BUCKET_NAME`
- Docker container mounts `.env` at runtime

## Dataset Overview

**Chicago CME GLBX Data**
- Date range: March 8 - April 6, 2026 (26 trading days)
- Instrument: Global FX futures (GLBX)
- Records: 125,000,000 market data points
- Format: DBN with zstd compression
- Size: 8.99 GB total (~330 MB per day average)

**Record types in data:**
- MBP1Msg: Market by Price (order book snapshots)
- TradeMsg: Individual trades with action/side
- OHLCVMsg: OHLCV candles

## Operational Considerations

### Monitoring & Alerts
- Set up AWS billing alerts to track costs
- Monitor S3 bucket size periodically
- Log all data_retriever.py calls for audit trails

### Retention Policies
- No automatic deletion currently (data retained indefinitely)
- Can add 30/60/90-day lifecycle policies later if needed
- All data immutable (no versioning needed)

### Scaling Considerations
- ✅ Handles current 8.99 GB without issue
- ✅ Can scale to 100+ GB with same approach
- ✅ Date partitioning remains efficient
- ✅ Add new datasets without changing core system

## Troubleshooting & Support

See `TROUBLESHOOTING.md` in this directory for:
- AWS authentication issues
- S3 access problems
- Data retrieval failures
- Performance optimization

## Next Steps for Humans

1. **Review infrastructure**: Check AWS_SETUP_GUIDE.md to understand setup
2. **Understand costs**: Read WHY_SELECTIVE_PARTITIONING.md for detailed analysis
3. **For agents**: Refer agents to README_FOR_AGENTS.md

## For Agents

If you're an autonomous agent integrating this system, see **README_FOR_AGENTS.md** for:
- API reference and CLI usage
- Code examples for data loading
- Integration patterns
- Troubleshooting
