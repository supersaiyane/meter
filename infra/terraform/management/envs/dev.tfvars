# Values for the development organization.
#
# external_id is deliberately absent. It is a secret and belongs in Secrets
# Manager on the hub side, passed at apply time with -var or TF_VAR_external_id.
# A tfvars file in version control is the single most common way an ExternalId
# stops being a control.

region         = "eu-west-1"
owner          = "platform"
hub_account_id = "000000000000"
