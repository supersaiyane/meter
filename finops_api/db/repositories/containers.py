"""Clusters and the reservations of the workloads on them. FEAT-036 and FEAT-037.

Two repositories over two tables, both scoped by account through the guard, because
a cluster lives in an account and so does every workload on it. Neither reaches the
other: a usage row can exist for a cluster whose own read failed, and a rule that
scoped usage through its cluster would need the cluster row to exist.

Coverage is counted here rather than from a length, for the reason the waste and
quota repositories give: a row count in the coverage slot has been the defect three
times, and the denominator a screen states has to come from a query that means it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from sqlalchemy import Row, Select, Table, func

from finops_api.db import models
from finops_api.db.repositories.base import ScopedRepository
from finops_core.domain.tenant import Scope


def _fetch(
    repository: ScopedRepository, scope: Scope, statement: Select[*tuple[Any, ...]]
) -> Sequence[Row[*tuple[Any, ...]]]:
    """Run a select through the scoped path, projected or not."""
    return repository.fetch(scope, statement)


class ContainerClusterRepository(ScopedRepository):
    """One row per cluster, measurable or not."""

    table: ClassVar[Table] = models.container_cluster
    resource: ClassVar[str] = "container_cluster"

    def clusters(self, scope: Scope) -> Sequence[Row[*tuple[Any, ...]]]:
        """Every cluster this caller may see, the unmeasurable ones included."""
        statement = self.scoped_select(scope).order_by(
            self.table.c.sub_account_id, self.table.c.region_id, self.table.c.cluster_name
        )
        return _fetch(self, scope, statement)

    def request_coverage(self, scope: Scope) -> tuple[int, int]:
        """Clusters that publish pod requests, against clusters found.

        The denominator of the waste screen: a cluster without enhanced observability
        has usage and no request, so requested against used cannot be stated for it.
        """
        statement = self.scoped_select(scope).with_only_columns(
            func.count().filter(self.table.c.enhanced_observability.is_(True)),
            func.count(),
        )
        rows = _fetch(self, scope, statement)
        return (int(rows[0][0]), int(rows[0][1])) if rows else (0, 0)

    def packing_coverage(self, scope: Scope) -> tuple[int, int]:
        """Clusters whose bin packing could be computed, against clusters with nodes.

        Clusters with nodes, not all clusters. A Fargate cluster runs tasks without
        nodes, so it has no fleet to pack, and counting it as unmeasured would leave
        the inventory screen permanently degraded for a gap that does not exist. It is
        still listed, with a reason of its own.
        """
        with_nodes = self.table.c.platform != "ECS"
        statement = self.scoped_select(scope).with_only_columns(
            func.count().filter(with_nodes & self.table.c.packing_efficiency.isnot(None)),
            func.count().filter(with_nodes),
        )
        rows = _fetch(self, scope, statement)
        return (int(rows[0][0]), int(rows[0][1])) if rows else (0, 0)


class ContainerUsageRepository(ScopedRepository):
    """One row per workload: what it reserved and what it used."""

    table: ClassVar[Table] = models.container_usage
    resource: ClassVar[str] = "container_usage"

    def reservations(self, scope: Scope, limit: int = 2000) -> Sequence[Row[*tuple[Any, ...]]]:
        statement = (
            self.scoped_select(scope)
            .order_by(
                self.table.c.sub_account_id,
                self.table.c.region_id,
                self.table.c.cluster_name,
                self.table.c.namespace,
                self.table.c.workload,
            )
            .limit(limit)
        )
        return _fetch(self, scope, statement)
