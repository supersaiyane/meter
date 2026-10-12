"""The ports a provider implements. No implementation, no cloud import.

Constraint 1 in CLAUDE.md. These protocols are the line that makes GCP a
connector rather than a rewrite, and `lint-imports` plus
`tests/core/test_ports.py` both prove that nothing behind the line has reached
across it.

Most describe a cloud, two describe identity, and `QuerySurface` describes a tool
that holds saved queries. P0 implements two, `AccountDiscovery` and
`CredentialBroker`, and defines the rest anyway. A port is cheap to define now
and expensive to retrofit once three consumers have grown around its absence.

`QuerySurface` arrived with P2 and is the first port that is not about a cloud
provider at all. That is the test of whether this package was the right shape:
adding it needed a new file and one line here, and changed nothing else.
"""

from finops_core.ports.accounts import AccountDiscovery
from finops_core.ports.ai import AiProviderReports, GpuMetrics, InvocationLogs
from finops_core.ports.catalog import (
    InstanceCatalog,
    PriceCatalog,
    SavingsPlansRates,
    SpotPrices,
)
from finops_core.ports.containers import ContainerSource
from finops_core.ports.cost import CostExport
from finops_core.ports.credentials import CredentialBroker
from finops_core.ports.identity import EntitlementResolver, IdentityProvider
from finops_core.ports.inventory import ResourceInventory
from finops_core.ports.llm import LlmProvider
from finops_core.ports.metrics import MetricSource
from finops_core.ports.ownership import ResourceCreators, ServiceCatalogue
from finops_core.ports.query import PanelRewrite, QuerySurface, RefreshFloor
from finops_core.ports.quotas import QuotaSource

#: The ones a cloud provider implements. `FakeProvider` satisfies all of them,
#: which is what lets every core and API test run with no AWS account. The count
#: is not written down here, because it was written down as eight and a ninth
#: arrived; `tests/core/test_ports.py` holds the number in one place instead.
PROVIDER_PORTS = (
    AccountDiscovery,
    ContainerSource,
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
SURFACE_PORTS = (QuerySurface, RefreshFloor, PanelRewrite)

#: The model behind the assistant, P7 and ADR-0028. Its own group, because the cloud
#: fake does not implement it and a model is not a query surface: the fake model is a
#: separate scripted class, and a group shared with either would have a test asking
#: one fake to be both.
MODEL_PORTS = (LlmProvider,)

#: AWS's price list and its description of instance types, P9 and TASK-P9-002. Their own group,
#: because they describe what AWS sells rather than an estate: the cloud fake does not implement
#: them, and their fakes are built from the estate's own prices in `finops_fakes/catalog.py`.
CATALOG_PORTS = (PriceCatalog, InstanceCatalog, SavingsPlansRates, SpotPrices)

#: Where an estate names a resource's owners beyond its tags, P11 and TASK-P11-001. Their own
#: group, because the cloud fake does not implement them: their fakes plant the owner cases in
#: `finops_fakes/ownership.py`.
OWNERSHIP_PORTS = (ServiceCatalogue, ResourceCreators)

#: Who spent tokens on which model, P13 and TASK-P13-003. Their own group, because the cloud fake
#: does not implement them: their fakes plant the AI estate in `finops_fakes/ai.py`.
AI_PORTS = (InvocationLogs, AiProviderReports, GpuMetrics)

__all__ = [
    "AI_PORTS",
    "CATALOG_PORTS",
    "MODEL_PORTS",
    "OWNERSHIP_PORTS",
    "PROVIDER_PORTS",
    "SURFACE_PORTS",
    "AccountDiscovery",
    "AiProviderReports",
    "ContainerSource",
    "CostExport",
    "CredentialBroker",
    "EntitlementResolver",
    "GpuMetrics",
    "IdentityProvider",
    "InstanceCatalog",
    "InvocationLogs",
    "LlmProvider",
    "MetricSource",
    "PanelRewrite",
    "PriceCatalog",
    "QuerySurface",
    "QuotaSource",
    "RefreshFloor",
    "ResourceCreators",
    "ResourceInventory",
    "SavingsPlansRates",
    "ServiceCatalogue",
    "SpotPrices",
]
# `ProviderSession` is deliberately absent. It is a supporting type for
# adapters rather than a port, and an adapter imports it from
# `finops_core.ports.credentials` directly.
