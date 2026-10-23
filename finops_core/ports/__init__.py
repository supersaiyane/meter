"""The eight ports a provider implements. No implementation, no cloud import.

Constraint 1 in CLAUDE.md. These protocols are the line that makes GCP a
connector rather than a rewrite, and `lint-imports` plus
`tests/core/test_ports.py` both prove that nothing behind the line has reached
across it.

Six of the eight describe a cloud and two describe identity. P0 implements two,
`AccountDiscovery` and `CredentialBroker`, and defines the rest anyway. A port
is cheap to define now and expensive to retrofit once three consumers have
grown around its absence.
"""

from finops_core.ports.accounts import AccountDiscovery
from finops_core.ports.cost import CostExport
from finops_core.ports.credentials import CredentialBroker
from finops_core.ports.identity import EntitlementResolver, IdentityProvider
from finops_core.ports.inventory import ResourceInventory
from finops_core.ports.metrics import MetricSource
from finops_core.ports.quotas import QuotaSource

__all__ = [
    "AccountDiscovery",
    "CostExport",
    "CredentialBroker",
    "EntitlementResolver",
    "IdentityProvider",
    "MetricSource",
    "QuotaSource",
    "ResourceInventory",
]
# `ProviderSession` is deliberately absent. It is a supporting type for
# adapters rather than a port, and an adapter imports it from
# `finops_core.ports.credentials` directly.
