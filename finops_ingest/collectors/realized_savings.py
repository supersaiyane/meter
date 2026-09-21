"""Reading back what a completed recommendation actually did to the bill.

The verdict arithmetic is in `finops_query.realized` and has no database. This is
the part that finds the recommendations old enough to judge, reads two windows of
`cost_focus_daily`, and writes the answer.

**It never estimates.** Every figure it writes comes out of billing rows that were
already there. The estimated saving on the recommendation is not consulted, not
copied, and not compared: the whole point of FEAT-029 is a number arrived at
independently, and a collector that could see the estimate is a collector that could
be tuned until the two agree.

**Sixty days, and the first thirty are thrown away.** A change made on a Tuesday
does not show up cleanly in Wednesday's bill. Amortized commitment discounts
redistribute, a terminated instance leaves a final partial day, and a resized one
bills at both sizes for an hour. So the after window is the thirty days *ending*
sixty days after the change, and the thirty days immediately following it are
deliberately not looked at.

**A recommendation is judged once its window completes, and then again every run.**
The verdict is a pure function of two fixed windows, so re running it produces the
same answer and the upsert replaces the row with an identical one. That is cheaper
than remembering which ones have been done and getting that wrong.

**It is the only thing that moves a recommendation out of DONE.** `ALLOWED` in the
domain says DONE goes to VERIFIED or REGRESSED and nothing else, and this is the
writer that promise refers to. An INCONCLUSIVE verdict moves nothing: there is no
inconclusive lifecycle, because a measurement nobody can read either way is not a
reason to close anything.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from finops_core.domain.waste import ALLOWED, Lifecycle
from finops_ingest.registry import CollectorContext, CollectorOutcome
from finops_query.realized import Realization, Verdict, Window, judge

COLLECTOR = "realized_savings"
SCOPE = "billing"

#: Days between the change and the start of the after window. The settling period,
#: and the reason a verdict is never available the week after the work is done.
SETTLE_DAYS = 30

#: Length of each window. Thirty days on both sides so a monthly billing cycle,
#: a weekday pattern and a month end batch all appear in each.
WINDOW_DAYS = 30

#: How long after the change a verdict becomes reachable at all.
MATURITY_DAYS = SETTLE_DAYS + WINDOW_DAYS

Clock = Callable[[], datetime]


def _system_clock() -> datetime:
    return datetime.now(UTC)


#: Recommendations that reached DONE long enough ago to have a complete after
#: window. `MAX(occurred_at)` rather than MIN because if a recommendation were ever
#: reopened and done a second time, the second change is the one being measured.
#: Today it can only happen once, since both of DONE's successors are terminal, so
#: the two agree and MAX is the one that stays right if that map ever changes.
MATURE = text(
    "SELECT r.recommendation_id, r.resource_id, r.lifecycle, "
    "MAX(e.occurred_at)::date AS done_on "
    "FROM recommendation r "
    "JOIN recommendation_event e ON e.recommendation_id = r.recommendation_id "
    "WHERE r.tenant_id = :tenant AND e.tenant_id = :tenant AND e.to_lifecycle = 'DONE' "
    "GROUP BY r.recommendation_id, r.resource_id, r.lifecycle "
    "HAVING MAX(e.occurred_at)::date <= :latest "
    "ORDER BY r.recommendation_id"
)

#: Both windows in one read. Cost is coalesced to zero because the absence of a
#: charge is a measured zero: the resource billed nothing. Usage is **not**, because
#: `consumed_quantity` is nullable in the billing rows and a null sum means nobody
#: published a quantity. Coalescing that to zero would turn an unmeasured control
#: into a workload that vanished, which is the one thing this collector exists to
#: avoid claiming. Constraint 5.
WINDOWS = text(
    "SELECT "
    "COALESCE(SUM(effective_cost) FILTER ("
    "  WHERE date(charge_period_start) >= :b_start AND date(charge_period_start) < :b_end"
    "), 0) AS cost_before, "
    "COALESCE(SUM(effective_cost) FILTER ("
    "  WHERE date(charge_period_start) >= :a_start AND date(charge_period_start) < :a_end"
    "), 0) AS cost_after, "
    "SUM(consumed_quantity) FILTER ("
    "  WHERE date(charge_period_start) >= :b_start AND date(charge_period_start) < :b_end"
    ") AS usage_before, "
    "SUM(consumed_quantity) FILTER ("
    "  WHERE date(charge_period_start) >= :a_start AND date(charge_period_start) < :a_end"
    ") AS usage_after, "
    "COUNT(*) AS billing_rows "
    "FROM cost_focus_daily "
    "WHERE tenant_id = :tenant AND resource_id = :resource "
    "AND date(charge_period_start) >= :b_start AND date(charge_period_start) < :a_end"
)

WRITE = text(
    "INSERT INTO realized_saving (realized_id, recommendation_id, tenant_id, "
    "window_before_start, window_before_end, window_after_start, window_after_end, "
    "cost_before, cost_after, usage_before, usage_after, verdict, why, as_of, collected_at) "
    "VALUES (:id, :recommendation, :tenant, :b_start, :b_end, :a_start, :a_end, "
    ":cost_before, :cost_after, :usage_before, :usage_after, :verdict, :why, :as_of, :now) "
    "ON CONFLICT (recommendation_id) DO UPDATE SET "
    "window_before_start = EXCLUDED.window_before_start, "
    "window_before_end = EXCLUDED.window_before_end, "
    "window_after_start = EXCLUDED.window_after_start, "
    "window_after_end = EXCLUDED.window_after_end, "
    "cost_before = EXCLUDED.cost_before, cost_after = EXCLUDED.cost_after, "
    "usage_before = EXCLUDED.usage_before, usage_after = EXCLUDED.usage_after, "
    "verdict = EXCLUDED.verdict, why = EXCLUDED.why, as_of = EXCLUDED.as_of, "
    "collected_at = EXCLUDED.collected_at"
)

MOVE = text(
    "UPDATE recommendation SET lifecycle = :to, collected_at = :now "
    "WHERE tenant_id = :tenant AND recommendation_id = :id"
)

#: The same append only log the route writes to. The actor is this collector rather
#: than a person, which is the honest entry: nobody decided this, a measurement did.
EVENT = text(
    "INSERT INTO recommendation_event (event_id, recommendation_id, tenant_id, "
    "from_lifecycle, to_lifecycle, actor, reason, occurred_at, as_of, collected_at) "
    "VALUES (:event, :id, :tenant, :from, :to, :actor, :reason, :now, :now, :now)"
)

#: A recommendation whose resource matches no billing row at all. Recorded rather
#: than left to read as INCONCLUSIVE, because every verdict for that resource will
#: be inconclusive for a reason that is ours: the resource identifier on the finding
#: does not match the one on the charge. An estate where that happens everywhere
#: would otherwise look like an estate where nothing can be proved.
UNJOINED_ERROR = text(
    "INSERT INTO sync_error (error_id, tenant_id, collector, scope_key, error_type, "
    "detail, remediation, first_seen_at, last_seen_at, occurrences) "
    "VALUES (:id, :t, :c, :s, 'NoData', :d, :r, :now, :now, 1) "
    "ON CONFLICT (tenant_id, collector, scope_key, error_type) DO UPDATE SET "
    "detail = EXCLUDED.detail, last_seen_at = EXCLUDED.last_seen_at, "
    "occurrences = sync_error.occurrences + 1"
)


def _windows(done_on: date) -> tuple[Window, Window]:
    """The two comparison periods around a change made on `done_on`.

    Half open on both sides, and the after window starts `SETTLE_DAYS` later than
    the before window ends, which is the gap the docstring argues for.
    """
    before = Window(start=done_on - timedelta(days=WINDOW_DAYS), end=done_on)
    after_start = done_on + timedelta(days=SETTLE_DAYS)
    return before, Window(start=after_start, end=after_start + timedelta(days=WINDOW_DAYS))


def _quantity(value: Any) -> Decimal | None:
    """A usage sum, or None where the rows published none.

    The null survives all the way to the column, per `0012`. Turning it into a zero
    here would be the same mistake one layer earlier than the screen.
    """
    return None if value is None else Decimal(value)


class RealizedSavingsCollector:
    """The north star metric, measured rather than modelled."""

    def __init__(self, clock: Clock = _system_clock) -> None:
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        at = self._clock()
        tenant = context.unit.tenant_id
        mature = context.connection.execute(
            MATURE,
            {"tenant": tenant, "latest": at.date() - timedelta(days=MATURITY_DAYS)},
        ).all()

        written = 0
        unjoined: list[str] = []

        for recommendation_id, resource_id, lifecycle, done_on in mature:
            before, after = _windows(done_on)
            found = context.connection.execute(
                WINDOWS,
                {
                    "tenant": tenant,
                    "resource": resource_id,
                    "b_start": before.start,
                    "b_end": before.end,
                    "a_start": after.start,
                    "a_end": after.end,
                },
            ).one()

            if found.billing_rows == 0:
                # No charge for this resource anywhere in either window. The
                # verdict would be inconclusive and the reason would be a join
                # that did not line up, so it is named instead of written.
                unjoined.append(resource_id)
                continue

            verdict = judge(
                before=before,
                after=after,
                cost_before=Decimal(found.cost_before),
                cost_after=Decimal(found.cost_after),
                usage_before=_quantity(found.usage_before),
                usage_after=_quantity(found.usage_after),
            )
            self._record(context, recommendation_id, before, after, found, verdict, at)
            self._maybe_move(context, recommendation_id, lifecycle, verdict, at)
            written += 1

        if unjoined:
            self._record_gap(context, unjoined, at)

        return CollectorOutcome(items_written=written)

    def _record(
        self,
        context: CollectorContext,
        recommendation_id: Any,
        before: Window,
        after: Window,
        found: Any,
        verdict: Realization,
        at: datetime,
    ) -> None:
        context.connection.execute(
            WRITE,
            {
                "id": uuid4(),
                "recommendation": recommendation_id,
                "tenant": context.unit.tenant_id,
                "b_start": before.start,
                "b_end": before.end,
                "a_start": after.start,
                "a_end": after.end,
                "cost_before": Decimal(found.cost_before),
                "cost_after": Decimal(found.cost_after),
                "usage_before": _quantity(found.usage_before),
                "usage_after": _quantity(found.usage_after),
                "verdict": verdict.verdict.value,
                "why": verdict.why,
                # The charges were true when they were billed, and the last day of
                # the after window is the latest of them. `collected_at` is when
                # this looked. Constraint 10.
                "as_of": datetime(after.end.year, after.end.month, after.end.day, tzinfo=UTC),
                "now": at,
            },
        )

    def _maybe_move(
        self,
        context: CollectorContext,
        recommendation_id: Any,
        lifecycle: str,
        verdict: Realization,
        at: datetime,
    ) -> None:
        """Move DONE on, or leave it exactly where it is.

        The transition map is the domain's, not a second copy. An INCONCLUSIVE
        verdict has no target at all, and a recommendation already moved on by an
        earlier run is left alone rather than moved from a terminal state, which
        `ALLOWED` would refuse anyway.
        """
        if lifecycle != Lifecycle.DONE.value:
            return
        target = {
            Verdict.VERIFIED: Lifecycle.VERIFIED,
            Verdict.REGRESSED: Lifecycle.REGRESSED,
        }.get(verdict.verdict)
        if target is None or target not in ALLOWED[Lifecycle.DONE]:
            return

        tenant = context.unit.tenant_id
        context.connection.execute(
            MOVE, {"to": target.value, "now": at, "tenant": tenant, "id": recommendation_id}
        )
        context.connection.execute(
            EVENT,
            {
                "event": uuid4(),
                "id": recommendation_id,
                "tenant": tenant,
                "from": Lifecycle.DONE.value,
                "to": target.value,
                "actor": COLLECTOR,
                # The working, carried into the log. A state change a reader cannot
                # account for is one they will not trust the next time.
                "reason": verdict.why,
                "now": at,
            },
        )

    def _record_gap(self, context: CollectorContext, unjoined: list[str], at: datetime) -> None:
        context.connection.execute(
            UNJOINED_ERROR,
            {
                "id": uuid4(),
                "t": context.unit.tenant_id,
                "c": COLLECTOR,
                "s": SCOPE,
                "d": (
                    f"{len(unjoined)} completed recommendations name a resource with no "
                    f"billing rows in either window, so no saving could be measured for "
                    f"them. First: {unjoined[0]}"
                ),
                "r": (
                    "Check that the resource identifier on the recommendation matches "
                    "the one on the charge. Compute Optimizer returns an ARN and the "
                    "billing export may carry a bare instance id, or the charge may be "
                    "attributed to a parent resource such as a cluster."
                ),
                "now": at,
            },
        )
