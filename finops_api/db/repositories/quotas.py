"""Reading quotas, and the increase requests made against them.

Separate repositories along the seam the two features follow. FEAT-033 is what a quota is
and FEAT-034 is what somebody asked for, and they are independent: most requests are for
quotas nothing can measure, so one object able to return both in a call would invite a join
nobody should make.

**Nothing here sorts the two lists together.** `measurable` orders by headroom and
`unmeasurable` orders by name, and they are separate methods because a single query
returning both would have to put the nulls somewhere. Wherever a null sorts is a claim: at
the top it reads as urgent and at the bottom as safe, and neither is known. That is the
argument in TASK-P5-006, enforced here rather than left to the screen.

**Headroom is computed and never stored.** A stored fraction would be wrong by the next
collection, and the arithmetic is one division. It is written so that a null limit, a limit
of zero and a null usage all produce a null rather than an error or a zero, which is the
rule `QuotaUsage.headroom` follows for the same reason: those three are the cases where the
fraction free is not a number anybody can act on.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from sqlalchemy import Row, Select, Table, case, func, literal

from finops_api.db import models
from finops_api.db.repositories.base import ScopedRepository
from finops_core.domain.tenant import Scope


def _fetch(
    repository: ScopedRepository, scope: Scope, statement: Select[tuple[Any, ...]]
) -> Sequence[Row[tuple[Any, ...]]]:
    """Run a select through the scoped path, projected or not."""
    return repository.fetch(scope, statement)


class QuotaRepository(ScopedRepository):
    """Service quotas, split by whether anything measured them. FEAT-033."""

    table: ClassVar[Table] = models.quota_usage
    resource: ClassVar[str] = "quota_usage"

    @property
    def _headroom(self) -> Any:
        """The fraction of the quota still free, or null where it is not a number.

        Null for an unmeasured usage, for an unpublished limit and for a limit of zero. The
        last is the one worth stating: a quota set to nothing exists and is visible, and the
        fraction free of nothing is not something a reader can act on or sort by. Dividing
        anyway would fail the whole query, and defaulting to zero would rank every switched
        off quota above every real problem.
        """
        return case(
            (
                (self.table.c.used_value.isnot(None))
                & (self.table.c.limit_value.isnot(None))
                & (self.table.c.limit_value > 0),
                (self.table.c.limit_value - self.table.c.used_value) / self.table.c.limit_value,
            ),
            else_=literal(None),
        )

    def measurable(self, scope: Scope, limit: int = 500) -> Sequence[Row[tuple[Any, ...]]]:
        """Quotas with a usage figure, least headroom first.

        The order is the finding: the quota nearest its limit is the one somebody has to act
        on, and it is the only list in this product ordered by something other than money.
        """
        statement = (
            self.scoped_select(scope)
            .add_columns(self._headroom.label("headroom"))
            .where(self.table.c.usage_source != "NONE")
            .order_by(
                self._headroom.asc().nullslast(),
                self.table.c.service_code,
                self.table.c.quota_code,
            )
            .limit(limit)
        )
        return _fetch(self, scope, statement)

    def unmeasurable(self, scope: Scope, limit: int = 500) -> Sequence[Row[tuple[Any, ...]]]:
        """Quotas nothing measured, by name, each carrying its reason.

        By name and not by limit, because a limit on its own ranks nothing: a quota of 5
        nobody is near and a quota of 5000 that is nearly full sort the same way and neither
        position means anything. Alphabetical is the only order here that makes no claim.
        """
        statement = (
            self.scoped_select(scope)
            .where(self.table.c.usage_source == "NONE")
            .order_by(self.table.c.service_code, self.table.c.quota_name)
            .limit(limit)
        )
        return _fetch(self, scope, statement)

    def one(
        self, scope: Scope, service_code: str, quota_code: str
    ) -> Sequence[Row[tuple[Any, ...]]]:
        """One quota, in every region it applies to.

        Several rows rather than one, because a quota code is per region: the same limit can
        be nearly full in one region and untouched in another, and collapsing them would
        answer the question with whichever row the query happened to return first.
        """
        statement = (
            self.scoped_select(scope)
            .add_columns(self._headroom.label("headroom"))
            .where(
                self.table.c.service_code == service_code,
                self.table.c.quota_code == quota_code,
            )
            .order_by(self.table.c.region_id.asc().nullsfirst())
        )
        return _fetch(self, scope, statement)

    def coverage(self, scope: Scope) -> tuple[int, int]:
        """Quotas measured, against quotas found.

        The figure the envelope carries, and it counts quotas rather than accounts. That is
        TASK-P5-005's fourth criterion, and the plan says plainly that a wrong count has
        reached that slot three times before. Accounts would be wrong here in the way that
        reads as reassuring: a reader whose whole organization is visible would be told
        coverage is complete while nine tenths of their quotas had no usage figure at all.
        """
        statement = self.scoped_select(scope).with_only_columns(
            func.count().filter(self.table.c.usage_source != "NONE"),
            func.count(),
        )
        rows = _fetch(self, scope, statement)
        if not rows:
            return (0, 0)
        return (int(rows[0][0] or 0), int(rows[0][1] or 0))


class QuotaRequestRepository(ScopedRepository):
    """Increase requests, read and never written. FEAT-034, spec section 6."""

    table: ClassVar[Table] = models.quota_request
    resource: ClassVar[str] = "quota_request"

    def all_requests(self, scope: Scope, limit: int = 200) -> Sequence[Row[tuple[Any, ...]]]:
        """Every request, the ones still going somewhere first, then oldest first.

        Settled requests are kept rather than filtered out, the refused ones especially. A
        tracking list showing only what is open answers the question it was built for with
        silence: somebody waiting on an increase wants to know it was denied three weeks ago
        more than they want a shorter list.
        """
        still_open = self.table.c.status.in_(("PENDING", "CASE_OPENED"))
        statement = (
            self.scoped_select(scope)
            .add_columns(still_open.label("is_open"))
            .order_by(still_open.desc(), self.table.c.requested_at.asc())
            .limit(limit)
        )
        return _fetch(self, scope, statement)

    def for_quota(
        self, scope: Scope, service_code: str, quota_code: str
    ) -> Sequence[Row[tuple[Any, ...]]]:
        """Requests against one quota, newest first, for the detail page."""
        statement = (
            self.scoped_select(scope)
            .where(
                self.table.c.service_code == service_code,
                self.table.c.quota_code == quota_code,
            )
            .order_by(self.table.c.requested_at.desc())
        )
        return _fetch(self, scope, statement)


class QuotaRequestHistoryRepository(ScopedRepository):
    """Every status a request passed through, and when.

    Its own repository because it is scoped `Through` the request rather than by account, and
    the guard resolves that per table. Reading it from `QuotaRequestRepository` would mean one
    repository over two tables and therefore two scope rules, which is how a read ends up
    confined by whichever rule its author happened to think of.
    """

    table: ClassVar[Table] = models.quota_request_history
    resource: ClassVar[str] = "quota_request_history"

    def for_request(self, scope: Scope, request_id: str) -> Sequence[Row[tuple[Any, ...]]]:
        statement = (
            self.scoped_select(scope)
            .where(self.table.c.request_id == request_id)
            .order_by(self.table.c.changed_at.asc())
        )
        return _fetch(self, scope, statement)
