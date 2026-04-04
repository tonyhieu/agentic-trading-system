# Scripts

Utility scripts for managing strategy snapshots.

## retrieve_snapshot.py

Download and browse strategy snapshots from S3.

### Setup

```bash
# Set environment variables (from GitHub Secrets)
export S3_BUCKET_NAME="your-bucket-name"
export AWS_REGION="us-east-1"
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
```

### Usage

**List all strategies:**
```bash
python3 scripts/retrieve_snapshot.py list
```

**List snapshots for a strategy:**
```bash
python3 scripts/retrieve_snapshot.py list momentum-trader
```

**Download latest snapshot:**
```bash
python3 scripts/retrieve_snapshot.py latest momentum-trader
```

**Download specific snapshot:**
```bash
python3 scripts/retrieve_snapshot.py download momentum-trader 2026-04-04T12-30-45Z-abc1234
```

Downloaded snapshots will be saved to `./snapshots/{strategy-name}/{timestamp-commit}/`

### Requirements

- AWS CLI installed and configured
- Python 3.7+
- Environment variables set (S3_BUCKET_NAME, AWS credentials)
