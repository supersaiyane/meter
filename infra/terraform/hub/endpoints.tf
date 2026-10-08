# The endpoint VPCs: one in us-east-1, for the services that answer only there, and one in the
# other collection Region. Each is peered to the hub. TASK-P9-001, ADR-0035, P9 spec 5.1.
#
# Cross Region PrivateLink does not reach these services, so each Region the hub calls has its
# own endpoints, in modules/endpoint_vpc. A private hosted zone here, one per service, resolves
# the hostname an SDK calls to the endpoint across the peering, so no client is configured with
# an endpoint URL and none can bypass this by forgetting one. The hub keeps no route out: its
# private route table gains a route to each endpoint VPC and nothing else.
#
# A Region added to OPEN-06 needs a provider, a module call and a peering here, because Terraform
# cannot make a provider per item of a list. `tests/contract/test_network_paths.py` fails until
# every service the adapters call in it has an endpoint.

locals {
  # The services that answer only in us-east-1, or only there among the Regions Meter uses.
  # Organizations and IAM have one global endpoint there; Cost Explorer and Cost Optimization
  # Hub answer nowhere else; the Price List Query API answers in three Regions, one of them this.
  global_endpoints = {
    ce = {
      service = "com.amazonaws.${var.global_region}.ce"
      host    = "ce.${var.global_region}.amazonaws.com"
    }
    organizations = {
      service = "com.amazonaws.${var.global_region}.organizations"
      host    = "organizations.${var.global_region}.amazonaws.com"
    }
    iam = {
      service = "com.amazonaws.iam"
      host    = "iam.amazonaws.com"
    }
    cost-optimization-hub = {
      service = "com.amazonaws.${var.global_region}.cost-optimization-hub"
      host    = "cost-optimization-hub.${var.global_region}.amazonaws.com"
    }
    pricing = {
      service = "com.amazonaws.${var.global_region}.pricing.api"
      host    = "api.pricing.${var.global_region}.amazonaws.com"
    }
  }

  # What the collectors call in each member account in every collection Region, by the name the
  # endpoint service and its hostname share. The hub's own Region has these in network.tf.
  collection_services = [
    "ec2",
    "monitoring",
    "logs",
    "cloudtrail",
    "servicequotas",
    "compute-optimizer",
  ]
  second_endpoints = {
    for service in local.collection_services : service => {
      service = "com.amazonaws.${var.second_region}.${service}"
      host    = "${service}.${var.second_region}.amazonaws.com"
    }
  }

  # One private hosted zone per endpoint, keyed so the keys are known before anything exists.
  peered_hosts = merge(
    { for key, endpoint in local.global_endpoints : "global-${key}" => { vpc = "global", key = key, host = endpoint.host } },
    { for key, endpoint in local.second_endpoints : "second-${key}" => { vpc = "second", key = key, host = endpoint.host } },
  )
}

# --- us-east-1 ----------------------------------------------------------------

resource "aws_vpc_peering_connection" "global" {
  vpc_id      = aws_vpc.hub.id
  peer_vpc_id = module.global_endpoints.vpc_id
  peer_region = var.global_region

  tags = { Name = "${local.name}-global-endpoints" }
}

module "global_endpoints" {
  source    = "./modules/endpoint_vpc"
  providers = { aws = aws.global }

  name                  = "${local.name}-global-endpoints"
  cidr                  = var.global_endpoint_vpc_cidr
  hub_cidr              = var.vpc_cidr
  peering_connection_id = aws_vpc_peering_connection.global.id
  endpoints             = local.global_endpoints
  flow_logs_role_arn    = aws_iam_role.flow_logs.arn
  log_retention_days    = var.log_retention_days
}

resource "aws_route" "to_global_endpoints" {
  route_table_id            = aws_route_table.private.id
  destination_cidr_block    = var.global_endpoint_vpc_cidr
  vpc_peering_connection_id = aws_vpc_peering_connection.global.id
}

# --- the other collection Region ------------------------------------------------

resource "aws_vpc_peering_connection" "second" {
  vpc_id      = aws_vpc.hub.id
  peer_vpc_id = module.second_endpoints.vpc_id
  peer_region = var.second_region

  tags = { Name = "${local.name}-second-endpoints" }
}

module "second_endpoints" {
  source    = "./modules/endpoint_vpc"
  providers = { aws = aws.second }

  name                  = "${local.name}-second-endpoints"
  cidr                  = var.second_endpoint_vpc_cidr
  hub_cidr              = var.vpc_cidr
  peering_connection_id = aws_vpc_peering_connection.second.id
  endpoints             = local.second_endpoints
  flow_logs_role_arn    = aws_iam_role.flow_logs.arn
  log_retention_days    = var.log_retention_days
}

resource "aws_route" "to_second_endpoints" {
  route_table_id            = aws_route_table.private.id
  destination_cidr_block    = var.second_endpoint_vpc_cidr
  vpc_peering_connection_id = aws_vpc_peering_connection.second.id
}

# --- names ----------------------------------------------------------------------

locals {
  peered_endpoints = {
    global = module.global_endpoints.endpoints
    second = module.second_endpoints.endpoints
  }
}

# Each hostname answered inside the hub by the endpoint across the peering. A zone per hostname
# rather than one per Region, because a zone named for a whole Region would answer every other
# service in it with nothing.
resource "aws_route53_zone" "endpoint" {
  for_each = local.peered_hosts

  name    = each.value.host
  comment = "Resolves ${each.value.host} to its endpoint in ${local.name}-${each.value.vpc}-endpoints. ADR-0035."

  vpc {
    vpc_id     = aws_vpc.hub.id
    vpc_region = var.region
  }
}

resource "aws_route53_record" "endpoint" {
  for_each = local.peered_hosts

  zone_id = aws_route53_zone.endpoint[each.key].zone_id
  name    = each.value.host
  type    = "A"

  alias {
    name                   = local.peered_endpoints[each.value.vpc][each.value.key].dns_name
    zone_id                = local.peered_endpoints[each.value.vpc][each.value.key].zone_id
    evaluate_target_health = false
  }
}
