"""P13's exit criteria, read through the API over the seeded demo. TASK-P13-009, spec section 13.

The local stack is seeded by `scripts/demo/seed_demo.py`, so the demo is what a person running it
meets. Each criterion is read here through the AI endpoints a person's screen reads, as the whole
estate's reader, rather than from the tables the collectors wrote.

Criterion 5, that only the worker reaches the internet, is held by the Terraform itself in
`tests/contract/test_network_paths.py`. That a provider's cost survives an AWS cost run is held by
`tests/ingest/collectors/test_ai_providers.py`, which runs the bill, OpenAI and Anthropic into one
period and finds each source's rows intact. The screen's labels are held by
`finops-web/src/screens/__tests__/AiSpendScreen.test.tsx` and `finops-web/e2e/ai.spec.ts`.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Engine, text

from finops_core.config import Settings
from finops_fakes import cur
from tests.api.test_query_routes import client_for
from tests.api.test_waste_routes import everything, get
from tests.scripts.test_seed_demo import DEMO_TENANT, _now, seed_demo

pytestmark = pytest.mark.integration

SPEND = "/api/v1/ai/spend"
GROUPINGS = ("provider", "model", "token_type", "feature", "caller")


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """The seed bills months into partitions, so this module gives them back. ISS-268."""


@pytest.fixture
def demo(engine: Engine, settings: Settings) -> Iterator[Any]:
    seed_demo.seed(engine, settings, _now())
    client, token = client_for(engine, everything(DEMO_TENANT), settings)
    try:
        yield lambda path: get(client, token, path)
    finally:
        seed_demo.remove(engine)


def test_1_a_bedrock_line_lands_with_its_model_tokens_and_principal_and_groups_each_way(
    engine: Engine, demo: Any
) -> None:
    with engine.connect() as connection:
        landed = connection.execute(
            text(
                "SELECT count(*) FROM cost_focus_daily WHERE tenant_id = :t AND x_ai_model "
                "IS NOT NULL AND x_ai_token_type IS NOT NULL AND x_ai_tokens IS NOT NULL "
                "AND x_iam_principal IS NOT NULL"
            ),
            {"t": DEMO_TENANT},
        ).scalar_one()
    assert landed > 0
    names = {
        grouping: {row["name"] for row in demo(f"{SPEND}?group_by={grouping}")["data"]["rows"]}
        for grouping in GROUPINGS
    }
    assert all(names.values()), "every grouping answers"
    assert {feature.model for feature in cur.BEDROCK_FEATURES} <= names["model"]
    assert {"input", "output"} <= names["token_type"]
    assert {cur.bedrock_principal(feature) for feature in cur.BEDROCK_FEATURES} <= names["caller"]


def test_2_callers_land_where_logs_reach_cloudwatch_and_not_opted_in_where_not(
    engine: Engine, demo: Any
) -> None:
    callers = demo("/api/v1/ai/callers")["data"]["callers"]
    logged = {row["account_id"] for row in callers if row["source"] == "bedrock"}
    assert logged == {"fake-platform-a"}, "fake-product-a sends its logs to S3 only"
    with engine.connect() as connection:
        refused = connection.execute(
            text(
                "SELECT scope_key FROM sync_error WHERE tenant_id = :t "
                "AND collector = 'bedrock_invocations' AND error_type = 'NotOptedIn'"
            ),
            {"t": DEMO_TENANT},
        ).scalars()
        assert any("fake-product-a" in key for key in refused)


def test_3_each_providers_cost_and_its_usage_per_model_workspace_and_key(demo: Any) -> None:
    providers = {row["name"] for row in demo(f"{SPEND}?group_by=provider")["data"]["rows"]}
    assert {"OpenAI", "Anthropic"} <= providers
    callers = demo("/api/v1/ai/callers")["data"]["callers"]
    for source in ("openai", "anthropic"):
        used = [row for row in callers if row["source"] == source]
        assert used, source
        # Per model, project or workspace, and key: the default workspace has no id, so the key is
        # what every row is held to, and some row names its project or workspace.
        assert all(row["model"] and row["api_key_id"] for row in used), source
        assert any(row["workspace"] for row in used), source


def test_4_gpu_instances_show_hours_cost_and_utilization_or_not_published(demo: Any) -> None:
    instances = {row["instance_id"]: row for row in demo("/api/v1/ai/gpu")["data"]["instances"]}
    assert set(instances) == {gpu.instance_id for gpu in cur.GPU_INSTANCES}
    for row in instances.values():
        assert Decimal(row["hours"]) > 0 and Decimal(row["cost"]) > 0
    assert instances["i-fakegpu0001"]["average_percent"] is not None
    silent = instances["i-fakegpu0002"]
    assert (silent["utilization"], silent["average_percent"]) == ("not published", None)


def test_6_every_unit_cost_says_measured_or_modelled(demo: Any) -> None:
    for grouping in GROUPINGS:
        for row in demo(f"{SPEND}?group_by={grouping}")["data"]["rows"]:
            for figure in ("tokens", "cost_per_1k_tokens", "cost_per_request"):
                basis = row[f"{figure}_basis"]
                assert (row[figure] is None) == (basis is None), (grouping, row["name"], figure)
                assert basis in {None, "measured", "modelled"}
            assert row["cost_per_request_basis"] in {None, "modelled"}
    by_provider = {row["name"]: row for row in demo(f"{SPEND}?group_by=provider")["data"]["rows"]}
    assert by_provider["OpenAI"]["tokens_basis"] == "modelled"
    measured = [row for row in by_provider.values() if row["tokens_basis"] == "measured"]
    assert measured, "the bill's own lines count their tokens"
