"""Values that are genuinely fixed, as opposed to values that are configured.

The test for membership here is whether changing the value would be a decision
rather than a deployment. The FOCUS version is a decision recorded in ADR-0002.
A connection timeout is a deployment, so it lives in `.env.example` and on the
settings class instead. Anything that fails that test belongs in configuration,
and `scripts/ci/check_hardcoded.py` exists to catch the ones that slip.
"""

from __future__ import annotations

# The canonical cost schema. Constraint 2 in CLAUDE.md and ADR-0002.
FOCUS_VERSION = "1.1"

# Every platform resource carries this tag. Constraint 7 in CLAUDE.md.
PLATFORM_TAG_KEY = "finops:module"

# Every environment variable this project reads carries this prefix.
ENV_PREFIX = "METER_"

# The environment name that turns on the production only guards.
PRODUCTION_ENV = "prod"

# The identity provider that reads users from a file. Refused in production,
# because a provider with no directory behind it is a total authentication
# bypass rather than a degraded one. ISS-017.
LOCAL_IDENTITY_PROVIDER = "local_config"

# How long a per tenant flag override is trusted before it is read again.
# Fixed rather than configured on purpose: it is the bound on how long a flag
# flip takes to reach every worker, which is a property of the design and not
# something an operator should be tuning under pressure.
TENANT_FLAG_CACHE_TTL_SECONDS = 60

# How long before a session expires the broker refreshes it. A design property
# rather than a deployment knob: it is the margin that stops a call starting
# with a credential that dies mid flight, and an expired session produces
# errors that read like permission problems, which is a bad hour for whoever
# is debugging.
SESSION_REFRESH_MARGIN_SECONDS = 300

# First delay before retrying a throttled organization call, doubling after
# each attempt. The Organizations API is throttled hard and globally, so the
# first retry has to wait rather than sprint, and the number of attempts comes
# from METER_AWS_MAX_RETRIES so an operator can lower it under pressure.
THROTTLE_BACKOFF_BASE_SECONDS = 1.0

# How many times a unit of work may be received before it is treated as poison
# and left for the dead letter queue. Three, because two is not enough to ride
# out a transient throttle and more than three turns a permanently broken
# account into a permanent load. It matches the queue redrive policy, and the
# worker knows it so that the fourth delivery records an outcome rather than
# silently disappearing into the queue's own accounting.
MAX_DELIVERY_ATTEMPTS = 3

# How many cadences a collector may miss before its data is called stale. Two,
# because one missed run is a retry and three is an outage nobody noticed. It is
# a multiple of the collector's own cadence rather than a fixed age, so a daily
# collector and an hourly one are judged by their own standard.
STALE_AFTER_CADENCE_MULTIPLE = 2

# The length below which an explanation is not a sentence. A decision rather than a
# deployment: it is the floor that stops a reason reading "not measured", which would
# teach a reader the explanations in this product are empty so they stop reading the
# ones that are not. Shared by the quota rule and by the database check that backs it,
# so the entity and the column cannot disagree about what counts as an explanation. A
# check constraint cannot read this, so the migration carries the same figure literally.
REASON_MIN_LENGTH = 12

# The most questions the assistant may answer at once, whatever a deployment sets. Each
# holds two of the API's worker threads while it runs, its own and the one its current tool
# call needs, and anyio's default pool is forty, so nineteen keeps questions under half of
# it. tests/api/test_assistant_limit.py reads the pool from the installed anyio rather than
# trusting the forty written here. ISS-225.
ASSISTANT_CONCURRENCY_CEILING = 19

# The longest name a saved view keeps, FEAT-068. Long enough for a sentence that says what the
# view shows, short enough to sit in the library's table and in a menu. Shared by the API's body
# and by the model's mirror of the database check, so the two cannot disagree; a check
# constraint cannot read this, so migration 0028 carries the same figure literally.
SAVED_VIEW_NAME_MAX_LENGTH = 120

# The most people one scheduled report renders for, FEAT-069. Each is a render of its own, in
# that person's scope, so the list is a cost as well as a list; fifty is a team's distribution
# list and not an organization's. Shared by the API's body and the model's mirror of the check,
# which migration 0029 carries literally because a check constraint cannot read this.
REPORT_RECIPIENTS_MAX = 50

# The tag that says whose a resource is: the key showback groups by unless asked for another,
# the key a team's weekly digest is grouped by, and where a recommendation's suggested owner
# comes from, ISS-021. One value for all three, because the team a resource's spend belongs
# to is the team to ask about changing it. A tenant that names its owners under another key
# needs a setting, ISS-021's next step, never a second literal.
TEAM_TAG = "team"
