"""Who called which model, written to `ai_usage_daily` and restated per source. TASK-P13-003.

FEAT-082, P13 spec sections 5.4 and 6. The collector runs on the fake estate's invocation logs:
one account sends them to CloudWatch Logs and is read, one sends them to S3 only and one nowhere,
and both of those are NotOptedIn rather than an account whose models nobody called. A rerun of a
window replaces that window's rows for that account and Region and touches nothing else.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.ai import AiUsage
from finops_core.errors import NotOptedIn
from finops_fakes import fixtures
from finops_fakes.ai import CALLERS, SUPPORT_ACCOUNT, FakeInvocationLogs
from finops_ingest.collectors.ai_usage import BedrockInvocationsCollector
from finops_ingest.collectors.retention import retention_ai_usage
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.registry import CollectorContext, CollectorOutcome

pytestmark = pytest.mark.integration

DAY = datetime(2026, 8, 23, tzinfo=UTC)
NEXT_DAY = DAY + timedelta(days=1)
NOW = datetime(2026, 8, 24, 6, 0, tzinfo=UTC)
REGION = fixtures.REGION
OTHER_REGION = "us-fake-2"


def unit(
    tenant: UUID, account: str = SUPPORT_ACCOUNT, region: str = REGION, day: datetime = DAY
) -> WorkUnit:
    return WorkUnit(
        tenant_id=tenant,
        collector="bedrock_invocations",
        window_start=day,
        window_end=day + timedelta(days=1),
        account=AccountKey(provider=Provider.AWS, account_id=account),
        region=region,
    )


def run(engine: Engine, work: WorkUnit, source: Any = None) -> CollectorOutcome:
    collector = BedrockInvocationsCollector(source or FakeInvocationLogs(at=NOW), clock=lambda: NOW)
    with engine.begin() as connection:
        return collector(CollectorContext(unit=work, connection=connection, run_id=uuid4()))


def rows(engine: Engine, tenant: UUID) -> list[Any]:
    with engine.connect() as connection:
        return list(
            connection.execute(
                text(
                    "SELECT usage_date, workspace, caller, application, requests, input_tokens, "
                    "provider, account_id, model, as_of, collected_at FROM ai_usage_daily "
                    "WHERE tenant_id = :t ORDER BY usage_date, workspace, caller"
                ),
                {"t": tenant},
            ).all()
        )


class Fewer:
    """The fake's logs, with one caller gone, as a rerun would read them after it stopped."""

    def __init__(self, gone: str) -> None:
        self._gone = gone

    def usage(
        self, account: AccountKey, region: str, start: datetime, end: datetime
    ) -> Iterable[AiUsage]:
        return [
            row
            for row in FakeInvocationLogs(at=NOW).usage(account, region, start, end)
            if row.caller != self._gone
        ]


def test_a_day_of_logs_lands_as_one_row_per_caller(engine: Engine, tenant_id: UUID) -> None:
    outcome = run(engine, unit(tenant_id))

    found = rows(engine, tenant_id)
    assert outcome.items_written == len(CALLERS) == len(found)
    assert {row.caller for row in found} == {caller.caller for caller in CALLERS}
    assert {row.application for row in found} == {"support-assistant", ""}
    first = found[0]
    assert (first.provider, first.account_id, first.workspace) == (
        "bedrock",
        SUPPORT_ACCOUNT,
        REGION,
    )
    assert first.usage_date == DAY.date()
    assert (first.as_of, first.collected_at) == (NEXT_DAY, NOW)
    assert all(row.requests > 0 and row.input_tokens > 0 for row in found)


def test_a_rerun_removes_a_caller_that_stopped_and_only_that(
    engine: Engine, tenant_id: UUID
) -> None:
    run(engine, unit(tenant_id))
    run(engine, unit(tenant_id, region=OTHER_REGION))
    run(engine, unit(tenant_id, day=DAY - timedelta(days=1)))
    before = rows(engine, tenant_id)

    gone = CALLERS[-1].caller
    outcome = run(engine, unit(tenant_id), source=Fewer(gone))

    after = rows(engine, tenant_id)
    assert outcome.items_removed == 1
    removed = {(r.usage_date, r.workspace, r.caller) for r in before} - {
        (r.usage_date, r.workspace, r.caller) for r in after
    }
    assert removed == {(DAY.date(), REGION, gone)}, "another day or Region went with it"


def test_another_providers_rows_are_not_this_runs_to_remove(
    engine: Engine, tenant_id: UUID
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO ai_usage_daily (tenant_id, ingest_run_id, provider, account_id, "
                "usage_date, model, input_tokens, output_tokens, cache_read_tokens, "
                "cache_write_tokens, as_of, collected_at) VALUES (:t, :r, 'openai', :a, :d, "
                "'gpt-fake', 1, 1, 0, 0, :at, :at)"
            ),
            {"t": tenant_id, "r": uuid4(), "a": SUPPORT_ACCOUNT, "d": DAY.date(), "at": NEXT_DAY},
        )
    run(engine, unit(tenant_id))
    assert {row.provider for row in rows(engine, tenant_id)} == {"bedrock", "openai"}


@pytest.mark.parametrize(
    ("account", "where"), [("fake-product-a", "S3 only"), ("fake-platform-b", "nowhere")]
)
def test_an_account_whose_logs_cannot_be_read_is_not_opted_in_and_writes_nothing(
    engine: Engine, tenant_id: UUID, account: str, where: str
) -> None:
    with pytest.raises(NotOptedIn, match=where):
        run(engine, unit(tenant_id, account=account))
    assert rows(engine, tenant_id) == []


def test_usage_past_its_window_is_removed_and_the_rest_kept(
    engine: Engine, tenant_id: UUID, settings: Any
) -> None:
    old = AiUsage(
        tenant_id=tenant_id,
        provider="bedrock",
        account_id=SUPPORT_ACCOUNT,
        usage_date=(NOW - timedelta(days=settings.retention_ai_usage_days + 1)).date(),
        model="m",
        input_tokens=1,
        as_of=NOW - timedelta(days=400),
        collected_at=NOW - timedelta(days=400),
    )
    fresh = replace(old, usage_date=(NOW - timedelta(days=30)).date())

    class Planted:
        def usage(self, *_args: Any) -> list[AiUsage]:
            return [old, fresh]

    run(engine, unit(tenant_id), source=Planted())
    with engine.begin() as connection:
        outcome = retention_ai_usage(
            CollectorContext(unit=unit(tenant_id), connection=connection, settings=settings),
            clock=lambda: NOW,
        )
    assert outcome.items_written == 1
    assert [row.usage_date for row in rows(engine, tenant_id)] == [fresh.usage_date]
