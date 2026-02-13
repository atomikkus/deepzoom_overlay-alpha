#!/bin/bash
# Deploy WSI Viewer to Google Cloud Run
# Usage: ./deploy_cloud_run.sh [options]

set -e

# Default values
SERVICE_NAME="deepzoom-overlay-alpha"
REGION="asia-south1"
MEMORY="4Gi"
CPU="2"
TIMEOUT="300"
MAX_INSTANCES="10"
MIN_INSTANCES="0"
CONCURRENCY="80"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}WSI Viewer - Cloud Run Deployment${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}Error: gcloud CLI not found. Please install it first.${NC}"
    echo "Visit: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Get current project
PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}Error: No GCloud project set.${NC}"
    echo "Run: gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

echo -e "${YELLOW}Project:${NC} $PROJECT_ID"
echo -e "${YELLOW}Service:${NC} $SERVICE_NAME"
echo -e "${YELLOW}Region:${NC} $REGION"
echo ""

# Check for environment variables
if [ -f .env ]; then
    echo -e "${YELLOW}Found .env file. Loading authentication settings...${NC}"
    source .env
fi

# Build environment variables
ENV_VARS="AUTH_ENABLED=${AUTH_ENABLED:-true}"

if [ ! -z "$AUTH_USERNAME" ]; then
    ENV_VARS="$ENV_VARS,AUTH_USERNAME=$AUTH_USERNAME"
    echo -e "${GREEN}✓${NC} Setting AUTH_USERNAME"
fi

if [ ! -z "$AUTH_PASSWORD_HASH" ]; then
    ENV_VARS="$ENV_VARS,AUTH_PASSWORD_HASH=$AUTH_PASSWORD_HASH"
    echo -e "${GREEN}✓${NC} Setting AUTH_PASSWORD_HASH"
elif [ ! -z "$AUTH_PASSWORD" ]; then
    echo -e "${YELLOW}⚠${NC}  Using AUTH_PASSWORD (not recommended for production)"
    ENV_VARS="$ENV_VARS,AUTH_PASSWORD=$AUTH_PASSWORD"
fi

if [ ! -z "$SESSION_TTL" ]; then
    ENV_VARS="$ENV_VARS,SESSION_TTL=$SESSION_TTL"
    echo -e "${GREEN}✓${NC} Setting SESSION_TTL=$SESSION_TTL"
fi

echo ""
echo -e "${YELLOW}Deploying to Cloud Run...${NC}"
echo ""

# Deploy
gcloud run deploy $SERVICE_NAME \
  --source . \
  --platform managed \
  --region $REGION \
  --memory $MEMORY \
  --cpu $CPU \
  --timeout $TIMEOUT \
  --max-instances $MAX_INSTANCES \
  --min-instances $MIN_INSTANCES \
  --concurrency $CONCURRENCY \
  --set-env-vars "$ENV_VARS" \
  --allow-unauthenticated

# Get service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
  --region $REGION \
  --format='value(status.url)')

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment Successful!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}Service URL:${NC} $SERVICE_URL"
echo -e "${YELLOW}API Docs:${NC} $SERVICE_URL/docs"
echo ""
echo -e "${YELLOW}Create a session:${NC}"
echo "curl -u \$USERNAME:\$PASSWORD -X POST \"$SERVICE_URL/api/sessions\" \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -d '{\"slides\": [\"gs://bucket/slide.svs\"], \"overlay\": []}'"
echo ""
echo -e "${YELLOW}View logs:${NC}"
echo "gcloud run services logs read $SERVICE_NAME --region $REGION"
echo ""
echo -e "${GREEN}========================================${NC}"
