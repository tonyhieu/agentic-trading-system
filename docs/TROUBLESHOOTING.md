# Troubleshooting Guide

## Quick Diagnosis

Use this decision tree to quickly identify your issue:

```
Is the workflow failing?
├─ Yes → See "Workflow Failures" section
└─ No
    ├─ Is the upload slow/timing out? → See "Performance Issues"
    ├─ Are files missing from S3? → See "Missing Files"
    ├─ Are costs higher than expected? → See "Cost Issues"  
    ├─ Can't find snapshots in S3? → See "Snapshot Discovery"
    └─ Other → See "Common Issues" or "Getting Help"
```

---

## Workflow Failures

### Error: "Strategy path does not exist"

**Symptoms:**
```
❌ Error: Strategy path 'strategies/my-strategy' does not exist!
Available directories:
.github
docs
```

**Causes:**
1. Strategy directory doesn't exist
2. Path is incorrect (typo or case sensitivity)
3. Files not committed to git

**Solutions:**

```bash
# 1. Check if directory exists locally
ls -la strategies/

# 2. Create directory if missing
mkdir -p strategies/my-strategy
echo "# My Strategy" > strategies/my-strategy/strategy.py

# 3. Commit and push
git add strategies/my-strategy/
git commit -m "Add my strategy"
git push origin main  # or your branch

# 4. Verify in GitHub web interface
# Go to your repo → strategies/ folder → confirm directory is there

# 5. Re-run workflow with exact path
# Use: strategies/my-strategy (not ./strategies or /strategies)
```

### Error: "AWS credentials error" / "AccessDenied"

**Symptoms:**
```
Error: Could not load credentials from any providers
- or -
An error occurred (AccessDenied) when calling the PutObject operation
```

**Causes:**
1. GitHub secrets not configured
2. Secrets have incorrect names (case-sensitive!)
3. IAM policy doesn't allow S3 access
4. Credentials expired or revoked

**Solutions:**

```bash
# Step 1: Verify GitHub Secrets exist
# Go to: Settings → Secrets and variables → Actions
# Must have all 4:
# - AWS_ACCESS_KEY_ID
# - AWS_SECRET_ACCESS_KEY
# - AWS_REGION
# - S3_BUCKET_NAME

# Step 2: Check secret names (EXACT matches required)
# ✅ AWS_ACCESS_KEY_ID
# ❌ aws_access_key_id (wrong case)
# ❌ ACCESS_KEY_ID (missing AWS_ prefix)

# Step 3: Verify IAM policy in AWS
aws iam list-attached-user-policies --user-name github-actions-snapshot-uploader

# Should show: GitHubActionsSnapshotUploadPolicy

# Step 4: Test credentials locally
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
export AWS_REGION="us-east-1"
aws s3 ls s3://your-bucket-name/

# If this fails locally, credentials are invalid
# → Regenerate access keys in IAM console
```

**Regenerating Access Keys:**

1. Go to AWS Console → IAM → Users → github-actions-snapshot-uploader
2. Security credentials tab
3. Access keys → "Create access key"
4. Download new keys
5. Update GitHub Secrets with new values
6. Delete old access key (after verifying new one works)

### Error: "No such bucket" / "BucketNotFound"

**Symptoms:**
```
An error occurred (NoSuchBucket) when calling the PutObject operation:
The specified bucket does not exist
```

**Causes:**
1. Bucket name is incorrect in GitHub secret
2. Bucket is in wrong region
3. Bucket was deleted

**Solutions:**

```bash
# Step 1: List your buckets
aws s3 ls

# Step 2: Find the correct bucket name
# Should see: s3://agentic-trading-snapshots-XXXXX

# Step 3: Update GitHub Secret
# Settings → Secrets → S3_BUCKET_NAME
# Must match EXACTLY (no s3:// prefix, no trailing /)

# Step 4: Verify bucket region matches
aws s3api get-bucket-location --bucket your-bucket-name
# Should match AWS_REGION secret

# Step 5: If bucket doesn't exist, recreate it
# See AWS_SETUP_GUIDE.md Step 3
```

### Error: Workflow timeout

**Symptoms:**
```
The job running on runner GitHub Actions 1 has exceeded the maximum execution time of 360 minutes.
```

**Causes:**
1. Extremely large files (> 1 GB)
2. Slow network connection
3. Infinite loop in code

**Solutions:**

```yaml
# Option 1: Increase timeout (in workflow file)
jobs:
  create-snapshot:
    timeout-minutes: 60  # Default is 360, adjust as needed
```

```bash
# Option 2: Reduce snapshot size
# Check file sizes
du -sh strategies/my-strategy/*
du -sh strategies/my-strategy/results/*

# Remove large files (> 100 MB)
# Compress images
# Sample large CSV files instead of uploading all rows
```

### Error: "metadata.json not found" after upload

**Symptoms:**
```
🔍 Verifying uploaded files...
❌ Verification failed: metadata.json not found
```

**Causes:**
1. Upload failed silently
2. S3 sync command excluded metadata.json
3. Incorrect S3 path

**Solutions:**

```bash
# Step 1: Check S3 manually
aws s3 ls s3://your-bucket/strategies/your-strategy/ --recursive

# Step 2: Look for the snapshot directory
# Should see: 2026-04-04T12-30-45Z-abc1234/

# Step 3: List contents of that directory
aws s3 ls s3://your-bucket/strategies/your-strategy/2026-04-04T12-30-45Z-abc1234/

# Step 4: If files are there but verification failed
# → Re-run workflow (may be transient S3 issue)

# Step 5: If no files were uploaded
# → Check IAM permissions (PutObject allowed?)
# → Check S3 bucket permissions (not blocked?)
```

---

## Performance Issues

### Slow upload (> 5 minutes)

**Causes:**
1. Large snapshot size
2. Many small files (overhead)
3. GitHub Actions runner location far from S3 region

**Solutions:**

```bash
# 1. Check snapshot size
du -sh strategies/my-strategy/

# 2. Optimize file sizes
# - Compress PNG images
# - Remove large CSV files (sample instead)
# - Use JSON summaries instead of raw data

# 3. Choose closer S3 region
# GitHub Actions runners are typically in us-east-1
# Consider using us-east-1 for S3 bucket

# 4. Use parallel upload (advanced)
# Modify workflow to use:
aws s3 sync --cli-connect-timeout 300 \
            --cli-read-timeout 300 \
            --max-concurrent-requests 20
```

### Workflow queued for long time

**Causes:**
1. Too many concurrent workflows
2. GitHub Actions minutes exhausted
3. GitHub service issues

**Solutions:**

```bash
# 1. Check concurrent workflow limit
# Settings → Actions → General
# Default: 20 concurrent jobs

# 2. Check minutes remaining
# Settings → Billing → Actions
# Free tier: 2,000 minutes/month

# 3. Check GitHub Status
# Visit: https://www.githubstatus.com/

# 4. Cancel unnecessary running workflows
# Actions → Running workflows → Cancel
```

---

## Missing Files

### Code files uploaded but no results

**Causes:**
1. `results/` directory doesn't exist
2. Files not committed to git
3. Copy command failed silently

**Solutions:**

```bash
# 1. Verify results directory exists
ls -la strategies/my-strategy/results/

# 2. Check git status
git status
# Results files should not be in .gitignore

# 3. Verify files are committed
git ls-files strategies/my-strategy/results/

# 4. Check workflow logs
# Look for "No JSON results found" messages
# This indicates files don't exist in the expected location

# 5. Ensure proper structure
strategies/my-strategy/
├── strategy.py          ✅
├── results/
│   ├── backtest-results.json  ✅
│   └── trade-history.csv      ✅
```

### Metadata missing performance metrics

**Causes:**
1. `backtest-results.json` doesn't exist
2. JSON is malformed
3. JSON doesn't have expected fields

**Solutions:**

```bash
# 1. Validate JSON syntax
cat strategies/my-strategy/results/backtest-results.json | python3 -m json.tool

# 2. Check for required fields
cat strategies/my-strategy/results/backtest-results.json | jq '.performance'

# Should have: total_return, sharpe_ratio, max_drawdown, win_rate

# 3. Use correct JSON structure (see SKILLS.md)
{
  "performance": {
    "total_return": 15.34,
    "sharpe_ratio": 1.42,
    "max_drawdown": -8.67,
    "win_rate": 58.33
  }
}
```

---

## Snapshot Discovery

### Can't find snapshots in S3

**Causes:**
1. Looking in wrong location
2. Snapshot failed to upload
3. Lifecycle policy deleted snapshot

**Solutions:**

```bash
# 1. List all snapshots
aws s3 ls s3://your-bucket/strategies/ --recursive | grep metadata.json

# 2. List snapshots for specific strategy
aws s3 ls s3://your-bucket/strategies/my-strategy/

# 3. Check snapshot age
aws s3 ls s3://your-bucket/strategies/my-strategy/ --recursive | \
  grep metadata.json | \
  awk '{print $1, $2, $4}'

# 4. If > 30 days old, it was deleted by lifecycle policy (expected)

# 5. Check workflow history for failed uploads
# Actions → Create Strategy Snapshot → Past runs
```

### Different snapshot format than expected

**Causes:**
1. Workflow file was modified
2. Looking at old snapshot (before system update)
3. Manual upload with different structure

**Solutions:**

```bash
# 1. Check workflow file version
cat .github/workflows/snapshot-strategy.yml | head -20

# 2. Download and inspect snapshot
aws s3 sync s3://your-bucket/strategies/my-strategy/2026-04-04T12-30-45Z-abc1234/ ./temp/

# 3. Check metadata
cat ./temp/metadata.json | jq .

# 4. Verify expected structure
tree ./temp/
# Should be: code/, results/, metadata.json
```

---

## Cost Issues

### Unexpected high costs

**Causes:**
1. Too many snapshots
2. Large file sizes
3. Lifecycle policy not working
4. Unexpected data downloads

**Solutions:**

```bash
# 1. Check total storage
aws s3 ls s3://your-bucket --recursive --summarize --human-readable

# 2. Count snapshots
aws s3 ls s3://your-bucket/strategies/ --recursive | grep metadata.json | wc -l

# 3. Find large snapshots
aws s3 ls s3://your-bucket --recursive --human-readable | \
  sort -k3 -h | \
  tail -20

# 4. Verify lifecycle policy
aws s3api get-bucket-lifecycle-configuration --bucket your-bucket

# 5. Check AWS Cost Explorer
# Billing → Cost Explorer → S3 costs by day

# 6. Look for old snapshots (> 30 days)
# These should be auto-deleted
```

**Emergency cost reduction:**

```bash
# Option 1: Reduce retention to 7 days
# S3 Console → Bucket → Management → Lifecycle → Edit rule
# Change "30" to "7"

# Option 2: Delete all snapshots (CAREFUL!)
# aws s3 rm s3://your-bucket/strategies/ --recursive
# (Not recommended - defeats purpose of backups)

# Option 3: Delete specific strategy snapshots
aws s3 rm s3://your-bucket/strategies/old-strategy/ --recursive
```

---

## Common Issues

### Issue: Branch not triggering workflow

**Symptoms:** Pushed to `snapshots/my-strategy` but workflow didn't run.

**Solutions:**

```bash
# 1. Check branch name format
git branch
# Must start with "snapshots/" exactly

# 2. Verify workflow file exists
cat .github/workflows/snapshot-strategy.yml | grep "snapshots/"

# 3. Check workflow is enabled
# Settings → Actions → General
# "Allow all actions and reusable workflows" should be selected

# 4. Force trigger manually
# Actions → Create Strategy Snapshot → Run workflow
```

### Issue: Permission denied errors

**Symptoms:** `403 Forbidden` or `Access Denied` errors

**Solutions:**

```bash
# 1. Check IAM policy
aws iam get-user-policy \
  --user-name github-actions-snapshot-uploader \
  --policy-name GitHubActionsSnapshotUploadPolicy

# 2. Verify S3 bucket policy
aws s3api get-bucket-policy --bucket your-bucket

# 3. Check bucket permissions
aws s3api get-bucket-acl --bucket your-bucket

# 4. Ensure public access is blocked (should be)
aws s3api get-public-access-block --bucket your-bucket
```

### Issue: Git conflicts when pushing snapshot branch

**Symptoms:** `! [rejected] snapshots/strategy -> snapshots/strategy (non-fast-forward)`

**Solutions:**

```bash
# Don't force push! Create new snapshot branch instead:

# 1. Delete local branch
git branch -D snapshots/my-strategy

# 2. Create fresh branch from main
git checkout main
git checkout -b snapshots/my-strategy-v2

# 3. Add updated strategy
cp -r /path/to/updated/strategy strategies/my-strategy/
git add strategies/my-strategy/
git commit -m "Updated strategy"

# 4. Push new branch
git push origin snapshots/my-strategy-v2

# Each snapshot branch can be unique!
```

---

## Debugging Steps

### Step-by-Step Debugging Process

1. **Check workflow logs:**
   - Go to Actions tab
   - Click on failed workflow run
   - Expand each step to see error messages

2. **Verify inputs:**
   - Strategy path exists and is committed
   - GitHub secrets are set correctly
   - S3 bucket exists and is accessible

3. **Test AWS credentials locally:**
   ```bash
   export AWS_ACCESS_KEY_ID="..."
   export AWS_SECRET_ACCESS_KEY="..."
   export AWS_REGION="us-east-1"
   aws s3 ls s3://your-bucket/
   ```

4. **Validate strategy structure:**
   ```bash
   ls -la strategies/my-strategy/
   ls -la strategies/my-strategy/results/
   cat strategies/my-strategy/results/backtest-results.json | python3 -m json.tool
   ```

5. **Check S3 manually:**
   ```bash
   aws s3 ls s3://your-bucket/strategies/my-strategy/ --recursive
   ```

6. **Review workflow file:**
   ```bash
   cat .github/workflows/snapshot-strategy.yml
   # Look for modifications or issues
   ```

---

## Getting Help

### Self-Service Resources

1. **Documentation:**
   - SKILLS.md - Usage instructions
   - AWS_SETUP_GUIDE.md - Infrastructure setup
   - README_FOR_HUMANS.md - Architecture overview

2. **AWS Resources:**
   - [S3 Documentation](https://docs.aws.amazon.com/s3/)
   - [IAM Documentation](https://docs.aws.amazon.com/iam/)
   - [AWS CLI Reference](https://docs.aws.amazon.com/cli/)

3. **GitHub Resources:**
   - [GitHub Actions Documentation](https://docs.github.com/en/actions)
   - [Workflow Syntax](https://docs.github.com/en/actions/reference/workflow-syntax-for-github-actions)

### Collecting Debug Information

When asking for help, include:

```bash
# 1. Workflow run URL
# Example: https://github.com/user/repo/actions/runs/123456789

# 2. Error message (from workflow logs)
# Copy the exact error text

# 3. Strategy structure
ls -laR strategies/my-strategy/

# 4. Git status
git status
git log --oneline -5

# 5. GitHub secrets (NAMES only, not values!)
# Example: "I have AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, S3_BUCKET_NAME"

# 6. AWS bucket info
aws s3 ls s3://your-bucket/ | head -10

# 7. Workflow file (if modified)
cat .github/workflows/snapshot-strategy.yml
```

---

## Prevention Tips

### Avoid Common Pitfalls

✅ **Always commit before creating snapshot**
```bash
git add strategies/my-strategy/
git commit -m "Add strategy"
git push  # Don't forget this!
```

✅ **Validate JSON before pushing**
```bash
cat strategies/my-strategy/results/backtest-results.json | python3 -m json.tool
```

✅ **Use consistent naming conventions**
- Strategies: `kebab-case`
- Branches: `snapshots/strategy-name`
- Files: `snake_case.py`

✅ **Test workflows manually first**
- Use workflow_dispatch before relying on automatic triggers
- Verify one snapshot works before creating many

✅ **Monitor costs regularly**
- Check AWS Cost Explorer monthly
- Set up budget alerts
- Review lifecycle policy is working

✅ **Keep documentation updated**
- Update SKILLS.md if workflow changes
- Document custom modifications
- Share troubleshooting tips with team

---

**Last Updated:** 2026-04-04  
**Version:** 1.0
