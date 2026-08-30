# The work queue and its dead letter queue.
#
# `max_receive_count` here and `MAX_DELIVERY_ATTEMPTS` in
# `finops_core/constants.py` are the same number described twice. If they
# disagree, the worker and the queue disagree about what a poisoned message is,
# and the symptom is a unit of work that is retried forever or one that is
# abandoned early. The variable's description says so, and a change to either
# should change both.

resource "aws_kms_key" "queue" {
  description             = "SQS messages for Meter ${var.env}."
  enable_key_rotation     = true
  deletion_window_in_days = 30
}

resource "aws_kms_alias" "queue" {
  name          = "alias/${local.name}-queue"
  target_key_id = aws_kms_key.queue.key_id
}

resource "aws_sqs_queue" "dead_letter" {
  name              = "${local.name}-work-dlq"
  kms_master_key_id = aws_kms_key.queue.id

  # Fourteen days, the maximum. A message here is a unit of work that failed
  # three times, and the person who has to look at it may not be on shift today.
  message_retention_seconds = 1209600
}

resource "aws_sqs_queue" "work" {
  name                       = "${local.name}-work"
  kms_master_key_id          = aws_kms_key.queue.id
  visibility_timeout_seconds = var.queue_visibility_timeout_seconds
  message_retention_seconds  = 345600

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dead_letter.arn
    maxReceiveCount     = var.queue_max_receive_count
  })
}

# Only the dead letter queue's own consumers may redrive from it. Without this,
# any principal that can write to SQS can push work back onto the main queue.
resource "aws_sqs_queue_redrive_allow_policy" "dead_letter" {
  queue_url = aws_sqs_queue.dead_letter.id

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.work.arn]
  })
}
