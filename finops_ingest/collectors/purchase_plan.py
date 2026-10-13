"""Meter's purchase plan, drafted daily from Meter's own tables. FEAT-089, TASK-P14-007.

P14 spec sections 5.2, 5.6 and 7, OPEN-40. One organization wide unit a day. It lapses a draft from
an earlier month that nobody approved, so a plan is never approved against usage a month old, then
drafts this month's plan, or redrafts it while it is still a draft. A plan somebody has acted on is
left as it is. The arithmetic is `finops_query.purchase_plan`, pure; this module gathers its inputs.

**What it reads.** The last 30 days of the bill's eligible usage, EC2 instances in shared tenancy,
at its on demand equivalent: what a commitment did not cover at its Effective Cost, and what one
did at its List Cost. P9's on demand price for each usage type, by the bill's SKU, or by the usage
type alone where only one operating system is priced for it, and P9's two Savings Plans rates for
the same usage type and operating system, in the policy's term and payment option. And what the
inventory holds that applies to EC2, each at its hourly value, a reservation's modelled.

**Nothing is guessed.** A usage type P9 cannot price unambiguously reaches the arithmetic with no
rate, so its share is named as unpriced rather than priced at a rate that may be another operating
system's.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Final
from uuid import UUID, uuid4

from sqlalchemy import text

from finops_core.domain.commitments import EC2, RESERVATION, SAVINGS_PLAN, CommitmentPolicy
from finops_ingest.commitment_policy import policy_for
from finops_ingest.registry import CollectorContext, CollectorOutcome
from finops_query.commitment_calendar import Held as Holding
from finops_query.commitment_calendar import hourly_value
from finops_query.purchase_plan import (
    FAMILY_BOUND,
    FLEXIBLE,
    Held,
    Line,
    Plan,
    Rate,
    Usage,
    draft,
    first_of_month,
)

COLLECTOR = "purchase_plan"

#: Who the collector's own transitions are recorded as.
PRINCIPAL: Final = "collector:purchase_plan"
WINDOW: Final = timedelta(days=30)
#: EC2 instance hours on demand in shared tenancy, the usage P9 holds Savings Plans rates for.
ELIGIBLE: Final = "%BoxUsage:%"
ON_DEMAND_SERVICE: Final = "AmazonEC2"
RATES_SERVICE: Final = "ComputeSavingsPlans"
#: Every rate P9 stores is in US dollars; it refuses a sheet in any other currency.
CURRENCY: Final = "USD"
#: The price list's operating system, as a Savings Plans rate names the same product.
PRODUCTS: Final = {
    "Linux": "Linux/UNIX",
    "Windows": "Windows",
    "RHEL": "Red Hat Enterprise Linux",
    "SUSE": "SUSE Linux",
}
LAPSED_NOTE: Final = "Nobody approved it within its month, and its usage is now a month old."

LAPSE = text(
    "UPDATE purchase_plan SET status = 'LAPSED' WHERE tenant_id = :tenant AND status = 'DRAFT' "
    "AND plan_month < :month RETURNING plan_id"
)
EVENT = text(
    "INSERT INTO purchase_plan_event (event_id, plan_id, tenant_id, from_status, to_status, "
    "principal, at, note) VALUES (:event, :plan, :tenant, :from_status, :to_status, :principal, "
    ":at, :note)"
)
CURRENT = text(
    "SELECT plan_id, status FROM purchase_plan WHERE tenant_id = :tenant AND plan_month = :month"
)
DAYS = text(
    "SELECT DISTINCT (charge_period_start AT TIME ZONE 'UTC')::date FROM cost_focus_daily "
    "WHERE tenant_id = :tenant AND billing_period_start >= :first_period "
    "AND charge_period_start >= :start AND charge_period_start < :end"
)
USAGE = text(
    "SELECT (charge_period_start AT TIME ZONE 'UTC')::date AS day, region_id, x_usage_type, "
    "sku_id, SUM(CASE WHEN commitment_discount_id IS NULL THEN effective_cost "
    "ELSE COALESCE(list_cost, effective_cost) END) AS on_demand, MAX(as_of) AS as_of "
    "FROM cost_focus_daily WHERE tenant_id = :tenant AND billing_period_start >= :first_period "
    "AND charge_period_start >= :start AND charge_period_start < :end "
    "AND charge_category = 'Usage' AND region_id IS NOT NULL AND x_usage_type LIKE :eligible "
    "GROUP BY 1, 2, 3, 4"
)
ON_DEMAND = text(
    "SELECT region, sku, sku_meter, recurring_unit_price, "
    "sku_price_details ->> 'operatingSystem' AS system, as_of FROM price "
    "WHERE tenant_id = :tenant AND service_code = :service AND pricing_category = 'Standard' "
    "AND region = ANY(:regions) AND (sku = ANY(:skus) OR sku_meter = ANY(:meters))"
)
COMMITTED = text(
    "SELECT region, sku_meter, offering_class, recurring_unit_price, "
    "sku_price_details ->> 'productDescription' AS product, as_of FROM price "
    "WHERE tenant_id = :tenant AND service_code = :service AND pricing_category = 'Committed' "
    "AND region = ANY(:regions) AND sku_meter = ANY(:meters) AND lease_years = :term "
    "AND purchase_option = :payment AND offering_class = ANY(:programs)"
)
HELD = text(
    "SELECT kind, commitment_id, program, region_id, applies_to, quantity, hourly_commitment, "
    "recurring_hourly, upfront_amount, term_months, ends_at FROM commitment_inventory "
    "WHERE tenant_id = :tenant AND ends_at > :now "
    "AND ((kind = :plan AND program = ANY(:programs)) OR (kind = :reservation AND program = :ec2))"
)
WRITE_PLAN = text(
    "INSERT INTO purchase_plan (plan_id, tenant_id, ingest_run_id, plan_month, target_coverage, "
    "term_years, payment_option, ladder_limit, window_start, window_end, days_held, "
    "steady_hourly, held_hourly, target_hourly, beyond_hourly, unpriced, no_purchase_reason, "
    "currency, as_of, collected_at) VALUES (:plan, :tenant, :run, :month, :coverage, :term, "
    ":payment, :ladder, :window_start, :window_end, :days, :steady, :held, :target, :beyond, "
    "CAST(:unpriced AS JSONB), :reason, :currency, :as_of, :collected_at) "
    "ON CONFLICT (plan_id) DO UPDATE SET ingest_run_id = EXCLUDED.ingest_run_id, "
    "target_coverage = EXCLUDED.target_coverage, term_years = EXCLUDED.term_years, "
    "payment_option = EXCLUDED.payment_option, ladder_limit = EXCLUDED.ladder_limit, "
    "window_start = EXCLUDED.window_start, window_end = EXCLUDED.window_end, "
    "days_held = EXCLUDED.days_held, steady_hourly = EXCLUDED.steady_hourly, "
    "held_hourly = EXCLUDED.held_hourly, target_hourly = EXCLUDED.target_hourly, "
    "beyond_hourly = EXCLUDED.beyond_hourly, unpriced = EXCLUDED.unpriced, "
    "no_purchase_reason = EXCLUDED.no_purchase_reason, currency = EXCLUDED.currency, "
    "as_of = EXCLUDED.as_of, collected_at = EXCLUDED.collected_at"
)
CLEAR_LINES = text("DELETE FROM purchase_plan_line WHERE plan_id = :plan")
WRITE_LINE = text(
    "INSERT INTO purchase_plan_line (plan_id, line_no, tenant_id, program, instance_family, "
    "region_id, tranche_month, hourly_commitment, discount_percent, covers_hourly, "
    "monthly_saving, usage_floor_percent, upfront_cost) VALUES (:plan, :line, :tenant, :program, "
    ":family, :region, :tranche, :hourly, :discount, :covers, :saving, :floor, :upfront)"
)

Clock = Callable[[], datetime]


def _system_clock() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class _Price:
    """One of P9's on demand prices: where, which SKU and usage type, and for which system."""

    region: str
    sku: str
    meter: str
    rate: Decimal
    system: str | None
    as_of: datetime


@dataclass(frozen=True)
class _Inputs:
    usage: tuple[Usage, ...]
    rates: dict[tuple[str, str], Rate]
    days: tuple[date, ...]
    as_of: datetime | None


def family_of(usage_type: str) -> str:
    """`EU-BoxUsage:m6i.large` is family `m6i`, and so is the instance type `m6i.large`."""
    instance = usage_type.split(":", 1)[-1]
    return instance.split(".", 1)[0]


class PurchasePlanCollector:
    """Lapses an earlier month's unapproved draft and drafts, or redrafts, this month's plan."""

    def __init__(self, *, clock: Clock = _system_clock) -> None:
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        if context.run_id is None:
            raise ValueError("purchase_plan needs the run id from the ledger's claim")
        connection = context.connection
        tenant = context.unit.tenant_id
        now = self._clock()
        today = now.date()
        month = first_of_month(today)
        lapsed = connection.execute(LAPSE, {"tenant": tenant, "month": month}).scalars().all()
        for plan_id in lapsed:
            _event(connection, plan_id, tenant, ("DRAFT", "LAPSED"), now, LAPSED_NOTE)
        current = connection.execute(CURRENT, {"tenant": tenant, "month": month}).one_or_none()
        if current is not None and current.status != "DRAFT":
            return CollectorOutcome(items_written=len(lapsed), items_removed=0)

        policy = policy_for(connection, tenant)
        start = today - WINDOW
        inputs = _inputs(connection, tenant, policy, start, today)
        plan = draft(
            usage=inputs.usage,
            rates=inputs.rates,
            held=_held(connection, tenant, now),
            days_held=inputs.days,
            policy=policy,
            start=today,
            window_start=start,
            window_end=today,
        )
        plan_id = current.plan_id if current is not None else uuid4()
        as_of = min(inputs.as_of or now, now)
        row = _plan_row(plan, plan_id, tenant, context.run_id, month, policy, as_of, now)
        connection.execute(WRITE_PLAN, row)
        if current is None:
            _event(connection, plan_id, tenant, (None, "DRAFT"), now, "Drafted.")
        removed = connection.execute(CLEAR_LINES, {"plan": plan_id}).rowcount or 0
        if plan.lines:
            connection.execute(
                WRITE_LINE,
                [_line_row(line, index, plan_id, tenant) for index, line in enumerate(plan.lines)],
            )
        return CollectorOutcome(
            items_written=1 + len(plan.lines) + len(lapsed), items_removed=int(removed)
        )


def _event(
    connection: Any,
    plan_id: UUID,
    tenant: UUID,
    transition: tuple[str | None, str],
    at: datetime,
    note: str,
) -> None:
    connection.execute(
        EVENT,
        {
            "event": uuid4(),
            "plan": plan_id,
            "tenant": tenant,
            "from_status": transition[0],
            "to_status": transition[1],
            "principal": PRINCIPAL,
            "at": at,
            "note": note,
        },
    )


def _inputs(
    connection: Any, tenant: UUID, policy: CommitmentPolicy, start: date, end: date
) -> _Inputs:
    window = {
        "tenant": tenant,
        "first_period": first_of_month(start),
        "start": datetime(start.year, start.month, start.day, tzinfo=UTC),
        "end": datetime(end.year, end.month, end.day, tzinfo=UTC),
    }
    days = tuple(connection.execute(DAYS, window).scalars().all())
    rows = connection.execute(USAGE, {**window, "eligible": ELIGIBLE}).all()
    regions = sorted({row.region_id for row in rows})
    meters = sorted({row.x_usage_type for row in rows})
    asked = {"tenant": tenant, "regions": regions, "meters": meters}
    on_demand = [
        _Price(row.region, row.sku, row.sku_meter, row.recurring_unit_price, row.system, row.as_of)
        for row in connection.execute(
            ON_DEMAND,
            {
                **asked,
                "service": ON_DEMAND_SERVICE,
                "skus": sorted({row.sku_id for row in rows if row.sku_id}),
            },
        )
    ]
    committed = connection.execute(
        COMMITTED,
        {
            **asked,
            "service": RATES_SERVICE,
            "term": policy.term_years,
            "payment": policy.payment_option,
            "programs": [FLEXIBLE, FAMILY_BOUND],
        },
    ).all()
    usage: list[Usage] = []
    rates: dict[tuple[str, str], Rate] = {}
    for row in rows:
        kind = f"{row.x_usage_type}|{row.sku_id or ''}"
        usage.append(
            Usage(
                day=row.day,
                region=row.region_id,
                family=family_of(row.x_usage_type),
                kind=kind,
                on_demand=Decimal(row.on_demand),
            )
        )
        if (row.region_id, kind) not in rates:
            rates[(row.region_id, kind)] = _rate(
                row.region_id, row.x_usage_type, row.sku_id, on_demand, committed
            )
    as_of = max((row.as_of for row in rows), default=None)
    return _Inputs(usage=tuple(usage), rates=rates, days=days, as_of=as_of)


def _held(connection: Any, tenant: UUID, now: datetime) -> tuple[Held, ...]:
    found = connection.execute(
        HELD,
        {
            "tenant": tenant,
            "now": now,
            "plan": SAVINGS_PLAN,
            "programs": [FLEXIBLE, FAMILY_BOUND],
            "reservation": RESERVATION,
            "ec2": EC2,
        },
    ).all()
    return tuple(_holding(row) for row in found)


def _rate(
    region: str,
    usage_type: str,
    sku: str | None,
    on_demand: Sequence[_Price],
    committed: Iterable[Any],
) -> Rate:
    """P9's rates for one usage type in one Region, or a Rate of nothing where they are unclear.

    The bill's SKU names the on demand price exactly. Without one, the usage type does only when
    P9 prices it for one operating system, because one usage type runs Linux and Windows at
    different prices.
    """
    in_region = [one for one in on_demand if one.region == region]
    named = [one for one in in_region if sku and one.sku == sku]
    found = named or [one for one in in_region if one.meter == usage_type]
    if not found or len({one.system for one in found}) != 1:
        return Rate(on_demand=None, flexible=None, family_bound=None)
    price = max(found, key=lambda one: one.as_of)
    product = PRODUCTS.get(price.system or "")
    newest: dict[str, tuple[datetime, Decimal]] = {}
    for row in committed:
        if (row.region, row.sku_meter, row.product) != (region, usage_type, product):
            continue
        seen = newest.get(row.offering_class)
        if seen is None or row.as_of > seen[0]:
            newest[row.offering_class] = (row.as_of, row.recurring_unit_price)
    flexible = newest.get(FLEXIBLE)
    family_bound = newest.get(FAMILY_BOUND)
    return Rate(
        on_demand=price.rate,
        flexible=flexible[1] if flexible else None,
        family_bound=family_bound[1] if family_bound else None,
    )


def _holding(row: Any) -> Held:
    """One commitment from the inventory at its hourly value, with the family it is bound to."""
    value, _basis = hourly_value(
        Holding(
            commitment_id=row.commitment_id,
            kind=row.kind,
            program=row.program,
            ends_at=row.ends_at,
            quantity=row.quantity,
            hourly_commitment=row.hourly_commitment,
            recurring_hourly=row.recurring_hourly,
            upfront_amount=row.upfront_amount,
            term_months=row.term_months,
        )
    )
    bound = row.kind == RESERVATION or row.program == FAMILY_BOUND
    return Held(
        hourly=value,
        ends=row.ends_at.date(),
        family=family_of(row.applies_to) if bound and row.applies_to else None,
        region=row.region_id if bound else None,
    )


def _plan_row(
    plan: Plan,
    plan_id: UUID,
    tenant: UUID,
    run: UUID,
    month: date,
    policy: CommitmentPolicy,
    as_of: datetime,
    now: datetime,
) -> dict[str, Any]:
    unpriced = [
        {
            "family": one.family,
            "region": one.region,
            "steady_hourly": str(one.steady_hourly),
            "reason": one.reason,
        }
        for one in plan.unpriced
    ]
    return {
        "plan": plan_id,
        "tenant": tenant,
        "run": run,
        "month": month,
        "coverage": policy.target_coverage,
        "term": policy.term_years,
        "payment": policy.payment_option,
        "ladder": policy.ladder_limit,
        "window_start": plan.window_start,
        "window_end": plan.window_end,
        "days": plan.days_held,
        "steady": plan.steady_hourly,
        "held": plan.held_hourly,
        "target": plan.target_hourly,
        "beyond": plan.beyond_hourly,
        "unpriced": json.dumps(unpriced),
        "reason": plan.reason,
        "currency": CURRENCY,
        "as_of": as_of,
        "collected_at": now,
    }


def _line_row(line: Line, index: int, plan_id: UUID, tenant: UUID) -> dict[str, Any]:
    return {
        "plan": plan_id,
        "line": index + 1,
        "tenant": tenant,
        "program": line.program,
        "family": line.family,
        "region": line.region,
        "tranche": line.tranche,
        "hourly": line.hourly_commitment,
        "discount": line.discount_percent,
        "covers": line.covers_hourly,
        "saving": line.monthly_saving,
        "floor": line.usage_floor_percent,
        "upfront": line.upfront_cost,
    }
