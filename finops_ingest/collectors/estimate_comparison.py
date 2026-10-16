"""Each resource a merged plan created, set against its bill. FEAT-097, TASK-P16-007.

P16 spec sections 5.6 and 7. Daily. For every priced line that a merged pull request's last plan
for its folder created, this waits until FEAT-057 sees the address in the state the folder is
mapped to, and records when, from the first reading after the merge; the resource then joins the
bill by its identifier, as FEAT-029 joins it. Once the bill reaches the thirty days after the first
full billed day, `finops_query.estimate_accuracy.judge` sets the window's list cost against the
estimate, and the verdict is restated each run for sixty days after, so a restated bill restates it.

**Creations only, in v1.** A replacement keeps its address, and `resource_management` holds one row
per resource, so the day after the merge Meter cannot tell the new resource from the one it
replaced. A replacement, a change and a destroy are not compared; FEAT-029 measures a change a
recommendation drove.

**Nothing unknown reads as right.** A folder mapped to no one state, a resource not seen within
sixty days of the merge, and a window with no billed row are `NOT_COMPARED` with the reason, and
the database refuses a verdict without its figures. It reads only Meter's own tables.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Final

from sqlalchemy import text

from finops_ingest.registry import CollectorContext, CollectorOutcome
from finops_query.estimate_accuracy import (
    Billed,
    Judgement,
    Verdict,
    billed_through,
    judge,
    unseen_too_long,
    window_after,
)

COLLECTOR = "estimate_comparison"
#: Days after its window ends that a verdict is still read again, as the bill may be restated.
RESTATED_FOR: Final = timedelta(days=60)
#: The places a figure is stored to, as NUMERIC(20, 6) holds it.
PLACES: Final = Decimal("0.000001")
PERCENT_PLACES: Final = Decimal("0.0001")

CREATED = text(
    "SELECT l.plan_id, l.address, l.resource_type, l.monthly_after, p.state_reference, "
    "pr.merged_seen_at, c.verdict, c.seen_at, c.provider_id, c.window_end "
    "FROM plan_estimate_line l "
    "JOIN terraform_plan p ON p.plan_id = l.plan_id "
    "JOIN plan_pull_request pr ON pr.tenant_id = p.tenant_id AND pr.repository = p.repository "
    "AND pr.pull_request = p.pull_request "
    "LEFT JOIN estimate_comparison c ON c.plan_id = l.plan_id AND c.address = l.address "
    "WHERE l.tenant_id = :t AND pr.state = 'MERGED' AND l.reason IS NULL "
    "AND l.actions = ARRAY['create']::text[] AND l.monthly_after IS NOT NULL "
    "AND p.received_at = (SELECT max(q.received_at) FROM terraform_plan q "
    "WHERE q.tenant_id = p.tenant_id AND q.repository = p.repository "
    "AND q.pull_request = p.pull_request AND q.folder = p.folder AND q.status = 'PRICED') "
    "ORDER BY l.plan_id, l.address"
)
SEEN = text(
    "SELECT provider_id, as_of FROM resource_management WHERE tenant_id = :t "
    "AND state_reference = :state AND address = :address AND as_of >= :merged "
    "ORDER BY as_of LIMIT 1"
)
LAST_BILLED = text(
    "SELECT max(date(charge_period_start)) AS last_day, max(as_of) AS as_of "
    "FROM cost_focus_daily WHERE tenant_id = :t"
)
BILLED = text(
    "SELECT count(*) AS rows, count(list_cost) AS listed, "
    "coalesce(sum(list_cost), 0) AS listed_cost, coalesce(sum(effective_cost), 0) AS effective "
    "FROM cost_focus_daily WHERE tenant_id = :t AND resource_id = :resource "
    "AND date(charge_period_start) >= :start AND date(charge_period_start) < :end"
)
WRITE = text(
    "INSERT INTO estimate_comparison (plan_id, address, tenant_id, resource_type, provider_id, "
    "seen_at, window_start, window_end, estimate_monthly, list_monthly, effective_monthly, "
    "variance_percent, verdict, reason, judged_at, as_of, collected_at) VALUES (:plan, :address, "
    ":t, :type, :provider, :seen, :start, :end, :estimate, :list, :effective, :variance, "
    ":verdict, :reason, :now, :as_of, :now) ON CONFLICT (plan_id, address) DO UPDATE SET "
    "provider_id = EXCLUDED.provider_id, seen_at = EXCLUDED.seen_at, "
    "window_start = EXCLUDED.window_start, window_end = EXCLUDED.window_end, "
    "list_monthly = EXCLUDED.list_monthly, effective_monthly = EXCLUDED.effective_monthly, "
    "variance_percent = EXCLUDED.variance_percent, verdict = EXCLUDED.verdict, "
    "reason = EXCLUDED.reason, judged_at = EXCLUDED.judged_at, as_of = EXCLUDED.as_of, "
    "collected_at = EXCLUDED.collected_at"
)

UNMAPPED: Final = (
    "its folder is mapped to no one Terraform state, so Meter cannot tell where it was applied"
)
UNSEEN: Final = "not seen in its mapped state within sixty days of the merge"

Clock = Callable[[], datetime]


class EstimateComparisonCollector:
    """Sets each created resource's estimate against its thirty billed days."""

    def __init__(self, clock: Clock | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        connection, tenant = context.connection, context.unit.tenant_id
        now = self._clock()
        bill = connection.execute(LAST_BILLED, {"t": tenant}).one()
        written = 0
        for line in connection.execute(CREATED, {"t": tenant}).all():
            if _settled(line, now):
                continue
            row = self._compare(connection, tenant, line, now, bill)
            if row is not None:
                connection.execute(WRITE, row)
                written += 1
        return CollectorOutcome(items_written=written)

    def _compare(
        self, connection: Any, tenant: Any, line: Any, now: datetime, bill: Any
    ) -> dict[str, Any] | None:
        """The comparison to write for one line, or None while it waits to be seen."""
        base = {
            "plan": line.plan_id,
            "address": line.address,
            "t": tenant,
            "type": line.resource_type,
            "estimate": line.monthly_after,
            "now": now,
            "as_of": now,
        }
        if line.state_reference is None:
            return _row(base, Judgement(Verdict.NOT_COMPARED, reason=UNMAPPED))
        seen = _seen(connection, tenant, line)
        if seen is None:
            if unseen_too_long(line.merged_seen_at, now):
                return _row(base, Judgement(Verdict.NOT_COMPARED, reason=UNSEEN))
            return None
        provider, seen_at = seen
        window = window_after(seen_at)
        placed = {
            **base,
            "provider": provider,
            "seen": seen_at,
            "start": window.start,
            "end": window.end,
        }
        if not billed_through(window, bill.last_day):
            return _row(placed, Judgement(Verdict.PENDING))
        found = connection.execute(
            BILLED, {"t": tenant, "resource": provider, "start": window.start, "end": window.end}
        ).one()
        billed = Billed(
            rows=int(found.rows),
            listed_rows=int(found.listed),
            list_cost=Decimal(found.listed_cost),
            effective_cost=Decimal(found.effective),
        )
        as_of = min(bill.as_of, now) if bill.as_of is not None else now
        return _row({**placed, "as_of": as_of}, judge(Decimal(line.monthly_after), billed))


def _settled(line: Any, now: datetime) -> bool:
    """A comparison that will not change: never seen and given up on, or judged long enough ago."""
    if line.verdict is None:
        return False
    if line.window_end is None:
        return bool(line.verdict == Verdict.NOT_COMPARED)
    return bool(now.date() > line.window_end + RESTATED_FOR)


def _seen(connection: Any, tenant: Any, line: Any) -> tuple[str, datetime] | None:
    """The resource's identifier and when it was first seen after the merge, kept once known."""
    if line.seen_at is not None and line.provider_id is not None:
        return str(line.provider_id), line.seen_at
    found = connection.execute(
        SEEN,
        {
            "t": tenant,
            "state": line.state_reference,
            "address": line.address,
            "merged": line.merged_seen_at,
        },
    ).first()
    return None if found is None else (str(found.provider_id), found.as_of)


def _row(base: dict[str, Any], judgement: Judgement) -> dict[str, Any]:
    variance = judgement.variance_percent
    return {
        "provider": None,
        "seen": None,
        "start": None,
        "end": None,
        **base,
        "list": _money(judgement.list_monthly),
        "effective": _money(judgement.effective_monthly),
        "variance": None if variance is None else variance.quantize(PERCENT_PLACES),
        "verdict": judgement.verdict.value,
        "reason": judgement.reason,
    }


def _money(amount: Decimal | None) -> Decimal | None:
    return None if amount is None else amount.quantize(PLACES)
