# The aggregator, in the payer account. One query surface over every account and region,
# which is the whole reason FEAT-030 reads Config this way rather than assuming a role
# three hundred times: `finops_providers/aws/config_inventory.py` holds one client.
#
# `all_regions = true` on the organization source, and it is not a contradiction with the
# selective recording in `resource_types.tf`. The aggregator aggregates whatever exists;
# the recorders decide what exists. A region with no recorder contributes nothing and the
# aggregator costs nothing for it, which is why the cost lever is the recorder list and
# not this flag.
resource "aws_config_configuration_aggregator" "organization" {
  name = var.aggregator_name

  organization_aggregation_source {
    all_regions = true
    role_arn    = aws_iam_role.aggregator.arn
  }

  depends_on = [aws_iam_role_policy_attachment.aggregator]
}

# The role the aggregator assumes to read the organization. AWS publishes a managed
# policy for exactly this, and using it rather than a hand written one means a new Config
# API that the aggregator needs does not become an outage while somebody edits a policy.
resource "aws_iam_role" "aggregator" {
  name = "${var.aggregator_name}-aggregator"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "config.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "aggregator" {
  role       = aws_iam_role.aggregator.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSConfigRoleForOrganizations"
}

# The recorders, as a service managed StackSet, for the same reason the collector role is
# one: an account vended tomorrow gets a recorder without anybody being told, and an
# account that leaves has its recorder removed. A recorder left behind in a departed
# account is a bill nobody owns.
resource "aws_cloudformation_stack_set" "recorders" {
  name             = "meter-config-recorder"
  description      = "Selective AWS Config recording for Meter, in every account in the organization."
  permission_model = "SERVICE_MANAGED"
  capabilities     = ["CAPABILITY_IAM"]

  template_body = file("${path.module}/recorder.yaml")

  parameters = {
    # The list, joined once here. The recorders read exactly what `resource_types.tf`
    # declares, so the count in COST.md and the count that bills are the same count.
    RecordedResourceTypes = join(",", local.recorded_resource_types)
    DeliveryBucketName    = var.delivery_bucket_name
    RecorderRoleName      = var.recorder_role_name
    HomeRegion            = var.home_region
    FinOpsOwner           = var.owner
  }

  auto_deployment {
    enabled                          = true
    retain_stacks_on_account_removal = false
  }

  operation_preferences {
    max_concurrent_percentage    = var.max_concurrent_percentage
    failure_tolerance_percentage = var.failure_tolerance_percentage
    region_concurrency_type      = "PARALLEL"
  }
}

# Where the recorders land. Separate from the StackSet because CloudFormation models them
# separately, and because the region list is the cost lever: a region added here adds its
# whole estate to the bill.
resource "aws_cloudformation_stack_instances" "recorders" {
  stack_set_name = aws_cloudformation_stack_set.recorders.name
  regions        = var.recorder_regions

  deployment_targets {
    organizational_unit_ids = [var.organization_id]
  }
}
