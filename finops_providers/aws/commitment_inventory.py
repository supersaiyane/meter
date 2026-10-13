"""What each member account holds: its Savings Plans and its reservations. FEAT-086.

TASK-P14-002 and TASK-P14-003, P14 spec sections 5.3 and 5.5, OPEN-37 and OPEN-39, ADR-0037.
Each read is made as the account's own collector role, because a commitment belongs to the account
that bought it.
Savings Plans and the RDS, ElastiCache, OpenSearch, Redshift and MemoryDB reservations come through
the relay: Savings Plans have no interface endpoint, and the others' are not worth paying for a
read made once a day. EC2 reservations come through the EC2 endpoint the hub already has.

**Every page, whichever path a client takes.** The relay follows a token itself where botocore has
no paginator, and a direct client is followed here the same way, so a call that pages is read to
its end on both paths and never read as its first page alone.

**What the source said, typed.** A refusal is AccessDenied and a throttle Throttled, through
`translate`, as every adapter's are. A field the source's own model promises and an answer lacks is
SchemaDrift, never a commitment of nothing.

Unproved against a real account, ISS-002. The shapes are botocore's own models, which the tests
hold every answer to.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import partial
from typing import Any, Final
from uuid import UUID

from botocore.exceptions import BotoCoreError, ClientError, OperationNotPageableError

from finops_core.domain.account import AccountKey
from finops_core.domain.commitments import (
    EC2,
    ELASTICACHE,
    MEMORYDB,
    OPENSEARCH,
    RDS,
    REDSHIFT,
    RESERVATION,
    SAVINGS_PLAN,
    HeldCommitment,
    term_months,
)
from finops_core.errors import SchemaDrift
from finops_providers.aws.client import translate

COLLECTOR: Final = "commitment_inventory"

#: How a reservation's recurring charge is billed when it is billed every hour.
HOURLY: Final = "Hourly"

#: The currency of a reservation whose API names none, ElastiCache's and MemoryDB's: their prices
#: are AWS's list prices, which are in US dollars.
UNSTATED_CURRENCY: Final = "USD"

#: The most pages followed by hand, as the relay's own limit, so a token that never ends is a
#: failure rather than a loop.
MAX_PAGES: Final = 200

#: A client for one account: the account's id. Savings Plans have no Region.
SavingsPlansFor = Callable[[str], Any]
#: A client for one account and Region: the account's id and the Region.
ReservationsFor = Callable[[str, str], Any]

Clock = Callable[[], datetime]


def _system_clock() -> datetime:
    return datetime.now(UTC)


def _instant(value: Any) -> datetime:
    """A time as either path delivers it: a datetime from boto3, a string from the relay."""
    found = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return found if found.tzinfo is not None else found.replace(tzinfo=UTC)


def _money(value: Any) -> Decimal:
    """An amount as a Decimal, from the string or the float the source sends."""
    return Decimal(str(value))


def _hourly(charges: Iterable[Mapping[str, Any]], amount: str, frequency: str) -> Decimal:
    """The recurring charges billed every hour, summed. Another frequency is not an hourly rate."""
    return sum(
        (_money(charge[amount]) for charge in charges if charge.get(frequency) == HOURLY),
        Decimal(0),
    )


def _follow(operation: Callable[..., Any], scope: str) -> list[Any]:
    """Every page of a call botocore cannot paginate, following its token by hand."""
    pages: list[Any] = []
    token: dict[str, Any] = {}
    while len(pages) < MAX_PAGES:
        page = operation(**token)
        pages.append(page)
        name = next((key for key in ("NextToken", "nextToken") if page.get(key)), None)
        if name is None:
            return pages
        token = {name: page[name]}
    raise SchemaDrift(
        scope_key=scope,
        collector=COLLECTOR,
        detail=f"more than {MAX_PAGES} pages of commitments; none is kept rather than some",
    )


@dataclass(frozen=True)
class ReservedService:
    """Where one reserved service keeps each field, which differs from service to service."""

    program: str
    #: The describe call, as boto3 spells it, and the list in its answer.
    method: str
    key: str
    id_field: str
    type_field: str
    count_field: str
    payment_field: str = "OfferingType"


def _payment(stated: str) -> str:
    """A payment option in one spelling: `NO_UPFRONT`, as OpenSearch writes it, is `No Upfront`."""
    return stated.replace("_", " ").title() if stated.isupper() else stated


def _reservation(
    service: ReservedService,
    tenant: UUID,
    held: Mapping[str, Any],
    account: AccountKey,
    region: str,
    at: datetime,
) -> HeldCommitment:
    starts = _instant(held.get("Start") or held["StartTime"])
    duration = int(held["Duration"])
    charges = held.get("RecurringCharges", [])
    return HeldCommitment(
        tenant_id=tenant,
        kind=RESERVATION,
        commitment_id=str(held[service.id_field]),
        program=service.program,
        account_id=account.account_id,
        region_id=region,
        applies_to=str(held[service.type_field]),
        quantity=int(held[service.count_field]),
        hourly_commitment=None,
        term_months=term_months(duration),
        payment_option=_payment(str(held[service.payment_field])),
        upfront_amount=_money(held.get("FixedPrice") or 0),
        # EC2 names a recurring charge's parts Amount and Frequency; every other service prefixes
        # them with RecurringCharge.
        recurring_hourly=_hourly(charges, "Amount", "Frequency")
        + _hourly(charges, "RecurringChargeAmount", "RecurringChargeFrequency")
        + _money(held.get("UsagePrice") or 0),
        currency=str(held.get("CurrencyCode") or UNSTATED_CURRENCY),
        starts_at=starts,
        # EC2 states an end; the others state a start and a length, and the end is their sum.
        ends_at=_instant(held["End"]) if held.get("End") else starts + timedelta(seconds=duration),
        state=str(held["State"]),
        as_of=at,
        collected_at=at,
    )


#: Each reserved service the inventory reads, OPEN-37. DynamoDB reserved capacity has no read API,
#: ISS-295, so it is not here and is listed as unreadable rather than as none held.
RESERVED: Final[dict[str, ReservedService]] = {
    one.program: one
    for one in (
        ReservedService(
            EC2,
            "describe_reserved_instances",
            "ReservedInstances",
            "ReservedInstancesId",
            "InstanceType",
            "InstanceCount",
        ),
        ReservedService(
            RDS,
            "describe_reserved_db_instances",
            "ReservedDBInstances",
            "ReservedDBInstanceId",
            "DBInstanceClass",
            "DBInstanceCount",
        ),
        ReservedService(
            ELASTICACHE,
            "describe_reserved_cache_nodes",
            "ReservedCacheNodes",
            "ReservedCacheNodeId",
            "CacheNodeType",
            "CacheNodeCount",
        ),
        ReservedService(
            OPENSEARCH,
            "describe_reserved_instances",
            "ReservedInstances",
            "ReservedInstanceId",
            "InstanceType",
            "InstanceCount",
            "PaymentOption",
        ),
        ReservedService(
            REDSHIFT,
            "describe_reserved_nodes",
            "ReservedNodes",
            "ReservedNodeId",
            "NodeType",
            "NodeCount",
        ),
        ReservedService(
            MEMORYDB,
            "describe_reserved_nodes",
            "ReservedNodes",
            "ReservationId",
            "NodeType",
            "NodeCount",
        ),
    )
}


class AwsCommitmentHoldings:
    """`CommitmentHoldings` over Savings Plans and the reserved services, as each account's role."""

    def __init__(
        self,
        tenant_id: UUID,
        *,
        savings_plans_for: SavingsPlansFor,
        reservations_for: Mapping[str, ReservationsFor],
        clock: Clock = _system_clock,
    ) -> None:
        unknown = set(reservations_for) - set(RESERVED)
        if unknown:
            raise ValueError(f"no reader for the reserved services {sorted(unknown)}")
        self._tenant_id = tenant_id
        self._savings_plans_for = savings_plans_for
        self._reservations_for = dict(reservations_for)
        self._clock = clock

    def savings_plans(self, account: AccountKey) -> Iterable[HeldCommitment]:
        scope = f"{account}:savingsplans"
        client = self._savings_plans_for(account.account_id)
        at = self._clock()
        return tuple(
            self._read(scope, partial(self._plan, plan, account, at))
            for page in self._pages(client, "describe_savings_plans", scope)
            for plan in page.get("savingsPlans", [])
        )

    def reservations(self, account: AccountKey, region: str) -> Iterable[HeldCommitment]:
        at = self._clock()
        found: list[HeldCommitment] = []
        for program, client_for in sorted(self._reservations_for.items()):
            scope = f"{account}:{region}:{program}"
            service = RESERVED[program]
            client = client_for(account.account_id, region)
            for page in self._pages(client, service.method, scope):
                for held in page.get(service.key, []):
                    built = partial(
                        _reservation, service, self._tenant_id, held, account, region, at
                    )
                    found.append(self._read(scope, built))
        return tuple(found)

    def _pages(self, client: Any, method: str, scope: str) -> list[Any]:
        try:
            try:
                paginator = client.get_paginator(method)
            except OperationNotPageableError:
                return _follow(getattr(client, method), scope)
            return list(paginator.paginate())
        except (BotoCoreError, ClientError) as error:
            raise translate(error, scope_key=scope, collector=COLLECTOR) from error

    @staticmethod
    def _read(scope: str, build: Callable[[], HeldCommitment]) -> HeldCommitment:
        try:
            return build()
        except (KeyError, TypeError, ValueError, InvalidOperation) as error:
            raise SchemaDrift(
                scope_key=scope,
                collector=COLLECTOR,
                detail=f"a commitment arrived in a shape this adapter cannot read: {error}",
            ) from error

    def _plan(self, plan: Mapping[str, Any], account: AccountKey, at: datetime) -> HeldCommitment:
        return HeldCommitment(
            tenant_id=self._tenant_id,
            kind=SAVINGS_PLAN,
            commitment_id=str(plan["savingsPlanId"]),
            program=str(plan["savingsPlanType"]),
            account_id=account.account_id,
            region_id=str(plan.get("region") or "") or None,
            applies_to=str(plan.get("ec2InstanceFamily") or "") or None,
            quantity=None,
            hourly_commitment=_money(plan["commitment"]),
            term_months=term_months(int(plan["termDurationInSeconds"])),
            payment_option=str(plan["paymentOption"]),
            upfront_amount=_money(plan.get("upfrontPaymentAmount") or 0),
            recurring_hourly=_money(plan.get("recurringPaymentAmount") or 0),
            currency=str(plan["currency"]),
            starts_at=_instant(plan["start"]),
            ends_at=_instant(plan["end"]),
            state=str(plan["state"]),
            as_of=at,
            collected_at=at,
        )
