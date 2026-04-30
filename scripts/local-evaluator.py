#!/usr/bin/env python3

"""
Local Execution Algorithm Evaluator

This script evaluates execution algorithms locally using the same code/output/formatting
as the Lambda function, without incurring AWS costs. Use this for debugging and development.

Workflow:
1. If 2-3 days of in-sample data exists locally, use it (skip download)
2. Otherwise, download 2-3 random days from S3 in-sample prefix
3. Run backtests using the local execution algorithm
4. Output metrics in Lambda-compatible format (JSON)
5. Save results to local disk

Usage:
    python3 scripts/08-local-evaluator.py <algorithm_name> [num_days]

Examples:
    python3 scripts/08-local-evaluator.py simple                  # Test "simple" algo, 2-3 days
    python3 scripts/08-local-evaluator.py my_algo 3               # Test "my_algo", exactly 3 days

Environment Variables (optional):
    GITHUB_REPO              GitHub repo (default: tonyhieu/agentic-trading-system)
    GITHUB_TOKEN            GitHub token for private repos
    S3_BUCKET_NAME          S3 bucket name (required if downloading)
    AWS_REGION              AWS region (default: us-east-2)
    LOCAL_CACHE_DIR         Cache directory for downloaded data (default: ./local-cache)

Requirements:
    - boto3
    - requests
    - nautilus-trader
    - pandas, numpy, zstandard
"""

import os
import sys
import json
import shutil
import tempfile
import traceback
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Configuration
GITHUB_REPO = os.environ.get("GITHUB_REPO", "tonyhieu/agentic-trading-system")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
S3_BUCKET = os.environ.get("S3_BUCKET_NAME", "agentic-trading-snapshots-uchicago-spring-2026")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-2")
LOCAL_CACHE_DIR = os.environ.get("LOCAL_CACHE_DIR", str(REPO_ROOT / "local-cache"))
SYMBOL = "MESM6"

# Create cache directory
Path(LOCAL_CACHE_DIR).mkdir(parents=True, exist_ok=True)

# In-sample dates (before March 30, 2026)
IN_SAMPLE_DATES = [
    "20260323", "20260324", "20260325", "20260326", "20260327",
    "20260328", "20260329",
]

# Colors for output
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
BLUE = "\033[0;34m"
NC = "\033[0m"


def log_info(msg: str):
    print(f"{BLUE}[INFO]{NC} {msg}")


def log_success(msg: str):
    print(f"{GREEN}[✓]{NC} {msg}")


def log_warning(msg: str):
    print(f"{YELLOW}[⚠]{NC} {msg}")


def log_error(msg: str):
    print(f"{RED}[✗]{NC} {msg}")


def find_local_data(num_days: int) -> Optional[List[str]]:
    """Check if we have cached in-sample data locally. Returns list of available dates."""
    cache_path = Path(LOCAL_CACHE_DIR) / "in-sample"
    if not cache_path.exists():
        return None

    available_dates = []
    for date in IN_SAMPLE_DATES:
        data_file = cache_path / f"{date}_{SYMBOL}.zst"
        if data_file.exists():
            available_dates.append(date)

    if len(available_dates) >= num_days:
        log_success(f"Found {len(available_dates)} cached in-sample data files")
        return available_dates[:num_days]

    return None


def download_in_sample_data(num_days: int) -> List[str]:
    """Download 2-3 random in-sample days from S3."""
    import boto3

    log_info(f"Downloading {num_days} in-sample data files from S3...")

    try:
        s3_client = boto3.client("s3", region_name=AWS_REGION)
    except Exception as e:
        log_error(f"Failed to initialize S3 client: {e}")
        log_error("Make sure AWS credentials are configured (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)")
        raise

    cache_path = Path(LOCAL_CACHE_DIR) / "in-sample"
    cache_path.mkdir(parents=True, exist_ok=True)

    downloaded_dates = []
    for date in IN_SAMPLE_DATES[:num_days]:
        try:
            s3_key = f"datasets/glbx-mdp3-market-data/v1.0.0/in-sample/{date}_{SYMBOL}.zst"
            local_file = cache_path / f"{date}_{SYMBOL}.zst"

            log_info(f"  Downloading {date}...")
            s3_client.download_file(S3_BUCKET, s3_key, str(local_file))
            downloaded_dates.append(date)
            log_success(f"    Downloaded {date}")

        except Exception as e:
            log_warning(f"  Failed to download {date}: {e}")
            continue

    if not downloaded_dates:
        log_error("No in-sample data could be downloaded")
        raise RuntimeError("Unable to download in-sample data from S3")

    return downloaded_dates


def clone_and_checkout_algorithm(algorithm_name: str) -> str:
    """Download GitHub repo contents from snapshots/{algorithm_name} branch using REST API."""
    log_info(f"Downloading algorithm from snapshots/{algorithm_name}...")

    try:
        import requests
        import zipfile
        import io
    except ImportError:
        log_error("Missing required packages: requests, zipfile")
        sys.exit(1)

    work_dir = tempfile.mkdtemp()

    try:
        # Use GitHub REST API to download branch as ZIP
        owner, repo = GITHUB_REPO.split("/")
        branch = f"snapshots/{algorithm_name}"
        api_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip"

        # Download with authentication if available
        headers = {}
        if GITHUB_TOKEN:
            headers["Authorization"] = f"token {GITHUB_TOKEN}"

        log_info(f"  Fetching {api_url}...")
        response = requests.get(api_url, headers=headers, timeout=60)
        response.raise_for_status()

        # Extract ZIP contents
        with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref:
            zip_ref.extractall(work_dir)

        # GitHub's ZIP has a top-level directory - move contents up
        extracted_items = os.listdir(work_dir)
        if len(extracted_items) == 1 and os.path.isdir(os.path.join(work_dir, extracted_items[0])):
            subdir = os.path.join(work_dir, extracted_items[0])
            for item in os.listdir(subdir):
                shutil.move(os.path.join(subdir, item), os.path.join(work_dir, item))
            os.rmdir(subdir)

        log_success(f"Downloaded algorithm from snapshots/{algorithm_name}")
        return work_dir

    except Exception as e:
        log_error(f"Failed to download algorithm: {e}")
        shutil.rmtree(work_dir, ignore_errors=True)
        raise


def run_backtest_for_day(algorithm_dir: str, algorithm_name: str, date: str) -> Dict[str, Any]:
    """Run backtest for one day using the execution algorithm."""
    log_info(f"Running backtest for {date}...")

    try:
        from backtest_engine.backtest_low_level import run_backtest

        # Add algorithm dir to Python path
        sys.path.insert(0, algorithm_dir)

        # Set up environment for data loading
        os.environ["DATA_CACHE_DIR"] = LOCAL_CACHE_DIR
        os.environ["S3_BUCKET_NAME"] = S3_BUCKET
        os.environ["AWS_REGION"] = AWS_REGION

        # Run backtest
        engine = run_backtest(
            strategy_name="ema_cross",
            execution_algorithm_name=algorithm_name,
            strategy_kwargs={"instrument_id": f"{SYMBOL}.GLBX"},
            execution_algorithm_kwargs={"exec_id": f"EVAL-{algorithm_name}"},
            date=date,
            symbol=SYMBOL,
        )

        # Extract results
        account_report = engine.trader.generate_account_report(engine.venue)
        orders_report = engine.trader.generate_orders_report()
        fills_report = engine.trader.generate_order_fills_report()

        return {
            "date": date,
            "account_report": account_report,
            "orders_report": orders_report,
            "fills_report": fills_report,
            "duration_seconds": 86400,
        }

    except Exception as e:
        log_error(f"Backtest failed for {date}: {e}")
        traceback.print_exc()
        raise


def calculate_slippage(fills: List[Dict]) -> float:
    """Calculate average slippage in basis points."""
    if not fills:
        return 0.0

    slippages = []
    for fill in fills:
        reference_price = fill.get("limit_price", fill.get("avg_price", 0))
        executed_price = fill.get("avg_price", 0)

        if reference_price > 0:
            slippage_bps = (executed_price - reference_price) / reference_price * 10000
            slippages.append(slippage_bps)

    return sum(slippages) / len(slippages) if slippages else 0.0


class ExecutionMetrics:
    """Metrics aggregation - matches Lambda function format."""

    def __init__(self):
        self.metrics = {
            "slippage_bps": [],
            "execution_time_ms": [],
            "fill_accuracy_pct": [],
            "latency_ms": [],
            "cost_bps": [],
            "orders_per_second": [],
            "execution_time_variance_ms": [],
            "peak_latency_ms": [],
        }

    def add_day_metrics(self, day_results: Dict[str, Any]):
        """Extract metrics from one day's backtest results."""
        try:
            account_report = day_results.get("account_report", {})
            orders_report = day_results.get("orders_report", {})
            fills_report = day_results.get("fills_report", {})

            # Slippage
            fills = fills_report.get("fills", [])
            if fills:
                slippage = calculate_slippage(fills)
                self.metrics["slippage_bps"].append(slippage)

            # Execution time
            if fills:
                exec_times = [
                    f.get("time_to_fill_ms", 0)
                    for f in fills
                    if f.get("time_to_fill_ms")
                ]
                if exec_times:
                    self.metrics["execution_time_ms"].append(
                        sum(exec_times) / len(exec_times)
                    )

            # Fill accuracy
            if orders_report.get("total_orders", 0) > 0:
                accuracy = 100.0 * len(fills) / orders_report.get("total_orders", 1)
                self.metrics["fill_accuracy_pct"].append(min(100.0, accuracy))

            # Latency (estimated from timestamp diffs)
            latencies = []
            for fill in fills:
                if "latency_ms" in fill:
                    latencies.append(fill["latency_ms"])
            if latencies:
                self.metrics["latency_ms"].append(sum(latencies) / len(latencies))

            # Cost in basis points
            total_cost = account_report.get("total_fees", 0)
            starting_balance = 1_000_000.0  # From backtest_low_level.py
            cost_bps = (total_cost / starting_balance) * 10000
            self.metrics["cost_bps"].append(cost_bps)

            # Orders per second
            if day_results.get("duration_seconds", 0) > 0:
                orders_per_sec = orders_report.get("total_orders", 0) / max(
                    day_results.get("duration_seconds", 1), 1
                )
                self.metrics["orders_per_second"].append(orders_per_sec)

            # Execution time variance
            if fills:
                exec_times = [
                    f.get("time_to_fill_ms", 0)
                    for f in fills
                    if f.get("time_to_fill_ms")
                ]
                if len(exec_times) > 1:
                    mean = sum(exec_times) / len(exec_times)
                    variance = sum((x - mean) ** 2 for x in exec_times) / len(
                        exec_times
                    )
                    self.metrics["execution_time_variance_ms"].append(variance ** 0.5)

            # Peak latency
            if fills:
                peak_latency = max(
                    (f.get("latency_ms", 0) for f in fills), default=0
                )
                self.metrics["peak_latency_ms"].append(peak_latency)

        except Exception as e:
            log_warning(f"Error extracting metrics: {e}")

    def aggregate(self) -> Dict[str, Any]:
        """Aggregate metrics across all days - matches Lambda format."""
        aggregated = {}
        for metric_name, values in self.metrics.items():
            if values:
                aggregated[metric_name] = {
                    "mean": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                    "count": len(values),
                }
            else:
                aggregated[metric_name] = {
                    "mean": 0.0,
                    "min": 0.0,
                    "max": 0.0,
                    "count": 0,
                }
        return aggregated


def save_evaluation_report(
    algorithm_name: str, metrics: Dict, execution_dates: List[str]
) -> str:
    """Save evaluation report to local disk."""
    report = {
        "algorithm_name": algorithm_name,
        "evaluation_timestamp": datetime.utcnow().isoformat(),
        "evaluation_type": "local_debug",
        "metrics": metrics,
        "in_sample_period": {
            "dates": execution_dates,
            "duration_days": len(execution_dates),
        },
    }

    # Create reports directory
    reports_dir = Path(LOCAL_CACHE_DIR) / "evaluation-reports" / algorithm_name
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Save JSON report
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    report_file = reports_dir / f"{timestamp}_evaluation_report.json"

    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)

    return str(report_file)


def print_results_summary(metrics: Dict[str, Any], algorithm_name: str):
    """Print a formatted summary of evaluation metrics."""
    print("\n" + "=" * 70)
    print(f"EVALUATION RESULTS: {algorithm_name}")
    print("=" * 70)

    for metric_name, values in metrics.items():
        print(f"\n{metric_name}:")
        if values.get("count", 0) > 0:
            print(f"  Mean:  {values.get('mean', 0):.4f}")
            print(f"  Min:   {values.get('min', 0):.4f}")
            print(f"  Max:   {values.get('max', 0):.4f}")
            print(f"  Days:  {values.get('count', 0)}")
        else:
            print(f"  (No data)")

    print("\n" + "=" * 70)


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <algorithm_name> [num_days]")
        print(f"Example: {sys.argv[0]} simple 2")
        sys.exit(1)

    algorithm_name = sys.argv[1]
    num_days = int(sys.argv[2]) if len(sys.argv) > 2 else 2

    if num_days < 1 or num_days > len(IN_SAMPLE_DATES):
        log_error(f"num_days must be between 1 and {len(IN_SAMPLE_DATES)}")
        sys.exit(1)

    log_info("=" * 70)
    log_info("Local Execution Algorithm Evaluator")
    log_info("=" * 70)
    log_info(f"Algorithm: {algorithm_name}")
    log_info(f"Days: {num_days}")
    log_info(f"Data type: In-sample")
    log_info(f"Symbol: {SYMBOL}")

    try:
        # Check for local data or download
        local_dates = find_local_data(num_days)
        if local_dates:
            dates_to_eval = local_dates
        else:
            log_info("No local data found, downloading from S3...")
            dates_to_eval = download_in_sample_data(num_days)

        # Download algorithm
        algorithm_dir = clone_and_checkout_algorithm(algorithm_name)

        try:
            # Run backtests
            metrics = ExecutionMetrics()
            for date in dates_to_eval:
                try:
                    day_results = run_backtest_for_day(
                        algorithm_dir, algorithm_name, date
                    )
                    metrics.add_day_metrics(day_results)
                except Exception as e:
                    log_warning(f"Skipping {date}: {e}")
                    continue

            # Aggregate and save
            aggregated_metrics = metrics.aggregate()
            report_path = save_evaluation_report(
                algorithm_name, aggregated_metrics, dates_to_eval
            )

            # Print results
            print_results_summary(aggregated_metrics, algorithm_name)

            log_success(f"Evaluation complete")
            log_success(f"Report saved to: {report_path}")

            # Print JSON for easy parsing
            print("\nJSON Output (for integration):")
            print(
                json.dumps(
                    {
                        "status": "success",
                        "algorithm_name": algorithm_name,
                        "report_path": report_path,
                        "metrics": aggregated_metrics,
                        "dates_evaluated": dates_to_eval,
                    },
                    indent=2,
                )
            )

        finally:
            # Cleanup algorithm directory
            shutil.rmtree(algorithm_dir, ignore_errors=True)

    except Exception as e:
        log_error(f"Evaluation failed: {e}")
        traceback.print_exc()
        print(
            json.dumps(
                {
                    "status": "error",
                    "algorithm_name": algorithm_name,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                },
                indent=2,
            )
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
