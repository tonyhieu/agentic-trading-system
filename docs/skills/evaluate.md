# Skill: Cloud Evaluation (Lambda)

How to retrieve out-of-sample evaluation results after snapshotting an
algorithm. The Lambda evaluator is the *test-set* counterpart to local
backtests — local runs use the train window in `config.yaml → data_window.train`;
the Lambda runs the held-out test window in `config.yaml → data_window.test`.

## 1. Trigger model

You do not invoke the evaluator directly. The flow is:

1. Push to `snapshots/<algo-id>` (see `snapshot.md` §4).
2. The GitHub Actions workflow uploads the snapshot to
   `s3://$S3_BUCKET_NAME/execution_algos/<algo-id>/<timestamp>-<commit>/`.
3. An S3 event invokes the `execution-algorithm-evaluator` Lambda
   (region `us-east-2`).
4. Lambda runs the snapshotted algorithm against the test window in
   `config.yaml → data_window.test` and writes a report back to S3.

A successful snapshot push is the trigger. If the snapshot upload fails, no
evaluation runs.

## 2. Cost discipline (read before triggering)

Each evaluation costs roughly **$0.30** (1 GB Lambda × ~12 minutes). The
research loop budget in `OBJECTIVE.md` is finite — treat cloud evaluations
as the gated, paid step that comes *after* train-window passes locally.

- Run the local backtest loop (`backtest.md` §7) against
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

## 5. Report shape (illustrative)

The report's exact field names are produced by the Lambda and may drift.
Treat the block below as a sketch — read the actual JSON before relying on
specific keys.

```json
{
  "algorithm_name": "<algo-id>",
  "evaluation_date": "2026-04-30T14:45:00Z",
  "backtest_period": { "start": "...", "end": "...", "days_oos": ... },
  "execution_metrics": {
    "slippage_bps":             ...,
    "execution_time_ms":        ...,
    "fill_accuracy_pct":        ...,
    "latency_ms":               ...,
    "cost_bps":                 ...,
    "orders_per_second":        ...,
    "execution_time_variance_ms": ...,
    "peak_latency_ms":          ...
  },
  "performance_summary": {
    "total_trades":         ...,
    "successful_fills":     ...,
    "failed_fills":         ...,
    "avg_profit_per_trade": ...,
    "total_pnl":            ...
  },
  "status": "completed",
  "errors": []
}
```

Map the report into your snapshot's `results/backtest-results.json`
(`snapshot.md` §3) under `period.test_dates` and a parallel
`performance_oos` block — do **not** overwrite the train-window
`performance` numbers. Both must remain auditable separately.

**Format note.** The Lambda envelope above (`execution_metrics` /
`performance_summary`) does not share field names with the local
`compute_metrics()` output (`backtest.md §5`) used for the `performance`
block. When you populate `performance_oos`, translate what's available:

| `performance` field (local) | Source in Lambda report |
|---|---|
| `realized_pnl`, `total_pnl` | `performance_summary.total_pnl` |
| `trade_count` | `performance_summary.total_trades` |
| `total_commissions` | derive from `execution_metrics.cost_bps × starting_balance / 10000` |
| `mean_slippage` (price units) | not directly available — record `execution_metrics.slippage_bps` separately |
| `sharpe_ratio`, `max_drawdown_pct`, `win_rate` | not present in Lambda report — leave as `null` in `performance_oos` |

Record raw values from the Lambda report. If a field is unavailable in
the OOS report, write `null` rather than estimating — the honesty rules
in `OBJECTIVE.md §8` require an honest gap, not a fabricated number.

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

The hard boundary in `analysis.md` §4 (no EDA on test dates) exists for the
same reason: the Lambda's report is only meaningful if test data was
genuinely held out during design.

## 9. Retention

Evaluation reports follow the same 30-day S3 lifecycle as snapshots
(`snapshot.md` §7). The durable record is the `performance_oos` block you
copy into `results/backtest-results.json` and commit alongside the
algorithm.
