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
AWS_REGION="${2:-us-east-2}"
FUNCTION_NAME="execution-algorithm-evaluator"
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

docker run --rm --entrypoint /bin/bash \
  -v "$WORK_DIR:/workspace" \
  public.ecr.aws/lambda/python:3.11 -c '
set -e
echo "[1/5] Installing system dependencies..."
yum install -y -q git zip

echo "[2/5] Creating Python package directory..."
mkdir -p /tmp/python

echo "[3/5] Installing Python dependencies..."
pip install -q \
  boto3>=1.26.0 \
  requests>=2.28.0 \
  gitpython>=3.1.0 \
  zstandard>=0.19.0 \
  -t /tmp/python/

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

LAYER_VERSION=$(aws lambda publish-layer-version \
  --layer-name "$LAYER_NAME" \
  --description "Core Python dependencies for algorithm evaluation" \
  --zip-file "fileb://$WORK_DIR/lambda_layer.zip" \
  --compatible-runtimes python3.11 \
  --region "$AWS_REGION" \
  --query 'Version' \
  --output text)

LAYER_ARN="arn:aws:lambda:$AWS_REGION:$ACCOUNT_ID:layer:$LAYER_NAME:$LAYER_VERSION"

log_success "Layer published: $LAYER_ARN"

###############################################################################
# Attach to Lambda Function
###############################################################################

log_info "Attaching layer to function: $FUNCTION_NAME"

aws lambda update-function-configuration \
  --function-name "$FUNCTION_NAME" \
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
