output "stack_set_id" {
  description = "For the operator checking a rollout in the console."
  value       = aws_cloudformation_stack_set.collector.stack_set_id
}

output "collector_role_name" {
  description = "Goes into METER_COLLECTOR_ROLE_NAME on the hub side. The two must agree."
  value       = var.collector_role_name
}
