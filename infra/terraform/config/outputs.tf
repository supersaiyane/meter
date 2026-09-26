output "aggregator_name" {
  description = "Set METER_CONFIG_AGGREGATOR on the hub to this, or the adapter queries an aggregator that does not exist."
  value       = aws_config_configuration_aggregator.organization.name
}

output "recorded_resource_type_count" {
  description = <<-DESCRIPTION
    How many types the recorders record. The number COST.md's estimate is computed from, so
    a diff that changes the list changes this output and a reviewer sees the cost move.
  DESCRIPTION
  value       = length(local.recorded_resource_types)
}

output "recorded_resource_types" {
  description = "The list itself, so an operator can compare it with what a recorder reports."
  value       = local.recorded_resource_types
}

output "recorder_regions" {
  description = <<-DESCRIPTION
    Where recorders were deployed. A region absent here has no configuration items and its
    graph_coverage row stays UNREAD, which is visibly different from empty.
  DESCRIPTION
  value       = var.recorder_regions
}

output "estimated_monthly_usd" {
  description = <<-DESCRIPTION
    The modelled monthly cost of this stack, from COST.md. Modelled, not measured: no
    recorder has ever run. It is an output rather than only a document so a plan prints it,
    and so the number moves in a diff when the type list or the region list does.
  DESCRIPTION
  value       = local.estimated_monthly_usd
}
