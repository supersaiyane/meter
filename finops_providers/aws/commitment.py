"""Commitment utilization and coverage, through Cost Explorer.

**Nothing in this file has ever made a call.** ISS-122. It is written against the
AWS documentation and the shapes botocore declares, it is unit tested against
recorded responses, and it is held to the same contract as the fake. None of that
is the same thing as having run.

Three things carry this file, and the third is the one to read.

**Four calls, not one.** Savings Plans and reservations are different APIs, and
utilization and coverage are different calls within each. That is not an
inconvenience to paper over: it is the shape of the truth. Utilization is per
commitment and coverage is per dimension, because a dollar of covered spend cannot
be attributed to one of several overlapping plans. See `CommitmentCoverage`.

**Cost Explorer charges per request.** Every call here is money, which is why the
cadence is a row in `collector_schedule` with its cost written next to it, per
ADR-0012, and why a window is read once rather than once per commitment.

**Savings Plans report money. Reservations report hours.** This is the part most
likely to be wrong, and it is wrong in a way no amount of care here can settle.
`SavingsPlansUtilization` gives `TotalCommitment` and `UsedCommitment` in the
billing currency, so those rows are measured. `ReservationAggregates` gives
`PurchasedHours`, `TotalActualHours` and `TotalAmortizedFee`, so the money a
reservation consumed is **derived**: the amortized fee scaled by the fraction of
purchased hours actually used. That derivation is stated here rather than hidden,
because it is the figure a reader would otherwise reconcile against an invoice and
fail to match. Reservation coverage has the same problem and is the weakest mapping
in the file.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from finops_core.config import Settings
from finops_core.domain.cost import (
    ACTIVE,
    BY_SERVICE,
    EXPIRED,
    QUEUED,
    CommitmentCoverage,
    CommitmentDay,
    CommitmentUse,
)
from finops_core.errors import NoData, SchemaDrift
from finops_providers.aws.client import botocore_config, translate

COLLECTOR = "commitment"
SCOPE = "billing"

SAVINGS_PLAN = "SavingsPlan"
RESERVED_INSTANCE = "ReservedInstance"

#: Cost Explorer has one endpoint for the whole commercial partition and answers
#: nowhere else, so this is not a region anybody configures and taking it from
#: `settings.regions` would send the call to an endpoint that does not exist. The
#: limit worth knowing is that aws-cn and GovCloud have their own endpoints, so a
#: deployment in either needs `partition_for` here. ISS-122 covers proving any of
#: this against a real account.
COST_EXPLORER_REGION = "us-east-1"  # allow-hardcoded: Cost Explorer is a single global endpoint

ZERO = Decimal("0")

#: Cost Explorer's own word for one row per day. A run reads a month of days in one request
#: per figure rather than one request per day, which is what makes a daily read affordable.
DAILY = "DAILY"

#: The four figures a day carries, each summed across whatever the response reports for it.
_DAY_FIGURES = ("committed", "used", "eligible_spend", "covered_spend")


def _money(raw: Any, field: str) -> Decimal:
    """A money string from Cost Explorer, or a typed refusal.

    A missing or unparseable amount is `SchemaDrift` rather than a zero.
    Constraint 5: a failure is never rendered as the number zero, and a commitment
    silently reported as costing nothing is the most expensive possible instance of
    that mistake.
    """
    if raw is None:
        raise SchemaDrift(
            scope_key=SCOPE,
            collector=COLLECTOR,
            detail=f"Cost Explorer returned no {field}",
        )
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError) as error:
        raise SchemaDrift(
            scope_key=SCOPE,
            collector=COLLECTOR,
            detail=f"{field} was not a number: {raw!r}",
        ) from error


def _a_date(raw: Any, fallback: date) -> date:
    """A date out of a Cost Explorer attribute, or the fallback.

    The attributes map is documented as free form and its keys have changed, so a
    missing one is not schema drift: the window is a usable answer, and refusing
    here would drop a commitment that is otherwise complete.
    """
    if raw is None:
        return fallback
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return fallback


def _the_day(span: Any) -> date:
    """The day a daily span describes, or a typed refusal.

    Unlike a plan's attributes, the period here is the key a figure is filed under, so a
    missing or unreadable one is schema drift rather than a fallback: falling back would file
    one day's money under another day, which no reader could ever find.
    """
    raw = (span.get("TimePeriod") or {}).get("Start")
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError as error:
        raise SchemaDrift(
            scope_key=SCOPE,
            collector=COLLECTOR,
            detail=f"a daily span had no readable start: {raw!r}",
        ) from error


def _reservation_money(committed: Decimal, actual: Decimal, purchased: Decimal) -> Decimal:
    """What the used reservation hours cost, which Cost Explorer does not report.

    **Derived, not measured.** The API reports reservation use in hours and its fee
    in money, and gives no figure for the money the used hours represent. Scaling
    the fee by the used fraction is the only reading available, and it assumes every
    purchased hour cost the same, which holds for one reservation and not for a
    group of them. A screen showing this figure is showing a model.

    No purchased hours means no obligation inside the window, which is a queued
    reservation rather than a wholly wasted one, so the answer is zero consumed
    against zero committed and not zero consumed against a fee.
    """
    if purchased == ZERO:
        return ZERO
    return committed * actual / purchased


def _status(term_start: date, term_end: date, window_end: date) -> str:
    """Where the term sits relative to the window being reported.

    Derived from the dates rather than read from a field, because the utilization
    response describes a window and not a lifecycle. A plan that ended inside the
    window has to be reported as expired rather than dropped, since the coverage
    gap its expiry leaves is the finding.
    """
    if term_start >= window_end:
        return QUEUED
    if term_end <= window_end:
        return EXPIRED
    return ACTIVE


class CostExplorerCommitmentReport:
    """`CommitmentReport` over Cost Explorer. Unproved, ISS-122."""

    def __init__(
        self,
        settings: Settings,
        tenant_id: UUID,
        *,
        client_factory: Callable[[], Any] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings = settings
        self._tenant_id = tenant_id
        self._config = botocore_config(settings)
        self._factory = client_factory or self._default_client
        self._clock = clock or (lambda: datetime.now(UTC))

    def _default_client(self) -> Any:
        return boto3.client("ce", region_name=COST_EXPLORER_REGION, config=self._config)

    def _call(self, name: str, **kwargs: Any) -> Any:
        try:
            return getattr(self._factory(), name)(**kwargs)
        except (BotoCoreError, ClientError) as error:
            raise translate(error, scope_key=SCOPE, collector=COLLECTOR) from error

    @staticmethod
    def _period(window_start: date, window_end: date) -> dict[str, str]:
        # Cost Explorer's End is exclusive, which matches every period in this
        # schema, so no adjustment is needed and none is made. A reader checking
        # this against the documentation should find nothing clever here.
        return {"Start": window_start.isoformat(), "End": window_end.isoformat()}

    def _timestamps(self, window_end: date) -> tuple[datetime, datetime]:
        """`as_of` is the end of the window, `collected_at` is now.

        Constraint 10. The figures were true across the window and its end is the
        latest moment they describe. Conflating that with the moment of the call
        would make a month old window look fresh.
        """
        return (
            datetime(window_end.year, window_end.month, window_end.day, tzinfo=UTC),
            self._clock(),
        )

    # -- the port ----------------------------------------------------------

    def utilization(self, window_start: date, window_end: date) -> Iterable[CommitmentUse]:
        found = (
            *self._savings_plan_use(window_start, window_end),
            *self._reservation_use(window_start, window_end),
        )
        if not found:
            raise NoData(
                scope_key=SCOPE,
                collector=COLLECTOR,
                detail=f"this payer holds no commitments between {window_start} and {window_end}",
            )
        return found

    def coverage(self, window_start: date, window_end: date) -> Iterable[CommitmentCoverage]:
        found = (
            *self._savings_plan_coverage(window_start, window_end),
            *self._reservation_coverage(window_start, window_end),
        )
        if not found:
            raise NoData(
                scope_key=SCOPE,
                collector=COLLECTOR,
                detail=(
                    f"nothing between {window_start} and {window_end} was eligible for a commitment"
                ),
            )
        return found

    # -- Savings Plans, which report in money ------------------------------

    def _savings_plan_use(self, window_start: date, window_end: date) -> tuple[CommitmentUse, ...]:
        response = self._call(
            "get_savings_plans_utilization_details",
            TimePeriod=self._period(window_start, window_end),
        )
        as_of, collected_at = self._timestamps(window_end)
        rows: list[CommitmentUse] = []

        for detail in response.get("SavingsPlansUtilizationDetails", []):
            found = detail.get("Utilization", {})
            committed = _money(found.get("TotalCommitment"), "TotalCommitment")
            used = _money(found.get("UsedCommitment"), "UsedCommitment")
            attributes = detail.get("Attributes", {})
            term_start = _a_date(attributes.get("startDateTime"), window_start)
            term_end = _a_date(attributes.get("endDateTime"), window_end)
            rows.append(
                CommitmentUse(
                    as_of=as_of,
                    collected_at=collected_at,
                    tenant_id=self._tenant_id,
                    commitment_id=str(detail.get("SavingsPlanArn", "")),
                    commitment_type=SAVINGS_PLAN,
                    status=_status(term_start, term_end, window_end),
                    term_start=term_start,
                    term_end=max(term_end, term_start + timedelta(days=1)),
                    window_start=window_start,
                    window_end=window_end,
                    committed=committed,
                    used=used,
                    # Not `UnusedCommitment`, although the response carries it. The
                    # database constrains `wasted` to be the difference, and taking
                    # a third number from the provider is how a row that violates
                    # that constraint gets built.
                    wasted=committed - used,
                )
            )
        return tuple(rows)

    def _savings_plan_coverage(
        self, window_start: date, window_end: date
    ) -> tuple[CommitmentCoverage, ...]:
        response = self._call(
            "get_savings_plans_coverage",
            TimePeriod=self._period(window_start, window_end),
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )
        as_of, collected_at = self._timestamps(window_end)
        rows: list[CommitmentCoverage] = []

        for slice_ in response.get("SavingsPlansCoverages", []):
            found = slice_.get("Coverage", {})
            rows.append(
                CommitmentCoverage(
                    as_of=as_of,
                    collected_at=collected_at,
                    tenant_id=self._tenant_id,
                    commitment_type=SAVINGS_PLAN,
                    dimension=BY_SERVICE,
                    dimension_value=str(slice_.get("Attributes", {}).get("SERVICE", "")),
                    window_start=window_start,
                    window_end=window_end,
                    # `TotalCost` is what a commitment of this kind could have
                    # covered. `OnDemandCost` is the part that was not covered, so
                    # using it as the denominator would report coverage as a
                    # fraction of the failure.
                    eligible_spend=_money(found.get("TotalCost"), "TotalCost"),
                    covered_spend=_money(
                        found.get("SpendCoveredBySavingsPlans"),
                        "SpendCoveredBySavingsPlans",
                    ),
                )
            )
        return tuple(rows)

    # -- reservations, which report in hours -------------------------------

    def _reservation_use(self, window_start: date, window_end: date) -> tuple[CommitmentUse, ...]:
        response = self._call(
            "get_reservation_utilization",
            TimePeriod=self._period(window_start, window_end),
            GroupBy=[{"Type": "DIMENSION", "Key": "SUBSCRIPTION_ID"}],
        )
        as_of, collected_at = self._timestamps(window_end)
        rows: list[CommitmentUse] = []

        for span in response.get("UtilizationsByTime", []):
            for group in span.get("Groups", []):
                found = group.get("Utilization", {})
                purchased = _money(found.get("PurchasedHours"), "PurchasedHours")
                actual = _money(found.get("TotalActualHours"), "TotalActualHours")
                committed = _money(found.get("TotalAmortizedFee"), "TotalAmortizedFee")

                used = _reservation_money(committed, actual, purchased)

                rows.append(
                    CommitmentUse(
                        as_of=as_of,
                        collected_at=collected_at,
                        tenant_id=self._tenant_id,
                        commitment_id=str(group.get("Key", "")),
                        commitment_type=RESERVED_INSTANCE,
                        status=ACTIVE if purchased > ZERO else QUEUED,
                        # The utilization response describes a window and not a
                        # term, so the window is the only honest answer here. A real
                        # term needs the reservation inventory, which is a different
                        # API and is not read in v1.
                        term_start=window_start,
                        term_end=window_end,
                        window_start=window_start,
                        window_end=window_end,
                        committed=committed,
                        used=used,
                        wasted=committed - used,
                    )
                )
        return tuple(rows)

    def _reservation_coverage(
        self, window_start: date, window_end: date
    ) -> tuple[CommitmentCoverage, ...]:
        response = self._call(
            "get_reservation_coverage",
            TimePeriod=self._period(window_start, window_end),
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )
        as_of, collected_at = self._timestamps(window_end)
        rows: list[CommitmentCoverage] = []

        for span in response.get("CoveragesByTime", []):
            for group in span.get("Groups", []):
                cost = group.get("Coverage", {}).get("CoverageCost", {})
                # **The weakest mapping in this file.** `CoverageCost` is documented
                # as carrying `OnDemandCost`, the uncovered part, and reserved hours
                # priced in money are not in the response at all. `ReservedCost` is
                # read where a payer returns it and defaults to zero rather than
                # refusing, because a coverage row reporting only the uncovered side
                # is still worth showing and a refusal would show nothing. It is the
                # first thing to check against a real account.
                on_demand = _money(cost.get("OnDemandCost"), "OnDemandCost")
                reserved = _money(cost.get("ReservedCost", "0"), "ReservedCost")
                rows.append(
                    CommitmentCoverage(
                        as_of=as_of,
                        collected_at=collected_at,
                        tenant_id=self._tenant_id,
                        commitment_type=RESERVED_INSTANCE,
                        dimension=BY_SERVICE,
                        dimension_value=str(group.get("Attributes", {}).get("SERVICE", "")),
                        window_start=window_start,
                        window_end=window_end,
                        eligible_spend=on_demand + reserved,
                        covered_spend=reserved,
                    )
                )
        return tuple(rows)

    # -- each day, at the provider's daily grain -----------------------------

    def daily(self, window_start: date, window_end: date) -> Iterable[CommitmentDay]:
        """Each kind's use and coverage per day, four requests for the whole window.

        The same four reads as a window, asked at the daily grain and without grouping:
        Savings Plans report one total across every plan per day, so that is the grain all
        four are read at. The reservation figures keep the derivation, and the weak coverage
        mapping, that the window reads document.
        """
        period = self._period(window_start, window_end)
        totals: dict[tuple[str, date], dict[str, Decimal]] = {}

        def add(kind: str, day: date, **amounts: Decimal) -> None:
            found = totals.setdefault((kind, day), dict.fromkeys(_DAY_FIGURES, ZERO))
            for name, amount in amounts.items():
                found[name] += amount

        for span in self._call(
            "get_savings_plans_utilization", TimePeriod=period, Granularity=DAILY
        ).get("SavingsPlansUtilizationsByTime", []):
            found = span.get("Utilization") or {}
            if found:
                add(
                    SAVINGS_PLAN,
                    _the_day(span),
                    committed=_money(found.get("TotalCommitment"), "TotalCommitment"),
                    used=_money(found.get("UsedCommitment"), "UsedCommitment"),
                )
        for slice_ in self._call(
            "get_savings_plans_coverage", TimePeriod=period, Granularity=DAILY
        ).get("SavingsPlansCoverages", []):
            found = slice_.get("Coverage") or {}
            if found:
                add(
                    SAVINGS_PLAN,
                    _the_day(slice_),
                    eligible_spend=_money(found.get("TotalCost"), "TotalCost"),
                    covered_spend=_money(
                        found.get("SpendCoveredBySavingsPlans"), "SpendCoveredBySavingsPlans"
                    ),
                )
        for span in self._call(
            "get_reservation_utilization", TimePeriod=period, Granularity=DAILY
        ).get("UtilizationsByTime", []):
            found = span.get("Total") or {}
            if found:
                purchased = _money(found.get("PurchasedHours"), "PurchasedHours")
                actual = _money(found.get("TotalActualHours"), "TotalActualHours")
                committed = _money(found.get("TotalAmortizedFee"), "TotalAmortizedFee")
                add(
                    RESERVED_INSTANCE,
                    _the_day(span),
                    committed=committed,
                    used=_reservation_money(committed, actual, purchased),
                )
        for span in self._call(
            "get_reservation_coverage", TimePeriod=period, Granularity=DAILY
        ).get("CoveragesByTime", []):
            cost = (span.get("Total") or {}).get("CoverageCost") or {}
            if cost:
                on_demand = _money(cost.get("OnDemandCost"), "OnDemandCost")
                reserved = _money(cost.get("ReservedCost", "0"), "ReservedCost")
                add(
                    RESERVED_INSTANCE,
                    _the_day(span),
                    eligible_spend=on_demand + reserved,
                    covered_spend=reserved,
                )

        rows = tuple(
            self._day(kind, day, figures)
            for (kind, day), figures in sorted(totals.items(), key=lambda item: item[0][::-1])
            if window_start <= day < window_end
            and (figures["committed"] > ZERO or figures["covered_spend"] > ZERO)
        )
        if not rows:
            raise NoData(
                scope_key=SCOPE,
                collector=COLLECTOR,
                detail=(
                    f"nothing was committed or covered on any day "
                    f"between {window_start} and {window_end}"
                ),
            )
        return rows

    def _day(self, kind: str, day: date, figures: dict[str, Decimal]) -> CommitmentDay:
        # True once the day has ended, so `as_of` is the start of the next one.
        as_of, collected_at = self._timestamps(day + timedelta(days=1))
        return CommitmentDay(
            as_of=as_of,
            collected_at=collected_at,
            tenant_id=self._tenant_id,
            commitment_type=kind,
            day=day,
            committed=figures["committed"],
            used=figures["used"],
            eligible_spend=figures["eligible_spend"],
            covered_spend=figures["covered_spend"],
        )
