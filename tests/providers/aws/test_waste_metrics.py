"""The batched metric read, against a recorded CloudWatch.

One decision is worth a whole test class: `GetMetricData` is charged per metric
requested, so how many calls this makes for a given number of series is a cost
question rather than a performance one. The batching assertion counts calls.

Nothing here makes a call. ISS-122.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from finops_core.config import Settings
from finops_core.domain.account import AccountKey, Provider
from finops_core.ports.metrics import MetricRequest
from finops_providers.aws.waste import PERIOD_SECONDS, CloudWatchWasteMetrics

START = datetime(2026, 9, 1, tzinfo=UTC)
END = datetime(2026, 9, 21, tzinfo=UTC)
NOW = datetime(2026, 9, 21, 6, 0, tzinfo=UTC)
ACCOUNT = AccountKey(provider=Provider.AWS, account_id="111122223333")


class CloudWatch:
    """Records every call, because the call count is the cost."""

    def __init__(self, *, answers_for: set[str] | None = None) -> None:
        self.batches: list[list[dict[str, Any]]] = []
        self.periods: list[int] = []
        self._answers_for = answers_for

    def get_metric_data(self, **kwargs: Any) -> Any:
        queries = kwargs["MetricDataQueries"]
        self.batches.append(queries)
        self.periods.extend(q["MetricStat"]["Period"] for q in queries)
        results = []
        for query in queries:
            name = query["MetricStat"]["Metric"]["MetricName"]
            if self._answers_for is not None and name not in self._answers_for:
                # A series that published nothing. It comes back with no
                # timestamps, which is how CloudWatch says it.
                results.append({"Id": query["Id"], "Timestamps": [], "Values": []})
                continue
            results.append(
                {
                    "Id": query["Id"],
                    "Label": "Percent",
                    "Timestamps": [START],
                    "Values": [7.5],
                }
            )
        return {"MetricDataResults": results}


def requests(count: int, *, name: str = "CPUUtilization") -> list[MetricRequest]:
    return [
        MetricRequest(
            key=f"series-{index}",
            account=ACCOUNT,
            region="eu-west-1",
            namespace="AWS/EC2",
            metric_name=name,
            dimensions={"InstanceId": f"i-{index:04d}"},
            statistic="Average",
        )
        for index in range(count)
    ]


def reader(settings: Settings, cloudwatch: CloudWatch) -> CloudWatchWasteMetrics:
    return CloudWatchWasteMetrics(
        settings, client_factory=lambda _a, _r: cloudwatch, clock=lambda: NOW
    )


class TestTheCallCountIsTheCost:
    def test_twelve_hundred_series_is_three_calls_not_twelve_hundred(
        self, settings: Settings
    ) -> None:
        """The reason the batch size is in the specification.

        One call per series across a three hundred account estate is a line item
        that shows up on our own platform cost screen.
        """
        cloudwatch = CloudWatch()
        reader(settings, cloudwatch).read_many(requests(1200), START, END)
        assert len(cloudwatch.batches) == 3
        assert [len(batch) for batch in cloudwatch.batches] == [500, 500, 200]

    def test_the_batch_size_comes_from_settings(self, settings: Settings) -> None:
        # Not a literal in the adapter. The value is already declared in
        # .env.example and was previously honoured by nothing.
        assert settings.getmetricdata_batch_size == 500

    def test_one_series_is_one_call(self, settings: Settings) -> None:
        cloudwatch = CloudWatch()
        reader(settings, cloudwatch).read_many(requests(1), START, END)
        assert len(cloudwatch.batches) == 1

    def test_two_accounts_are_never_batched_together(self, settings: Settings) -> None:
        # A metric read is an assumed role call into the account that owns the
        # resource, so a batch spanning accounts is a call that cannot be made.
        other = AccountKey(provider=Provider.AWS, account_id="444455556666")
        mixed = [
            *requests(2),
            MetricRequest(
                key="elsewhere",
                account=other,
                region="eu-west-1",
                namespace="AWS/EC2",
                metric_name="CPUUtilization",
                dimensions={"InstanceId": "i-9999"},
                statistic="Average",
            ),
        ]
        cloudwatch = CloudWatch()
        reader(settings, cloudwatch).read_many(mixed, START, END)
        assert len(cloudwatch.batches) == 2


class TestThePeriod:
    def test_it_reads_at_one_hour(self, settings: Settings) -> None:
        """Both for the bill and for the percentile.

        A percentile over daily points is the second largest value, which makes
        the p99 rule silently become the max rule it exists to replace.
        """
        cloudwatch = CloudWatch()
        reader(settings, cloudwatch).read_many(requests(3), START, END)
        assert set(cloudwatch.periods) == {PERIOD_SECONDS}
        assert PERIOD_SECONDS == 3600


class TestAbsentIsNotZero:
    def test_a_series_that_published_nothing_is_missing_from_the_result(
        self, settings: Settings
    ) -> None:
        """The most expensive possible instance of rendering a failure as a number.

        A caller reading an absent key as zero utilization would recommend
        terminating a running system, so the key is absent rather than empty and
        the caller has to decide what to do about it.
        """
        cloudwatch = CloudWatch(answers_for=set())
        found = reader(settings, cloudwatch).read_many(requests(3), START, END)
        assert found == {}

    def test_a_partly_empty_batch_returns_the_rest(self, settings: Settings) -> None:
        # A batch where some series are empty is the normal case, and failing the
        # whole read for it would make the method unusable at the scale it exists
        # for. NoData is deliberately not raised.
        mixed = [*requests(2), *requests(1, name="MemoryUtilization")]
        cloudwatch = CloudWatch(answers_for={"CPUUtilization"})
        found = reader(settings, cloudwatch).read_many(mixed, START, END)
        assert len(found) == 2


class TestThePointsThemselves:
    def test_money_and_values_are_decimal(self, settings: Settings) -> None:
        found = reader(settings, CloudWatch()).read_many(requests(1), START, END)
        point = found["series-0"][0]
        assert isinstance(point.value, Decimal)

    def test_both_timestamps_are_present_and_ordered(self, settings: Settings) -> None:
        # Constraint 10. For a metric `at` and `as_of` coincide, and
        # `collected_at` is when we looked.
        found = reader(settings, CloudWatch()).read_many(requests(1), START, END)
        point = found["series-0"][0]
        assert point.at == point.as_of
        assert point.collected_at == NOW

    def test_a_provider_failure_becomes_a_typed_cause(self, settings: Settings) -> None:
        from botocore.exceptions import ClientError

        from finops_core.errors import Throttled

        class Refusing:
            def get_metric_data(self, **_: Any) -> Any:
                raise ClientError(
                    {"Error": {"Code": "ThrottlingException", "Message": "slow"}}, "GetMetricData"
                )

        source = CloudWatchWasteMetrics(
            settings, client_factory=lambda _a, _r: Refusing(), clock=lambda: NOW
        )
        with pytest.raises(Throttled):
            source.read_many(requests(1), START, END)
