"""`cost_focus_monthly`, derived from `cost_focus_daily` and never ingested.

Two callers need this aggregate and they need it for different reasons, which
is exactly why the arithmetic lives here rather than in both of them. The cost
collector rolls up the period it just wrote, so a screen can read a month
without summing a month of line items. Retention rolls up everything past the
cutoff before dropping those partitions, so the shape survives the detail.

Two sources for one number is how the two come to disagree, and the
disagreement is always found by a person reading a screen rather than by a
test.

**The two callers differ in one way that matters.** The collector may prune,
because the period it just wrote still has all its daily rows, so a monthly row
with nothing behind it is a group the provider retracted entirely. Retention may
not, because the whole point of its pass is that the monthly rows outlive the
daily partitions it is about to drop. Pruning there would delete the archive it
exists to create.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import text

#: One body, two predicates. Written once because the columns, the grouping and
#: the conflict rule are the definition of the aggregate, and a second copy of a
#: definition is a second definition.
_BODY = (
    "INSERT INTO cost_focus_monthly (tenant_id, billing_month, sub_account_id, "
    "service_name, region_id, billed_cost, effective_cost, line_items, as_of, "
    "collected_at) "
    "SELECT tenant_id, date_trunc('month', billing_period_start)::date, "
    "COALESCE(sub_account_id, ''), service_name, COALESCE(region_id, ''), "
    "SUM(billed_cost), SUM(effective_cost), COUNT(*), MIN(as_of), :at "
    "FROM cost_focus_daily WHERE tenant_id = :tenant AND {predicate} "
    "GROUP BY tenant_id, date_trunc('month', billing_period_start), "
    "COALESCE(sub_account_id, ''), service_name, COALESCE(region_id, '') "
    "ON CONFLICT (tenant_id, billing_month, sub_account_id, service_name, region_id) "
    "DO UPDATE SET billed_cost = EXCLUDED.billed_cost, "
    "effective_cost = EXCLUDED.effective_cost, line_items = EXCLUDED.line_items, "
    "collected_at = EXCLUDED.collected_at"
)

#: A predicate on the column rather than on a function of it, so the partition
#: is pruned instead of the whole table being scanned to find one month.
ONE_PERIOD = text(_BODY.format(predicate="billing_period_start = :period"))
EVERYTHING_BEFORE = text(_BODY.format(predicate="billing_period_start < :before"))

#: Groups whose last line item was withdrawn. Scoped to the one month being
#: rolled up, because outside it the absence of daily rows is retention having
#: done its job rather than the provider having retracted anything.
PRUNE = text(
    "DELETE FROM cost_focus_monthly m WHERE m.tenant_id = :tenant "
    "AND m.billing_month = :period AND NOT EXISTS ("
    "SELECT 1 FROM cost_focus_daily d WHERE d.tenant_id = m.tenant_id "
    "AND d.billing_period_start = m.billing_month "
    "AND COALESCE(d.sub_account_id, '') = m.sub_account_id "
    "AND d.service_name = m.service_name "
    "AND COALESCE(d.region_id, '') = m.region_id)"
)


def roll_up_period(connection: Any, *, tenant: Any, period: date, at: datetime) -> int:
    """Recompute one month from its line items, and drop what is no longer there.

    Called by the cost collector inside the same transaction that wrote the
    daily rows, so there is no instant at which the two disagree.

    The prune is why this is not simply an upsert. A group whose every line item
    the provider retracted leaves a monthly row with nothing behind it, and
    since the upsert only ever replaces groups it can still see, that row would
    keep its last known total forever. One vanished group is a small number. It
    is also permanent, and it only ever points one way.
    """
    written = connection.execute(
        ONE_PERIOD, {"tenant": tenant, "period": period, "at": at}
    ).rowcount
    connection.execute(PRUNE, {"tenant": tenant, "period": period})
    return int(written or 0)


def roll_up_before(connection: Any, *, tenant: Any, before: date, at: datetime) -> int:
    """Aggregate every month older than the boundary, ahead of dropping them.

    No prune. These months are about to lose their daily rows on purpose, and a
    pass that removed monthly rows with nothing behind them would delete the
    archive it exists to create.
    """
    written = connection.execute(
        EVERYTHING_BEFORE, {"tenant": tenant, "before": before, "at": at}
    ).rowcount
    return int(written or 0)
