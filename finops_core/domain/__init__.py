"""The domain. No persistence concern, no cloud concern, no framework.

Constraint 1 in CLAUDE.md: `finops_core` imports no cloud SDK. `lint-imports`
proves it on every build. Everything here is a frozen dataclass, so an update
returns a new instance and nothing is edited underneath a caller that is still
reading it.
"""

from finops_core.domain.account import AccountKey, AccountStatus, CloudAccount, Provider
from finops_core.domain.cost import CostRecord
from finops_core.domain.fact import Fact
from finops_core.domain.identity import Entitlement, Principal
from finops_core.domain.ingest import CollectionFailure, IngestRun, RunStatus, Watermark
from finops_core.domain.org import OrgNode, OrgNodeType
from finops_core.domain.tenant import Scope, Tenant

__all__ = [
    "AccountKey",
    "AccountStatus",
    "CloudAccount",
    "CollectionFailure",
    "CostRecord",
    "Entitlement",
    "Fact",
    "IngestRun",
    "OrgNode",
    "OrgNodeType",
    "Principal",
    "Provider",
    "RunStatus",
    "Scope",
    "Tenant",
    "Watermark",
]
