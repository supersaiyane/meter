# Four repositories: api, worker, web and cache. There is no mcp repository.
#
# The MCP server is a second process in the api image, selected by the container
# command. A fifth repository would duplicate the whole dependency tree for one
# module and would need its own build, scan, signature and lifecycle policy,
# which is how a deployable ends up outside the security gates. ADR-0009,
# A001-F08.

locals {
  repositories = ["api", "worker", "web", "cache"]
}

resource "aws_ecr_repository" "meter" {
  for_each = toset(local.repositories)

  name = "meter-${each.value}"

  # IMMUTABLE, so a tag cannot be repointed at a different image after it was
  # scanned and signed. Without this, `meter-api:abc1234` verified on Tuesday
  # and `meter-api:abc1234` deployed on Friday can be different images and
  # nothing in the pipeline would notice. ISS-054.
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.storage.arn
  }
}

# Enhanced scanning, which is set per registry rather than per repository. It
# continues scanning images after push as new advisories are published, which
# is the difference between knowing an image was clean when it was built and
# knowing it is clean now.
resource "aws_ecr_registry_scanning_configuration" "enhanced" {
  scan_type = "ENHANCED"

  rule {
    scan_frequency = "CONTINUOUS_SCAN"

    repository_filter {
      filter      = "meter-*"
      filter_type = "WILDCARD"
    }
  }
}

resource "aws_ecr_lifecycle_policy" "meter" {
  for_each = aws_ecr_repository.meter

  repository = each.value.name

  # Thirty images is roughly a month of deploys. Enough to roll back to
  # anything anyone would actually roll back to, and not a storage bill that
  # grows forever.
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep the last 30 images. Older ones are not rollback targets anybody uses."
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 30
        }
        action = { type = "expire" }
      },
    ]
  })
}
