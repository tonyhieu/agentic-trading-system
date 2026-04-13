# System Architecture: Strategy Snapshot System

## Overview

The Strategy Snapshot System provides automated, reliable backups of trading strategy iterations developed by autonomous agents. This document describes the system architecture, data flow, and technical implementation.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Developer / Agent                            │
│                                                                       │
│  1. Develops strategy        2. Commits code        3. Pushes        │
│     locally                      + results              to GitHub    │
└───────────────────────┬─────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         GitHub Repository                            │
│                                                                       │
│  ┌──────────────────┐        ┌─────────────────────────────────┐   │
│  │  strategies/     │        │  .github/workflows/             │   │
│  │  ├─ strategy-1/  │        │  └─ snapshot-strategy.yml       │   │
│  │  ├─ strategy-2/  │        │                                 │   │
│  │  └─ strategy-3/  │        │  Triggered by:                  │   │
│  └──────────────────┘        │  • Push to snapshots/* branches │   │
│                               │  • Manual workflow_dispatch     │   │
│                               └─────────────┬───────────────────┘   │
└─────────────────────────────────────────────┼───────────────────────┘
                                              │
                                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       GitHub Actions Workflow                        │
│                                                                       │
│  Step 1: Checkout Code                                              │
│  ├─ Fetch repository with full history                              │
│  └─ Extract commit SHA and branch info                              │
│                                                                       │
│  Step 2: Generate Metadata                                          │
│  ├─ Create ISO 8601 timestamp                                       │
│  ├─ Get commit SHA (short form)                                     │
│  ├─ Determine strategy name from input/branch                       │
│  └─ Build snapshot directory name: {timestamp}-{commit-sha}         │
│                                                                       │
│  Step 3: Package Strategy                                           │
│  ├─ Create temp directory structure:                                │
│  │   snapshot-temp/{strategy-name}/{timestamp}-{commit-sha}/        │
│  │   ├── code/          (*.py, *.ipynb, requirements.txt)           │
│  │   ├── results/       (*.json, *.csv, *.png)                      │
│  │   └── metadata.json                                              │
│  └─ Copy files from strategies/{strategy-name}/                     │
│                                                                       │
│  Step 4: Extract Performance Metrics                                │
│  ├─ Read results/backtest-results.json                              │
│  ├─ Extract: total_return, sharpe_ratio, max_drawdown, win_rate    │
│  └─ Include in metadata.json                                        │
│                                                                       │
│  Step 5: Configure AWS Credentials                                  │
│  ├─ Load from GitHub Secrets:                                       │
│  │   • AWS_ACCESS_KEY_ID                                            │
│  │   • AWS_SECRET_ACCESS_KEY                                        │
│  │   • AWS_REGION                                                   │
│  │   • S3_BUCKET_NAME                                               │
│  └─ Authenticate with AWS STS                                       │
│                                                                       │
│  Step 6: Upload to S3                                               │
│  ├─ Sync snapshot-temp/ to S3                                       │
│  ├─ S3 Path: strategies/{strategy-name}/{timestamp}-{commit-sha}/   │
│  └─ Storage class: STANDARD                                         │
│                                                                       │
│  Step 7: Verify Upload                                              │
│  ├─ List files in S3 path                                           │
│  ├─ Check metadata.json exists                                      │
│  └─ Report success/failure                                          │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         AWS S3 Bucket                                │
│                  agentic-trading-snapshots-*                         │
│                                                                       │
│  strategies/                                                         │
│  ├── momentum-trader/                                               │
│  │   ├── 2026-04-04T12-30-45Z-abc1234/                             │
│  │   │   ├── code/                                                  │
│  │   │   │   ├── momentum_strategy.py                               │
│  │   │   │   └── requirements.txt                                   │
│  │   │   ├── results/                                               │
│  │   │   │   ├── backtest-results.json                              │
│  │   │   │   └── trade-history.csv                                  │
│  │   │   └── metadata.json                                          │
│  │   └── 2026-04-05T08-15-22Z-def5678/                             │
│  │       └── ...                                                     │
│  ├── mean-reversion/                                                │
│  │   └── 2026-04-04T14-20-10Z-ghi9012/                             │
│  │       └── ...                                                     │
│  └── ...                                                             │
│                                                                       │
│  Lifecycle Policy: Delete objects > 30 days old                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Data Flow

### Automatic Snapshot Workflow

```
1. Agent develops strategy
   ├─ Create code: strategies/strategy-name/*.py
   ├─ Run backtests: strategies/strategy-name/results/*.json
   └─ Commit locally

2. Agent creates snapshot branch
   └─ git checkout -b snapshots/strategy-name

3. Agent pushes to GitHub
   └─ git push origin snapshots/strategy-name

4. GitHub Actions triggered automatically
   └─ Detects push to snapshots/* branch

5. Workflow packages strategy
   ├─ Copies all code files
   ├─ Copies all result files
   └─ Generates metadata.json

6. Workflow uploads to S3
   └─ Path: s3://bucket/strategies/strategy-name/{timestamp}-{commit}/

7. S3 stores snapshot
   └─ Applies 30-day lifecycle policy

8. Agent receives confirmation
   └─ GitHub Actions workflow completes with success
```

### Manual Snapshot Workflow

```
1. Agent develops strategy (same as automatic)

2. Agent navigates to GitHub Actions UI
   └─ Actions → Create Strategy Snapshot → Run workflow

3. Agent provides inputs
   ├─ strategy_name: "momentum-trader"
   └─ strategy_path: "strategies/momentum-trader"

4-8. (Same as automatic workflow steps 4-8)
```

## Component Details

### 1. Strategy Directory Structure

```
strategies/
└── {strategy-name}/              # Kebab-case naming
    ├── *.py                       # Strategy implementation
    ├── *.ipynb                    # Jupyter notebooks (optional)
    ├── requirements.txt           # Python dependencies (optional)
    └── results/                   # Backtesting outputs
        ├── backtest-results.json  # Performance metrics (recommended)
        ├── trade-history.csv      # Trade log (optional)
        └── *.png                  # Charts/visualizations (optional)
```

**Requirements:**
- Directory must exist in `strategies/` folder
- At least one .py or .ipynb file required
- `results/backtest-results.json` strongly recommended for metrics

### 2. GitHub Actions Workflow

**File:** `.github/workflows/snapshot-strategy.yml`

**Triggers:**
- `workflow_dispatch`: Manual trigger with inputs
- `push` to `snapshots/**` branches: Automatic trigger

**Inputs (workflow_dispatch only):**
- `strategy_name`: Name of the strategy
- `strategy_path`: Path to strategy directory (relative to repo root)

**Environment:**
- Runner: `ubuntu-latest`
- Python: 3.11
- AWS CLI: Provided by GitHub Actions runner

**Steps:**
1. Checkout repository (with full history)
2. Generate snapshot metadata
3. Verify strategy path exists
4. Create snapshot directory structure
5. Copy strategy files to snapshot structure
6. Generate metadata.json with performance metrics
7. Configure AWS credentials from secrets
8. Upload to S3 using `aws s3 sync`
9. Verify upload succeeded
10. Display summary

### 3. Snapshot Metadata

**File:** `metadata.json` (generated during workflow)

**Structure:**
```json
{
  "strategy_name": "momentum-trader",
  "snapshot_timestamp": "2026-04-04T12-30-45Z",
  "commit_sha": "abc1234",
  "commit_sha_full": "abc1234567890abcdef1234567890abcdef12345",
  "branch": "snapshots/momentum-trader",
  "repository": "username/agentic-trading-system",
  "triggered_by": "push",
  "actor": "agent-username",
  "workflow_run_id": "123456789",
  "snapshot_stats": {
    "code_files": 3,
    "result_files": 2,
    "total_size": "245K"
  },
  "performance_metrics": {
    "total_return": 15.34,
    "sharpe_ratio": 1.42,
    "max_drawdown": -8.67,
    "win_rate": 58.33
  },
  "created_at": "2026-04-04T12:30:45Z"
}
```

### 4. AWS S3 Storage

**Bucket Configuration:**
- **Name:** `agentic-trading-snapshots-{unique-suffix}`
- **Region:** Configurable (e.g., us-east-1, us-west-2)
- **Versioning:** Disabled (using timestamped directories instead)
- **Encryption:** SSE-S3 (Amazon S3 managed keys)
- **Public Access:** Blocked (all 4 settings)
- **Object Lock:** Disabled

**Lifecycle Policy:**
```json
{
  "Rules": [{
    "Id": "delete-old-snapshots-30-days",
    "Status": "Enabled",
    "Filter": {
      "Prefix": ""
    },
    "Expiration": {
      "Days": 30
    }
  }]
}
```

**S3 Path Structure:**
```
s3://{bucket-name}/strategies/{strategy-name}/{timestamp}-{commit-sha}/
├── code/
│   └── {copied from strategies/{strategy-name}/*.py}
├── results/
│   └── {copied from strategies/{strategy-name}/results/*}
└── metadata.json
```

### 5. IAM Security

**IAM User:** `github-actions-snapshot-uploader`

**Policy:** `GitHubActionsSnapshotUploadPolicy`

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "AllowSnapshotUpload",
    "Effect": "Allow",
    "Action": [
      "s3:PutObject",
      "s3:GetObject",
      "s3:ListBucket"
    ],
    "Resource": [
      "arn:aws:s3:::{bucket-name}",
      "arn:aws:s3:::{bucket-name}/*"
    ]
  }]
}
```

**Principle of Least Privilege:**
- Only 3 S3 actions allowed
- Scoped to single bucket
- No delete permissions (prevents accidental data loss)
- No IAM permissions
- No access to other AWS services

### 6. GitHub Secrets

**Required Secrets:**
- `AWS_ACCESS_KEY_ID`: IAM user access key
- `AWS_SECRET_ACCESS_KEY`: IAM user secret key
- `AWS_REGION`: S3 bucket region (e.g., us-east-1)
- `S3_BUCKET_NAME`: Full bucket name

**Security:**
- Encrypted at rest by GitHub
- Only accessible during workflow execution
- Never logged or exposed in workflow output
- Can be rotated without code changes

## Scalability Considerations

### Storage Scaling

**Current Design:**
- Handles 100-1000 snapshots easily
- Each snapshot: 1-100 MB typical
- Total storage: 10-100 GB expected

**Scaling Limits:**
- S3: Unlimited storage capacity
- S3: Unlimited objects per bucket
- Lifecycle policy automatically manages growth

**Cost Scaling:**
- Linear with storage volume
- ~$0.023/GB/month for storage
- ~$0.005/1000 PUT requests
- Expected: $3-10/month for moderate usage

### Compute Scaling

**GitHub Actions:**
- Free tier: 2,000 minutes/month for private repos
- Each snapshot: ~2-5 minutes
- Can handle 400-1000 snapshots/month on free tier

**Concurrent Snapshots:**
- GitHub Actions: 20 concurrent jobs (default)
- No issues with parallel execution
- Each snapshot isolated (no conflicts)

### Performance

**Upload Speed:**
- Depends on file size and network
- Typical: 1-10 MB/s
- 50 MB snapshot: ~5-50 seconds upload time

**Workflow Duration:**
- Checkout + setup: ~30 seconds
- Package strategy: ~10 seconds
- Upload to S3: ~10-60 seconds (size dependent)
- **Total: 1-2 minutes per snapshot**

## Reliability & Availability

### Failure Handling

**Workflow Failures:**
- GitHub Actions automatically retries on infrastructure failures
- Failed workflows clearly visible in Actions tab
- Logs available for 90 days for debugging

**S3 Availability:**
- S3 Standard: 99.99% availability SLA
- 99.999999999% (11 nines) durability
- Automatic replication across availability zones

**Recovery:**
- Failed snapshots can be re-triggered manually
- No data corruption risk (atomic uploads)
- Old snapshots remain unaffected

### Monitoring

**GitHub Actions:**
- Workflow status visible in Actions tab
- Email notifications on failure (configurable)
- Workflow run history retained for 90 days

**AWS:**
- AWS Cost Explorer for spending monitoring
- Budget alerts (configured during setup)
- S3 metrics via CloudWatch (optional)

## Security

### Threat Model

**Protected Against:**
- ✅ Credential exposure (secrets encrypted)
- ✅ Unauthorized access (IAM minimal permissions)
- ✅ Data loss from force push (separate S3 storage)
- ✅ Accidental public exposure (S3 bucket private)
- ✅ Runaway costs (lifecycle policy + budget alerts)

**Not Protected Against:**
- ❌ Malicious code in strategy files (out of scope)
- ❌ Compromised AWS root account (mitigated by MFA)
- ❌ Compromised GitHub account with repo admin access

### Best Practices

1. **Never commit AWS credentials to git**
2. **Use GitHub Secrets for all sensitive data**
3. **Enable MFA on AWS root account**
4. **Rotate IAM access keys periodically (every 90 days)**
5. **Review workflow logs for credential leakage**
6. **Use minimal IAM permissions**
7. **Monitor AWS costs regularly**

## Maintenance

### Regular Tasks

**Monthly:**
- Review AWS billing (should be $3-10/month)
- Check snapshot count in S3
- Verify lifecycle policy is running

**Quarterly:**
- Rotate IAM access keys
- Update GitHub secrets with new keys
- Review and clean up old strategies

**Annually:**
- Review system architecture for improvements
- Update workflow dependencies (actions versions)
- Evaluate cost optimization opportunities

### Updates

**Workflow Updates:**
- Modify `.github/workflows/snapshot-strategy.yml`
- Test with sample strategy before production use
- Document changes in commit message

**Infrastructure Updates:**
- AWS changes require console access
- Update documentation to reflect changes
- Notify users of any breaking changes

## Future Enhancements

### Planned Improvements

1. **Snapshot Retrieval Workflow**
   - Download snapshots via GitHub Actions
   - List available snapshots for a strategy
   - Compare snapshots across time

2. **Performance Dashboard**
   - Visualize strategy performance over time
   - Compare multiple strategies
   - Track improvement metrics

3. **Automated Validation**
   - Validate backtest results format
   - Check for required files before upload
   - Lint strategy code automatically

4. **Multi-Cloud Backup**
   - Replicate to Google Cloud Storage
   - Replicate to Azure Blob Storage
   - Geographic redundancy

5. **Notification System**
   - Slack/Discord notifications on snapshot creation
   - Email summaries of daily snapshots
   - Performance anomaly alerts

## Troubleshooting Guide

See [AWS_SETUP_GUIDE.md](./AWS_SETUP_GUIDE.md) for detailed troubleshooting steps.

Common issues:
- Strategy path not found → Verify directory exists and is committed
- AWS credentials error → Check GitHub secrets are set correctly
- Upload timeout → Large files may need workflow timeout adjustment
- Missing metadata → Ensure backtest-results.json exists and is valid JSON

---

**Document Version:** 1.0  
**Last Updated:** 2026-04-04  
**Author:** GitHub Copilot CLI  
**Status:** Production
