"""P12's first exit criterion, held against the whole demo estate. TASK-P12-009, spec section 13.

TASK-P12-005's test runs one collector from dispatch to `ingest_run`, and the local stack run on
2026-10-12 ran all of them once, by hand. This runs every collector the demo tenant's schedule
dispatches through the local stack's own entry points, the fake composition, the SQS publisher and
consumer over moto, and the worker loop, and holds each to a recorded run that either succeeded or
failed with a typed cause, so a collector that composes but cannot run fails here. The other three
criteria are held by `test_deployed_settings.py`, `test_pipeline.py` and `test_first_contact.py`.
"""

from __future__ import annotations

import os
import signal
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import pytest
from moto import mock_aws
from sqlalchemy import Engine, text

from finops_core import errors
from finops_core.config import Settings
from finops_core.flags import FlagResolver
from finops_fakes import worker as fake_worker
from finops_fakes.composition import fake_registry
from finops_ingest import processes
from finops_ingest.dispatcher import Dispatcher
from finops_ingest.sqs import SqsConsumer, SqsPublisher
from tests.scripts.test_seed_demo import DEMO_TENANT, _now, seed_demo

pytestmark = pytest.mark.integration

#: Every typed cause a collector may fail with; anything else is a collector that cannot run.
TYPED = {
    cause.__name__
    for cause in (
        errors.AccessDenied,
        errors.Throttled,
        errors.NotOptedIn,
        errors.NoData,
        errors.Unreachable,
        errors.Misconfigured,
        errors.SchemaDrift,
    )
}


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """The seed bills months into partitions, so this module gives them back. ISS-268."""


@pytest.fixture
def seeded(engine: Engine, settings: Settings) -> Iterator[Engine]:
    seed_demo.seed(engine, settings, _now())
    try:
        yield engine
    finally:
        seed_demo.remove(engine)


@pytest.fixture
def restored_signals() -> Iterator[None]:
    saved = {signum: signal.getsignal(signum) for signum in (signal.SIGTERM, signal.SIGINT)}
    yield
    for signum, handler in saved.items():
        signal.signal(signum, handler)


class StopsWhenEmpty(SqsConsumer):
    """The worker's consumer, which sends this process SIGTERM once the queue is drained."""

    def receive(self, max_messages: int = 10) -> Any:
        received = super().receive(max_messages)
        if not received.deliveries and not received.undecodable:
            os.kill(os.getpid(), signal.SIGTERM)
        return received


@pytest.mark.usefixtures("restored_signals")
def test_every_collector_the_schedule_dispatches_runs_end_to_end_on_the_local_stack(
    seeded: Engine, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Far enough ahead that every collector is due, the monthly ones included.
    later = datetime.now(UTC) + timedelta(days=40)
    only_demo = f"SELECT tenant_id FROM tenant WHERE tenant_id = '{DEMO_TENANT}'"
    with mock_aws():
        client = boto3.client("sqs", region_name="eu-west-1")
        url = client.create_queue(QueueName="meter-p12-exit")["QueueUrl"]
        monkeypatch.setattr(processes, "TENANTS", only_demo)
        summary = processes.dispatch_all(
            seeded.connect,
            Dispatcher(fake_registry(processes.system_clock), SqsPublisher(client, url)),
            FlagResolver(settings).is_enabled,
            settings.region_list,
            later,
        )
        assert (summary.tenants, summary.failed_tenants) == (1, 0)
        assert summary.published > 0

        monkeypatch.setattr(
            processes, "load_settings", lambda: settings.model_copy(update={"queue_url": url})
        )
        monkeypatch.setattr(processes, "create_engine", lambda *_a, **_k: seeded)
        monkeypatch.setattr(processes, "queue_client", lambda *_a: client)
        monkeypatch.setattr(
            processes, "SqsConsumer", lambda c, u: StopsWhenEmpty(c, u, wait_seconds=0)
        )
        assert fake_worker.main() == 0

    with seeded.connect() as connection:
        scheduled = set(
            connection.execute(
                text(
                    "SELECT collector FROM collector_schedule "
                    "WHERE tenant_id = :t AND is_enabled AND runs_in = 'worker'"
                ),
                {"t": DEMO_TENANT},
            ).scalars()
        )
        runs = connection.execute(
            text(
                "SELECT collector, status, error_type FROM ingest_run "
                "WHERE tenant_id = :t AND as_of_window_end > :now"
            ),
            {"t": DEMO_TENANT, "now": datetime.now(UTC)},
        ).all()

    assert {run.collector for run in runs} == scheduled, "every dispatched collector ran"
    untyped = [tuple(run) for run in runs if run.status == "FAILED" and run.error_type not in TYPED]
    assert untyped == [], "a failure that is not one of the typed causes"
    assert {run.status for run in runs} <= {"SUCCEEDED", "PARTIAL", "FAILED"}
    assert sum(run.status == "SUCCEEDED" for run in runs) > len(runs) // 2
