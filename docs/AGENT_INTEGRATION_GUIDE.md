# Agent Integration Guide: Data Retrieval & Strategy Development

This guide shows how autonomous agents can integrate data retrieval into their strategy development workflow.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Agent Workflow                        │
├─────────────────────────────────────────────────────────┤
│ 1. Discover available datasets in S3 manifest            │
│ 2. Fetch manifest.json to understand partition layout   │
│ 3. Select date ranges (e.g., "2026-03-08 to 2026-03-15") │
│ 4. Download selected date partitions to local cache     │
│ 5. Load DBN data into strategy backtest engine          │
│ 6. Iterate: modify strategy, re-test with same data    │
│ 7. Publish results to snapshots/agent-name branch      │
└─────────────────────────────────────────────────────────┘
        ↓ All data in Docker for reproducibility
┌─────────────────────────────────────────────────────────┐
│           Docker Container (agent:latest)               │
├─────────────────────────────────────────────────────────┤
│ Python 3.11 + AWS CLI + databento-dbn + numpy           │
│ Mounts: /workspace (strategy), /data-cache (persistent) │
└─────────────────────────────────────────────────────────┘
        ↓ Downloads from
┌─────────────────────────────────────────────────────────┐
│                    AWS S3 Bucket                         │
├─────────────────────────────────────────────────────────┤
│ datasets/                                                │
│ ├── glbx-mdp3-market-data/v1.0.0/                       │
│ │   ├── manifest.json                                   │
│ │   ├── schema.json                                     │
│ │   └── partitions/date=2026-03-08/data.dbn.zst        │
│ │       partitions/date=2026-03-09/data.dbn.zst        │
│ │       ... (one per trading date)                      │
│ ├── historical-data/v2.1.0/...                          │
│ └── market-data/v1.5.0/...                              │
│                                                          │
│ strategies/ (snapshots created by agents)               │
│ └── agent-momentum-1/2026-04-11-ABC123/                │
│     ├── code/momentum_strategy.py                       │
│     ├── results/backtest-results.json                   │
│     └── metadata.json                                   │
└─────────────────────────────────────────────────────────┘
```

## Step 1: Discover Datasets (Python)

```python
#!/usr/bin/env python3
"""Agent data discovery step."""

import subprocess
import os
import json

class AgentDataManager:
    def __init__(self):
        self.bucket = os.environ["S3_BUCKET_NAME"]
        self.region = os.environ.get("AWS_REGION", "us-east-1")
    
    def discover_datasets(self):
        """List available datasets."""
        cmd = f"aws s3 ls s3://{self.bucket}/datasets/ --region {self.region}"
        output = subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout
        datasets = [line.split()[-1].rstrip('/') for line in output.split('\n') if 'PRE' in line]
        return datasets
    
    def select_dataset(self):
        """Agent selects which dataset to use."""
        datasets = self.discover_datasets()
        print(f"Available datasets: {datasets}")
        
        # Example: Agent selects first dataset
        selected = datasets[0]
        print(f"Agent selected: {selected}")
        return selected

if __name__ == "__main__":
    manager = AgentDataManager()
    dataset = manager.select_dataset()
```

## Step 2: Fetch Manifest (CLI)

```bash
#!/bin/bash
# Agent runs this to understand dataset structure

DATASET_NAME="glbx-mdp3-market-data"
VERSION="v1.0.0"

# Get manifest
python /scripts/data_retriever.py fetch-manifest "$DATASET_NAME" "$VERSION" > manifest.json

# Parse manifest
python3 << 'PYTHON'
import json
with open("manifest.json") as f:
    m = json.load(f)
    
print(f"Date range: {m['date_range']['start']} to {m['date_range']['end']}")
print(f"Symbols: {', '.join(m['symbols'])}")
print(f"Total size: {m['total_size_bytes'] / (1024**3):.2f} GB")
print(f"Record count: {m['record_count']:,}")
PYTHON
```

## Step 3: Selective Retrieval (Agent Decision Logic)

Agent decides which partitions to download based on strategy:

```python
#!/usr/bin/env python3
"""Agent selects data partitions based on strategy goals."""

import json
from datetime import datetime, timedelta

class StrategyDataPlanner:
    def __init__(self, manifest_path="manifest.json"):
        with open(manifest_path) as f:
            self.manifest = json.load(f)
    
    def get_backtest_partitions(self, start_date, end_date, symbols):
        """Return list of partition paths to download."""
        
        partitions = []
        
        # Generate date range
        current = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        
        partitions = []
        while current <= end:
            date_str = current.strftime("%Y-%m-%d")
            partition = f"date={date_str}"
            if f"partitions/{partition}/data.dbn.zst" in self.manifest["partitions"]:
                partitions.append(partition)
            current += timedelta(days=1)
        
        return partitions

# Example: Momentum strategy needs 60 days of trading data
planner = StrategyDataPlanner()
partitions = planner.get_backtest_partitions(
    start_date="2026-03-12",
    end_date="2026-05-10",
    symbols=None  # All symbols in each date partition
)

print(f"Agent will download {len(partitions)} partitions (~{len(partitions) * 330} MB)")
for p in partitions[:5]:
    print(f"  {p}")
if len(partitions) > 5:
    print(f"  ... and {len(partitions) - 5} more")
```

## Step 4: Download Partitions

```bash
#!/bin/bash
# Download selected partitions for backtest

DATASET_NAME="glbx-mdp3-market-data"
VERSION="v1.0.0"

# Download one date partition
python /scripts/data_retriever.py sync-partition \
  "$DATASET_NAME" \
  "$VERSION" \
  "date=2026-03-08"

# Now data is in /data-cache/glbx-mdp3-market-data/v1.0.0/partitions/date=2026-03-08/data.dbn.zst
```

## Step 5: Load & Backtest

```python
#!/usr/bin/env python3
"""Agent loads data and runs backtest."""

import subprocess
from pathlib import Path
import databento_dbn as dbn

class BacktestEngine:
    def __init__(self, dataset_name, version, cache_dir="/data-cache"):
        self.cache_base = Path(cache_dir) / dataset_name / version / "partitions"
    
    def load_date_data(self, date):
        """Load DBN data for a single date partition."""
        partition_dir = self.cache_base / f"date={date}"
        dbn_file = partition_dir / "data.dbn.zst"
        
        if not dbn_file.exists():
            raise FileNotFoundError(f"No data found for {date}")
        
        # Load DBN file
        records = dbn.load_from_file(str(dbn_file))
        
        # Convert to DataFrame
        df = records.to_df()
        return df
    
    def backtest(self, strategy_func, start_date, end_date):
        """Run backtest on selected dates."""
        
        all_data = []
        current = pd.Timestamp(start_date)
            
            while current <= end:
                date_str = current.strftime("%Y-%m-%d")
                try:
                    df = self.load_partition_data(date_str, symbol)
                    all_data.append(df)
                except FileNotFoundError:
                    pass  # Partition not downloaded
                
                current += pd.Timedelta(days=1)
        
        if not all_data:
            raise ValueError("No data loaded")
        
        # Combine all data
        data = pd.concat(all_data, ignore_index=True).sort_values("timestamp")
        
        # Run strategy
        results = strategy_func(data)
        return results

# Example usage
def simple_momentum_strategy(data):
    """Example strategy."""
    # ... strategy implementation ...
    return {"returns": 0.15, "sharpe": 1.2, "max_dd": -0.08}

engine = BacktestEngine("us-equities-bars-1m", "v1.0.0")
results = engine.backtest(
    simple_momentum_strategy,
    start_date="2026-04-01",
    end_date="2026-04-10",
    symbols=["AAPL", "MSFT"]
)

print(f"Backtest results: {results}")
```

## Step 6: Iterate Locally

Agent can now iterate quickly without re-downloading:

```bash
#!/bin/bash
# Local iteration loop - data already cached

cd /workspace

# Run backtest 1
python strategy_v1.py --data-dir /data-cache

# Modify strategy
vim strategy_v2.py

# Run backtest 2 (data cache reused)
python strategy_v2.py --data-dir /data-cache

# Compare results, iterate...
```

## Step 7: Publish Results

Once satisfied, agent creates a snapshot:

```bash
#!/bin/bash
# Create snapshot of best strategy

# 1. Create snapshot branch
git checkout -b snapshots/agent-momentum-v2

# 2. Add strategy and results
cp strategy_v2.py /workspace/strategies/momentum-strategy/
cp backtest-results.json /workspace/strategies/momentum-strategy/results/

# 3. Commit and push to snapshots branch
git add strategies/
git commit -m "Agent momentum strategy v2: Sharpe 1.5, MDD -6%"
git push origin snapshots/agent-momentum-v2

# Workflow automatically uploads to S3!
```

---

## Complete Agent Workflow (Docker)

```bash
#!/bin/bash
# Complete agent iteration loop in Docker

set -e

# Setup
export S3_BUCKET_NAME="agentic-trading-snapshots-YOUR-SUFFIX"
export AWS_REGION="us-east-1"
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."

# Build agent image
docker build -t agent .

# Run agent
docker run --rm \
  -e AWS_REGION \
  -e S3_BUCKET_NAME \
  -e AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY \
  -v "$(pwd)/workspace:/workspace" \
  -v "$(pwd)/data-cache:/data-cache" \
  agent bash -c "
    # Discover datasets
    python /scripts/data_retriever.py list-datasets
    
    # Fetch manifest
    python /scripts/data_retriever.py fetch-manifest glbx-mdp3-market-data v1.0.0
    
    # Download data
    python /scripts/data_retriever.py sync-partition \
      glbx-mdp3-market-data v1.0.0 'date=2026-03-08'
    
    # Run strategy
    cd /workspace
    python strategy.py
    
    # Save results
    cp results.json /workspace/backtest-results.json
  "

# Results now in ./workspace/backtest-results.json
# Data cached in ./data-cache/ for next run
```

---

## Cost Optimization for Agents

### Download Cost Calculation

```
Single partition (1 date, 1 symbol): ~5-20 MB
  - Download: $0.0001
  - Request cost: $0.0000002
  - Total per partition: ~$0.00011

40-day backtest (40 dates, 1 symbol):
  - 40 downloads: $0.0044
  - Very cheap!

Full dataset (40 GB):
  - Download: $0.02
  - Request cost: $20 (1M file requests)
  - Total: ~$20 (expensive!)
```

**Best practice**: Always use selective partition sync.

### Data Cache Persistence

```
# First run: 100 MB downloaded
time: 5 minutes, cost: $0.00011

# Second run: Data cached
time: 10 seconds, cost: $0 (local cache hit)

# Same agent, 100 iterations
cost: $0.00011 total (download once, reuse 100x)
```

---

## Troubleshooting for Agents

| Problem | Solution |
|---------|----------|
| "S3_BUCKET_NAME not set" | Set env var: `export S3_BUCKET_NAME=...` |
| "Partition not found" | Check manifest for exact partition path |
| "Out of disk space" | Clean old data: `rm -rf ./data-cache/*` |
| "Download too slow" | Download smaller date ranges or fewer symbols |
| "Docker image too large" | Use `amazon/aws-cli:latest` instead of building custom |

---

## Example: Complete Momentum Strategy Agent

```python
#!/usr/bin/env python3
"""Complete momentum strategy agent with data retrieval."""

import json
import subprocess
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import os

class MomentumAgent:
    def __init__(self):
        self.bucket = os.environ["S3_BUCKET_NAME"]
        self.region = os.environ.get("AWS_REGION", "us-east-1")
        self.cache_dir = Path(os.environ.get("DATA_CACHE_DIR", "/data-cache"))
    
    def run(self):
        """Execute full workflow."""
        print("=== Momentum Agent Starting ===")
        
        # 1. Discover and select dataset
        dataset = self._select_dataset()
        version = self._select_version(dataset)
        
        # 2. Get manifest
        manifest = self._fetch_manifest(dataset, version)
        print(f"Dataset: {dataset} ({version})")
        print(f"  Date range: {manifest['date_range']}")
        print(f"  Symbols: {manifest['symbols']}")
        
        # 3. Plan backtest
        partitions = self._plan_backtest(manifest)
        print(f"Will download {len(partitions)} partitions")
        
        # 4. Download partitions
        self._download_partitions(dataset, version, partitions)
        
        # 5. Run backtest
        results = self._backtest(dataset, version, manifest)
        print(f"Results: {json.dumps(results, indent=2)}")
        
        # 6. Save results
        with open("/workspace/backtest-results.json", "w") as f:
            json.dump(results, f)
        
        print("=== Agent Complete ===")
        return results
    
    def _select_dataset(self):
        """Select dataset."""
        cmd = f"aws s3 ls s3://{self.bucket}/datasets/ --region {self.region}"
        output = subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout
        datasets = [line.split()[-1].rstrip('/') for line in output.split('\n') if 'PRE' in line]
        return datasets[0] if datasets else None
    
    def _select_version(self, dataset):
        """Select latest version."""
        cmd = f"aws s3 ls s3://{self.bucket}/datasets/{dataset}/ --region {self.region}"
        output = subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout
        versions = [line.split()[-1].rstrip('/') for line in output.split('\n') if 'PRE' in line]
        return sorted(versions)[-1] if versions else None
    
    def _fetch_manifest(self, dataset, version):
        """Get manifest."""
        manifest_path = self.cache_dir / dataset / version / "manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        
        s3_path = f"s3://{self.bucket}/datasets/{dataset}/{version}/manifest.json"
        cmd = f"aws s3 cp {s3_path} {manifest_path} --region {self.region}"
        subprocess.run(cmd, shell=True, check=True, capture_output=True)
        
        with open(manifest_path) as f:
            return json.load(f)
    
    def _plan_backtest(self, manifest):
        """Decide which partitions to download."""
        # Example: 10 days of trading data
        partitions = []
        start = datetime.strptime(manifest["date_range"]["start"], "%Y-%m-%d")
        for i in range(10):
            date = (start + timedelta(days=i)).strftime("%Y-%m-%d")
            partition = f"date={date}"
            if partition in [p.split("date=")[1].split("/")[0] for p in manifest["partitions"]]:
                partitions.append(partition)
        return partitions
    
    def _download_partitions(self, dataset, version, partitions):
        """Download partitions."""
        for partition in partitions:
            cmd = f"python /scripts/data_retriever.py sync-partition {dataset} {version} '{partition}'"
            subprocess.run(cmd, shell=True, check=True)
    
    def _backtest(self, dataset, version, manifest):
        """Run momentum strategy."""
        # Simplified backtest logic
        return {
            "strategy": "momentum",
            "total_return": 0.15,
            "sharpe_ratio": 1.2,
            "max_drawdown": -0.08,
            "win_rate": 0.58,
            "backtest_period": f"{manifest['date_range']['start']} to {manifest['date_range']['end']}",
            "symbols": ["AAPL", "MSFT"]
        }

if __name__ == "__main__":
    agent = MomentumAgent()
    agent.run()
```

Run with:
```bash
docker-compose run agent python /scripts/example_agent.py
```

---

## Next Steps

1. **Review contracts**: Read `docs/DATA_STORAGE_CONTRACT.md`
2. **Learn CLI**: Practice commands in `docs/DATA_OPERATIONS_PLAYBOOK.md`
3. **Build your agent**: Adapt example above for your strategy
4. **Test locally**: Run agent in Docker with sample data
5. **Deploy**: Push to snapshots/* branch, GitHub Actions creates snapshot
