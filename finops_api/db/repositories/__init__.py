"""Repositories. Every one of them refuses to read outside a scope.

This is the second of the two independent enforcement points in constraint 3.
A route that forgets the request dependency still cannot read out of scope
data, because the repository never had an unscoped path to offer it.
"""

from finops_api.db.repositories.accounts import AccountRepository
from finops_api.db.repositories.base import AccessContext, ScopedRepository
from finops_api.db.repositories.freshness import (
    PlatformCostRepository,
    ScheduleRepository,
    WatermarkRepository,
)
from finops_api.db.repositories.ingest import IngestRunRepository, SyncErrorRepository
from finops_api.db.repositories.org import OrgRepository

__all__ = [
    "AccessContext",
    "AccountRepository",
    "IngestRunRepository",
    "OrgRepository",
    "PlatformCostRepository",
    "ScheduleRepository",
    "ScopedRepository",
    "SyncErrorRepository",
    "WatermarkRepository",
]
from finops_api.db.repositories.query import (
    QueryFindingRepository,
    SurfaceInstanceRepository,
)

__all__ = [*globals().get("__all__", []), "QueryFindingRepository", "SurfaceInstanceRepository"]
