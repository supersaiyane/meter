"""The answer set. Every figure an answer shows is the figure the screen shows.

P7 spec section 11, set one. Not that the prose is right, which is not testable, but that
no figure differs from the deterministic one, which is the whole claim of section 5.2.

The expected figure is read from the route the screen reads, with the same token, and
compared exactly: Decimal against Decimal and no tolerance, because a tolerance is where
a wrong figure hides. For cost, the deterministic layer is the repository behind that
route, so the screen is the reference rather than a second computation that could agree
with the first by sharing its mistake. Every case also runs the provenance test.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import Engine

from finops_core.config import Settings
from finops_core.domain.insight import Provenance, Unit
from finops_fakes.containers import PLATFORM_EKS
from tests.query.insight.harness import (
    IN_SCOPE,
    answer,
    ask_as,
    asker,
    assert_cited_from_real_results,
    call,
    everything,
    only,
    screen,
    seed_bill,
)

pytestmark = pytest.mark.integration


def test_the_most_expensive_service_is_the_one_the_screen_ranks_first(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed_bill(engine, tenant_id, split=False)
    client, token = asker(engine, settings, everything(tenant_id))
    shown = screen(client, token, "/cost/by-service")
    top = max(shown["data"], key=lambda row: Decimal(str(row["effective_cost"])))
    row = f"data[name={top['name']}]"

    exchange, _ = ask_as(
        client,
        token,
        "Which service cost the most last month?",
        call("t1", "get_cost_by_service"),
        answer(
            "{{service}} cost the most last month, at {{cost}}.",
            service=("t1", f"{row}.name"),
            cost=("t1", f"{row}.effective_cost"),
        ),
    )

    outcome = assert_cited_from_real_results(exchange)
    cited = {citation.placeholder: citation for citation in outcome.citations}
    assert cited["service"].value == top["name"]
    assert cited["cost"].value == Decimal(str(top["effective_cost"]))
    assert cited["cost"].provenance is Provenance.MEASURED
    assert cited["cost"].as_of == datetime.fromisoformat(shown["meta"]["as_of"])
    # As the tool table declares them, ISS-231: dollars for the cost, nothing for the name.
    assert (cited["cost"].unit, cited["service"].unit) == (Unit.USD, None)
    # Spec section 11's cost test, in its first place: an exchange that reached a model
    # says what it spent, in both directions, and neither is zero.
    assert exchange.usage.input_tokens > 0
    assert exchange.usage.output_tokens > 0


def test_one_accounts_cost_is_the_figure_its_row_shows(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed_bill(engine, tenant_id, split=False)
    client, token = asker(engine, settings, only(tenant_id, IN_SCOPE))
    shown = screen(client, token, "/cost/by-account")
    (expected,) = [row for row in shown["data"] if row["name"] == IN_SCOPE]

    exchange, _ = ask_as(
        client,
        token,
        f"What did {IN_SCOPE} cost last month?",
        call("t1", "get_cost_by_account"),
        answer(
            "That account cost {{cost}} last month.",
            cost=("t1", f"data[name={IN_SCOPE}].effective_cost"),
        ),
    )

    (cost,) = assert_cited_from_real_results(exchange).citations
    assert cost.value == Decimal(str(expected["effective_cost"]))
    assert cost.tool == "get_cost_by_account"


def test_how_much_of_the_organization_a_figure_covers_is_the_screens_coverage(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The figure most worth getting right. A partial total stated as complete is the
    failure every screen here guards against, and the assistant must say it too."""
    seed_bill(engine, tenant_id, split=False)
    client, token = asker(engine, settings, only(tenant_id, IN_SCOPE))
    coverage = screen(client, token, "/cost/by-account")["meta"]["scope_coverage"]

    exchange, _ = ask_as(
        client,
        token,
        "How much of the organization do these cost figures cover?",
        call("t1", "get_cost_by_account"),
        answer(
            "These figures cover {{visible}} of {{total}} accounts.",
            visible=("t1", "meta.scope_coverage.visible"),
            total=("t1", "meta.scope_coverage.total"),
        ),
    )

    citations = assert_cited_from_real_results(exchange).citations
    cited = {c.placeholder: c.value for c in citations}
    assert cited == {"visible": Decimal(coverage["visible"]), "total": Decimal(coverage["total"])}
    assert {c.unit for c in citations} == {Unit.COUNT}, "a coverage figure counts accounts"


def test_a_clusters_unrequested_capacity_is_the_figure_the_cost_screen_shows(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed_bill(engine, tenant_id, split=True)
    client, token = asker(engine, settings, everything(tenant_id))
    shown = screen(client, token, "/cost/containers")
    (cluster,) = [c for c in shown["data"]["clusters"] if c["cluster_name"] == PLATFORM_EKS.name]

    exchange, _ = ask_as(
        client,
        token,
        "How much of the platform cluster did nothing ask for?",
        call("t1", "get_container_cost"),
        answer(
            "Capacity no workload requested cost {{idle}} last month.",
            idle=("t1", f"data.clusters[cluster_name={PLATFORM_EKS.name}].unallocated"),
        ),
    )

    (idle,) = assert_cited_from_real_results(exchange).citations
    assert idle.value == Decimal(str(cluster["unallocated"]))
    assert idle.provenance is Provenance.MEASURED
    assert idle.unit is Unit.USD, "money under a name that does not say so, declared by its tool"
