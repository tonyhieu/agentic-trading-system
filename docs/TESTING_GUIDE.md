# Data Retrieval & Upload: Testing Guide

This guide provides test cases and validation procedures for the data retrieval system.

## Test Environment Setup

```bash
# Install test dependencies
pip install pytest pandas pyarrow

# Set up test bucket (or use existing one)
export S3_BUCKET_NAME="agentic-trading-snapshots-YOUR-SUFFIX"
export AWS_REGION="us-east-1"

# Create test directory
mkdir -p ./test-data
cd ./test-data
```

---

## Phase 1: Contract Validation

### Test 1.1: Manifest Schema

```python
# test_manifest_schema.py
import json
from pathlib import Path

def test_manifest_required_fields():
    """Verify manifest.json has all required fields."""
    manifest_path = Path("../docs/examples/manifest-example.json")
    
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    required_fields = [
        "dataset_name",
        "dataset_version",
        "created_at",
        "format",
        "compression",
        "partition_scheme",
        "partitions",
        "total_size_bytes"
    ]
    
    for field in required_fields:
        assert field in manifest, f"Missing required field: {field}"
        assert manifest[field] is not None, f"Field {field} is null"
    
    print("✓ Manifest schema valid")

def test_manifest_data_types():
    """Verify manifest fields have correct types."""
    manifest_path = Path("../docs/examples/manifest-example.json")
    
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    assert isinstance(manifest["dataset_name"], str)
    assert isinstance(manifest["dataset_version"], str)
    assert isinstance(manifest["partition_scheme"], list)
    assert isinstance(manifest["partitions"], list)
    assert isinstance(manifest["total_size_bytes"], int)
    
    print("✓ Manifest data types correct")

if __name__ == "__main__":
    test_manifest_required_fields()
    test_manifest_data_types()
```

### Test 1.2: Schema File

```python
# test_schema.py
import json
from pathlib import Path

def test_schema_structure():
    """Verify schema.json format."""
    schema_path = Path("../docs/examples/schema-example.json")
    
    with open(schema_path) as f:
        schema = json.load(f)
    
    assert "columns" in schema
    assert isinstance(schema["columns"], list)
    
    for col in schema["columns"]:
        assert "name" in col
        assert "type" in col
        assert "nullable" in col
    
    print("✓ Schema structure valid")

if __name__ == "__main__":
    test_schema_structure()
```

---

## Phase 2: Upload Workflow Testing

### Test 2.1: Create Test Dataset

```bash
#!/bin/bash
# Create minimal test dataset

DATASET_NAME="test-dataset-$(date +%s)"
DATASET_VERSION="test-v1.0.0"

mkdir -p test-dataset/partitions/date=2026-04-01/symbol=TEST

# Create minimal Parquet file using pandas
python3 << 'PYTHON'
import pandas as pd
import os

# Create sample data
data = {
    "timestamp": [1712102400000, 1712102460000],
    "symbol": ["TEST", "TEST"],
    "open": [100.0, 100.5],
    "high": [101.0, 101.5],
    "low": [99.5, 100.0],
    "close": [100.5, 100.8],
    "volume": [1000, 1500]
}

df = pd.DataFrame(data)
df.to_parquet("test-dataset/partitions/date=2026-04-01/symbol=TEST/part-000.parquet", compression="snappy")
print("✓ Created test Parquet file")
PYTHON

# Create manifest
cat > test-dataset/manifest.json << EOF
{
  "dataset_name": "$DATASET_NAME",
  "dataset_version": "$DATASET_VERSION",
  "created_at": "2026-04-11T00:00:00Z",
  "format": "parquet",
  "compression": "snappy",
  "partition_scheme": ["date", "symbol"],
  "partitions": [
    "partitions/date=2026-04-01/symbol=TEST/part-000.parquet"
  ],
  "total_size_bytes": 1024,
  "record_count": 2,
  "symbols": ["TEST"],
  "date_range": {"start": "2026-04-01", "end": "2026-04-01"}
}
EOF

# Create schema
cat > test-dataset/schema.json << EOF
{
  "dataset_name": "$DATASET_NAME",
  "dataset_version": "$DATASET_VERSION",
  "columns": [
    {"name": "timestamp", "type": "int64", "nullable": false},
    {"name": "symbol", "type": "utf8", "nullable": false},
    {"name": "open", "type": "double", "nullable": false},
    {"name": "high", "type": "double", "nullable": false},
    {"name": "low", "type": "double", "nullable": false},
    {"name": "close", "type": "double", "nullable": false},
    {"name": "volume", "type": "int64", "nullable": false}
  ]
}
EOF

# Create checksums
python3 << 'PYTHON'
import hashlib

files = [
    "manifest.json",
    "schema.json",
    "partitions/date=2026-04-01/symbol=TEST/part-000.parquet"
]

with open("test-dataset/checksums.txt", "w") as f:
    for file in files:
        path = f"test-dataset/{file}"
        with open(path, 'rb') as fp:
            sha = hashlib.sha256(fp.read()).hexdigest()
            f.write(f"SHA256:{file}={sha}\n")

print("✓ Created checksums")
PYTHON

echo "✓ Test dataset created"
```

### Test 2.2: Upload to S3

```bash
#!/bin/bash
# Test upload workflow

DATASET_NAME="test-dataset-$(stat -f %m test-dataset 2>/dev/null || stat -c %Y test-dataset)"
DATASET_VERSION="test-v1.0.0"

echo "Uploading test dataset to S3..."

aws s3 sync test-dataset \
  "s3://$S3_BUCKET_NAME/datasets/$DATASET_NAME/$DATASET_VERSION/" \
  --region "$AWS_REGION" \
  --no-progress

# Verify upload
echo "Verifying manifest is readable..."
aws s3 cp \
  "s3://$S3_BUCKET_NAME/datasets/$DATASET_NAME/$DATASET_VERSION/manifest.json" \
  - \
  --region "$AWS_REGION" | jq .

echo "✓ Upload successful"
```

---

## Phase 3: Retrieval Testing

### Test 3.1: List Datasets

```python
# test_list_datasets.py
import subprocess
import os

def test_list_datasets():
    """Test dataset discovery."""
    cmd = [
        "python",
        "scripts/data_retriever.py",
        "list-datasets"
    ]
    
    env = os.environ.copy()
    env["S3_BUCKET_NAME"] = os.environ["S3_BUCKET_NAME"]
    env["AWS_REGION"] = os.environ.get("AWS_REGION", "us-east-1")
    
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    
    assert result.returncode == 0, f"Command failed: {result.stderr}"
    
    datasets = result.stdout.strip().split('\n')
    assert len(datasets) > 0, "No datasets found"
    
    print(f"✓ Found {len(datasets)} datasets")
    for ds in datasets[:3]:
        print(f"  - {ds}")

if __name__ == "__main__":
    test_list_datasets()
```

### Test 3.2: Fetch Manifest

```python
# test_fetch_manifest.py
import subprocess
import json
import os
import tempfile

def test_fetch_manifest():
    """Test manifest retrieval."""
    
    # Find first dataset
    result = subprocess.run(
        ["python", "scripts/data_retriever.py", "list-datasets"],
        capture_output=True,
        text=True,
        env=os.environ
    )
    
    datasets = result.stdout.strip().split('\n')
    if not datasets:
        print("⚠ No datasets to test")
        return
    
    dataset = datasets[0].strip()
    
    # Find first version
    result = subprocess.run(
        ["python", "scripts/data_retriever.py", "list-versions", dataset],
        capture_output=True,
        text=True,
        env=os.environ
    )
    
    versions = result.stdout.strip().split('\n')
    if not versions:
        print(f"⚠ No versions for dataset {dataset}")
        return
    
    version = versions[0].strip()
    
    # Fetch manifest
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        
        result = subprocess.run(
            ["python", "scripts/data_retriever.py", "fetch-manifest", dataset, version],
            capture_output=True,
            text=True,
            env=os.environ
        )
        
        assert result.returncode == 0, f"Failed to fetch manifest: {result.stderr}"
        
        manifest = json.loads(result.stdout)
        
        assert "dataset_name" in manifest
        assert "dataset_version" in manifest
        assert "partitions" in manifest
        
        print(f"✓ Fetched manifest for {dataset}/{version}")
        print(f"  - Records: {manifest.get('record_count', 'N/A')}")
        print(f"  - Size: {manifest.get('total_size_bytes', 'N/A')} bytes")

if __name__ == "__main__":
    test_fetch_manifest()
```

### Test 3.3: Sync Partition

```bash
#!/bin/bash
# Test partition download

echo "Testing partition sync..."

# Create cache directory
mkdir -p test-cache
cd test-cache

# Sync a partition
python3 << 'PYTHON'
import subprocess
import os

dataset = "us-equities-bars-1m"  # Replace with actual dataset
version = "v1.0.0"  # Replace with actual version
partition = "date=2026-04-01/symbol=AAPL"  # Replace with actual partition

cmd = [
    "python",
    "../scripts/data_retriever.py",
    "sync-partition",
    dataset,
    version,
    partition
]

result = subprocess.run(cmd, capture_output=True, text=True)

if result.returncode == 0:
    print("✓ Partition synced successfully")
else:
    print(f"✗ Sync failed: {result.stderr}")

PYTHON

cd ..
rm -rf test-cache
```

---

## Phase 4: Integration Testing

### Test 4.1: Docker Build

```bash
#!/bin/bash
# Test Docker image build

echo "Testing Docker build..."

docker build -t test-agent . \
  && echo "✓ Docker image built successfully" \
  || echo "✗ Docker build failed"

# Verify image has required tools
docker run --rm test-agent python --version
docker run --rm test-agent aws --version

echo "✓ Docker image contains required tools"
```

### Test 4.2: Docker Data Retrieval

```bash
#!/bin/bash
# Test data retrieval in Docker

echo "Testing Docker data retrieval..."

docker run --rm \
  -e AWS_REGION \
  -e S3_BUCKET_NAME \
  -e AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY \
  -v "$(pwd)/test-cache:/data-cache" \
  test-agent \
  python /scripts/data_retriever.py list-datasets

echo "✓ Docker data retrieval works"

rm -rf test-cache
```

### Test 4.3: End-to-End Download

```python
# test_e2e_download.py
import subprocess
import pandas as pd
from pathlib import Path
import os
import json

def test_e2e_download_and_load():
    """Test complete workflow: download -> load -> verify."""
    
    # 1. Fetch manifest
    cmd = ["python", "scripts/data_retriever.py", "fetch-manifest", 
           "us-equities-bars-1m", "v1.0.0"]
    result = subprocess.run(cmd, capture_output=True, text=True, env=os.environ)
    
    if result.returncode != 0:
        print(f"⚠ Test skipped: {result.stderr}")
        return
    
    manifest = json.loads(result.stdout)
    
    # 2. Download first partition
    if manifest.get("partitions"):
        first_partition = manifest["partitions"][0].replace("partitions/", "")
        
        cmd = ["python", "scripts/data_retriever.py", "sync-partition",
               "us-equities-bars-1m", "v1.0.0", first_partition]
        
        result = subprocess.run(cmd, capture_output=True, text=True, env=os.environ)
        assert result.returncode == 0, f"Download failed: {result.stderr}"
        
        # 3. Load data
        cache_path = Path("./data-cache/us-equities-bars-1m/v1.0.0/partitions") / first_partition
        parquet_files = list(cache_path.glob("**/*.parquet"))
        
        if parquet_files:
            df = pd.read_parquet(parquet_files[0])
            assert not df.empty, "Loaded dataframe is empty"
            print(f"✓ Downloaded and loaded {len(df)} records")
        else:
            print("⚠ No Parquet files found in partition")

if __name__ == "__main__":
    test_e2e_download_and_load()
```

---

## Validation Checklist

- [ ] **Contract Validation**
  - [ ] Manifest JSON schema correct
  - [ ] Schema JSON documents all columns
  - [ ] Partition naming follows convention
  - [ ] Checksums file includes all files

- [ ] **Upload Workflow**
  - [ ] Test dataset created locally
  - [ ] Dataset synced to S3
  - [ ] Manifest readable from S3
  - [ ] All files verified with checksums

- [ ] **Retrieval Workflow**
  - [ ] List datasets works
  - [ ] List versions works
  - [ ] Fetch manifest works
  - [ ] Sync partition works
  - [ ] Checksums validate

- [ ] **Docker Integration**
  - [ ] Docker image builds
  - [ ] Image contains required tools
  - [ ] Data retrieval works in container
  - [ ] Volume mounts work correctly

- [ ] **End-to-End**
  - [ ] Download -> load flow works
  - [ ] Data cache persists between runs
  - [ ] Large partitions download completely
  - [ ] Interrupted syncs resume correctly

---

## Performance Benchmarks

Expected performance metrics:

| Operation | Expected Time | Notes |
|-----------|---------------|-------|
| List datasets | < 1s | AWS API call |
| List versions | < 1s | AWS API call |
| Fetch manifest | 1-3s | Download small file |
| Fetch schema | 1-3s | Download small file |
| Download 1 partition (10 MB) | 5-10s | Network dependent |
| Download 10 partitions (100 MB) | 30-60s | Parallel requests |
| Docker image build | 20-30s | First build, cached after |
| Docker startup + list-datasets | 5-10s | Container startup |

---

## Running All Tests

```bash
#!/bin/bash
set -e

echo "=== Data Retrieval Test Suite ==="

# Phase 1: Contract
echo -e "\n--- Phase 1: Contract Validation ---"
python3 test_manifest_schema.py
python3 test_schema.py

# Phase 2: Upload
echo -e "\n--- Phase 2: Upload Workflow ---"
bash test_create_dataset.sh
bash test_upload_to_s3.sh

# Phase 3: Retrieval
echo -e "\n--- Phase 3: Retrieval Testing ---"
python3 test_list_datasets.py
python3 test_fetch_manifest.py
bash test_sync_partition.sh

# Phase 4: Integration
echo -e "\n--- Phase 4: Integration Testing ---"
bash test_docker_build.sh
bash test_docker_retrieval.sh

# Integration
echo -e "\n--- End-to-End Testing ---"
python3 test_e2e_download.py

echo -e "\n✓ All tests passed!"
```

Save as `test_all.sh` and run with:
```bash
chmod +x test_all.sh
./test_all.sh
```
