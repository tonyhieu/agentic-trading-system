# Architecture & Design

This guide explains the strategic decisions, architecture, and operational
considerations for the autonomous execution-algorithm research environment.
For the agent's brief and the research loop, see `docs/OBJECTIVE.md`.

## Quick Overview

This repository runs **autonomous execution-algorithm research**:

- A trading strategy is held fixed (`research/config.yaml → strategy.name`).
- A research agent proposes new execution algorithms in
  `execution_algos/<algo-id>/`, registers them in the factory, and runs
  `run_backtest()` against a baseline (default `simple`).
- Passing algorithms are snapshotted to S3 via a `snapshots/*` branch push.
- Market data is stored in S3 and pulled on demand by the backtest engine —
  agents do not retrieve data directly.

## System flow

```
┌──────────────────────────────────────────────────────────────────┐
│  Research agent (.claude/agents/researcher.md)                   │
│                                                                  │
│  1. Read docs/OBJECTIVE.md + research/config.yaml                │
│  2. Read research/program_database.json (history)                │
│  3. Implement execution_algos/<algo-id>/execution_algorithm.py   │
│  4. Register in execution_algos/__init__.py                      │
│  5. Call run_backtest(strategy=oracle, exec=<algo-id>, date,...) │
│  6. Compare metrics.json vs baseline run                         │
│  7. Append to program_database.json + commit                     │
│  8. On PASS: push snapshots/<algo-id> branch                     │
└────────────────┬─────────────────────────────────┬───────────────┘
                 │                                 │
                 │ run_backtest() →                │ git push
                 │ load_dbn_partition() →          │ snapshots/*
                 │ DataRetriever.sync_partition    │
                 ↓                                 ↓
        ┌──────────────────┐          ┌────────────────────────┐
        │  data_retriever  │          │  GitHub Actions        │
        │  (internal)      │          │  snapshot-execution-   │
        └────────┬─────────┘          │  algo.yml              │
                 │                    └────────────┬───────────┘
                 │ AWS S3 read                     │ AWS S3 write
                 ↓                                 ↓
    ┌─────────────────────────────────────────────────────────┐
    │  AWS S3 Bucket                                          │
    │  ├─ datasets/glbx-mdp3-market-data/v1.0.0/              │
    │  │  ├─ manifest.json, schema.json, checksums.txt        │
    │  │  └─ partitions/date=YYYYMMDD/data.dbn.zst            │
    │  └─ execution_algos/<algo-id>/<timestamp>-<sha>/        │
    │     ├─ code/, results/, NOTES.md, metadata.json         │
    └─────────────────────────────────────────────────────────┘
```

## Key Design Decisions

### 1. Execution algorithm is the variable; strategy is the constant
Trading strategy is fixed across runs (configurable in `research/config.yaml
→ strategy`). The agent varies execution algorithms only. This means
results are directly attributable to execution choices, not signal noise.

### 2. DBN format with zstd compression for market data
- Already compressed (better than Parquet for tick-level data)
- Industry standard via Databento
- One atomic file per trading date contains all symbols
- ~330 MB per date partition

### 3. Date-only partitioning
26 trading days = 26 separate files. Agents typically backtest date ranges,
not symbol lists; symbol filtering happens in memory at load time. The
alternative (date × symbol) would have meant ~125,000 tiny partitions for
no win.

### 4. S3 for storage, not git
- Scales to large datasets (tested with 8.99 GB; can grow to 100+ GB)
- Pay-per-use pricing (~$0.21/month storage)
- Lifecycle policies handle retention
- Snapshots and dataset both live here, separated by S3 prefix

### 5. Data retrieval wrapped by the backtest engine
`backtest_engine/data_loader.py:load_dbn_partition()` calls
`DataRetriever.sync_partition` internally. Agents call `run_backtest()` and
data flow is automatic. The CLI (`scripts/data_retriever.py`) exists for
ad-hoc human/operator use, not as the agent path.

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

## Operational Considerations

### Monitoring & Alerts
- Set up AWS billing alerts to track costs
- Monitor S3 bucket size periodically
- Log all run_backtest() invocations for audit trails (the per-run dirs
  under `execution_algos/<algo-id>/results/` are themselves the audit log)

### Retention Policies
- No automatic deletion currently (data retained indefinitely)
- Can add 30/60/90-day lifecycle policies later if needed
- All data immutable (no versioning needed)

### Scaling Considerations
- ✅ Handles current 8.99 GB without issue
- ✅ Can scale to 100+ GB with same approach
- ✅ Date partitioning remains efficient
- ✅ Add new datasets without changing core system

## EC2 Instance Access

Setup an EC2 instance and run the following to SSH into it:

```
ssh -i your_key_pair.pem ubuntu@your_ip
```

## Troubleshooting & Support

See `troubleshooting.md` (next to this file) for:
- AWS authentication issues
- S3 access problems
- Workflow failures
- Cost issues

## Next Steps for Humans

1. **Review infrastructure**: see `aws-setup.md` for the full setup walkthrough.
2. **Agent entry point**: `docs/OBJECTIVE.md` (the brief) and `.claude/agents/researcher.md` (the agent).
