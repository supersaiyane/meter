# The member account stack: one service managed StackSet, applied once in the
# management account, deploying one role into every account in the organization.
#
# Applied with management account credentials, like `infra/terraform/management`
# and unlike the hub, which is why it is a separate root module.

terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      "finops:module" = "member"
      "finops:owner"  = var.owner
      ManagedBy       = "terraform"
    }
  }
}
