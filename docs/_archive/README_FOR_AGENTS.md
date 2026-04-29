# Data Retrieval System: Integration Guide for Agents

**Status**: ✅ Production Ready

This guide is for autonomous trading agents that need to retrieve market data for backtesting and strategy development.

## Quick Start (5 Minutes)

### 1. Set Environment Variables
```bash
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
export AWS_REGION="us-east-2"
export S3_BUCKET_NAME="agentic-trading-snapshots-uchicago-spring-2026"
```

### 2. Discover Available Data
```bash
python scripts/data_retriever.py list-datasets
python scripts/data_retriever.py list-versions glbx-mdp3-market-data
```

### 3. Download a Partition
```bash
python scripts/data_retriever.py sync-partition "glbx-mdp3-market-data" "v1.0.0" "date=20260309"
```

### 4. Load and Analyze
```python
import databento_dbn as dbn
from pathlib import Path

dbn_file = Path("data-cache/glbx-mdp3-market-data/v1.0.0/partitions/date=20260309/data.dbn.zst")

with open(dbn_file, "rb") as f:
    decoder = dbn.DBNDecoder(f)
    df = decoder.to_df()
    
    print(f"Loaded {len(df)} records")
    print(f"Columns: {list(df.columns)}")
    print(df.head())
```

## API Reference

### CLI Tool: `data_retriever.py`

#### List Datasets
```bash
python scripts/data_retriever.py list-datasets
```
Returns: `glbx-mdp3-market-data` (Chicago CME GLBX data)

#### List Versions
```bash
python scripts/data_retriever.py list-versions <dataset>
```
Example:
```bash
python scripts/data_retriever.py list-versions glbx-mdp3-market-data
# Output: v1.0.0
```

#### Fetch Manifest (Dataset Inventory)
```bash
python scripts/data_retriever.py fetch-manifest <dataset> <version>
```
Example:
```bash
python scripts/data_retriever.py fetch-manifest glbx-mdp3-market-data v1.0.0
```

Returns JSON with:
- List of all 26 date partitions
- Total size: 8.99 GB
- Record count: 125,000,000
- Date range: 2026-03-08 to 2026-04-06

#### Fetch Schema (Data Structure)
```bash
python scripts/data_retriever.py fetch-schema <dataset> <version>
```

Returns JSON describing:
- **MBP1Msg**: Market by Price (order book)
  - `ts_event`: Exchange timestamp (nanoseconds)
  - `ts_recv`: Receiver timestamp (nanoseconds)
  - `bid_px`, `ask_px`: Bid/ask prices
  - `bid_sz`, `ask_sz`: Bid/ask sizes
- **TradeMsg**: Individual trades
  - `ts_event`, `ts_recv`: Timestamps
  - `side`: 1=Buy, 2=Sell
  - `action`: Trade action code
  - `price`, `size`: Price and quantity
  - `depth`: Market depth level
- **OHLCVMsg**: Candles
  - `ts_event`: Candle timestamp
  - `open`, `high`, `low`, `close`, `volume`

#### Download Partition
```bash
python scripts/data_retriever.py sync-partition <dataset> <version> <partition>
```

Example:
```bash
# Download one day
python scripts/data_retriever.py sync-partition "glbx-mdp3-market-data" "v1.0.0" "date=20260309"

# Download multiple dates
python scripts/data_retriever.py sync-partition "glbx-mdp3-market-data" "v1.0.0" "date=20260310"
python scripts/data_retriever.py sync-partition "glbx-mdp3-market-data" "v1.0.0" "date=20260311"
```

Downloaded files cached in: `data-cache/glbx-mdp3-market-data/v1.0.0/partitions/date=YYYYMMDD/`

#### Validate Checksums
```bash
python scripts/data_retriever.py validate <dataset> <version>
```

Verifies integrity of downloaded files against SHA256 checksums.

## Code Examples

### Example 1: Load One Day of Data
```python
import subprocess
import databento_dbn as dbn
from pathlib import Path

# Download
subprocess.run([
    "python", "scripts/data_retriever.py", "sync-partition",
    "glbx-mdp3-market-data", "v1.0.0", "date=20260309"
])

# Load
dbn_file = Path("data-cache/glbx-mdp3-market-data/v1.0.0/partitions/date=20260309/data.dbn.zst")
with open(dbn_file, "rb") as f:
    decoder = dbn.DBNDecoder(f)
    df = decoder.to_df()
    
print(f"Shape: {df.shape}")
print(f"Columns: {list(df.columns)}")
```

### Example 2: Multi-Day Backtest
```python
import subprocess
import databento_dbn as dbn
from pathlib import Path
import pandas as pd

# Define date range
dates = ["20260309", "20260310", "20260311"]

# Download all dates
for date in dates:
    subprocess.run([
        "python", "scripts/data_retriever.py", "sync-partition",
        "glbx-mdp3-market-data", "v1.0.0", f"date={date}"
    ])

# Load and concatenate
dfs = []
for date in dates:
    dbn_file = Path(f"data-cache/glbx-mdp3-market-data/v1.0.0/partitions/date={date}/data.dbn.zst")
    with open(dbn_file, "rb") as f:
        decoder = dbn.DBNDecoder(f)
        dfs.append(decoder.to_df())

combined = pd.concat(dfs, ignore_index=True)
print(f"Total records: {len(combined)}")

# Run your backtest
# ... your strategy code here
```

### Example 3: Filter by Record Type
```python
import databento_dbn as dbn
from pathlib import Path

dbn_file = Path("data-cache/glbx-mdp3-market-data/v1.0.0/partitions/date=20260309/data.dbn.zst")

with open(dbn_file, "rb") as f:
    decoder = dbn.DBNDecoder(f)
    df = decoder.to_df()
    
    # Get only MBP (order book) records
    mbp_records = df[df['rtype'] == 'MBP1Msg']
    
    # Get only trade records
    trade_records = df[df['rtype'] == 'TradeMsg']
    
    print(f"MBP records: {len(mbp_records)}")
    print(f"Trade records: {len(trade_records)}")
```

### Example 4: Cost-Efficient Backtesting
```python
# Query manifest to find available dates
import subprocess
import json

result = subprocess.run([
    "python", "scripts/data_retriever.py", "fetch-manifest",
    "glbx-mdp3-market-data", "v1.0.0"
], capture_output=True, text=True)

manifest = json.loads(result.stdout)
all_dates = [p.split('=')[1].split('/')[0] for p in manifest['partitions']]

print(f"Available dates: {all_dates}")
print(f"Cost for 1 day: $0.01")
print(f"Cost for 10 days: $0.13")
print(f"Cost for full dataset: $0.32")

# Download only what you need
backtest_dates = all_dates[:10]  # First 10 trading days
total_cost = 0.01 * len(backtest_dates)
print(f"Cost for your backtest: ${total_cost}")
```

## Data Format Details

### S3 Storage Structure
```
s3://agentic-trading-snapshots-uchicago-spring-2026/
└── datasets/
    └── glbx-mdp3-market-data/
        └── v1.0.0/
            ├── manifest.json          # Dataset inventory
            ├── schema.json            # Data structure definition
            ├── checksums.txt          # File integrity hashes
            └── partitions/
                ├── date=20260308/
                │   └── data.dbn.zst
                ├── date=20260309/
                │   └── data.dbn.zst
                └── ... (26 total)
```

### Manifest Format
```json
{
  "dataset_name": "glbx-mdp3-market-data",
  "dataset_version": "v1.0.0",
  "format": "dbn",
  "compression": "zstd",
  "partition_scheme": ["date"],
  "partitions": [
    "partitions/date=20260308/data.dbn.zst",
    "partitions/date=20260309/data.dbn.zst",
    ...
  ],
  "total_size_bytes": 8990765938,
  "record_count": 125000000,
  "date_range": {
    "start": "20260308",
    "end": "20260406"
  }
}
```

## Performance Tips

### 1. Cache Locally
The system automatically caches downloads in `data-cache/`. Subsequent requests for the same date won't re-download.

### 2. Download in Parallel
For multi-day backtests, download multiple dates at once:
```python
import concurrent.futures
import subprocess

dates = ["20260309", "20260310", "20260311"]

def download_date(date):
    subprocess.run([
        "python", "scripts/data_retriever.py", "sync-partition",
        "glbx-mdp3-market-data", "v1.0.0", f"date={date}"
    ])

with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
    executor.map(download_date, dates)
```

### 3. Stream Large Datasets
For datasets larger than available RAM, process in chunks:
```python
import databento_dbn as dbn
from pathlib import Path

dbn_file = Path("data-cache/glbx-mdp3-market-data/v1.0.0/partitions/date=20260309/data.dbn.zst")

with open(dbn_file, "rb") as f:
    decoder = dbn.DBNDecoder(f)
    
    chunk_size = 100000
    for chunk_start in range(0, len(decoder), chunk_size):
        df_chunk = decoder.to_df().iloc[chunk_start:chunk_start+chunk_size]
        # Process chunk
```

## Troubleshooting

### Error: `AWS_ACCESS_KEY_ID not found`
**Solution**: Set environment variables before running:
```bash
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_REGION="us-east-2"
export S3_BUCKET_NAME="agentic-trading-snapshots-uchicago-spring-2026"
```

### Error: `No such file or directory: 'aws'`
**Solution**: AWS CLI not installed. Install with:
```bash
# macOS
brew install awscli

# Linux
pip install awscli

# Verify
aws --version
```

### Error: `DBNDecoder.__new__() got multiple values for argument 'has_metadata'`
**Solution**: Use file object, not path string:
```python
# ❌ Wrong
decoder = dbn.DBNDecoder("data.dbn.zst")

# ✅ Correct
with open("data.dbn.zst", "rb") as f:
    decoder = dbn.DBNDecoder(f)
```

### Error: `Could not parse line XXX in checksums file`
**Solution**: Checksums file format issue. Manually validate:
```bash
# Verify file integrity
sha256sum data-cache/glbx-mdp3-market-data/v1.0.0/partitions/date=20260309/data.dbn.zst
```

## Dependencies

Agents need these installed:
```bash
pip install databento-dbn pandas numpy
```

In Docker:
```dockerfile
RUN pip install databento-dbn pandas numpy
```

## Cost Tracking

Track your data retrieval costs:
```bash
# Cost per operation
- List datasets/versions: Free
- Fetch manifest: $0.0001 (per request)
- Fetch schema: $0.0001 (per request)
- Download 1 day (~330 MB): $0.01
- Download full dataset (8.99 GB): $0.32

# Cost optimization strategies
1. Cache downloaded data locally
2. Query manifest before downloading to plan dates
3. Download only dates you need for backtesting
4. Reuse downloads across multiple backtest runs
```

## Next Steps

1. **Set credentials**: Configure AWS credentials in `.env`
2. **Test retrieval**: Run `list-datasets` to verify access
3. **Download sample data**: Get one day with `sync-partition`
4. **Load and explore**: Use the code examples to analyze data
5. **Build strategy**: Use data for backtesting

## Support

For issues not covered here, see `TROUBLESHOOTING.md` in the docs directory.
