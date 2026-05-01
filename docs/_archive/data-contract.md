# Data Storage Contract

Canonical S3 dataset layout and metadata schema for autonomous agent data
retrieval. Operational use (CLI commands, costs, loading) is in
`docs/skills/data-retrieval.md` — this file is the reference for *what files
exist and what they look like*.

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

### Dataset name
- **Format**: kebab-case, lowercase alphanumeric with hyphens
- **Examples**: `glbx-mdp3-market-data`, `historical-options-chains`
- **Rule**: Unique within bucket; immutable once published

### Dataset version
- **Format**: semantic versioning (`v1.0.0`, `v2.0.1-beta`) or ISO 8601
  timestamp with hyphens (`2026-04-11T00-00-00Z` — colons replaced for S3
  compatibility)
- **Rule**: Each version is immutable; publish a new version for updates

### Partition keys
- **Primary**: `date=YYYYMMDD` (required) — no hyphens in the date
- One date per directory level

### File naming
- **Format**: `data.dbn.zst` (Databento Binary, zstd compressed) for the
  current GLBX dataset
- **Alternative**: `part-000.parquet` for parquet datasets — see Examples §3
- **Rule**: One file per trading date, contains all symbols for that date.
  Symbol filtering happens at load time in memory.

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

### Required fields

- `dataset_name` — kebab-case identifier
- `dataset_version` — semver or ISO 8601 timestamp
- `created_at` — ISO 8601 creation timestamp
- `format` — data format (`dbn` for the production GLBX dataset; `parquet`
  for the alternative layout)
- `compression` — compression algorithm (`zstd`, `snappy`, `gzip`, `none`)
- `partition_scheme` — list of partition keys in order (e.g., `["date"]`)
- `partitions` — array of relative paths to all partitions
- `total_size_bytes` — cumulative size of all partitions

### Recommended fields

- `updated_at` — last modification timestamp
- `record_count` — total records across all partitions
- `date_range` — start/end dates for time-series data
- `symbols` — list of unique symbols if partitioned by symbol
- `schema_file`, `checksums_file` — pointers

## Schema File

**Filename**: `schema.json`

Captures record types and fields. For the production GLBX dataset, schema
documents the DBN record types:

```json
{
  "dataset_name": "glbx-mdp3-market-data",
  "dataset_version": "v1.0.0",
  "record_types": {
    "MBP1Msg": {
      "description": "Market by Price, top of book",
      "fields": [
        { "name": "ts_event",  "type": "uint64", "description": "Exchange timestamp (ns)" },
        { "name": "ts_recv",   "type": "uint64", "description": "Receiver timestamp (ns)" },
        { "name": "bid_px",    "type": "int64",  "description": "Best bid price (1e-9 USD)" },
        { "name": "ask_px",    "type": "int64",  "description": "Best ask price (1e-9 USD)" },
        { "name": "bid_sz",    "type": "uint32", "description": "Best bid size" },
        { "name": "ask_sz",    "type": "uint32", "description": "Best ask size" },
        { "name": "symbol",    "type": "utf8" }
      ]
    },
    "TradeMsg": {
      "description": "Individual trade",
      "fields": [
        { "name": "ts_event", "type": "uint64" },
        { "name": "ts_recv",  "type": "uint64" },
        { "name": "price",    "type": "int64",  "description": "Trade price (1e-9 USD)" },
        { "name": "size",     "type": "uint32" },
        { "name": "side",     "type": "uint8",  "description": "1=Buy, 2=Sell" },
        { "name": "action",   "type": "uint8" },
        { "name": "depth",    "type": "uint8" },
        { "name": "symbol",   "type": "utf8" }
      ]
    },
    "OHLCVMsg": {
      "description": "Candle aggregation",
      "fields": [
        { "name": "ts_event", "type": "uint64" },
        { "name": "open",     "type": "int64" },
        { "name": "high",     "type": "int64" },
        { "name": "low",      "type": "int64" },
        { "name": "close",    "type": "int64" },
        { "name": "volume",   "type": "uint64" }
      ]
    }
  }
}
```

For parquet alternatives, schema lists columns with types — see
`docs/examples/schema-example.json` (template).

## Checksums File

**Filename**: `checksums.txt`

Line-delimited format for integrity verification:

```
SHA256:data.dbn.zst=a1b2c3d4e5f6...
SHA256:schema.json=1234567890abcdef...
SHA256:manifest.json=fedcba0987654321...
```

Format: `{ALGORITHM}:{filename}={hash}`

The `data_retriever.py validate` command compares local files against this.

## Compliance Checklist

When publishing a new dataset version:

- [ ] Dataset name is kebab-case
- [ ] Version tag follows semver or ISO 8601
- [ ] `manifest.json` exists at version root with all required fields
- [ ] All partitions are listed in manifest
- [ ] Partition structure matches `partition_scheme`
- [ ] `schema.json` documents record types or columns
- [ ] `checksums.txt` includes all files
- [ ] At least one partition exists (no empty datasets)
- [ ] Total size is accurate (verified via `du -sh` locally before upload)

## Discovery Protocol for Agents

Agents follow this sequence (operational details in
`docs/skills/data-retrieval.md`):

1. List datasets → `list-datasets`
2. List versions → `list-versions <dataset>`
3. Fetch manifest → `fetch-manifest <dataset> <version>`
4. Inspect schema → `fetch-schema <dataset> <version>`
5. Validate checksums → `validate <dataset> <version>` (after download)
6. Retrieve partitions → `sync-partition <dataset> <version> <partition>`

## Backward Compatibility

If dataset structure changes, publish as a new version (e.g., `v1.0.0` →
`v1.1.0`). Do not modify an existing version. Document breaking changes in
the manifest's `notes` field or a `CHANGELOG.md` at the version root.

## Examples

### Example 1: GLBX market data (DBN, date-only) — production layout

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

### Example 2: Multi-year DBN archive

```
datasets/historical-market-data/v1.0.0/
└── partitions/
    ├── date=20240101/data.dbn.zst
    ├── date=20240102/data.dbn.zst
    └── ... (one per trading date)
```

### Example 3: Parquet with date+symbol partitioning — *template only*

This layout is supported but not currently in production. See
`docs/examples/manifest-example.json` for a full template. Cost model differs
from the DBN layout (many small partitions vs one per date).

```
datasets/us-equities-bars-1m/v1.0.0/
└── partitions/
    ├── date=20260401/symbol=AAPL/part-000.parquet
    ├── date=20260401/symbol=MSFT/part-000.parquet
    └── ...
```
