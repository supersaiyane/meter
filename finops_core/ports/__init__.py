"""The nine ports a provider implements. No implementation, no cloud import.

Constraint 1 in CLAUDE.md. These protocols are the line that makes GCP a
connector rather than a rewrite, and `lint-imports` plus
`tests/core/test_ports.py` both prove that nothing behind the line has reached
across it.

Six describe a cloud, two describe identity, and `QuerySurface` describes a tool
that holds saved queries. P0 implements two, `AccountDiscovery` and
`CredentialBroker`, and defines the rest anyway. A port is cheap to define now
and expensive to retrofit once three consumers have grown around its absence.

`QuerySurface` arrived with P2 and is the first port that is not about a cloud
provider at all. That is the test of whether this package was the right shape:
adding it needed a new file and one line here, and changed nothing else.
"""

from finops_core.ports.accounts import AccountDiscovery
from finops_core.ports.cost import CostExport
from finops_core.ports.credentials import CredentialBroker
from finops_core.ports.identity import EntitlementResolver, IdentityProvider
from finops_core.ports.inventory import ResourceInventory
from finops_core.ports.metrics import MetricSource
from finops_core.ports.query import QuerySurface
from finops_core.ports.quotas import QuotaSource

#: The eight a cloud provider implements. `FakeProvider` satisfies all of them,
#: which is what lets every core and API test run with no AWS account.
PROVIDER_PORTS = (
    AccountDiscovery,
    CostExport,
    CredentialBroker,
    EntitlementResolver,
    IdentityProvider,
    MetricSource,
    QuotaSource,
    ResourceInventory,
)

#: Ports that are not about a cloud provider. `QuerySurface` is the first, and
#: grouping them here rather than describing the difference in prose is what
#: stops a test deriving "every port" from `__all__` and then failing because a
#: cloud fake does not implement a query surface. That is exactly what happened
#: when `QuerySurface` was added.
SURFACE_PORTS = (QuerySurface,)

__all__ = [
    "PROVIDER_PORTS",
    "SURFACE_PORTS",
    "AccountDiscovery",
    "CostExport",
    "CredentialBroker",
    "EntitlementResolver",
    "IdentityProvider",
    "MetricSource",
    "QuerySurface",
    "QuotaSource",
    "ResourceInventory",
]
# `ProviderSession` is deliberately absent. It is a supporting type for
# adapters rather than a port, and an adapter imports it from
# `finops_core.ports.credentials` directly.
