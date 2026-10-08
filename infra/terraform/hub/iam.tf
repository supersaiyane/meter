# What the running tasks may do.
#
# Two roles per the ECS split. The execution role is what Fargate itself uses to
# pull the image and open the log stream, before the container starts. The task
# role is what the application code holds once it is running. Collapsing them
# would give application code the ability to pull any image and decrypt the log
# key, neither of which it needs.

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }

    # Without this an ECS task in any account could assume these roles. It is
    # the same confused deputy problem as the cross account roles, in the
    # account's own back yard.
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:${data.aws_partition.current.partition}:ecs:${var.region}:${data.aws_caller_identity.current.account_id}:*"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "FinOpsHubExecutionRole"
  description        = "Used by Fargate to pull the image and open the log stream. Never by application code."
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_extra" {
  statement {
    sid    = "DecryptImageAndLogKeys"
    effect = "Allow"

    actions = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [
      aws_kms_key.storage.arn,
      aws_kms_key.logs.arn,
    ]
  }

  # The database password, injected as a secret into the container definition.
  # Read by the execution role at task start rather than by application code,
  # so the running process never holds permission to read it again.
  statement {
    sid       = "ReadInjectedSecrets"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_rds_cluster.hub.master_user_secret[0].secret_arn]
  }
}

resource "aws_iam_role_policy" "execution_extra" {
  name   = "PullAndLog"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_extra.json
}

# --- the task role -----------------------------------------------------------

resource "aws_iam_role" "task" {
  name               = "FinOpsHubTaskRole"
  description        = "Held by Meter's own code. Named in the trust policy of every collector role."
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

data "aws_iam_policy_document" "task" {
  # The one permission the whole product depends on, and the one most worth
  # getting wrong. Scoped to the collector role NAME in any account, not to
  # `*`: a compromised container can then assume FinOpsCollectorRole and
  # nothing else, and only inside this organization.
  statement {
    sid       = "AssumeTheCollectorRoleAndNothingElse"
    effect    = "Allow"
    actions   = ["sts:AssumeRole"]
    resources = ["arn:${data.aws_partition.current.partition}:iam::*:role/${var.collector_role_name}"]

    condition {
      test     = "StringEquals"
      variable = "aws:PrincipalOrgID"
      values   = [var.organization_id]
    }
  }

  # The management account role, which is a different name in one known
  # account, so it is named exactly.
  dynamic "statement" {
    for_each = var.org_reader_role_arn == "" ? [] : [var.org_reader_role_arn]

    content {
      sid       = "AssumeTheOrganizationReader"
      effect    = "Allow"
      actions   = ["sts:AssumeRole"]
      resources = [statement.value]
    }
  }

  statement {
    sid    = "WorkTheQueue"
    effect = "Allow"

    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:SendMessage",
      "sqs:ChangeMessageVisibility",
    ]

    resources = [aws_sqs_queue.work.arn, aws_sqs_queue.dead_letter.arn]
  }

  statement {
    sid       = "ReadTheExternalId"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.external_id.arn]
  }

  # TASK-P9-001, ADR-0035. The relay outside the VPC, for the calls no endpoint carries. Its
  # answers are read back under UseTheBucket below.
  statement {
    sid       = "InvokeTheRelay"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.relay.arn]
  }

  statement {
    sid    = "UseTheBucket"
    effect = "Allow"

    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.data.arn}/*"]
  }

  statement {
    sid       = "ListTheBucket"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data.arn]
  }

  statement {
    sid    = "UseTheDataKeys"
    effect = "Allow"

    actions = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [
      aws_kms_key.storage.arn,
      aws_kms_key.queue.arn,
      aws_kms_key.database.arn,
    ]
  }

  # Meter's own cost, which is the front page. Cost Explorer has no resource
  # level permissions, so this is a wildcard AWS will not let us narrow.
  statement {
    sid    = "ReadOurOwnCost"
    effect = "Allow"

    actions = [
      "ce:GetCostAndUsage",
      "ce:GetDimensionValues",
      "ce:GetTags",
    ]

    resources = ["*"]
  }

  # AWS's public prices, FEAT-071, TASK-P9-004: finops_providers/aws/price_list.py reads the
  # list's versions and its products through the endpoint in us-east-1, ADR-0035. The Price
  # List API has no resource level permissions, so this is a wildcard AWS will not let us
  # narrow. Read only, constraint 6.
  statement {
    sid    = "ReadAwsPrices"
    effect = "Allow"

    actions = [
      "pricing:ListPriceLists",
      "pricing:GetProducts",
    ]

    resources = ["*"]
  }

  # EC2's description of its instance types, FEAT-072, TASK-P9-005:
  # finops_providers/aws/instance_types.py reads it in the hub's Region and the Region it is
  # compared with, through the endpoints there, ADR-0035. A describe call takes no resource
  # level permission. Read only, constraint 6.
  statement {
    sid       = "DescribeInstanceTypes"
    effect    = "Allow"
    actions   = ["ec2:DescribeInstanceTypes"]
    resources = ["*"]
  }

  # Metrics the collectors publish about themselves. Restricted to the Meter
  # namespace, so a bug cannot overwrite another team's metrics.
  statement {
    sid       = "PublishOurOwnMetrics"
    effect    = "Allow"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = [var.metric_namespace]
    }
  }

  # The model behind the assistant, ADR-0028, reached only through its tagged inference
  # profile below, ISS-230. Two statements because the service authorizes two resources
  # for one call: the profile the request names, and the foundation model the profile
  # routes to. The model is granted only on condition that the call came through one of
  # these profiles, so a call naming the model directly is refused rather than billed
  # with no module, which is the one way the assistant's spend could leave the platform
  # cost screen.
  #
  # Named foundation models in this region only, never a wildcard: adding a model is a
  # change to assistant_model_ids that somebody reviews, and a wildcard would grant every
  # model the service ever adds. Absent until a model is named, which is OPEN-10, so a
  # deployment that has not chosen one grants nothing and the assistant says it is not
  # enabled.
  #
  # Invocation only. Neither action creates, changes or deletes anything, here or in a
  # member account, and no member account role gains anything for the assistant. The
  # profiles are created by whoever applies this stack, never by the task role.
  dynamic "statement" {
    for_each = length(var.assistant_model_ids) == 0 ? [] : [var.assistant_model_ids]

    content {
      sid    = "InvokeThroughTheTaggedProfiles"
      effect = "Allow"

      actions = [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
      ]

      resources = [
        for model_id in statement.value : aws_bedrock_inference_profile.assistant[model_id].arn
      ]
    }
  }

  dynamic "statement" {
    for_each = length(var.assistant_model_ids) == 0 ? [] : [var.assistant_model_ids]

    content {
      sid    = "ReachTheModelsOnlyThroughTheProfiles"
      effect = "Allow"

      actions = [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
      ]

      resources = [
        for model_id in statement.value :
        "arn:${data.aws_partition.current.partition}:bedrock:${var.region}::foundation-model/${model_id}"
      ]

      # The key the Bedrock documentation names for this, typed as an ARN by the service
      # reference, so an ARN operator rather than a string one.
      condition {
        test     = "ArnEquals"
        variable = "bedrock:InferenceProfileArn"
        values = [
          for model_id in statement.value : aws_bedrock_inference_profile.assistant[model_id].arn
        ]
      }
    }
  }
}

resource "aws_iam_role_policy" "task" {
  name   = "MeterHubTask"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task.json
}

# --- the assistant's model, behind a tagged profile ---------------------------
#
# One application inference profile per model in assistant_model_ids, ISS-230. An on
# demand call to a foundation model is not a resource, so default_tags cannot reach it
# and its line on the bill arrives with no module. A call made through an application
# inference profile carries the profile's tags onto the bill, and the platform cost
# collector groups by finops:module, so the assistant's spend arrives as a module of its
# own rather than in unallocated. Constraint 7.
#
# Each profile copies the foundation model in this region, so it routes nowhere the model
# did not already run: it adds a tag, not a destination. It lives beside the grant that
# names it because the two change together. Whether the tag reaches the cost line of the
# model OPEN-10 chooses has not been seen on a real bill, ISS-002.
resource "aws_bedrock_inference_profile" "assistant" {
  for_each = toset(var.assistant_model_ids)

  # A profile name holds letters, digits and single separators, and a model identifier
  # carries dots and a colon, so each run of anything else becomes one hyphen. The
  # provider refuses a name over 64 characters before anything is created.
  name = "${local.name}-assistant-${replace(each.value, "/[^0-9A-Za-z]+/", "-")}"

  model_source {
    copy_from = "arn:${data.aws_partition.current.partition}:bedrock:${var.region}::foundation-model/${each.value}"
  }

  # Overrides the stack default of hub on purpose. The assistant's spend moves with the
  # questions asked rather than with the hours the stack runs, and folded into hub the
  # screen could not say what the assistant costs, which is the question ISS-230 asks.
  tags = {
    "finops:module" = "assistant"
  }
}
