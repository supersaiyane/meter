"""Watermarks and platform cost, both read through the same scope guard.

`ingest_watermark` is scoped by tenant and not by account, because a watermark
names a collector and a scope key rather than an account row. That is recorded
in `SCOPED_TABLES` rather than decided here.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from sqlalchemy import Row, Table

from finops_api.db import models
from finops_api.db.repositories.base import ScopedRepository
from finops_core.domain.tenant import Scope


class WatermarkRepository(ScopedRepository):
    table: ClassVar[Table] = models.ingest_watermark
    resource: ClassVar[str] = "ingest_watermark"

    def list_all(self, scope: Scope) -> Sequence[Row[*tuple[object, ...]]]:
        statement = self.scoped_select(scope).order_by(
            self.table.c["collector"], self.table.c["scope_key"]
        )
        return self.fetch(scope, statement)


class PlatformCostRepository(ScopedRepository):
    table: ClassVar[Table] = models.platform_cost
    resource: ClassVar[str] = "platform_cost"

    def by_day_and_module(self, scope: Scope) -> Sequence[Row[*tuple[object, ...]]]:
        """Meter's own cost. Constraint 7 puts this on the front page."""
        statement = self.scoped_select(scope).order_by(
            self.table.c["day"].desc(), self.table.c["module"], self.table.c["service"]
        )
        return self.fetch(scope, statement)


class ScheduleRepository(ScopedRepository):
    table: ClassVar[Table] = models.collector_schedule
    resource: ClassVar[str] = "collector_schedule"

    def cadences(self, scope: Scope) -> dict[str, int]:
        """Each enabled collector's interval, so staleness is judged per collector.

        A daily collector and an hourly one cannot share a staleness threshold.
        ADR-0012 puts the interval in the database precisely so this comparison
        uses the number an operator can change rather than one compiled in.
        """
        rows = self.fetch(scope, self.scoped_select(scope))
        return {str(row.collector): int(row.cadence_seconds) for row in rows if row.is_enabled}
