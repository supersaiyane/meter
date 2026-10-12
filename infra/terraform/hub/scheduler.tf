# What wakes the dispatcher up.
#
# This is not the collection cadence. Cadence is data, in `collector_schedule`,
# with its reason and its cost, per constraint 9 and ADR-0012. This schedule
# only decides how often something asks the table which collectors are due, so
# it has to be at least as frequent as the shortest cadence in the table.
#
# EventBridge Scheduler rather than an EventBridge rule: it runs the dispatcher
# as a one shot ECS task rather than keeping a service alive to look at a clock.

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "FinOpsHubSchedulerRole"
  description        = "Lets EventBridge Scheduler run the dispatcher task, and nothing else."
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    sid       = "RunTheDispatcherTask"
    effect    = "Allow"
    actions   = ["ecs:RunTask"]
    resources = ["${aws_ecs_task_definition.dispatcher.arn_without_revision}:*"]

    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [aws_ecs_cluster.hub.arn]
    }
  }

  # RunTask needs to hand the task its roles, which is a separate permission
  # from running it. Scoped to the two roles by ARN: without the resource
  # restriction the scheduler could start a task as any role in the account.
  statement {
    sid       = "PassOnlyTheTaskRoles"
    effect    = "Allow"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.task.arn, aws_iam_role.execution.arn]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "RunDispatcher"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}

resource "aws_ecs_task_definition" "dispatcher" {
  family                   = "${local.name}-dispatcher"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    cpu_architecture        = "X86_64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([
    {
      name      = "dispatcher"
      image     = "${local.registry}/meter-worker:${var.image_tag}"
      essential = true
      # The image's entrypoint is already `python -m`, so the command is the module alone. It
      # was the interpreter, `-m` and the module, which ran `python -m /opt/venv/bin/python`. ISS-277.
      command = ["finops_ingest.dispatcher"]

      environment = local.setting_environment
      secrets     = local.setting_secrets

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.dispatcher.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "dispatcher"
        }
      }
    },
  ])
}

resource "aws_scheduler_schedule" "dispatcher" {
  name                         = "${local.name}-dispatcher"
  description                  = "Wakes the dispatcher to ask collector_schedule which collectors are due."
  schedule_expression          = var.dispatcher_schedule
  schedule_expression_timezone = "UTC"

  # No flexible window. The dispatcher is idempotent, so a late run is
  # harmless, but a predictable start time makes a missed run obvious on the
  # freshness screen rather than looking like jitter.
  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_ecs_cluster.hub.arn
    role_arn = aws_iam_role.scheduler.arn

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.dispatcher.arn_without_revision
      launch_type         = "FARGATE"
      task_count          = 1

      network_configuration {
        subnets          = aws_subnet.private[*].id
        security_groups  = [aws_security_group.tasks.id]
        assign_public_ip = false
      }
    }

    # One retry, not the default of 185. A dispatch that failed because the
    # database was unreachable will fail again in a minute, and the next hourly
    # run is the real retry.
    retry_policy {
      maximum_retry_attempts       = 1
      maximum_event_age_in_seconds = 300
    }
  }
}
