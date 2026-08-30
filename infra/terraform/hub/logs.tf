# Meter's own log groups, with retention set at creation.
#
# A log group created by the awslogs driver on first use has no retention and
# never expires. That is a bill that only grows and a data retention promise
# that is silently false, and it is why these are declared here rather than left
# to be created implicitly: an implicitly created group cannot be given
# retention at creation, only after somebody notices.

resource "aws_kms_key" "logs" {
  description             = "CloudWatch log groups for Meter ${var.env}."
  enable_key_rotation     = true
  deletion_window_in_days = 30

  # CloudWatch Logs encrypts with a key it must be able to use. Without this
  # statement the log group creation fails with an unhelpful access denied.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AccountRoot"
        Effect    = "Allow"
        Principal = { AWS = "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root" }
        Action    = "kms:*"
        Resource  = "*"
      },
      {
        Sid       = "CloudWatchLogs"
        Effect    = "Allow"
        Principal = { Service = "logs.${var.region}.amazonaws.com" }
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:Describe*",
        ]
        Resource = "*"
        Condition = {
          ArnLike = {
            "kms:EncryptionContext:aws:logs:arn" = "arn:${data.aws_partition.current.partition}:logs:${var.region}:${data.aws_caller_identity.current.account_id}:log-group:*"
          }
        }
      },
    ]
  })
}

resource "aws_kms_alias" "logs" {
  name          = "alias/${local.name}-logs"
  target_key_id = aws_kms_key.logs.key_id
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/meter/${var.env}/api"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.logs.arn
}

resource "aws_cloudwatch_log_group" "mcp" {
  name              = "/meter/${var.env}/mcp"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.logs.arn
}

resource "aws_cloudwatch_log_group" "web" {
  name              = "/meter/${var.env}/web"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.logs.arn
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/meter/${var.env}/worker"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.logs.arn
}

resource "aws_cloudwatch_log_group" "dispatcher" {
  name              = "/meter/${var.env}/dispatcher"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.logs.arn
}
