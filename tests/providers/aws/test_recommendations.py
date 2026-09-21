"""The three AWS services, against recorded responses.

The contract suite asks whether this adapter answers like the fake. This file asks
what only the real response shapes raise, and the sharpest of those is that all
three services report money and none of them agrees on where to put it.

Nothing here makes a call. ISS-122.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from botocore.exceptions import ClientError

from finops_core.config import Settings
from finops_core.domain.observation import MINIMUM_HISTORY
from finops_core.domain.waste import Source, WasteClass
from finops_core.errors import AccessDenied, NotOptedIn, SchemaDrift
from finops_providers.aws.recommendations import CostRecommendationSource
from finops_providers.fake import fixtures

NOW = datetime(2026, 9, 21, 6, 0, tzinfo=UTC)
EMPTY: dict[str, Any] = {}


class Services:
    """Three AWS clients in one stub, answering with whatever they were handed."""

    def __init__(self, **responses: Any) -> None:
        self._responses = responses
        self.calls: list[str] = []

    def __call__(self, service: str) -> Any:
        return _Client(service, self._responses, self.calls)


class _Client:
    def __init__(self, service: str, responses: dict[str, Any], calls: list[str]) -> None:
        self._service = service
        self._responses = responses
        self._calls = calls

    def _answer(self, name: str) -> Any:
        self._calls.append(name)
        answer = self._responses.get(name, EMPTY)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def get_ec2_instance_recommendations(self, **_: Any) -> Any:
        return self._answer("get_ec2_instance_recommendations")

    def list_recommendations(self, **_: Any) -> Any:
        return self._answer("list_recommendations")

    def describe_trusted_advisor_check_result(self, **_: Any) -> Any:
        return self._answer("describe_trusted_advisor_check_result")


def source(settings: Settings, services: Services) -> CostRecommendationSource:
    return CostRecommendationSource(
        settings,
        tenant_id=fixtures.TENANT_ID,
        # Fixed rather than read from settings, so a test asserting severity is
        # asserting the adapter passes the money through and not what the bands are.
        severity_of=lambda amount: "HIGH" if amount >= Decimal("100") else "LOW",
        client_factory=services,
        clock=lambda: NOW,
    )


def optimizer(*, finding: str = "Overprovisioned", saving: Any = "240.00") -> dict[str, Any]:
    return {
        "instanceRecommendations": [
            {
                "instanceArn": "arn:aws:ec2:eu-west-1:111122223333:instance/i-0001",
                "finding": finding,
                "lookBackPeriodInDays": 30,
                "recommendationOptions": [
                    {
                        "instanceType": "m6i.large",
                        "savingsOpportunity": {"estimatedMonthlySavings": {"value": saving}},
                    }
                ],
            }
        ]
    }


class TestComputeOptimizer:
    def test_a_recommendation_carries_its_money_and_its_working(self, settings: Settings) -> None:
        found = tuple(
            source(
                settings, Services(get_ec2_instance_recommendations=optimizer())
            ).compute_optimizer()
        )
        assert found[0].estimated_monthly_saving == Decimal("240.00")
        assert found[0].source == Source.COMPUTE_OPTIMIZER
        assert "m6i.large" in found[0].rationale

    def test_the_account_and_region_come_out_of_the_arn(self, settings: Settings) -> None:
        found = tuple(
            source(
                settings, Services(get_ec2_instance_recommendations=optimizer())
            ).compute_optimizer()
        )
        assert found[0].sub_account_id == "111122223333"
        assert found[0].region_id == "eu-west-1"

    def test_an_unrecognised_finding_is_skipped_rather_than_guessed(
        self, settings: Settings
    ) -> None:
        """A finding mapped to the wrong class is worse than one absent.

        The absent one is countable. The wrong one is believed.
        """
        response = optimizer(finding="SomethingAWSAddedLastTuesday")
        found = tuple(
            source(
                settings, Services(get_ec2_instance_recommendations=response)
            ).compute_optimizer()
        )
        assert found == ()

    def test_idle_and_overprovisioned_are_different_classes(self, settings: Settings) -> None:
        over = tuple(
            source(
                settings, Services(get_ec2_instance_recommendations=optimizer())
            ).compute_optimizer()
        )
        idle = tuple(
            source(
                settings,
                Services(get_ec2_instance_recommendations=optimizer(finding="Idle")),
            ).compute_optimizer()
        )
        assert over[0].waste_class == WasteClass.RIGHTSIZE_INSTANCE
        assert idle[0].waste_class == WasteClass.IDLE_INSTANCE

    def test_a_missing_saving_is_refused_rather_than_read_as_zero(self, settings: Settings) -> None:
        # A recommendation saving nothing is one nobody acts on, and it looks
        # exactly like one that genuinely saves nothing.
        response = optimizer()
        del response["instanceRecommendations"][0]["recommendationOptions"][0]["savingsOpportunity"]
        with pytest.raises(SchemaDrift):
            tuple(
                source(
                    settings, Services(get_ec2_instance_recommendations=response)
                ).compute_optimizer()
            )

    def test_an_unparseable_saving_is_refused(self, settings: Settings) -> None:
        with pytest.raises(SchemaDrift):
            tuple(
                source(
                    settings,
                    Services(get_ec2_instance_recommendations=optimizer(saving="not money")),
                ).compute_optimizer()
            )


class TestNotOptedInIsNotAFault:
    @pytest.mark.parametrize(
        "code",
        ["OptInRequiredException", "ResourceNotFoundException", "SubscriptionRequiredException"],
    )
    def test_an_unenabled_service_raises_not_opted_in(self, settings: Settings, code: str) -> None:
        """The distinction the screen depends on.

        An estate that never enabled Compute Optimizer is correctly configured and
        has fewer signals. Reporting that as no waste found is the comfortable lie.
        """
        error = ClientError({"Error": {"Code": code, "Message": "no"}}, "GetRecommendations")
        with pytest.raises(NotOptedIn):
            tuple(
                source(
                    settings, Services(get_ec2_instance_recommendations=error)
                ).compute_optimizer()
            )

    def test_a_throttle_is_still_a_throttle(self, settings: Settings) -> None:
        # Only the opt in codes become NotOptedIn. Widening that would make every
        # transient failure look like a configuration choice.
        from finops_core.errors import Throttled

        error = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "slow down"}}, "Get"
        )
        with pytest.raises(Throttled):
            tuple(
                source(
                    settings, Services(get_ec2_instance_recommendations=error)
                ).compute_optimizer()
            )

    def test_an_access_failure_reads_as_not_opted_in_here_and_that_is_deliberate(
        self, settings: Settings
    ) -> None:
        """AccessDenied on these three services is ambiguous.

        It means either the role lacks the permission or the organization never
        enabled the service, and AWS does not distinguish them. Treating it as
        NotOptedIn tells the reader to check whether it is switched on, which is
        the more common cause and the cheaper thing to check first. The message
        carries the code so the other cause is still findable.
        """
        error = ClientError({"Error": {"Code": "AccessDeniedException", "Message": "no"}}, "Get")
        with pytest.raises(NotOptedIn, match="AccessDeniedException"):
            tuple(
                source(
                    settings, Services(get_ec2_instance_recommendations=error)
                ).compute_optimizer()
            )
        assert AccessDenied is not NotOptedIn


class TestCostOptimizationHub:
    def test_it_reads_the_money_and_the_action(self, settings: Settings) -> None:
        response = {
            "items": [
                {
                    "recommendationId": "hub-0001",
                    "actionType": "MigrateToGraviton",
                    "estimatedMonthlySavings": "88.40",
                    "resourceId": "i-0002",
                    "region": "eu-west-2",
                    "currentResourceType": "Ec2Instance",
                    "lookbackPeriodInDays": 60,
                }
            ]
        }
        found = tuple(
            source(settings, Services(list_recommendations=response)).cost_optimization_hub()
        )
        assert found[0].estimated_monthly_saving == Decimal("88.40")
        assert found[0].waste_class == WasteClass.GRAVITON_CANDIDATE
        assert found[0].observation_days == 60


class TestTrustedAdvisor:
    def test_the_money_is_found_in_a_positional_array(self, settings: Settings) -> None:
        """The weakest mapping in the adapter, and the test says so.

        Trusted Advisor returns metadata whose meaning differs per check. The money
        is conventionally last, and anything unparseable is refused rather than
        guessed at.
        """
        response = {
            "result": {
                "flaggedResources": [
                    {
                        "resourceId": "eipalloc-0001",
                        "region": "eu-west-1",
                        "metadata": ["eu-west-1", "eipalloc-0001", "$3.60"],
                    }
                ]
            }
        }
        found = tuple(
            source(
                settings, Services(describe_trusted_advisor_check_result=response)
            ).trusted_advisor()
        )
        assert found[0].estimated_monthly_saving == Decimal("3.60")
        assert found[0].observation_days == MINIMUM_HISTORY

    def test_metadata_with_no_number_is_refused(self, settings: Settings) -> None:
        response = {
            "result": {
                "flaggedResources": [
                    {"resourceId": "x", "region": "eu-west-1", "metadata": ["a", "b"]}
                ]
            }
        }
        with pytest.raises(SchemaDrift):
            tuple(
                source(
                    settings, Services(describe_trusted_advisor_check_result=response)
                ).trusted_advisor()
            )


class TestItSaysItHasNeverRun:
    def test_every_unproved_adapter_says_so_in_the_same_words(self) -> None:
        """Asserted across all three rather than only this one.

        The phrase is the convention `aws/cur.py` established, and a test naming
        one file would let the next adapter use different words and still look
        compliant. A green test suite must not read as a working integration.
        """
        from pathlib import Path

        for name in ("cur.py", "commitment.py", "recommendations.py"):
            head = Path(f"finops_providers/aws/{name}").read_text(encoding="utf-8")[:900]
            assert "has ever made a call" in head, name
            assert "ISS-122" in head, name
