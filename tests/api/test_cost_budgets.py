"""Budget against actual, and the four times it refuses to be green.

FEAT-060. Over a real database.

The status is the one figure an executive will look at and nothing else, so the cases that
carry this file are the ones where it declines to answer. A green light on a budget nobody
could compute is acted on exactly as readily as a green light on one that was.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.config import Settings
from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.tenant import Scope
from finops_ingest.collectors.partitions import ensure_partition
from tests.api.test_query_routes import auth, client_for

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 26, 6, 0, tzinfo=UTC)
START, END = date(2026, 9, 1), date(2026, 10, 1)
MINE = "111122223333"
PATH = "/api/v1/cost/budgets"

INSERT_BUDGET = text(
    "INSERT INTO budget (budget_pk, tenant_id, ingest_run_id, budget_id, name, scope, "
    "scope_value, limit_amount, currency, period_start, period_end, as_of, collected_at) "
    "VALUES (:pk, :t, :run, :bid, :name, :scope, :value, :limit, 'USD', :start, :end, "
    ":at, :at)"
)
#: Every NOT NULL column, spelled out. The first draft invented a `row_id` and a shorter list,
#: which the database refused: a fixture that guesses at a schema tests the guess.
INSERT_COST = text(
    "INSERT INTO cost_focus_daily (tenant_id, ingest_run_id, source_fingerprint, as_of, "
    "collected_at, billing_account_id, sub_account_id, billing_period_start, "
    "billing_period_end, charge_period_start, charge_period_end, provider_name, "
    "service_name, region_id, resource_id, charge_category, billed_cost, effective_cost, "
    "list_cost, contracted_cost, tags) "
    "VALUES (:t, :run, :fingerprint, :at, :at, :payer, :a, :period, :period_end, :period, "
    ":period, 'aws', :service, 'eu-west-1', :resource, 'Usage', :cost, :cost, :cost, :cost, "
    "'{}'::jsonb)"
)


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """This module writes cost rows, and `cost_focus_daily` is partitioned by month, so it
    creates its partition and gives it back. See conftest."""


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID


def everything(tenant: UUID) -> Scope:
    return Scope(tenant_id=tenant, is_global=True, accounts=frozenset())


def only(tenant: UUID, account: str) -> Scope:
    return Scope(
        tenant_id=tenant,
        is_global=False,
        accounts=frozenset({AccountKey(provider=Provider.AWS, account_id=account)}),
    )


def budget(
    engine: Engine,
    tenant: UUID,
    *,
    name: str = "All accounts",
    scope: str = "ALL",
    value: str = "",
    limit: str = "1000",
) -> None:
    with engine.begin() as connection:
        connection.execute(
            INSERT_BUDGET,
            {
                "pk": uuid4(),
                "t": tenant,
                "run": uuid4(),
                "bid": name,
                "name": name,
                "scope": scope,
                "value": value,
                "limit": Decimal(limit),
                "start": START,
                "end": END,
                "at": NOW,
            },
        )


def spend(
    engine: Engine, tenant: UUID, *, amount: str, account: str = MINE, service: str = "AmazonEC2"
) -> None:
    with engine.begin() as connection:
        ensure_partition(connection, "cost_focus_daily", START)
        connection.execute(
            INSERT_COST,
            {
                "t": tenant,
                "run": uuid4(),
                "fingerprint": uuid4().hex,
                "payer": MINE,
                "a": account,
                "period": START,
                "period_end": END,
                "service": service,
                "resource": f"r-{uuid4().hex[:8]}",
                "cost": Decimal(amount),
                "at": NOW,
            },
        )


def get(engine: Engine, tenant: UUID, settings: Settings, scope: Scope | None = None) -> Any:
    client, token = client_for(engine, scope or everything(tenant), settings)
    response = client.get(PATH, headers=auth(token))
    assert response.status_code == 200, response.text
    return response.json()["data"]


def one(engine: Engine, tenant: UUID, settings: Settings) -> Any:
    found = get(engine, tenant, settings)["budgets"]
    assert len(found) == 1, found
    return found[0]


# --- the refusals to be green -----------------------------------------------


def test_a_budget_with_no_collected_spend_is_unknown_not_under(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """An estate whose first ingest has not run has not spent nothing. Rendering that as under
    budget is the same defect as rendering a failed collection as a zero."""
    budget(engine, tenant_id)
    found = one(engine, tenant_id, settings)
    assert found["actual"] is None
    assert found["status"] == "UNKNOWN"
    assert found["used"] is None


def test_a_budget_this_product_cannot_join_gets_no_status(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """A budget over a tag expression, over several accounts, or measuring usage rather than
    cost. Matching it against the wrong spend would be worse than showing no number, because a
    green light on the wrong number is acted on."""
    budget(engine, tenant_id, name="Cost centre 4471", scope="UNSUPPORTED")
    spend(engine, tenant_id, amount="100")
    body = get(engine, tenant_id, settings)
    assert body["budgets"][0]["status"] == "UNKNOWN"
    assert body["budgets"][0]["actual"] is None
    # And counted, because an estate with ten of these is not an estate with no budgets.
    assert body["unsupported"] == 1


def test_an_account_the_bill_does_not_mention_is_unknown_not_zero(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Constraint 5 applied to a join. An account absent from the bill is one the bill does not
    mention, not one that was free, and a budget judged against a zero reads as healthy."""
    budget(engine, tenant_id, name="Quiet team", scope="ACCOUNT", value="999988887777")
    spend(engine, tenant_id, amount="500")
    found = one(engine, tenant_id, settings)
    assert found["actual"] is None
    assert found["status"] == "UNKNOWN"


def test_a_narrowed_reader_reads_no_budgets_at_all(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """ADR-0025. A budget is set at the payer and the API reporting it is a payer API, so it
    inherits that scoping: a narrowed reader reads nothing rather than a number that is not
    theirs.

    A 404, which is the same answer `/cost/commitments` gives a narrowed reader and for the
    same reason. An empty list would be a different claim: it would say the payer has no
    budgets, when what is true is that this reader may not see them.
    """
    budget(engine, tenant_id)
    client, token = client_for(engine, only(tenant_id, MINE), settings)
    assert client.get(PATH, headers=auth(token)).status_code == 404


def test_coverage_is_the_payer_so_a_whole_estate_is_never_called_partial(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """ISS-293. A budget belongs to the payer, so its coverage is one payer of one. Counted in
    accounts it read 1 of 5 for a reader who sees all five, and the front page said so."""
    budget(engine, tenant_id)
    spend(engine, tenant_id, amount="100")
    client, token = client_for(engine, everything(tenant_id), settings)
    response = client.get(PATH, headers=auth(token))
    coverage = response.json()["meta"]["scope_coverage"]
    assert (coverage["visible"], coverage["total"], coverage["unit"]) == (1, 1, "payer")
    assert coverage["is_partial"] is False


# --- the three it does answer ------------------------------------------------


def test_spending_at_pace_is_under(engine: Engine, tenant_id: UUID, settings: Settings) -> None:
    budget(engine, tenant_id, limit="10000")
    spend(engine, tenant_id, amount="100")
    found = one(engine, tenant_id, settings)
    assert found["status"] == "UNDER"
    assert Decimal(found["actual"]) == Decimal("100")


def test_spending_the_whole_limit_is_over(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    budget(engine, tenant_id, limit="100")
    spend(engine, tenant_id, amount="250")
    found = one(engine, tenant_id, settings)
    assert found["status"] == "OVER"
    assert Decimal(found["used"]) > 1


def test_a_service_budget_is_judged_against_that_service_alone(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Through `GROUPABLE`, the same mapping the cost screen groups by, so a budget over a
    service is compared against exactly the number that screen shows for it."""
    budget(engine, tenant_id, name="Databases", scope="SERVICE", value="AmazonRDS", limit="100")
    spend(engine, tenant_id, amount="80", service="AmazonRDS")
    spend(engine, tenant_id, amount="900", service="AmazonEC2")
    found = one(engine, tenant_id, settings)
    assert Decimal(found["actual"]) == Decimal("80")
    assert found["status"] != "OVER"


# --- the working, published --------------------------------------------------


def test_the_pace_denominator_is_on_the_wire(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The status rests on how far through the period we are, so that figure travels with it.
    A status a reader cannot reproduce is one they either take or ignore, and the whole
    argument for pace over a forecast is that anybody can check the arithmetic."""
    budget(engine, tenant_id)
    found = one(engine, tenant_id, settings)
    assert Decimal("0") <= Decimal(found["elapsed"]) <= Decimal("1")
    assert found["period_start"] == "2026-09-01"
    assert found["period_end"] == "2026-10-01"
