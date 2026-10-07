variable "name" {
  description = "Names every resource here, meter-<env>-<role>."
  type        = string
}

variable "cidr" {
  description = "This VPC's addresses. A /24 is far more than a handful of endpoint interfaces need."
  type        = string
}

variable "hub_cidr" {
  description = "The hub VPC, the one place these endpoints accept traffic from."
  type        = string
}

variable "peering_connection_id" {
  description = "The peering the hub requested, accepted here."
  type        = string
}

variable "endpoints" {
  description = <<-EOT
    The interface endpoints, by short name: the service to create one for, and the hostname a
    client calls it by, which the hub's private hosted zone resolves to the endpoint.
  EOT
  type = map(object({
    service = string
    host    = string
  }))
}

variable "flow_logs_role_arn" {
  description = "The hub's flow logs role, which may write to this VPC's log group too."
  type        = string
}

variable "log_retention_days" {
  description = "Retention on this VPC's flow logs, the hub's own setting."
  type        = number
}
