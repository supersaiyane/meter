# The relay outside the VPC. TASK-P9-001, ADR-0035, P9 spec 5.1, and the owner's answer to
# OPEN-17.
#
# Budgets, Support and Invoicing have no interface endpoint, and spot prices and Savings Plans
# rates are wanted in every Region, so those calls cannot leave the hub through an endpoint. The
# hub invokes this function instead, through the Lambda endpoint in network.tf. It has no VPC,
# makes the one call `finops_relay/relay.py` allows, and writes the answer to the data bucket,
# which the hub reads through its S3 gateway endpoint. The hub keeps no route out.
#
# Its role holds only what those calls need, and every role it assumes is narrowed further by a
# session policy to the one action. It is invoked by the hub task role and nothing else.

resource "aws_cloudwatch_log_group" "relay" {
  name              = "/aws/lambda/${local.name}-relay"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.logs.arn
}

data "aws_iam_policy_document" "relay_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role" "relay" {
  name               = var.relay_role_name
  description        = "Makes the hub's allow listed read only calls outside its VPC. ADR-0035."
  assume_role_policy = data.aws_iam_policy_document.relay_assume.json
}

data "aws_iam_policy_document" "relay" {
  statement {
    sid       = "WriteItsOwnLogs"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.relay.arn}:*"]
  }

  statement {
    sid       = "TraceItsCalls"
    effect    = "Allow"
    actions   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"]
    resources = ["*"]
  }

  statement {
    sid       = "WriteItsAnswers"
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.data.arn}/${local.relay_prefix}/*"]
  }

  statement {
    sid       = "UseTheDataKey"
    effect    = "Allow"
    actions   = ["kms:GenerateDataKey", "kms:Decrypt"]
    resources = [aws_kms_key.storage.arn]
  }

  statement {
    sid       = "ReadTheExternalId"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.external_id.arn]
  }

  # Support's Trusted Advisor reads, and since TASK-P14-002 each account's Savings Plans and RDS
  # reservations, ADR-0037, made as the member account's collector role.
  statement {
    sid       = "AssumeTheCollectorRole"
    effect    = "Allow"
    actions   = ["sts:AssumeRole"]
    resources = ["arn:${data.aws_partition.current.partition}:iam::*:role/${var.collector_role_name}"]
  }

  # Budgets and Invoicing, made as the payer's organization reader.
  dynamic "statement" {
    for_each = var.org_reader_role_arn == "" ? [] : [var.org_reader_role_arn]

    content {
      sid       = "AssumeTheOrganizationReader"
      effect    = "Allow"
      actions   = ["sts:AssumeRole"]
      resources = [statement.value]
    }
  }

  # Public price data that belongs to no account, read as the relay itself. Neither action
  # supports a resource narrower than everything.
  statement {
    sid    = "ReadPublicPrices"
    effect = "Allow"
    actions = [
      "ec2:DescribeSpotPriceHistory",
      "savingsplans:DescribeSavingsPlansOfferingRates",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "relay" {
  name   = "RelayAllowListedReads"
  role   = aws_iam_role.relay.id
  policy = data.aws_iam_policy_document.relay.json
}

resource "aws_lambda_function" "relay" {
  function_name = "${local.name}-relay"
  description   = "One allow listed, read only AWS call for the hub, outside its VPC. ADR-0035."
  role          = aws_iam_role.relay.arn
  runtime       = "python3.13"
  handler       = "finops_relay.relay.handler"
  architectures = ["x86_64"]

  # Built by `make build-relay`, which zips finops_relay alone: the runtime provides boto3 and
  # the package imports nothing else, a contract in pyproject.toml.
  filename         = var.relay_package
  source_code_hash = fileexists(var.relay_package) ? filebase64sha256(var.relay_package) : null

  timeout     = 300
  memory_size = 256
  # A ceiling on what a runaway caller can spend, well above what the collectors ask at once.
  reserved_concurrent_executions = 4

  environment {
    variables = {
      METER_S3_BUCKET           = aws_s3_bucket.data.id
      METER_ORG_READER_ROLE_ARN = var.org_reader_role_arn
      METER_COLLECTOR_ROLE_NAME = var.collector_role_name
      METER_EXTERNAL_ID_SECRET  = aws_secretsmanager_secret.external_id.name
    }
  }

  tracing_config {
    mode = "Active"
  }

  logging_config {
    log_format = "JSON"
    log_group  = aws_cloudwatch_log_group.relay.name
  }

  depends_on = [aws_iam_role_policy.relay, aws_cloudwatch_log_group.relay]
}
