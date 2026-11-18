"""The response envelope. Every figure arrives with what it is worth trusting.

FEAT-050 and constraints 4, 5 and 10 in CLAUDE.md meet here. A number without
`as_of` is a number nobody can tell is stale. A view that covers two accounts
out of five, presented without saying so, is a true answer to a question nobody
asked. A failed collection rendered as an absent row is indistinguishable from
zero cost.

So `meta` is not decoration and it is not optional. It carries when the data was
true, when it was fetched, how much of the organization it covers, whether
anything is broken, and what to do about each broken thing. `degraded` is
computed rather than assigned, because a flag someone can forget to set is a
flag that will be wrong exactly when it matters.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field


class CoverageOut(BaseModel):
    """Visible accounts against every account the organization holds. ISS-016."""

    model_config = ConfigDict(frozen=True)

    visible: int
    total: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_partial(self) -> bool:
        return self.visible < self.total


class FailureOut(BaseModel):
    """One thing that is broken, and what the reader should do about it."""

    model_config = ConfigDict(frozen=True)

    scope_key: str
    collector: str
    #: One of the six causes in finops_core.errors. Never a free text message.
    cause: str
    remediation: str
    occurrences: int
    last_seen_at: datetime


class Meta(BaseModel):
    """What the numbers beside this are worth."""

    model_config = ConfigDict(frozen=True)

    #: When the data was true at the source. None when nothing has been collected.
    as_of: datetime | None
    #: When Meter fetched it. Never earlier than as_of. Constraint 10.
    collected_at: datetime | None
    scope_coverage: CoverageOut
    failures: tuple[FailureOut, ...] = ()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def degraded(self) -> bool:
        """True when the reader must not take these figures at face value.

        Computed, never assigned. Three separate things make a view untrustworthy
        and any one of them is enough: something failed, the view covers only
        part of the organization, or nothing has been collected at all.
        """
        return bool(self.failures) or self.scope_coverage.is_partial or self.as_of is None

    @classmethod
    def build(
        cls,
        visible: int,
        total: int,
        as_of: datetime | None = None,
        collected_at: datetime | None = None,
        failures: Sequence[FailureOut] = (),
    ) -> Meta:
        return cls(
            as_of=as_of,
            collected_at=collected_at,
            scope_coverage=CoverageOut(visible=visible, total=total),
            failures=tuple(failures),
        )


class Envelope[T](BaseModel):
    """Every route returns this. There is no bare data variant."""

    model_config = ConfigDict(frozen=True)

    data: T
    meta: Meta


class CollectorHealth(BaseModel):
    """How long since a collector last succeeded, against its own cadence."""

    model_config = ConfigDict(frozen=True)

    collector: str
    last_success_at: datetime | None
    cadence_seconds: int
    age_seconds: float | None
    is_stale: bool


class HealthOut(BaseModel):
    """`/healthz`. Deliberately not a bare liveness probe.

    A process that is running while the database is unreachable, or while
    ingestion stopped six hours ago, is a process that will serve confident and
    wrong numbers. Reporting only liveness makes that invisible to exactly the
    system that is supposed to notice.
    """

    model_config = ConfigDict(frozen=True)

    status: str
    database_reachable: bool
    collectors: tuple[CollectorHealth, ...]
