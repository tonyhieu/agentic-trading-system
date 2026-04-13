# Cost Management Guide

## Overview

This document provides detailed information about the costs associated with the Strategy Snapshot System, how to monitor spending, and tips for cost optimization.

## Expected Monthly Costs

### AWS S3 Storage (Primary Cost)

**Storage Costs (S3 Standard):**
- Rate: $0.023 per GB/month
- Expected: 10-100 GB total storage
- **Monthly: $0.23 - $2.30**

**Request Costs:**
- PUT requests: $0.005 per 1,000 requests
- GET requests: $0.0004 per 1,000 requests
- Expected: 100-500 snapshots/month
- **Monthly: $0.01 - $0.05**

**Data Transfer:**
- Uploads to S3: FREE
- Downloads from S3: $0.09/GB (first 100 GB/month free)
- Expected: Minimal downloads (mostly automated)
- **Monthly: ~$0.00**

### GitHub Actions (Included)

**Compute Minutes:**
- Free tier: 2,000 minutes/month (private repos)
- Each snapshot: 2-5 minutes
- Can handle 400-1,000 snapshots/month
- **Monthly: $0.00** (within free tier)

### Total Expected Cost

| Usage Level | Storage | Requests | Total/Month |
|-------------|---------|----------|-------------|
| Light (50 snapshots, 10 GB) | $0.23 | $0.01 | **$0.24** |
| Moderate (250 snapshots, 50 GB) | $1.15 | $0.03 | **$1.18** |
| Heavy (500 snapshots, 100 GB) | $2.30 | $0.05 | **$2.35** |

**Well within the $10-50/month budget!**

## Cost Breakdown by Component

### 1. S3 Storage

```
Cost = (Total GB × $0.023) + (PUT requests ÷ 1000 × $0.005)
```

**Factors affecting cost:**
- Number of snapshots per month
- Average snapshot size (code + results)
- Retention period (currently 30 days)

**Example calculation:**
```
Scenario: 250 snapshots/month, 200 MB each, 30-day retention

Total storage after 30 days:
= 250 snapshots × 0.2 GB × 30 days ÷ 30 days
= 50 GB (steady state with lifecycle policy)

Storage cost: 50 GB × $0.023 = $1.15/month
Request cost: 250 PUT × $0.005/1000 = $0.001/month
Total: ~$1.15/month
```

### 2. Lifecycle Policy Savings

**Without lifecycle policy:**
- Unlimited growth
- Cost increases linearly over time
- Example: 6 months = 300 GB = $6.90/month

**With 30-day lifecycle policy:**
- Storage plateaus at ~30 days worth
- Cost remains constant
- Example: Steady state = 50 GB = $1.15/month

**Savings: ~85% after 6 months**

### 3. Hidden Costs (None!)

✅ No data transfer costs (uploads are free)  
✅ No API gateway costs (direct S3)  
✅ No Lambda costs (GitHub Actions handles compute)  
✅ No NAT gateway costs  
✅ No VPC costs  
✅ No CloudFront costs  

This is one of the most cost-effective architectures possible!

## Monitoring Costs

### Option 1: AWS Cost Explorer (Recommended)

1. Log in to AWS Console
2. Navigate to "Billing and Cost Management"
3. Click "Cost Explorer" in the left sidebar
4. Click "Launch Cost Explorer" (one-time setup)

**View daily costs:**
- Select date range (last 30 days)
- Group by: Service
- Filter to: S3
- View detailed breakdown

**Features:**
- Daily cost graphs
- Service-level breakdown
- Month-to-date spending
- Forecast for end of month

### Option 2: AWS Budget Alerts (Recommended)

Set up during infrastructure setup (see AWS_SETUP_GUIDE.md).

**Alert thresholds:**
- 85% of budget: Warning email
- 100% of budget: Critical email

**Recommended budget: $15/month**
- Light usage: ~$1/month (93% under budget)
- Moderate usage: ~$5/month (67% under budget)
- Heavy usage: ~$10/month (33% under budget)

### Option 3: AWS CLI

```bash
# Get current month costs
aws ce get-cost-and-usage \
  --time-period Start=$(date -u +%Y-%m-01),End=$(date -u +%Y-%m-%d) \
  --granularity MONTHLY \
  --metrics "UnblendedCost" \
  --group-by Type=SERVICE

# Get S3 costs specifically
aws ce get-cost-and-usage \
  --time-period Start=$(date -u +%Y-%m-01),End=$(date -u +%Y-%m-%d) \
  --granularity DAILY \
  --metrics "UnblendedCost" \
  --filter file://s3-filter.json

# s3-filter.json:
{
  "Dimensions": {
    "Key": "SERVICE",
    "Values": ["Amazon Simple Storage Service"]
  }
}
```

### Option 4: Check S3 Storage Size

```bash
# Get total bucket size
aws s3 ls s3://your-bucket-name --recursive --summarize | grep "Total Size"

# Get number of objects
aws s3 ls s3://your-bucket-name --recursive --summarize | grep "Total Objects"

# Estimate monthly cost
# (Size in bytes ÷ 1073741824) × $0.023 = Monthly storage cost
```

## Cost Optimization Strategies

### 1. Adjust Retention Period

**Current: 30 days**

**Reduce to 14 days:**
- Storage: ~50% savings
- Trade-off: Less history available
- Recommended: Only if running out of budget

**Reduce to 7 days:**
- Storage: ~75% savings
- Trade-off: Minimal history
- Recommended: Not recommended unless necessary

**To change:**
1. Go to S3 Console
2. Open your bucket
3. Management → Lifecycle rules
4. Edit "delete-old-snapshots-30-days"
5. Change "Days after object creation" to desired value

### 2. Optimize Snapshot Size

**Strategy code:**
- Already minimal (typically < 1 MB)
- No optimization needed

**Backtesting results:**
- JSON files: Usually < 10 KB (very efficient)
- CSV files: Can be large (1-100 MB)
- Charts/images: Can be large (1-10 MB each)

**Optimization tips:**
- ✅ Compress PNG images before committing
- ✅ Sample large CSV files (e.g., first/last 1000 rows)
- ✅ Store aggregate metrics in JSON, not raw trades
- ❌ Don't include large datasets (> 100 MB)

**Example:**
```python
# Bad: Include all 1M trades
df.to_csv('results/all_trades.csv')  # 500 MB file!

# Good: Include summary only
summary = {
    'total_trades': len(df),
    'profitable_trades': len(df[df['pnl'] > 0]),
    'avg_pnl': df['pnl'].mean(),
    'total_pnl': df['pnl'].sum()
}
with open('results/trade_summary.json', 'w') as f:
    json.dump(summary, f)  # 1 KB file!
```

### 3. Use Intelligent-Tiering (Advanced)

For long-term archival needs:

**S3 Intelligent-Tiering:**
- Automatically moves objects to cheaper tiers
- Same retrieval performance
- Small monitoring fee ($0.0025 per 1,000 objects)

**When to use:**
- Retention > 90 days
- Rare access to old snapshots
- Potential 40-70% savings on storage

**Not recommended for 30-day retention** (overhead not worth it)

### 4. Compress Snapshots (Advanced)

Currently, files are uploaded uncompressed. For further optimization:

**Option A: Gzip individual files**
```yaml
# In workflow, before upload
- name: Compress results
  run: |
    find snapshot-temp -name "*.csv" -exec gzip {} \;
    find snapshot-temp -name "*.json" -exec gzip {} \;
```
Savings: ~70% for CSV, ~50% for JSON

**Option B: Tar.gz entire snapshot**
```yaml
- name: Archive snapshot
  run: |
    tar -czf snapshot.tar.gz snapshot-temp/
```
Savings: ~60-80% total

**Trade-off:** Harder to browse individual files in S3

### 5. Selective Snapshots

Not every commit needs a snapshot. Save costs by:

**Only snapshot when:**
- ✅ Major strategy changes
- ✅ Performance improvements
- ✅ Production deployments

**Don't snapshot when:**
- ❌ Minor code cleanups
- ❌ Documentation changes
- ❌ Work-in-progress experiments

**Implementation:** Use manual workflow dispatch instead of automatic triggers for non-critical changes.

## Cost Anomaly Detection

### Warning Signs

🚨 **Unusual cost increase:**
- Check S3 bucket for unexpected files
- Verify lifecycle policy is enabled
- Look for extremely large snapshots

🚨 **Many failed uploads retrying:**
- Each retry incurs PUT request costs
- Fix workflow issues promptly

🚨 **Accidental data downloads:**
- GET requests are cheap, but data transfer costs accumulate
- Review CloudTrail logs for unexpected access

### Monthly Cost Check

Perform this check on the 1st of each month:

```bash
# 1. Check total S3 storage
aws s3 ls s3://your-bucket --recursive --summarize --human-readable

# 2. Count snapshots
aws s3 ls s3://your-bucket/strategies/ --recursive | grep metadata.json | wc -l

# 3. Get month-to-date costs
# (Use AWS Cost Explorer as described above)

# 4. Verify lifecycle policy
aws s3api get-bucket-lifecycle-configuration --bucket your-bucket

# 5. Check for objects > 30 days old (should be none)
aws s3 ls s3://your-bucket --recursive | awk '{if ($1 < "2026-03-05") print $0}'
```

### Setting Up Anomaly Alerts

**AWS Cost Anomaly Detection (Free):**

1. Go to AWS Console → Cost Management
2. Click "Cost Anomaly Detection"
3. Click "Create monitor"
4. Configure:
   - Monitor type: AWS Services
   - Service: Amazon S3
   - Alerting threshold: $1.00
   - Email: your-email@example.com
5. Save

You'll receive automatic emails if S3 costs spike unexpectedly!

## Sample Cost Scenarios

### Scenario 1: Single Agent, Weekly Snapshots

```
Assumptions:
- 4 snapshots/month (weekly)
- 100 MB per snapshot
- 30-day retention

Calculations:
Storage: 0.1 GB × 4 snapshots × $0.023 = $0.009/month
Requests: 4 PUT × $0.005/1000 = $0.00002/month
Total: ~$0.01/month

Verdict: Negligible cost!
```

### Scenario 2: Multiple Agents, Daily Snapshots

```
Assumptions:
- 5 agents × 30 snapshots/month each = 150 snapshots/month
- 50 MB per snapshot
- 30-day retention

Calculations:
Storage: 0.05 GB × 150 × $0.023 = $0.17/month
Requests: 150 PUT × $0.005/1000 = $0.00075/month
Total: ~$0.17/month

Verdict: Still very cheap!
```

### Scenario 3: Heavy Research, Hourly Snapshots

```
Assumptions:
- 10 agents × 720 snapshots/month each = 7,200 snapshots/month
- 200 MB per snapshot
- 30-day retention (but only ~720 snapshots stored due to lifecycle)

Calculations:
Storage: 0.2 GB × 720 × $0.023 = $3.31/month
Requests: 7,200 PUT × $0.005/1000 = $0.036/month
Total: ~$3.35/month

Verdict: Still under $5/month!
```

## Cost Comparison

### Alternative Solutions

| Solution | Storage Cost | Compute Cost | Total/Month |
|----------|-------------|--------------|-------------|
| **Current (S3 + GitHub Actions)** | $1-3 | $0 | **$1-3** |
| Git LFS | $5/50 GB | $0 | $5+ |
| Backblaze B2 | $0.5-1 | $0 | $0.5-1 |
| Google Cloud Storage | $1-3 | $0 | $1-3 |
| Self-hosted NAS | $0 | $50 (amortized) | $50 |
| GitHub Packages | $0.50/GB | $0 | $25+ |

**Our solution is competitive with the cheapest options while offering better reliability!**

## ROI Analysis

### Cost vs. Value

**Monthly cost: ~$3**

**Value provided:**
- ✅ Prevents data loss (invaluable)
- ✅ Enables iteration (critical for agents)
- ✅ Auditability (compliance/research)
- ✅ Reproducibility (scientific value)
- ✅ Time saved (automation vs manual backup)

**Time savings:**
- Manual backup: 5 min/snapshot × 250 snapshots = 1,250 min/month
- Automated system: 0 minutes
- **Savings: ~20 hours/month of agent time**

Even valuing agent time at $10/hour = $200/month value  
**ROI: ~6,600% return on investment**

---

## Summary

✅ **Expected cost: $1-5/month** (well under budget)  
✅ **Monitoring: AWS Cost Explorer + Budget Alerts**  
✅ **Optimization: Adjust retention, optimize file sizes**  
✅ **ROI: Extremely high value for minimal cost**  

The Strategy Snapshot System is designed to be cost-effective while providing maximum value. With proper monitoring and the 30-day lifecycle policy, costs will remain predictable and low.

---

**Last Updated:** 2026-04-04  
**Budget Recommendation:** $15/month (provides 3-5x buffer)
