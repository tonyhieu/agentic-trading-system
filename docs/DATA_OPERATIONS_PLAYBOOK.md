# Data Operations Playbook

Complete step-by-step CLI workflows for uploading, discovering, and retrieving large datasets from AWS S3. All commands assume AWS credentials are configured and S3 bucket exists per `docs/AWS_SETUP_GUIDE.md`.

## Environment Setup

```bash
# Required environment variables
export AWS_REGION="us-east-1"
export S3_BUCKET_NAME="agentic-trading-snapshots-YOUR-SUFFIX"

# Verify connectivity
aws s3 ls s3://$S3_BUCKET_NAME/ --region "$AWS_REGION"
```

---

## Workflow 1: Upload a New Dataset Version

Use this workflow to publish a dataset to S3 following the storage contract.

### Prerequisites

- Local directory with manifest, schema, checksums, and partitions
- Example structure:
  ```
  ./my-dataset/
  ├── manifest.json
  ├── schema.json
  ├── checksums.txt
  └── partitions/
      ├── date=2026-04-01/symbol=AAPL/part-000.parquet
      ├── date=2026-04-01/symbol=MSFT/part-000.parquet
      └── ...
  ```

### Upload Steps

```bash
# 1. Define dataset variables
DATASET_NAME="us-equities-bars-1m"
DATASET_VERSION="2026-04-11T00-00-00Z"
LOCAL_DATASET_ROOT="./my-dataset"

# 2. Validate manifest locally
python3 << 'PYTHON'
import json
with open(f"{LOCAL_DATASET_ROOT}/manifest.json") as f:
    manifest = json.load(f)
    assert manifest["dataset_name"] == "${DATASET_NAME}"
    assert manifest["dataset_version"] == "${DATASET_VERSION}"
    assert manifest["format"] == "parquet"
    print("✓ Manifest valid")
PYTHON

# 3. Sync entire version directory to S3
aws s3 sync "$LOCAL_DATASET_ROOT" \
  "s3://$S3_BUCKET_NAME/datasets/$DATASET_NAME/$DATASET_VERSION/" \
  --region "$AWS_REGION" \
  --no-progress

echo "✓ Upload complete: datasets/$DATASET_NAME/$DATASET_VERSION/"

# 4. Verify manifest is readable from S3
aws s3 cp \
  "s3://$S3_BUCKET_NAME/datasets/$DATASET_NAME/$DATASET_VERSION/manifest.json" \
  - \
  --region "$AWS_REGION" | jq .

# 5. Validate checksums in S3
aws s3 cp \
  "s3://$S3_BUCKET_NAME/datasets/$DATASET_NAME/$DATASET_VERSION/checksums.txt" \
  ./checksums-remote.txt \
  --region "$AWS_REGION"
  
sha256sum -c ./checksums-remote.txt
echo "✓ Checksums verified"
```

---

## Workflow 2: Discover Datasets and Versions

Agents use this to find available datasets and select which version to retrieve.

### List All Datasets

```bash
# Show all datasets in bucket
aws s3 ls "s3://$S3_BUCKET_NAME/datasets/" --region "$AWS_REGION"

# Output:
# PRE us-equities-bars-1m/
# PRE trade-execution-logs/
# PRE historical-options/
```

### List All Versions of a Dataset

```bash
DATASET_NAME="us-equities-bars-1m"

# Show all versions
aws s3 ls "s3://$S3_BUCKET_NAME/datasets/$DATASET_NAME/" \
  --region "$AWS_REGION" \
  | awk '{print $2}'

# Output:
# 2026-04-10T00-00-00Z/
# 2026-04-11T00-00-00Z/
# v1.0.0/
```

### Programmatic Discovery (Python)

```python
import subprocess
import json

def list_datasets(bucket_name, region):
    """List all datasets."""
    cmd = f"aws s3 ls s3://{bucket_name}/datasets/ --region {region}"
    output = subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout
    return [line.split()[-1].rstrip('/') for line in output.strip().split('\n') if line]

def list_versions(bucket_name, dataset_name, region):
    """List all versions for a dataset."""
    cmd = f"aws s3 ls s3://{bucket_name}/datasets/{dataset_name}/ --region {region}"
    output = subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout
    return [line.split()[-1].rstrip('/') for line in output.strip().split('\n') if line]

datasets = list_datasets("my-bucket", "us-east-1")
print(f"Available datasets: {datasets}")

versions = list_versions("my-bucket", "us-equities-bars-1m", "us-east-1")
print(f"Available versions: {versions}")
```

---

## Workflow 3: Fetch Metadata First

Always read manifest and schema before retrieving partitions.

```bash
DATASET_NAME="us-equities-bars-1m"
DATASET_VERSION="2026-04-11T00-00-00Z"
CACHE_DIR="./data-cache"

# 1. Create cache directory
mkdir -p "$CACHE_DIR/$DATASET_NAME/$DATASET_VERSION"

# 2. Download manifest
aws s3 cp \
  "s3://$S3_BUCKET_NAME/datasets/$DATASET_NAME/$DATASET_VERSION/manifest.json" \
  "$CACHE_DIR/$DATASET_NAME/$DATASET_VERSION/manifest.json" \
  --region "$AWS_REGION"

# 3. Parse manifest to understand structure
python3 << 'PYTHON'
import json
import os

manifest_path = f"{os.environ['CACHE_DIR']}/{os.environ['DATASET_NAME']}/{os.environ['DATASET_VERSION']}/manifest.json"
with open(manifest_path) as f:
    manifest = json.load(f)

print(f"Dataset: {manifest['dataset_name']}")
print(f"Version: {manifest['dataset_version']}")
print(f"Format: {manifest['format']}")
print(f"Compression: {manifest['compression']}")
print(f"Partitions: {manifest['partition_scheme']}")
print(f"Total Size: {manifest['total_size_bytes'] / (1024**3):.2f} GB")
print(f"Date Range: {manifest['date_range']['start']} to {manifest['date_range']['end']}")
print(f"Symbols: {', '.join(manifest['symbols'])}")
print(f"Record Count: {manifest['record_count']:,}")
PYTHON

# 4. Download schema
aws s3 cp \
  "s3://$S3_BUCKET_NAME/datasets/$DATASET_NAME/$DATASET_VERSION/schema.json" \
  "$CACHE_DIR/$DATASET_NAME/$DATASET_VERSION/schema.json" \
  --region "$AWS_REGION"

# 5. View schema
cat "$CACHE_DIR/$DATASET_NAME/$DATASET_VERSION/schema.json" | jq .
```

---

## Workflow 4: Selective Partition Retrieval

Download only the partitions you need. This is the core optimization for 40+ GB datasets.

### Single Partition (One Date, One Symbol)

```bash
DATASET_NAME="us-equities-bars-1m"
DATASET_VERSION="2026-04-11T00-00-00Z"
DATE="2026-04-01"
SYMBOL="AAPL"

aws s3 sync \
  "s3://$S3_BUCKET_NAME/datasets/$DATASET_NAME/$DATASET_VERSION/partitions/date=$DATE/symbol=$SYMBOL/" \
  "./data-cache/$DATASET_NAME/$DATASET_VERSION/partitions/date=$DATE/symbol=$SYMBOL/" \
  --region "$AWS_REGION" \
  --no-progress

echo "✓ Downloaded: date=$DATE, symbol=$SYMBOL"
```

### Multiple Partitions (Date Range, Single Symbol)

```bash
DATASET_NAME="us-equities-bars-1m"
DATASET_VERSION="2026-04-11T00-00-00Z"
SYMBOL="AAPL"

# Download for April 1-5, 2026
for DATE in 2026-04-0{1..5}; do
  aws s3 sync \
    "s3://$S3_BUCKET_NAME/datasets/$DATASET_NAME/$DATASET_VERSION/partitions/date=$DATE/symbol=$SYMBOL/" \
    "./data-cache/$DATASET_NAME/$DATASET_VERSION/partitions/date=$DATE/symbol=$SYMBOL/" \
    --region "$AWS_REGION" \
    --no-progress
    
  echo "✓ Downloaded: date=$DATE"
done
```

### Multiple Symbols (Single Date)

```bash
DATASET_NAME="us-equities-bars-1m"
DATASET_VERSION="2026-04-11T00-00-00Z"
DATE="2026-04-01"

for SYMBOL in AAPL MSFT GOOGL; do
  aws s3 sync \
    "s3://$S3_BUCKET_NAME/datasets/$DATASET_NAME/$DATASET_VERSION/partitions/date=$DATE/symbol=$SYMBOL/" \
    "./data-cache/$DATASET_NAME/$DATASET_VERSION/partitions/date=$DATE/symbol=$SYMBOL/" \
    --region "$AWS_REGION" \
    --no-progress
    
  echo "✓ Downloaded: symbol=$SYMBOL"
done
```

### Full Dataset (Use with caution on 40+ GB datasets)

```bash
DATASET_NAME="us-equities-bars-1m"
DATASET_VERSION="2026-04-11T00-00-00Z"

# WARNING: This may download 40+ GB
aws s3 sync \
  "s3://$S3_BUCKET_NAME/datasets/$DATASET_NAME/$DATASET_VERSION/partitions/" \
  "./data-cache/$DATASET_NAME/$DATASET_VERSION/partitions/" \
  --region "$AWS_REGION" \
  --no-progress

echo "✓ Full dataset downloaded"
```

---

## Workflow 5: Resume Interrupted Sync

If a download is interrupted, AWS S3 sync is safe to rerun.

```bash
DATASET_NAME="us-equities-bars-1m"
DATASET_VERSION="2026-04-11T00-00-00Z"

# Rerun sync — AWS will skip files already downloaded
aws s3 sync \
  "s3://$S3_BUCKET_NAME/datasets/$DATASET_NAME/$DATASET_VERSION/partitions/" \
  "./data-cache/$DATASET_NAME/$DATASET_VERSION/partitions/" \
  --region "$AWS_REGION" \
  --no-progress

echo "✓ Sync resumed; only new files downloaded"
```

---

## Workflow 6: Validate Data Integrity

Use checksums to verify downloaded data hasn't been corrupted.

```bash
DATASET_NAME="us-equities-bars-1m"
DATASET_VERSION="2026-04-11T00-00-00Z"
CACHE_DIR="./data-cache"

# 1. Download checksums file
aws s3 cp \
  "s3://$S3_BUCKET_NAME/datasets/$DATASET_NAME/$DATASET_VERSION/checksums.txt" \
  "$CACHE_DIR/$DATASET_NAME/$DATASET_VERSION/checksums.txt" \
  --region "$AWS_REGION"

# 2. Change to cache directory
cd "$CACHE_DIR/$DATASET_NAME/$DATASET_VERSION"

# 3. Extract filenames and verify
python3 << 'PYTHON'
import subprocess
import hashlib

checksums_file = "checksums.txt"
with open(checksums_file) as f:
    lines = [l.strip() for l in f if l.strip()]

passed = 0
failed = 0

for line in lines:
    algo, rest = line.split(":", 1)
    filename, expected_hash = rest.split("=", 1)
    
    try:
        with open(filename, 'rb') as f:
            actual_hash = hashlib.sha256(f.read()).hexdigest()
        
        if actual_hash == expected_hash:
            print(f"✓ {filename}")
            passed += 1
        else:
            print(f"✗ {filename} (hash mismatch)")
            failed += 1
    except FileNotFoundError:
        print(f"✗ {filename} (file not found)")
        failed += 1

print(f"\nPassed: {passed}, Failed: {failed}")
if failed == 0:
    print("✓ All files verified")
else:
    print("✗ Verification failed; redownload affected files")
PYTHON
```

---

## Docker Workflow: Isolated Agent Execution

Run data retrieval and strategy execution inside Docker for reproducibility.

### Setup

```bash
# Create workspace and cache directories
mkdir -p ./workspace
mkdir -p ./data-cache

# Copy strategy code to workspace
cp my_strategy.py ./workspace/
cp requirements.txt ./workspace/
```

### Run Retrieval Inside Docker

```bash
docker run --rm \
  -e AWS_REGION \
  -e S3_BUCKET_NAME \
  -e AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY \
  -v "$(pwd)/workspace:/workspace" \
  -v "$(pwd)/data-cache:/data-cache" \
  amazon/aws-cli:latest \
  s3 ls s3://$S3_BUCKET_NAME/datasets/
```

### Run Python Strategy with Data

```bash
docker run --rm \
  -e AWS_REGION \
  -e S3_BUCKET_NAME \
  -e AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY \
  -v "$(pwd)/workspace:/workspace" \
  -v "$(pwd)/data-cache:/data-cache" \
  python:3.11-slim \
  bash -c "
    cd /workspace && \
    pip install -r requirements.txt && \
    python my_strategy.py
  "
```

### Docker Compose Example

Create `docker-compose.yml`:

```yaml
version: '3'
services:
  agent:
    image: python:3.11-slim
    working_dir: /workspace
    environment:
      AWS_REGION: us-east-1
      S3_BUCKET_NAME: ${S3_BUCKET_NAME}
      AWS_ACCESS_KEY_ID: ${AWS_ACCESS_KEY_ID}
      AWS_SECRET_ACCESS_KEY: ${AWS_SECRET_ACCESS_KEY}
    volumes:
      - ./workspace:/workspace
      - ./data-cache:/data-cache
    command: >
      bash -c "
        pip install -r requirements.txt &&
        python my_strategy.py
      "
```

Run with:

```bash
export S3_BUCKET_NAME=my-bucket
export AWS_ACCESS_KEY_ID=$(aws configure get aws_access_key_id)
export AWS_SECRET_ACCESS_KEY=$(aws configure get aws_secret_access_key)

docker-compose run --rm agent
```

---

## Workflow 7: Python Retrieval Script

For more complex retrieval logic, use a Python wrapper.

```python
#!/usr/bin/env python3
import subprocess
import json
import os
import sys

class DataRetriever:
    def __init__(self, bucket_name, region):
        self.bucket_name = bucket_name
        self.region = region
    
    def _run_aws(self, cmd):
        """Execute AWS CLI command."""
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error: {result.stderr}", file=sys.stderr)
            sys.exit(1)
        return result.stdout.strip()
    
    def list_datasets(self):
        """List all datasets."""
        cmd = f"aws s3 ls s3://{self.bucket_name}/datasets/ --region {self.region}"
        output = self._run_aws(cmd)
        return [line.split()[-1].rstrip('/') for line in output.split('\n') if line]
    
    def list_versions(self, dataset_name):
        """List versions for dataset."""
        cmd = f"aws s3 ls s3://{self.bucket_name}/datasets/{dataset_name}/ --region {self.region}"
        output = self._run_aws(cmd)
        return [line.split()[-1].rstrip('/') for line in output.split('\n') if line]
    
    def fetch_manifest(self, dataset_name, version, local_path):
        """Download manifest.json."""
        s3_path = f"s3://{self.bucket_name}/datasets/{dataset_name}/{version}/manifest.json"
        cmd = f"aws s3 cp {s3_path} {local_path} --region {self.region}"
        self._run_aws(cmd)
        
        with open(local_path) as f:
            return json.load(f)
    
    def sync_partition(self, dataset_name, version, partition_path, local_dir):
        """Sync a single partition."""
        s3_path = f"s3://{self.bucket_name}/datasets/{dataset_name}/{version}/partitions/{partition_path}"
        cmd = f"aws s3 sync {s3_path} {local_dir} --region {self.region} --no-progress"
        self._run_aws(cmd)

if __name__ == "__main__":
    retriever = DataRetriever("my-bucket", "us-east-1")
    
    # List datasets
    datasets = retriever.list_datasets()
    print(f"Datasets: {datasets}")
    
    # List versions
    versions = retriever.list_versions(datasets[0])
    print(f"Versions: {versions}")
    
    # Fetch manifest
    manifest = retriever.fetch_manifest(datasets[0], versions[0], "/tmp/manifest.json")
    print(f"Manifest: {json.dumps(manifest, indent=2)}")
```

---

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| Access denied | Invalid IAM policy or credentials | Verify `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and IAM policy |
| No such bucket | Wrong bucket name or region | Check `S3_BUCKET_NAME` and `AWS_REGION` |
| Connection timeout | Network issue or region mismatch | Verify `AWS_REGION` and network connectivity |
| Slow sync | Downloading too many partitions | Use selective sync with specific date/symbol filters |
| Incomplete files | Interrupted sync | Rerun sync command; AWS will resume |
| Checksum failure | Corrupted download | Delete local files and rerun sync |

---

## Cost Estimation

For a 40 GB dataset with selective retrieval:

- **Full sync**: ~40 GB transfer = $0.02 (data transfer) + $20 (GET requests for 1M small files)
- **Selective sync (1 date, 1 symbol)**: ~100 MB = $0.0001 + $0.005 (GET requests)

Always use selective partition sync for large datasets.
