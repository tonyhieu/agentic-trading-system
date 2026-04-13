# Data Retrieval & Upload: Quick Start

This guide shows how to quickly set up and use the data retrieval system for autonomous agents.

## Prerequisites

- AWS bucket configured (see `docs/AWS_SETUP_GUIDE.md`)
- AWS CLI installed: `brew install awscli`
- Docker installed (optional, for containerized agents)
- Environment variables set:
  ```bash
  export S3_BUCKET_NAME="agentic-trading-snapshots-YOUR-SUFFIX"
  export AWS_REGION="us-east-1"
  ```

---

## Quick Start: Upload a Dataset

### 1. Prepare your dataset locally

```bash
mkdir -p my-dataset/partitions

# Create manifest.json
cat > my-dataset/manifest.json << 'EOF'
{
  "dataset_name": "glbx-mdp3-market-data",
  "dataset_version": "v1.0.0",
  "created_at": "2026-04-13T00:00:00Z",
  "format": "dbn",
  "compression": "zstd",
  "partition_scheme": ["date"],
  "partitions": [
    "partitions/date=2026-03-08/data.dbn.zst"
  ],
  "total_size_bytes": 8990765938,
  "record_count": 125000000,
  "date_range": {
    "start": "2026-03-08",
    "end": "2026-04-06"
  },
  "exchange": "GLBX"
}
EOF

# Add your DBN files
# my-dataset/partitions/date=2026-03-08/data.dbn.zst
```

### 2. Upload to S3

```bash
DATASET_NAME="glbx-mdp3-market-data"
DATASET_VERSION="v1.0.0"

aws s3 sync my-dataset \
  "s3://$S3_BUCKET_NAME/datasets/$DATASET_NAME/$DATASET_VERSION/" \
  --region "$AWS_REGION"

echo "✓ Dataset uploaded to S3"
```

---

## Quick Start: Retrieve a Dataset

### 1. List available datasets

```bash
python3 scripts/data_retriever.py list-datasets
```

### 2. Fetch manifest (always do this first!)

```bash
python3 scripts/data_retriever.py fetch-manifest glbx-mdp3-market-data v1.0.0
```

### 3. Download specific date partition

```bash
python3 scripts/data_retriever.py sync-partition \
  glbx-mdp3-market-data \
  v1.0.0 \
  "date=2026-03-08"
```

Data downloaded to: `./data-cache/glbx-mdp3-market-data/v1.0.0/partitions/date=2026-03-08/`

### 4. Load data in Python

```python
import subprocess

# Extract and read DBN file
dbn_file = "./data-cache/glbx-mdp3-market-data/v1.0.0/partitions/date=2026-03-08/data.dbn.zst"

# Decompress and read (using databento-dbn library)
import databento_dbn as dbn

# Read DBN file
records = dbn.load_from_file(dbn_file)

# Convert to pandas for analysis
df = records.to_df()
print(df.head())
```

---

## Docker Usage

### Build agent container

```bash
docker build -t agent .
```

### Run agent with data access

```bash
docker run --rm \
  -e AWS_REGION \
  -e S3_BUCKET_NAME \
  -e AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY \
  -v "$(pwd)/workspace:/workspace" \
  -v "$(pwd)/data-cache:/data-cache" \
  agent python /scripts/data_retriever.py list-datasets
```

### Using docker-compose

```bash
# List datasets
docker-compose run agent data_retriever.py list-datasets

# Fetch manifest
docker-compose run agent data_retriever.py fetch-manifest glbx-mdp3-market-data v1.0.0

# Interactive shell
docker-compose run agent bash
# Inside container:
# $ data_retriever.py sync-partition glbx-mdp3-market-data v1.0.0 "date=2026-03-08"
```

---

## File Organization

```
agentic-trading-system/
├── Dockerfile                           # Agent container image
├── docker-compose.yml                   # Multi-container setup
├── scripts/
│   └── data_retriever.py               # Retrieval client
├── docs/
│   ├── DATA_STORAGE_CONTRACT.md        # S3 layout spec
│   ├── DATA_OPERATIONS_PLAYBOOK.md     # CLI workflows
│   ├── DATA_RETRIEVAL_MVP_PLAN.md      # Project plan
│   ├── DATA_UPLOAD_AND_RETRIEVAL_GUIDE.md
│   └── examples/
│       ├── manifest-example.json
│       └── schema-example.json
├── workspace/                          # Strategy code (mounted in Docker)
├── data-cache/                         # Downloaded datasets (persistent)
└── strategies/                         # Strategy implementations
```

---

## Environment Variables

Required:
- `S3_BUCKET_NAME`: Your S3 bucket name
- `AWS_REGION`: AWS region (default: us-east-1)
- `AWS_ACCESS_KEY_ID`: AWS credentials
- `AWS_SECRET_ACCESS_KEY`: AWS credentials

Optional:
- `DATA_CACHE_DIR`: Local cache directory (default: ./data-cache)

---

## Troubleshooting

**"AWS CLI not found"**
```bash
brew install awscli
# or
pip install awscli
```

**"Access denied"**
- Verify S3_BUCKET_NAME is correct
- Check AWS credentials: `aws configure`
- Verify IAM policy allows S3 access

**"Slow downloads"**
- Use selective partitions (don't sync full dataset)
- Filter by date: `date=2026-04-01/symbol=AAPL`

**"Connection timeout"**
- Check internet connectivity
- Verify AWS_REGION is correct

---

## Next Steps

1. **Upload your first dataset**: Follow the upload steps above
2. **Test retrieval**: Use `data_retriever.py` to fetch and load data
3. **Run in Docker**: Build container and test isolated execution
4. **Integrate with strategies**: Modify your strategy to use `data_retriever.py`

See `docs/DATA_OPERATIONS_PLAYBOOK.md` for advanced workflows.
