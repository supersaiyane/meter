output "vpc_id" {
  description = "The endpoint VPC, the peer of the hub's peering connection."
  value       = aws_vpc.this.id
}

output "flow_log_group_arn" {
  description = "This VPC's flow log group, which the hub's flow logs role must be able to write."
  value       = aws_cloudwatch_log_group.flow_logs.arn
}

output "endpoints" {
  description = "Each endpoint's hostname and the DNS entry the hub's private hosted zone points it at."
  value = {
    for key, endpoint in aws_vpc_endpoint.this : key => {
      host     = var.endpoints[key].host
      dns_name = endpoint.dns_entry[0].dns_name
      zone_id  = endpoint.dns_entry[0].hosted_zone_id
    }
  }
}
