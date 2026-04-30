# SKILLS: Execution Algorithm Snapshot System

This document provides instructions for autonomous agents on how to create snapshots of execution algorithms using our automated backup system.

## 📸 What is a Snapshot?

A snapshot is a timestamped backup of your execution algorithm that includes:
- **Code files** (.py, .ipynb, requirements.txt)
- **Backtesting results** (JSON, CSV, charts)
- **Metadata** (commit SHA, timestamp, performance metrics)
- **NOTES.md** (agent reasoning — hypothesis, implementation decisions, backtest observations)

Snapshots are automatically uploaded to AWS S3 and retained for 30 days. They provide a reliable backup separate from the GitHub repository, preventing data loss from force pushes.

---

## 🚀 How to Create a Snapshot

There are two methods to create a snapshot: **Manual** and **Automatic**.

### Method 1: Manual Snapshot (Recommended for Testing)

Use this method when you want to manually trigger a snapshot for a specific execution algorithm.

#### Step 1: Prepare Your Execution Algorithm

Ensure your execution algorithm follows this directory structure:

```
execution_algos/
└── your-algo-name/
    ├── algo_file.py              # Your execution algorithm code
    ├── NOTES.md                  # Agent reasoning (required — see PROBLEM_DEFINITION.md §10)
    ├── requirements.txt           # Python dependencies (optional)
    └── results/                   # Backtesting results (optional)
        ├── backtest-results.json  # Performance metrics
        ├── trade-history.csv      # Trade log
        └── charts.png             # Visualization (optional)
```

**Important Notes:**
- Place your algorithm in the `execution_algos/` directory
- Use a descriptive, kebab-case name (e.g., `my-algo-v1`, `execution-algo-v2`)
- Include a `results/backtest-results.json` file for automatic metric extraction
- Include a `NOTES.md` capturing your hypothesis, implementation decisions, and backtest observations — this is included in the snapshot and read by future agents

#### Step 2: Trigger Manual Snapshot via GitHub Actions

1. Go to your repository on GitHub
2. Navigate to **Actions** tab
3. Click **"Create Execution Algorithm Snapshot"** workflow (left sidebar)
4. Click **"Run workflow"** button (right side)
5. Fill in the inputs:
   - **Algorithm name:** `your-algo-name` (e.g., `my-algo`)
   - **Algorithm path:** `execution_algos/your-algo-name`
6. Click **"Run workflow"** (green button)

#### Step 3: Monitor Progress

1. The workflow will appear in the workflow runs list
2. Click on it to see real-time progress
3. Wait for the green checkmark (✅) indicating success
4. Review the workflow logs to see:
   - Snapshot timestamp and commit SHA
   - Files included in the snapshot
   - S3 upload location

#### Step 4: Verify Snapshot

The workflow automatically verifies that your snapshot was uploaded successfully. Check the final step for the S3 path:

```
s3://your-bucket-name/execution_algos/your-algo-name/2026-04-04T12-30-45Z-abc1234/
```

---

### Method 2: Automatic Snapshot (Recommended for Production)

Use this method to automatically create snapshots when you push code to special branches.

#### Step 1: Create a Snapshot Branch

```bash
# From your local repository
git checkout -b snapshots/your-algo-name

# Example:
git checkout -b snapshots/my-algo-v2
```

Branch naming convention: `snapshots/{algo-name}`

#### Step 2: Add or Update Your Execution Algorithm

```bash
# Make sure your algorithm is in the execution_algos/ directory
mkdir -p execution_algos/your-algo-name
cp your_code.py execution_algos/your-algo-name/

# Add backtesting results
mkdir -p execution_algos/your-algo-name/results
cp backtest-results.json execution_algos/your-algo-name/results/

# Commit your changes
git add execution_algos/your-algo-name/
git commit -m "Add momentum execution algorithm with backtest results"
```

#### Step 3: Push to Trigger Snapshot

```bash
git push origin snapshots/your-algo-name
```

This automatically triggers the snapshot workflow! The system will:
- Detect the push to a `snapshots/*` branch
- Extract the algorithm name from the branch name
- Package and upload the snapshot to S3

#### Step 4: Check GitHub Actions

1. Go to the **Actions** tab on GitHub
2. You'll see the workflow running automatically
3. Wait for completion and verify success

---

## 📋 Strategy Naming Conventions

Follow these naming conventions for consistency:

| Component | Format | Example |
|-----------|--------|---------|
| Strategy directory | `kebab-case` | `momentum-trader`, `mean-reversion-v2` |
| Branch name | `snapshots/{algo-name}` | `snapshots/my-algo` |
| Python files | `snake_case.py` | `momentum_algo.py` |
| Results files | Specific names | `backtest-results.json`, `trade-history.csv` |

---

## 📊 Backtest Results Format

For automatic performance metric extraction, use this JSON structure in `backtest-results.json`:

```json
{
  "algo_name": "Your Execution Algorithm Name",
  "backtest_date": "2026-04-04T12:00:00Z",
  "parameters": {
    "param1": "value1",
    "param2": "value2"
  },
  "performance": {
    "total_return": 15.34,
    "sharpe_ratio": 1.42,
    "max_drawdown": -8.67,
    "win_rate": 58.33,
    "total_trades": 24,
    "final_equity": 115340.00
  },
  "period": {
    "start_date": "2025-04-04",
    "end_date": "2026-04-04",
    "trading_days": 252
  }
}
```

**Key Fields:**
- `total_return`: Percentage return (e.g., 15.34 = 15.34%)
- `sharpe_ratio`: Risk-adjusted return metric
- `max_drawdown`: Maximum percentage loss from peak
- `win_rate`: Percentage of profitable trades

The snapshot system will automatically extract these metrics and include them in the snapshot metadata.

---

## 🔍 Retrieving Snapshots

Snapshots are stored in S3 with the following structure:

```
s3://bucket-name/execution_algos/{algo-name}/{timestamp}-{commit-sha}/
├── code/
│   ├── momentum_algo.py
│   └── requirements.txt
├── results/
│   ├── backtest-results.json
│   └── trade-history.csv
├── NOTES.md
└── metadata.json
```

### Option 1: View via AWS Console

1. Log in to AWS Console
2. Navigate to S3 service
3. Open your bucket (e.g., `agentic-trading-snapshots-*`)
4. Browse to `execution_algos/your-algo-name/`
5. Select a timestamped snapshot folder
6. Download files as needed

### Option 2: Use AWS CLI

```bash
# List all snapshots for an algorithm
aws s3 ls s3://your-bucket-name/execution_algos/your-algo-name/

# Download a specific snapshot
aws s3 sync s3://your-bucket-name/execution_algos/your-algo-name/2026-04-04T12-30-45Z-abc1234/ ./local-folder/

# Download just the metadata
aws s3 cp s3://your-bucket-name/execution_algos/your-algo-name/2026-04-04T12-30-45Z-abc1234/metadata.json ./
```

### Option 3: Use GitHub Actions (Future Enhancement)

A snapshot retrieval workflow will be added in the future to download snapshots directly through GitHub Actions.

---

## 📊 Data Retrieval for Strategy Development

Use the data retrieval system to fetch large datasets (research data, market data, historical bars) from AWS S3 for backtesting.

### Quick Start: Download Data

```bash
# 1. List available datasets
python /scripts/data_retriever.py list-datasets

# 2. Fetch manifest to understand structure
python /scripts/data_retriever.py fetch-manifest us-equities-bars-1m v1.0.0

# 3. Download specific partition
python /scripts/data_retriever.py sync-partition \
  us-equities-bars-1m v1.0.0 "date=2026-04-01/symbol=AAPL"

# Data now in: ./data-cache/us-equities-bars-1m/v1.0.0/partitions/...
```

### Load Data in Python

```python
import pandas as pd
import glob

# Find Parquet files for partition
files = glob.glob(
  "./data-cache/us-equities-bars-1m/v1.0.0/partitions/date=2026-04-01/symbol=AAPL/**/*.parquet",
  recursive=True
)

# Load data
df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
print(df.head())
```

### Docker: Isolated Execution

```bash
docker-compose run agent python /scripts/data_retriever.py list-datasets
docker-compose run agent python /scripts/data_retriever.py sync-partition \
  us-equities-bars-1m v1.0.0 "date=2026-04-01/symbol=AAPL"
```

### Cost Optimization

- **Single partition (1 date, 1 symbol)**: ~5-20 MB, $0.00011
- **40-day backtest**: 40 partitions, $0.0044 total
- **Full dataset (40 GB)**: $20+ (avoid!)

**Best practice**: Always use selective partition downloads for large datasets.

### Complete Backtest Integration

```python
#!/usr/bin/env python3
import subprocess
import pandas as pd
from pathlib import Path

# 1. Download data
subprocess.run([
  "python", "/scripts/data_retriever.py", "sync-partition",
  "us-equities-bars-1m", "v1.0.0", "date=2026-04-01/symbol=AAPL"
], check=True)

# 2. Load data
cache_dir = Path("./data-cache/us-equities-bars-1m/v1.0.0/partitions/date=2026-04-01/symbol=AAPL")
df = pd.read_parquet(list(cache_dir.glob("**/*.parquet"))[0])

# 3. Run backtest
results = {
  "total_return": 0.15,
  "sharpe_ratio": 1.2,
  "max_drawdown": -0.08
}

# 4. Save results
import json
with open("./results/backtest-results.json", "w") as f:
  json.dump(results, f)

# 5. Commit and push (creates snapshot)
# git add results/
# git commit -m "Backtest with AAPL data"
# git push origin snapshots/my-algo
```

### Data Discovery Contract

All datasets follow this structure:

```
s3://$S3_BUCKET_NAME/datasets/
└── {dataset-name}/
    └── {version}/
        ├── manifest.json         # Dataset metadata
        ├── schema.json           # Column definitions
        ├── checksums.txt         # File integrity
        └── partitions/
            ├── date=YYYY-MM-DD/symbol=TICKER/part-000.parquet
            └── ...
```

**manifest.json** contains:
- Dataset name and version
- Date range available
- List of symbols
- Total size in bytes
- Partition structure

See `docs/DATA_STORAGE_CONTRACT.md` for full specification.

### Advanced: Selective Retrieval

```python
from datetime import datetime, timedelta

# Strategy: Backtest momentum with 60 days of AAPL + MSFT
dataset = "us-equities-bars-1m"
version = "v1.0.0"
start_date = datetime(2026, 3, 12)
end_date = datetime(2026, 5, 10)

partitions = []
current = start_date
while current <= end_date:
    for symbol in ["AAPL", "MSFT"]:
        date_str = current.strftime("%Y-%m-%d")
        partition = f"date={date_str}/symbol={symbol}"
        partitions.append(partition)
    current += timedelta(days=1)

print(f"Downloading {len(partitions)} partitions (~{len(partitions)*10} MB)...")
for p in partitions:
    subprocess.run([
      "python", "/scripts/data_retriever.py", "sync-partition",
      dataset, version, p
    ], check=True)
```

### Troubleshooting Data Retrieval

| Issue | Fix |
|-------|-----|
| "S3_BUCKET_NAME not set" | `export S3_BUCKET_NAME=your-bucket` |
| "Partition not found" | Check manifest for exact path |
| "Connection timeout" | Verify AWS credentials and region |
| "Out of disk" | `rm -rf ./data-cache/` to clear cache |

For complete reference: See `docs/AGENT_INTEGRATION_GUIDE.md`

---

### Manual Snapshot Command Sequence

```bash
# 1. Ensure strategy is in place
ls execution_algos/your-algo-name/

# 2. Go to GitHub → Actions → Create Execution Algorithm Snapshot → Run workflow
# 3. Input: algo_name = "your-algo-name"
# 4. Input: algo_path = "execution_algos/your-algo-name"
# 5. Click "Run workflow"
```

### Automatic Snapshot Command Sequence

```bash
# 1. Create snapshot branch
git checkout -b snapshots/your-algo-name

# 2. Add your algorithm
mkdir -p execution_algos/your-algo-name/results
cp your_code.py execution_algos/your-algo-name/
cp backtest-results.json execution_algos/your-algo-name/results/

# 3. Commit and push
git add execution_algos/your-algo-name/
git commit -m "Add strategy with results"
git push origin snapshots/your-algo-name

# 4. Check GitHub Actions for status
```

---

## ⚠️ Important Notes

### Do's ✅
- **Always** include meaningful backtest results in your snapshots
- **Always** write a `NOTES.md` before snapshotting — hypothesis, implementation decisions, and backtest observations (see PROBLEM_DEFINITION.md §10 for the format)
- **Use** descriptive algorithm names (e.g., `momentum-trader-v2`, not `strategy1`)
- **Verify** your algorithm structure before triggering a snapshot
- **Check** the Actions tab to confirm successful uploads
- **Include** a `requirements.txt` file for reproducibility

### Don'ts ❌
- **Don't** commit large data files (> 100MB) to the repository
- **Don't** include API keys or credentials in strategy code
- **Don't** use special characters in algorithm names (stick to lowercase, hyphens)
- **Don't** rely solely on snapshots for version control (still use git commits)
- **Don't** manually delete snapshots from S3 (they auto-expire after 30 days)

---

## 🐛 Troubleshooting

### Snapshot Failed: "Strategy path does not exist"

**Cause:** The specified path doesn't exist in the repository.

**Solution:**
1. Verify your algorithm exists: `ls execution_algos/your-algo-name/`
2. Check that the path matches exactly (case-sensitive)
3. Ensure you've committed and pushed your code before running the workflow

### Snapshot Failed: "AWS credentials error"

**Cause:** GitHub secrets are not configured correctly.

**Solution:**
1. Contact repository administrator
2. Verify these secrets exist in GitHub Settings → Secrets:
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `AWS_REGION`
   - `S3_BUCKET_NAME`

### No Performance Metrics in Metadata

**Cause:** `backtest-results.json` is missing or incorrectly formatted.

**Solution:**
1. Add `results/backtest-results.json` to your algorithm directory
2. Follow the JSON structure shown in "Backtest Results Format" section
3. Validate JSON syntax: `cat backtest-results.json | python3 -m json.tool`

### Snapshot Missing Files

**Cause:** Files weren't in the expected locations or weren't committed.

**Solution:**
1. Ensure all files are in the strategy directory
2. Commit all files: `git add execution_algos/your-algo-name/`
3. Push before triggering snapshot: `git push`
4. Re-run the snapshot workflow

---

## 📞 Support

For issues with the snapshot system:

1. Check the **GitHub Actions logs** for detailed error messages
2. Review this SKILLS.md document for best practices
3. Consult the **AWS Setup Guide** (docs/AWS_SETUP_GUIDE.md) for infrastructure issues
4. Check the **Implementation Plan** (docs/IMPLEMENTATION_PLAN.md) for system architecture

---

## 🎓 Example Workflow

Here's a complete example of adding a new execution algorithm and creating a snapshot:

```bash
# 1. Create your algorithm locally
mkdir -p execution_algos/my-algo/results

# 2. Write your algorithm code
cat > execution_algos/my-algo/my_algo.py << EOF
# Your execution algorithm code here
class MyExecutionAlgorithm:
    def __init__(self, exec_id):
        self.exec_id = exec_id
    
    def execute(self, order):
        # Your algorithm implementation
        pass
EOF

# 3. Create backtest results
cat > execution_algos/my-algo/results/backtest-results.json << EOF
{
  "algo_name": "My Execution Algorithm",
  "performance": {
    "total_return": 22.5,
    "sharpe_ratio": 1.8,
    "max_drawdown": -6.2,
    "win_rate": 65.0
  }
}
EOF

# 4. Write agent reasoning (required before snapshotting)
cat > execution_algos/my-algo/NOTES.md << EOF
# Execution Algorithm Notes: my-algo

## Hypothesis

**Approach**: Describe the core execution strategy
**Why it works**: Explain the edge or inefficiency being exploited
**Why it survives costs**: Quantify the performance margin over transaction costs
**Parent algorithm**: Link to any parent algorithm or note if original
**Alternatives considered**: List other approaches tested and why they were rejected

---

## Implementation Decisions

Document key implementation choices, parameter selections, and trade-offs made.

---

## Backtest Observations

**What drove performance**: Conditions where the algorithm performs well
**What underperformed**: Conditions where the algorithm struggles
**Hypothesis verdict**: Was the hypothesis confirmed or rejected by backtesting?
**Suggested refinement**: What changes might improve the algorithm?
EOF

# 5. Create requirements file
cat > execution_algos/my-algo/requirements.txt << EOF
nautilus-trader>=1.225.0
pandas>=2.0.0
numpy>=1.24.0
EOF

# 6. Commit your algorithm
git add execution_algos/my-algo/
git commit -m "Add execution algorithm with backtest results"
git push origin main

# 7. Create automatic snapshot via branch
git checkout -b snapshots/my-algo
git push origin snapshots/my-algo

# 8. Verify in GitHub Actions
# Go to Actions tab and check for successful completion

# 9. Done! Your algorithm is safely backed up to S3 (including NOTES.md)
```

---

---

# 📊 Data Retrieval & Upload Skills

This section describes how autonomous agents can retrieve trading data from AWS S3 and upload their own datasets.

## 🎯 Available Datasets

### GLBX MDP3 Market Data (Chicago CME Global FX)

**Dataset:** `glbx-mdp3-market-data` | **Version:** `v1.0.0`

- **Format:** DBN (Databento Binary Format)
- **Compression:** zstd
- **Size:** 8.37 GB
- **Coverage:** 26 trading days (2026-03-08 to 2026-04-06)
- **Exchange:** GLBX (Chicago Mercantile Exchange)
- **Instruments:** Global FX futures (all symbols in one file per date)
- **Partitioning:** By trading date (one .dbn.zst file per date)
- **Location:** `s3://agentic-trading-snapshots-uchicago-spring-2026/datasets/glbx-mdp3-market-data/v1.0.0/`

---

## 🚀 How to Retrieve Data

### Step 1: Set Up Environment

```bash
# Set your AWS credentials (already configured in CI/CD)
export AWS_ACCESS_KEY_ID="your-key-id"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_REGION="us-east-2"
export S3_BUCKET_NAME="agentic-trading-snapshots-uchicago-spring-2026"
```

### Step 2: List Available Datasets

```bash
# List all available datasets
python scripts/data_retriever.py list-datasets

# Output:
# glbx-mdp3-market-data
# historical-data
# ... (more datasets)
```

### Step 3: Fetch Dataset Metadata

```bash
# Always fetch manifest first to understand what's available
python scripts/data_retriever.py fetch-manifest glbx-mdp3-market-data v1.0.0

# Output: manifest.json with partition list, checksums, date range
```

### Step 4: Download Specific Date Partitions

```bash
# Download a single date
python scripts/data_retriever.py sync-partition \
  glbx-mdp3-market-data v1.0.0 \
  "date=2026-03-08"

# Download multiple dates
for date in 2026-03-08 2026-03-09 2026-03-10; do
  python scripts/data_retriever.py sync-partition \
    glbx-mdp3-market-data v1.0.0 \
    "date=$date"
done

# Data downloaded to: ./data-cache/glbx-mdp3-market-data/v1.0.0/partitions/date=2026-03-08/data.dbn.zst
```

### Step 5: Load Data in Python

```python
import databento_dbn as dbn
from pathlib import Path

# Load a single date partition
dbn_file = Path("./data-cache/glbx-mdp3-market-data/v1.0.0/partitions/date=2026-03-08/data.dbn.zst")

# Load DBN file
records = dbn.load_from_file(str(dbn_file))

# Convert to pandas DataFrame
df = records.to_df()

print(f"Loaded {len(df)} records")
print(df.head())

# Filter by symbol/ticker (optional)
symbol_data = df[df['symbol'] == 'ES']  # E-mini S&P 500 futures
```

### Example: Complete Workflow

```bash
#!/bin/bash
# Strategy backtest workflow

DATASET="glbx-mdp3-market-data"
VERSION="v1.0.0"
START_DATE="2026-03-08"
END_DATE="2026-03-10"

# 1. Fetch metadata
python scripts/data_retriever.py fetch-manifest "$DATASET" "$VERSION"

# 2. Download date range
for date_int in {20260308..20260310}; do
  # Convert 20260308 to 2026-03-08
  year=${date_int:0:4}
  month=${date_int:4:2}
  day=${date_int:6:2}
  date_str="$year-$month-$day"
  
  echo "Downloading $date_str..."
  python scripts/data_retriever.py sync-partition "$DATASET" "$VERSION" "date=$date_str"
done

# 3. Run backtest
python your_algo.py

# 4. Save results
# Results saved to snapshots/your-algo-name/...
```

### Cost Information

- **Single date partition (~330 MB):** ~$0.01
- **10-day backtest (~3.3 GB):** ~$0.13
- **Full dataset (26 days, 8.37 GB):** ~$0.32

**Key insight:** Selective date retrieval costs 62% less than full downloads!

---

## 📤 How to Upload Your Own Dataset

### Prerequisites

- Dataset organized by trading date
- Compressed to zstd format (optional but recommended)
- Manifest, schema, and checksums files

### Step 1: Prepare Local Dataset Structure

```
my-dataset/
├── manifest.json          # Required
├── schema.json            # Recommended
├── checksums.txt          # Recommended
└── partitions/
    ├── date=2026-04-01/
    │   └── data.dbn.zst
    ├── date=2026-04-02/
    │   └── data.dbn.zst
    └── ... (one per trading date)
```

### Step 2: Create Manifest

```json
{
  "dataset_name": "my-trading-data",
  "dataset_version": "v1.0.0",
  "created_at": "2026-04-15T00:00:00Z",
  "format": "dbn",
  "compression": "zstd",
  "partition_scheme": ["date"],
  "partitions": [
    "partitions/date=2026-04-01/data.dbn.zst",
    "partitions/date=2026-04-02/data.dbn.zst"
  ],
  "total_size_bytes": 1000000000,
  "date_range": {
    "start": "2026-04-01",
    "end": "2026-04-02"
  },
  "exchange": "YOUR_EXCHANGE"
}
```

### Step 3: Upload to S3

```bash
# Sync entire dataset to S3
DATASET_NAME="my-trading-data"
VERSION="v1.0.0"

aws s3 sync ./my-dataset \
  "s3://$S3_BUCKET_NAME/datasets/$DATASET_NAME/$VERSION/" \
  --region us-east-2 \
  --no-progress

echo "✓ Dataset uploaded to S3"
```

### Step 4: Verify Upload

```bash
# List uploaded files
aws s3 ls "s3://$S3_BUCKET_NAME/datasets/$DATASET_NAME/$VERSION/" \
  --recursive \
  --region us-east-2

# Fetch manifest to verify it's readable
python scripts/data_retriever.py fetch-manifest "$DATASET_NAME" "$VERSION"
```

---

## 💡 Best Practices

1. **Always fetch manifest first** - Understand what partitions exist before downloading
2. **Use selective dates** - Don't download full dataset unless necessary
3. **Cache locally** - Reuse downloaded data across multiple strategy runs
4. **Validate checksums** - Verify data integrity using `checksums.txt`
5. **Use Docker** - Ensure reproducibility across agent runs

---

**Last Updated:** 2026-04-23 
**System Version:** 1.0  
**Retention Policy:** 30 days

---

# 🐳 Docker Execution Skill

This section describes how to build and run the backtesting environment using Docker.

## Why Docker?

Docker ensures every agent runs in an identical, reproducible environment regardless of the host machine. All dependencies (NautilusTrader, pandas, AWS CLI) are pre-installed in the image.

## Prerequisites

- Docker installed
- `.env` file with AWS credentials at repo root

## Quick Start

### Build the image

```bash
docker build -t agentic-trading .
```

### Run a backtest

```bash
docker-compose run --rm agent
```

### Run a single command

```bash
# Check Python version
docker-compose run --rm agent python --version

# Verify NautilusTrader is installed
docker-compose run --rm agent python -c "import nautilus_trader; print('ok')"

# Interactive shell for debugging
docker-compose run --rm dev
```

## Services

| Service | Purpose |
|---------|---------|
| `agent` | Runs full backtest via `python main.py` |
| `dev` | Interactive bash shell for development |
| `aws` | AWS CLI utility for S3 operations |

## Data Caching

Downloaded market data is persisted in `./data-cache/` and mounted into the container, so re-runs don't re-download data.

## Environment Variables

All credentials are loaded from `.env` file. See `.env.example` for required variables.

---

# 🎯 Execution Algorithm Evaluator Skill

This section describes how to retrieve evaluation results from the automated evaluator function and important cost considerations.

## ⚠️ CRITICAL: Cost and Resource Warning

The Execution Algorithm Evaluator is a **production resource that incurs AWS costs**. Before requesting algorithm evaluation:

1. **Run extensive local backtests first** - Verify your algorithm works correctly on your development machine
2. **Test on sample data** - Don't submit untested code to the evaluator
3. **Minimize iterations** - Each evaluation costs approximately **$0.30** (1 GB Lambda, ~12 minutes runtime)
4. **Request evaluation sparingly** - Only after you've thoroughly validated locally

**Abuse Policy:** Agents that repeatedly submit untested or buggy algorithms will have their evaluation privileges revoked. Test first, evaluate second.

## Overview

After you push an execution algorithm to a `snapshots/{algo_name}` branch, the evaluation system automatically:

1. **Triggers Lambda Evaluator** - S3 event automatically invokes the evaluator
2. **Runs 7-day backtest** - Tests against out-of-sample data (March 30 - April 6, 2026)
3. **Computes metrics** - Generates 8 execution metrics from backtest results
4. **Stores results** - Saves evaluation report to S3

## Where to Find Evaluation Results

### Location in S3

Evaluation results are stored in your S3 bucket at:

```
s3://agentic-trading-snapshots-uchicago-spring-2026/
  └── evaluation-reports/
      └── {algo_name}/
          ├── {timestamp}_evaluation_report.json      # Main results
          ├── {timestamp}_backtest_logs.txt           # Execution logs
          └── {timestamp}_metrics_summary.json        # Metric summary
```

### Accessing Results

#### Via AWS CLI

```bash
# List all evaluation reports
aws s3 ls s3://agentic-trading-snapshots-uchicago-spring-2026/evaluation-reports/ --recursive

# Download a specific report
aws s3 cp s3://agentic-trading-snapshots-uchicago-spring-2026/evaluation-reports/{algo_name}/{timestamp}_evaluation_report.json .

# Stream report to console
aws s3 cp s3://agentic-trading-snapshots-uchicago-spring-2026/evaluation-reports/{algo_name}/{timestamp}_evaluation_report.json - | python -m json.tool
```

#### Via Python Script

```python
import boto3
import json

s3 = boto3.client('s3', region_name='us-east-2')
bucket = 'agentic-trading-snapshots-uchicago-spring-2026'

# List all reports for an algorithm
response = s3.list_objects_v2(
    Bucket=bucket,
    Prefix='evaluation-reports/my-algo-name/'
)

# Download and parse latest report
for obj in response.get('Contents', []):
    if 'evaluation_report.json' in obj['Key']:
        response = s3.get_object(Bucket=bucket, Key=obj['Key'])
        report = json.load(response['Body'])
        print(report)
```

## Evaluation Report Structure

Each evaluation report contains:

```json
{
  "algorithm_name": "my-algo-v1",
  "evaluation_date": "2026-04-30T00:00:00Z",
  "backtest_period": {
    "start": "2026-03-30",
    "end": "2026-04-06",
    "days_oos": 7
  },
  "execution_metrics": {
    "slippage_bps": 12.5,              # Average slippage (basis points)
    "execution_time_ms": 245.3,         # Average execution time
    "fill_accuracy_pct": 98.7,          # % of orders filled at expected price
    "latency_ms": 42.1,                 # Order latency
    "cost_bps": 8.3,                    # Execution cost (basis points)
    "orders_per_second": 15.2,          # Throughput
    "execution_time_variance_ms": 89.4, # Variability
    "peak_latency_ms": 156.3            # Maximum latency observed
  },
  "performance_summary": {
    "total_trades": 523,
    "successful_fills": 516,
    "failed_fills": 7,
    "avg_profit_per_trade": 1.23,
    "total_pnl": 642.09
  },
  "status": "completed",
  "errors": []
}
```

## Monitoring Evaluation Progress

### Check CloudWatch Logs

```bash
# Stream Lambda logs in real-time
aws logs tail /aws/lambda/execution-algorithm-evaluator --follow --region us-east-2

# View last 50 lines
aws logs tail /aws/lambda/execution-algorithm-evaluator --max-items 50 --region us-east-2
```

### Check Function Execution

```bash
# Get function invocation metrics for last hour
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=execution-algorithm-evaluator \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum \
  --region us-east-2
```

## Troubleshooting Evaluations

### Status: "pending"
Algorithm is queued for evaluation. Check back in 5-10 minutes.

### Status: "failed" with error "Branch not found"
- Verify `snapshots/{algo_name}` branch exists in repository
- Check branch name spelling and formatting (kebab-case)
- Ensure branch has been pushed to GitHub

### Status: "failed" with error "Algorithm import error"
- Algorithm code has syntax errors
- Missing required dependencies in `requirements.txt`
- Review backtest logs in S3 for detailed error message

### Status: "timeout" after 15 minutes
- Backtest took too long on 7 days of data
- Algorithm may have performance issues
- Consider profiling locally first

## Best Practices

1. **Local validation first** - Always backtest locally before submitting to evaluator
2. **Include NOTES.md** - Document your algorithm's approach for future review
3. **Check results quickly** - Results are retained for 30 days; download before they expire
4. **Archive good results** - Keep copies of successful evaluation reports for comparison
5. **Iterate thoughtfully** - Each evaluation iteration costs money; make it count

## Cost Tracking

Each evaluation incurs approximately:
- **Compute**: $0.20 (1 GB memory × 10-12 minutes)
- **S3 storage**: $0.01 per evaluation report (retrieval costs included in monthly)
- **Data transfer**: Minimal (within AWS region)

**Total per evaluation: ~$0.30**

---

## 🐛 Local Debugging: Free Algorithm Testing

**RECOMMENDED:** Before using the cloud evaluator, test your execution algorithm locally using the free debugging script.

### Why Use Local Testing?

- **Cost**: Free (no AWS charges)
- **Speed**: Instant feedback (2-3 minutes vs. 12+ minute cloud evaluation)
- **Development**: Iterate rapidly without worrying about costs
- **Debugging**: Full console output and error messages
- **Same format**: Output matches Lambda evaluator exactly (same metrics, same JSON)

### Local Evaluator Script

Use `scripts/local-evaluator.py` to evaluate algorithms locally on in-sample data:

```bash
# Test an algorithm locally
python3 scripts/local-evaluator.py <algorithm_name> [num_days]

# Examples:
python3 scripts/local-evaluator.py simple              # Test "simple" algo on 2 days
python3 scripts/local-evaluator.py my_algo 3           # Test "my_algo" on 3 in-sample days
```

### How It Works

1. **Checks for cached data** - If 2-3 days of in-sample data exist locally, uses them (skip S3 download)
2. **Downloads (if needed)** - Fetches in-sample data from S3 (March 23-29, 2026)
3. **Downloads algorithm** - Fetches your algorithm from `snapshots/{algorithm_name}` branch
4. **Runs backtests** - Executes same backtest logic as Lambda (EMA cross strategy + your execution algorithm)
5. **Computes metrics** - Generates 8 execution metrics (identical to cloud evaluator)
6. **Saves report** - Stores JSON report to `local-cache/evaluation-reports/{algorithm_name}/`

### Environment Variables

```bash
# Optional - defaults provided
GITHUB_REPO="tonyhieu/agentic-trading-system"  # Your fork/repo
GITHUB_TOKEN=""                                 # Token for private repos
S3_BUCKET_NAME="agentic-trading-snapshots-uchicago-spring-2026"
AWS_REGION="us-east-2"
LOCAL_CACHE_DIR="./local-cache"                # Where to cache data
```

### Output Format

Results are saved in two formats (both to `local-cache/evaluation-reports/{algo_name}/`):

**JSON Report** (`{timestamp}_evaluation_report.json`):
```json
{
  "algorithm_name": "my_algo",
  "evaluation_timestamp": "2026-04-30T17:25:23.087-05:00",
  "evaluation_type": "local_debug",
  "metrics": {
    "slippage_bps": {"mean": 1.2, "min": 0.5, "max": 2.1, "count": 3},
    "execution_time_ms": {"mean": 45.3, ...},
    "fill_accuracy_pct": {"mean": 99.8, ...},
    ...
  },
  "in_sample_period": {
    "dates": ["20260323", "20260324", "20260325"],
    "duration_days": 3
  }
}
```

### Workflow

**Step 1: Test Locally (Free)**
```bash
cd /Users/avo/GitHub/agentic-trading-system
python3 scripts/local-evaluator.py my_algo 2
```

**Step 2: Review Results**
```bash
cat local-cache/evaluation-reports/my_algo/*/evaluation_report.json | python3 -m json.tool
```

**Step 3: Iterate & Refine**
- Fix algorithm issues (if any detected)
- Re-test locally until satisfied
- No AWS costs, fast feedback loop

**Step 4: Submit to Cloud (When Ready)**
- Only after local testing passes
- Push to `snapshots/{algo_name}` branch
- Lambda evaluator runs automatically on out-of-sample data
- ~$0.30 cost, ~12 minute wait

### Common Issues

**"No data found"** → Download S3 data (requires AWS credentials and S3_BUCKET_NAME)

**"Import error"** → Algorithm must be valid Python, check `execution_algos/` examples

**"Backtest failed"** → Check algorithm code, review console output for errors

### Data

Local evaluator uses **in-sample data** (2-3 days from March 23-29, 2026):
- Same market conditions as what Lambda sees
- Subset of ~19 in-sample partitions available
- Cached locally after first download

Cloud evaluator uses **out-of-sample data** (7 days from March 30 - April 6, 2026):
- Never seen during development
- True test of algorithm quality
- Reserved for final evaluation only

### Example: Full Development Cycle

```bash
# 1. Create new algorithm (push to snapshots/my_test_algo)

# 2. Test locally first (free, instant feedback)
python3 scripts/local-evaluator.py my_test_algo 3

# 3. Review results
cat local-cache/evaluation-reports/my_test_algo/*/evaluation_report.json | python3 -m json.tool

# 4. Iterate & refine (repeat 2-3 until happy)

# 5. Only then, submit for cloud evaluation
# → Lambda will test on 7 days of out-of-sample data
# → You'll get official metrics in 12 minutes
# → Results in s3://agentic-trading-snapshots-uchicago-spring-2026/evaluation-reports/my_test_algo/
```

### Summary

| Aspect | Local Testing | Cloud Evaluator |
|--------|---------------|-----------------|
| **Cost** | Free | ~$0.30 |
| **Time** | 2-3 min | 12+ min |
| **Data** | In-sample (train) | Out-of-sample (test) |
| **Use Case** | Development/Debugging | Final Validation |
| **Output** | Same format | Same format |

**Rule: Always test locally before cloud evaluation. Save money, iterate faster.**

Budget responsibly: 10 iterations = $3.00, 100 iterations = $30.00
