#!/bin/bash

################################################################################
# Lambda Layer Deployment Script
#
# Automates the process of building and deploying the Python dependencies
# layer to AWS Lambda. Uses Docker to build in Amazon Linux environment.
#
# Usage:
#   ./deploy_lambda_layer.sh [layer-name] [region]
#
# Examples:
#   ./deploy_lambda_layer.sh                    # Uses defaults
#   ./deploy_lambda_layer.sh lambda-deps us-west-2
#
################################################################################

set -e

# Configuration
LAYER_NAME="${1:-lambda-core-dependencies}"
AWS_REGION="${2:-us-east-1}"
FUNCTION_NAME="execution-algorithm-evaluator"
LAMBDA_RUNTIME="${LAMBDA_RUNTIME:-python3.11}"
DOCKER_IMAGE="${DOCKER_IMAGE:-public.ecr.aws/lambda/python:3.11}"
NAUTILUS_TRADER_VERSION="${NAUTILUS_TRADER_VERSION:-1.219.0}"
LAYER_S3_BUCKET="${LAYER_S3_BUCKET:-agentic-trading-snapshots-uchicago-spring-2026}"
LAYER_S3_PREFIX="${LAYER_S3_PREFIX:-lambda-layers}"
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
  echo -e "${GREEN}[✓]${NC} $1"
}

log_error() {
  echo -e "${RED}[ERROR]${NC} $1"
}

log_warn() {
  echo -e "${YELLOW}[WARN]${NC} $1"
}

# Cleanup on exit
cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

# Verify prerequisites
log_info "Verifying prerequisites..."

if ! command -v docker &> /dev/null; then
  log_error "Docker not found. Please install Docker first."
  exit 1
fi

if ! command -v aws &> /dev/null; then
  log_error "AWS CLI not found. Please install AWS CLI first."
  exit 1
fi

if ! aws sts get-caller-identity >/dev/null 2>&1; then
  log_error "AWS credentials not configured"
  exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
log_success "AWS authenticated as account: $ACCOUNT_ID"

###############################################################################
# Build Lambda Layer in Docker
###############################################################################

log_info "Building Lambda layer in Docker..."
log_info "Working directory: $WORK_DIR"

docker run --rm --platform linux/amd64 --entrypoint /bin/bash \
  -v "$WORK_DIR:/workspace" \
  "$DOCKER_IMAGE" -c '
set -e
echo "[1/5] Installing system dependencies..."
if command -v yum >/dev/null 2>&1; then
  yum install -y -q git zip gcc gcc-c++ make clang rust cargo
elif command -v dnf >/dev/null 2>&1; then
  dnf install -y git zip gcc gcc-c++ make clang rust cargo
elif command -v microdnf >/dev/null 2>&1; then
  microdnf install -y git zip gcc gcc-c++ make clang rust cargo
fi

echo "[2/5] Creating Python package directory..."
mkdir -p /tmp/python

echo "[2.5/5] Writing dependency constraints..."
cat >/tmp/constraints.txt <<'CONSTRAINTS'
numpy==1.26.4
pandas==2.2.3
pyarrow==20.0.0
CONSTRAINTS

echo "[2.6/5] Upgrading pip and applying constraints to build deps..."
python -m pip install -q --upgrade pip
export PIP_CONSTRAINT=/tmp/constraints.txt
export PIP_BUILD_CONSTRAINT=/tmp/constraints.txt
export PARALLEL_BUILD=False
export CARGO_BUILD_JOBS=1
export PYO3_ONLY=True
export HIGH_PRECISION=False

echo "[3/5] Installing Python dependencies..."
pip install -q --constraint /tmp/constraints.txt \
  numpy==1.26.4 \
  pandas==2.2.3 \
  pyarrow==20.0.0 \
  nautilus-trader=='"$NAUTILUS_TRADER_VERSION"' \
  boto3==1.34.162 \
  requests==2.32.3 \
  gitpython==3.1.43 \
  zstandard==0.23.0 \
  python-dotenv>=1.0.0 \
  -t /tmp/python/

echo "[3.5/5] Pruning and stripping for layer size..."
find /tmp/python -type d -name "__pycache__" -prune -exec rm -rf {} +
find /tmp/python -type d -name "tests" -prune -exec rm -rf {} +
find /tmp/python -type f -name "*.pyc" -delete
find /tmp/python -type f -name "*.a" -delete
find /tmp/python -type f -name "*.so" -exec strip -s {} + || true

echo "[4/5] Installing zip utility..."
# Already installed above

echo "[5/5] Creating ZIP file..."
cd /tmp
zip -r9 -q /workspace/lambda_layer.zip python/

ls -lh /workspace/lambda_layer.zip
'

log_success "Lambda layer built successfully"
ls -lh "$WORK_DIR/lambda_layer.zip"

###############################################################################
# Publish to AWS Lambda
###############################################################################

log_info "Publishing layer to AWS Lambda..."
ZIP_SIZE_BYTES=$(wc -c <"$WORK_DIR/lambda_layer.zip")
MAX_DIRECT_UPLOAD_BYTES=70000000
if [ "$ZIP_SIZE_BYTES" -gt "$MAX_DIRECT_UPLOAD_BYTES" ]; then
  LAYER_S3_KEY="${LAYER_S3_PREFIX}/${LAYER_NAME}/$(date -u +%Y%m%dT%H%M%SZ)-nautilus-trader-${NAUTILUS_TRADER_VERSION}.zip"
  log_warn "Layer zip is too large for direct publish ($ZIP_SIZE_BYTES bytes). Uploading to s3://$LAYER_S3_BUCKET/$LAYER_S3_KEY"
  aws s3 cp "$WORK_DIR/lambda_layer.zip" "s3://$LAYER_S3_BUCKET/$LAYER_S3_KEY" --region "$AWS_REGION" >/dev/null
  LAYER_VERSION=$(aws lambda publish-layer-version \
    --layer-name "$LAYER_NAME" \
    --description "Core Python dependencies for algorithm evaluation (nautilus-trader ${NAUTILUS_TRADER_VERSION})" \
    --content S3Bucket="$LAYER_S3_BUCKET",S3Key="$LAYER_S3_KEY" \
    --compatible-runtimes "$LAMBDA_RUNTIME" \
    --region "$AWS_REGION" \
    --query 'Version' \
    --output text)
else
  LAYER_VERSION=$(aws lambda publish-layer-version \
    --layer-name "$LAYER_NAME" \
    --description "Core Python dependencies for algorithm evaluation (nautilus-trader ${NAUTILUS_TRADER_VERSION})" \
    --zip-file "fileb://$WORK_DIR/lambda_layer.zip" \
    --compatible-runtimes "$LAMBDA_RUNTIME" \
    --region "$AWS_REGION" \
    --query 'Version' \
    --output text)
fi

LAYER_ARN="arn:aws:lambda:$AWS_REGION:$ACCOUNT_ID:layer:$LAYER_NAME:$LAYER_VERSION"

log_success "Layer published: $LAYER_ARN"

###############################################################################
# Attach to Lambda Function
###############################################################################

log_info "Attaching layer to function: $FUNCTION_NAME"

aws lambda update-function-configuration \
  --function-name "$FUNCTION_NAME" \
  --runtime "$LAMBDA_RUNTIME" \
  --layers "$LAYER_ARN" \
  --region "$AWS_REGION" >/dev/null

log_success "Layer attached to $FUNCTION_NAME"

###############################################################################
# Verify Deployment
###############################################################################

log_info "Verifying configuration..."

LAYERS=$(aws lambda get-function-configuration \
  --function-name "$FUNCTION_NAME" \
  --region "$AWS_REGION" \
  --query 'Layers[*].Arn' \
  --output text)

log_success "Function layers: $LAYERS"

###############################################################################
# Summary
###############################################################################

echo ""
echo "════════════════════════════════════════════════════════════"
log_success "Lambda layer deployment complete!"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "Layer Information:"
echo "  Name:    $LAYER_NAME"
echo "  Version: $LAYER_VERSION"
echo "  ARN:     $LAYER_ARN"
echo ""
echo "Function: $FUNCTION_NAME (Region: $AWS_REGION)"
echo ""
echo "Next Steps:"
echo "  1. Test the Lambda function:"
echo "     aws lambda invoke --function-name $FUNCTION_NAME \\"
echo "       --payload '{\"execution_algorithm_name\":\"test\"}' \\"
echo "       --cli-binary-format raw-in-base64-out \\"
echo "       --region $AWS_REGION response.json"
echo ""
echo "  2. View CloudWatch logs:"
echo "     aws logs tail /aws/lambda/$FUNCTION_NAME --follow --region $AWS_REGION"
echo ""
