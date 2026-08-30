# Four services on Fargate: api, mcp, web and worker.
#
# The mcp service runs the api image with the command overridden. That is the
# deployment half of ADR-0009 and it is why there is no fifth ECR repository.

locals {
  registry = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.region}.amazonaws.com"

  # Every task gets these. The database password is not here: it is injected as
  # a secret by the execution role, so the running process never holds the
  # permission to read it again.
  common_environment = [
    { name = "METER_ENV", value = var.env },
    { name = "METER_REGION", value = var.region },
    { name = "METER_QUEUE_URL", value = aws_sqs_queue.work.url },
    { name = "METER_EXTERNAL_ID_SECRET", value = aws_secretsmanager_secret.external_id.name },
    { name = "METER_COLLECTOR_ROLE_NAME", value = var.collector_role_name },
    { name = "METER_ORG_READER_ROLE_ARN", value = var.org_reader_role_arn },
    { name = "METER_S3_BUCKET", value = aws_s3_bucket.data.id },
  ]
}

resource "aws_ecs_cluster" "hub" {
  name = local.name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_cluster_capacity_providers" "hub" {
  cluster_name = aws_ecs_cluster.hub.name

  # Fargate Spot for the worker only, declared here and selected per service.
  # A worker unit that is interrupted is redelivered by the queue, so Spot costs
  # a retry. An interrupted API task costs a request.
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
  }
}

# --- api ---------------------------------------------------------------------

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    # Constraint 13. A push never converts an image, and the failure reads as
    # `exec format error`, which does not obviously mean "wrong architecture".
    cpu_architecture        = "X86_64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([
    {
      name      = "api"
      image     = "${local.registry}/meter-api:${var.image_tag}"
      essential = true

      portMappings = [{ containerPort = 8000, protocol = "tcp" }]
      environment  = local.common_environment
      secrets = [
        {
          name      = "METER_DATABASE_URL"
          valueFrom = "${aws_rds_cluster.hub.master_user_secret[0].secret_arn}:METER_DATABASE_URL::"
        },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.api.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "api"
        }
      }
    },
  ])
}

resource "aws_ecs_service" "api" {
  name            = "${local.name}-api"
  cluster         = aws_ecs_cluster.hub.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"

  # Rolling, never all at once. minimum_healthy_percent at 100 means a new task
  # is healthy before an old one goes, so a broken image cannot take the service
  # down, it just fails to roll out.
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  wait_for_steady_state              = true

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  depends_on = [aws_lb_listener.http]
}

# --- mcp, the same image with a different command -----------------------------

resource "aws_ecs_task_definition" "mcp" {
  family                   = "${local.name}-mcp"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution.arn

  # No task role. The facade holds no credential of its own and reaches Meter
  # only over HTTP with the caller's token. Giving it a task role would give it
  # a way to read data the caller is not entitled to, which is the bug ADR-0009
  # exists to prevent.
  runtime_platform {
    cpu_architecture        = "X86_64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([
    {
      name      = "mcp"
      image     = "${local.registry}/meter-api:${var.image_tag}"
      essential = true

      command = [
        "/opt/venv/bin/uvicorn",
        "finops_mcp.server:bootstrap",
        "--factory",
        "--host", "0.0.0.0",
        "--port", "8001",
      ]

      portMappings = [{ containerPort = 8001, protocol = "tcp" }]

      environment = [
        { name = "METER_API_BASE_URL", value = "http://${aws_lb.hub.dns_name}" },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.mcp.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "mcp"
        }
      }
    },
  ])
}

resource "aws_ecs_service" "mcp" {
  name            = "${local.name}-mcp"
  cluster         = aws_ecs_cluster.hub.id
  task_definition = aws_ecs_task_definition.mcp.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = false
  }
}

# --- web ---------------------------------------------------------------------

resource "aws_ecs_task_definition" "web" {
  family                   = "${local.name}-web"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution.arn

  runtime_platform {
    cpu_architecture        = "X86_64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([
    {
      name      = "web"
      image     = "${local.registry}/meter-web:${var.image_tag}"
      essential = true

      portMappings = [{ containerPort = 8080, protocol = "tcp" }]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.web.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "web"
        }
      }
    },
  ])
}

resource "aws_ecs_service" "web" {
  name            = "${local.name}-web"
  cluster         = aws_ecs_cluster.hub.id
  task_definition = aws_ecs_task_definition.web.arn
  desired_count   = var.web_desired_count
  launch_type     = "FARGATE"

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  wait_for_steady_state              = true

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.web.arn
    container_name   = "web"
    container_port   = 8080
  }

  depends_on = [aws_lb_listener.http]
}

# --- worker ------------------------------------------------------------------

resource "aws_ecs_task_definition" "worker" {
  family                   = "${local.name}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    cpu_architecture        = "X86_64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([
    {
      name      = "worker"
      image     = "${local.registry}/meter-worker:${var.image_tag}"
      essential = true

      environment = local.common_environment
      secrets = [
        {
          name      = "METER_DATABASE_URL"
          valueFrom = "${aws_rds_cluster.hub.master_user_secret[0].secret_arn}:METER_DATABASE_URL::"
        },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.worker.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "worker"
        }
      }
    },
  ])
}

resource "aws_ecs_service" "worker" {
  name            = "${local.name}-worker"
  cluster         = aws_ecs_cluster.hub.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = var.worker_min_count

  capacity_provider_strategy {
    capacity_provider = "FARGATE_SPOT"
    weight            = 1
  }

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = false
  }

  lifecycle {
    # Autoscaling owns this after the first apply. Without the exception, every
    # plan proposes to scale the workers back down to the floor.
    ignore_changes = [desired_count]
  }
}

resource "aws_appautoscaling_target" "worker" {
  service_namespace  = "ecs"
  resource_id        = "service/${aws_ecs_cluster.hub.name}/${aws_ecs_service.worker.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  min_capacity       = var.worker_min_count
  max_capacity       = var.worker_max_count
}

# Scales on queue depth rather than on CPU. A worker waiting on a throttled AWS
# API uses almost no CPU while the queue backs up, so CPU based scaling would
# scale down exactly when the backlog is worst.
resource "aws_appautoscaling_policy" "worker_queue_depth" {
  name               = "${local.name}-worker-queue-depth"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = aws_appautoscaling_target.worker.service_namespace
  resource_id        = aws_appautoscaling_target.worker.resource_id
  scalable_dimension = aws_appautoscaling_target.worker.scalable_dimension

  target_tracking_scaling_policy_configuration {
    target_value = 20

    customized_metric_specification {
      metrics {
        id    = "visible"
        label = "Messages waiting"

        metric_stat {
          metric {
            namespace   = "AWS/SQS"
            metric_name = "ApproximateNumberOfMessagesVisible"

            dimensions {
              name  = "QueueName"
              value = aws_sqs_queue.work.name
            }
          }

          stat = "Average"
        }

        return_data = true
      }
    }

    # Scale out quickly and in slowly. An hourly burst means the cost of being
    # slow to scale out is a late collection, and the cost of being quick to
    # scale in is starting a task again a minute later.
    scale_out_cooldown = 60
    scale_in_cooldown  = 300
  }
}
