"""The sizing detector against an estate that says in advance what it contains.

`test_waste_compute.py` drives the collector through seven flat shapes written by
the same hand that wrote the assertions, which tests the plumbing and cannot test
the judgement: a detector and its fixture agreeing proves only that they agree.

This drives the same collector over the generated utilization estate, where every
instance carries two years of hourly behaviour and `planted.PLANTED` states the
outcome a correct detector reaches, with a reason. The set is what makes it worth
running:

- two instances that **should** be found, one idle and one oversized
- three that should **not**, and each is a different false positive: a burstable
  instance on a healthy credit balance, a dev box that is idle every night by
  design, and a memory bound instance whose CPU looks idle because the work is not
  CPU work
- one that should be **refused**, because nine days is under the fourteen day floor
- one under upward pressure, which P3 does not size and must not report

The third of those is the one this file exists for. The collector reads CPU and
nothing else, so an instance busy in memory and quiet in CPU is exactly the shape it
is most likely to get wrong, and no fixture written alongside the detector would
have contained one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from itertools import pairwise
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.config import Settings
from finops_core.domain.account import AccountKey, Provider
from finops_core.ports.metrics import MetricRequest
from finops_fakes import fixtures, planted
from finops_fakes.estate_metrics import EstateMetrics, ec2_candidates
from finops_ingest.collectors.waste_compute import Candidate, WasteComputeCollector
from finops_ingest.registry import CollectorContext

pytestmark = pytest.mark.integration

#: The estate's own reference point. The collector runs here rather than on a real
#: clock, because two years of generated history end at this instant and a run a
#: month later would judge a window half of which the estate does not cover.
NOW = fixtures.AS_OF


def _expected() -> dict[str, tuple[tuple[str, str], ...]]:
    """What the planted entries say about each EC2 instance.

    A list per subject, not one entry, because an instance can carry more than one
    expectation: the idle one in `fake-product-b` is both `EC2_IDLE`, which P3
    should find, and `QUOTA_HELD_BY_IDLE_RESOURCE`, which P5 reads as quota
    pressure. A mapping that kept the last entry per subject would silently swap
    one for the other, and the test would then look for a finding under a code
    that no longer named it.
    """
    found: dict[str, list[tuple[str, str]]] = {}
    for entry in planted.PLANTED:
        for subject in entry.subjects:
            if subject.startswith("amazonec2/"):
                found.setdefault(subject, []).append((entry.expected, entry.code))
    return {subject: tuple(entries) for subject, entries in found.items()}


EXPECTED = _expected()


def codes(subject: str) -> tuple[str, ...]:
    return tuple(code for _, code in EXPECTED[subject])


def subject_of(code: str) -> str:
    """The one instance a planted code names. Raises if the code moved."""
    return next(subject for subject in EXPECTED if code in codes(subject))


def should_be_found(subject: str) -> bool:
    """Any FINDING expectation means the detector should report it.

    A subject carrying both a FINDING and a PRESSURE is still a finding: the second
    is another sub project's reading of the same instance, not a reason to stay
    quiet about this one.
    """
    return any(verdict == "FINDING" for verdict, _ in EXPECTED[subject])


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID


def cpu_request(resource_id: str, account_id: str, region_id: str) -> MetricRequest:
    return MetricRequest(
        key=resource_id,
        account=AccountKey(provider=Provider.AWS, account_id=account_id),
        region=region_id,
        namespace="AWS/EC2",
        metric_name="CPUUtilization",
        dimensions={"InstanceId": resource_id},
        statistic="Average",
    )


def collect(engine: Engine, tenant: UUID, settings: Settings) -> int:
    candidates = [
        Candidate(
            resource_id=c.resource_id,
            account_id=c.account_id,
            region_id=c.region_id,
            observation_days=c.observation_days,
            monthly_cost=c.monthly_cost,
            credit_balance=c.credit_balance,
        )
        for c in ec2_candidates(at=NOW)
    ]
    with engine.begin() as connection:
        outcome = WasteComputeCollector(
            EstateMetrics(at=NOW), lambda _context: candidates, clock=lambda: NOW
        )(
            CollectorContext(
                unit=Unit(tenant_id=tenant),
                connection=connection,
                run_id=uuid4(),
                settings=settings,
            )
        )
    return int(outcome.items_written)


def found(engine: Engine, tenant: UUID) -> dict[str, tuple[str, Decimal]]:
    with engine.connect() as connection:
        return {
            row[0]: (row[1], Decimal(row[2]))
            for row in connection.execute(
                text(
                    "SELECT resource_id, waste_class, estimated_monthly_saving "
                    "FROM recommendation WHERE tenant_id = :t AND source = 'METER'"
                ),
                {"t": tenant},
            ).all()
        }


#: Planted EC2 subjects P3's per instance rule is not allowed to judge, and why.
#: A group absorbs demand by changing how many instances it runs, so one member's
#: CPU says nothing about whether the instance type is too large. Listed rather than
#: filtered out silently, so excluding one is a decision a reader can disagree with.
GROUPS = {
    "amazonec2/fake-product-a/0001": "an Auto Scaling group, sized at group level",
    "amazonec2/fake-platform-b/0001": "an EKS node group, which is P6's to size",
}


def test_the_oracle_covers_every_instance_the_collector_is_given() -> None:
    """The expectations, checked before they are trusted.

    An oracle missing an entry silently excuses whatever the detector does about
    that instance, which is the failure mode of every expected output test. So the
    two lists are compared as sets first, with the groups named rather than dropped.
    """
    given = {c.resource_id for c in ec2_candidates(at=NOW)}
    judgeable = set(EXPECTED) - set(GROUPS)
    assert given == judgeable, {
        "given but not planted": sorted(given - judgeable),
        "planted but not given": sorted(judgeable - given),
    }
    # And the excluded ones really are planted, so this list cannot quietly grow to
    # cover a resource the detector started getting wrong.
    assert set(GROUPS) <= set(EXPECTED), sorted(set(GROUPS) - set(EXPECTED))


def test_a_scaling_group_is_never_offered_to_the_per_instance_rule() -> None:
    """The estate's own reason, asserted rather than trusted.

    `ASG_SCALE_OUT_ON_SPIKE_DAY` scales to six times its size on the day the bill
    spikes, and its planted expectation is no finding, because a recommendation for
    a group is made at group level. So the group never reaches the rule at all,
    which is a cleaner answer than a rule that looks and then declines.
    """
    given = {c.resource_id for c in ec2_candidates(at=NOW)}
    for subject, reason in GROUPS.items():
        assert subject not in given, (subject, reason)
    assert "ASG_SCALE_OUT_ON_SPIKE_DAY" in codes("amazonec2/fake-product-a/0001")


class TestWhatItFinds:
    def test_it_finds_exactly_the_planted_findings_and_nothing_else(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """Both directions in one test, deliberately.

        A detector that finds everything passes the first half and a detector that
        finds nothing passes the second, so the two are worth nothing apart.
        """
        collect(engine, tenant_id, settings)
        reported = set(found(engine, tenant_id))
        judgeable = set(EXPECTED) - set(GROUPS)
        should_find = {s for s in judgeable if should_be_found(s)}
        should_not = judgeable - should_find

        missed = should_find - reported
        invented = reported & should_not
        assert not missed, {"missed": sorted((s, codes(s)) for s in missed)}
        assert not invented, {"false positives": sorted((s, codes(s)) for s in invented)}

    def test_the_idle_instance_is_called_idle_rather_than_oversized(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # The two classes are different recommendations: one says make it smaller
        # and one says it should not exist. Getting the class wrong sends somebody
        # to resize a machine nobody is using.
        collect(engine, tenant_id, settings)
        assert found(engine, tenant_id)[subject_of("EC2_IDLE")][0] == "IDLE_INSTANCE"

    def test_the_oversized_instance_is_a_rightsizing(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        collect(engine, tenant_id, settings)
        oversized = subject_of("OVERSIZED_MEMORY_UNOBSERVED")
        assert found(engine, tenant_id)[oversized][0] == "RIGHTSIZE_INSTANCE"


class TestWhatItRefusesToFind:
    @pytest.mark.parametrize(
        "code",
        ["BURSTABLE_HEALTHY_CREDITS", "DEV_BOX_IDLE_AT_NIGHT", "MEMORY_BOUND_CPU_LOOKS_IDLE"],
        ids=lambda code: code.lower(),
    )
    def test_a_correctly_sized_instance_produces_no_recommendation(
        self, engine: Engine, tenant_id: UUID, settings: Settings, code: str
    ) -> None:
        """Three different reasons an instance looks idle and is not.

        Named one by one rather than folded into the set assertion above, because
        when one of them regresses the failing test should say which mistake the
        detector started making.
        """
        collect(engine, tenant_id, settings)
        assert subject_of(code) not in found(engine, tenant_id), planted.BY_CODE[code].why

    def test_an_instance_under_the_history_floor_is_refused(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # Nine days. Below the floor a new instance looks exactly like an idle one,
        # and the row should not exist at all rather than exist with a low
        # confidence attached to it.
        collect(engine, tenant_id, settings)
        assert subject_of("UNDER_HISTORY_FLOOR") not in found(engine, tenant_id)

    def test_an_instance_under_upward_pressure_is_not_reported(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """P3 sizes downward only, and this is the instance that proves it.

        An over utilized instance is a real finding and a different product: it
        costs more money rather than less, and reporting it on a screen headed by a
        saving would put a number there that nobody saves.
        """
        collect(engine, tenant_id, settings)
        assert subject_of("EC2_OVER_UTILIZED") not in found(engine, tenant_id)


class TestTheEstateItself:
    def test_a_denied_account_is_unobserved_rather_than_an_empty_estate(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """The refusal path, through the batched read.

        `series_for` raises for the denied account, and a batch that let that
        propagate would lose every other series in the request. The adapter omits
        the key instead, which the collector counts as unobserved and records.
        """
        candidates = [
            Candidate(
                resource_id="i-denied",
                account_id=fixtures.DENIED_ACCOUNT_KEY.account_id,
                region_id=fixtures.REGION,
                observation_days=90,
                monthly_cost=Decimal("100.00"),
            )
        ]
        with engine.begin() as connection:
            outcome = WasteComputeCollector(
                EstateMetrics(at=NOW), lambda _context: candidates, clock=lambda: NOW
            )(
                CollectorContext(
                    unit=Unit(tenant_id=tenant_id),
                    connection=connection,
                    run_id=uuid4(),
                    settings=settings,
                )
            )
        assert int(outcome.items_written) == 0
        with engine.connect() as connection:
            detail = connection.execute(
                text(
                    "SELECT detail FROM sync_error WHERE tenant_id = :t "
                    "AND collector = 'waste_compute'"
                ),
                {"t": tenant_id},
            ).scalar_one()
        assert "published no metrics" in detail

    def test_every_series_is_hourly(self) -> None:
        """The resolution the sizing rules are written for.

        `finops_query.waste` says every series is hourly, and that a p99 over daily
        points silently becomes the maximum. This asserts the estate actually is,
        rather than trusting a sentence in a docstring.
        """
        candidate = next(c for c in ec2_candidates(at=NOW) if c.observation_days > 300)
        series = EstateMetrics(at=NOW).read_many(
            [cpu_request(candidate.resource_id, candidate.account_id, candidate.region_id)],
            NOW - timedelta(days=14),
            NOW,
        )
        points = series[candidate.resource_id]
        # Fourteen days of hourly points, which is the 336 the module names as the
        # count that keeps a percentile from collapsing onto the maximum.
        assert len(points) >= 336
        gaps = {(b.at - a.at).total_seconds() for a, b in pairwise(points)}
        assert gaps == {3600.0}

    def test_the_series_has_a_shape_rather_than_one_repeated_value(self) -> None:
        """What the estate buys over the hand written fixture, asserted.

        The old fake returns one value for every hour. If this estate ever started
        doing the same, every test above would still pass while testing nothing
        about a percentile, so the variety is checked rather than assumed.
        """
        candidate = next(c for c in ec2_candidates(at=NOW) if c.observation_days > 300)
        series = EstateMetrics(at=NOW).read_many(
            [cpu_request(candidate.resource_id, candidate.account_id, candidate.region_id)],
            NOW - timedelta(days=14),
            NOW,
        )
        values = {point.value for point in series[candidate.resource_id]}
        assert len(values) > 300, "a flat series would make every percentile test vacuous"
