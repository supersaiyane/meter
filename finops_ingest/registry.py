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


#: A collector receives the unit it is running and, for account scoped work, the
#: session to run it with. Organization scoped collectors get None.
CollectorRunner = Callable[[Any, Any], CollectorOutcome]


@dataclass(frozen=True)
class Collector:
    name: str
    scope: CollectorScope
    run: CollectorRunner


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
