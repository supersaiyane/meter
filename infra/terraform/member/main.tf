# Service managed, so it deploys to accounts that do not exist yet.
#
# `auto_deployment` is what makes onboarding automatic: an account vended
# tomorrow gets the collector role without anybody being told about it, and an
# account that leaves the organization has its stack removed. Both halves matter.
# `retain_stacks_on_account_removal = false` is deliberate: a departed account
# keeping a role that trusts our hub is a trust relationship nobody owns.
#
# This requires trusted access between Organizations and CloudFormation, which
# is a management account setting and not something Terraform can turn on from
# here. It is tracked as ISS-002 and is the one external dependency this stack
# has.

resource "aws_cloudformation_stack_set" "collector" {
  name             = "meter-collector-role"
  description      = "Read only collector role for Meter, in every account in the organization."
  permission_model = "SERVICE_MANAGED"
  capabilities     = ["CAPABILITY_NAMED_IAM"]

  template_body = file("${path.module}/collector_role.yaml")

  parameters = {
    HubAccountId    = var.hub_account_id
    HubTaskRoleName = var.hub_task_role_name
    RelayRoleName   = var.relay_role_name
    ExternalId      = var.external_id
    OrganizationId  = var.organization_id
    RoleName        = var.collector_role_name
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

  lifecycle {
    # The parameter is marked NoEcho in the template, so a drift comparison on
    # it compares against a masked value and reports a change on every plan.
    ignore_changes = [parameters["ExternalId"]]
  }
}

# The instances. Separate from the StackSet because CloudFormation models them
# separately: the StackSet is the template, this is where it lands.
#
# IAM is global, so one region deploys the role to the whole account. Deploying
# it to two regions would create the same named role twice and the second would
# fail.
resource "aws_cloudformation_stack_instances" "collector" {
  stack_set_name = aws_cloudformation_stack_set.collector.name
  regions        = [var.region]

  deployment_targets {
    organizational_unit_ids = var.organizational_unit_ids
  }

  operation_preferences {
    max_concurrent_percentage    = var.max_concurrent_percentage
    failure_tolerance_percentage = var.failure_tolerance_percentage
  }
}
