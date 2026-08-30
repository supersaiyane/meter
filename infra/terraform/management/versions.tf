# The management account stack. One role and nothing else.
#
# It lives in its own root module because it is applied by a different person
# with different credentials: the organization's management account is usually
# owned by a platform or security team, and Meter's own deployment role has no
# access to it. Putting it in the hub stack would mean the hub apply needs
# management account credentials, which is a much larger blast radius than one
# read only role justifies.
#
# See ADR-0004 and ISS-002.

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
      "finops:module" = "management"
      "finops:owner"  = var.owner
      ManagedBy       = "terraform"
    }
  }
}
