"""The dispatcher and the worker as processes. TASK-P12-004, FEAT-079.

P12 spec section 5.2: the dispatcher publishes each tenant's due units and exits, the worker
runs batches and settles them, and SIGTERM stops it between units. The loop is driven here in
process; `test_entry_points.py` runs the modules themselves.
"""

from __future__ import annotations

import logging
import os
import signal
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from finops_core.domain.account import AccountKey, Provider
from finops_core.flags import FlagResolver
from finops_ingest import processes
from finops_ingest.composition import production_registry
from finops_ingest.dispatcher import Dispatcher, InMemoryPublisher, WorkUnit
from finops_ingest.processes import Stop, dispatch_all, run_worker, window
from finops_ingest.registry import CollectorScope, install_default_schedule
from finops_ingest.sqs import Delivery, Received
from finops_ingest.worker import Outcome

NOW = datetime(2026, 10, 12, 7, 30, tzinfo=UTC)
REGIONS = ("eu-west-1", "us-east-1")
ACCOUNT = "111111111111"


def unit(collector: str) -> WorkUnit:
    return WorkUnit(tenant_id=uuid4(), collector=collector, window_start=NOW, window_end=NOW)


def delivery(collector: str, attempt: int = 1) -> Delivery:
    return Delivery(
        unit=unit(collector), receipt=f"r-{collector}", attempt=attempt, message_id=collector
    )


class Consumer:
    """The queue in shape: hands out the batches it is given, then stops the loop."""

    def __init__(self, batches: list[tuple[Delivery, ...]], stop: Any) -> None:
        self.batches = batches
        self.stop = stop
        self.deleted: list[str] = []

    def receive(self) -> Received:
        if not self.batches:
            self.stop.requested = True
            return Received(deliveries=(), undecodable=0)
        return Received(deliveries=self.batches.pop(0), undecodable=0)

    def delete(self, deliveries: Any) -> tuple[str, ...]:
        self.deleted.extend(one.message_id for one in deliveries)
        return ()


class Worker:
    """The worker in shape: each collector's name says what happens to its unit."""

    def __init__(self, on_handle: Any = None) -> None:
        self.ran: list[str] = []
        self.attempts: list[int] = []
        self.on_handle = on_handle

    def handle(self, unit: WorkUnit, delivery_attempt: int = 1) -> Outcome:
        self.ran.append(unit.collector)
        self.attempts.append(delivery_attempt)
        if self.on_handle is not None:
            self.on_handle()
        if unit.collector == "explodes":
            raise RuntimeError("a bug in a collector")
        return Outcome(unit.collector)


@pytest.fixture
def restored_signals() -> Iterator[None]:
    saved = {signum: signal.getsignal(signum) for signum in (signal.SIGTERM, signal.SIGINT)}
    yield
    for signum, handler in saved.items():
        signal.signal(signum, handler)


# --- windows -------------------------------------------------------------------------------


def test_a_window_is_the_cadence_period_that_ended_last() -> None:
    assert window(NOW, 3600) == (NOW.replace(minute=0) - timedelta(hours=1), NOW.replace(minute=0))
    day = datetime(2026, 10, 12, tzinfo=UTC)
    assert window(NOW, 86400) == (day - timedelta(days=1), day)


def test_two_dispatches_inside_one_period_name_the_same_window() -> None:
    assert window(NOW, 3600) == window(NOW + timedelta(minutes=29), 3600)
    assert window(NOW, 3600) != window(NOW + timedelta(minutes=31), 3600)


# --- the dispatcher ------------------------------------------------------------------------


def enrol(engine: Engine, tenant_id: UUID) -> None:
    with engine.begin() as connection:
        install_default_schedule(connection, tenant_id, "test")
        connection.execute(
            text(
                "INSERT INTO cloud_account (account_pk, tenant_id, provider, account_id, name, "
                "status, as_of, collected_at) "
                "VALUES (:pk, :tenant, 'aws', :account, 'Test', 'ACTIVE', :at, :at)"
            ),
            {"pk": uuid4(), "tenant": tenant_id, "account": ACCOUNT, "at": NOW},
        )


def test_a_dispatch_publishes_every_due_unit_of_a_tenant(engine: Engine, tenant_id: UUID) -> None:
    enrol(engine, tenant_id)
    registry = production_registry()
    publisher = InMemoryPublisher()
    flags = FlagResolver(SimpleNamespace(feature_retention_jobs=True)).is_enabled  # type: ignore[arg-type]
    summary = dispatch_all(engine.connect, Dispatcher(registry, publisher), flags, REGIONS, NOW)

    ours = [one for one in publisher.published if one.tenant_id == tenant_id]
    names = {one.collector for one in ours}
    per_account = {name for name in names if registry.get(name).scope is CollectorScope.ACCOUNT}
    assert names == set(registry.names())
    assert len(ours) == len(names - per_account) + len(per_account) * len(REGIONS)
    assert {one.account for one in ours if one.collector in per_account} == {
        AccountKey(provider=Provider.AWS, account_id=ACCOUNT)
    }
    assert summary.failed_tenants == 0


def test_a_second_dispatch_in_the_same_period_sends_nothing_new(
    engine: Engine, tenant_id: UUID
) -> None:
    enrol(engine, tenant_id)
    publisher = InMemoryPublisher()
    dispatcher = Dispatcher(production_registry(), publisher)
    flags = FlagResolver(SimpleNamespace()).is_enabled  # type: ignore[arg-type]
    dispatch_all(engine.connect, dispatcher, flags, REGIONS, NOW)
    first = {one.dedup_key for one in publisher.published if one.tenant_id == tenant_id}
    dispatch_all(engine.connect, dispatcher, flags, REGIONS, NOW + timedelta(minutes=5))
    again = {one.dedup_key for one in publisher.published if one.tenant_id == tenant_id}
    assert first and again == first


def test_one_tenant_failing_never_stops_the_others(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    good, bad = uuid4(), uuid4()

    @contextmanager
    def connections() -> Iterator[Any]:
        yield SimpleNamespace(
            execute=lambda *_a, **_k: SimpleNamespace(scalars=lambda: iter((bad, good)))
        )

    def dispatch_tenant(_connection: Any, _dispatcher: Any, tenant: UUID, *_rest: Any) -> Any:
        if tenant == bad:
            raise RuntimeError("this tenant's schedule is broken")
        return 3, 1

    monkeypatch.setattr(processes, "dispatch_tenant", dispatch_tenant)
    with caplog.at_level(logging.ERROR, logger="finops_ingest.processes"):
        summary = dispatch_all(connections, Any, lambda _flag: True, REGIONS, NOW)  # type: ignore[arg-type]
    assert (summary.tenants, summary.published, summary.deduplicated) == (2, 3, 1)
    assert summary.failed_tenants == 1
    (record,) = caplog.records
    assert record.exc_info and record.tenant_id == str(bad)  # type: ignore[attr-defined]


# --- the worker ----------------------------------------------------------------------------


def test_the_worker_deletes_what_it_settled_and_leaves_the_rest(
    caplog: pytest.LogCaptureFixture,
) -> None:
    stop = SimpleNamespace(requested=False)
    names = ("done", "skipped", "recorded_failure", "dead_lettered", "explodes")
    batch = tuple(delivery(name, attempt) for attempt, name in enumerate(names, start=1))
    consumer = Consumer([batch], stop)
    worker = Worker()
    with caplog.at_level(logging.ERROR, logger="finops_ingest.processes"):
        summary = run_worker(consumer, worker, lambda: stop.requested)  # type: ignore[arg-type]
    assert worker.attempts == [1, 2, 3, 4, 5], "each unit runs as the delivery it arrived as"
    assert consumer.deleted == ["done", "skipped", "recorded_failure"]
    assert (summary.settled, summary.left) == (3, 2)
    (record,) = caplog.records
    assert record.exc_info, "the unexpected failure is logged with its traceback"
    assert record.collector == "explodes"  # type: ignore[attr-defined]


@pytest.mark.usefixtures("restored_signals")
def test_sigterm_stops_the_worker_between_units() -> None:
    stop = Stop().install()
    worker = Worker(on_handle=lambda: os.kill(os.getpid(), signal.SIGTERM))
    consumer = Consumer([(delivery("done"), delivery("skipped"))], stop)
    summary = run_worker(consumer, worker, stop)  # type: ignore[arg-type]
    assert worker.ran == ["done"], "the unit in hand finished, the next was not started"
    assert consumer.deleted == ["done"]
    assert (summary.batches, summary.settled, summary.left) == (1, 1, 1)
    assert stop()


@pytest.mark.usefixtures("restored_signals")
def test_sigint_is_a_stop_too() -> None:
    stop = Stop().install()
    os.kill(os.getpid(), signal.SIGINT)
    assert stop()
