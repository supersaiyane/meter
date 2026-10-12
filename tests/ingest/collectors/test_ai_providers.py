"""An AI provider's cost and usage for every connected organization. TASK-P13-004, FEAT-083.

The collector runs on the fake OpenAI organization. Its cost lands beside the bill as FOCUS rows
of its own source and its usage beside Bedrock's; a rerun removes only what that organization
withdrew; one organization failing is typed under its own scope and never fails another; and a
provider nobody connected reads nothing and claims nothing.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.domain.ai import AiUsage, ProviderAccount
from finops_core.domain.cost import CostRecord
from finops_core.errors import AccessDenied, Unreachable
from finops_fakes.ai import FAKE_ANTHROPIC, FAKE_OPENAI, FakeProviderReports
from finops_fakes.cur import ESTATE, FakeCostExport
from finops_ingest.ai_accounts import connected
from finops_ingest.collectors.ai_providers import AiProviderCollector, period_of
from finops_ingest.collectors.anthropic_usage import anthropic_collector
from finops_ingest.collectors.cost_focus import CostFocusCollector
from finops_ingest.collectors.partitions import ensure_partition
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.registry import CollectorContext, CollectorOutcome

pytestmark = pytest.mark.integration

END = datetime(2026, 8, 24, tzinfo=UTC)
NOW = datetime(2026, 8, 24, 6, 0, tzinfo=UTC)
SECOND = replace(FAKE_OPENAI, organization_id="org-fake-second", name="A second organization")


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """This module creates partitions, so it gives them back. See conftest."""


def unit(tenant: UUID) -> WorkUnit:
    return WorkUnit(
        tenant_id=tenant,
        collector="openai_usage",
        window_start=END - timedelta(days=1),
        window_end=END,
    )


class Failing:
    def __init__(self, failure: Exception) -> None:
        self._failure = failure

    def costs(self, *_args: Any) -> Iterable[CostRecord]:
        raise self._failure

    def usage(self, *_args: Any) -> Iterable[AiUsage]:
        raise self._failure


class Withdrawn:
    """The fake's reports with one project's lines gone, as a rerun after a restatement reads."""

    def __init__(self, project: str) -> None:
        self._project = project
        self._fake = FakeProviderReports(at=NOW)

    def costs(
        self, account: ProviderAccount, start: datetime, end: datetime
    ) -> Iterable[CostRecord]:
        rows = self._fake.costs(account, start, end)
        return [row for row in rows if row.sub_account_id != self._project]

    def usage(self, account: ProviderAccount, start: datetime, end: datetime) -> Iterable[AiUsage]:
        return [
            row for row in self._fake.usage(account, start, end) if row.workspace != self._project
        ]


def run(
    engine: Engine,
    tenant: UUID,
    accounts: tuple[ProviderAccount, ...] = (FAKE_OPENAI,),
    reports: dict[str, Any] | None = None,
) -> CollectorOutcome:
    chosen = reports or {}
    collector = AiProviderCollector(
        name="openai_usage",
        provider="openai",
        reports_for=lambda _c, account: chosen.get(
            account.organization_id, FakeProviderReports(at=NOW)
        ),
        accounts=lambda _connection, _tenant: accounts,
        clock=lambda: NOW,
    )
    with engine.begin() as connection:
        ensure_partition(connection, "cost_focus_daily", period_of(END))
        return collector(CollectorContext(unit=unit(tenant), connection=connection, run_id=uuid4()))


def scalar(engine: Engine, sql: str, tenant: UUID) -> Any:
    with engine.connect() as connection:
        return connection.execute(text(sql), {"t": tenant}).scalar_one()


def test_the_period_to_date_lands_as_cost_and_usage_of_its_own_source(
    engine: Engine, tenant_id: UUID
) -> None:
    outcome = run(engine, tenant_id)

    cost_rows = scalar(
        engine,
        "SELECT count(*) FROM cost_focus_daily WHERE tenant_id = :t AND ingest_source = 'openai'",
        tenant_id,
    )
    usage_rows = scalar(
        engine,
        "SELECT count(*) FROM ai_usage_daily WHERE tenant_id = :t AND provider = 'openai'",
        tenant_id,
    )
    days = (END - datetime(2026, 8, 1, tzinfo=UTC)).days
    assert cost_rows > 0 and usage_rows > 0
    assert outcome.items_written == cost_rows + usage_rows
    distinct_days = scalar(
        engine,
        "SELECT count(DISTINCT charge_period_start) FROM cost_focus_daily WHERE tenant_id = :t",
        tenant_id,
    )
    assert distinct_days == days
    accounts = scalar(
        engine,
        "SELECT count(DISTINCT billing_account_id) FROM cost_focus_daily WHERE tenant_id = :t",
        tenant_id,
    )
    assert accounts == 1
    monthly = scalar(
        engine, "SELECT count(*) FROM cost_focus_monthly WHERE tenant_id = :t", tenant_id
    )
    assert monthly > 0, "the month was not rolled up with the rows it aggregates"


def test_a_rerun_removes_what_the_organization_withdrew_and_nothing_else(
    engine: Engine, tenant_id: UUID
) -> None:
    run(engine, tenant_id, accounts=(FAKE_OPENAI, SECOND))
    before = scalar(engine, "SELECT count(*) FROM cost_focus_daily WHERE tenant_id = :t", tenant_id)

    outcome = run(
        engine,
        tenant_id,
        accounts=(FAKE_OPENAI, SECOND),
        reports={FAKE_OPENAI.organization_id: Withdrawn("proj-search")},
    )

    after = scalar(engine, "SELECT count(*) FROM cost_focus_daily WHERE tenant_id = :t", tenant_id)
    gone = before - after
    assert gone > 0 and outcome.items_removed > gone, "usage rows should have gone too"
    kept = scalar(
        engine,
        "SELECT count(*) FROM cost_focus_daily WHERE tenant_id = :t "
        "AND billing_account_id = 'org-fake-second' AND sub_account_id = 'proj-search'",
        tenant_id,
    )
    assert kept > 0, "the second organization's rows went with the first's"


def test_one_organization_failing_is_typed_and_the_other_is_read(
    engine: Engine, tenant_id: UUID
) -> None:
    outcome = run(
        engine,
        tenant_id,
        accounts=(FAKE_OPENAI, SECOND),
        reports={SECOND.organization_id: Failing(AccessDenied(scope_key="x", collector="y"))},
    )

    assert outcome.items_written > 0
    with engine.connect() as connection:
        failures = connection.execute(
            text("SELECT scope_key, error_type FROM sync_error WHERE tenant_id = :t"),
            {"t": tenant_id},
        ).all()
    assert [tuple(row) for row in failures] == [("openai:org-fake-second", "AccessDenied")]

    run(engine, tenant_id, accounts=(FAKE_OPENAI, SECOND))
    assert scalar(engine, "SELECT count(*) FROM sync_error WHERE tenant_id = :t", tenant_id) == 0


def test_every_organization_failing_fails_the_run_typed(engine: Engine, tenant_id: UUID) -> None:
    failing = Failing(Unreachable(scope_key="x", collector="y"))
    with pytest.raises(Unreachable):
        run(engine, tenant_id, reports={FAKE_OPENAI.organization_id: failing})


def test_a_provider_nobody_connected_reads_nothing(engine: Engine, tenant_id: UUID) -> None:
    assert run(engine, tenant_id, accounts=()) == CollectorOutcome()


def test_the_connected_organizations_are_the_tenants_active_ones(
    engine: Engine, tenant_id: UUID
) -> None:
    # The organization is the table's key across tenants, so each test's are its own.
    a, b, gone = (f"org-{name}-{tenant_id}" for name in ("a", "b", "gone"))
    with engine.begin() as connection:
        for organization, active in ((b, True), (a, True), (gone, False)):
            connection.execute(
                text(
                    "INSERT INTO ai_provider_account (provider, organization_id, tenant_id, name, "
                    "key_secret_name, enrolled_at, active) VALUES ('openai', :o, :t, :o, "
                    "'meter/test/ai/k', :now, :active)"
                ),
                {"o": organization, "t": tenant_id, "now": NOW, "active": active},
            )
        found = connected(connection, tenant_id, "openai")
        anthropic = connected(connection, tenant_id, "anthropic")
    assert [account.organization_id for account in found] == [a, b]
    assert anthropic == ()


@pytest.mark.parametrize(
    "secret", ["meter/test/database", "other/test/ai/k", "meter/Test/ai/k", "meter/test/ai/"]
)
def test_a_key_outside_the_ai_path_cannot_be_recorded(
    engine: Engine, tenant_id: UUID, secret: str
) -> None:
    with pytest.raises(Exception, match="key_under_the_ai_path"), engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO ai_provider_account (provider, organization_id, tenant_id, name, "
                "key_secret_name, enrolled_at) VALUES ('openai', :o, :t, 'x', :s, :now)"
            ),
            {"o": f"org-{tenant_id}", "t": tenant_id, "s": secret, "now": NOW},
        )


def test_a_providers_run_leaves_the_bills_rows_and_anthropic_lands_beside_openai(
    engine: Engine, tenant_id: UUID
) -> None:
    """TASK-P13-005. The bill's rows survive a provider's restatement, and two providers' sit
    side by side, each under its own source."""
    bill = tuple(row for row in ESTATE if row.billing_period_start == period_of(END))
    with engine.begin() as connection:
        ensure_partition(connection, "cost_focus_daily", period_of(END))
        CostFocusCollector(FakeCostExport(rows=bill), clock=lambda: NOW)(
            CollectorContext(unit=unit(tenant_id), connection=connection, run_id=uuid4())
        )
    run(engine, tenant_id)
    anthropic = anthropic_collector(
        lambda _c, _a: FakeProviderReports(at=NOW),
        accounts=lambda _connection, _tenant: (FAKE_ANTHROPIC,),
        clock=lambda: NOW,
    )
    with engine.begin() as connection:
        anthropic(CollectorContext(unit=unit(tenant_id), connection=connection, run_id=uuid4()))
    run(engine, tenant_id)

    with engine.connect() as connection:
        by_source: dict[str, int] = dict(
            connection.execute(
                text(
                    "SELECT ingest_source, count(*) FROM cost_focus_daily WHERE tenant_id = :t "
                    "GROUP BY ingest_source"
                ),
                {"t": tenant_id},
            ).all()
        )
        workspaces = set(
            connection.execute(
                text(
                    "SELECT workspace FROM ai_usage_daily WHERE tenant_id = :t "
                    "AND provider = 'anthropic'"
                ),
                {"t": tenant_id},
            ).scalars()
        )
    assert by_source["aws_export"] == len(bill)
    assert by_source["openai"] > 0 and by_source["anthropic"] > 0
    assert workspaces == {"wrkspc-fake-agents", ""}, "the default workspace reads as no id"
