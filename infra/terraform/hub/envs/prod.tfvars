# The production hub.
#
# Four values are deliberately absent and are supplied at apply time:
# image_tag, certificate_arn, page_topic_arn and ticket_topic_arn. The last
# three are refused as empty in production by preconditions, so a first apply
# without them fails at plan rather than producing a stack with TLS off and no
# alerting.

env    = "prod"
owner  = "platform"
region = "eu-west-1"

organization_id = "o-prodexample0"

# Set from the output of infra/terraform/management once that stack is applied.
org_reader_role_arn = ""

database_min_capacity = 0.5
database_max_capacity = 4

api_desired_count = 2
web_desired_count = 2
worker_max_count  = 4

# Ninety days, matching the operational retention window in
# docs/09-DATA-CLASSIFICATION.md.
log_retention_days = 90

# The AWS maximum, which is below every table retention window, so a backup
# never resurrects data the policy says was removed.
backup_retention_days = 35
