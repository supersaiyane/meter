"""AWS's purchase recommendations, read from Cost Explorer as the payer. TASK-P14-006, FEAT-089.

Every answer here goes through botocore's Stubber, which refuses a response that does not match
the service's own model, so the shapes this adapter reads are AWS's and not invented. What matters:
the question is asked in the tenant's policy's terms, an answer advising nothing is an answer and
not a failure, every page of a reservation answer is read, and a refusal is AccessDenied.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import boto3
import pytest
from botocore.stub import Stubber

from finops_core.domain.commitments import (
    ALL_UPFRONT,
    DEFAULT_POLICY,
    RESERVATION,
    SAVINGS_PLAN,
    CommitmentPolicy,
)
from finops_core.errors import AccessDenied, SchemaDrift
from finops_providers.aws import commitment_recommendations
from finops_providers.aws.commitment_recommendations import CostExplorerRecommendations

TENANT = uuid4()
AT = datetime(2026, 10, 13, 6, tzinfo=UTC)
GENERATED = "2026-10-13T01:00:00Z"
RDS_NAME = "Amazon Relational Database Service"
ASKED = {
    "TermInYears": "ONE_YEAR",
    "PaymentOption": "NO_UPFRONT",
    "LookbackPeriodInDays": "THIRTY_DAYS",
    "AccountScope": "PAYER",
}


def stubbed() -> tuple[CostExplorerRecommendations, Stubber]:
    client = boto3.client(
        "ce", region_name="us-east-1", aws_access_key_id="x", aws_secret_access_key="y"
    )
    stubber = Stubber(client)
    return CostExplorerRecommendations(TENANT, client_factory=lambda: client, clock=lambda: AT), (
        stubber
    )


def plan_answer(**summary: str) -> dict[str, Any]:
    return {
        "Metadata": {"RecommendationId": "rec-1", "GenerationTimestamp": GENERATED},
        "SavingsPlansPurchaseRecommendation": {
            "SavingsPlansPurchaseRecommendationDetails": [
                {"UpfrontCost": "0", "HourlyCommitmentToPurchase": "0.85"}
            ],
            "SavingsPlansPurchaseRecommendationSummary": {
                "HourlyCommitmentToPurchase": "0.85",
                "EstimatedMonthlySavingsAmount": "142.35",
                "EstimatedSavingsPercentage": "21.4",
                "CurrencyCode": "USD",
                **summary,
            },
        },
    }


def reservation_page(units: str, savings: str, token: str | None = None) -> dict[str, Any]:
    page: dict[str, Any] = {
        "Metadata": {"RecommendationId": "rec-2", "GenerationTimestamp": GENERATED},
        "Recommendations": [
            {
                "RecommendationDetails": [
                    {"RecommendedNumberOfInstancesToPurchase": units, "UpfrontCost": "0"}
                ],
                "RecommendationSummary": {
                    "TotalEstimatedMonthlySavingsAmount": savings,
                    "TotalEstimatedMonthlySavingsPercentage": "28.5",
                    "CurrencyCode": "USD",
                },
            }
        ],
    }
    if token:
        page["NextPageToken"] = token
    return page


def test_a_savings_plans_answer_is_read_in_the_policys_terms() -> None:
    adapter, stubber = stubbed()
    stubber.add_response(
        "get_savings_plans_purchase_recommendation",
        plan_answer(),
        {"SavingsPlansType": "COMPUTE_SP", **ASKED},
    )
    with stubber:
        found = adapter.savings_plans("Compute", DEFAULT_POLICY)
    assert (found.kind, found.program, found.recommended) == (SAVINGS_PLAN, "Compute", True)
    assert found.hourly_commitment == Decimal("0.85")
    assert found.units is None
    assert found.estimated_monthly_savings == Decimal("142.35")
    assert found.estimated_savings_percent == Decimal("21.4")
    assert (found.term_years, found.payment_option, found.lookback_days) == (1, "No Upfront", 30)
    assert found.as_of == datetime(2026, 10, 13, 1, tzinfo=UTC)
    assert found.collected_at == AT


def test_another_policy_asks_another_question() -> None:
    adapter, stubber = stubbed()
    policy = CommitmentPolicy(
        target_coverage=Decimal("0.8"),
        term_years=3,
        payment_option=ALL_UPFRONT,
        ladder_limit=Decimal("0.0833"),
    )
    stubber.add_response(
        "get_savings_plans_purchase_recommendation",
        plan_answer(),
        {
            "SavingsPlansType": "EC2_INSTANCE_SP",
            **ASKED,
            "TermInYears": "THREE_YEARS",
            "PaymentOption": "ALL_UPFRONT",
        },
    )
    with stubber:
        found = adapter.savings_plans("EC2Instance", policy)
    assert (found.term_years, found.payment_option) == (3, ALL_UPFRONT)


def test_an_answer_advising_nothing_is_an_answer() -> None:
    adapter, stubber = stubbed()
    stubber.add_response(
        "get_savings_plans_purchase_recommendation",
        {"Metadata": {"RecommendationId": "rec-0"}},
        {"SavingsPlansType": "COMPUTE_SP", **ASKED},
    )
    with stubber:
        found = adapter.savings_plans("Compute", DEFAULT_POLICY)
    assert found.recommended is False
    assert (found.hourly_commitment, found.estimated_monthly_savings) == (None, Decimal(0))
    assert found.currency == "USD"
    # No generation time given, so it was true when it was read.
    assert found.as_of == AT


def test_every_page_of_a_reservation_answer_is_read() -> None:
    adapter, stubber = stubbed()
    asked = {"Service": RDS_NAME, **ASKED}
    stubber.add_response(
        "get_reservation_purchase_recommendation",
        reservation_page("2", "60.00", token="next"),
        asked,
    )
    stubber.add_response(
        "get_reservation_purchase_recommendation",
        reservation_page("1", "28.60"),
        {**asked, "NextPageToken": "next"},
    )
    with stubber:
        found = adapter.reservations(RDS_NAME, DEFAULT_POLICY)
    stubber.assert_no_pending_responses()
    assert (found.kind, found.program, found.recommended) == (RESERVATION, RDS_NAME, True)
    assert found.units == Decimal(3)
    assert found.hourly_commitment is None
    assert found.estimated_monthly_savings == Decimal("88.60")
    assert found.estimated_savings_percent == Decimal("28.5")


def test_a_refusal_is_access_denied_and_never_advice_to_buy_nothing() -> None:
    adapter, stubber = stubbed()
    stubber.add_client_error(
        "get_reservation_purchase_recommendation",
        service_error_code="AccessDeniedException",
        http_status_code=400,
    )
    with stubber, pytest.raises(AccessDenied):
        adapter.reservations(RDS_NAME, DEFAULT_POLICY)


def test_a_figure_it_cannot_read_is_drift() -> None:
    adapter, stubber = stubbed()
    stubber.add_response(
        "get_savings_plans_purchase_recommendation",
        plan_answer(EstimatedSavingsPercentage="about a fifth"),
        {"SavingsPlansType": "COMPUTE_SP", **ASKED},
    )
    with stubber, pytest.raises(SchemaDrift, match="cannot read"):
        adapter.savings_plans("Compute", DEFAULT_POLICY)


def test_an_answer_that_never_stops_paging_is_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(commitment_recommendations, "MAX_PAGES", 2)
    adapter, stubber = stubbed()
    for _ in range(2):
        stubber.add_response(
            "get_reservation_purchase_recommendation", reservation_page("1", "1.00", token="more")
        )
    with stubber, pytest.raises(SchemaDrift, match="more than 2 pages"):
        adapter.reservations(RDS_NAME, DEFAULT_POLICY)
