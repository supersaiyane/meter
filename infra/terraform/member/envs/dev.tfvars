# Values for the development organization.
#
# external_id is absent on purpose. See the management stack for why.

region          = "eu-west-1"
owner           = "platform"
hub_account_id  = "000000000000"
organization_id = "o-devexample00"

# The organization root, so every account gets the role, including accounts
# created after this was applied.
organizational_unit_ids = ["r-dev0"]
