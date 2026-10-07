# Object storage and the cross account secret.
#
# One bucket, versioned, encrypted, with public access blocked at the account
# boundary rather than by a policy somebody can edit. It holds raw provider
# exports and generated reports, both of which are derived: losing the bucket
# costs a re collection, not the product.

resource "aws_kms_key" "storage" {
  description             = "S3 objects and Secrets Manager entries for Meter ${var.env}."
  enable_key_rotation     = true
  deletion_window_in_days = 30
}

resource "aws_kms_alias" "storage" {
  name          = "alias/${local.name}-storage"
  target_key_id = aws_kms_key.storage.key_id
}

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# Bucket names are globally unique, so the name carries a random suffix rather
# than the account id. An account id in a bucket name is an account id published
# to anyone who can resolve the DNS name.
resource "aws_s3_bucket" "data" {
  bucket = "${local.name}-data-${random_id.bucket_suffix.hex}"
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket = aws_s3_bucket.data.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.storage.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  # Versioning without expiry is a bill that only grows. Ninety days matches the
  # operational retention window in docs/09-DATA-CLASSIFICATION.md, so a
  # superseded version does not outlive the row it came from.
  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }

  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  # TASK-P9-001. The relay's answers are read once, by the collector that asked, so a day is
  # more than they need, and one kept longer is a copy of AWS's data that nobody reads.
  rule {
    id     = "expire-relay-answers"
    status = "Enabled"

    filter {
      prefix = "${local.relay_prefix}/"
    }

    expiration {
      days = 1
    }
  }
}

# The ExternalId. Created empty and populated out of band, because a secret
# whose value passes through a Terraform variable is a secret in Terraform
# state.
resource "aws_secretsmanager_secret" "external_id" {
  name        = "meter/external-id"
  description = "Shared secret required on every cross account assume. Set out of band, never by Terraform."
  kms_key_id  = aws_kms_key.storage.arn

  recovery_window_in_days = var.env == "prod" ? 30 : 7
}

# Access logs for the data bucket, in a bucket of their own.
#
# A bucket cannot log to itself without producing an infinite regress, which is
# why this is a second bucket rather than a prefix. It is the record of who read
# a raw provider export, and raw exports are the most sensitive thing Meter
# stores.

resource "aws_s3_bucket" "access_logs" {
  bucket = "${local.name}-access-logs-${random_id.bucket_suffix.hex}"
}

resource "aws_s3_bucket_public_access_block" "access_logs" {
  bucket = aws_s3_bucket.access_logs.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# SSE-S3 rather than the KMS key used elsewhere. S3 server access logging cannot
# write to a bucket encrypted with a customer managed key, and the alternative
# is no access log at all.
resource "aws_s3_bucket_server_side_encryption_configuration" "access_logs" {
  bucket = aws_s3_bucket.access_logs.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "access_logs" {
  bucket = aws_s3_bucket.access_logs.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "access_logs" {
  bucket = aws_s3_bucket.access_logs.id

  rule {
    id     = "expire"
    status = "Enabled"

    filter {}

    # Ninety days, matching the operational retention window.
    expiration {
      days = 90
    }

    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}

resource "aws_s3_bucket_logging" "data" {
  bucket        = aws_s3_bucket.data.id
  target_bucket = aws_s3_bucket.access_logs.id
  target_prefix = "data/"
}
