# The load balancer, and the only thing in this stack with a public address.

resource "aws_security_group" "alb" {
  name        = "${local.name}-alb"
  description = "The load balancer. The only public entry point."
  vpc_id      = aws_vpc.hub.id

  tags = { Name = "${local.name}-alb" }
}

resource "aws_vpc_security_group_ingress_rule" "alb_https" {
  security_group_id = aws_security_group.alb.id
  description       = "HTTPS from the internet."
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "alb_http" {
  security_group_id = aws_security_group.alb.id
  description       = "HTTP, redirected to HTTPS when a certificate exists."
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "alb_to_tasks" {
  security_group_id            = aws_security_group.alb.id
  description                  = "To the tasks, and nowhere else."
  referenced_security_group_id = aws_security_group.tasks.id
  ip_protocol                  = "-1"
}

resource "aws_security_group" "tasks" {
  name        = "${local.name}-tasks"
  description = "The ECS tasks. Reachable from the load balancer only."
  vpc_id      = aws_vpc.hub.id

  tags = { Name = "${local.name}-tasks" }
}

resource "aws_vpc_security_group_ingress_rule" "tasks_from_alb" {
  security_group_id            = aws_security_group.tasks.id
  description                  = "From the load balancer only. Not from the VPC."
  referenced_security_group_id = aws_security_group.alb.id
  from_port                    = 8000
  to_port                      = 8080
  ip_protocol                  = "tcp"
}

# The tasks talk to each other: the MCP server calls the API over the network,
# which is the whole of ADR-0009. Without this rule that call is refused and the
# facade cannot work.
resource "aws_vpc_security_group_ingress_rule" "tasks_from_tasks" {
  security_group_id            = aws_security_group.tasks.id
  description                  = "Task to task, so the MCP facade can call the API as any caller does."
  referenced_security_group_id = aws_security_group.tasks.id
  from_port                    = 8000
  to_port                      = 8080
  ip_protocol                  = "tcp"
}

# To the endpoints by security group, not to 0.0.0.0/0. The private route table
# has no default route, so a wider rule would have reached nothing extra, but a
# rule that says "anywhere" is read as "anywhere" by the next person and by the
# scanner. Narrowing it costs nothing and makes the intent legible.
resource "aws_vpc_security_group_egress_rule" "tasks_endpoints" {
  security_group_id            = aws_security_group.tasks.id
  description                  = "HTTPS to the interface endpoints, which is every AWS call Meter makes."
  referenced_security_group_id = aws_security_group.endpoints.id
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
}

# The S3 gateway endpoint is a route rather than a security group, so egress to
# it is expressed as a prefix list. Without this an image layer pull fails, and
# the failure looks like a task that will not start rather than a network rule.
resource "aws_vpc_security_group_egress_rule" "tasks_s3" {
  security_group_id = aws_security_group.tasks.id
  description       = "HTTPS to S3 through the gateway endpoint. ECR layers come from here."
  prefix_list_id    = aws_vpc_endpoint.s3.prefix_list_id
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "tasks_database" {
  security_group_id            = aws_security_group.tasks.id
  description                  = "PostgreSQL to Aurora."
  referenced_security_group_id = aws_security_group.database.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "tasks_internal" {
  security_group_id            = aws_security_group.tasks.id
  description                  = "Task to task, the other half of the MCP path."
  referenced_security_group_id = aws_security_group.tasks.id
  ip_protocol                  = "-1"
}

# Development may serve over HTTP. Production may not, and the refusal is here
# rather than in a review checklist, because "we will add TLS before we go live"
# is a sentence that survives going live.
resource "terraform_data" "tls_is_required_in_production" {
  lifecycle {
    precondition {
      condition     = var.env != "prod" || var.certificate_arn != ""
      error_message = "Production requires certificate_arn. Serving the product over plain HTTP is not acceptable."
    }
  }
}

resource "aws_lb" "hub" {
  name               = local.name
  load_balancer_type = "application"
  subnets            = aws_subnet.public[*].id
  security_groups    = [aws_security_group.alb.id]

  drop_invalid_header_fields = true
  enable_deletion_protection = var.env == "prod"
}

resource "aws_lb_target_group" "api" {
  name        = "${local.name}-api"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.hub.id
  target_type = "ip"

  # /healthz, which reports whether the database is reachable and whether
  # collection is still running, not whether the process is alive. A liveness
  # only probe would keep a task in service while it serves confident and wrong
  # numbers.
  health_check {
    path                = "/healthz"
    matcher             = "200"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  # Long enough for an in flight request to finish, short enough that a deploy
  # is not dominated by waiting.
  deregistration_delay = 30
}

resource "aws_lb_target_group" "web" {
  name        = "${local.name}-web"
  port        = 8080
  protocol    = "HTTP"
  vpc_id      = aws_vpc.hub.id
  target_type = "ip"

  health_check {
    path                = "/"
    matcher             = "200"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  deregistration_delay = 30
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.hub.arn
  port              = 80
  protocol          = "HTTP"

  # With a certificate, HTTP exists only to send the caller to HTTPS. Without
  # one, which is development only, it serves.
  dynamic "default_action" {
    for_each = var.certificate_arn == "" ? [] : [1]

    content {
      type = "redirect"

      redirect {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }
  }

  dynamic "default_action" {
    for_each = var.certificate_arn == "" ? [1] : []

    content {
      type             = "forward"
      target_group_arn = aws_lb_target_group.web.arn
    }
  }
}

resource "aws_lb_listener" "https" {
  count = var.certificate_arn == "" ? 0 : 1

  load_balancer_arn = aws_lb.hub.arn
  port              = 443
  protocol          = "HTTPS"
  certificate_arn   = var.certificate_arn

  # TLS 1.2 as the floor. The 1.3 only policies exclude clients Meter has no
  # reason to exclude, and 1.0 and 1.1 are not acceptable in a financial
  # services environment.
  ssl_policy = "ELBSecurityPolicy-TLS13-1-2-2021-06"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web.arn
  }
}

# The API is reached under /api, and so is the OpenAPI document and the health
# endpoint. Everything else is the single page application.
resource "aws_lb_listener_rule" "api" {
  listener_arn = var.certificate_arn == "" ? aws_lb_listener.http.arn : aws_lb_listener.https[0].arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  condition {
    path_pattern {
      values = ["/api/*", "/healthz", "/openapi.json", "/docs", "/docs/*"]
    }
  }
}
