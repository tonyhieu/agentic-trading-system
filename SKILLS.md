# SKILLS: Strategy Snapshot System

This document provides instructions for autonomous agents on how to create snapshots of trading strategies using our automated backup system.

## 📸 What is a Snapshot?

A snapshot is a timestamped backup of your trading strategy that includes:
- **Code files** (.py, .ipynb, requirements.txt)
- **Backtesting results** (JSON, CSV, charts)
- **Metadata** (commit SHA, timestamp, performance metrics)

Snapshots are automatically uploaded to AWS S3 and retained for 30 days. They provide a reliable backup separate from the GitHub repository, preventing data loss from force pushes.

---

## 🚀 How to Create a Snapshot

There are two methods to create a snapshot: **Manual** and **Automatic**.

### Method 1: Manual Snapshot (Recommended for Testing)

Use this method when you want to manually trigger a snapshot for a specific strategy.

#### Step 1: Prepare Your Strategy

Ensure your strategy follows this directory structure:

```
strategies/
└── your-strategy-name/
    ├── strategy_file.py          # Your strategy code
    ├── requirements.txt           # Python dependencies (optional)
    └── results/                   # Backtesting results (optional)
        ├── backtest-results.json  # Performance metrics
        ├── trade-history.csv      # Trade log
        └── charts.png             # Visualization (optional)
```

**Important Notes:**
- Place your strategy in the `strategies/` directory
- Use a descriptive, kebab-case name (e.g., `momentum-trader`, `mean-reversion-v2`)
- Include a `results/backtest-results.json` file for automatic metric extraction

#### Step 2: Trigger Manual Snapshot via GitHub Actions

1. Go to your repository on GitHub
2. Navigate to **Actions** tab
3. Click **"Create Strategy Snapshot"** workflow (left sidebar)
4. Click **"Run workflow"** button (right side)
5. Fill in the inputs:
   - **Strategy name:** `your-strategy-name` (e.g., `momentum-trader`)
   - **Strategy path:** `strategies/your-strategy-name`
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
s3://your-bucket-name/strategies/your-strategy-name/2026-04-04T12-30-45Z-abc1234/
```

---

### Method 2: Automatic Snapshot (Recommended for Production)

Use this method to automatically create snapshots when you push code to special branches.

#### Step 1: Create a Snapshot Branch

```bash
# From your local repository
git checkout -b snapshots/your-strategy-name

# Example:
git checkout -b snapshots/momentum-trader-v2
```

Branch naming convention: `snapshots/{strategy-name}`

#### Step 2: Add or Update Your Strategy

```bash
# Make sure your strategy is in the strategies/ directory
mkdir -p strategies/your-strategy-name
cp your_code.py strategies/your-strategy-name/

# Add backtesting results
mkdir -p strategies/your-strategy-name/results
cp backtest-results.json strategies/your-strategy-name/results/

# Commit your changes
git add strategies/your-strategy-name/
git commit -m "Add momentum trading strategy with backtest results"
```

#### Step 3: Push to Trigger Snapshot

```bash
git push origin snapshots/your-strategy-name
```

This automatically triggers the snapshot workflow! The system will:
- Detect the push to a `snapshots/*` branch
- Extract the strategy name from the branch name
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
| Branch name | `snapshots/{strategy-name}` | `snapshots/momentum-trader` |
| Python files | `snake_case.py` | `momentum_strategy.py` |
| Results files | Specific names | `backtest-results.json`, `trade-history.csv` |

---

## 📊 Backtest Results Format

For automatic performance metric extraction, use this JSON structure in `backtest-results.json`:

```json
{
  "strategy_name": "Your Strategy Name",
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
s3://bucket-name/strategies/{strategy-name}/{timestamp}-{commit-sha}/
├── code/
│   ├── momentum_strategy.py
│   └── requirements.txt
├── results/
│   ├── backtest-results.json
│   └── trade-history.csv
└── metadata.json
```

### Option 1: View via AWS Console

1. Log in to AWS Console
2. Navigate to S3 service
3. Open your bucket (e.g., `agentic-trading-snapshots-*`)
4. Browse to `strategies/your-strategy-name/`
5. Select a timestamped snapshot folder
6. Download files as needed

### Option 2: Use AWS CLI

```bash
# List all snapshots for a strategy
aws s3 ls s3://your-bucket-name/strategies/your-strategy-name/

# Download a specific snapshot
aws s3 sync s3://your-bucket-name/strategies/your-strategy-name/2026-04-04T12-30-45Z-abc1234/ ./local-folder/

# Download just the metadata
aws s3 cp s3://your-bucket-name/strategies/your-strategy-name/2026-04-04T12-30-45Z-abc1234/metadata.json ./
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
# git push origin snapshots/my-strategy
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

For complete reference: `docs/DATA_OPERATIONS_PLAYBOOK.md` and `docs/AGENT_INTEGRATION_GUIDE.md`

---

### Manual Snapshot Command Sequence

```bash
# 1. Ensure strategy is in place
ls strategies/your-strategy-name/

# 2. Go to GitHub → Actions → Create Strategy Snapshot → Run workflow
# 3. Input: strategy_name = "your-strategy-name"
# 4. Input: strategy_path = "strategies/your-strategy-name"
# 5. Click "Run workflow"
```

### Automatic Snapshot Command Sequence

```bash
# 1. Create snapshot branch
git checkout -b snapshots/your-strategy-name

# 2. Add your strategy
mkdir -p strategies/your-strategy-name/results
cp your_code.py strategies/your-strategy-name/
cp backtest-results.json strategies/your-strategy-name/results/

# 3. Commit and push
git add strategies/your-strategy-name/
git commit -m "Add strategy with results"
git push origin snapshots/your-strategy-name

# 4. Check GitHub Actions for status
```

---

## ⚠️ Important Notes

### Do's ✅
- **Always** include meaningful backtest results in your snapshots
- **Use** descriptive strategy names (e.g., `momentum-trader-v2`, not `strategy1`)
- **Verify** your strategy structure before triggering a snapshot
- **Check** the Actions tab to confirm successful uploads
- **Include** a `requirements.txt` file for reproducibility

### Don'ts ❌
- **Don't** commit large data files (> 100MB) to the repository
- **Don't** include API keys or credentials in strategy code
- **Don't** use special characters in strategy names (stick to lowercase, hyphens)
- **Don't** rely solely on snapshots for version control (still use git commits)
- **Don't** manually delete snapshots from S3 (they auto-expire after 30 days)

---

## 🐛 Troubleshooting

### Snapshot Failed: "Strategy path does not exist"

**Cause:** The specified path doesn't exist in the repository.

**Solution:**
1. Verify your strategy exists: `ls strategies/your-strategy-name/`
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
1. Add `results/backtest-results.json` to your strategy directory
2. Follow the JSON structure shown in "Backtest Results Format" section
3. Validate JSON syntax: `cat backtest-results.json | python3 -m json.tool`

### Snapshot Missing Files

**Cause:** Files weren't in the expected locations or weren't committed.

**Solution:**
1. Ensure all files are in the strategy directory
2. Commit all files: `git add strategies/your-strategy-name/`
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

Here's a complete example of adding a new strategy and creating a snapshot:

```bash
# 1. Create your strategy locally
mkdir -p strategies/rsi-reversal-strategy/results

# 2. Write your strategy code
cat > strategies/rsi-reversal-strategy/rsi_strategy.py << EOF
# Your strategy code here
def calculate_rsi(prices, period=14):
    # RSI calculation
    pass
EOF

# 3. Create backtest results
cat > strategies/rsi-reversal-strategy/results/backtest-results.json << EOF
{
  "strategy_name": "RSI Reversal Strategy",
  "performance": {
    "total_return": 22.5,
    "sharpe_ratio": 1.8,
    "max_drawdown": -6.2,
    "win_rate": 65.0
  }
}
EOF

# 4. Create requirements file
cat > strategies/rsi-reversal-strategy/requirements.txt << EOF
pandas>=2.0.0
numpy>=1.24.0
ta-lib>=0.4.0
EOF

# 5. Commit your strategy
git add strategies/rsi-reversal-strategy/
git commit -m "Add RSI reversal strategy with backtest results"
git push origin main

# 6. Create automatic snapshot via branch
git checkout -b snapshots/rsi-reversal-strategy
git push origin snapshots/rsi-reversal-strategy

# 7. Verify in GitHub Actions
# Go to Actions tab and check for successful completion

# 8. Done! Your strategy is safely backed up to S3
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
python your_strategy.py

# 4. Save results
# Results saved to snapshots/your-strategy-name/...
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

**Last Updated:** 2026-04-15  
**System Version:** 1.0  
**Retention Policy:** 30 days
