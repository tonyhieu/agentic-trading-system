# Troubleshooting

Organized by the skill or system the error comes from. If you don't know where to start, skim the headings below.

- [Setup](#setup) — problems bringing up AWS infrastructure or credentials
- [Snapshots](#snapshots) — problems creating or locating strategy snapshots
- [Data Retrieval](#data-retrieval) — problems downloading or loading dataset partitions

---

## Setup

### "Bucket name already exists"

S3 bucket names are globally unique. Try a more specific suffix (e.g. `-uchicago-2026-<initials>`).

### "Access denied" when testing credentials

1. Verify the IAM policy ARN matches your bucket name.
2. Check GitHub secret names are exact (case-sensitive): `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `S3_BUCKET_NAME`.
3. Confirm the policy is attached to the IAM user.

```bash
aws iam list-attached-user-policies --user-name github-actions-snapshot-uploader
# Should list: GitHubActionsSnapshotUploadPolicy

aws s3 ls s3://$S3_BUCKET_NAME/
# Should succeed without AccessDenied
```

### "Credentials not working"

Regenerate the access key pair in IAM → Users → Security credentials, update GitHub secrets, and verify you copied the whole key (no spaces/newlines).

### Unexpected cost spike

1. List total storage: `aws s3 ls s3://$S3_BUCKET_NAME --recursive --summarize --human-readable`
2. Find large snapshots: `aws s3 ls s3://$S3_BUCKET_NAME --recursive --human-readable | sort -k3 -h | tail -20`
3. Verify the 30-day lifecycle rule exists: `aws s3api get-bucket-lifecycle-configuration --bucket $S3_BUCKET_NAME`
4. Inspect AWS Cost Explorer (Billing dashboard) for the time window.

If you need to shrink retention quickly, edit the lifecycle rule in the S3 console from 30 days down to 7–14.

---

## Snapshots

### "Strategy path does not exist"

```
❌ Error: Strategy path 'strategies/my-strategy' does not exist!
```

1. Verify directory exists locally: `ls strategies/my-strategy/`
2. Ensure it is committed and pushed — the workflow reads from GitHub, not your working tree.
3. Use the exact path, case-sensitive: `strategies/my-strategy` (no leading `./` or `/`).

### "AccessDenied" / "Could not load credentials" during workflow

See the Setup section above. Most commonly: a missing or mis-named GitHub secret. Must be all four of:

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_REGION`
- `S3_BUCKET_NAME`

### "NoSuchBucket"

Bucket name in the secret is wrong. Must match exactly — no `s3://` prefix, no trailing `/`. Region also must match the bucket's region:

```bash
aws s3api get-bucket-location --bucket $S3_BUCKET_NAME
```

### Workflow timeout

Default GitHub Actions timeout is 360 min. If your snapshot genuinely takes longer, something is wrong — most likely a huge file that shouldn't be committed. Check sizes:

```bash
du -sh strategies/my-strategy/*
```

Strip large CSVs; sample instead. Images: compress PNGs.

### "metadata.json not found" after upload

Usually a transient S3 issue — re-run the workflow. If it persists:

```bash
aws s3 ls s3://$S3_BUCKET_NAME/strategies/<strategy-name>/ --recursive
```

If files are listed, the verification step is flaky. If the directory is empty, the upload step failed silently — check IAM permissions include `s3:PutObject`.

### No performance metrics in metadata

`results/backtest-results.json` is missing or malformed. Validate:

```bash
cat strategies/my-strategy/results/backtest-results.json | python3 -m json.tool
cat strategies/my-strategy/results/backtest-results.json | jq '.performance'
```

See the format spec in [../SKILLS.md](../SKILLS.md#backtest-resultsjson-format).

### Snapshot branch push rejected (non-fast-forward)

Don't force push. Make a fresh branch:

```bash
git checkout main
git checkout -b snapshots/my-strategy-v2
git add strategies/my-strategy/
git commit -m "Updated strategy"
git push origin snapshots/my-strategy-v2
```

### Can't find a snapshot in S3

```bash
# All snapshots across strategies
aws s3 ls s3://$S3_BUCKET_NAME/strategies/ --recursive | grep metadata.json

# By age
aws s3 ls s3://$S3_BUCKET_NAME/strategies/<strategy>/ --recursive \
  | grep metadata.json | awk '{print $1, $2, $4}'
```

Snapshots older than 30 days are removed by the lifecycle policy — that is expected behavior.

### Branch not triggering a workflow

Branch must start with `snapshots/` exactly. Also confirm Actions is enabled under Settings → Actions → General → "Allow all actions and reusable workflows". You can force-run from the Actions tab as a fallback.

---

## Data Retrieval

### `AWS_ACCESS_KEY_ID not found` / `S3_BUCKET_NAME not set`

Environment variables aren't exported. See [../SKILLS.md](../SKILLS.md#environment-setup).

### `No such file or directory: 'aws'`

AWS CLI isn't installed.

```bash
# macOS
brew install awscli
# Linux
pip install awscli
# Verify
aws --version
```

In the project's Docker image the CLI is pre-installed — run commands via `docker-compose run agent`.

### `DBNDecoder.__new__() got multiple values for argument 'has_metadata'`

You passed a path string to `DBNDecoder`. It needs a file object:

```python
# Wrong
decoder = dbn.DBNDecoder("data.dbn.zst")

# Right
with open("data.dbn.zst", "rb") as f:
    decoder = dbn.DBNDecoder(f)
    df = decoder.to_df()
```

### "Partition not found"

The partition path doesn't match the manifest. Fetch the manifest first and use an exact path from its `partitions` list:

```bash
python scripts/data_retriever.py fetch-manifest glbx-mdp3-market-data v1.0.0
```

Partition format is `date=YYYYMMDD` (no hyphens inside the date).

### "Could not parse line XXX in checksums file"

Checksum file has a format anomaly. Fall back to a manual check:

```bash
sha256sum data-cache/glbx-mdp3-market-data/v1.0.0/partitions/date=20260308/data.dbn.zst
```

and compare against the hash in `checksums.txt`.

### Connection timeout / slow download

Verify region matches (`AWS_REGION=us-east-2`). If you're on a slow link, download fewer dates per iteration. A single date is ~330 MB.

### Out of disk space

```bash
rm -rf ./data-cache/
```

The cache is safe to wipe — partitions will re-download as needed. Cached data is free to reuse, but storage is local.

---

## Gathering debug info

When asking for help, include:

1. Workflow run URL (if applicable).
2. Exact error text.
3. `git status` and `git log --oneline -5`.
4. Directory listing: `ls -laR strategies/<strategy-name>/`.
5. Names (not values) of the GitHub secrets that are set.
6. Output of `aws s3 ls s3://$S3_BUCKET_NAME/ | head`.
