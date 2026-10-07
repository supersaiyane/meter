# One endpoint VPC: interface endpoints for the services a Region answers, peered to the hub.
#
# TASK-P9-001, ADR-0035. Cross Region PrivateLink does not reach the services the hub calls in
# us-east-1 or in the other collection Region, so each of those Regions has a small VPC holding
# nothing but endpoints. The hub reaches it over a peering connection, and a private hosted zone
# in the hub, root endpoints.tf, resolves each service's ordinary hostname to its endpoint here.
# That is why private DNS is off on these endpoints: it would answer only inside this VPC.
#
# Nothing runs here and nothing leaves: no internet gateway, no NAT, and one route, back to the
# hub. The endpoints accept HTTPS from the hub's addresses and from nowhere else.

terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
    }
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "this" {
  cidr_block           = var.cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = var.name }
}

# Two zones, as the hub's endpoints have, so one zone failing leaves every service reachable.
resource "aws_subnet" "endpoints" {
  count = 2

  vpc_id                  = aws_vpc.this.id
  cidr_block              = cidrsubnet(var.cidr, 1, count.index)
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = false

  tags = { Name = "${var.name}-${data.aws_availability_zones.available.names[count.index]}" }
}

resource "aws_route_table" "this" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = var.name }
}

resource "aws_route_table_association" "endpoints" {
  count = length(aws_subnet.endpoints)

  subnet_id      = aws_subnet.endpoints[count.index].id
  route_table_id = aws_route_table.this.id
}

resource "aws_vpc_peering_connection_accepter" "hub" {
  vpc_peering_connection_id = var.peering_connection_id
  auto_accept               = true

  tags = { Name = "${var.name}-hub" }
}

# The only route here, and it leads back to the hub.
resource "aws_route" "to_hub" {
  route_table_id            = aws_route_table.this.id
  destination_cidr_block    = var.hub_cidr
  vpc_peering_connection_id = var.peering_connection_id

  depends_on = [aws_vpc_peering_connection_accepter.hub]
}

resource "aws_security_group" "endpoints" {
  name        = "${var.name}-endpoints"
  description = "Interface endpoints, reachable from the hub only."
  vpc_id      = aws_vpc.this.id

  tags = { Name = "${var.name}-endpoints" }
}

resource "aws_vpc_security_group_ingress_rule" "from_hub" {
  security_group_id = aws_security_group.endpoints.id
  description       = "HTTPS from the hub across the peering. The endpoint itself enforces IAM."
  cidr_ipv4         = var.hub_cidr
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

resource "aws_vpc_endpoint" "this" {
  for_each = var.endpoints

  vpc_id             = aws_vpc.this.id
  service_name       = each.value.service
  vpc_endpoint_type  = "Interface"
  subnet_ids         = aws_subnet.endpoints[*].id
  security_group_ids = [aws_security_group.endpoints.id]
  # Off, because it would answer only inside this VPC. The hub resolves these by its own
  # private hosted zones instead.
  private_dns_enabled = false

  tags = { Name = "${var.name}-${replace(each.key, ".", "-")}" }
}

# Flow logs, as the hub has, so a call that reached an endpoint here is on a record somewhere.
# The log group is in this Region, so its key is too.
resource "aws_kms_key" "flow_logs" {
  description         = "${var.name} flow logs."
  enable_key_rotation = true
  policy              = data.aws_iam_policy_document.flow_logs_key.json
}

resource "aws_cloudwatch_log_group" "flow_logs" {
  name              = "/meter/${var.name}/vpc-flow-logs"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.flow_logs.arn
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_partition" "current" {}

data "aws_iam_policy_document" "flow_logs_key" {
  statement {
    sid       = "TheAccountAdministersTheKey"
    effect    = "Allow"
    actions   = ["kms:*"]
    resources = ["*"]

    principals {
      type        = "AWS"
      identifiers = ["arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }

  statement {
    sid    = "CloudWatchLogsUsesTheKey"
    effect = "Allow"
    actions = [
      "kms:Encrypt",
      "kms:Decrypt",
      "kms:ReEncrypt*",
      "kms:GenerateDataKey*",
      "kms:DescribeKey",
    ]
    resources = ["*"]

    principals {
      type        = "Service"
      identifiers = ["logs.${data.aws_region.current.region}.amazonaws.com"]
    }
  }
}

resource "aws_flow_log" "this" {
  vpc_id          = aws_vpc.this.id
  traffic_type    = "ALL"
  iam_role_arn    = var.flow_logs_role_arn
  log_destination = aws_cloudwatch_log_group.flow_logs.arn

  tags = { Name = "${var.name}-flow-logs" }
}
