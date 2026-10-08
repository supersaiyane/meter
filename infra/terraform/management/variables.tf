variable "region" {
  description = "Where the provider talks to IAM. IAM is global, so this only decides the endpoint."
  type        = string
  default     = "eu-west-1"
}

variable "owner" {
  description = "The team accountable for this stack. Ends up on every resource as a tag."
  type        = string
}

variable "hub_account_id" {
  description = <<-EOT
    The account Meter's hub runs in. The only principal this role trusts.

    An account id rather than a role ARN would trust every principal in that
    account, so the trust policy names the role. See `hub_task_role_name`.
  EOT
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.hub_account_id))
    error_message = "hub_account_id must be a 12 digit AWS account id."
  }
}

variable "hub_task_role_name" {
  description = "The ECS task role in the hub account. Named, not wildcarded."
  type        = string
  default     = "FinOpsHubTaskRole"
}

variable "hub_relay_role_name" {
  description = <<-EOT
    The relay's role in the hub account, which makes the payer's Budgets and Invoicing reads
    outside the hub's VPC, ADR-0035. Named, not wildcarded, and equal to the hub's
    relay_role_name.
  EOT
  type        = string
  default     = "FinOpsRelayRole"
}

variable "external_id" {
  description = <<-EOT
    The shared secret required on every assume. Held in Secrets Manager on the
    hub side and passed in here, never committed to a tfvars file in version
    control.

    It is the second half of the confused deputy defence. The first half is
    naming the hub role in the trust policy.
  EOT
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.external_id) >= 32
    error_message = "external_id must be at least 32 characters. A guessable ExternalId is not a control."
  }
}

variable "role_name" {
  description = "The role Meter assumes to read the organization tree."
  type        = string
  default     = "FinOpsOrgReaderRole"
}

variable "max_session_duration_seconds" {
  description = <<-EOT
    How long an assumed session lasts. One hour, because the credential broker
    refreshes five minutes before expiry and a longer session only widens the
    window a leaked credential is useful for.
  EOT
  type        = number
  default     = 3600

  validation {
    condition     = var.max_session_duration_seconds >= 900 && var.max_session_duration_seconds <= 43200
    error_message = "AWS accepts 900 to 43200 seconds."
  }
}
