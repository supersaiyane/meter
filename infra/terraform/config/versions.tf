# The Config stack: one organization aggregator in the payer, and one recorder per
# account and region, deployed as a service managed StackSet.
#
# Applied with management account credentials, like `infra/terraform/member` and unlike
# the hub, which is why it is a separate root module.
#
# **Nothing here has been planned and nothing has been applied.** ISS-122 and ISS-203.
# That is what done means for this stack rather than a caveat on it: the recorders cost
# real money per configuration item, and provisioning them before the estimate below has
# been argued with somebody who owns the bill is the failure ISS-012 exists to prevent.

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

  # Constraint 7 in CLAUDE.md: the platform meters itself. Every resource here is
  # tagged, so the real Config bill reaches Meter's own cost screen under
  # `finops:module = config` and can be compared with the estimate in COST.md. Without
  # that tag the largest number this sub project produces would be invisible to the
  # product whose purpose is to show it.
  default_tags {
    tags = {
      "finops:module" = "config"
      "finops:owner"  = var.owner
      ManagedBy       = "terraform"
    }
  }
}
