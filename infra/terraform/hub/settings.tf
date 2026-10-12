# Every setting the Python services read, one SSM parameter each under /meter/<env>/. FEAT-080,
# TASK-P12-006, OPEN-29, ISS-250.
#
# Three sources, and a test holds their union to every field of finops_core.config.Settings:
#   derived   the names of what this stack creates, which no person should type twice
#   settings  a committed map per environment, envs/<env>.tfvars, for everything else
#   secret    SecureString parameters made with a placeholder the settings model refuses,
#             whose value the owner sets once and Terraform never reads back or overwrites
#
# SSM refuses a parameter with an empty value, and several settings are empty on purpose
# (no assistant model yet, no Terraform state locations). Those reach the task as an empty
# environment value from the same map; give one a value and it becomes a parameter.
#
# The database URL carries no password. The task's PGPASSWORD comes from the secret RDS manages,
# its password key, and libpq reads it, because that secret holds a username and a password and
# nothing else: the METER_DATABASE_URL key the task definitions asked it for never existed.

locals {
  derived_settings = {
    METER_ENV                             = var.env
    METER_DATABASE_URL                    = "postgresql+psycopg://${aws_rds_cluster.hub.master_username}@${aws_rds_cluster.hub.endpoint}:${aws_rds_cluster.hub.port}/${aws_rds_cluster.hub.database_name}?sslmode=require"
    METER_QUEUE_URL                       = aws_sqs_queue.work.url
    METER_EXTERNAL_ID_SECRET              = aws_secretsmanager_secret.external_id.name
    METER_COLLECTOR_ROLE_NAME             = var.collector_role_name
    METER_ORG_READER_ROLE_ARN             = var.org_reader_role_arn
    METER_S3_BUCKET                       = aws_s3_bucket.data.id
    METER_RELAY_FUNCTION_NAME             = aws_lambda_function.relay.function_name
    METER_CUR_EXPORT_BUCKET               = aws_s3_bucket.cost_exports.id
    METER_CUR_ATHENA_DATABASE             = aws_glue_catalog_database.cost.name
    METER_CUR_ATHENA_WORKGROUP            = aws_athena_workgroup.cost.name
    METER_ASSISTANT_MODEL_ID              = var.assistant_model_in_use
    METER_ASSISTANT_INFERENCE_PROFILE_ARN = var.assistant_model_in_use == "" ? "" : aws_bedrock_inference_profile.assistant[var.assistant_model_in_use].arn
  }

  # Must equal UNSET_SECRET in finops_core/config.py, which refuses to start on it.
  unset_secret     = "unset: the owner sets this parameter once, docs/runbooks/deploy.md"
  secret_settings  = toset(["METER_SESSION_SIGNING_KEY"])
  all_settings     = merge(var.settings, local.derived_settings)
  setting_values   = { for name, value in local.all_settings : name => value if value != "" }
  setting_absences = sort([for name, value in local.all_settings : name if value == ""])

  # What a Python task is given: every setting, and the database password.
  setting_secrets = concat(
    [for name in sort(keys(local.setting_values)) : { name = name, valueFrom = aws_ssm_parameter.setting[name].arn }],
    [for name in sort(tolist(local.secret_settings)) : { name = name, valueFrom = aws_ssm_parameter.secret[name].arn }],
    [{ name = "PGPASSWORD", valueFrom = "${aws_rds_cluster.hub.master_user_secret[0].secret_arn}:password::" }],
  )
  setting_environment = [for name in local.setting_absences : { name = name, value = "" }]
}

resource "aws_ssm_parameter" "setting" {
  for_each = local.setting_values

  name  = "/meter/${var.env}/${each.key}"
  type  = "String"
  value = each.value
}

resource "aws_ssm_parameter" "secret" {
  for_each = local.secret_settings

  name   = "/meter/${var.env}/${each.key}"
  type   = "SecureString"
  key_id = aws_kms_key.storage.arn
  value  = local.unset_secret

  # The owner sets the value once with put-parameter --overwrite. Terraform made the parameter
  # and never manages what it holds, so no secret reaches git or the Terraform state.
  lifecycle {
    ignore_changes = [value]
  }
}
