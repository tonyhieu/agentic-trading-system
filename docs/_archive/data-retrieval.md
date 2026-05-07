# Skill: Data Retrieval

Single canonical source for downloading market data partitions and the
underlying data contract that defines them.

The first half is **operational** (run these commands to load data). The
second half is **reference** (this is what files look like, and the rules
publishers follow when adding new datasets).

---

## Operational

### 1. Setup

```bash
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_REGION="us-east-2"
export S3_BUCKET_NAME="agentic-trading-snapshots-uchicago-spring-2026"
```

The Docker image (see `docs/operator/architecture.md`) has the AWS CLI and
`databento-dbn` pre-installed. Outside Docker, install with:

```bash
brew install awscli   # macOS
pip install databento-dbn pandas
```

### 2. Discover what's available

```bash
# All datasets
python scripts/data_retriever.py list-datasets

# Versions of a dataset
python scripts/data_retriever.py list-versions glbx-mdp3-market-data

# Manifest (date range, partition list, total size, checksums)
python scripts/data_retriever.py fetch-manifest glbx-mdp3-market-data v1.0.0

# Schema (record types and fields)
python scripts/data_retriever.py fetch-schema glbx-mdp3-market-data v1.0.0
```

The manifest's `partitions` array is authoritative — always read it before
constructing a partition path.

### 3. Download a partition

**Partition path format**: `date=YYYYMMDD` (no hyphens).

```bash
# Single day (~330 MB, ~$0.01)
python scripts/data_retriever.py sync-partition \
  glbx-mdp3-market-data v1.0.0 "date=20260308"
```

Cached at:
```
data-cache/glbx-mdp3-market-data/v1.0.0/partitions/date=20260308/data.dbn.zst
```

The cache persists across runs — the same date is free to re-load.

**Cost budget**: see `research/config.yaml → data_window.max_days_per_iteration`
(default 10).

### 4. Load DBN data in Python

```python
import databento_dbn as dbn
from pathlib import Path

dbn_file = Path("data-cache/glbx-mdp3-market-data/v1.0.0/partitions/date=20260308/data.dbn.zst")

# IMPORTANT: pass a file object, not a path string.
with open(dbn_file, "rb") as f:
    df = dbn.DBNDecoder(f).to_df()
```

Field reference is in §"Schema file (record types)" below. Filter by record
type with `df[df['rtype'] == 'MBP1Msg']` etc.

### 5. Verify integrity

```bash
python scripts/data_retriever.py validate glbx-mdp3-market-data v1.0.0
```

Compares local files against `checksums.txt` (SHA256). Run this before
trusting a backtest if you suspect a corrupted download.

### 6. Cost reference

| Scope | Size | Cost |
|---|---|---|
| One date partition | ~330 MB | ~$0.01 |
| 10-day backtest | ~3.3 GB | ~$0.13 |
| Full GLBX dataset (26 days) | 8.99 GB | ~$0.32 |
| Manifest / schema fetch | trivial | ~$0.0001 |

Cached partitions are free to reuse across iterations.

### 7. Common errors

| Symptom | Cause | Fix |
|---|---|---|
| `S3_BUCKET_NAME not set` | env var missing | Export the four AWS env vars (§1) |
| `command not found: aws` | AWS CLI not installed | Run inside Docker, or install locally |
| `Partition not found` | wrong date format or out-of-range date | Check the `partitions` array in the manifest; format is `date=YYYYMMDD` |
| `DBNDecoder.__new__() got multiple values for argument 'has_metadata'` | passed a path string instead of a file object | `with open(path, "rb") as f: dbn.DBNDecoder(f)` |
| `Could not parse line ... in checksums file` | malformed checksums.txt | Re-run `validate`, or fall back to manual `sha256sum -c` |

---

## Reference: Data Contract

### S3 directory structure

```
s3://$S3_BUCKET_NAME/datasets/
└── {dataset-name}/
    └── {dataset-version}/
        ├── manifest.json          (Required)
        ├── schema.json            (Recommended)
        ├── checksums.txt          (Recommended)
        └── partitions/
            ├── date=YYYYMMDD/
            │   └── data.dbn.zst
            └── ...
```

### Naming conventions

- **Dataset name**: kebab-case, lowercase alphanumeric with hyphens
  (e.g., `glbx-mdp3-market-data`). Unique within bucket; immutable once published.
- **Dataset version**: semver (`v1.0.0`) or ISO 8601 timestamp with hyphens
  (`2026-04-11T00-00-00Z` — colons replaced for S3 compatibility). Each
  version is immutable; publish a new version for updates.
- **Partition key**: `date=YYYYMMDD` (no hyphens). One date per directory level.
- **File**: `data.dbn.zst` (Databento Binary, zstd compressed) for the
  current GLBX dataset. One file per trading date contains all symbols;
  filter by symbol at load time in memory.

### Manifest schema

Every dataset version MUST include `manifest.json` at the version root:

```json
{
  "dataset_name": "glbx-mdp3-market-data",
  "dataset_version": "v1.0.0",
  "created_at": "2026-04-13T00:00:00Z",
  "updated_at": "2026-04-13T00:00:00Z",
  "format": "dbn",
  "compression": "zstd",
  "partition_scheme": ["date"],
  "partitions": [
    "partitions/date=20260308/data.dbn.zst",
    "partitions/date=20260309/data.dbn.zst"
  ],
  "total_size_bytes": 8990765938,
  "record_count": 125000000,
  "date_range": { "start": "2026-03-08", "end": "2026-04-06" },
  "exchange": "GLBX",
  "instruments": "Global FX futures",
  "schema_file": "schema.json",
  "checksums_file": "checksums.txt"
}
```

**Required**: `dataset_name`, `dataset_version`, `created_at`, `format`,
`compression`, `partition_scheme`, `partitions`, `total_size_bytes`.

**Recommended**: `updated_at`, `record_count`, `date_range`, `symbols` (if
partitioned by symbol), `schema_file`, `checksums_file`.

### Schema file (record types)

`schema.json` documents record types and fields. For the production GLBX
dataset:

| Record type | Key fields |
|---|---|
| `MBP1Msg` (top of book) | `ts_event`, `ts_recv`, `bid_px`, `ask_px`, `bid_sz`, `ask_sz`, `symbol` |
| `TradeMsg` (individual trade) | `ts_event`, `ts_recv`, `price`, `size`, `side` (1=Buy, 2=Sell), `action`, `depth`, `symbol` |
| `OHLCVMsg` (candle) | `ts_event`, `open`, `high`, `low`, `close`, `volume` |

Prices are `int64` in 1e-9 USD (divide by 1e9 for dollars). Timestamps are
nanoseconds. The full type-and-description JSON comes back from
`fetch-schema` (§2).

### Checksums file

`checksums.txt` is line-delimited:

```
SHA256:data.dbn.zst=a1b2c3d4...
SHA256:schema.json=12345678...
SHA256:manifest.json=fedcba09...
```

Format: `{ALGORITHM}:{filename}={hash}`. The `validate` command (§5) uses this.

### Compliance checklist for publishing a new dataset

- [ ] Dataset name is kebab-case
- [ ] Version tag follows semver or ISO 8601
- [ ] `manifest.json` exists at version root with all required fields
- [ ] All partitions are listed in the manifest
- [ ] Partition structure matches `partition_scheme`
- [ ] `schema.json` documents record types or columns
- [ ] `checksums.txt` includes all files
- [ ] At least one partition exists
- [ ] Total size verified via `du -sh` before upload

### Backward compatibility

If dataset structure changes, publish a new version (e.g., `v1.0.0` →
`v1.1.0`). Do not modify an existing version. Document breaking changes in
the manifest's `notes` field.
