# Ten alarms, four of which page. Every one names an action, and every paging
# one has a runbook in docs/runbooks/ written with it rather than after it.
#
# `docs/10-OBSERVABILITY.md` is the specification. Two of the four paging alerts
# are unusual and both are deliberate: collection stalled pages because silent
# staleness is the failure mode of this product, and platform cost anomaly pages
# because a FinOps tool that quietly becomes expensive has no standing left to
# comment on anyone else's bill. The other two, widespread staleness and API
# 5xx, page for ordinary reasons.
#
# An alert that does not lead to an action is deleted rather than downgraded.

locals {
  page   = var.page_topic_arn == "" ? [] : [var.page_topic_arn]
  ticket = var.ticket_topic_arn == "" ? [] : [var.ticket_topic_arn]

  # Named here so the alarm descriptions and the runbooks cannot drift apart:
  # every paging alarm's description ends with the path to its runbook, and a
  # test asserts that the file exists.
  runbooks = {
    collection_stalled    = "docs/runbooks/collection-stalled.md"
    collection_widespread = "docs/runbooks/collection-stalled.md"
    api_5xx               = "docs/runbooks/api-5xx.md"
    platform_cost_anomaly = "docs/runbooks/platform-cost-anomaly.md"
  }
}

# An alarm with no action is a coloured square nobody looks at. Development may
# have no topic wired up yet; production may not.
resource "terraform_data" "alerting_is_wired_up_in_production" {
  lifecycle {
    precondition {
      condition     = var.env != "prod" || (var.page_topic_arn != "" && var.ticket_topic_arn != "")
      error_message = "Production needs both an alert topic and a ticket topic. An alarm with no action is not an alert."
    }
  }
}

# --- SLO 1, collection freshness. The one this product exists to catch --------

resource "aws_cloudwatch_metric_alarm" "collection_stalled" {
  alarm_name        = "${local.name}-collection-stalled"
  alarm_description = <<-EOT
    PAGE. A collector and scope pair has not advanced its watermark for three
    times its cadence. Read sync_error for the typed cause before anything else:
    AccessDenied means the member role broke, Throttled means back off,
    NotOptedIn means the account never had the service enabled.

    Runbook: ${local.runbooks.collection_stalled}
  EOT

  namespace   = var.metric_namespace
  metric_name = "StalledScopes"
  statistic   = "Maximum"
  period      = 300

  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  evaluation_periods  = 2
  datapoints_to_alarm = 2

  # A missing datapoint is a stalled metric publisher, which is the same class
  # of failure as a stalled collector and must not read as healthy. This is the
  # setting that makes the alarm survive its own telemetry stopping.
  treat_missing_data = "breaching"

  alarm_actions = local.page
  ok_actions    = local.page
}

resource "aws_cloudwatch_metric_alarm" "collection_stalled_widespread" {
  alarm_name        = "${local.name}-collection-stalled-widespread"
  alarm_description = <<-EOT
    PAGE. More than five percent of scopes are stalled at once. This is almost
    always the hub role, a credential, or an organization wide change. Do not
    chase individual accounts.

    Runbook: ${local.runbooks.collection_widespread}
  EOT

  namespace   = var.metric_namespace
  metric_name = "StalledScopePercent"
  statistic   = "Maximum"
  period      = 300

  comparison_operator = "GreaterThanThreshold"
  threshold           = 5
  evaluation_periods  = 2
  datapoints_to_alarm = 2
  treat_missing_data  = "breaching"

  alarm_actions = local.page
  ok_actions    = local.page
}

# --- SLO 2, collection success ------------------------------------------------

# PARTIAL is success at the run level and is not counted here. A run that
# completed while one account returned AccessDenied did its job, and the account
# level failure is SLO 1's problem through the watermark that did not advance.
# Conflating the two would make this fire constantly at three hundred accounts
# and it would be muted inside a week.
resource "aws_cloudwatch_metric_alarm" "run_failure_rate" {
  alarm_name        = "${local.name}-run-failure-rate"
  alarm_description = "TICKET. FAILED runs above one percent over an hour. Read the typed errors, a single cause usually explains all of them."

  comparison_operator = "GreaterThanThreshold"
  threshold           = 1
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"

  metric_query {
    id          = "failed"
    return_data = false

    metric {
      namespace   = var.metric_namespace
      metric_name = "RunsFailed"
      stat        = "Sum"
      period      = 3600
    }
  }

  metric_query {
    id          = "total"
    return_data = false

    metric {
      namespace   = var.metric_namespace
      metric_name = "RunsTotal"
      stat        = "Sum"
      period      = 3600
    }
  }

  metric_query {
    id          = "rate"
    label       = "Failed runs, percent"
    expression  = "IF(total > 0, 100 * failed / total, 0)"
    return_data = true
  }

  alarm_actions = local.ticket
}

resource "aws_cloudwatch_metric_alarm" "dead_letter_queue" {
  alarm_name        = "${local.name}-dead-letter-queue"
  alarm_description = "TICKET. A unit of work failed three times. Inspect before purging: the queue is the only record of it."

  namespace   = "AWS/SQS"
  metric_name = "ApproximateNumberOfMessagesVisible"
  statistic   = "Maximum"
  period      = 300

  dimensions = { QueueName = aws_sqs_queue.dead_letter.name }

  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"

  alarm_actions = local.ticket
}

resource "aws_cloudwatch_metric_alarm" "retention_job_absent" {
  alarm_name        = "${local.name}-retention-job-absent"
  alarm_description = <<-EOT
    TICKET. A retention job has not run for forty eight hours, so data is being
    kept past policy. See docs/09-DATA-CLASSIFICATION.md.

    Forty eight hours rather than twenty four, because the daily jobs would
    otherwise alarm on a single missed run, and the cost of one late retention
    pass is nothing.
  EOT

  namespace   = var.metric_namespace
  metric_name = "RetentionJobAgeSeconds"
  statistic   = "Maximum"
  period      = 3600

  comparison_operator = "GreaterThanThreshold"
  threshold           = 172800
  evaluation_periods  = 1
  treat_missing_data  = "breaching"

  alarm_actions = local.ticket
}

# --- SLO 3 and 4, ordinary service health -------------------------------------

resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name        = "${local.name}-api-5xx"
  alarm_description = <<-EOT
    PAGE. Server errors above one percent over five minutes.

    Runbook: ${local.runbooks.api_5xx}
  EOT

  comparison_operator = "GreaterThanThreshold"
  threshold           = 1
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"

  metric_query {
    id          = "errors"
    return_data = false

    metric {
      namespace   = "AWS/ApplicationELB"
      metric_name = "HTTPCode_Target_5XX_Count"
      stat        = "Sum"
      period      = 300
      dimensions = {
        LoadBalancer = aws_lb.hub.arn_suffix
        TargetGroup  = aws_lb_target_group.api.arn_suffix
      }
    }
  }

  metric_query {
    id          = "requests"
    return_data = false

    metric {
      namespace   = "AWS/ApplicationELB"
      metric_name = "RequestCount"
      stat        = "Sum"
      period      = 300
      dimensions = {
        LoadBalancer = aws_lb.hub.arn_suffix
        TargetGroup  = aws_lb_target_group.api.arn_suffix
      }
    }
  }

  metric_query {
    id          = "rate"
    label       = "Server errors, percent"
    expression  = "IF(requests > 0, 100 * errors / requests, 0)"
    return_data = true
  }

  alarm_actions = local.page
  ok_actions    = local.page
}

resource "aws_cloudwatch_metric_alarm" "api_latency" {
  alarm_name        = "${local.name}-api-latency"
  alarm_description = <<-EOT
    TICKET. p95 above 1.5 seconds over fifteen minutes. This is the ADR-0003
    trigger to reconsider the serving layer. Capture the query plan before it
    resolves itself, because it usually does and then nobody can reproduce it.
  EOT

  namespace          = "AWS/ApplicationELB"
  metric_name        = "TargetResponseTime"
  extended_statistic = "p95"
  period             = 900

  dimensions = {
    LoadBalancer = aws_lb.hub.arn_suffix
    TargetGroup  = aws_lb_target_group.api.arn_suffix
  }

  comparison_operator = "GreaterThanThreshold"
  threshold           = 1.5
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"

  alarm_actions = local.ticket
}

resource "aws_cloudwatch_metric_alarm" "database_connections" {
  alarm_name        = "${local.name}-database-connections"
  alarm_description = "TICKET. Above eighty percent of maximum connections. Usually a leaked session in a collector."

  namespace   = "AWS/RDS"
  metric_name = "DatabaseConnections"
  statistic   = "Maximum"
  period      = 300

  dimensions = { DBClusterIdentifier = aws_rds_cluster.hub.cluster_identifier }

  # Aurora Serverless v2 scales max_connections with capacity. At the ceiling of
  # var.database_max_capacity ACU the limit is roughly 190 per ACU, so this is
  # eighty percent of the ceiling rather than of whatever it happens to be right
  # now. Alarming on the current limit would move the threshold under itself
  # every time the cluster scaled.
  comparison_operator = "GreaterThanThreshold"
  threshold           = floor(var.database_max_capacity * 190 * 0.8)
  evaluation_periods  = 2
  treat_missing_data  = "notBreaching"

  alarm_actions = local.ticket
}

# --- the platform metering itself ---------------------------------------------

resource "aws_cloudwatch_metric_alarm" "platform_cost_anomaly" {
  alarm_name        = "${local.name}-platform-cost-anomaly"
  alarm_description = <<-EOT
    PAGE. Meter's own daily cost is above ${var.platform_cost_anomaly_multiple}
    times its thirty day median. Meter is doing to itself what it exists to
    prevent. Check Athena scanned bytes and GetMetricData volume first.

    Runbook: ${local.runbooks.platform_cost_anomaly}
  EOT

  comparison_operator = "GreaterThanUpperThreshold"
  threshold_metric_id = "band"
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"

  metric_query {
    id          = "cost"
    return_data = true

    metric {
      namespace   = var.metric_namespace
      metric_name = "PlatformDailyCost"
      stat        = "Maximum"
      period      = 86400
    }
  }

  # Anomaly detection rather than a fixed threshold, because Meter's cost is
  # expected to grow with the number of accounts it reads. A fixed number would
  # be wrong within a quarter and would then be raised rather than investigated.
  metric_query {
    id          = "band"
    expression  = "ANOMALY_DETECTION_BAND(cost, ${var.platform_cost_anomaly_multiple})"
    label       = "Expected range"
    return_data = true
  }

  alarm_actions = local.page
  ok_actions    = local.page
}

resource "aws_cloudwatch_metric_alarm" "security_posture_regressed" {
  alarm_name        = "${local.name}-security-posture-regressed"
  alarm_description = "TICKET. The nightly scan found something. See docs/05-SECURITY.md."

  namespace   = var.metric_namespace
  metric_name = "SecurityFindings"
  statistic   = "Maximum"
  period      = 86400

  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  evaluation_periods  = 1

  # Not breaching on a missing datapoint, unlike the collection alarms. The
  # nightly scan runs in the pipeline rather than in this account, so an absent
  # datapoint means the pipeline did not run, which the pipeline itself reports.
  treat_missing_data = "notBreaching"

  alarm_actions = local.ticket
}

# --- dashboards ---------------------------------------------------------------
#
# Three, provisioned as code rather than drawn by hand. A dashboard drawn by
# hand exists in one account, is not reviewable, and is lost when somebody
# tidies up.
#
# They are also subject to FEAT-014, which is the control this product sells:
# minimum refresh interval one minute, and no Logs Insights panel over a window
# longer than twenty four hours. A team that exempts its own dashboards from the
# control it sells has already lost the argument, so the JSON carries both and a
# test asserts them.

resource "aws_cloudwatch_dashboard" "meter" {
  for_each = toset(["collection-health", "service-health", "platform-cost"])

  dashboard_name = "${local.name}-${each.value}"
  dashboard_body = file("${path.module}/dashboards/${each.value}.json")
}
