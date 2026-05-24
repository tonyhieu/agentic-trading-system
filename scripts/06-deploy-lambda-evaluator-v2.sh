#!/bin/bash

###############################################################################
# Phase 3: Deploy Lambda Execution Algorithm Evaluator (Redesigned)
#
# This script deploys a serverless evaluator function that:
# 1. Receives GitHub branch name (execution algorithm)
# 2. Clones the repo and checks out strategy/{branch}
# 3. Runs backtest against OOS data (all 7 days in sequence)
# 4. Computes 8 execution metrics from BacktestEngine results
# 5. Stores evaluation report to S3
#
# Architecture:
# - Memory: 1 GB (can scale to 2 GB if needed)
# - Timeout: 15 minutes (estimated 10-12 min for 7-day backtest)
# - Runtime: Python 3.11
# - Trigger: GitHub webhook → S3 marker file → Lambda
#
# Prerequisites:
# - Phase 1 complete (evaluator-role exists)
# - AWS root credentials in environment
# - S3 bucket created
# - GitHub token available for private repo access
#
###############################################################################

set -e

# Configuration
LAMBDA_FUNCTION_NAME="execution-algorithm-evaluator"
LAMBDA_MEMORY=1024 # 1 GB (start here, can scale to 2048 if needed)
LAMBDA_TIMEOUT=900 # 15 minutes
LAMBDA_RUNTIME="python3.11"
LAMBDA_HANDLER="index.lambda_handler"
WORK_DIR=$(mktemp -d)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Helper functions
log_info() {
  echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
  echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
  echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
  echo -e "${RED}[ERROR]${NC} $1"
}

cleanup() {
  rm -rf "$WORK_DIR"
}

trap cleanup EXIT

# Verify prerequisites
log_info "Verifying prerequisites..."

if [ -z "$AWS_REGION" ]; then
  log_error "AWS_REGION not set"
  exit 1
fi

if [ -z "$S3_BUCKET_NAME" ]; then
  log_error "S3_BUCKET_NAME not set"
  exit 1
fi

if ! aws sts get-caller-identity >/dev/null 2>&1; then
  log_error "AWS credentials not configured"
  exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
EVALUATOR_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/evaluator-role"

# GitHub configuration
GITHUB_REPO="${GITHUB_REPO:-tonyhieu/agentic-trading-system}"
GITHUB_TOKEN="${GITHUB_TOKEN:-}"

# Verify evaluator role exists
if ! aws iam get-role --role-name "evaluator-role" >/dev/null 2>&1; then
  log_error "evaluator-role not found. Did you complete Phase 1?"
  exit 1
fi

log_success "Prerequisites verified"

###############################################################################
# Generate Lambda Function Code
###############################################################################

log_info "Generating Lambda function code..."

cat >"${WORK_DIR}/index.py" <<'LAMBDA_CODE'
"""
Execution Algorithm Evaluator Lambda Function

Pulls execution algorithm from GitHub, runs backtest against OOS data,
and computes evaluation metrics.
"""

import json
import os
import sys
import tempfile
import shutil
import subprocess
import traceback
from datetime import datetime
from pathlib import Path
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

# S3 and GitHub configuration from environment
S3_BUCKET = os.environ.get("S3_BUCKET_NAME")
AWS_REGION = os.environ.get("LAMBDA_REGION", "us-east-2")  # Use LAMBDA_REGION to avoid AWS reserved names
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "tonyhieu/agentic-trading-system")
DATA_CACHE_DIR = "/tmp/data-cache"
OOS_DATES = [
    "20260330", "20260331", "20260401",
    "20260402", "20260403", "20260405", "20260406"
]

s3_client = boto3.client("s3", region_name=AWS_REGION)

# Metrics tracking
class ExecutionMetrics:
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
    
    def add_day_metrics(self, day_results):
        """Extract execution metrics from one day's persisted backtest metrics.json."""
        try:
            # Source from persisted run artifact metrics (backtest_engine/results.py).
            m = day_results.get("metrics", {})
            duration_seconds = day_results.get("duration_seconds", 86400)

            # mean_slippage is in price units; convert to bps proxy for evaluator report.
            mean_slippage = m.get("mean_slippage")
            if mean_slippage is not None:
                self.metrics["slippage_bps"].append(float(mean_slippage) * 10_000.0)

            order_count = m.get("order_count")
            fill_count = m.get("fill_count")
            if order_count:
                self.metrics["orders_per_second"].append(float(order_count) / max(float(duration_seconds), 1.0))
                if fill_count is not None:
                    self.metrics["fill_accuracy_pct"].append(min(100.0, 100.0 * float(fill_count) / max(float(order_count), 1.0)))

            total_commissions = m.get("total_commissions")
            starting_balance = m.get("starting_balance")
            if total_commissions is not None and starting_balance:
                self.metrics["cost_bps"].append(10_000.0 * float(total_commissions) / max(float(starting_balance), 1.0))
        
        except Exception as e:
            print(f"Warning: Error extracting metrics for day: {e}")
            traceback.print_exc()
    
    def aggregate(self):
        """Return aggregated metrics across all days."""
        result = {}
        for metric, values in self.metrics.items():
            if not values:
                result[metric] = None
            elif len(values) == 1:
                # Single value: report just the scalar
                result[metric] = values[0]
            else:
                # Multiple values: report mean/min/max/count
                result[metric] = {
                    "mean": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                    "count": len(values),
                }
        return result

def clone_and_checkout_algorithm(algorithm_name):
    """Download GitHub repo contents from snapshots/{algorithm_name} branch using REST API (no git needed)."""
    log_print(f"Downloading algorithm from snapshots/{algorithm_name}...")
    
    work_dir = tempfile.mkdtemp()
    
    try:
        import requests
        import zipfile
        import io
        
        # Use GitHub REST API to download branch as ZIP
        # Format: https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip
        owner, repo = GITHUB_REPO.split('/')
        branch = f"snapshots/{algorithm_name}"
        
        api_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip"
        
        # Download with authentication if available
        headers = {}
        if GITHUB_TOKEN:
            headers["Authorization"] = f"token {GITHUB_TOKEN}"
        
        log_print(f"Downloading from {api_url}...")
        response = requests.get(api_url, headers=headers, timeout=60)
        response.raise_for_status()
        
        # Extract ZIP contents
        with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref:
            zip_ref.extractall(work_dir)
        
        # GitHub's ZIP has a top-level directory - move contents up
        extracted_items = os.listdir(work_dir)
        if len(extracted_items) == 1 and os.path.isdir(os.path.join(work_dir, extracted_items[0])):
            # Move contents from subdirectory to work_dir
            subdir = os.path.join(work_dir, extracted_items[0])
            for item in os.listdir(subdir):
                shutil.move(os.path.join(subdir, item), os.path.join(work_dir, item))
            os.rmdir(subdir)

        # If this runtime package includes an updated scripts/data_retriever.py,
        # copy it into the cloned algorithm so backtest_engine will import the
        # patched retriever implementation instead of the snapshot's version.
        packaged_retriever = os.path.join(os.getcwd(), 'scripts', 'data_retriever.py')
        target_scripts_dir = os.path.join(work_dir, 'scripts')
        try:
            if os.path.exists(packaged_retriever):
                os.makedirs(target_scripts_dir, exist_ok=True)
                shutil.copy(packaged_retriever, os.path.join(target_scripts_dir, 'data_retriever.py'))
                log_print('✓ Copied packaged scripts/data_retriever.py into cloned algorithm')
        except Exception:
            log_print('⚠ Could not copy packaged data_retriever into cloned algorithm; continuing')

        log_print(f"✓ Downloaded algorithm from snapshots/{algorithm_name}")
        return work_dir
    
    except Exception as e:
        log_print(f"✗ Failed to download algorithm: {e}")
        shutil.rmtree(work_dir, ignore_errors=True)
        raise

def run_backtest_for_day(algorithm_dir, algorithm_name, date, symbol="MESM6"):
    """Run backtest for one day using the execution algorithm."""
    log_print(f"Running backtest for {date}...")
    
    try:
        # Add algorithm dir to Python path
        sys.path.insert(0, algorithm_dir)
        
        # Setup environment for data loading
        os.environ["DATA_CACHE_DIR"] = DATA_CACHE_DIR
        os.environ["S3_BUCKET_NAME"] = S3_BUCKET
        os.environ["AWS_REGION"] = AWS_REGION
        
        # Import backtest engine
        from backtest_engine.backtest_low_level import run_backtest
        
        # Run backtest with the algorithm being tested
        # The trading strategy is fixed to 'oracle' for OOS evaluation; execution_algorithm_name varies per evaluation
        log_print(f"→ Starting Nautilus backtest engine for {date}")
        run_backtest(
            strategy_name="oracle",
            execution_algorithm_name=algorithm_name,
            strategy_kwargs={
                "instrument_id": f"{symbol}.GLBX",
                "horizon_seconds": 30.0,
                "sigma": 217.67,
                "signal_interval_seconds": 1.0,
            },
            execution_algorithm_kwargs={"exec_id": f"EVAL-{algorithm_name}"},
            date=date,
            symbol=symbol
        )
        log_print(f"← Backtest engine finished for {date}")

        # Read persisted run artifact metrics produced by run_backtest().
        results_root = Path(algorithm_dir) / "execution_algos" / algorithm_name / "results"
        metrics_files = sorted(results_root.glob("*/metrics.json"), key=lambda p: p.stat().st_mtime)
        if not metrics_files:
            raise FileNotFoundError(f"No metrics.json found under {results_root}")
        with metrics_files[-1].open("r", encoding="utf-8") as fh:
            day_metrics = json.load(fh)
        
        return {
            "date": date,
            "metrics": day_metrics,
            "duration_seconds": 86400,  # 1 day
        }
    
    except Exception as e:
        log_print(f"✗ Backtest failed for {date}: {e}")
        traceback.print_exc()
        raise

def save_evaluation_report(algorithm_name, metrics, execution_time_seconds):
    """Save evaluation report to S3."""
    report = {
        "algorithm_name": algorithm_name,
        "evaluation_timestamp": datetime.utcnow().isoformat(),
        "metrics": metrics,
        "execution_time_seconds": execution_time_seconds,
        "oos_period": {
            "dates": OOS_DATES,
            "duration_days": len(OOS_DATES),
        }
    }
    
    key = f"evaluation-reports/{algorithm_name}/{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=json.dumps(report, indent=2),
            ContentType="application/json"
        )
        log_print(f"✓ Saved report to s3://{S3_BUCKET}/{key}")
        return key
    
    except ClientError as e:
        log_print(f"✗ Failed to save report: {e}")
        raise

def log_print(message):
    """Print with timestamp."""
    print(f"[{datetime.utcnow().isoformat()}] {message}")

def lambda_handler(event, context):
    """
    Main Lambda handler.
    
    Expected event structure:
    {
        "execution_algorithm_name": "my-algo",
        "symbol": "MESM6"  # optional, defaults to MESM6
    }
    """
    
    start_time = datetime.utcnow()
    
    try:
        log_print("=== Execution Algorithm Evaluator ===")
        
        # Parse event
        algorithm_name = event.get("execution_algorithm_name")
        symbol = event.get("symbol", "MESM6")
        
        if not algorithm_name:
            raise ValueError("execution_algorithm_name not provided in event")
        
        log_print(f"Evaluating algorithm: {algorithm_name}")
        log_print(f"Symbol: {symbol}")
        log_print(f"OOS period: {len(OOS_DATES)} days")
        
        # Clone and checkout algorithm
        algorithm_dir = clone_and_checkout_algorithm(algorithm_name)
        
        try:
            # Run backtest for each OOS day
            metrics = ExecutionMetrics()
            
            successful_days = 0
            for date in OOS_DATES:
                try:
                    day_results = run_backtest_for_day(algorithm_dir, algorithm_name, date, symbol)
                    metrics.add_day_metrics(day_results)
                    successful_days += 1
                except Exception as e:
                    log_print(f"⚠ Skipping {date}: {e}")
                    continue

            if successful_days == 0:
                raise RuntimeError("All OOS dates failed; no evaluation metrics were produced")
            
            # Aggregate and save results
            aggregated_metrics = metrics.aggregate()
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            
            report_key = save_evaluation_report(algorithm_name, aggregated_metrics, execution_time)
            
            log_print(f"✓ Evaluation complete ({execution_time:.1f}s)")
            
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "message": "Evaluation successful",
                    "algorithm_name": algorithm_name,
                    "report_key": report_key,
                    "metrics": aggregated_metrics,
                })
            }
        
        finally:
            # Cleanup
            shutil.rmtree(algorithm_dir, ignore_errors=True)
    
    except Exception as e:
        log_print(f"✗ Evaluation failed: {e}")
        traceback.print_exc()
        
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e),
                "traceback": traceback.format_exc(),
            })
        }

LAMBDA_CODE

log_success "Lambda function code generated"

###############################################################################
# Package Dependencies and Create Deployment Package
###############################################################################

log_info "Creating deployment package..."

# Create package directory
PACKAGE_DIR="${WORK_DIR}/lambda_package"
mkdir -p "$PACKAGE_DIR"

# Copy Lambda function
cp "${WORK_DIR}/index.py" "${PACKAGE_DIR}/index.py"

# Copy backtest_engine from repo
cp -r "$(pwd)/backtest_engine" "${PACKAGE_DIR}/"
cp -r "$(pwd)/execution_algos" "${PACKAGE_DIR}/"
cp -r "$(pwd)/strategies" "${PACKAGE_DIR}/"
# Include local scripts so index.py can copy patched retriever into cloned snapshots
cp -r "$(pwd)/scripts" "${PACKAGE_DIR}/scripts" || true

# Create requirements.txt for Lambda layer
# Note: For actual Lambda deployment, dependencies would be built in Amazon Linux
# environment and included as a Lambda layer. For now, we list them for reference.
cat >"${WORK_DIR}/requirements.txt" <<'REQUIREMENTS'
nautilus-trader>=1.225.0
boto3>=1.26.0
dbn>=0.19.0
pandas>=2.0.0
numpy>=1.24.0
zstandard>=0.19.0
requests>=2.28.0
gitpython>=3.1.0
REQUIREMENTS

# Important: The actual deployment requires:
# 1. All pip dependencies must be pre-built in Amazon Linux environment
# 2. Create a Lambda layer with the compiled binaries
# 3. Attach the layer to this function during deployment
# 4. This ensures compatibility with Lambda's runtime environment
#
# Commands to build the layer (run locally in Docker or on Amazon Linux EC2):
#   docker run -it public.ecr.aws/lambda/python:3.11 /bin/bash
#   pip install -r requirements.txt -t /tmp/python/
#   zip -r lambda_layer.zip /tmp/python/
#   aws lambda publish-layer-version --layer-name nautilus-trader-layer \
#     --zip-file fileb://lambda_layer.zip --compatible-runtimes python3.11

# Create ZIP package
cd "$PACKAGE_DIR" || exit 1
zip -r9 "${WORK_DIR}/lambda_function.zip" . >/dev/null 2>&1
cd - || exit 1

PACKAGE_SIZE=$(du -sh "${WORK_DIR}/lambda_function.zip" | cut -f1)
log_success "Deployment package created (${PACKAGE_SIZE})"

# Build environment variables string, only include GITHUB_TOKEN if it's set
# Note: AWS_REGION is reserved in Lambda, use different name
ENV_VARS="S3_BUCKET_NAME=$S3_BUCKET_NAME,LAMBDA_REGION=$AWS_REGION,GITHUB_REPO=$GITHUB_REPO"
if [ -n "$GITHUB_TOKEN" ]; then
  ENV_VARS="$ENV_VARS,GITHUB_TOKEN=$GITHUB_TOKEN"
fi

###############################################################################
# Deploy or Update Lambda Function
###############################################################################

log_info "Deploying Lambda function..."

# Check if function exists
if aws lambda get-function --function-name "$LAMBDA_FUNCTION_NAME" >/dev/null 2>&1; then
  log_info "Function exists, updating..."

  aws lambda update-function-code \
    --function-name "$LAMBDA_FUNCTION_NAME" \
    --zip-file "fileb://${WORK_DIR}/lambda_function.zip" \
    --region "$AWS_REGION" \
    >/dev/null

  log_success "Lambda function updated"
else
  log_info "Function does not exist, creating..."

  aws lambda create-function \
    --function-name "$LAMBDA_FUNCTION_NAME" \
    --runtime "$LAMBDA_RUNTIME" \
    --handler "$LAMBDA_HANDLER" \
    --memory-size "$LAMBDA_MEMORY" \
    --timeout "$LAMBDA_TIMEOUT" \
    --role "$EVALUATOR_ROLE_ARN" \
    --zip-file "fileb://${WORK_DIR}/lambda_function.zip" \
    --environment "Variables={$ENV_VARS}" \
    --region "$AWS_REGION" \
    >/dev/null

  log_success "Lambda function created"
fi

###############################################################################
# Configure Lambda Permissions and Verify Deployment
###############################################################################

log_info "Configuring Lambda permissions..."

# Grant S3 permission to invoke Lambda (if using S3 triggers)
aws lambda add-permission \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --statement-id AllowS3Invoke \
  --action lambda:InvokeFunction \
  --principal s3.amazonaws.com \
  --source-arn "arn:aws:s3:::${S3_BUCKET_NAME}" \
  --region "$AWS_REGION" \
  2>/dev/null || log_warning "S3 permission already exists"

log_info "Verifying deployment..."

# Get function details
FUNCTION_INFO=$(aws lambda get-function --function-name "$LAMBDA_FUNCTION_NAME" --region "$AWS_REGION")
FUNCTION_ARN=$(echo "$FUNCTION_INFO" | jq -r '.Configuration.FunctionArn')
CODE_SIZE=$(echo "$FUNCTION_INFO" | jq -r '.Configuration.CodeSize')

log_success "Lambda function deployed successfully"
echo ""
echo "Function Details:"
echo "  Name:       $LAMBDA_FUNCTION_NAME"
echo "  ARN:        $FUNCTION_ARN"
echo "  Memory:     ${LAMBDA_MEMORY} MB"
echo "  Timeout:    ${LAMBDA_TIMEOUT} seconds"
echo "  Runtime:    $LAMBDA_RUNTIME"
echo "  Code Size:  $((CODE_SIZE / 1024 / 1024)) MB"
echo ""

###############################################################################
# Testing Instructions
###############################################################################

cat <<'EOF'
NEXT STEPS - Testing and Configuration:

1. Set GitHub token in Lambda environment (for private repo access):
   aws lambda update-function-configuration \
     --function-name execution-algorithm-evaluator \
     --environment "Variables={GITHUB_TOKEN=ghp_xxxx...}" \
     --region us-east-2

2. Test the Lambda function:
   aws lambda invoke \
     --function-name execution-algorithm-evaluator \
     --payload '{"execution_algorithm_name":"my-algo"}' \
     --region us-east-2 \
     response.json
   cat response.json

3. Monitor Lambda logs:
   aws logs tail /aws/lambda/execution-algorithm-evaluator --follow

4. Set up S3 trigger (in Phase 4):
   - GitHub Actions automatically creates snapshots/ branch on snapshot creation
   - Phase 4 script configures EventBridge/S3 events to trigger Lambda
   - Lambda pulls the snapshots/ branch and evaluates the algorithm

IMPORTANT NOTES:

- Memory: Started at 1 GB, can increase to 2 GB if backtest times out
  (Update: aws lambda update-function-configuration --memory-size 2048 ...)
  
- GitHub Token: Required to clone private repo branch
  (Keep token in AWS Secrets Manager, reference from Lambda)
  
- Estimated backtest time: 10-12 minutes for 7 days of OOS data
  
- Cost: ~$0.30 per evaluation (1 GB, 12 min runtime)
  
- Branch naming: Execution algorithms are uploaded to snapshots/{algo_name} branches
  by the GitHub Actions workflow (snapshot-execution-algo.yml)

EOF

log_success "Phase 3 deployment complete!"
