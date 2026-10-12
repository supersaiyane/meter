variable "region" {
  description = "The region the hub runs in. Not the regions it collects from."
  type        = string
  default     = "eu-west-1"
}

variable "env" {
  description = "dev or prod. Appears in every name and in finops:env."
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.env)
    error_message = "env must be dev or prod."
  }
}

variable "owner" {
  description = "The team accountable for this stack."
  type        = string
}

variable "vpc_cidr" {
  description = "The hub VPC. A /20 is 4096 addresses, which is far more than three services need."
  type        = string
  default     = "10.40.0.0/20"
}

variable "availability_zones" {
  description = <<-EOT
    Two zones. Aurora needs a subnet group spanning at least two, and the
    interface endpoints are priced per zone, so a third would add a third of the
    endpoint bill for redundancy the workload does not need.
  EOT
  type        = list(string)
  default     = ["eu-west-1a", "eu-west-1b"]

  validation {
    condition     = length(var.availability_zones) >= 2
    error_message = "Aurora requires a subnet group spanning at least two availability zones."
  }
}

variable "database_min_capacity" {
  description = "Aurora Serverless v2 floor, in ACU. Half an ACU is the smallest AWS accepts."
  type        = number
  default     = 0.5
}

variable "database_max_capacity" {
  description = <<-EOT
    Aurora Serverless v2 ceiling, in ACU.

    Four against a modelled average of two, from `docs/04-DEPLOYMENT.md`. The
    ceiling is a cost control as much as a capacity one: without it a runaway
    query scales the cluster and the first anyone hears of it is the bill.
  EOT
  type        = number
  default     = 4
}

variable "backup_retention_days" {
  description = <<-EOT
    Automated backup retention.

    Set to the shortest table retention window in
    `docs/09-DATA-CLASSIFICATION.md`, which is ninety days for principals and
    operational history. A backup held longer than the table policy holds data
    that policy says was removed, which undoes the policy. It is capped at 35
    by AWS, so 35 it is, and that is below every table window.
  EOT
  type        = number
  default     = 35

  validation {
    condition     = var.backup_retention_days >= 7 && var.backup_retention_days <= 35
    error_message = "AWS allows 1 to 35 days. Meter's floor is 7, and 35 is the ceiling."
  }
}

variable "queue_max_receive_count" {
  description = <<-EOT
    How many times a unit of work is retried before it goes to the dead letter
    queue. Three, matching MAX_DELIVERY_ATTEMPTS in finops_core/constants.py.
    The two must agree or the worker and the queue disagree about what a
    poisoned message is.
  EOT
  type        = number
  default     = 3
}

variable "queue_visibility_timeout_seconds" {
  description = <<-EOT
    Must exceed the worker's claim timeout, or the queue redelivers a unit that
    is still being worked and two workers process it at once. The run ledger
    would catch the duplicate, but paying twice for the API call it already made
    is avoidable.
  EOT
  type        = number
  default     = 900
}

variable "log_retention_days" {
  description = <<-EOT
    Retention on Meter's own log groups, set at creation.

    A log group created without it defaults to never expiring, and a never
    expiring log group is a bill that grows forever and a data retention promise
    that is silently false.
  EOT
  type        = number
  default     = 90
}

variable "collector_role_name" {
  description = <<-EOT
    The role the task role may assume in a member account. Must match
    METER_COLLECTOR_ROLE_NAME and the StackSet in infra/terraform/member.

    It is a name rather than a list of ARNs because the account varies and the
    broker builds the ARN. The name is what keeps the grant narrow: the task
    role may assume this one role in any account, and no other role in any
    account.
  EOT
  type        = string
  default     = "FinOpsCollectorRole"
}

variable "organization_id" {
  description = "Constrains every cross account assume to this organization."
  type        = string

  validation {
    condition     = can(regex("^o-[a-z0-9]{10,32}$", var.organization_id))
    error_message = "organization_id must look like o-abc1234567."
  }
}

variable "org_reader_role_arn" {
  description = <<-EOT
    The management account role, output by infra/terraform/management.

    Empty is valid and means the organization collector runs against LocalStack
    instead of a real management account, which is how development proceeds
    without waiting for management account cooperation. See ISS-002.
  EOT
  type        = string
  default     = ""
}

variable "assistant_model_ids" {
  description = <<-EOT
    Bedrock foundation model identifiers the task role may invoke, ADR-0028.

    Empty is valid and is the default: no model has been chosen, OPEN-10, the role
    grants nothing, and the assistant says it is not enabled. Each identifier is
    named exactly, because a wildcard would grant every model the service ever adds.

    Each one gets an application inference profile tagged finops:module, and the
    task role may reach the model only through it, ISS-230. A call made to the model
    directly is not a resource, so no tag would reach its cost line and the platform
    cost screen could not say what the assistant costs.
  EOT
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for model_id in var.assistant_model_ids :
      length(trimspace(model_id)) > 0 && !strcontains(model_id, "*")
    ])
    error_message = "A model identifier is named exactly. A wildcard grants every model the service adds."
  }
}

variable "assistant_model_in_use" {
  description = <<-EOT
    The one model in assistant_model_ids the API invokes. The stack sets
    METER_ASSISTANT_MODEL_ID on the API task to the ARN of that model's inference
    profile, never to the model identifier, because only a call through the profile
    carries the tag and the task role may reach the model no other way. ISS-230.

    Empty is valid and is the default, and the assistant says it is not enabled. A
    model may be named in assistant_model_ids before it is in use, which is how a
    change of model rolls out: name the new one, apply, point this at it, and drop
    the old one in a later release once no running task uses it. Constraint 12.
  EOT
  type        = string
  default     = ""

  validation {
    condition     = var.assistant_model_in_use == "" || contains(var.assistant_model_ids, var.assistant_model_in_use)
    error_message = "assistant_model_in_use must be one of assistant_model_ids, or there is no profile for it and the task role may not invoke it."
  }
}

variable "metric_namespace" {
  description = "The CloudWatch namespace Meter publishes its own metrics to."
  type        = string
  default     = "Meter"
}

variable "image_tag" {
  description = <<-EOT
    The image every service runs, set by the pipeline to the commit sha.

    Never `latest`. A mutable tag makes a rollback impossible to express: there
    is no way to say "the one from before" when both are called the same thing.
  EOT
  type        = string

  validation {
    condition     = var.image_tag != "latest"
    error_message = "image_tag must not be latest. Use the commit sha, so a rollback names a specific image."
  }
}

variable "api_desired_count" {
  description = "API tasks. Two, so a rolling deploy always leaves one serving."
  type        = number
  default     = 2
}

variable "web_desired_count" {
  description = "Web tasks. Two, for the same reason."
  type        = number
  default     = 2
}

variable "worker_min_count" {
  description = <<-EOT
    Worker floor. Zero is deliberate: collection is a burst once an hour and
    paying for an idle worker for fifty five minutes is paying for nothing.
  EOT
  type        = number
  default     = 0
}

variable "worker_max_count" {
  description = "Worker ceiling. A cost control as much as a capacity one."
  type        = number
  default     = 4
}

variable "certificate_arn" {
  description = <<-EOT
    The ACM certificate for the load balancer.

    Empty means HTTP only, which is acceptable in development and is refused in
    production by a validation below.
  EOT
  type        = string
  default     = ""
}

variable "dispatcher_schedule" {
  description = <<-EOT
    How often the dispatcher runs, as a schedule expression.

    This is not the collection cadence. Cadence is data, in the
    collector_schedule table, per constraint 9 and ADR-0012. This is only how
    often something wakes up to ask which collectors are due, so it has to be at
    least as frequent as the shortest cadence in that table, which is hourly.
  EOT
  type        = string
  default     = "rate(1 hour)"
}

variable "page_topic_arn" {
  description = <<-EOT
    Where a paging alert goes. Empty means the alarms are created without an
    action, which is valid for a development environment and is refused in
    production by a check in observability.tf.

    An alarm without an action is not an alert. It is a coloured square nobody
    is looking at.
  EOT
  type        = string
  default     = ""
}

variable "ticket_topic_arn" {
  description = "Where a non paging alert goes. Same reasoning as page_topic_arn."
  type        = string
  default     = ""
}

variable "platform_cost_anomaly_multiple" {
  description = <<-EOT
    How far above its own thirty day median Meter's daily cost may go before it
    pages. Two, from docs/10-OBSERVABILITY.md.

    It pages rather than raising a ticket because a FinOps tool that quietly
    becomes expensive has no standing left to comment on anyone else's bill.
  EOT
  type        = number
  default     = 2
}

variable "cost_export_version_retention_days" {
  description = <<-EOT
    How long a superseded billing export object is kept. Data Exports restates a
    period in place all month, so every restatement leaves an older version
    behind. Ninety days outlasts the restatement window with room to spare and
    stops the bucket growing without bound, which would make the cost report a
    cost.
  EOT
  type        = number
  default     = 90

  validation {
    condition     = var.cost_export_version_retention_days >= 35
    error_message = "A period can be restated for weeks after it closes, so anything under 35 days can delete a version that is still the live one."
  }
}

variable "athena_bytes_scanned_cutoff" {
  description = <<-EOT
    The most one query may scan, in bytes. Athena bills on bytes scanned, so a
    query that forgets to prune on the billing period partition scans the whole
    table at full price and reads as nothing worse than a slow query until the
    bill arrives. Ten gibibytes is generous for one pruned month and small
    enough that a full scan is refused rather than invoiced.
  EOT
  type        = number
  default     = 10737418240

  validation {
    condition     = var.athena_bytes_scanned_cutoff >= 10485760
    error_message = "Athena refuses a cutoff below ten mebibytes."
  }
}

# --- the network path, TASK-P9-001 and ADR-0035 --------------------------------

variable "global_region" {
  description = <<-EOT
    The Region AWS answers its global services in. Cost Explorer, Organizations, IAM and Cost
    Optimization Hub answer only there, so its endpoint VPC holds theirs. An AWS fact rather than
    a choice, held here so no Region is written inline.
  EOT
  type        = string
  default     = "us-east-1"
}

variable "second_region" {
  description = <<-EOT
    The collection Region other than the hub's own, OPEN-06. The collectors call each member
    account there, through the endpoint VPC endpoints.tf builds in it.
  EOT
  type        = string
  default     = "eu-west-2"

  validation {
    condition     = var.second_region != var.region
    error_message = "second_region is the collection Region that is not the hub's own."
  }
}

variable "global_endpoint_vpc_cidr" {
  description = "The us-east-1 endpoint VPC. Must not overlap the hub or the other endpoint VPC."
  type        = string
  default     = "10.41.0.0/24"
}

variable "second_endpoint_vpc_cidr" {
  description = "The second Region's endpoint VPC. Must not overlap the hub or the other."
  type        = string
  default     = "10.42.0.0/24"
}

variable "relay_package" {
  description = <<-EOT
    The relay's zip, built by `make build-relay` and by the build:relay job, relative to this
    stack. Absent at validate, which is why the hash is taken only when it exists.
  EOT
  type        = string
  default     = "../../../build/relay.zip"
}

variable "relay_role_name" {
  description = <<-EOT
    The relay's role. The member StackSet and the management stack trust it by this name, so the
    three must agree, as they do for the task role.
  EOT
  type        = string
  default     = "FinOpsRelayRole"
}

variable "settings" {
  description = <<-EOT
    Every setting the Python services read that this stack does not derive, by its METER_ name.
    Each becomes an SSM parameter under /meter/<env>/, settings.tf, or an empty environment value
    when it is empty. A test holds this map, the derived names and the secret ones to every field
    of finops_core.config.Settings. TASK-P12-006, ISS-250.
  EOT
  type        = map(string)
}
