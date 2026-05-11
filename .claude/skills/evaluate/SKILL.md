---
name: evaluate
description: Retrieve the Lambda evaluator's out-of-sample report after snapshotting an algorithm and merge it into the algorithm's backtest-results.json as performance_oos.
when_to_use: Use in a follow-up invocation after a successful snapshot push. The Lambda runs automatically on snapshot upload — this skill is only for fetching the report and merging it into the canonical summary.
user-invocable: false
allowed-tools: Bash Read Edit
---

# Cloud Evaluation (Lambda)

How to retrieve out-of-sample evaluation results after snapshotting an
algorithm. The Lambda evaluator is the *test-set* counterpart to local
backtests — local runs use `config.yaml → data_window.train`; the Lambda
runs the held-out `config.yaml → data_window.test`.

## 1. Trigger model

You do not invoke the evaluator directly. The flow is:

1. Push to `snapshots/<algo-id>` (see the `snapshot` skill §4).
2. The GitHub Actions workflow uploads to
   `s3://$S3_BUCKET_NAME/execution_algos/<algo-id>/<timestamp>-<commit>/`.
3. An S3 event invokes the `execution-algorithm-evaluator` Lambda
   (region `us-east-1`).
4. Lambda runs the snapshotted algorithm against `data_window.test` and
   writes a report back to S3.

A successful snapshot push is the trigger. If the snapshot upload fails, no
evaluation runs.

## 2. Cost discipline (read before triggering)

Each evaluation costs roughly **$0.30** (1 GB Lambda × ~12 minutes). The
research loop budget in `OBJECTIVE.md` is finite — treat cloud evaluations
as the gated, paid step that comes *after* train-window passes locally.

- Run the local backtest loop (see the `backtest` skill §7) against
  `data_window.train` first and confirm the algorithm beats `pass_gate`.
- Only then snapshot. Pushing untested code wastes budget.
- Each refinement variant (`OBJECTIVE.md §6`) is a separate evaluation —
  budget accordingly before opening a refinement chain.

## 3. Where reports land

```
s3://$S3_BUCKET_NAME/evaluation-reports/<algo-id>/
├── <timestamp>_evaluation_report.json   # metrics + status
├── <timestamp>_backtest_logs.txt        # Lambda execution logs
└── <timestamp>_metrics_summary.json     # condensed metric block
```

`<timestamp>` matches the snapshot timestamp, so a snapshot at
`2026-04-30T14-32-00Z-abc1234` produces a report under the same prefix.

## 4. Retrieve a report

```bash
# List all reports for an algorithm
aws s3 ls "s3://$S3_BUCKET_NAME/evaluation-reports/<algo-id>/" \
  --region us-east-2

# Download the latest report (sort + tail)
LATEST=$(aws s3 ls "s3://$S3_BUCKET_NAME/evaluation-reports/<algo-id>/" \
  --region us-east-2 \
  | awk '/evaluation_report\.json$/ {print $4}' | sort | tail -1)

aws s3 cp "s3://$S3_BUCKET_NAME/evaluation-reports/<algo-id>/$LATEST" - \
  --region us-east-2 | python3 -m json.tool
```

Or via boto3:

```python
import boto3, json, os
s3 = boto3.client("s3", region_name="us-east-2")
bucket = os.environ["S3_BUCKET_NAME"]

resp = s3.list_objects_v2(Bucket=bucket, Prefix="evaluation-reports/<algo-id>/")
keys = sorted(o["Key"] for o in resp.get("Contents", [])
              if o["Key"].endswith("evaluation_report.json"))
report = json.load(s3.get_object(Bucket=bucket, Key=keys[-1])["Body"])
```

## 5. Report shape and OOS merging

The Lambda report's exact field names may drift; read the actual JSON
before relying on specific keys. The shape, the field-by-field mapping
into `performance_oos`, and which fields are unavailable (record `null`
rather than estimating, per `OBJECTIVE.md §8` honesty rules) are in
[oos-report.md](oos-report.md). Load that file when you actually need to
merge a report — most invocations only need the procedural steps in this
file.

Map the report into your snapshot's `results/backtest-results.json`
(see the `snapshot` skill §3) under `period.test_dates` and a parallel
`performance_oos` block — do **not** overwrite the train-window
`performance` numbers. Both must remain auditable separately.

Also set `oos_retrieved_at` on the matching `research/program_database.json`
entry (find it by `id == <algo-id>`) to the current UTC timestamp
(`datetime.now(timezone.utc).isoformat()` form). This is one of the two
edit exceptions to the append-only rule (the other being the `meta`
backfill — see OBJECTIVE.md §9). Commit both edits together on a new
commit on the current branch.

## 6. Monitor a run in flight

```bash
# Tail Lambda logs in real time
aws logs tail /aws/lambda/execution-algorithm-evaluator \
  --follow --region us-east-2

# Last 50 lines (one-shot)
aws logs tail /aws/lambda/execution-algorithm-evaluator \
  --max-items 50 --region us-east-2
```

A run typically completes in 10–13 minutes. If no report appears after
~20 minutes, check CloudWatch for a timeout or import error.

## 7. Status troubleshooting

| `status` / symptom                | Likely cause                                                                 |
|-----------------------------------|------------------------------------------------------------------------------|
| `pending` (no report yet)         | Snapshot still uploading or Lambda queued — wait 10–15 min                   |
| `failed`, "Branch not found"      | `snapshots/<algo-id>` push didn't land. Verify with `git ls-remote origin`   |
| `failed`, "Algorithm import error"| Syntax error or missing dep. Check `requirements.txt`; reproduce locally     |
| `failed`, "Algo not registered"   | Missing entry in `execution_algos/__init__.py → _EXEC_ALGORITHM_FACTORIES`   |
| `timeout` after 15 min            | Algorithm too slow on test window. Profile locally before resubmitting       |
| Report missing entirely           | S3 upload failed. Check the Actions run for the snapshot                     |

## 8. Train vs test discipline

`config.yaml → data_window` defines the boundary:

| Window | Dates (config-driven)        | Where it runs           |
|--------|------------------------------|-------------------------|
| Train  | `data_window.train`          | Local — `run_backtest()`|
| Test   | `data_window.test`           | Lambda — this skill     |

Honesty rules (`OBJECTIVE.md §8`) require reporting OOS metrics raw, even
when they regress vs train. A train pass plus a test regression is a
legitimate research outcome — log it in `program_database.json` and
`NOTES.md` rather than re-running until you get a favorable test draw.

The hard boundary in the `analysis` skill (no EDA on test dates) exists for
the same reason: the Lambda's report is only meaningful if test data was
genuinely held out during design.

## 9. Retention

Evaluation reports follow the same 30-day S3 lifecycle as snapshots
(see the `snapshot` skill §7). The durable record is the `performance_oos`
block you copy into `results/backtest-results.json` and commit alongside
the algorithm.
