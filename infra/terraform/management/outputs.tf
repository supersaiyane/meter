output "role_arn" {
  description = "Goes into METER_ORG_READER_ROLE_ARN on the hub side."
  value       = aws_iam_role.org_reader.arn
}

output "management_account_id" {
  description = "The account this was applied to, so the hub can be told which payer it is reading."
  value       = data.aws_caller_identity.current.account_id
}
