"""Both processes run whole, in process, on the test database and a moto queue. TASK-P12-004.

`test_entry_points.py` starts the modules as processes but can only show them refusing to start,
because a process of its own reaches neither this test's database nor moto. These run the same
`main` functions with the settings, engine and queue client swapped for the test's, through the
local stack's entry points, so what runs is the composition, the loop and the signal handling a
container runs.
"""

from __future__ import annotations

import os
import signal
from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import boto3
import pytest
from moto import mock_aws
from sqlalchemy import text
from sqlalchemy.engine import Engine

from finops_core.config import Settings
from finops_fakes import dispatcher as fake_dispatcher
from finops_fakes import worker as fake_worker
from finops_ingest import processes
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.registry import install_default_schedule
from finops_ingest.sqs import SqsConsumer, SqsPublisher

REGION = "eu-west-1"


@pytest.fixture
def wired(
    engine: Engine, tenant_id: UUID, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> Iterator[SimpleNamespace]:
    """The mains' settings, engine and queue client, swapped for the test's own."""
    saved = {signum: signal.getsignal(signum) for signum in (signal.SIGTERM, signal.SIGINT)}
    with mock_aws():
        client = boto3.client("sqs", region_name=REGION)
        url = client.create_queue(QueueName="meter-test-work")["QueueUrl"]
        monkeypatch.setattr(
            processes, "load_settings", lambda: settings.model_copy(update={"queue_url": url})
        )
        monkeypatch.setattr(processes, "create_engine", lambda *_a, **_k: engine)
        monkeypatch.setattr(processes, "queue_client", lambda *_a: client)
        # Only this test's tenant, so another test's rows cannot decide this one's outcome.
        monkeypatch.setattr(
            processes, "TENANTS", f"SELECT tenant_id FROM tenant WHERE tenant_id = '{tenant_id}'"
        )
        yield SimpleNamespace(client=client, url=url, engine=engine, tenant=tenant_id)
    for signum, handler in saved.items():
        signal.signal(signum, handler)


def test_the_local_dispatcher_publishes_its_tenants_due_units(wired: SimpleNamespace) -> None:
    with wired.engine.begin() as connection:
        install_default_schedule(connection, wired.tenant, "test")
    assert fake_dispatcher.main() == 0
    reader = SqsConsumer(wired.client, wired.url, wait_seconds=0)
    units: list[WorkUnit] = []
    while received := reader.receive().deliveries:
        units.extend(one.unit for one in received)
    assert units and {one.tenant_id for one in units} == {wired.tenant}


class StopsOnSecondReceive(SqsConsumer):
    """A consumer that sends this process SIGTERM when it is asked for a second batch."""

    receives = 0

    def receive(self, max_messages: int = 10) -> Any:
        type(self).receives += 1
        if type(self).receives == 2:
            os.kill(os.getpid(), signal.SIGTERM)
        return super().receive(max_messages)


def test_the_local_worker_runs_a_unit_settles_it_and_stops_on_sigterm(
    wired: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    at = datetime(2026, 10, 12, 6, 0, tzinfo=UTC)
    unit = WorkUnit(
        tenant_id=wired.tenant, collector="finops_score", window_start=at, window_end=at
    )
    SqsPublisher(wired.client, wired.url).publish(unit)
    StopsOnSecondReceive.receives = 0
    monkeypatch.setattr(
        processes,
        "SqsConsumer",
        lambda client, url: StopsOnSecondReceive(client, url, wait_seconds=0),
    )

    assert fake_worker.main() == 0
    assert StopsOnSecondReceive.receives == 2
    assert SqsConsumer(wired.client, wired.url, wait_seconds=0).receive().deliveries == ()
    with wired.engine.connect() as connection:
        status = connection.execute(
            text(
                "SELECT status FROM ingest_run WHERE tenant_id = :t AND collector = 'finops_score'"
            ),
            {"t": wired.tenant},
        ).scalar_one()
    assert status == "SUCCEEDED"
