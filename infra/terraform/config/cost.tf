# The estimate, computed rather than asserted, so a diff that changes the type list or the
# region list moves the number a reviewer sees.
#
# **Every figure here is modelled.** No recorder has ever run, ISS-203, so there is no
# measured number to compare with. COST.md carries the working in prose; this is the same
# arithmetic in a form a plan prints.
#
# The assumptions are the estimate. A number with no working is not an estimate, which is
# what TASK-P4-010 asks for, so each one is named and each one is a variable a reviewer can
# disagree with rather than a constant folded into a total.

locals {
  # Assumed, from the fake estate's shape scaled up. The generated estate has five accounts
  # and thirty six resources; a real organization at the scale this project targets has
  # three hundred accounts, and most of them run in two regions rather than eleven.
  assumed_accounts = 300

  # Recorded resources per account and region, across the types in `resource_types.tf`.
  # Assumed at two hundred: a VPC, three subnets, a handful of security groups, the
  # instances and volumes behind one application, and the network interfaces those imply.
  # The network interface count is what dominates, which is why it is in the list rather
  # than assumed away.
  assumed_resources_per_slice = 200

  # How many configuration items each resource produces in a month. One for its existence
  # at the start of recording, plus one per change. Three changes a month is the assumption
  # and it is the least certain number here: a stable estate is nearer one and an estate
  # with autoscaling groups cycling instances is very much more.
  assumed_items_per_resource_month = 4

  # The published price per configuration item recorded, in the regions this stack
  # defaults to. Modelled from the price list at the time of writing, not measured.
  usd_per_configuration_item = 0.003

  active_slices = local.assumed_accounts * length(var.recorder_regions)

  monthly_configuration_items = (
    local.active_slices
    * local.assumed_resources_per_slice
    * local.assumed_items_per_resource_month
  )

  estimated_monthly_usd = local.monthly_configuration_items * local.usd_per_configuration_item

  # What the same estate would cost with `AllSupported = true`, which is the decision this
  # stack exists to avoid making by accident. AWS Config supports several hundred types, and
  # recording all of them multiplies the resource count rather than the type count: the
  # assumption is a factor of six, which is the ratio of everything an account holds to the
  # twenty two types Meter reads.
  all_supported_multiplier = 6

  estimated_monthly_usd_if_all_supported = (
    local.estimated_monthly_usd * local.all_supported_multiplier
  )
}
