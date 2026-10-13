"""The AI spend routes, read through the API as a person reads them. TASK-P13-007, FEAT-085.

The tenant's AI spend is planted by running P13's collectors on the fake estate for one billing
period: the bill's Bedrock and GPU lines, the fake OpenAI organization's cost and usage, a day of
invocation logs and a day of GPU utilization. Then each route is read by a reader of the whole
estate and by one narrowed to an account: a provider's spend, which no account grant names, is
the whole reader's only, and every figure says how it was arrived at.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.config import Settings
from finops_core.domain.account import AccountKey, Provider
from finops_fakes import fixtures
from finops_fakes.ai import FAKE_OPENAI, FakeGpuMetrics, FakeInvocationLogs, FakeProviderReports
from finops_fakes.cur import CLOSED_PERIOD, ESTATE, FakeCostExport
from finops_ingest.collectors.ai_usage import BedrockInvocationsCollector
from finops_ingest.collectors.cost_focus import CostFocusCollector
from finops_ingest.collectors.gpu_utilization import GpuUtilizationCollector
from finops_ingest.collectors.openai_usage import openai_collector
from finops_ingest.collectors.partitions import ensure_partition
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.registry import CollectorContext
from tests.api.test_query_routes import auth, client_for
from tests.api.test_waste_routes import everything, get, only

pytestmark = pytest.mark.integration

SPEND = "/api/v1/ai/spend"
CALLERS = "/api/v1/ai/callers"
GPU = "/api/v1/ai/gpu"
CLOSED = tuple(row for row in ESTATE if row.billing_period_start == CLOSED_PERIOD)
LAST_DAY = max(row.charge_period_start for row in CLOSED)
PERIOD_END = LAST_DAY + timedelta(days=1)
NOW = PERIOD_END + timedelta(hours=6)
ACCOUNT = "fake-platform-a"


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """This module creates partitions, so it gives them back. See conftest."""


def run(engine: Engine, collector: Any, work: WorkUnit) -> None:
    with engine.begin() as connection:
        ensure_partition(connection, "cost_focus_daily", CLOSED_PERIOD)
        collector(CollectorContext(unit=work, connection=connection, run_id=uuid4()))


def unit(tenant: UUID, collector: str, account: str | None = None) -> WorkUnit:
    return WorkUnit(
        tenant_id=tenant,
        collector=collector,
        window_start=LAST_DAY,
        window_end=PERIOD_END,
        account=None if account is None else AccountKey(provider=Provider.AWS, account_id=account),
        region=None if account is None else fixtures.REGION,
    )


def clock() -> datetime:
    return NOW


@pytest.fixture
def planted(engine: Engine, tenant_id: UUID) -> UUID:
    run(
        engine,
        CostFocusCollector(FakeCostExport(rows=CLOSED, ai=True), clock=clock),
        unit(tenant_id, "cost_focus"),
    )
    provider = openai_collector(
        lambda _c, _a: FakeProviderReports(at=NOW),
        accounts=lambda _connection, _tenant: (FAKE_OPENAI,),
        clock=clock,
    )
    run(engine, provider, unit(tenant_id, "openai_usage"))
    logs = BedrockInvocationsCollector(FakeInvocationLogs(at=NOW), clock=clock)
    run(engine, logs, unit(tenant_id, "bedrock_invocations", ACCOUNT))
    gpu = GpuUtilizationCollector(FakeGpuMetrics(at=NOW), clock=clock)
    run(engine, gpu, unit(tenant_id, "gpu_utilization", ACCOUNT))
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO ai_provider_account (provider, organization_id, tenant_id, name, "
                "key_secret_name, enrolled_at) VALUES ('openai', :o, :t, 'Fake OpenAI', "
                "'meter/test/ai/openai', :at)"
            ),
            {"o": f"{FAKE_OPENAI.organization_id}-{tenant_id}", "t": tenant_id, "at": NOW},
        )
    return tenant_id


def read(engine: Engine, settings: Settings, tenant: UUID, path: str, account: str = "") -> Any:
    scope = only(tenant, account) if account else everything(tenant)
    client, token = client_for(engine, scope, settings)
    return get(client, token, path)


def test_spend_by_provider_is_the_bill_and_the_providers_side_by_side(
    engine: Engine, settings: Settings, planted: UUID
) -> None:
    found = read(engine, settings, planted, SPEND)
    data = found["data"]
    assert data["period"] == CLOSED_PERIOD.isoformat()
    by_name = {row["name"]: row for row in data["rows"]}
    assert set(by_name) == {"Fake", "OpenAI"}
    assert Decimal(data["total_cost"]) == sum(Decimal(row["cost"]) for row in data["rows"])
    # The cloud bill counts its own tokens; OpenAI's come from its usage report.
    assert by_name["Fake"]["tokens_basis"] == "measured"
    assert by_name["OpenAI"]["tokens_basis"] == "modelled"
    assert by_name["OpenAI"]["cost_per_request_basis"] == "modelled"
    assert [one["provider"] for one in data["connected"]] == ["openai"]
    assert "key_secret_name" not in data["connected"][0]
    assert found["meta"]["as_of"] is not None and found["meta"]["collected_at"] is not None


def test_spend_by_model_matches_the_logs_requests_to_the_bills_model(
    engine: Engine, settings: Settings, planted: UUID
) -> None:
    rows = read(engine, settings, planted, f"{SPEND}?group_by=model")["data"]["rows"]
    sonnet = next(row for row in rows if row["name"] == "ClaudeSonnet4")
    assert sonnet["requests"], "the log's model id met the bill's name"
    assert (sonnet["cost_per_1k_tokens_basis"], sonnet["cost_per_request_basis"]) == (
        "measured",
        "modelled",
    )


@pytest.mark.parametrize("group_by", ["token_type", "feature", "caller"])
def test_every_grouping_answers(
    engine: Engine, settings: Settings, planted: UUID, group_by: str
) -> None:
    rows = read(engine, settings, planted, f"{SPEND}?group_by={group_by}")["data"]["rows"]
    assert rows and all(Decimal(row["cost"]) >= 0 for row in rows)


def test_a_reader_narrowed_to_an_account_sees_none_of_a_providers_spend(
    engine: Engine, settings: Settings, planted: UUID
) -> None:
    data = read(engine, settings, planted, SPEND, account=ACCOUNT)["data"]
    assert {row["name"] for row in data["rows"]} == {"Fake"}
    assert data["connected"] == []
    gpu = read(engine, settings, planted, GPU, account="fake-product-b")["data"]
    assert gpu["instances"] == []


def test_callers_are_priced_at_the_bills_unit_cost_and_say_it_is_modelled(
    engine: Engine, settings: Settings, planted: UUID
) -> None:
    callers = read(engine, settings, planted, CALLERS)["data"]["callers"]
    logged = [one for one in callers if one["account_id"] == ACCOUNT]
    assert len(logged) == 3
    assert all(one["modelled_cost_basis"] == "modelled" for one in callers)
    assert all(one["modelled_cost"] is not None for one in logged)
    reported = [one for one in callers if one["source"] == "openai"]
    assert reported and all(one["modelled_cost"] is not None for one in reported)


def test_the_gpu_fleet_says_not_published_rather_than_nought(
    engine: Engine, settings: Settings, planted: UUID
) -> None:
    instances = read(engine, settings, planted, GPU)["data"]["instances"]
    by_id = {one["instance_id"]: one for one in instances}
    assert set(by_id) == {"i-fakegpu0001", "i-fakegpu0002"}
    measured = by_id["i-fakegpu0001"]
    assert measured["utilization"] == "partly published", "one day of the month was read"
    assert Decimal(measured["average_percent"]) == Decimal("18.50")
    silent = by_id["i-fakegpu0002"]
    assert (silent["utilization"], silent["average_percent"]) == ("not published", None)
    assert Decimal(silent["hours"]) > 0 and Decimal(silent["cost"]) > 0


def test_a_tenant_with_no_ai_spend_says_none_was_seen(
    engine: Engine, settings: Settings, tenant_id: UUID
) -> None:
    data = read(engine, settings, tenant_id, SPEND)["data"]
    assert (data["period"], data["total_cost"], data["rows"]) == (None, None, [])
    assert read(engine, settings, tenant_id, GPU)["data"]["instances"] == []


def test_a_period_that_is_not_a_first_day_is_refused(
    engine: Engine, settings: Settings, tenant_id: UUID
) -> None:
    client, token = client_for(engine, everything(tenant_id), settings)
    response = client.get(f"{SPEND}?period=2026-07-15", headers=auth(token))
    assert response.status_code == 422
    assert client.get(f"{SPEND}?group_by=region", headers=auth(token)).status_code == 422


def test_spend_exports(engine: Engine, settings: Settings, planted: UUID) -> None:
    client, token = client_for(engine, everything(planted), settings)
    response = client.get(f"{SPEND}?format=csv", headers=auth(token))
    assert response.status_code == 200
    assert "OpenAI" in response.text


def test_collected_at_is_after_as_of_on_every_route(
    engine: Engine, settings: Settings, planted: UUID
) -> None:
    for path in (SPEND, CALLERS, GPU):
        meta = read(engine, settings, planted, path)["meta"]
        as_of = datetime.fromisoformat(meta["as_of"]).astimezone(UTC)
        collected = datetime.fromisoformat(meta["collected_at"]).astimezone(UTC)
        assert collected >= as_of, path


def test_coverage_counts_the_cloud_accounts_and_never_a_providers_project(
    engine: Engine, settings: Settings, planted: UUID
) -> None:
    """ISS-288: a global reader sees the whole estate, whichever accounts happen to use a model."""
    accounts = len({row.sub_account_id for row in CLOSED})
    every = (SPEND, CALLERS, GPU, "/api/v1/cost/summary", "/api/v1/cost/explore")
    for path in (*every, "/api/v1/cost/anomalies"):
        coverage = read(engine, settings, planted, path)["meta"]["scope_coverage"]
        assert coverage["visible"] == accounts, path
