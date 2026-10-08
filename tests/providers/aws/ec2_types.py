"""A stubbed EC2 client, answering DescribeInstanceTypes as EC2 does. TASK-P9-005.

Shared by the adapter's tests and the catalog contract. The descriptions are the fake catalog's
types written into the shape the real `t2.micro` description in
`tests/providers/aws/extracts/describe-instance-types-t2-micro.json` has, so the adapter is held
to the contract by reading the fake's own types through the shape EC2 sends them in.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from datetime import datetime, timedelta
from typing import Any

from botocore.exceptions import ClientError

from finops_core.domain.catalog import InstanceTypeSpec, SpotPrice
from finops_core.errors import CollectionError
from finops_fakes import fixtures
from finops_fakes.catalog import FakeInstanceCatalog, FakeSpotPrices
from finops_fakes.estate_shape import REGIONS
from finops_providers.aws.instance_types import AwsInstanceCatalog
from finops_providers.aws.spot import AwsSpotPrices

#: The code EC2 answers each cause with.
CODES: dict[str, str] = {
    "AccessDenied": "UnauthorizedOperation",
    "Throttled": "RequestLimitExceeded",
    "NotOptedIn": "OptInRequired",
}


def described(spec: InstanceTypeSpec) -> dict[str, Any]:
    """One `InstanceTypes` entry for a type, in EC2's own shape."""
    return {
        "InstanceType": spec.instance_type,
        "CurrentGeneration": spec.current_generation,
        "ProcessorInfo": {"SupportedArchitectures": list(spec.architectures)},
        "BurstablePerformanceSupported": spec.burstable,
        "VCpuInfo": {"DefaultVCpus": spec.vcpus},
        "MemoryInfo": {"SizeInMiB": spec.memory_mib},
        "NetworkInfo": {"NetworkPerformance": spec.network_performance},
        "GpuInfo": {"Gpus": [{"Count": spec.gpu_count}]} if spec.gpu_count else {},
    }


class StubEc2:
    """Answers `get_paginator("describe_instance_types").paginate()` a page at a time."""

    def __init__(
        self,
        types: Iterable[dict[str, Any]],
        *,
        failure: str | None = None,
        page_size: int = 5,
    ) -> None:
        self._types = list(types)
        self._failure = failure
        self._page_size = page_size
        self.calls = 0

    def get_paginator(self, operation: str) -> StubEc2:
        assert operation == "describe_instance_types"
        return self

    def paginate(self, **request: Any) -> Iterator[dict[str, Any]]:
        assert request == {}, "the adapter asks for every type, unfiltered"
        self.calls += 1
        if self._failure is not None:
            code = CODES[self._failure]
            raise ClientError(
                {"Error": {"Code": code, "Message": "stubbed"}}, "DescribeInstanceTypes"
            )
        for start in range(0, max(len(self._types), 1), self._page_size):
            yield {"InstanceTypes": self._types[start : start + self._page_size]}


def fake_backed(
    *,
    not_opted_in: Iterable[str] = (),
    failure: type[CollectionError] | None = None,
) -> AwsInstanceCatalog:
    """The AWS adapter over stubs serving the fake's types in every Region, for the contract."""
    refusing = frozenset(not_opted_in)
    types = [described(s) for s in FakeInstanceCatalog().instance_types(REGIONS[0])]

    def client_for(region: str) -> StubEc2:
        if failure is not None:
            return StubEc2(types, failure=failure.cause)
        return StubEc2(types, failure="NotOptedIn" if region in refusing else None)

    return AwsInstanceCatalog(client_for=client_for, clock=lambda: fixtures.COLLECTED_AT)


# --- spot prices, TASK-P9-013 ---------------------------------------------------------------


def spot_entry(reading: SpotPrice) -> dict[str, Any]:
    """One `SpotPriceHistory` entry, in EC2's own shape."""
    return {
        "AvailabilityZone": reading.availability_zone,
        "InstanceType": reading.instance_type,
        "ProductDescription": reading.product_description,
        "SpotPrice": f"{reading.price:.6f}",
        "Timestamp": reading.as_of,
    }


class StubSpot:
    """Answers `get_paginator("describe_spot_price_history").paginate(...)` a page at a time."""

    def __init__(
        self, entries: Iterable[dict[str, Any]], *, failure: str | None = None, page_size: int = 25
    ) -> None:
        self._entries = list(entries)
        self._failure = failure
        self._page_size = page_size
        self.requests: list[dict[str, Any]] = []

    def get_paginator(self, operation: str) -> StubSpot:
        assert operation == "describe_spot_price_history"
        return self

    def paginate(self, **request: Any) -> Iterator[dict[str, Any]]:
        self.requests.append(request)
        if self._failure is not None:
            code = CODES[self._failure]
            raise ClientError({"Error": {"Code": code, "Message": "stubbed"}}, "DescribeSpot")
        for start in range(0, max(len(self._entries), 1), self._page_size):
            yield {"SpotPriceHistory": self._entries[start : start + self._page_size]}


def fake_spot_backed(
    *,
    not_opted_in: Iterable[str] = (),
    failure: type[CollectionError] | None = None,
) -> AwsSpotPrices:
    """The AWS adapter over stubs serving the fake's readings in each Region, for the contract."""
    refusing = frozenset(not_opted_in)
    fake = FakeSpotPrices()
    clock = SpotClock()

    def client_for(region: str) -> StubSpot:
        if failure is not None:
            return StubSpot((), failure=failure.cause)
        if region in refusing:
            return StubSpot((), failure="NotOptedIn")
        if region not in REGIONS:
            return StubSpot(())
        since = clock.since
        return StubSpot(spot_entry(r) for r in fake.prices(region, since))

    return AwsSpotPrices(client_for=client_for, clock=clock)


class SpotClock:
    """The read's clock, two hours after the window the contract asks for opens."""

    since = fixtures.COLLECTED_AT

    def __call__(self) -> datetime:
        return self.since + timedelta(hours=2)
