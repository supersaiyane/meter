"""AWS's own purchase recommendations, read as the payer. FEAT-089, TASK-P14-006, OPEN-35.

P14 spec section 5.1. Cost Explorer's `GetSavingsPlansPurchaseRecommendation` and
`GetReservationPurchaseRecommendation`, each asked in the tenant's policy's term and payment option
over the last thirty days, for the whole organization, so AWS's answer and Meter's own plan are
about the same purchase. Each request costs USD 0.01 at AWS's published price, modelled; the
collector's schedule row carries the cost.

**AWS's estimate, labelled as AWS's.** The savings here are AWS's model of AWS's prices, and the
screen says so beside Meter's own. A recommendation to buy nothing is an answer, kept as one.

**Every page of a reservation recommendation.** Cost Explorer pages it by `NextPageToken`, and a
recommendation read as its first page alone would understate what AWS advises.

Unproved against a real payer, ISS-002; the service names it is asked about are unverified but for
Amazon Redshift until first contact, ISS-297.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Final
from uuid import UUID

from botocore.exceptions import BotoCoreError, ClientError

from finops_core.domain.commitments import (
    RESERVATION,
    SAVINGS_PLAN,
    CommitmentPolicy,
    PurchaseRecommendation,
)
from finops_core.errors import SchemaDrift
from finops_providers.aws.client import translate
from finops_providers.aws.commitment_inventory import UNSTATED_CURRENCY

COLLECTOR: Final = "purchase_recommendation"
SCOPE: Final = "billing:recommendations"

#: The lookback both calls are asked about, in Cost Explorer's spelling and in days.
LOOKBACK: Final = "THIRTY_DAYS"
LOOKBACK_DAYS: Final = 30
#: The whole organization, the management account and every member.
ACCOUNT_SCOPE: Final = "PAYER"

#: Each Savings Plans type as Meter names it, and as Cost Explorer asks for it.
SAVINGS_PLANS_TYPES: Final = {"Compute": "COMPUTE_SP", "EC2Instance": "EC2_INSTANCE_SP"}
TERMS: Final = {1: "ONE_YEAR", 3: "THREE_YEARS"}
PAYMENTS: Final = {
    "No Upfront": "NO_UPFRONT",
    "Partial Upfront": "PARTIAL_UPFRONT",
    "All Upfront": "ALL_UPFRONT",
}

#: The most pages of one recommendation followed, so a token that never ends is a failure.
MAX_PAGES: Final = 50

Clock = Callable[[], datetime]


def _system_clock() -> datetime:
    return datetime.now(UTC)


def _amount(value: Any) -> Decimal:
    return Decimal(str(value)) if value not in (None, "") else Decimal(0)


def _generated(answer: Mapping[str, Any], at: datetime) -> datetime:
    """When AWS generated the recommendation, which is when it was true; now where it says none."""
    stamp = (answer.get("Metadata") or {}).get("GenerationTimestamp")
    if not stamp:
        return at
    found = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    return min(found if found.tzinfo else found.replace(tzinfo=UTC), at)


class CostExplorerRecommendations:
    """`PurchaseRecommendations` over Cost Explorer, as the payer."""

    def __init__(
        self, tenant_id: UUID, *, client_factory: Callable[[], Any], clock: Clock = _system_clock
    ) -> None:
        self._tenant_id = tenant_id
        self._factory = client_factory
        self._clock = clock

    def _call(self, name: str, **kwargs: Any) -> Any:
        try:
            return getattr(self._factory(), name)(**kwargs)
        except (BotoCoreError, ClientError) as error:
            raise translate(error, scope_key=SCOPE, collector=COLLECTOR) from error

    def _asked(self, policy: CommitmentPolicy) -> dict[str, str]:
        return {
            "TermInYears": TERMS[policy.term_years],
            "PaymentOption": PAYMENTS[policy.payment_option],
            "LookbackPeriodInDays": LOOKBACK,
            "AccountScope": ACCOUNT_SCOPE,
        }

    def savings_plans(self, program: str, policy: CommitmentPolicy) -> PurchaseRecommendation:
        at = self._clock()
        answer = self._call(
            "get_savings_plans_purchase_recommendation",
            SavingsPlansType=SAVINGS_PLANS_TYPES[program],
            **self._asked(policy),
        )
        summary = (answer.get("SavingsPlansPurchaseRecommendation") or {}).get(
            "SavingsPlansPurchaseRecommendationSummary"
        )
        return self._read(
            lambda: self._recommendation(
                kind=SAVINGS_PLAN,
                program=program,
                policy=policy,
                generated=_generated(answer, at),
                at=at,
                summary=summary or {},
                hourly=_amount((summary or {}).get("HourlyCommitmentToPurchase")),
                units=None,
                savings=_amount((summary or {}).get("EstimatedMonthlySavingsAmount")),
                percent=(summary or {}).get("EstimatedSavingsPercentage"),
                upfront=sum(
                    (
                        _amount(one.get("UpfrontCost"))
                        for one in (answer.get("SavingsPlansPurchaseRecommendation") or {}).get(
                            "SavingsPlansPurchaseRecommendationDetails", []
                        )
                    ),
                    Decimal(0),
                ),
            )
        )

    def reservations(self, service: str, policy: CommitmentPolicy) -> PurchaseRecommendation:
        at = self._clock()
        pages = self._pages(service, policy)
        recommendations = [one for page in pages for one in page.get("Recommendations", [])]
        details = [one for rec in recommendations for one in rec.get("RecommendationDetails", [])]
        summaries = [rec.get("RecommendationSummary") or {} for rec in recommendations]
        currency = next(
            (one.get("CurrencyCode") for one in summaries if one.get("CurrencyCode")), None
        )
        return self._read(
            lambda: self._recommendation(
                kind=RESERVATION,
                program=service,
                policy=policy,
                generated=_generated(pages[0] if pages else {}, at),
                at=at,
                summary={"CurrencyCode": currency} if currency else {},
                hourly=None,
                units=sum(
                    (_amount(one.get("RecommendedNumberOfInstancesToPurchase")) for one in details),
                    Decimal(0),
                ),
                savings=sum(
                    (_amount(one.get("TotalEstimatedMonthlySavingsAmount")) for one in summaries),
                    Decimal(0),
                ),
                percent=next(
                    (
                        one.get("TotalEstimatedMonthlySavingsPercentage")
                        for one in summaries
                        if one.get("TotalEstimatedMonthlySavingsPercentage")
                    ),
                    None,
                ),
                upfront=sum((_amount(one.get("UpfrontCost")) for one in details), Decimal(0)),
            )
        )

    def _pages(self, service: str, policy: CommitmentPolicy) -> list[Any]:
        pages: list[Any] = []
        token: dict[str, str] = {}
        while len(pages) < MAX_PAGES:
            page = self._call(
                "get_reservation_purchase_recommendation",
                Service=service,
                **self._asked(policy),
                **token,
            )
            pages.append(page)
            if not page.get("NextPageToken"):
                return pages
            token = {"NextPageToken": page["NextPageToken"]}
        raise SchemaDrift(
            scope_key=SCOPE,
            collector=COLLECTOR,
            detail=f"more than {MAX_PAGES} pages of one recommendation; none is kept",
        )

    @staticmethod
    def _read(build: Callable[[], PurchaseRecommendation]) -> PurchaseRecommendation:
        try:
            return build()
        except (KeyError, TypeError, ValueError, InvalidOperation) as error:
            raise SchemaDrift(
                scope_key=SCOPE,
                collector=COLLECTOR,
                detail=f"a recommendation arrived in a shape this adapter cannot read: {error}",
            ) from error

    def _recommendation(
        self,
        *,
        kind: str,
        program: str,
        policy: CommitmentPolicy,
        generated: datetime,
        at: datetime,
        summary: Mapping[str, Any],
        hourly: Decimal | None,
        units: Decimal | None,
        savings: Decimal,
        percent: Any,
        upfront: Decimal,
    ) -> PurchaseRecommendation:
        buys = (hourly or Decimal(0)) > 0 or (units or Decimal(0)) > 0
        return PurchaseRecommendation(
            tenant_id=self._tenant_id,
            kind=kind,
            program=program,
            term_years=policy.term_years,
            payment_option=policy.payment_option,
            lookback_days=LOOKBACK_DAYS,
            recommended=buys,
            hourly_commitment=hourly if buys else None,
            units=units if buys else None,
            estimated_monthly_savings=savings,
            estimated_savings_percent=None if percent in (None, "") else Decimal(str(percent)),
            upfront_cost=upfront,
            currency=str(summary.get("CurrencyCode") or UNSTATED_CURRENCY),
            as_of=generated,
            collected_at=at,
        )
