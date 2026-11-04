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
