#!/bin/sh
# The local work queue and its dead letter queue, shaped as infra/terraform/hub/queue.tf declares
# the hub's: a standard queue, a 900 second visibility timeout, and the dead letter queue after
# three receives, matching MAX_DELIVERY_ATTEMPTS. TASK-P12-005.
#
# LocalStack runs this once it is ready, and docker-compose.yml calls it healthy only after this
# has completed, so the worker never starts against a queue that does not exist yet. The Region
# is the one the local clients use; LocalStack keeps a queue per Region.
set -eu
export AWS_DEFAULT_REGION=eu-west-1
awslocal sqs create-queue --queue-name meter-ingest-dlq \
  --attributes '{"MessageRetentionPeriod":"1209600"}' >/dev/null
awslocal sqs create-queue --queue-name meter-ingest \
  --attributes '{"VisibilityTimeout":"900","RedrivePolicy":"{\"deadLetterTargetArn\":\"arn:aws:sqs:eu-west-1:000000000000:meter-ingest-dlq\",\"maxReceiveCount\":\"3\"}"}' >/dev/null
echo "meter-ingest and meter-ingest-dlq are ready"
