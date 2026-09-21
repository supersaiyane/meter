"""The Cost Explorer adapter against recorded responses.

The contract suite asks whether this adapter answers like the fake. This file asks
the questions only the real response shape raises, and the sharpest of them is the
one the documentation makes easy to get wrong: Savings Plans report money and
reservations report hours, so half the figures here are measured and half are
derived. A test that treated them alike would pass while the reservation numbers
were nonsense.

Nothing here makes a call. ISS-122.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from botocore.exceptions import ClientError

from finops_core.config import Settings
from finops_core.domain.cost import ACTIVE, EXPIRED, QUEUED
from finops_core.errors import AccessDenied, NoData, SchemaDrift, Throttled
from finops_fakes import fixtures
from finops_providers.aws.commitment import CostExplorerCommitmentReport

WINDOW_START = date(2026, 8, 1)
WINDOW_END = date(2026, 9, 1)
NOW = datetime(2026, 9, 20, 6, 0, tzinfo=UTC)

EMPTY: dict[str, Any] = {}


class Explorer:
    """A Cost Explorer that answers with whatever it was handed.

    Records the keyword arguments of every call, because the window is the thing
    most easily sent wrong and a request nobody inspected is a request nobody
    tested.
    """

    def __init__(self, **responses: Any) -> None:
        self._responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _answer(self, name: str, kwargs: dict[str, Any]) -> Any:
        self.calls.append((name, kwargs))
        answer = self._responses.get(name, EMPTY)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def get_savings_plans_utilization_details(self, **kwargs: Any) -> Any:
        return self._answer("get_savings_plans_utilization_details", kwargs)

    def get_savings_plans_coverage(self, **kwargs: Any) -> Any:
        return self._answer("get_savings_plans_coverage", kwargs)

    def get_reservation_utilization(self, **kwargs: Any) -> Any:
        return self._answer("get_reservation_utilization", kwargs)

    def get_reservation_coverage(self, **kwargs: Any) -> Any:
        return self._answer("get_reservation_coverage", kwargs)


def report(settings: Settings, explorer: Explorer) -> CostExplorerCommitmentReport:
    return CostExplorerCommitmentReport(
        settings,
        tenant_id=fixtures.TENANT_ID,
        client_factory=lambda: explorer,
        clock=lambda: NOW,
    )


def savings_plan(
    *,
    arn: str = "arn:aws:savingsplans::111122223333:savingsplan/one",
    committed: str = "1000.00",
    used: str = "800.00",
    unused: str = "200.00",
    start: str = "2026-01-01T00:00:00Z",
    end: str = "2027-01-01T00:00:00Z",
) -> dict[str, Any]:
    return {
        "SavingsPlansUtilizationDetails": [
            {
                "SavingsPlanArn": arn,
                "Attributes": {"startDateTime": start, "endDateTime": end},
                "Utilization": {
                    "TotalCommitment": committed,
                    "UsedCommitment": used,
                    "UnusedCommitment": unused,
                },
            }
        ]
    }


def reservation(
    *, purchased: str = "744", actual: str = "372", fee: str = "1000.00"
) -> dict[str, Any]:
    return {
        "UtilizationsByTime": [
            {
                "Groups": [
                    {
                        "Key": "ri-one",
                        "Utilization": {
                            "PurchasedHours": purchased,
                            "TotalActualHours": actual,
                            "TotalAmortizedFee": fee,
                        },
                    }
                ]
            }
        ]
    }


class TestSavingsPlansAreMeasured:
    def test_committed_and_used_come_straight_from_the_response(self, settings: Settings) -> None:
        found = tuple(
            report(
                settings, Explorer(get_savings_plans_utilization_details=savings_plan())
            ).utilization(WINDOW_START, WINDOW_END)
        )
        assert found[0].committed == Decimal("1000.00")
        assert found[0].used == Decimal("800.00")

    def test_waste_is_the_subtraction_and_not_the_providers_third_number(
        self, settings: Settings
    ) -> None:
        """`UnusedCommitment` is in the response and is deliberately ignored.

        The database constrains `wasted` to equal `committed - used`. Taking a third
        number from the provider is how a row that violates that constraint gets
        built, so the response is given a disagreeing `UnusedCommitment` and the
        adapter must still subtract.
        """
        response = savings_plan(committed="1000.00", used="800.00", unused="999.99")
        found = tuple(
            report(settings, Explorer(get_savings_plans_utilization_details=response)).utilization(
                WINDOW_START, WINDOW_END
            )
        )
        assert found[0].wasted == Decimal("200.00")

    def test_a_plan_that_ended_inside_the_window_is_expired(self, settings: Settings) -> None:
        response = savings_plan(end="2026-08-15T00:00:00Z")
        found = tuple(
            report(settings, Explorer(get_savings_plans_utilization_details=response)).utilization(
                WINDOW_START, WINDOW_END
            )
        )
        assert found[0].status == EXPIRED

    def test_a_plan_that_starts_after_the_window_is_queued(self, settings: Settings) -> None:
        response = savings_plan(
            start="2026-09-01T00:00:00Z",
            end="2027-09-01T00:00:00Z",
            committed="0",
            used="0",
            unused="0",
        )
        found = tuple(
            report(settings, Explorer(get_savings_plans_utilization_details=response)).utilization(
                WINDOW_START, WINDOW_END
            )
        )
        assert found[0].status == QUEUED
        assert found[0].utilization is None

    def test_a_plan_inside_the_window_is_active(self, settings: Settings) -> None:
        found = tuple(
            report(
                settings, Explorer(get_savings_plans_utilization_details=savings_plan())
            ).utilization(WINDOW_START, WINDOW_END)
        )
        assert found[0].status == ACTIVE

    def test_a_missing_amount_is_refused_rather_than_read_as_zero(self, settings: Settings) -> None:
        response = savings_plan()
        del response["SavingsPlansUtilizationDetails"][0]["Utilization"]["TotalCommitment"]
        with pytest.raises(SchemaDrift):
            tuple(
                report(
                    settings, Explorer(get_savings_plans_utilization_details=response)
                ).utilization(WINDOW_START, WINDOW_END)
            )

    def test_an_unparseable_amount_is_refused(self, settings: Settings) -> None:
        response = savings_plan(committed="not money")
        with pytest.raises(SchemaDrift):
            tuple(
                report(
                    settings, Explorer(get_savings_plans_utilization_details=response)
                ).utilization(WINDOW_START, WINDOW_END)
            )

    def test_a_term_with_no_dates_falls_back_to_the_window_rather_than_refusing(
        self, settings: Settings
    ) -> None:
        # The attributes map is documented as free form and its keys have changed. A
        # commitment that is otherwise complete should not be dropped over it.
        response = savings_plan()
        response["SavingsPlansUtilizationDetails"][0]["Attributes"] = {}
        found = tuple(
            report(settings, Explorer(get_savings_plans_utilization_details=response)).utilization(
                WINDOW_START, WINDOW_END
            )
        )
        assert found[0].term_start == WINDOW_START

    def test_a_nonsense_date_falls_back_too(self, settings: Settings) -> None:
        response = savings_plan(start="the third of never")
        found = tuple(
            report(settings, Explorer(get_savings_plans_utilization_details=response)).utilization(
                WINDOW_START, WINDOW_END
            )
        )
        assert found[0].term_start == WINDOW_START


class TestReservationsAreDerived:
    def test_the_money_is_the_fee_scaled_by_the_hours_actually_used(
        self, settings: Settings
    ) -> None:
        """The figure Cost Explorer does not give.

        Half of 744 purchased hours used, against a thousand dollar amortized fee,
        is five hundred dollars consumed. If this ever reads as the fee itself, or
        as the hours, the screen will show a reservation as fully used when it is
        half wasted.
        """
        found = tuple(
            report(
                settings,
                Explorer(get_reservation_utilization=reservation(purchased="744", actual="372")),
            ).utilization(WINDOW_START, WINDOW_END)
        )
        assert found[0].committed == Decimal("1000.00")
        assert found[0].used == Decimal("500.00")
        assert found[0].wasted == Decimal("500.00")

    def test_no_purchased_hours_is_queued_rather_than_wholly_wasted(
        self, settings: Settings
    ) -> None:
        found = tuple(
            report(
                settings,
                Explorer(
                    get_reservation_utilization=reservation(purchased="0", actual="0", fee="0")
                ),
            ).utilization(WINDOW_START, WINDOW_END)
        )
        assert found[0].status == QUEUED
        assert found[0].used == Decimal("0")

    def test_a_missing_hour_count_is_refused_rather_than_read_as_zero(
        self, settings: Settings
    ) -> None:
        response = reservation()
        del response["UtilizationsByTime"][0]["Groups"][0]["Utilization"]["PurchasedHours"]
        with pytest.raises(SchemaDrift):
            tuple(
                report(settings, Explorer(get_reservation_utilization=response)).utilization(
                    WINDOW_START, WINDOW_END
                )
            )


class TestCoverage:
    def test_the_denominator_is_the_total_and_never_the_uncovered_part(
        self, settings: Settings
    ) -> None:
        """`OnDemandCost` is what was missed. `TotalCost` is what was eligible.

        Using the first would report coverage as a fraction of the failure, which
        rises as coverage falls.
        """
        response = {
            "SavingsPlansCoverages": [
                {
                    "Attributes": {"SERVICE": "AmazonEC2"},
                    "Coverage": {
                        "SpendCoveredBySavingsPlans": "250.00",
                        "OnDemandCost": "750.00",
                        "TotalCost": "1000.00",
                    },
                }
            ]
        }
        found = tuple(
            report(settings, Explorer(get_savings_plans_coverage=response)).coverage(
                WINDOW_START, WINDOW_END
            )
        )
        assert found[0].eligible_spend == Decimal("1000.00")
        assert found[0].coverage == Decimal("0.25")

    def test_a_reservation_without_a_reserved_cost_still_reports_its_uncovered_side(
        self, settings: Settings
    ) -> None:
        # The weakest mapping in the adapter. A payer that returns only
        # `OnDemandCost` should still produce a row, because a coverage figure of
        # zero against real eligible spend is exactly the row a reader acts on.
        response = {
            "CoveragesByTime": [
                {
                    "Groups": [
                        {
                            "Attributes": {"SERVICE": "AmazonRDS"},
                            "Coverage": {"CoverageCost": {"OnDemandCost": "400.00"}},
                        }
                    ]
                }
            ]
        }
        found = tuple(
            report(settings, Explorer(get_reservation_coverage=response)).coverage(
                WINDOW_START, WINDOW_END
            )
        )
        assert found[0].eligible_spend == Decimal("400.00")
        assert found[0].covered_spend == Decimal("0")
        assert found[0].coverage == Decimal("0")

    def test_the_window_is_grouped_by_service(self, settings: Settings) -> None:
        explorer = Explorer()
        with pytest.raises(NoData):
            tuple(report(settings, explorer).coverage(WINDOW_START, WINDOW_END))
        grouped = [kwargs.get("GroupBy") for _, kwargs in explorer.calls]
        assert all(group == [{"Type": "DIMENSION", "Key": "SERVICE"}] for group in grouped)


class TestTheRequestAndTheFailures:
    def test_the_window_is_sent_with_an_exclusive_end_unchanged(self, settings: Settings) -> None:
        # Cost Explorer's End is exclusive, which matches every period in this
        # schema. An adapter that adjusted it would silently read a day short.
        explorer = Explorer(get_savings_plans_utilization_details=savings_plan())
        tuple(report(settings, explorer).utilization(WINDOW_START, WINDOW_END))
        sent = explorer.calls[0][1]["TimePeriod"]
        assert sent == {"Start": "2026-08-01", "End": "2026-09-01"}

    def test_nothing_at_all_is_a_typed_no_data_and_not_an_empty_list(
        self, settings: Settings
    ) -> None:
        with pytest.raises(NoData):
            tuple(report(settings, Explorer()).utilization(WINDOW_START, WINDOW_END))

    @pytest.mark.parametrize(
        ("code", "expected"),
        [("AccessDeniedException", AccessDenied), ("ThrottlingException", Throttled)],
    )
    def test_a_provider_refusal_becomes_the_typed_cause(
        self, settings: Settings, code: str, expected: type[Exception]
    ) -> None:
        error = ClientError({"Error": {"Code": code, "Message": "no"}}, "GetSavingsPlans")
        with pytest.raises(expected):
            tuple(
                report(settings, Explorer(get_savings_plans_utilization_details=error)).utilization(
                    WINDOW_START, WINDOW_END
                )
            )


class TestFreshness:
    def test_as_of_is_the_end_of_the_window_and_collected_at_is_now(
        self, settings: Settings
    ) -> None:
        # Constraint 10. The figures were true across the window; the end of it is
        # the latest moment they describe, and the call happened later.
        found = tuple(
            report(
                settings, Explorer(get_savings_plans_utilization_details=savings_plan())
            ).utilization(WINDOW_START, WINDOW_END)
        )
        assert found[0].as_of == datetime(2026, 9, 1, tzinfo=UTC)
        assert found[0].collected_at == NOW
