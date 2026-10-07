variable "region" {
  description = "Where the StackSet is administered from. The stacks themselves are IAM, which is global."
  type        = string
  default     = "eu-west-1"
}

variable "owner" {
  description = "The team accountable for this stack."
  type        = string
}

variable "hub_account_id" {
  description = "The account Meter's hub runs in."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.hub_account_id))
    error_message = "hub_account_id must be a 12 digit AWS account id."
  }
}

variable "hub_task_role_name" {
  description = "The exact hub role permitted to assume the collector role."
  type        = string
  default     = "FinOpsHubTaskRole"
}

variable "relay_role_name" {
  description = "The hub's relay role, ADR-0035, also permitted to assume the collector role."
  type        = string
  default     = "FinOpsRelayRole"
}

variable "collector_role_name" {
  description = "Must match METER_COLLECTOR_ROLE_NAME on the hub side."
  type        = string
  default     = "FinOpsCollectorRole"
}

variable "organization_id" {
  description = "Used in aws:PrincipalOrgID. o- followed by ten to thirty two characters."
  type        = string

  validation {
    condition     = can(regex("^o-[a-z0-9]{10,32}$", var.organization_id))
    error_message = "organization_id must look like o-abc1234567."
  }
}

variable "organizational_unit_ids" {
  description = <<-EOT
    Where the StackSet deploys. The organization root deploys everywhere,
    including accounts created later, which is the point.

    Narrow it to specific organizational units only when a part of the
    organization is deliberately out of scope, and expect onboarding of a new
    account in an excluded unit to become a human step again.
  EOT
  type        = list(string)
}

variable "external_id" {
  description = "Passed at apply time, never committed. See the management stack."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.external_id) >= 32
    error_message = "external_id must be at least 32 characters."
  }
}

variable "max_concurrent_percentage" {
  description = <<-EOT
    How much of the organization the StackSet updates at once.

    Twenty percent rather than a hundred, so a template that fails in a way
    CloudFormation does not catch reaches a fifth of the organization before
    the failure tolerance stops it.
  EOT
  type        = number
  default     = 20
}

variable "failure_tolerance_percentage" {
  description = "Fraction of accounts that may fail before the whole operation stops."
  type        = number
  default     = 5
}
