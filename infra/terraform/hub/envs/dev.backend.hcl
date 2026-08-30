# Where the development state lives.
#
# Per environment rather than hardcoded in versions.tf, because a single key
# shared by dev and prod makes "do not apply dev over prod" a matter of
# remembering. The bucket and table are created outside this stack: a stack
# cannot hold the state that describes it.
#
# use_lockfile rather than dynamodb_table. The DynamoDB locking argument is
# deprecated in the AWS provider 6 series, and S3 native locking does the same
# job with one less resource to create.

bucket       = "meter-terraform-state-dev"
key          = "hub/dev.tfstate"
region       = "eu-west-1"
encrypt      = true
use_lockfile = true
