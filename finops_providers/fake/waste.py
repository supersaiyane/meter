"""An estate with waste in it, and with things that look like waste and are not.

A fake where every low utilization instance is wasteful proves nothing about a
detector: the tests pass whether or not the detector is right. Three of the five
instances here are deliberately fine, and each stands for a different way a naive
detector goes wrong.

| Instance | Looks like | Actually |
| --- | --- | --- |
| `i-oversized` | 8 percent CPU | Genuinely oversized |
| `i-idle` | Nothing at all | Genuinely idle |
| `i-burstable` | 20 percent CPU | Correctly sized, running on credits |
| `i-batch` | Idle 95 percent of the time | A batch worker, busy in bursts |
| `i-new` | 6 percent CPU | Nine days old, under the floor |

Series are **hourly**, which is what the adapter reads and what makes a percentile
mean anything. `i-unobserved` publishes no series at all and is absent from the
result rather than present with zeroes, because that is what the port says an
unobserved series looks like and a caller must handle it.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.metrics import MetricPoint
from finops_core.ports.metrics import MetricRequest
from finops_providers.fake import fixtures

#: An hour of points per hour, over the window each instance has existed for.
HOURS_PER_DAY = 24

ACCOUNT = AccountKey(provider=Provider.AWS, account_id="fake-platform-a")


class Shape:
    """How one instance behaves, as a function of the hour."""

    def __init__(
        self,
        instance_id: str,
        *,
        days: int,
        monthly_cost: Decimal,
        credit_balance: Decimal | None = None,
        publishes: bool = True,
    ) -> None:
        self.instance_id = instance_id
        self.days = days
        self.monthly_cost = monthly_cost
        self.credit_balance = credit_balance
        self.publishes = publishes

    def at(self, hour: int) -> Decimal:  # pragma: no cover - overridden
        raise NotImplementedError


class _Flat(Shape):
    def __init__(self, instance_id: str, level: Decimal, **kwargs: object) -> None:
        super().__init__(instance_id, **kwargs)  # type: ignore[arg-type]
        self._level = level

    def at(self, hour: int) -> Decimal:  # noqa: ARG002  a flat shape ignores the hour
        return self._level


class _Bursty(Shape):
    """Idle most of the time and busy in bursts. A batch worker, not waste.

    The mean would call this idle. p95 does not, which is the whole reason the
    detector uses a percentile.
    """

    def at(self, hour: int) -> Decimal:
        return Decimal("92") if hour % HOURS_PER_DAY in (2, 3) else Decimal("0")


class _Diurnal(Shape):
    """Busy by day and quiet at night. Also not waste."""

    def at(self, hour: int) -> Decimal:
        of_day = hour % HOURS_PER_DAY
        return Decimal(str(round(45 + 35 * math.sin((of_day - 6) / 24 * 2 * math.pi), 2)))


SHAPES: tuple[Shape, ...] = (
    _Flat("i-oversized", Decimal("8"), days=45, monthly_cost=Decimal("420.00")),
    _Flat("i-idle", Decimal("0.2"), days=45, monthly_cost=Decimal("180.00")),
    # The single most common false positive in this whole category.
    _Flat(
        "i-burstable",
        Decimal("20"),
        days=45,
        monthly_cost=Decimal("90.00"),
        credit_balance=Decimal("144"),
    ),
    _Bursty("i-batch", days=45, monthly_cost=Decimal("260.00")),
    _Diurnal("i-diurnal", days=45, monthly_cost=Decimal("310.00")),
    # Under the floor. Nine days is not enough to say anything.
    _Flat("i-new", Decimal("6"), days=9, monthly_cost=Decimal("200.00")),
    # Publishes nothing. Absent from the result, not zero.
    _Flat("i-unobserved", Decimal("0"), days=45, monthly_cost=Decimal("150.00"), publishes=False),
)

BY_ID: Mapping[str, Shape] = {shape.instance_id: shape for shape in SHAPES}


def instances() -> tuple[Shape, ...]:
    """Every instance in the fake estate, including the ones nothing is wrong with."""
    return SHAPES


class FakeWasteMetrics:
    """`MetricSource.read_many` over the estate above."""

    def __init__(self, at: datetime = fixtures.AS_OF) -> None:
        self._at = at

    def read_many(
        self,
        requests: Iterable[MetricRequest],
        window_start: datetime,  # noqa: ARG002  the shape decides its own length
        window_end: datetime,
        period_seconds: int = 3600,  # noqa: ARG002  the fake is hourly by construction
    ) -> Mapping[str, tuple[MetricPoint, ...]]:
        found: dict[str, tuple[MetricPoint, ...]] = {}
        for request in requests:
            shape = BY_ID.get(request.dimensions.get("InstanceId", ""))
            if shape is None or not shape.publishes:
                # Absent, not empty. The port says an unobserved series does not
                # appear, and a caller must tell that from a series of zeroes.
                continue
            points = []
            for hour in range(shape.days * HOURS_PER_DAY):
                at = window_end - timedelta(hours=hour)
                points.append(
                    MetricPoint(
                        as_of=at,
                        collected_at=self._at.replace(tzinfo=UTC),
                        at=at,
                        account_key=request.account,
                        namespace=request.namespace,
                        metric_name=request.metric_name,
                        statistic=request.statistic,
                        unit="Percent",
                        value=shape.at(hour),
                    )
                )
            found[request.key] = tuple(points)
        return found
