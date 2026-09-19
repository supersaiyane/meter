# Where the billing export lands, and what reads it. P1, FEAT-020.
#
# Data Exports writes CUR 2.0 in FOCUS shape to S3, partitioned by billing
# period. Glue holds the table definition and Athena runs one partition pruned
# query per period. None of it is in the serving path: the API reads Postgres,
# and this exists so the collector has something to read.
#
# **Nothing here has been planned or applied.** ISS-122. It passes validate and
# fmt, which checks syntax, provider schema and references, and checks nothing
# at all about whether the stack builds.

# A separate bucket from the one in storage.tf. That one holds derived
# artefacts under a lifecycle rule that expires them, because losing them costs
# a re collection. A billing export is the record of what was actually charged,
# and expiring it on the same schedule would delete the only copy of a month
# somebody needs at an audit.
resource "aws_s3_bucket" "cost_exports" {
  bucket = "${local.name}-cost-exports-${random_id.bucket_suffix.hex}"
}

resource "aws_s3_bucket_public_access_block" "cost_exports" {
  bucket = aws_s3_bucket.cost_exports.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "cost_exports" {
  bucket = aws_s3_bucket.cost_exports.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "cost_exports" {
  bucket = aws_s3_bucket.cost_exports.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.storage.arn
    }
    bucket_key_enabled = true
  }
}

# Delivered to the same access log bucket as the data bucket. This one holds
# the record of what an organization was actually charged, so who read it is
# worth knowing, and a second log destination would be a second place to look
# during an incident.
resource "aws_s3_bucket_logging" "cost_exports" {
  bucket = aws_s3_bucket.cost_exports.id

  target_bucket = aws_s3_bucket.access_logs.id
  target_prefix = "cost-exports/"
}

# Data Exports restates a period in place all month, which is why the ingest is
# keyed on a fingerprint rather than on arrival. Superseded versions are of no
# use to anybody once the month closes, and keeping every one of them turns a
# cost report into a cost.
resource "aws_s3_bucket_lifecycle_configuration" "cost_exports" {
  bucket = aws_s3_bucket.cost_exports.id

  rule {
    id     = "expire-superseded-exports"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = var.cost_export_version_retention_days
    }
  }
}

# The billing service writes here. Conditioned on this account's own export, so
# a policy that leaked could not let another account write into it.
data "aws_iam_policy_document" "cost_exports" {
  statement {
    sid    = "AllowBillingExportDelivery"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["bcm-data-exports.amazonaws.com", "billingreports.amazonaws.com"]
    }

    actions   = ["s3:PutObject", "s3:GetBucketAcl", "s3:GetBucketPolicy"]
    resources = [aws_s3_bucket.cost_exports.arn, "${aws_s3_bucket.cost_exports.arn}/*"]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_s3_bucket_policy" "cost_exports" {
  bucket = aws_s3_bucket.cost_exports.id
  policy = data.aws_iam_policy_document.cost_exports.json
}

resource "aws_glue_catalog_database" "cost" {
  name        = replace("${local.name}_cost", "-", "_")
  description = "FOCUS billing export for Meter ${var.env}. Read by Athena, never by the API."
}

# The workgroup carries the result location, which is why the application has
# no setting for one. Enforcing it here is what stops a query writing results
# wherever the caller fancied.
#
# The bytes scanned cutoff is the point of this resource. A query that forgets
# to prune on the billing period partition scans the whole table at full price,
# and it reads as nothing worse than a slow query until the bill arrives. The
# tool that reports on cost running away with its own is the most embarrassing
# way this product can fail, so the ceiling is enforced by the service rather
# than by the care of whoever wrote the SQL.
resource "aws_athena_workgroup" "cost" {
  name  = local.name
  state = "ENABLED"

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = var.athena_bytes_scanned_cutoff

    result_configuration {
      output_location = "s3://${aws_s3_bucket.cost_exports.id}/athena-results/"

      encryption_configuration {
        encryption_option = "SSE_KMS"
        kms_key_arn       = aws_kms_key.storage.arn
      }
    }
  }
}
