# Private subnets and interface endpoints. No NAT Gateway.
#
# `docs/04-DEPLOYMENT.md` records that this was once justified on cost and that
# the justification was wrong: NAT is cheaper below roughly 1,560 GB per month
# and Meter's egress is nowhere near that. The reasoning was corrected and the
# conclusion kept, on two grounds that do hold.
#
# A NAT Gateway gives every task a route to the whole internet. A collector that
# only ever calls AWS APIs does not need one, and a container that cannot reach
# the internet cannot exfiltrate to it. Endpoints also have no single point of
# failure per zone, which a NAT Gateway is.
#
# The consequence is real and worth stating: adding a dependency that talks to a
# non AWS endpoint means adding an endpoint or a proxy, not just writing the
# call. That is a design question worth being forced to answer.

locals {
  name = "meter-${var.env}"

  # Two /24s for the private subnets and two /26s for the public ones. Public
  # exists only for the load balancer, which needs a handful of addresses.
  private_cidrs = [for i, _ in var.availability_zones : cidrsubnet(var.vpc_cidr, 4, i)]
  public_cidrs  = [for i, _ in var.availability_zones : cidrsubnet(var.vpc_cidr, 6, i + 8)]

  # Every AWS service the tasks call in the hub's own Region. This list once said it was
  # every service the tasks call, and held six, while the collectors called about fifteen
  # more, ISS-242. The services that answer only in us-east-1, Cost Explorer among them, are
  # reached through the endpoint VPC there, and calls into the other collection Region through
  # the one there, both in endpoints.tf. Budgets, Support and Invoicing have no interface
  # endpoint at all and go through the relay, relay.tf. ADR-0035.
  # `tests/contract/test_network_paths.py` holds every service the adapters call to one of
  # those paths, so a collector that calls something new fails a test, not a deploy.
  interface_endpoints = [
    # The tasks themselves.
    "sts",
    "sqs",
    "secretsmanager",
    "logs",
    "ecr.api",
    "ecr.dkr",
    # The collectors, TASK-P9-001.
    "ec2",
    "monitoring",
    "cloudtrail",
    "servicequotas",
    "compute-optimizer",
    "athena",
    "config",
    "grafana",
    "bedrock-runtime",
    # The relay is invoked through this one, so the hub still has no route out.
    "lambda",
  ]

  # Where the relay writes its answers in the data bucket. Equal to `PREFIX` in
  # finops_relay/relay.py, held by the same test.
  relay_prefix = "relay"
}

resource "aws_vpc" "hub" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = local.name }
}

resource "aws_subnet" "private" {
  count = length(var.availability_zones)

  vpc_id            = aws_vpc.hub.id
  cidr_block        = local.private_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]

  # Stated rather than left to the default, so a later edit that wants a public
  # task has to say so in the diff.
  map_public_ip_on_launch = false

  tags = { Name = "${local.name}-private-${var.availability_zones[count.index]}" }
}

resource "aws_subnet" "public" {
  count = length(var.availability_zones)

  vpc_id                  = aws_vpc.hub.id
  cidr_block              = local.public_cidrs[count.index]
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = false

  tags = { Name = "${local.name}-public-${var.availability_zones[count.index]}" }
}

resource "aws_internet_gateway" "hub" {
  vpc_id = aws_vpc.hub.id
  tags   = { Name = local.name }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.hub.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.hub.id
  }

  tags = { Name = "${local.name}-public" }
}

resource "aws_route_table_association" "public" {
  count = length(aws_subnet.public)

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# The private route table has no default route, deliberately. Everything the
# tasks reach, they reach through an endpoint in this file.
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.hub.id
  tags   = { Name = "${local.name}-private" }
}

resource "aws_route_table_association" "private" {
  count = length(aws_subnet.private)

  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# --- endpoints ---------------------------------------------------------------

resource "aws_security_group" "endpoints" {
  name        = "${local.name}-endpoints"
  description = "Interface endpoints. Reachable from inside the VPC only."
  vpc_id      = aws_vpc.hub.id

  tags = { Name = "${local.name}-endpoints" }
}

resource "aws_vpc_security_group_ingress_rule" "endpoints_https" {
  security_group_id = aws_security_group.endpoints.id
  description       = "HTTPS from anywhere inside the VPC. The endpoint itself enforces IAM."
  cidr_ipv4         = aws_vpc.hub.cidr_block
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

resource "aws_vpc_endpoint" "interface" {
  for_each = toset(local.interface_endpoints)

  vpc_id              = aws_vpc.hub.id
  service_name        = "com.amazonaws.${var.region}.${each.value}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.endpoints.id]
  private_dns_enabled = true

  tags = { Name = "${local.name}-${replace(each.value, ".", "-")}" }
}

# S3 is a gateway endpoint, which is free and attaches to a route table rather
# than a subnet. ECR pulls image layers from S3, so this is required for a task
# to start at all, not only for the object storage in storage.tf.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.hub.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]

  tags = { Name = "${local.name}-s3" }
}

# Flow logs, rejects and accepts both.
#
# This is what turns "the tasks have no route to the internet" from a claim into
# something a reviewer can check. It is also the only record of an attempted
# connection that a security group refused, which is exactly the evidence needed
# when the question is whether a container tried to reach somewhere it should
# not have.

resource "aws_cloudwatch_log_group" "flow_logs" {
  name              = "/meter/${var.env}/vpc-flow-logs"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.logs.arn
}

data "aws_iam_policy_document" "flow_logs_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["vpc-flow-logs.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

data "aws_iam_policy_document" "flow_logs" {
  statement {
    sid    = "WriteFlowLogs"
    effect = "Allow"

    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogStreams",
    ]

    resources = [
      "${aws_cloudwatch_log_group.flow_logs.arn}:*",
      "${module.global_endpoints.flow_log_group_arn}:*",
      "${module.second_endpoints.flow_log_group_arn}:*",
    ]
  }
}

resource "aws_iam_role" "flow_logs" {
  name               = "FinOpsHubFlowLogsRole"
  description        = "Lets VPC Flow Logs write to one log group, and nothing else."
  assume_role_policy = data.aws_iam_policy_document.flow_logs_assume.json
}

resource "aws_iam_role_policy" "flow_logs" {
  name   = "WriteFlowLogs"
  role   = aws_iam_role.flow_logs.id
  policy = data.aws_iam_policy_document.flow_logs.json
}

resource "aws_flow_log" "hub" {
  vpc_id          = aws_vpc.hub.id
  traffic_type    = "ALL"
  iam_role_arn    = aws_iam_role.flow_logs.arn
  log_destination = aws_cloudwatch_log_group.flow_logs.arn

  tags = { Name = "${local.name}-flow-logs" }
}
