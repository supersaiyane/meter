# Example values. Not applied, and no real account identifier appears here: ISS-203 and
# the rule in CLAUDE.md's definition of done about hardcoded account identifiers.
#
# `owner` and `delivery_bucket_name` have no defaults on purpose. A stack that costs money
# per configuration item should not be appliable without somebody naming who owns the bill.

owner                = "platform-finops"
organization_id      = "o-example12345"
delivery_bucket_name = "example-meter-config-delivery"

# The cost lever. Two regions, and COST.md says what an eleventh one would do.
recorder_regions = ["eu-west-1", "eu-west-2"]
home_region      = "eu-west-1"
