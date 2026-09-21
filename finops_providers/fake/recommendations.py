"""AWS's own findings, in memory, for an estate that is not all waste.

Sized from `cur.ESTATE` rather than written down, for the reason the commitment
fake is: a saving larger than the resource's own bill is a number a reader spots
immediately and cannot explain, and hand written figures drift the first time a
service or an account weight changes.

**The estate deliberately contains findings that are wrong to act on**, because a
fake where every recommendation is good proves nothing about a product whose job
is to be trusted. Two of them:

`fake-ta-eip` saves three dollars a month, which is under the floor and should
never reach a screen. It is here so the floor is exercised rather than assumed.

`fake-co-burstable` is a t class instance at twenty percent, which Compute
Optimizer does flag and which our own collector correctly refuses. Both appear,
because the product's answer to "AWS says this and we disagree" has to be visible
somewhere.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import TypedDict
from uuid import UUID

from finops_core.domain.waste import Lifecycle, Recommendation, Source, WasteClass
from finops_core.errors import CollectionError, NotOptedIn
from finops_providers.fake import cur, fixtures

COLLECTOR = "recommendations"

CENTS = Decimal("0.01")


class _Common(TypedDict):
    as_of: datetime
    collected_at: datetime
    tenant_id: UUID


def _service_cost(service: str, at: datetime) -> Decimal:
    """What the estate billed for one service in its newest period.

    The same rows the cost screens read, so a saving here is a fraction of a number
    a reader can find on another screen.
    """
    rows = cur.estate(at=at)
    period = max(row.billing_period_start for row in rows)
    return sum(
        (
            row.effective_cost
            for row in rows
            if row.billing_period_start == period and row.service_name == service
        ),
        Decimal("0"),
    )


def _money(amount: Decimal) -> Decimal:
    return amount.quantize(CENTS, rounding=ROUND_HALF_UP)


def findings(
    at: datetime = fixtures.AS_OF, *, severity_of: Callable[[Decimal], str] | None = None
) -> tuple[Recommendation, ...]:
    """Every finding the three fake services report, before any floor is applied."""
    grade = severity_of or (lambda amount: "HIGH" if amount >= Decimal("100") else "LOW")
    common: _Common = {"as_of": at, "collected_at": at, "tenant_id": fixtures.TENANT_ID}
    ec2 = _service_cost("AmazonEC2", at)
    rds = _service_cost("AmazonRDS", at)

    def build(
        *,
        source: Source,
        reference: str,
        waste_class: WasteClass,
        resource: str,
        saving: Decimal,
        days: int,
        rationale: str,
        account: str = "fake-platform-a",
    ) -> Recommendation:
        return Recommendation(
            **common,
            sub_account_id=account,
            source=source,
            source_reference=reference,
            waste_class=waste_class,
            resource_id=resource,
            region_id=fixtures.REGION,
            estimated_monthly_saving=saving,
            severity=grade(saving),
            observation_days=days,
            lifecycle=Lifecycle.OPEN,
            owner=None,
            ticket_reference=None,
            rationale=rationale,
        )

    return (
        build(
            source=Source.COMPUTE_OPTIMIZER,
            reference="arn:aws:ec2:eu-west-1:fake-platform-a:instance/i-oversized",
            waste_class=WasteClass.RIGHTSIZE_INSTANCE,
            resource="i-oversized",
            # A fifth of the estate's EC2 bill, which is a plausible rightsizing
            # and is large enough to clear any sane severity band.
            saving=_money(ec2 * Decimal("0.20")),
            days=45,
            rationale="Compute Optimizer finding Overprovisioned, recommending m6i.large",
        ),
        build(
            source=Source.COMPUTE_OPTIMIZER,
            reference="arn:aws:ec2:eu-west-1:fake-platform-b:instance/i-burstable",
            waste_class=WasteClass.RIGHTSIZE_INSTANCE,
            resource="i-burstable",
            saving=_money(ec2 * Decimal("0.04")),
            days=30,
            account="fake-platform-b",
            # The disagreement, on purpose. Our own collector refuses this one
            # because the credit balance is healthy, and both answers being
            # visible is the point.
            rationale="Compute Optimizer finding Overprovisioned on a t class instance",
        ),
        build(
            source=Source.COST_OPTIMIZATION_HUB,
            reference="hub-graviton-0001",
            waste_class=WasteClass.GRAVITON_CANDIDATE,
            resource="db-fake-0001",
            saving=_money(rds * Decimal("0.12")),
            days=90,
            rationale="Cost Optimization Hub MigrateToGraviton on DbInstance",
        ),
        build(
            source=Source.TRUSTED_ADVISOR,
            reference="Z4AUBRNSmz:eipalloc-fake",
            waste_class=WasteClass.ELASTIC_IP_UNASSOCIATED,
            resource="eipalloc-fake",
            # Under the floor on purpose. A real estate is full of these and a
            # screen that shows them is a screen nobody reads.
            saving=Decimal("3.60"),
            days=14,
            rationale="Trusted Advisor check Z4AUBRNSmz flagged this resource",
        ),
    )


class FakeRecommendationSource:
    """`RecommendationSource` in memory. Every failure is asked for."""

    def __init__(
        self,
        failure: type[CollectionError] | None = None,
        *,
        not_opted_in: frozenset[Source] = frozenset(),
        at: datetime = fixtures.AS_OF,
        severity_of: Callable[[Decimal], str] | None = None,
    ) -> None:
        self._failure = failure
        self._not_opted_in = not_opted_in
        self._at = at
        self._severity_of = severity_of

    def _for(self, source: Source) -> Iterable[Recommendation]:
        if self._failure is not None:
            raise self._failure(
                scope_key=fixtures.ORGANIZATION_SCOPE,
                collector=COLLECTOR,
                detail="planned by the fake recommendation source",
            )
        if source in self._not_opted_in:
            raise NotOptedIn(
                scope_key=fixtures.ORGANIZATION_SCOPE,
                collector=COLLECTOR,
                detail=f"{source.value} has never been enabled for this organization",
            )
        return tuple(
            item
            for item in findings(self._at, severity_of=self._severity_of)
            if item.source is source
        )

    def compute_optimizer(self) -> Iterable[Recommendation]:
        return self._for(Source.COMPUTE_OPTIMIZER)

    def cost_optimization_hub(self) -> Iterable[Recommendation]:
        return self._for(Source.COST_OPTIMIZATION_HUB)

    def trusted_advisor(self) -> Iterable[Recommendation]:
        return self._for(Source.TRUSTED_ADVISOR)
