"""What CloudWatch is holding, in memory.

Six log groups and four alarms, and most of them are fine. The ones that are fine
are the point: a group with a retention policy, a group too young for a policy to
have saved anything yet, an alarm in alarm, and an alarm that only just went quiet.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta
from decimal import Decimal

from finops_core.ports.cloudwatch_estate import Alarm, LogGroup
from finops_providers.fake import fixtures

ACCOUNT = "fake-platform-a"
REGION = "eu-west-1"

#: Roughly the eu-west-1 list price. A fake, and the adapter reads the real one.
PRICE_PER_GB_MONTH = Decimal("0.03")

GB = 1024**3


def log_groups(at: datetime = fixtures.AS_OF) -> tuple[LogGroup, ...]:
    return (
        # The finding. Two years of logs nobody chose to keep.
        LogGroup(
            name="/aws/lambda/fake-ingest",
            account_id=ACCOUNT,
            region_id=REGION,
            stored_bytes=900 * GB,
            retention_days=None,
            created_at=at - timedelta(days=730),
        ),
        # Somebody chose. Not a finding, however large it is.
        LogGroup(
            name="/aws/eks/fake-cluster/cluster",
            account_id=ACCOUNT,
            region_id=REGION,
            stored_bytes=1200 * GB,
            retention_days=30,
            created_at=at - timedelta(days=500),
        ),
        # No policy, but only three weeks old. Setting one saves nothing yet, and
        # a product that flagged it would be asking for work with no payoff.
        LogGroup(
            name="/aws/lambda/fake-new",
            account_id=ACCOUNT,
            region_id=REGION,
            stored_bytes=4 * GB,
            retention_days=None,
            created_at=at - timedelta(days=21),
        ),
        # No policy and old, but tiny. Under the dollar floor.
        LogGroup(
            name="/aws/lambda/fake-quiet",
            account_id=ACCOUNT,
            region_id=REGION,
            stored_bytes=1 * GB,
            retention_days=None,
            created_at=at - timedelta(days=400),
        ),
    )


def alarms(at: datetime = fixtures.AS_OF) -> tuple[Alarm, ...]:
    return (
        # The finding. Watching a metric that stopped reporting last spring.
        Alarm(
            name="fake-orphaned-queue-depth",
            account_id=ACCOUNT,
            region_id=REGION,
            state="INSUFFICIENT_DATA",
            state_changed_at=at - timedelta(days=210),
        ),
        # Insufficient data for two hours. Normal, and flagging it would teach a
        # reader to skim the screen.
        Alarm(
            name="fake-deploying-service",
            account_id=ACCOUNT,
            region_id=REGION,
            state="INSUFFICIENT_DATA",
            state_changed_at=at - timedelta(hours=2),
        ),
        Alarm(
            name="fake-healthy",
            account_id=ACCOUNT,
            region_id=REGION,
            state="OK",
            state_changed_at=at - timedelta(days=400),
        ),
        Alarm(
            name="fake-firing",
            account_id=ACCOUNT,
            region_id=REGION,
            state="ALARM",
            state_changed_at=at - timedelta(minutes=30),
        ),
    )


class FakeCloudWatchEstate:
    """`CloudWatchEstate` in memory."""

    def __init__(self, at: datetime = fixtures.AS_OF, *, price_known: bool = True) -> None:
        self._at = at
        self._price_known = price_known

    def log_groups(self) -> Iterable[LogGroup]:
        return log_groups(self._at)

    def alarms(self) -> Iterable[Alarm]:
        return alarms(self._at)

    def storage_price_per_gb_month(self) -> Decimal:
        if not self._price_known:
            from finops_core.errors import NoData

            raise NoData(
                scope_key=fixtures.ORGANIZATION_SCOPE,
                collector="waste_cloudwatch",
                detail="no storage price could be determined for this region",
            )
        return PRICE_PER_GB_MONTH
