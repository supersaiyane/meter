variable "region" {
  description = "Where the aggregator lives and the StackSet is administered from."
  type        = string
  default     = "eu-west-1"
}

variable "owner" {
  description = "The team accountable for this stack, and for the Config bill it creates."
  type        = string
}

variable "organization_id" {
  description = "Used by the aggregator's organization source. o- followed by ten to thirty two characters."
  type        = string

  validation {
    condition     = can(regex("^o-[a-z0-9]{10,32}$", var.organization_id))
    error_message = "organization_id must look like o-abc1234567."
  }
}

variable "aggregator_name" {
  description = "Must match METER_CONFIG_AGGREGATOR on the hub side, or the adapter queries an aggregator that does not exist."
  type        = string
  default     = "meter-organization"
}

variable "recorder_regions" {
  description = <<-DESCRIPTION
    The regions the recorders are deployed into. This is a cost lever, not a completeness
    setting: a region absent here has no configuration items and its graph_coverage row
    stays UNREAD, which is the honest state and is visibly different from empty.
  DESCRIPTION
  type        = list(string)
  default     = ["eu-west-1", "eu-west-2"]

  validation {
    condition     = length(var.recorder_regions) > 0
    error_message = "A recorder in no region records nothing, and the hub would report every slice as unread."
  }
}

variable "home_region" {
  description = <<-DESCRIPTION
    The one region that records global resource types. IAM roles are global, so recording
    them in every region would store the same role once per region and bill for each copy.
  DESCRIPTION
  type        = string
  default     = "eu-west-1"
}

variable "delivery_bucket_name" {
  description = <<-DESCRIPTION
    The bucket the recorders deliver snapshots and history to. Required by Config and
    unused by Meter, which reads the aggregator API rather than the delivered files.
    Named rather than created here because it is a hub concern with its own lifecycle
    policy, and a bucket created by this stack would be deleted by destroying it.
  DESCRIPTION
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.delivery_bucket_name))
    error_message = "delivery_bucket_name must be a valid S3 bucket name."
  }
}

variable "recorder_role_name" {
  description = "The service linked role name Config uses in each member account."
  type        = string
  default     = "AWSServiceRoleForConfig"
}

variable "max_concurrent_percentage" {
  description = "How much of the organization a StackSet operation touches at once."
  type        = number
  default     = 25

  validation {
    condition     = var.max_concurrent_percentage > 0 && var.max_concurrent_percentage <= 100
    error_message = "max_concurrent_percentage must be between 1 and 100."
  }
}

variable "failure_tolerance_percentage" {
  description = <<-DESCRIPTION
    How many accounts may fail before the operation stops. Non zero on purpose: one
    account refusing must not stop the other two hundred and ninety nine from getting a
    recorder, which is constraint 5 applied to a deployment.
  DESCRIPTION
  type        = number
  default     = 10

  validation {
    condition     = var.failure_tolerance_percentage >= 0 && var.failure_tolerance_percentage < 100
    error_message = "failure_tolerance_percentage must be between 0 and 99."
  }
}
