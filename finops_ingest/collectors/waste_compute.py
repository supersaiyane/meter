"""What AWS is blind to, from the metrics it publishes.

Reads one batch of series for the whole estate, asks `finops_query.waste` about
each, and writes the ones worth a row into the same `recommendation` table the AWS
findings land in.

Three decisions.

**Idle is asked before oversized.** An instance doing nothing is idle, and the
action is to turn it off. The rightsizing arithmetic will also happily report it,
as an instance that could be very much smaller, and that recommendation is true
and useless: nobody shrinks a machine they could delete. Asking in the other order
produces a screen full of rightsizings for dead instances.

**An absent series is skipped, loudly.** The port returns nothing for a resource
that published no metrics, and that is not a resource at zero utilization. The
count of skipped instances is returned so the run ledger records it, because an
estate where half the instances publish nothing is a configuration problem rather
than an estate with no waste.

**Auto Scaling groups are recommended once, not once per instance.** FEAT-026's
binding rule. Twenty identical instances behind one group produce one
recommendation naming the group, because twenty rows telling somebody the same
thing is how a screen gets ignored.

**A rightsizing names its target and quotes a price difference**, TASK-P9-007, P9 spec
sections 5.5 and 5.6. Where the instance's type is known and the catalog holds its
Region, `finops_query.targets` chooses the cheapest type that fits from the types
offered there, and the saving is the two prices' difference for the hours the
instance runs, scaled to what the bill shows, both modelled, with the price version.
No cheaper type that fits is a refusal with the reason, never a recommendation. Where
the type or the catalog is missing, the old estimate stands, the unused share of the
bill, and its rationale says why no target is named. The batch reads network and EBS
bytes beside CPU and memory so the fit can hold a target to its baselines.

**An instance under pressure is an Upsize**, TASK-P9-008, spec section 5.7. Where the
shrink was refused and CPU or memory p95 is above 90 percent, or network sits at its
baseline, the rule names the cheapest larger type that fits, and the recommendation is
`UPSIZE_INSTANCE` with what it adds to the bill a month and a saving of nought, so no
total of savings falls because of it. Its severity is read from that added cost, the
money at stake. Without a type or a catalog, or with no larger type that fits, the
refusal says the instance is under pressure and why nothing could be named.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.metrics import MetricPoint
from finops_core.domain.observation import MINIMUM_HISTORY
from finops_core.domain.waste import Source, WasteClass, confidence_of
from finops_core.ports.metrics import MetricRequest
from finops_ingest.collectors.catalog_reads import LINUX, latest_version, offers
from finops_ingest.registry import CollectorContext, CollectorOutcome
from finops_query.severity import severity_for, thresholds_from
from finops_query.targets import (
    Demand,
    Target,
    TypeOffer,
    added_cost,
    choose,
    grow,
    hours_per_month,
    pressure,
    saving,
)
from finops_query.waste import FLOOR_USD, Estimate, idle, percentile, rightsize_cpu

COLLECTOR = "waste_compute"
SCOPE = "billing"

NAMESPACE = "AWS/EC2"
CPU = "CPUUtilization"

#: Memory is not an EC2 metric. The CloudWatch agent publishes it under its own
#: namespace, so an instance without the agent has no memory series at all, which
#: is unobserved rather than fine. FEAT-026.
AGENT_NAMESPACE = "CWAgent"
MEMORY = "mem_used_percent"

#: How a memory request is keyed, so it cannot collide with the CPU request for
#: the same instance in a batch the port returns as one mapping.
MEMORY_KEY = "memory:"

#: Bytes an hour, in and out, which the fit holds against a target's baselines. TASK-P9-007.
NETWORK = ("NetworkIn", "NetworkOut")
EBS = ("EBSReadBytes", "EBSWriteBytes")
NETWORK_KEY = "network:"
EBS_KEY = "ebs:"
SECONDS_PER_HOUR = Decimal(3600)
GIGABIT = Decimal(10) ** 9
MEGABIT = Decimal(10) ** 6

Clock = Callable[[], datetime]


def _system_clock() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Candidate:
    """One thing the collector was asked to look at."""

    resource_id: str
    account_id: str
    region_id: str
    observation_days: int
    monthly_cost: Decimal
    credit_balance: Decimal | None = None
    #: Where the instance belongs to a group, the group is what gets recommended.
    scaling_group: str | None = None
    #: The type it runs as, which the target is chosen against. None where the
    #: inventory does not say, and then no target is named. TASK-P9-007.
    instance_type: str | None = None
    #: The operating system its prices are quoted for, as the price list words it.
    operating_system: str = LINUX


WRITE = text(
    "INSERT INTO recommendation (recommendation_id, tenant_id, sub_account_id, source, "
    "source_reference, waste_class, resource_id, region_id, estimated_monthly_saving, "
    "confidence, severity, observation_days, lifecycle, owner, ticket_reference, "
    "rationale, as_of, collected_at, current_sku_price_id, target_instance_type, "
    "target_sku_price_id, price_version, added_monthly_cost) "
    "VALUES (:id, :tenant, :account, :source, :reference, :waste_class, :resource, :region, "
    ":saving, :confidence, :severity, :days, 'OPEN', NULL, NULL, :rationale, :now, :now, "
    ":current, :target_type, :target, :version, :added) "
    "ON CONFLICT (tenant_id, source, source_reference) DO UPDATE SET "
    "estimated_monthly_saving = EXCLUDED.estimated_monthly_saving, "
    "current_sku_price_id = EXCLUDED.current_sku_price_id, "
    "target_instance_type = EXCLUDED.target_instance_type, "
    "target_sku_price_id = EXCLUDED.target_sku_price_id, "
    "price_version = EXCLUDED.price_version, added_monthly_cost = EXCLUDED.added_monthly_cost, "
    "waste_class = EXCLUDED.waste_class, confidence = EXCLUDED.confidence, "
    "severity = EXCLUDED.severity, observation_days = EXCLUDED.observation_days, "
    "rationale = EXCLUDED.rationale, as_of = EXCLUDED.as_of, "
    "collected_at = EXCLUDED.collected_at, "
    "lifecycle = CASE WHEN recommendation.lifecycle IN ('OPEN', 'DISMISSED') "
    "THEN 'OPEN' ELSE recommendation.lifecycle END"
)

FIRST_EVENT = text(
    "INSERT INTO recommendation_event (event_id, recommendation_id, tenant_id, "
    "from_lifecycle, to_lifecycle, actor, reason, occurred_at, as_of, collected_at) "
    "SELECT :id, r.recommendation_id, :tenant, NULL, 'OPEN', :actor, NULL, :now, :now, :now "
    "FROM recommendation r "
    "WHERE r.tenant_id = :tenant AND r.source = :source AND r.source_reference = :reference "
    "AND NOT EXISTS ("
    "  SELECT 1 FROM recommendation_event e WHERE e.recommendation_id = r.recommendation_id"
    ")"
)


#: One row per resource per rule, overwritten each run. FEAT-062. A refusal is a statement
#: about the current measurement, so last week's p99 is not a fact about today and the row is
#: replaced rather than accumulated.
WRITE_REFUSAL = text(
    "INSERT INTO sizing_refusal (refusal_id, tenant_id, ingest_run_id, sub_account_id, "
    "region_id, resource_id, waste_class, reason, observation_days, as_of, collected_at) "
    "VALUES (:id, :tenant, :run, :account, :region, :resource, :waste_class, :reason, "
    ":days, :now, :now) "
    "ON CONFLICT (tenant_id, resource_id, waste_class) DO UPDATE SET "
    "ingest_run_id = EXCLUDED.ingest_run_id, reason = EXCLUDED.reason, "
    "observation_days = EXCLUDED.observation_days, as_of = EXCLUDED.as_of, "
    "collected_at = EXCLUDED.collected_at"
)

#: Recorded rather than silent. An estate where half the instances publish nothing
#: is a configuration problem, and a run reporting "no waste found" would hide it.
#: Upserted on the scope, like every other sync error, so a persistent gap shows as
#: one row with a rising count rather than one row per run.
UNOBSERVED_ERROR = text(
    "INSERT INTO sync_error (error_id, tenant_id, collector, scope_key, error_type, "
    "detail, remediation, first_seen_at, last_seen_at, occurrences) "
    "VALUES (:id, :t, :c, :s, 'NoData', :d, :r, :now, :now, 1) "
    "ON CONFLICT (tenant_id, collector, scope_key, error_type) DO UPDATE SET "
    "detail = EXCLUDED.detail, last_seen_at = EXCLUDED.last_seen_at, "
    "occurrences = sync_error.occurrences + 1"
)


class WasteComputeCollector:
    """Our own findings, from metrics the provider publishes."""

    def __init__(
        self,
        metrics: Any,
        candidates: Callable[[CollectorContext], Sequence[Candidate]],
        clock: Clock = _system_clock,
    ) -> None:
        self._metrics = metrics
        # Passed in rather than discovered here, because which resources exist is
        # an inventory question and this collector's job is the arithmetic. P4
        # will supply a real one.
        self._candidates = candidates
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        if context.settings is None:
            # Severity comes from the money, per ADR-0016, and the boundaries are
            # settings. Defaulting them would put a severity nobody chose onto a
            # screen, which is the same refusal `cost_anomaly` makes.
            raise ValueError(
                "waste_compute needs settings. Its severity boundaries are "
                "configuration, not constants."
            )

        now = self._clock()
        thresholds = thresholds_from(context.settings)
        candidates = self._candidates(context)
        window_end = now
        window_start = now - timedelta(
            days=max((c.observation_days for c in candidates), default=0)
        )

        # Two series per instance in one batch. Memory is asked for because a CPU
        # only judgement cannot tell an oversized instance from a memory bound one,
        # and an instance whose work is memory work has a quiet CPU for a reason.
        # Batched rather than fetched per instance, because GetMetricData is charged
        # per metric requested and a second round trip would double the requests
        # without reducing the metrics.
        series = self._metrics.read_many(
            [
                MetricRequest(
                    key=candidate.resource_id,
                    account=AccountKey(provider=Provider.AWS, account_id=candidate.account_id),
                    region=candidate.region_id,
                    namespace=NAMESPACE,
                    metric_name=CPU,
                    dimensions={"InstanceId": candidate.resource_id},
                    statistic="Average",
                )
                for candidate in candidates
            ]
            + [
                MetricRequest(
                    key=f"{MEMORY_KEY}{candidate.resource_id}",
                    account=AccountKey(provider=Provider.AWS, account_id=candidate.account_id),
                    region=candidate.region_id,
                    namespace=AGENT_NAMESPACE,
                    metric_name=MEMORY,
                    dimensions={"InstanceId": candidate.resource_id},
                    statistic="Maximum",
                )
                for candidate in candidates
            ]
            + [
                MetricRequest(
                    key=f"{prefix}{metric}:{candidate.resource_id}",
                    account=AccountKey(provider=Provider.AWS, account_id=candidate.account_id),
                    region=candidate.region_id,
                    namespace=NAMESPACE,
                    metric_name=metric,
                    dimensions={"InstanceId": candidate.resource_id},
                    statistic="Sum",
                )
                for candidate in candidates
                for prefix, metrics in ((NETWORK_KEY, NETWORK), (EBS_KEY, EBS))
                for metric in metrics
            ],
            window_start,
            window_end,
        )

        written = 0
        unobserved = 0
        seen_groups: set[str] = set()

        for candidate in candidates:
            points = series.get(candidate.resource_id)
            if points is None:
                # Not zero. An instance publishing nothing may be perfectly busy.
                unobserved += 1
                continue

            # One recommendation per Auto Scaling group, per FEAT-026. Twenty rows
            # saying the same thing is how a screen gets ignored.
            if candidate.scaling_group is not None:
                if candidate.scaling_group in seen_groups:
                    continue
                seen_groups.add(candidate.scaling_group)

            values = [point.value for point in points]
            # Absent, not zero. An instance with no agent has no memory series, and
            # the judgement says so rather than assuming there is room.
            memory = series.get(f"{MEMORY_KEY}{candidate.resource_id}")
            peak = max((point.value for point in memory), default=None) if memory else None
            estimate = self._judge(candidate, values, peak)
            if estimate is None:
                continue
            prices: dict[str, str | None] | None = None
            if (
                estimate.is_worth_acting_on
                and estimate.waste_class is WasteClass.RIGHTSIZE_INSTANCE
            ):
                demand = Demand(
                    cpu_p99_percent=percentile(values, 99),
                    memory_peak_percent=peak,
                    network_p99_gbps=_p99_rate(series, NETWORK_KEY, NETWORK, candidate, GIGABIT),
                    ebs_p99_mbps=_p99_rate(series, EBS_KEY, EBS, candidate, MEGABIT),
                )
                estimate, prices = self._priced(context, candidate, estimate, demand, len(values))
            elif _may_grow(candidate, estimate):
                demand = Demand(
                    cpu_p99_percent=percentile(values, 99),
                    memory_peak_percent=peak,
                    network_p99_gbps=_p99_rate(series, NETWORK_KEY, NETWORK, candidate, GIGABIT),
                    ebs_p99_mbps=_p99_rate(series, EBS_KEY, EBS, candidate, MEGABIT),
                    cpu_p95_percent=percentile(values, 95),
                    memory_p95_percent=(
                        percentile([point.value for point in memory], 95) if memory else None
                    ),
                )
                estimate, prices = self._grown(context, candidate, estimate, demand, len(values))
            if not estimate.is_worth_acting_on:
                # Examined and cleared. Recorded so a reader can see the rule looked, and
                # never as a recommendation: it has no saving, and a zero in a list ranked by
                # money reads as the least valuable action rather than the absence of one.
                self._write_refusal(context, candidate, estimate, now)
                continue
            self._write(context, candidate, estimate, thresholds, now, prices)
            written += 1

        if unobserved:
            # Recorded rather than silent. An estate where half the instances
            # publish nothing is a configuration problem, and a run that reported
            # "no waste found" would hide it.
            context.connection.execute(
                UNOBSERVED_ERROR,
                {
                    "id": uuid4(),
                    "t": context.unit.tenant_id,
                    "c": COLLECTOR,
                    "s": SCOPE,
                    "d": f"{unobserved} resources published no metrics and were not judged",
                    "r": (
                        "Check that detailed monitoring is enabled for these resources. "
                        "Until it is they are neither judged nor reported as wasteful."
                    ),
                    "now": now,
                },
            )

        # Recommendations only. A refusal is not an item this collector produced for the
        # queue, and counting it here would inflate a number a reader takes as findings.
        return CollectorOutcome(items_written=written)

    def _judge(
        self,
        candidate: Candidate,
        values: list[Decimal],
        memory_peak_percent: Decimal | None,
    ) -> Estimate | None:
        """Idle first, then oversized.

        An instance doing nothing is idle and the action is to turn it off. The
        rightsizing arithmetic would also report it, truthfully and uselessly:
        nobody shrinks a machine they could delete.

        The idle question does not consult memory, deliberately. An instance nobody
        is using is worth turning off whatever its memory footprint was, and a
        memory bound instance is not idle in the first place: its CPU is quiet and
        its p95 is not.
        """
        gone = idle(
            utilization_percent=values,
            observation_days=candidate.observation_days,
            monthly_cost=candidate.monthly_cost,
        )
        if gone.is_worth_acting_on:
            return gone

        smaller = rightsize_cpu(
            utilization_percent=values,
            observation_days=candidate.observation_days,
            monthly_cost=candidate.monthly_cost,
            credit_balance=candidate.credit_balance,
            memory_peak_percent=memory_peak_percent,
        )
        # The refusal is returned rather than dropped. FEAT-062: a resource examined and
        # cleared is a different fact from one nobody looked at, and this line used to render
        # them identically by producing nothing in both cases. `Estimate` was always shaped for
        # this, and its docstring says so.
        return smaller

    def _priced(
        self,
        context: CollectorContext,
        candidate: Candidate,
        estimate: Estimate,
        demand: Demand,
        points: int,
    ) -> tuple[Estimate, dict[str, str | None] | None]:
        """The estimate with a named target and a price difference, or why there is none."""
        if candidate.instance_type is None:
            return _unnamed(estimate, "the instance's type is not known"), None
        tenant, region = context.unit.tenant_id, candidate.region_id
        version = latest_version(context.connection, tenant, region)
        if version is None:
            return _unnamed(estimate, f"the catalog holds no EC2 prices for {region} yet"), None
        offered = offers(context.connection, tenant, region, version, candidate.operating_system)
        current = offered.get(candidate.instance_type)
        if current is None:
            reason = f"the catalog does not describe {candidate.instance_type} in {region}"
            return _unnamed(estimate, reason), None
        chosen = choose(current, list(offered.values()), demand)
        if isinstance(chosen, str):
            return replace(
                estimate,
                is_worth_acting_on=False,
                monthly_saving=Decimal(0),
                reason=f"{estimate.reason}. No target: {chosen}",
            ), None
        return self._quoted(candidate, estimate, current, chosen, version, points)

    def _quoted(
        self,
        candidate: Candidate,
        estimate: Estimate,
        current: TypeOffer,
        chosen: Target,
        version: str,
        points: int,
    ) -> tuple[Estimate, dict[str, str | None] | None]:
        target, current_hourly = chosen.offer, current.hourly_price
        if current_hourly is None or target.hourly_price is None:
            return _unnamed(estimate, "the catalog holds no price for the pair"), None
        money = saving(
            current_hourly=current_hourly,
            target_hourly=target.hourly_price,
            hours=hours_per_month(points, candidate.observation_days),
            paid_monthly=candidate.monthly_cost,
        )
        sentence = (
            f"{estimate.reason}. Move {candidate.instance_type} to {target.instance_type}: "
            f"{current_hourly} to {target.hourly_price} USD an hour at list, for "
            f"{money.hours_per_month:.0f} hours a month, saves {money.at_list} USD a month at "
            f"list and {money.as_paid} as the bill pays (modelled), price list version {version}"
            + "".join(f". {note[0].upper()}{note[1:]}" for note in chosen.notes)
        )
        if money.as_paid < FLOOR_USD:
            return replace(
                estimate,
                is_worth_acting_on=False,
                monthly_saving=Decimal(0),
                reason=f"{sentence}. {money.as_paid} is under the {FLOOR_USD} floor",
            ), None
        return replace(estimate, monthly_saving=money.as_paid, reason=sentence), {
            "current": current.sku_price_id,
            "target_type": target.instance_type,
            "target": target.sku_price_id,
            "version": version,
        }

    def _grown(
        self,
        context: CollectorContext,
        candidate: Candidate,
        refusal: Estimate,
        demand: Demand,
        points: int,
    ) -> tuple[Estimate, dict[str, str | None] | None]:
        """An Upsize for an instance under pressure, or the refusal it already was."""
        tenant, region = context.unit.tenant_id, candidate.region_id
        version = latest_version(context.connection, tenant, region)
        offered = (
            offers(context.connection, tenant, region, version, candidate.operating_system)
            if version is not None
            else {}
        )
        current = offered.get(candidate.instance_type or "")
        short = pressure(current, demand) if current is not None else _short(demand)
        if short is None:
            return refusal, None
        upsize = WasteClass.UPSIZE_INSTANCE
        if current is None or version is None:
            why = (
                "the instance's type is not known"
                if candidate.instance_type is None
                else f"the catalog holds no description or price of {candidate.instance_type} "
                f"in {region}"
            )
            return _refused(
                upsize, f"Under pressure, {short}, and no larger type is named because {why}"
            ), None
        chosen = grow(current, list(offered.values()), demand)
        if isinstance(chosen, str):
            return _refused(upsize, f"Under pressure, {short}, and {chosen}"), None
        target = chosen.offer
        if current.hourly_price is None or target.hourly_price is None:
            return _refused(upsize, f"Under pressure, {short}, and the pair has no price"), None
        cost = added_cost(
            current_hourly=current.hourly_price,
            target_hourly=target.hourly_price,
            hours=hours_per_month(points, candidate.observation_days),
            paid_monthly=candidate.monthly_cost,
        )
        sentence = (
            f"Under pressure, {short}. Grow {candidate.instance_type} to "
            f"{target.instance_type}: {current.hourly_price} to {target.hourly_price} USD an "
            f"hour at list, for {cost.hours_per_month:.0f} hours a month, adds {cost.at_list} USD "
            f"a month at list and {cost.as_paid} as the bill pays (modelled), price list version "
            f"{version}" + "".join(f". {note[0].upper()}{note[1:]}" for note in chosen.notes)
        )
        if cost.as_paid <= 0:
            return _refused(upsize, f"{sentence}. It costs no more, so it is not an Upsize"), None
        return Estimate(
            is_worth_acting_on=True,
            waste_class=upsize,
            monthly_saving=Decimal(0),
            reason=sentence,
            added_monthly_cost=cost.as_paid,
        ), {
            "current": current.sku_price_id,
            "target_type": target.instance_type,
            "target": target.sku_price_id,
            "version": version,
        }

    def _write_refusal(
        self,
        context: CollectorContext,
        candidate: Candidate,
        estimate: Estimate,
        now: datetime,
    ) -> None:
        """Record that a rule looked at this and declined, with the sentence that decided it.

        Keyed on the resource and the rule rather than on the run, so a resource declined for
        the same reason every six hours has one row rather than a history nobody asked for. The
        reason is overwritten on each run on purpose: a refusal is a statement about the
        current measurement, and last week's p99 is not a fact about today.
        """
        target = candidate.scaling_group or candidate.resource_id
        context.connection.execute(
            WRITE_REFUSAL,
            {
                "id": uuid4(),
                "tenant": context.unit.tenant_id,
                "run": context.run_id,
                "account": candidate.account_id,
                "region": candidate.region_id,
                "resource": target,
                "waste_class": estimate.waste_class.value,
                "reason": estimate.reason,
                "days": candidate.observation_days,
                "now": now,
            },
        )

    def _write(
        self,
        context: CollectorContext,
        candidate: Candidate,
        estimate: Estimate,
        thresholds: Any,
        now: datetime,
        prices: Mapping[str, str | None] | None = None,
    ) -> None:
        target = candidate.scaling_group or candidate.resource_id
        reference = f"meter:{target}:{estimate.waste_class.value}"
        context.connection.execute(
            WRITE,
            {
                "id": uuid4(),
                "tenant": context.unit.tenant_id,
                "account": candidate.account_id,
                "source": Source.METER.value,
                "reference": reference,
                "waste_class": estimate.waste_class.value,
                "resource": target,
                "region": candidate.region_id,
                "saving": estimate.monthly_saving,
                "confidence": confidence_of(candidate.observation_days).value,
                # An Upsize's money at stake is what it adds; everything else's is its saving.
                "severity": severity_for(
                    estimate.added_monthly_cost or estimate.monthly_saving, thresholds
                ),
                "days": candidate.observation_days,
                "rationale": estimate.reason,
                "now": now,
                # Every run says what it chose, so a target that stopped fitting is cleared.
                "current": (prices or {}).get("current"),
                "target_type": (prices or {}).get("target_type"),
                "target": (prices or {}).get("target"),
                "version": (prices or {}).get("version"),
                "added": estimate.added_monthly_cost,
            },
        )
        context.connection.execute(
            FIRST_EVENT,
            {
                "id": uuid4(),
                "tenant": context.unit.tenant_id,
                "source": Source.METER.value,
                "reference": reference,
                "actor": f"collector:{COLLECTOR}",
                "now": now,
            },
        )


def _unnamed(estimate: Estimate, why: str) -> Estimate:
    """The estimate as it stood, saying why it names no target."""
    return replace(
        estimate,
        reason=f"{estimate.reason}. No target is named because {why}, so the saving is the "
        "unused share of the bill rather than a price difference",
    )


def _p99_rate(
    series: Mapping[str, Sequence[MetricPoint]],
    prefix: str,
    metrics: Sequence[str],
    candidate: Candidate,
    unit: Decimal,
) -> Decimal | None:
    """The 99th percentile of bits a second across `metrics` together, or None if unobserved.

    Each point is the bytes moved in its hour; in and out, or read and write, are summed per
    hour before the percentile, because a baseline bounds the two together.
    """
    streams = [series.get(f"{prefix}{metric}:{candidate.resource_id}") for metric in metrics]
    if any(stream is None for stream in streams):
        return None
    hourly: dict[datetime, Decimal] = {}
    for stream in streams:
        for point in stream or ():
            hourly[point.at] = hourly.get(point.at, Decimal(0)) + point.value
    if not hourly:
        return None
    return percentile([value * 8 / SECONDS_PER_HOUR / unit for value in hourly.values()], 99)


def _may_grow(candidate: Candidate, estimate: Estimate) -> bool:
    """A refused shrink worth asking about growth: old enough, and not a burstable at ease."""
    return (
        not estimate.is_worth_acting_on
        and estimate.waste_class is WasteClass.RIGHTSIZE_INSTANCE
        and candidate.observation_days >= MINIMUM_HISTORY
        and candidate.credit_balance is None
    )


def _short(demand: Demand) -> str | None:
    """Pressure judged without the type's baselines, which the catalog could not supply."""
    unknown = TypeOffer(
        instance_type="",
        vcpus=1,
        memory_mib=1,
        architectures=("x86_64",),
        burstable=False,
        hourly_price=None,
    )
    return pressure(unknown, demand)


def _refused(waste_class: WasteClass, reason: str) -> Estimate:
    return Estimate(
        is_worth_acting_on=False,
        waste_class=waste_class,
        monthly_saving=Decimal(0),
        reason=reason,
    )
