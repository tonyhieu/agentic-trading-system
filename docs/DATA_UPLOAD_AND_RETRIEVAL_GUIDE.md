# AWS Data Upload and Autonomous Retrieval Guide

This guide defines a minimum viable, agent-friendly workflow for uploading and retrieving large research datasets (up to and beyond 40 GB) using the existing AWS/S3 setup in this repository.

## Goals

- Make dataset retrieval easy for autonomous agents.
- Avoid full 40 GB downloads by default.
- Keep data organization deterministic and reproducible.
- Reuse existing AWS credential and bucket setup patterns.

## Assumptions

- AWS credentials are available through environment variables or `aws configure`.
- The existing S3 bucket and IAM setup from `docs/AWS_SETUP_GUIDE.md` is in place.
- Variables used below:

```bash
export AWS_REGION="us-east-1"
export S3_BUCKET_NAME="your-bucket-name"
```

## Canonical S3 Dataset Layout

Use this fixed layout:

```text
s3://$S3_BUCKET_NAME/datasets/
└── {dataset-name}/
    └── {dataset-version}/
        ├── manifest.json
        ├── schema.json
        ├── checksums.txt
        └── partitions/
            ├── date=2026-04-01/symbol=AAPL/part-000.parquet
            ├── date=2026-04-01/symbol=MSFT/part-000.parquet
            └── ...
```

### Naming Conventions

- `dataset-name`: kebab-case (example: `us-equities-bars-1m`)
- `dataset-version`: timestamp or semantic version (examples: `2026-04-11T00-00-00Z`, `v1.2.0`)

## Manifest Contract

Each dataset version must include `manifest.json` with at least:

```json
{
  "dataset_name": "us-equities-bars-1m",
  "dataset_version": "2026-04-11T00-00-00Z",
  "created_at": "2026-04-11T00:00:00Z",
  "format": "parquet",
  "compression": "snappy",
  "partition_scheme": ["date", "symbol"],
  "partitions": [
    "partitions/date=2026-04-01/symbol=AAPL/part-000.parquet"
  ],
  "total_size_bytes": 42949672960
}
```

`schema.json` and `checksums.txt` are strongly recommended.

## Upload Workflow

1. Build the local dataset folder with `manifest.json` and partitioned files.
2. Upload the version directory.
3. Validate by reading the manifest from S3.

```bash
# Example local structure:
# ./dataset-root/
#   manifest.json
#   schema.json
#   checksums.txt
#   partitions/...

DATASET_NAME="us-equities-bars-1m"
DATASET_VERSION="2026-04-11T00-00-00Z"

aws s3 sync ./dataset-root \
  "s3://$S3_BUCKET_NAME/datasets/$DATASET_NAME/$DATASET_VERSION/" \
  --region "$AWS_REGION" \
  --no-progress

aws s3 cp \
  "s3://$S3_BUCKET_NAME/datasets/$DATASET_NAME/$DATASET_VERSION/manifest.json" \
  - \
  --region "$AWS_REGION"
```

## Autonomous Retrieval Workflow (MVP)

Agents should use this sequence:

1. List datasets.
2. List versions for target dataset.
3. Pull `manifest.json` first.
4. Pull only required partitions.
5. Reuse local cache between runs.

```bash
# 1) Discover datasets
aws s3 ls "s3://$S3_BUCKET_NAME/datasets/" --region "$AWS_REGION"

# 2) Discover versions
aws s3 ls "s3://$S3_BUCKET_NAME/datasets/$DATASET_NAME/" --region "$AWS_REGION"

# 3) Pull metadata first
mkdir -p ./data-cache/$DATASET_NAME/$DATASET_VERSION
aws s3 cp \
  "s3://$S3_BUCKET_NAME/datasets/$DATASET_NAME/$DATASET_VERSION/manifest.json" \
  "./data-cache/$DATASET_NAME/$DATASET_VERSION/manifest.json" \
  --region "$AWS_REGION"
```

### Selective Sync Patterns

Retrieve only required partitions (example: one date range and one symbol):

```bash
aws s3 sync \
  "s3://$S3_BUCKET_NAME/datasets/$DATASET_NAME/$DATASET_VERSION/partitions/date=2026-04-01/symbol=AAPL/" \
  "./data-cache/$DATASET_NAME/$DATASET_VERSION/partitions/date=2026-04-01/symbol=AAPL/" \
  --region "$AWS_REGION" \
  --no-progress
```

Repeat for additional partition prefixes. Avoid syncing the full version root unless explicitly needed.

## Docker Recommendation for Agents

Use Docker by default for reproducibility and dependency isolation.

Suggested mounts:

- `./workspace` -> strategy code/results
- `./data-cache` -> retrieved dataset partitions (persistent cache)

Example:

```bash
docker run --rm \
  -e AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY \
  -e AWS_REGION \
  -e S3_BUCKET_NAME \
  -v "$(pwd)/workspace:/workspace" \
  -v "$(pwd)/data-cache:/data-cache" \
  python:3.11-slim \
  bash -lc "pip install pandas pyarrow && python /workspace/run_strategy.py"
```

Host CLI remains a valid fallback when Docker is not required.

## 40 GB Storage Strategy

For 40 GB datasets, use:

- Partitioned storage by high-selectivity keys (date, then symbol if useful).
- Compressed Parquet (snappy or zstd).
- Manifest-first discovery to prevent large listings and unnecessary transfer.
- Incremental retrieval: fetch only changed/new partitions per iteration.

Do not store the dataset as a single large file.

## Operational Policy (MVP Defaults)

- Default retrieval mode: metadata-first + selective partition sync.
- Keep local cache across agent runs.
- Treat dataset versions as immutable once published.
- Publish a new dataset version instead of in-place mutation.

## Troubleshooting

- **Access denied:** verify IAM policy and credentials.
- **No such bucket/prefix:** verify `S3_BUCKET_NAME`, region, and path.
- **Slow pulls:** sync narrower prefixes; avoid root-level sync.
- **Inconsistent data:** verify version and checksums against manifest.

See also `docs/TROUBLESHOOTING.md` and `docs/AWS_SETUP_GUIDE.md`.
