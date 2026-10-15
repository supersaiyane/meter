"""The hours nothing runs, written as findings.

FEAT-054, TASK-P3-021. The arithmetic is in `finops_query/parking.py` and is pure; this
module reads the metrics, prices the windows and writes the rows.

**Why it is a separate collector rather than a rule inside `waste_compute`.** The window is a
different question asked of the same series, and it needs a different read. `waste_compute`
asks for an average over fourteen days and cares about the shape of the distribution;
parking needs each hour kept apart, because folding is the whole method. Two collectors also
means a parking failure does not take the rightsizing findings with it, which is constraint 5
applied at the collector level.

**What the saving is, and what it is not.** The parked hours multiplied by the hourly on
demand rate. It is never the whole monthly cost, because a stopped instance still holds its
volumes and still pays for them, and a finding that claimed the full cost would be
overstating every parking recommendation in the product by the storage share. The rationale
says which part is not saved, because a number a reader cannot reconcile with their bill is a
number they stop believing.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.waste import Source, WasteClass, confidence_of
from finops_core.ports.metrics import MetricRequest
from finops_ingest.collectors.waste_compute import FIRST_EVENT, WRITE
from finops_ingest.registry import CollectorContext, CollectorOutcome
from finops_query.parking import ParkingShape, shape_of
from finops_query.severity import severity_for, thresholds_from

COLLECTOR = "waste_parking"
SCOPE = "billing"

NAMESPACE = "AWS/EC2"
CPU = "CPUUtilization"

#: Weeks in an average month. 52 over 12, so a window of 42 hours a week is priced at the
#: hours it actually recurs for rather than at four times its weekly figure, which would
#: understate every finding by about eight percent.
WEEKS_PER_MONTH = Decimal("52") / Decimal("12")

#: The busiest reading in the hour, not the mean. An hour whose average is quiet can hold a
#: five minute spike that is the only thing the resource exists to do, and parking through it
#: is the failure this statistic prevents.
STATISTIC = "Maximum"

#: Recorded rather than silent, like `waste_compute`'s. An estate where nothing publishes
#: hourly metrics produces no parking findings, and a run reporting none found would present
#: a configuration gap as good news.
UNOBSERVED_ERROR = text(
    "INSERT INTO sync_error (error_id, tenant_id, collector, scope_key, error_type, "
    "detail, remediation, first_seen_at, last_seen_at, occurrences) "
    "VALUES (:id, :t, :c, :s, 'NoData', :d, :r, :now, :now, 1) "
    "ON CONFLICT (tenant_id, collector, scope_key, error_type) DO UPDATE SET "
    "detail = EXCLUDED.detail, last_seen_at = EXCLUDED.last_seen_at, "
    "occurrences = sync_error.occurrences + 1"
)


def _system_clock() -> datetime:
    return datetime.now(UTC)


Clock = Callable[[], datetime]


@dataclass(frozen=True)
class Parkable:
    """A resource worth asking the parking question about.

    `hourly_rate` and `storage_monthly_cost` are separate because the saving is the first and
    the honesty is the second: a reader has to be told what parking does not save.
    """

    account_id: str
    region_id: str
    resource_id: str
    hourly_rate: Decimal
    #: What continues to be charged while the resource is stopped. Volumes, mostly. Null
    #: where it is not known, which is reported as not known rather than as nothing.
    storage_monthly_cost: Decimal | None


class WasteParkingCollector:
    """Findings that say keep this and stop paying for the nights."""

    def __init__(
        self,
        metrics: Any,
        candidates: Callable[[CollectorContext], Sequence[Parkable]],
        clock: Clock = _system_clock,
    ) -> None:
        self._metrics = metrics
        # Passed in, like `waste_compute`'s, because which resources exist is an inventory
        # question and this collector's job is the fold and the arithmetic.
        self._candidates = candidates
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        settings = context.settings
        if settings is None:
            # Four of the rules here decide what gets flagged on somebody's production
            # schedule. Defaulting them would put a threshold nobody chose onto a finding
            # that asks an engineer to stop a workload, which is the same refusal
            # `waste_compute` and `cost_anomaly` make.
            raise ValueError(
                "waste_parking needs settings. Its idle threshold, its observation window "
                "and its minimum weeks are configuration, not constants."
            )

        now = self._clock()
        thresholds = thresholds_from(settings)
        candidates = self._candidates(context)
        window_end = now
        window_start = now - timedelta(days=settings.parking_observation_days)

        series = self._metrics.read_many(
            [
                MetricRequest(
                    key=candidate.resource_id,
                    account=AccountKey(provider=Provider.AWS, account_id=candidate.account_id),
                    region=candidate.region_id,
                    namespace=NAMESPACE,
                    metric_name=CPU,
                    dimensions={"InstanceId": candidate.resource_id},
                    statistic=STATISTIC,
                )
                for candidate in candidates
            ],
            window_start,
            window_end,
            # Hourly, explicitly. The adapter defaults to the same number and passing it
            # anyway is the point: the fold is only meaningful at this period, and a caller
            # that inherited a five minute or a daily default would fold nonsense without
            # anything failing.
            3600,
        )

        written = 0
        unobserved = 0
        for candidate in candidates:
            points = series.get(candidate.resource_id)
            if not points:
                # Not zero, and not quiet. A resource publishing nothing may be perfectly
                # busy, and it may already be stopped.
                unobserved += 1
                continue

            shape = shape_of(
                points,
                idle_at_or_below=settings.parking_idle_percent,
                minimum_weeks=settings.parking_minimum_weeks,
                minimum_window_hours=settings.parking_minimum_window_hours,
            )
            if shape is None:
                # Three different refusals, all of which mean there is no honest finding
                # here. `finops_query/parking.py` documents which.
                continue

            self._write(context, candidate, shape, thresholds, settings, now)
            written += 1

        if unobserved:
            context.connection.execute(
                UNOBSERVED_ERROR,
                {
                    "id": uuid4(),
                    "t": context.unit.tenant_id,
                    "c": COLLECTOR,
                    "s": SCOPE,
                    "d": (
                        f"{unobserved} resources published no hourly metrics, so no parking "
                        "window could be found for them"
                    ),
                    "r": (
                        "Check that detailed monitoring is enabled. Without an hourly series "
                        "a recurring quiet window cannot be distinguished from a resource "
                        "that is already stopped."
                    ),
                    "now": now,
                },
            )

        return CollectorOutcome(items_written=written)

    def _saving(self, candidate: Parkable, shape: ParkingShape) -> Decimal:
        """The parked hours a month at the on demand rate.

        Compute only. Storage continues while a resource is stopped, so it is excluded here
        and named in the rationale rather than quietly folded in.
        """
        return (Decimal(shape.hours_per_week) * WEEKS_PER_MONTH * candidate.hourly_rate).quantize(
            Decimal("0.0001")
        )

    def _rationale(self, candidate: Parkable, shape: ParkingShape, saving: Decimal) -> str:
        """The working, published. ADR-0007: a modelled number states how it was reached."""
        still_paid = (
            "What continues to be charged while it is stopped is not known"
            if candidate.storage_monthly_cost is None
            else (
                f"Storage of {candidate.storage_monthly_cost} USD a month continues while it "
                "is stopped and is not part of this saving"
            )
        )
        return (
            f"Quiet in every one of {shape.observed_weeks} observed weeks during "
            f"{shape.say()}. That is {shape.hours_per_week} hours a week, so stopping it "
            f"through that window would save about {saving} USD a month at "
            f"{candidate.hourly_rate} USD an hour. {still_paid}. Times are UTC, because "
            "Meter holds no timezone for this tenant."
        )

    def _write(
        self,
        context: CollectorContext,
        candidate: Parkable,
        shape: ParkingShape,
        thresholds: Any,
        settings: Any,
        now: datetime,
    ) -> None:
        saving = self._saving(candidate, shape)
        # One finding per resource. The reference is the resource rather than the window, so a
        # schedule that shifts by an hour updates the finding somebody is working on instead
        # of opening a second one beside it and leaving the first to look abandoned.
        reference = f"parking:{candidate.resource_id}"
        context.connection.execute(
            WRITE,
            {
                "id": uuid4(),
                "tenant": context.unit.tenant_id,
                "account": candidate.account_id,
                "source": Source.METER.value,
                "reference": reference,
                "waste_class": WasteClass.PARKABLE_WINDOW.value,
                "resource": candidate.resource_id,
                "region": candidate.region_id,
                "saving": saving,
                "confidence": confidence_of(settings.parking_observation_days).value,
                "severity": severity_for(saving, thresholds),
                "days": settings.parking_observation_days,
                "rationale": self._rationale(candidate, shape, saving),
                "now": now,
                # Parking changes when an instance runs, not what it runs as: no target.
                "current": None,
                "target_type": None,
                "target": None,
                "version": None,
                "added": None,
                "iops": None,
                "mibps": None,
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
