"""Runs, the failures inside them, and how far each collector has read.

Constraint 5 in CLAUDE.md: partial failure is first class. That is why a run
counts accounts succeeded and failed separately and has a `PARTIAL` status. A
run that reports success while three accounts returned AccessDenied is a run
that has taught the reader to trust a number that is missing three accounts.

`CollectionFailure` carries the cause as text rather than as an exception,
because it is stored and rendered long after the exception is gone. The value
is always one of the six names in `finops_core.errors`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from finops_core.domain.account import AccountKey
from finops_core.domain.fact import Fact


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    #: Some accounts failed and the rest are usable. Never rendered as success.
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass(frozen=True, kw_only=True)
class IngestRun:
    """One execution of one collector.

    Not a `Fact`. This is a record of our own work rather than something that
    was true in a cloud, so it has no `as_of` to give.
    """

    run_id: UUID
    tenant_id: UUID
    collector: str
    status: RunStatus
    started_at: datetime
    finished_at: datetime | None
    accounts_total: int
    accounts_succeeded: int
    accounts_failed: int


@dataclass(frozen=True, kw_only=True)
class CollectionFailure(Fact):
    """One account failing inside a run, with the reason kept typed."""

    scope_key: str
    collector: str
    #: One of the six names in `finops_core.errors`.
    cause: str
    remediation: str


@dataclass(frozen=True, kw_only=True)
class Watermark(Fact):
    """How far one collector has read for one account, so a rerun is idempotent."""

    tenant_id: UUID
    collector: str
    account_key: AccountKey
    watermark: datetime
