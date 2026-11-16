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
from enum import StrEnum
from typing import Any


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
DAILY = 86400

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
)


def install_default_schedule(connection: Any, tenant_id: Any, updated_by: str) -> int:
    """Give a tenant the P0 cadences. Idempotent, and never overwrites a change.

    An operator who has deliberately slowed a collector down should not have that
    undone by a redeploy, so an existing row is left alone.
    """
    from sqlalchemy import text

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
