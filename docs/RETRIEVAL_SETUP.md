# Snapshot Retrieval Script - Setup Guide

## Prerequisites

The `retrieve_snapshot.py` script requires:
1. ✅ Python 3.7+ (you have this)
2. ❌ AWS CLI (needs to be installed)
3. AWS credentials configured

## Step 1: Install AWS CLI

### On macOS (using Homebrew - Recommended):

```bash
brew install awscli
```

### On macOS (using pip):

```bash
pip3 install awscli
```

### Verify Installation:

```bash
aws --version
# Should output: aws-cli/2.x.x Python/3.x.x Darwin/...
```

## Step 2: Configure AWS Credentials

You have two options:

### Option A: Using `aws configure` (Easiest)

```bash
aws configure
```

You'll be prompted for:
- **AWS Access Key ID:** (from your AWS account setup)
- **AWS Secret Access Key:** (from your AWS account setup)  
- **Default region:** `us-east-1` (or whatever region you used)
- **Default output format:** `json`

### Option B: Using Environment Variables

Add to your `~/.zshrc` or `~/.bash_profile`:

```bash
export AWS_ACCESS_KEY_ID="your-access-key-id"
export AWS_SECRET_ACCESS_KEY="your-secret-access-key"
export AWS_REGION="us-east-1"
export S3_BUCKET_NAME="agentic-trading-snapshots-YOUR-SUFFIX"
```

Then reload:
```bash
source ~/.zshrc  # or source ~/.bash_profile
```

## Step 3: Set S3 Bucket Name

```bash
export S3_BUCKET_NAME="agentic-trading-snapshots-YOUR-SUFFIX"
```

Replace `YOUR-SUFFIX` with your actual bucket name.

## Step 4: Test the Script

```bash
cd /Users/avo/GitHub/agentic-trading-system

# List all strategies
python3 scripts/retrieve_snapshot.py list

# List snapshots for a specific strategy
python3 scripts/retrieve_snapshot.py list sample-momentum-strategy

# Download latest snapshot
python3 scripts/retrieve_snapshot.py latest sample-momentum-strategy
```

## Troubleshooting

### Error: "AWS CLI is not installed"
- Run: `brew install awscli` (macOS)
- Or: `pip3 install awscli`

### Error: "Set S3_BUCKET_NAME environment variable"
- Run: `export S3_BUCKET_NAME="your-bucket-name"`
- Or add to `~/.zshrc`

### Error: "Unable to locate credentials"
- Run: `aws configure`
- Or set environment variables (see Option B above)

### Error: "Access Denied"
- Check your AWS credentials are correct
- Verify your IAM user has read permissions to the S3 bucket
- See docs/AWS_SETUP_GUIDE.md for IAM policy details

## Quick Setup Script

Copy and paste this (replace with your actual values):

```bash
# Install AWS CLI (macOS)
brew install awscli

# Configure credentials
aws configure
# Enter your access key ID
# Enter your secret access key
# Enter region: us-east-1
# Enter output format: json

# Set bucket name
export S3_BUCKET_NAME="agentic-trading-snapshots-YOUR-SUFFIX"

# Test it
python3 scripts/retrieve_snapshot.py list
```

## Permanent Setup

To avoid setting environment variables every time, add to `~/.zshrc`:

```bash
# Add this to the end of ~/.zshrc
export S3_BUCKET_NAME="agentic-trading-snapshots-YOUR-SUFFIX"
export AWS_REGION="us-east-1"
```

Then reload:
```bash
source ~/.zshrc
```

## Usage Examples

```bash
# List all strategies in S3
python3 scripts/retrieve_snapshot.py list

# List all snapshots for a strategy
python3 scripts/retrieve_snapshot.py list momentum-trader

# Download the latest snapshot
python3 scripts/retrieve_snapshot.py latest momentum-trader

# Download specific snapshot
python3 scripts/retrieve_snapshot.py download momentum-trader 2026-04-04T12-30-45Z-abc1234

# Downloaded files will be in: ./snapshots/strategy-name/timestamp-commit/
```

## Success!

Once setup is complete, you should see:
```
📋 Available strategies:

  • sample-momentum-strategy (1 snapshots)
```

---

**Need help?** See docs/TROUBLESHOOTING.md
