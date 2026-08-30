# The development hub.
#
# Absent on purpose:
#
#   image_tag        set by the pipeline to the commit sha, never written here.
#                    A value in this file would be a stale default that quietly
#                    deploys the wrong image when somebody forgets the flag.
#   certificate_arn  empty means HTTP only, which is acceptable here and is
#                    refused in production by a check in alb.tf.
#   page_topic_arn   empty means the alarms are created with no action, which is
#   ticket_topic_arn acceptable here and refused in production.

env    = "dev"
owner  = "platform"
region = "eu-west-1"

organization_id = "o-devexample00"

# Empty means the organization collector runs against LocalStack rather than a
# real management account, which is how development proceeds without waiting on
# management account cooperation. See ISS-002.
org_reader_role_arn = ""

# Smaller than production, because development is one person at a time.
database_min_capacity = 0.5
database_max_capacity = 2

api_desired_count = 1
web_desired_count = 1
worker_max_count  = 2

# Seven days rather than ninety. Development logs are not evidence of anything.
log_retention_days = 7

# The AWS minimum. Development data is reconstructible by re collecting it.
backup_retention_days = 7
