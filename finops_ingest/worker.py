"""Consuming units of work, one at a time, one transaction each.

Constraint 5 in CLAUDE.md is the whole design: partial failure is first class,
one account failing never fails a run, and a failure is never rendered as the
number zero. Two decisions carry that.

Each unit runs in its own transaction. Processing a batch in one transaction
means one account's failure rolls back the other two hundred and ninety nine,
and the symptom is a run that reports nothing wrong and wrote nothing.

Only the six domain errors are caught. Anything else is allowed to crash the
worker, loudly, because an `except Exception` that logs and moves on turns an
unknown bug into a permanently quiet one: the queue drains, the run says
success, and the numbers are wrong for a reason nobody can reconstruct
afterwards. A crash is recoverable. A silent unknown failure is not.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy.engine import Connection

from finops_core.constants import MAX_DELIVERY_ATTEMPTS
from finops_core.errors import CollectionError, SchemaDrift
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.ledger import RunLedger
from finops_ingest.registry import CollectorContext, CollectorRegistry, CollectorScope

Clock = Callable[[], datetime]
Connections = Callable[[], AbstractContextManager[Connection]]

LOGGER = logging.getLogger("meter.ingest.worker")


def _system_clock() -> datetime:
    return datetime.now(UTC)


class Outcome(StrEnum):
    """What happened to one unit. Every one of these is a normal result."""

    DONE = "done"
    #: Somebody else already owns or finished this unit. Not an error.
    SKIPPED = "skipped"
    #: The collector raised one of the six. Recorded against the scope, batch continues.
    RECORDED_FAILURE = "recorded_failure"
    #: Delivered too many times. Left for the dead letter queue, with a record.
    DEAD_LETTERED = "dead_lettered"


@dataclass(frozen=True)
class BatchResult:
    outcomes: tuple[Outcome, ...]

    def count(self, outcome: Outcome) -> int:
        return sum(1 for entry in self.outcomes if entry is outcome)

    @property
    def is_partial(self) -> bool:
        """True when the batch wrote something and something also failed.

        PARTIAL is the normal outcome at three hundred accounts. It is not an
        error state, and it must never render as success.
        """
        return self.count(Outcome.DONE) > 0 and (
            self.count(Outcome.RECORDED_FAILURE) > 0 or self.count(Outcome.DEAD_LETTERED) > 0
        )


def log_fields(unit: WorkUnit, run_id: object) -> dict[str, str]:
    """The three fields every line carries, so a failure can be joined up.

    `run_id` is empty for a unit nobody claimed, because there is no run of ours
    to name. The field is present rather than absent, so a log query never has
    to handle two shapes.
    """
    return {
        "run_id": "" if run_id is None else str(run_id),
        "collector": unit.collector,
        "scope_key": unit.scope_key,
    }


class Worker:
    """Claims a unit, resolves credentials, runs the collector, records the outcome."""

    def __init__(
        self,
        registry: CollectorRegistry,
        connections: Connections,
        claim_timeout_minutes: int,
        broker: Any = None,
        settings: Any = None,
        clock: Clock = _system_clock,
        logger: logging.Logger = LOGGER,
    ) -> None:
        self._registry = registry
        self._connections = connections
        self._timeout = claim_timeout_minutes
        self._broker = broker
        self._settings = settings
        self._clock = clock
        self._log = logger

    def handle_batch(self, units: Iterable[WorkUnit], delivery_attempt: int = 1) -> BatchResult:
        """One transaction per unit. Never one transaction for the batch."""
        return BatchResult(
            outcomes=tuple(self.handle(unit, delivery_attempt=delivery_attempt) for unit in units)
        )

    def handle(self, unit: WorkUnit, delivery_attempt: int = 1) -> Outcome:
        if delivery_attempt > MAX_DELIVERY_ATTEMPTS:
            return self._dead_letter(unit, delivery_attempt)

        collector = self._registry.get(unit.collector)
        with self._connections() as connection:
            ledger = RunLedger(connection, unit.tenant_id, self._timeout, clock=self._clock)
            claim = ledger.claim(unit.collector, unit.scope_key, unit.window_start, unit.window_end)
            if claim is None:
                self._log.info("unit already claimed, skipping", extra=log_fields(unit, None))
                return Outcome.SKIPPED

            fields = log_fields(unit, claim.run_id)
            ledger.running(claim)
            self._log.info("running collector", extra=fields)

            try:
                session = self._session_for(unit, collector.scope)
                result = collector.run(
                    CollectorContext(
                        unit=unit,
                        connection=connection,
                        session=session,
                        settings=self._settings,
                    )
                )
            except CollectionError as failure:
                # Exactly the six, and nothing wider. An unexpected exception is
                # allowed past here deliberately.
                ledger.fail(claim, failure)
                ledger.record_sync_error(unit.collector, unit.scope_key, failure)
                self._log.warning(
                    "collector failed, recorded against the scope",
                    extra={**fields, "cause": failure.cause},
                )
                return Outcome.RECORDED_FAILURE

            ledger.complete(claim, result.items_written, result.bytes_read)
            ledger.clear_sync_error(unit.collector, unit.scope_key)
            self._log.info(
                "collector finished", extra={**fields, "items_written": result.items_written}
            )
            return Outcome.DONE

    def _session_for(self, unit: WorkUnit, scope: CollectorScope) -> Any:
        """Organization scoped collectors run on the hub's own credentials."""
        if scope is not CollectorScope.ACCOUNT:
            return None
        if self._broker is None or unit.account is None or unit.region is None:
            raise SchemaDrift(
                scope_key=unit.scope_key,
                collector=unit.collector,
                detail="an account scoped unit arrived without an account, a region or a broker",
            )
        return self._broker.session_for(unit.account, unit.region)

    def _dead_letter(self, unit: WorkUnit, delivery_attempt: int) -> Outcome:
        """Leave a record before the queue takes the message away.

        Without this the message disappears into the queue's own accounting and
        the only trace is a metric nobody is watching.
        """
        with self._connections() as connection:
            ledger = RunLedger(connection, unit.tenant_id, self._timeout, clock=self._clock)
            ledger.record_sync_error(
                unit.collector,
                unit.scope_key,
                SchemaDrift(
                    scope_key=unit.scope_key,
                    collector=unit.collector,
                    detail=(
                        f"delivered {delivery_attempt} times without completing, past the "
                        f"limit of {MAX_DELIVERY_ATTEMPTS}"
                    ),
                ),
            )
        self._log.error(
            "unit exceeded the delivery limit, leaving it for the dead letter queue",
            extra={**log_fields(unit, None), "delivery_attempt": delivery_attempt},
        )
        return Outcome.DEAD_LETTERED
