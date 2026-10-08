"""The spot price adapter, held to EC2's shape. TASK-P9-013, FEAT-071.

The entries are written in the shape the botocore 1.43.108 model gives `DescribeSpotPriceHistory`,
which `tests/providers/aws/test_response_shapes.py` holds every name read here to.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from finops_core.errors import AccessDenied, NoData, NotOptedIn, SchemaDrift, Throttled
from finops_providers.aws.spot import AwsSpotPrices
from tests.providers.aws.ec2_types import StubSpot

AT = datetime(2026, 10, 8, 6, 0, tzinfo=UTC)
SINCE = AT - timedelta(hours=8)
REGION = "eu-west-1"


def entry(**overrides: Any) -> dict[str, Any]:
    return {
        "AvailabilityZone": "eu-west-1a",
        "InstanceType": "m5.large",
        "ProductDescription": "Linux/UNIX",
        "SpotPrice": "0.038100",
        "Timestamp": SINCE - timedelta(days=2),
        **overrides,
    }


def read(*entries: dict[str, Any], failure: str | None = None) -> tuple[Any, StubSpot]:
    stub = StubSpot(entries, failure=failure)
    spot = AwsSpotPrices(client_for=lambda _region: stub, clock=lambda: AT)
    return tuple(spot.prices(REGION, SINCE)), stub


def test_a_reading_is_a_pools_price_at_its_own_time() -> None:
    (reading,), stub = read(entry())
    assert reading.pool == ("eu-west-1a", "m5.large", "Linux/UNIX")
    assert reading.price == Decimal("0.038100")
    assert (reading.as_of, reading.collected_at) == (SINCE - timedelta(days=2), AT)
    assert stub.requests == [
        {"StartTime": SINCE.isoformat(), "EndTime": AT.isoformat(), "MaxResults": 1000}
    ]


def test_every_page_is_read() -> None:
    entries = [entry(InstanceType=f"m5.{n}xlarge") for n in range(60)]
    readings, _ = read(*entries)
    assert len(readings) == 60


def test_a_time_without_a_zone_is_read_as_utc() -> None:
    (reading,), _ = read(entry(Timestamp=datetime(2026, 10, 8, 1, 0)))
    assert reading.as_of == datetime(2026, 10, 8, 1, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "overrides",
    [
        {"SpotPrice": "0"},
        {"SpotPrice": "not a price"},
        {"Timestamp": "2026-10-08T01:00:00Z"},
        {"AvailabilityZone": "us-east-1a"},
        {"ProductDescription": None},
    ],
)
def test_a_reading_this_cannot_read_is_schema_drift(overrides: dict[str, Any]) -> None:
    raw = entry(**overrides)
    if "ProductDescription" in overrides:
        del raw["ProductDescription"]
    with pytest.raises(SchemaDrift, match=r"m5\.large"):
        read(raw)


def test_a_region_with_no_pool_is_no_data() -> None:
    with pytest.raises(NoData):
        read()


@pytest.mark.parametrize(
    ("code", "cause"),
    [("AccessDenied", AccessDenied), ("Throttled", Throttled), ("NotOptedIn", NotOptedIn)],
)
def test_a_refused_read_is_raised_by_its_cause(code: str, cause: type[Exception]) -> None:
    with pytest.raises(cause):
        read(entry(), failure=code)
