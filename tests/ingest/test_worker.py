"""One account failing must never fail the run. The plan calls this the most
important test in P0, and it is right.

Everything else in this project is downstream of it. If a single AccessDenied
can take a batch down, then at three hundred accounts the batch is always down,
and the response to that is invariably a bare except that logs and moves on,
which turns every future unknown failure into silence. So the boundary is tested
from both sides: the six domain errors are recorded and the batch continues, and
anything else is allowed to crash.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import Engine, text

from finops_core.domain.account import AccountKey, Provider
from finops_core.errors import AccessDenied, NoData, Throttled
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.registry import Collector, CollectorOutcome, CollectorRegistry, CollectorScope
from finops_ingest.worker import Outcome, Worker

START = datetime(2026, 8, 24, 0, 0, tzinfo=UTC)
END = datetime(2026, 8, 24, 6, 0, tzinfo=UTC)
NOW = datetime(2026, 8, 24, 6, 5, tzinfo=UTC)
TIMEOUT = 30

GOOD = AccountKey(provider=Provider.AWS, account_id="111122223333")
DENIED = AccountKey(provider=Provider.AWS, account_id="444455556666")
EMPTY = AccountKey(provider=Provider.AWS, account_id="777788889999")
REGION = "eu-west-1"

pytestmark = pytest.mark.integration


class ScriptedCollector:
    """Succeeds, or raises whatever the test says for a given account."""

    def __init__(self, failures: dict[str, Exception] | None = None) -> None:
        self.failures = failures or {}
        self.ran: list[str] = []

    def __call__(self, unit: WorkUnit, _session: object) -> CollectorOutcome:
        self.ran.append(unit.scope_key)
        failure = self.failures.get(unit.account.account_id if unit.account else "")
        if failure is not None:
            raise failure
        return CollectorOutcome(items_written=7, bytes_read=70)


class StubBroker:
    def session_for(self, _account: AccountKey, _region: str) -> object:
        return object()


def build(
    engine: Engine, collector: ScriptedCollector, logger: logging.Logger | None = None
) -> Worker:
    registry = CollectorRegistry()
    registry.register(Collector("account_health", CollectorScope.ACCOUNT, collector))
    return Worker(
        registry,
        connections=engine.begin,
        claim_timeout_minutes=TIMEOUT,
        broker=StubBroker(),
        clock=lambda: NOW,
        logger=logger or logging.getLogger("meter.ingest.worker"),
    )


def unit_for(tenant: UUID, account: AccountKey) -> WorkUnit:
    return WorkUnit(
        tenant_id=tenant,
        collector="account_health",
        window_start=START,
        window_end=END,
        account=account,
        region=REGION,
    )


def rows(engine: Engine, table_name: str, tenant: UUID) -> list[dict[str, object]]:
    with engine.connect() as connection:
        result = connection.execute(
            text(f"SELECT * FROM {table_name} WHERE tenant_id = :t"), {"t": tenant}
        ).mappings()
        return [dict(row) for row in result]


# --- the test everything else depends on ------------------------------------


def test_one_account_access_denied_does_not_fail_run(engine: Engine, tenant_id: UUID) -> None:
    """Spec section 11, test 1."""
    collector = ScriptedCollector(
        {DENIED.account_id: AccessDenied(scope_key=str(DENIED), collector="account_health")}
    )
    worker = build(engine, collector)
    result = worker.handle_batch([unit_for(tenant_id, GOOD), unit_for(tenant_id, DENIED)])

    assert result.outcomes == (Outcome.DONE, Outcome.RECORDED_FAILURE)
    assert result.is_partial is True
    assert collector.ran == [f"{GOOD}:{REGION}", f"{DENIED}:{REGION}"]

    statuses = {row["scope_key"]: row["status"] for row in rows(engine, "ingest_run", tenant_id)}
    assert statuses[f"{GOOD}:{REGION}"] == "SUCCEEDED"
    assert statuses[f"{DENIED}:{REGION}"] == "FAILED"


def test_the_good_account_is_committed_even_though_the_other_failed(
    engine: Engine, tenant_id: UUID
) -> None:
    """One transaction for the batch would roll back the other two hundred and ninety nine."""
    collector = ScriptedCollector(
        {DENIED.account_id: AccessDenied(scope_key=str(DENIED), collector="account_health")}
    )
    build(engine, collector).handle_batch([unit_for(tenant_id, GOOD), unit_for(tenant_id, DENIED)])
    watermarks = rows(engine, "ingest_watermark", tenant_id)
    assert {row["scope_key"] for row in watermarks} == {f"{GOOD}:{REGION}"}


def test_no_data_and_access_denied_are_distinguishable(engine: Engine, tenant_id: UUID) -> None:
    """Spec section 11, test 2. ISS-015.

    NoData is the one cause that may be drawn as a zero. If it cannot be told
    apart from a refusal, every refusal becomes a zero and the product lies.
    """
    collector = ScriptedCollector(
        {
            DENIED.account_id: AccessDenied(scope_key=str(DENIED), collector="account_health"),
            EMPTY.account_id: NoData(scope_key=str(EMPTY), collector="account_health"),
        }
    )
    build(engine, collector).handle_batch([unit_for(tenant_id, DENIED), unit_for(tenant_id, EMPTY)])

    causes = {row["scope_key"]: row["error_type"] for row in rows(engine, "ingest_run", tenant_id)}
    assert causes[f"{DENIED}:{REGION}"] == "AccessDenied"
    assert causes[f"{EMPTY}:{REGION}"] == "NoData"

    errors = {row["scope_key"]: row for row in rows(engine, "sync_error", tenant_id)}
    assert errors[f"{DENIED}:{REGION}"]["error_type"] == "AccessDenied"
    assert errors[f"{EMPTY}:{REGION}"]["error_type"] == "NoData"
    assert errors[f"{DENIED}:{REGION}"]["remediation"]


# --- the boundary of what is caught -----------------------------------------


def test_an_unexpected_exception_crashes_the_worker(engine: Engine, tenant_id: UUID) -> None:
    """A silent unknown failure is worse than a crash, so this must not be caught."""

    class Exploding(ScriptedCollector):
        def __call__(self, _unit: WorkUnit, _session: object) -> CollectorOutcome:
            raise ValueError("something nobody predicted")

    with pytest.raises(ValueError, match="nobody predicted"):
        build(engine, Exploding()).handle(unit_for(tenant_id, GOOD))


def test_a_throttle_is_recorded_and_the_batch_continues(engine: Engine, tenant_id: UUID) -> None:
    collector = ScriptedCollector(
        {GOOD.account_id: Throttled(scope_key=str(GOOD), collector="account_health")}
    )
    result = build(engine, collector).handle_batch(
        [unit_for(tenant_id, GOOD), unit_for(tenant_id, EMPTY)]
    )
    assert result.outcomes == (Outcome.RECORDED_FAILURE, Outcome.DONE)


# --- claiming and redelivery -------------------------------------------------


def test_a_second_delivery_of_a_finished_unit_is_skipped(engine: Engine, tenant_id: UUID) -> None:
    collector = ScriptedCollector()
    worker = build(engine, collector)
    assert worker.handle(unit_for(tenant_id, GOOD)) is Outcome.DONE
    assert worker.handle(unit_for(tenant_id, GOOD)) is Outcome.SKIPPED
    assert collector.ran == [f"{GOOD}:{REGION}"], "the collector must not run twice"


def test_delivery_past_the_limit_is_dead_lettered_with_a_record(
    engine: Engine, tenant_id: UUID
) -> None:
    """Otherwise the message disappears into the queue's own accounting."""
    collector = ScriptedCollector()
    outcome = build(engine, collector).handle(unit_for(tenant_id, GOOD), delivery_attempt=4)
    assert outcome is Outcome.DEAD_LETTERED
    assert collector.ran == []
    errors = rows(engine, "sync_error", tenant_id)
    assert len(errors) == 1
    assert "delivered 4 times" in str(errors[0]["detail"])


def test_a_success_clears_a_previous_error_for_that_scope(engine: Engine, tenant_id: UUID) -> None:
    """A fixed account must stop being reported as broken."""
    failing = ScriptedCollector(
        {GOOD.account_id: AccessDenied(scope_key=str(GOOD), collector="account_health")}
    )
    build(engine, failing).handle(unit_for(tenant_id, GOOD))
    assert rows(engine, "sync_error", tenant_id)

    later = WorkUnit(
        tenant_id=tenant_id,
        collector="account_health",
        window_start=END,
        window_end=datetime(2026, 8, 24, 12, tzinfo=UTC),
        account=GOOD,
        region=REGION,
    )
    build(engine, ScriptedCollector()).handle(later)
    assert rows(engine, "sync_error", tenant_id) == []


def test_repeated_failures_count_rather_than_pile_up(engine: Engine, tenant_id: UUID) -> None:
    """Ten thousand rows saying so would bury the three accounts that are broken."""
    for hour in (6, 12, 18):
        collector = ScriptedCollector(
            {GOOD.account_id: AccessDenied(scope_key=str(GOOD), collector="account_health")}
        )
        build(engine, collector).handle(
            WorkUnit(
                tenant_id=tenant_id,
                collector="account_health",
                window_start=START,
                window_end=datetime(2026, 8, 24, hour, tzinfo=UTC),
                account=GOOD,
                region=REGION,
            )
        )
    errors = rows(engine, "sync_error", tenant_id)
    assert len(errors) == 1
    assert errors[0]["occurrences"] == 3


# --- logging -----------------------------------------------------------------


def test_every_log_line_carries_run_id_collector_and_scope_key(
    engine: Engine, tenant_id: UUID, caplog: pytest.LogCaptureFixture
) -> None:
    """A failure nobody can join to a run is a failure nobody can investigate."""
    logger = logging.getLogger("meter.ingest.worker.test")
    collector = ScriptedCollector(
        {DENIED.account_id: AccessDenied(scope_key=str(DENIED), collector="account_health")}
    )
    with caplog.at_level(logging.INFO, logger=logger.name):
        build(engine, collector, logger=logger).handle_batch(
            [unit_for(tenant_id, GOOD), unit_for(tenant_id, DENIED)]
        )

    assert caplog.records
    for record in caplog.records:
        assert hasattr(record, "run_id")
        assert record.collector == "account_health"  # type: ignore[attr-defined]
        assert record.scope_key.startswith("aws:")  # type: ignore[attr-defined]


def test_a_failure_line_names_the_cause(
    engine: Engine, tenant_id: UUID, caplog: pytest.LogCaptureFixture
) -> None:
    logger = logging.getLogger("meter.ingest.worker.cause")
    collector = ScriptedCollector(
        {GOOD.account_id: NoData(scope_key=str(GOOD), collector="account_health")}
    )
    with caplog.at_level(logging.INFO, logger=logger.name):
        build(engine, collector, logger=logger).handle(unit_for(tenant_id, GOOD))
    causes = [getattr(r, "cause", None) for r in caplog.records]
    assert "NoData" in causes
