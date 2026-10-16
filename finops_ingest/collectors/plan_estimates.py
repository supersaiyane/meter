"""Each Terraform plan received, priced and its estimate written. FEAT-095, TASK-P16-005.

P16 spec sections 5.3, 5.4, 5.7 and 7. Every ten minutes, for each plan `RECEIVED`, the changes the
reduction kept are priced by `finops_query.plan_pricing` from the catalog Meter already holds, read
by `StoredCatalogue`, and the estimate is written: its monthly figures before, after and the change,
and one line per change with its figures and components, or the reason it has none. The plan is
then `PRICED`. It reads only Meter's own tables, so it is bound with the other collectors that do,
and a code host that is down holds no estimate back; the comment is written apart, TASK-P16-006.

**A figure is never nought for a resource not priced.** A line with a reason carries no figure, and
the database refuses one that does, constraint 5. Every figure is modelled, at list, on demand, 730
hours a month, and is stored to six places, with the change the after less the before as stored.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Final

from sqlalchemy import text

from finops_ingest.collectors.catalog_reads import StoredCatalogue
from finops_ingest.registry import CollectorContext, CollectorOutcome
from finops_query.plan_pricing import Estimate, EstimateLine, price_change
from finops_query.plan_quotes import CURRENCY, Side
from finops_query.plan_reading import PlannedChange

COLLECTOR = "plan_estimates"
#: The places a figure is stored to, as NUMERIC(20, 6) holds it.
PLACES: Final = Decimal("0.000001")

RECEIVED = text(
    "SELECT plan_id, as_of FROM terraform_plan WHERE tenant_id = :t AND status = 'RECEIVED' "
    "ORDER BY received_at, plan_id"
)
CHANGES = text(
    "SELECT address, resource_type, actions, region, before, after, unknown, withheld "
    "FROM planned_change WHERE plan_id = :plan ORDER BY address"
)
WRITE_ESTIMATE = text(
    "INSERT INTO plan_estimate (plan_id, tenant_id, monthly_before, monthly_after, monthly_change, "
    "currency, priced_lines, unpriced_lines, priced_at, as_of, collected_at) VALUES (:plan, :t, "
    ":before, :after, :change, :currency, :priced, :unpriced, :now, :as_of, :now)"
)
WRITE_LINE = text(
    "INSERT INTO plan_estimate_line (plan_id, tenant_id, address, resource_type, actions, region, "
    "monthly_before, monthly_after, reason, notes, components) VALUES (:plan, :t, :address, "
    ":type, :actions, :region, :before, :after, :reason, :notes, CAST(:components AS jsonb))"
)
PRICED = text(
    "UPDATE terraform_plan SET status = 'PRICED' WHERE plan_id = :plan AND status = 'RECEIVED'"
)

Clock = Callable[[], datetime]


def _system_clock() -> datetime:
    return datetime.now(UTC)


class PlanEstimatesCollector:
    """Prices every plan received for the unit's tenant and writes each estimate."""

    def __init__(self, clock: Clock = _system_clock) -> None:
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        connection = context.connection
        tenant = context.unit.tenant_id
        now = self._clock()
        catalogue = StoredCatalogue(connection, tenant)
        plans = connection.execute(RECEIVED, {"t": tenant}).all()
        for plan in plans:
            rows = connection.execute(CHANGES, {"plan": plan.plan_id}).all()
            estimate = Estimate(tuple(price_change(_change(row), catalogue) for row in rows))
            _write(connection, tenant, plan, estimate, now)
        return CollectorOutcome(items_written=len(plans))


def _change(row: Any) -> PlannedChange:
    return PlannedChange(
        address=row.address,
        resource_type=row.resource_type,
        actions=tuple(row.actions),
        region=row.region,
        before=row.before,
        after=row.after,
        unknown=tuple(row.unknown),
        withheld=tuple(row.withheld),
    )


def money(amount: Decimal | None) -> Decimal | None:
    """A figure to the places it is stored to; no figure stays none."""
    return None if amount is None else amount.quantize(PLACES)


def _write(connection: Any, tenant: Any, plan: Any, estimate: Estimate, now: datetime) -> None:
    before = money(estimate.monthly_before) or Decimal(0)
    after = money(estimate.monthly_after) or Decimal(0)
    unpriced = len(estimate.unpriced)
    connection.execute(
        WRITE_ESTIMATE,
        {
            "plan": plan.plan_id,
            "t": tenant,
            "before": before,
            "after": after,
            "change": after - before,
            "currency": CURRENCY,
            "priced": len(estimate.lines) - unpriced,
            "unpriced": unpriced,
            "now": now,
            "as_of": plan.as_of,
        },
    )
    if estimate.lines:
        connection.execute(WRITE_LINE, [_line(plan.plan_id, tenant, one) for one in estimate.lines])
    connection.execute(PRICED, {"plan": plan.plan_id})


def _line(plan: Any, tenant: Any, line: EstimateLine) -> dict[str, Any]:
    return {
        "plan": plan,
        "t": tenant,
        "address": line.address,
        "type": line.resource_type,
        "actions": list(line.actions),
        "region": line.region,
        "before": money(line.monthly_before),
        "after": money(line.monthly_after),
        "reason": line.reason,
        "notes": list(line.notes),
        "components": json.dumps(
            [*_components("before", line.before), *_components("after", line.after)]
        ),
    }


def _components(side: str, priced: Side | None) -> list[dict[str, str]]:
    """Each component as figures, its price kept so a pruned catalog changes no past line."""
    if priced is None:
        return []
    return [
        {
            "side": side,
            "what": one.what,
            "quantity": str(one.quantity),
            "unit": one.quote.unit,
            "unit_price": str(one.quote.unit_price),
            "monthly": str(one.monthly),
            "sku_price_id": one.quote.sku_price_id,
            "version": one.quote.version,
        }
        for one in priced.components
    ]
