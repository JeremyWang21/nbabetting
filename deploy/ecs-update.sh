#!/bin/bash
# Force a new ECS deployment (pulls the latest image from ECR).
# Run after pushing a new image to ECR.
#
# Usage:
#   ./deploy/ecs-update.sh
#
# Prerequisites:
#   AWS CLI configured, ECS_CLUSTER and ECS_SERVICE set as env vars or edited below.

set -euo pipefail

CLUSTER="${ECS_CLUSTER:-nbabetting}"
SERVICE="${ECS_SERVICE:-nbabetting-service}"
REGION="${AWS_REGION:-us-east-1}"

echo "Forcing new deployment: cluster=$CLUSTER service=$SERVICE region=$REGION"

aws ecs update-service \
  --cluster "$CLUSTER" \
  --service "$SERVICE" \
  --force-new-deployment \
  --region "$REGION" \
  --query "service.deployments[0].{status:status,desiredCount:desiredCount}" \
  --output table

echo "Deployment triggered. Monitor progress:"
echo "  aws ecs describe-services --cluster $CLUSTER --services $SERVICE --region $REGION"
