"""The dispatcher and the worker as processes. FEAT-079, TASK-P12-004.

P12 spec section 5.2. `python -m finops_ingest.dispatcher` and `python -m finops_ingest.worker`
run `dispatcher_main` and `worker_main` on the production composition; the local stack runs the
same two functions on the fake composition, from `finops_fakes`. Which composition runs is the
entry point's choice, so no setting can put a deployed process on fakes, ADR-0022.

**The dispatcher is one shot.** For each tenant it reads which collectors are due, enumerates
their units and publishes them, then exits. A unit's window is aligned to its collector's
cadence, so two dispatches inside one cadence period name the same window, and the ledger's claim
on the dedup key makes the second a skip. One tenant that fails is logged and the others are
still dispatched; the process then exits non zero, so the failure is visible where it ran.

**The worker runs until it is told to stop.** It long polls, runs each unit, deletes what it
settled and leaves the rest for the queue's redrive. SIGTERM, which ECS sends before it replaces
a task, is honoured between units: the unit in hand finishes its transaction, the ones not yet
started stay on the queue, and nothing is ever killed halfway through a write.

**What is left on the queue.** A unit the worker dead letters is left, so the queue's own redrive
moves it. A unit whose collector raised something unexpected is logged with its traceback and
left, so it is retried and, after the queue's maxReceiveCount, dead lettered: never deleted as if
it had been done.
"""

from __future__ import annotations

import logging
import signal
import sys
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import FrameType
from typing import Any, Final

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from finops_core.config import ConfigurationError, Settings, load_settings
from finops_core.flags import FlagResolver
from finops_core.logs import configure as configure_logging
from finops_ingest.accounts import active_accounts
from finops_ingest.composition import production_registry
from finops_ingest.dispatcher import Dispatcher
from finops_ingest.registry import CollectorRegistry, due_collectors
from finops_ingest.sqs import LONG_POLL_SECONDS, SqsConsumer, SqsPublisher
from finops_ingest.worker import Outcome, Worker
from finops_providers.aws.credentials import AwsCredentialBroker
from finops_providers.aws.reach import queue_client

LOGGER = logging.getLogger(__name__)

#: The exit status for a process that cannot start because it is configured wrongly, EX_CONFIG.
EXIT_CONFIGURATION: Final = 78
#: The exit status for a dispatch in which at least one tenant failed.
EXIT_PARTIAL: Final = 1

#: The outcomes after which a unit's message is deleted. DEAD_LETTERED is not one: the queue's
#: redrive moves that message, and deleting it would leave nothing in the dead letter queue.
SETTLED: Final = frozenset({Outcome.DONE, Outcome.SKIPPED, Outcome.RECORDED_FAILURE})

TENANTS: Final = "SELECT tenant_id FROM tenant ORDER BY tenant_id"
CADENCES: Final = (
    "SELECT collector, cadence_seconds FROM collector_schedule WHERE tenant_id = :tenant"
)

Clock = Callable[[], datetime]
Connections = Callable[[], AbstractContextManager[Connection]]


def system_clock() -> datetime:
    """The wall clock, which an entry point hands to whatever must not read it itself."""
    return datetime.now(UTC)


def window(now: datetime, cadence_seconds: int) -> tuple[datetime, datetime]:
    """The cadence period that ended last at or before `now`, aligned to the epoch."""
    end = datetime.fromtimestamp(int(now.timestamp()) // cadence_seconds * cadence_seconds, tz=UTC)
    return end - timedelta(seconds=cadence_seconds), end


@dataclass(frozen=True)
class DispatchSummary:
    """What one dispatch did, across every tenant."""

    tenants: int
    published: int
    deduplicated: int
    failed_tenants: int


def dispatch_tenant(
    connection: Any,
    dispatcher: Dispatcher,
    tenant_id: Any,
    is_enabled: Callable[[str], bool],
    regions: Sequence[str],
    now: datetime,
) -> tuple[int, int]:
    """Publish one tenant's due units. Returns (published, deduplicated)."""
    due = due_collectors(connection, tenant_id, is_enabled, now)
    cadences = {
        str(row["collector"]): int(row["cadence_seconds"])
        for row in connection.execute(text(CADENCES), {"tenant": tenant_id}).mappings()
    }
    accounts = active_accounts(connection, tenant_id)
    published = deduplicated = 0
    for name in due:
        start, end = window(now, cadences[name])
        result = dispatcher.dispatch(
            dispatcher.enumerate_units(tenant_id, [name], accounts, regions, start, end)
        )
        published += result.published
        deduplicated += result.deduplicated
    return published, deduplicated


def dispatch_all(
    connections: Connections,
    dispatcher: Dispatcher,
    is_enabled: Callable[[str], bool],
    regions: Sequence[str],
    now: datetime,
    logger: logging.Logger = LOGGER,
) -> DispatchSummary:
    """Every tenant's due units. One tenant failing is logged and never stops the others."""
    with connections() as connection:
        tenants = tuple(connection.execute(text(TENANTS)).scalars())
    published = deduplicated = failed = 0
    for tenant_id in tenants:
        try:
            with connections() as connection:
                sent, refused = dispatch_tenant(
                    connection, dispatcher, tenant_id, is_enabled, regions, now
                )
        except Exception:
            failed += 1
            logger.exception(
                "a tenant could not be dispatched", extra={"tenant_id": str(tenant_id)}
            )
            continue
        published += sent
        deduplicated += refused
    return DispatchSummary(
        tenants=len(tenants), published=published, deduplicated=deduplicated, failed_tenants=failed
    )


class Stop:
    """Whether the process has been asked to stop, by SIGTERM or SIGINT."""

    def __init__(self, logger: logging.Logger = LOGGER) -> None:
        self.requested = False
        self._log = logger

    def install(self) -> Stop:
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, self._request)
        return self

    def _request(self, signum: int, _frame: FrameType | None) -> None:
        self.requested = True
        self._log.info(
            "asked to stop, finishing the unit in hand",
            extra={"signal": signal.Signals(signum).name},
        )

    def __call__(self) -> bool:
        return self.requested


@dataclass(frozen=True)
class WorkerSummary:
    """What the worker did before it stopped."""

    batches: int
    settled: int
    left: int


def run_worker(
    consumer: SqsConsumer,
    worker: Worker,
    stopping: Callable[[], bool],
    logger: logging.Logger = LOGGER,
) -> WorkerSummary:
    """Receive, run and settle batches until `stopping` says to stop."""
    batches = settled_total = left = 0
    while not stopping():
        received = consumer.receive()
        settled = []
        for delivery in received.deliveries:
            if stopping():
                left += 1
                continue
            try:
                outcome = worker.handle(delivery.unit, delivery_attempt=delivery.attempt)
            except Exception:
                left += 1
                logger.exception(
                    "a unit failed unexpectedly and is left for the redrive",
                    extra={"message_id": delivery.message_id, "collector": delivery.unit.collector},
                )
                continue
            if outcome in SETTLED:
                settled.append(delivery)
            else:
                left += 1
        consumer.delete(settled)
        settled_total += len(settled)
        left += received.undecodable
        batches += 1
    return WorkerSummary(batches=batches, settled=settled_total, left=left)


def _start(name: str) -> Settings | None:
    """Settings, with logging configured from them, or None after saying why they are wrong."""
    try:
        settings = load_settings()
    except ConfigurationError as error:
        print(f"{name} cannot start: {error}", file=sys.stderr)
        return None
    configure_logging(settings.log_level)
    return settings


def dispatcher_main(registry: Callable[[], CollectorRegistry] = production_registry) -> int:
    """Run one dispatch and exit: 0, EXIT_PARTIAL when a tenant failed, or EXIT_CONFIGURATION."""
    settings = _start("the dispatcher")
    if settings is None:
        return EXIT_CONFIGURATION
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    publisher = SqsPublisher(queue_client(settings, LONG_POLL_SECONDS), settings.queue_url)
    summary = dispatch_all(
        engine.connect,
        Dispatcher(registry(), publisher),
        FlagResolver(settings).is_enabled,
        settings.region_list,
        system_clock(),
    )
    LOGGER.info("dispatch finished", extra=vars(summary))
    return EXIT_PARTIAL if summary.failed_tenants else 0


def worker_main(
    registry: Callable[[], CollectorRegistry] = production_registry,
    broker: Callable[[Settings], Any] = AwsCredentialBroker,
) -> int:
    """Run the worker until SIGTERM: 0 after a clean stop, or EXIT_CONFIGURATION."""
    settings = _start("the worker")
    if settings is None:
        return EXIT_CONFIGURATION
    stop = Stop().install()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    worker = Worker(
        registry(),
        engine.begin,
        claim_timeout_minutes=settings.run_claim_timeout_minutes,
        broker=broker(settings),
        settings=settings,
    )
    consumer = SqsConsumer(queue_client(settings, LONG_POLL_SECONDS), settings.queue_url)
    summary = run_worker(consumer, worker, stop)
    LOGGER.info("worker stopped", extra=vars(summary))
    return 0
