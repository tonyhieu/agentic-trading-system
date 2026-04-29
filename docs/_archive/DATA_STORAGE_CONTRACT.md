# Data Storage Contract

This document defines the canonical S3 dataset layout and metadata schema for autonomous agent data retrieval.

## S3 Directory Structure

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
            ├── date=YYYYMMDD/
            │   └── data.dbn.zst
            └── ... (one per trading date)
```

## Naming Conventions

### Dataset Name
- **Format**: kebab-case, lowercase alphanumeric with hyphens
- **Examples**: `us-equities-bars-1m`, `market-microstructure-data`, `historical-options-chains`
- **Rule**: Must be unique within bucket; immutable once published

### Dataset Version
- **Format**: ISO 8601 timestamp OR semantic versioning
- **Timestamp**: `2026-04-11T00-00-00Z` (T and colons replaced with hyphens for S3 compatibility)
- **Semantic**: `v1.2.0`, `v2.0.1-beta`
- **Rule**: Each version is immutable; publish new version for updates

### Partition Keys
1. **Primary**: `date=YYYYMMDD` (required)
   - Always partition by date for temporal data
   - One date per directory level

### File Naming
- **Format**: `data.dbn.zst` (DBN binary format, zstd compressed)
- **Compression**: zstd (Zstandard compression, already applied)
- **Rule**: One file per trading date, contains all symbols/instruments for that date
- **Symbol filtering**: Performed at query time (agent loads DBN file, filters symbols in memory)

## Manifest Schema

Each dataset version **must** include `manifest.json` at the root:

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
    "partitions/date=20260309/data.dbn.zst",
    "partitions/date=20260310/data.dbn.zst"
  ],
  "total_size_bytes": 8990765938,
  "record_count": 125000000,
  "date_range": {
    "start": "2026-03-08",
    "end": "2026-04-06"
  },
  "exchange": "GLBX",
  "instruments": "Global FX futures",
  "schema_file": "schema.json",
  "checksums_file": "checksums.txt"
}
```

### Required Fields
- `dataset_name`: Kebab-case identifier
- `dataset_version`: Version tag
- `created_at`: ISO 8601 creation timestamp
- `format`: Data format (parquet)
- `compression`: Compression algorithm (snappy, zstd, gzip, none)
- `partition_scheme`: List of partition keys in order
- `partitions`: Array of relative paths to all partitions
- `total_size_bytes`: Cumulative size of all partitions

### Recommended Fields
- `updated_at`: Last modification timestamp
- `record_count`: Total records across all partitions
- `date_range`: Start and end dates for time-series data
- `symbols`: List of unique symbols if partitioned by symbol
- `schema_file`: Pointer to schema.json
- `checksums_file`: Pointer to checksums.txt

## Schema File

**Filename**: `schema.json`

Captures Parquet column names, types, and logical data layout:

```json
{
  "dataset_name": "us-equities-bars-1m",
  "dataset_version": "2026-04-11T00-00-00Z",
  "columns": [
    {
      "name": "timestamp",
      "type": "int64",
      "logical_type": "timestamp_ms",
      "nullable": false,
      "description": "Unix millisecond timestamp"
    },
    {
      "name": "symbol",
      "type": "utf8",
      "nullable": false,
      "description": "Ticker symbol (AAPL, MSFT, etc.)"
    },
    {
      "name": "open",
      "type": "double",
      "nullable": false,
      "description": "Opening price in USD"
    },
    {
      "name": "high",
      "type": "double",
      "nullable": false,
      "description": "High price in USD"
    },
    {
      "name": "low",
      "type": "double",
      "nullable": false,
      "description": "Low price in USD"
    },
    {
      "name": "close",
      "type": "double",
      "nullable": false,
      "description": "Closing price in USD"
    },
    {
      "name": "volume",
      "type": "int64",
      "nullable": false,
      "description": "Trading volume in shares"
    }
  ]
}
```

## Checksums File

**Filename**: `checksums.txt`

Line-delimited format for integrity verification:

```
SHA256:data.dbn.zst=a1b2c3d4e5f6...
SHA256:schema.json=1234567890abcdef...
SHA256:manifest.json=fedcba0987654321...
```

Format: `{ALGORITHM}:{filename}={hash}`

Agents can validate using:
```bash
sha256sum -c checksums.txt
```

## Compliance Checklist

When publishing a new dataset version:

- [ ] Dataset name is kebab-case
- [ ] Version tag follows ISO 8601 or semantic versioning
- [ ] `manifest.json` exists at version root with all required fields
- [ ] All partitions are listed in manifest
- [ ] Partition structure matches `partition_scheme`
- [ ] `schema.json` documents all columns with types and descriptions
- [ ] `checksums.txt` includes all files
- [ ] At least one partition exists (no empty datasets)
- [ ] Total size is accurate (verified via `du -sh` locally before upload)
- [ ] README or metadata notes any data quality issues or known limitations

## Version Lifecycle

1. **Draft**: Building locally, not in S3
2. **Published**: Uploaded to S3, manifest valid, checksums correct
3. **Stable**: Used by agents, no changes expected
4. **Deprecated** (optional): Mark in manifest as superseded; announce new version
5. **Archived** (optional): Move to cheap storage tier (Glacier) if not used

## Discovery Protocol for Agents

Agents follow this sequence:

1. **List datasets**: `aws s3 ls s3://$S3_BUCKET_NAME/datasets/`
2. **List versions**: `aws s3 ls s3://$S3_BUCKET_NAME/datasets/{dataset-name}/`
3. **Fetch manifest**: `aws s3 cp s3://.../manifest.json -` → parse JSON
4. **Inspect schema**: `aws s3 cp s3://.../schema.json -` → understand columns
5. **Validate checksums**: Compare local files against `checksums.txt`
6. **Retrieve partitions**: Sync only required partition prefixes

## Backward Compatibility

If dataset structure changes:
- Publish as new version (e.g., `v1.2.0` → `v1.3.0`)
- Do NOT modify existing version
- Update manifest with new partition layout if needed
- Document breaking changes in README

## Examples

### Example 1: Market Data (Date-Only Partitioning)
```
datasets/glbx-mdp3-market-data/v1.0.0/
├── manifest.json
├── schema.json
├── checksums.txt
└── partitions/
    ├── date=20260308/data.dbn.zst
    ├── date=20260309/data.dbn.zst
    └── date=20260310/data.dbn.zst
```

### Example 2: Trade Execution Logs (Date-Only DBN)
```
datasets/trade-execution-logs/v1.0.0/
├── manifest.json
├── schema.json
└── partitions/
    ├── date=20260401/data.dbn.zst
    ├── date=20260402/data.dbn.zst
    └── date=20260403/data.dbn.zst
```

### Example 3: Multi-Year Archive
```
datasets/historical-market-data/v1.0.0/
├── manifest.json
├── schema.json
└── partitions/
    ├── date=20240101/data.dbn.zst
    ├── date=20240102/data.dbn.zst
    └── ... (one per trading date)
```
