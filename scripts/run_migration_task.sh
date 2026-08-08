#!/usr/bin/env bash
# Run database migrations as a one off ECS task, on the image being deployed.
#
# Usage: scripts/run_migration_task.sh <env> <image_tag>
#
# Migrations must be backward compatible. During a rolling deploy the old and
# new task definition revisions run against the same schema at the same time.
# See docs/04-DEPLOYMENT.md, section "Migrations".

set -euo pipefail

ENV="${1:?environment is required, for example dev}"
IMAGE_TAG="${2:?image tag is required}"
AWS_REGION="${AWS_REGION:-eu-west-1}"

CLUSTER="meter-${ENV}"
TASK_FAMILY="meter-migrate-${ENV}"

echo "Running migrations on ${CLUSTER} at image tag ${IMAGE_TAG}"

SUBNETS=$(aws ssm get-parameter --name "/meter/${ENV}/private_subnet_ids" \
  --query 'Parameter.Value' --output text)
SECURITY_GROUP=$(aws ssm get-parameter --name "/meter/${ENV}/app_security_group_id" \
  --query 'Parameter.Value' --output text)

TASK_ARN=$(aws ecs run-task \
  --cluster "${CLUSTER}" \
  --task-definition "${TASK_FAMILY}" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[${SUBNETS}],securityGroups=[${SECURITY_GROUP}],assignPublicIp=DISABLED}" \
  --overrides "{\"containerOverrides\":[{\"name\":\"migrate\",\"command\":[\"alembic\",\"upgrade\",\"head\"]}]}" \
  --query 'tasks[0].taskArn' --output text)

echo "Task started: ${TASK_ARN}"
aws ecs wait tasks-stopped --cluster "${CLUSTER}" --tasks "${TASK_ARN}"

EXIT_CODE=$(aws ecs describe-tasks --cluster "${CLUSTER}" --tasks "${TASK_ARN}" \
  --query 'tasks[0].containers[0].exitCode' --output text)

# A migration that fails must fail the pipeline. Deploying application code
# against a schema that did not migrate is how an outage starts.
if [[ "${EXIT_CODE}" != "0" ]]; then
  echo "Migration failed with exit code ${EXIT_CODE}"
  aws logs tail "/ecs/meter-migrate-${ENV}" --since 10m || true
  exit 1
fi

echo "Migrations applied successfully"
