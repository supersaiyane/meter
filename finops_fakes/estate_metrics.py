"""The utilization estate behind the `MetricSource` port.

`utilization.py` and `containers.py` generate an estate. This is the adapter that
lets a collector read it through the port it already speaks, so `waste_compute` can
run against 36 resources with two years of hourly behaviour instead of the seven
flat shapes in `waste.py`.

Three things it has to get right, and each is a rule the estate already keeps.

**A refusal is not an empty series.** `series_for` raises `AccessDenied` for the
account that refuses and `NotOptedIn` for the region that is not enabled. A batch
read catches those per slice and omits the key, because the port says an absent key
means unobserved and the collector counts those separately. A batch that failed
entirely because one account denied us would be useless at the scale the batched
read exists for.

**Absent is not zero.** A resource that publishes no memory series, because it runs
no agent, has no key in the result. Returning an empty tuple would be a series of
no values, which a percentile over would read as nought.

**The money comes from `prices.py`.** The estate itself carries none, on purpose.
Until 2026-09-21 that meant the join `DATA_DICTIONARY.md` decision 6 describes was
missing and this module kept its own instance price list. `cur.py` now bills every
estate resource from the same module, so the estimated saving and the charge it is
about cannot disagree about what a thing costs.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from finops_core.domain.account import AccountKey
from finops_core.domain.metrics import MetricPoint
from finops_core.errors import CollectionError
from finops_core.ports.metrics import MetricRequest
from finops_fakes import estate_shape as shape
from finops_fakes import fixtures, prices, utilization


#: The price list lives in `prices.py`, read by this module and by `cur.py`, so a
#: rightsizing saving and the bill line it is about come from one number. Two lists
#: drifted apart is how an estimated saving and a realized saving disagree for a
#: reason that is an artefact of the fixture.
def monthly_cost(spec: utilization.Spec) -> Decimal:
    """What one estate resource costs per month. Invented, see `prices.py`."""
    return prices.monthly_usd(spec)


def _resource_of(dimensions: Mapping[str, str]) -> str | None:
    """Which resource a dimension set names, whatever the dimension is called.

    CloudWatch names the dimension differently per namespace: `InstanceId` for EC2,
    `DBInstanceIdentifier` for RDS, `LoadBalancer` for an ALB. The estate carries
    the dimension name beside each point, so rather than keep a second mapping that
    can disagree with it, this takes the single value and matches on the resource.
    """
    if len(dimensions) != 1:
        return None
    return next(iter(dimensions.values()))


class EstateMetrics:
    """`MetricSource` over the generated utilization estate.

    `at` fixes the estate's reference point. It defaults to `fixtures.AS_OF`, which
    is where the two years of generated history end, so a collector running on a
    later clock still reads real behaviour for the part of its window that overlaps
    rather than an estate that stops existing.
    """

    def __init__(self, *, at: datetime = fixtures.AS_OF) -> None:
        self._at = at

    def read_series(
        self,
        account: AccountKey,
        region: str,
        namespace: str,
        metric_name: str,
        dimensions: Mapping[str, str],
        statistic: str,
        window_start: datetime,
        window_end: datetime,
    ) -> Iterable[MetricPoint]:
        """One series, or nothing. Refusals propagate here, unlike in a batch.

        A single read names one resource, so a caller that asked about a denied
        account wants to be told rather than handed an empty answer.
        """
        wanted = _resource_of(dimensions)
        return tuple(
            sp.point
            for sp in utilization.series_for(
                account.account_id, region, start=window_start, end=window_end, at=self._at
            )
            if sp.resource_id == wanted
            and sp.point.namespace == namespace
            and sp.point.metric_name == metric_name
            and sp.point.statistic == statistic
        )

    def read_many(
        self,
        requests: Iterable[MetricRequest],
        window_start: datetime,
        window_end: datetime,
        period_seconds: int = 3600,
    ) -> Mapping[str, tuple[MetricPoint, ...]]:
        """Every requested series in one pass over each account and region.

        Grouped before reading, because the estate generates a series by walking
        hours and a read per request would walk the same window once per instance.
        `period_seconds` is accepted and not used: the estate is hourly by
        construction, which is the resolution the sizing rules need anyway.
        """
        del period_seconds

        by_slice: dict[tuple[str, str], list[MetricRequest]] = {}
        for request in requests:
            by_slice.setdefault((request.account.account_id, request.region), []).append(request)

        found: dict[str, tuple[MetricPoint, ...]] = {}
        for (account_id, region), group in by_slice.items():
            try:
                stream = tuple(
                    utilization.series_for(
                        account_id, region, start=window_start, end=window_end, at=self._at
                    )
                )
            except CollectionError:
                # The denied account and the refusing region. Omitted rather than
                # raised, so one refusal does not cost the other four hundred series
                # in the batch, and omitted rather than emptied, so the collector
                # counts them as unobserved and says so.
                continue

            for request in group:
                wanted = _resource_of(request.dimensions)
                points = tuple(
                    sp.point
                    for sp in stream
                    if sp.resource_id == wanted
                    and sp.point.namespace == request.namespace
                    and sp.point.metric_name == request.metric_name
                    and sp.point.statistic == request.statistic
                )
                if points:
                    found[request.key] = points
        return found


@dataclass(frozen=True)
class EstateCandidate:
    """One EC2 instance from the estate, as `waste_compute` needs to see it.

    A plain record rather than the collector's own `Candidate`, because
    `finops_providers` sits below `finops_ingest` and importing upward would break
    the layer contract. The caller maps this onto a `Candidate` in one expression,
    which is a smaller price than inverting the dependency.
    """

    resource_id: str
    account_id: str
    region_id: str
    observation_days: int
    monthly_cost: Decimal
    #: None where the instance is not burstable, which is not the same as a
    #: burstable one whose credits have run out.
    credit_balance: Decimal | None
    #: The type it runs as, which a rightsizing names its target against. TASK-P9-007.
    instance_type: str | None = None


#: The estate kinds P3's per instance CPU rule may look at. Scaling groups are
#: excluded, and the exclusion is the rule rather than an oversight: a group absorbs
#: demand by changing how many instances it runs, so one member's CPU says nothing
#: about whether the instance type is too large. The estate plants exactly that case
#: and expects no finding, with the reason that recommendations for a group are made
#: at group level. Sizing a fleet is FEAT-047, and it needs the group's node count
#: against its bounds rather than a percentile over one member.
SIZEABLE_KINDS = ("instance",)

#: The kinds that are groups. Named so a caller can say why they are absent rather
#: than leaving a reader to infer it from a count.
GROUP_KINDS = ("asg", "asg_eks")


def ec2_candidates(*, at: datetime = fixtures.AS_OF) -> tuple[EstateCandidate, ...]:
    """Every standalone EC2 instance in the estate, with the facts a sizing rule needs.

    Scaling groups are not here. See `SIZEABLE_KINDS`.

    `observation_days` comes from how long the instance has existed, capped at the
    window, because an instance launched a week ago has a week of history whatever
    the window says. That is what makes the one planted instance under the fourteen
    day floor actually fall under it rather than merely being described as doing so.

    `credit_balance` is read from the estate's own series rather than invented, so a
    burstable instance running on a healthy balance is one whose balance a test can
    go and look at.
    """
    window_start, window_end = shape.window(at)
    found: list[EstateCandidate] = []
    for spec in utilization.SPECS:
        if spec.kind not in SIZEABLE_KINDS:
            continue
        launched = utilization.launched_at(spec, at)
        days = (window_end - max(launched, window_start)).days
        found.append(
            EstateCandidate(
                resource_id=spec.resource_id,
                account_id=spec.account_id,
                region_id=spec.region_id,
                observation_days=max(days, 0),
                monthly_cost=monthly_cost(spec),
                credit_balance=_credits(spec, window_end, at),
                instance_type=_type_of(spec),
            )
        )
    return tuple(found)


def _type_of(spec: utilization.Spec) -> str | None:
    """The instance type the estate configured, or None where it names none."""
    value = spec.config.get("instance_type")
    return value if isinstance(value, str) else None


def _credits(spec: utilization.Spec, window_end: datetime, at: datetime) -> Decimal | None:
    """The most recent CPU credit balance, or None on a non burstable instance.

    None and nought are different answers and the sizing rule reads them
    differently: an instance with no credit concept is sized on its CPU alone, and
    one whose balance has drained is a throttled instance that looks idle.
    """
    if not spec.config.get("burstable"):
        return None
    recent = tuple(
        sp.point.value
        for sp in utilization.series_for(
            spec.account_id,
            spec.region_id,
            start=window_end - timedelta(days=1),
            end=window_end,
            at=at,
        )
        if sp.resource_id == spec.resource_id and sp.point.metric_name == "CPUCreditBalance"
    )
    return recent[-1] if recent else None
