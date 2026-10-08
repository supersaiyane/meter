"""Reading AWS's price list and instance types as Meter holds them. FEAT-071, FEAT-072.

TASK-P9-010. The catalog is about no account, so the guard's rule for these tables is the
tenant's and nothing narrower: a reader granted one account sees the same price list as one
granted all of them. One repository per table, along the tables' own seam.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from sqlalchemy import Row, Table, func, select

from finops_api.db import models
from finops_api.db.repositories.base import ScopedRepository
from finops_api.guards import scope_predicate
from finops_core.domain.tenant import Scope


class InstanceTypeRepository(ScopedRepository):
    """What each type is, in each Region it is sold. FEAT-072."""

    table: ClassVar[Table] = models.instance_type_spec
    resource: ClassVar[str] = "instance_type_spec"

    def matching(
        self,
        scope: Scope,
        *,
        service: str,
        region: str | None = None,
        family: str | None = None,
        architecture: str | None = None,
        vcpus: int | None = None,
        memory_mib: int | None = None,
        offered: bool = True,
        limit: int,
    ) -> Sequence[Row[*tuple[Any, ...]]]:
        """The types that match every filter given, smallest first within a family."""
        spec = self.table
        statement = self.scoped_select(scope).where(spec.c.service_code == service)
        if offered:
            statement = statement.where(spec.c.offered)
        if region is not None:
            statement = statement.where(spec.c.region == region)
        if family is not None:
            statement = statement.where(spec.c.family == family)
        if architecture is not None:
            statement = statement.where(spec.c.architectures.any(architecture))
        if vcpus is not None:
            statement = statement.where(spec.c.vcpus == vcpus)
        if memory_mib is not None:
            statement = statement.where(spec.c.memory_mib == memory_mib)
        statement = statement.order_by(
            spec.c.region, spec.c.family, spec.c.vcpus, spec.c.memory_mib, spec.c.instance_type
        ).limit(limit)
        return self.fetch(scope, statement)


class PriceListVersionRepository(ScopedRepository):
    """Which version of each service's price list the catalog holds in each Region."""

    table: ClassVar[Table] = models.price_list_version
    resource: ClassVar[str] = "price_list_version"

    def regions_held(self, scope: Scope, service: str) -> int:
        """How many Regions the catalog holds a version for: a coverage's whole."""
        statement = (
            self.scoped_select(scope)
            .where(self.table.c.service_code == service)
            .with_only_columns(func.count(func.distinct(self.table.c.region)))
        )
        rows = self.fetch(scope, statement)
        counted: Any = rows[0][0] if rows else 0
        return int(counted or 0)


class PriceRepository(ScopedRepository):
    """AWS's prices, one version of each service in each Region at a time. FEAT-071."""

    table: ClassVar[Table] = models.price
    resource: ClassVar[str] = "price"

    def matching(
        self,
        scope: Scope,
        *,
        service: str,
        region: str | None = None,
        sku: str | None = None,
        instance_type: str | None = None,
        pricing_category: str | None = None,
        version: str | None = None,
        limit: int,
    ) -> Sequence[Row[*tuple[Any, ...]]]:
        """The prices that match, from the version named or else each Region's newest.

        The newest by publication, as the collectors that price a recommendation read it, so a
        price shown here is the one a saving would be worked out from today.
        """
        price = self.table
        statement = self.scoped_select(scope).where(price.c.service_code == service)
        if version is not None:
            statement = statement.where(price.c.version == version)
        else:
            statement = statement.where(price.c.version == self._newest(scope))
        if region is not None:
            statement = statement.where(price.c.region == region)
        if sku is not None:
            statement = statement.where(price.c.sku == sku)
        if instance_type is not None:
            statement = statement.where(
                price.c.sku_price_details["instanceType"].astext == instance_type
            )
        if pricing_category is not None:
            statement = statement.where(price.c.pricing_category == pricing_category)
        statement = statement.order_by(price.c.region, price.c.sku_price_id).limit(limit)
        return self.fetch(scope, statement)

    def _newest(self, scope: Scope) -> Any:
        """Each Region's newest version of the service, confined by the version table's rule."""
        versions = models.price_list_version
        price = self.table
        return (
            select(versions.c.version)
            .where(versions.c.tenant_id == price.c.tenant_id)
            .where(versions.c.service_code == price.c.service_code)
            .where(versions.c.region == price.c.region)
            .where(scope_predicate(versions, scope))
            .order_by(versions.c.as_of.desc())
            .limit(1)
            .correlate(price)
            .scalar_subquery()
        )
