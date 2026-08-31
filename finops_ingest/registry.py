"""What a collector is, and the register of the ones that exist.

A collector is a name, the scope it runs at, and something callable. Keeping
the register separate from the things registered is what lets the dispatcher
enumerate work without importing every collector, and what lets a test run the
dispatcher against two lines of fake instead of against AWS.

Cadence is deliberately not here. Constraint 9 in CLAUDE.md and ADR-0012 put it
in the `collector_schedule` table with its reason and its cost, because a
cadence in code is a number nobody can change without a deploy and nobody can
explain a year later.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import text


class CollectorScope(StrEnum):
    """What one unit of this collector's work covers."""

    #: One account in one region. Needs an assumed session.
    ACCOUNT = "account"
    #: The whole organization, once. Runs on the hub's own credentials.
    ORGANIZATION = "organization"


@dataclass(frozen=True)
class CollectorOutcome:
    """What a collector did, for the run ledger to record."""

    items_written: int = 0
    bytes_read: int = 0


@dataclass(frozen=True)
class CollectorContext:
    """Everything a collector is given, and nothing it is not.

    The connection is the worker's own transaction for this one unit. A
    collector writing through it inherits the guarantee that its work commits or
    rolls back with the run record, and a collector cannot open a second
    transaction and leave the two disagreeing.

    `unit` is typed loosely on purpose: `WorkUnit` lives in the dispatcher, and
    the dispatcher already imports this module.
    """

    unit: Any
    connection: Any
    #: The assumed session for account scoped work. None for organization scope,
    #: which runs on the hub's own credentials.
    session: Any = None
    #: Runtime configuration. On the context rather than on the unit, because a
    #: unit is a message that outlives the process that wrote it and settings
    #: are whatever the worker running it was started with.
    settings: Any = None


#: A collector receives one context and reports what it did.
CollectorRunner = Callable[[CollectorContext], CollectorOutcome]


@dataclass(frozen=True)
class Collector:
    name: str
    scope: CollectorScope
    run: CollectorRunner


@dataclass(frozen=True)
class ScheduleEntry:
    """One collector's cadence, with the reason it is that number.

    ADR-0012 and constraint 9: cadence is data, not code. `reason` is NOT NULL
    in the table because a cadence nobody can explain is a number nobody can
    safely change, and the first thing anyone does with an unexplained interval
    under cost pressure is double it.
    """

    collector: str
    cadence_seconds: int
    reason: str
    est_cost_per_run: str


HOURLY = 3600
#: Six hours. The interval the P2 specification asks for, named rather than
#: written as a multiplication at the call site.
SIX_HOURLY = 21600
DAILY = 86400
#: Thirty days. The cost roll up is not calendar aware and does not need to be:
#: it aggregates everything past a cutoff, so running a day early or a day late
#: changes nothing except how many line items are left over until next time.
MONTHLY = 2592000

#: What a new tenant starts with. Installed at onboarding rather than in a
#: migration, because the table is keyed by tenant and a migration knows none.
DEFAULT_SCHEDULE: tuple[ScheduleEntry, ...] = (
    ScheduleEntry(
        collector="org_tree",
        cadence_seconds=HOURLY,
        reason=(
            "A new account has to appear within one hour with no human step, which is "
            "the P0 definition of done for onboarding. Faster buys nothing, because "
            "accounts are created by people and not by autoscaling."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="account_health",
        cadence_seconds=HOURLY,
        reason=(
            "A broken collector role is invisible until something tries to read the "
            "account, so the check runs as often as the tree it belongs to. The calls "
            "are free, and the alternative is finding out from a missing number."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="query_audit",
        cadence_seconds=SIX_HOURLY,
        reason=(
            "A dashboard is edited by a person, so the population changes on a human "
            "timescale rather than a machine one. Six hours catches a bad panel within "
            "one working day, which is fast enough to matter and slow enough that the "
            "survey itself is not the thing being audited: every run reads every "
            "dashboard in every workspace, and the Grafana API is the cost."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="platform_cost",
        cadence_seconds=DAILY,
        reason=(
            "Cost Explorer charges per request, so the cadence is itself a cost "
            "decision. Daily is the granularity the data has, and running hourly "
            "would pay twenty four times over for a figure that changes once."
        ),
        # The published per request price at the time of writing. Modelled, not
        # measured: the real figure arrives in the next day's own report, which
        # is the point of metering ourselves.
        est_cost_per_run="0.01",
    ),
    ScheduleEntry(
        collector="retention_principal",
        cadence_seconds=DAILY,
        reason=(
            "The retention window is stated in days, so checking it more than once "
            "a day cannot make the promise more true. Daily is also what makes a "
            "stopped retention job visible on the freshness screen within a day."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="retention_operational",
        cadence_seconds=DAILY,
        reason=(
            "Run history is the largest table by row count and the least valuable "
            "row for row. Daily keeps the deletion small enough to stay inside one "
            "transaction, which a weekly cadence would not."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="retention_audit",
        cadence_seconds=DAILY,
        reason=(
            "Thirteen months is a regulatory floor rather than a preference, so the "
            "job runs on the same daily cadence as the rest and is never the thing "
            "that made the window drift."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="retention_cost",
        cadence_seconds=MONTHLY,
        reason=(
            "Aggregating three year old line items is expensive and the answer does "
            "not change between runs, because nothing new becomes three years old "
            "inside a day. Monthly is the cheapest cadence that still bounds the "
            "table's growth."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="partition_maintenance",
        cadence_seconds=DAILY,
        reason=(
            "Partitions are created months ahead, so this could run weekly and still "
            "be correct. It runs daily because a stopped job is then visible within a "
            "day on the freshness screen, and the failure it prevents is every cost "
            "insert failing at midnight on the first of a month."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="retention_scope_cache",
        cadence_seconds=HOURLY,
        reason=(
            "An expired entitlement row is already ignored by the reader, so this is "
            "housekeeping and not enforcement. Hourly keeps the table small without "
            "anyone having to think about it."
        ),
        est_cost_per_run="0",
    ),
)


#: The flag that stops every retention job at once. Declared in
#: `docs/feature-flags.yaml` as a permanent operational control: retention
#: removes data, so a suspected bug in one has to be stoppable now rather than
#: after a deploy.
RETENTION_FLAG = "retention_jobs"

#: Which collectors that flag governs. Derived from the name rather than listed,
#: because a list here and the collectors in `retention.py` is two places to add
#: a job and one place to forget.
RETENTION_PREFIXES = ("retention_", "partition_")


def governed_by_retention_flag(collector: str) -> bool:
    return collector.startswith(RETENTION_PREFIXES)


def due_collectors(
    connection: Any,
    tenant_id: Any,
    is_enabled: Callable[[str], bool],
    now: datetime,
) -> tuple[str, ...]:
    """Which of a tenant's collectors are due, honouring the kill switch.

    `is_enabled` is passed in rather than imported. The flag resolver lives in
    `finops_api` and this package sits below it, so taking the predicate is what
    keeps the layering intact. It has no default: a default of "everything is
    on" would turn a missing wire up into a silently ignored kill switch, which
    is the one failure an operational control must not have.

    A collector the flag turns off produces no unit and therefore no
    `ingest_run`, so it reads as stale on the freshness screen rather than as a
    successful run that removed nothing. That is the honest rendering: retention
    is not running, and the flag's own reason calls that a deliberate,
    temporary and auditable act.
    """
    rows = connection.execute(
        text(
            "SELECT s.collector, s.cadence_seconds, latest.finished_at "
            "FROM collector_schedule s LEFT JOIN LATERAL ("
            "  SELECT MAX(r.finished_at) AS finished_at FROM ingest_run r "
            "  WHERE r.tenant_id = s.tenant_id AND r.collector = s.collector "
            "  AND r.status IN ('SUCCEEDED', 'PARTIAL')"
            ") latest ON true WHERE s.tenant_id = :tenant AND s.is_enabled "
            "ORDER BY s.collector"
        ),
        {"tenant": tenant_id},
    ).mappings()

    retention_on = is_enabled(RETENTION_FLAG)
    due = []
    for row in rows:
        name = str(row["collector"])
        if governed_by_retention_flag(name) and not retention_on:
            continue
        last = row["finished_at"]
        # Never run is due. An absent last run is the case the first dispatch
        # after onboarding depends on.
        if last is None or (now - last).total_seconds() >= int(row["cadence_seconds"]):
            due.append(name)
    return tuple(due)


def install_default_schedule(connection: Any, tenant_id: Any, updated_by: str) -> int:
    """Give a tenant the P0 cadences. Idempotent, and never overwrites a change.

    An operator who has deliberately slowed a collector down should not have that
    undone by a redeploy, so an existing row is left alone.
    """
    written = 0
    for entry in DEFAULT_SCHEDULE:
        result = connection.execute(
            text(
                "INSERT INTO collector_schedule (tenant_id, collector, cadence_seconds, "
                "reason, est_cost_per_run, updated_by) VALUES (:tenant, :collector, "
                ":cadence, :reason, :cost, :who) "
                "ON CONFLICT (tenant_id, collector) DO NOTHING"
            ),
            {
                "tenant": tenant_id,
                "collector": entry.collector,
                "cadence": entry.cadence_seconds,
                "reason": entry.reason,
                "cost": entry.est_cost_per_run,
                "who": updated_by,
            },
        )
        written += result.rowcount or 0
    return written


class CollectorRegistry:
    """The collectors this process knows how to run."""

    def __init__(self) -> None:
        self._collectors: dict[str, Collector] = {}

    def register(self, collector: Collector) -> None:
        if collector.name in self._collectors:
            raise ValueError(
                f"{collector.name} is already registered. Two collectors under one name "
                f"means the dispatcher and the worker disagree about what ran."
            )
        self._collectors[collector.name] = collector

    def get(self, name: str) -> Collector:
        try:
            return self._collectors[name]
        except KeyError as missing:
            raise KeyError(
                f"No collector named {name!r}. A unit of work naming a collector that "
                f"does not exist is a dispatch bug, not something to skip quietly."
            ) from missing

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._collectors))

    def __contains__(self, name: object) -> bool:
        return name in self._collectors
