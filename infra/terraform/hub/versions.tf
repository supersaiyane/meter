# The hub stack. Everything Meter runs on, in Meter's own account.
#
# Applied by the pipeline with a GitLab OIDC session, which is why it is
# separate from the two organization stacks: those need management account
# credentials that the deploy role deliberately does not have.
#
# Terraform owns the ECS task definition, so a deploy is an apply rather than a
# separate `aws ecs update-service`. One system owns the desired state, which
# means there is no drift between what Terraform believes and what is running.

terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Configured per environment from envs/<env>.backend.hcl, because the state
  # for dev and prod must not share a key and a hardcoded one makes that a
  # matter of remembering.
  backend "s3" {}
}

provider "aws" {
  region = var.region

  # Constraint 7: the platform meters itself. Every resource carries
  # finops:module, and the platform's own cost is on the front page. A resource
  # without the tag is invisible to that page, and self metering reports nothing
  # rather than failing, which is the worst kind of broken. Default tags mean it
  # cannot be forgotten on a resource, only overridden deliberately.
  default_tags {
    tags = {
      "finops:module" = "hub"
      "finops:env"    = var.env
      "finops:owner"  = var.owner
      ManagedBy       = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_region" "current" {}
