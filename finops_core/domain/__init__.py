"""The domain. No persistence concern, no cloud concern, no framework.

Constraint 1 in CLAUDE.md: `finops_core` imports no cloud SDK. `lint-imports`
proves it on every build. Everything here is a frozen dataclass, so an update
returns a new instance and nothing is edited underneath a caller that is still
reading it.
"""

from finops_core.domain.account import (
    AccountHealth,
    AccountKey,
    AccountStatus,
    CloudAccount,
    Provider,
    RoleHealth,
)
from finops_core.domain.cost import BillingPeriod, CostMeasure, CostRecord, CostTotal
from finops_core.domain.fact import Fact
from finops_core.domain.identity import Entitlement, Principal
from finops_core.domain.ingest import CollectionFailure, IngestRun, RunStatus, Watermark
from finops_core.domain.org import OrgNode, OrgNodeType
from finops_core.domain.platform import UNALLOCATED, PlatformCost
from finops_core.domain.tenant import Scope, Tenant
from finops_core.domain.topology import (
    NODE_NAMESPACE,
    SOURCE_MAX_LENGTH,
    CoverageCause,
    CoverageState,
    Edge,
    EdgeKind,
    GraphCoverage,
    Node,
    NodeKind,
    node_id_for,
)

__all__ = [
    "NODE_NAMESPACE",
    "SOURCE_MAX_LENGTH",
    "UNALLOCATED",
    "AccountHealth",
    "AccountKey",
    "AccountStatus",
    "BillingPeriod",
    "CloudAccount",
    "CollectionFailure",
    "CostMeasure",
    "CostRecord",
    "CostTotal",
    "CoverageCause",
    "CoverageState",
    "Edge",
    "EdgeKind",
    "Entitlement",
    "Fact",
    "GraphCoverage",
    "IngestRun",
    "Node",
    "NodeKind",
    "OrgNode",
    "OrgNodeType",
    "PlatformCost",
    "Principal",
    "Provider",
    "RoleHealth",
    "RunStatus",
    "Scope",
    "Tenant",
    "Watermark",
    "node_id_for",
]
