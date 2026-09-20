"""The commitments route, called rather than imported.

A test that imports a route proves nothing. TASK-P2-021 wrote six routes that
imported cleanly, passed their tests, and returned 500 on every real call, because
the tables they read were not in `SCOPED_TABLES`. That is the standing lesson in
`tasks/lessons.md`, and it is why every test here goes through the client.

Two questions carry this file.

**Does a narrow scope read nothing?** A commitment is bought by the payer and
consumed by whichever accounts ran the usage, and no API reports which, so there is
no honest way to apportion it. Both tables are `PayerWide`, and a viewer restricted
to two accounts must not learn the size of the organization's commitment position.

**Are utilization and coverage still two answers at the payload?** They are stored
apart and read apart, and the last place they could be collapsed into one is here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from finops_core.config import Settings
from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.tenant import Scope
from finops_ingest.collectors.commitment import CommitmentCollector
from finops_ingest.registry import CollectorContext
from finops_providers.fake.commitment import FakeCommitmentReport
from tests.api.test_query_routes import another_tenant, auth, client_for

pytestmark = pytest.mark.integration

#: Inside August, because the collector's month arithmetic decides the window and
#: the fake is sized against August's estate.
NOW = datetime(2026, 8, 24, 6, 0, tzinfo=UTC)
PATH = "/api/v1/cost/commitments"


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID


def seed(engine: Engine, tenant: UUID, report: object | None = None) -> None:
    with engine.begin() as connection:
        CommitmentCollector(report or FakeCommitmentReport(), clock=lambda: NOW)(
            CollectorContext(unit=Unit(tenant_id=tenant), connection=connection, run_id=uuid4())
        )


def everything(tenant: UUID) -> Scope:
    return Scope(tenant_id=tenant, is_global=True, accounts=frozenset())


def only(tenant: UUID, account: str) -> Scope:
    return Scope(
        tenant_id=tenant,
        is_global=False,
        accounts=frozenset({AccountKey(provider=Provider.AWS, account_id=account)}),
    )


def get(client: TestClient, token: str) -> dict[str, Any]:
    response = client.get(PATH, headers=auth(token))
    assert response.status_code == 200, f"{PATH} returned {response.status_code}: {response.text}"
    result = response.json()
    assert isinstance(result, dict)
    return result


class TestItAnswers:
    def test_it_returns_an_envelope_with_both_grains(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        payload = get(client, token)
        assert len(payload["data"]["commitments"]) == 4
        assert len(payload["data"]["coverage"]) == 3
        assert payload["meta"]["as_of"]

    def test_the_worst_waste_is_first(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # Ranked by money, per ADR-0016. A ranking by percentage puts a ten dollar
        # reservation at forty percent above a ten thousand dollar plan at ninety
        # five, and only one of those is worth a morning.
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        rows = get(client, token)["data"]["commitments"]
        wasted = [Decimal(row["wasted"]) for row in rows]
        assert wasted == sorted(wasted, reverse=True)
        assert wasted[0] > Decimal("0")

    def test_the_total_equals_the_rows_it_sits_above(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        found = get(client, token)["data"]
        assert Decimal(found["wasted_total"]) == sum(
            (Decimal(row["wasted"]) for row in found["commitments"]), Decimal("0")
        )


class TestTheCoverageBannerCountsTheRightThing:
    def test_it_reports_a_payer_rather_than_a_count_of_commitments(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """Seen on the screen, not in a test, and the second time in this project.

        The default coverage compares `visible` to the number of accounts in the
        organization. Passing the row count there rendered "4 of 5 accounts" above a
        table of four commitments, exactly as a line item count once rendered
        "showing all 450 accounts" on an estate with five.

        A commitment belongs to the payer and to no account, so the unit is a payer
        and the coverage is complete by construction: this route is only reachable by
        a scope that sees every account.
        """
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        coverage = get(client, token)["meta"]["scope_coverage"]
        assert coverage["unit"] == "payer"
        assert coverage["visible"] == 1
        assert coverage["total"] == 1
        assert coverage["is_partial"] is False


class TestTheTwoFiguresStaySeparate:
    def test_no_commitment_row_carries_a_coverage_figure(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """The last place the two could be collapsed.

        A coverage field on a commitment would be a number nobody measured, because
        a dollar of covered spend cannot be attributed to one of several overlapping
        plans.
        """
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        for row in get(client, token)["data"]["commitments"]:
            assert "coverage" not in row
            assert "covered_spend" not in row
            assert "eligible_spend" not in row

    def test_no_coverage_row_names_a_commitment(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        for row in get(client, token)["data"]["coverage"]:
            assert "commitment_id" not in row
            assert row["dimension"] == "SERVICE"

    def test_a_fully_used_commitment_can_still_cover_little(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """The estate this screen exists for.

        The compute plan is fully utilized, so reading utilization alone says the
        purchase was correct and nothing more is needed. Its service is under half
        covered, so reading coverage alone says buy. Both are true, and a payload
        reporting one number could not say so.
        """
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        found = get(client, token)["data"]
        compute = next(
            row for row in found["commitments"] if row["commitment_id"] == "fake-sp-compute"
        )
        assert Decimal(compute["utilization"]) == Decimal("1")

        ec2 = next(row for row in found["coverage"] if row["dimension_value"] == "AmazonEC2")
        assert Decimal(ec2["coverage"]) < Decimal("0.5")


class TestNullIsNotZero:
    def test_a_commitment_that_has_not_started_reports_no_utilization(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # Zero would say the whole commitment was wasted. It has not started, and
        # the screen renders the two differently on purpose.
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        queued = next(
            row for row in get(client, token)["data"]["commitments"] if row["status"] == "QUEUED"
        )
        assert queued["utilization"] is None

    def test_a_service_eligible_and_uncovered_reports_zero(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        lambda_row = next(
            row
            for row in get(client, token)["data"]["coverage"]
            if row["dimension_value"] == "AWSLambda"
        )
        assert Decimal(lambda_row["coverage"]) == Decimal("0")


class TestScope:
    def test_a_narrow_scope_reads_nothing_rather_than_the_payers_position(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """The assertion this route was hardest to get right.

        `PayerWide` rather than `None` in the guard. With `None` the tenant filter
        would be the whole of the scoping and this call would return all four
        commitments to a viewer entitled to one account, telling them the size of
        the organization's commitment position. A 404 is the correct answer: there
        is no commitment window this scope can be shown.
        """
        seed(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, "fake-platform-a"), settings)
        response = client.get(PATH, headers=auth(token))
        assert response.status_code == 404
        assert "commitment window" in response.json()["detail"]

    def test_one_tenant_does_not_read_another(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        neighbour = another_tenant(engine)
        seed(engine, neighbour)
        client, token = client_for(engine, everything(tenant_id), settings)
        response = client.get(PATH, headers=auth(token))
        assert response.status_code == 404


class TestWhenThereIsNothing:
    def test_a_tenant_with_no_collection_is_told_so_rather_than_shown_zero(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # A 404 says the thing does not exist. A page of zeroes would say the estate
        # holds no commitments and wastes nothing, which is a claim nobody has earned
        # the right to make. Constraint 5.
        client, token = client_for(engine, everything(tenant_id), settings)
        response = client.get(PATH, headers=auth(token))
        assert response.status_code == 404

    def test_a_payer_that_holds_no_commitments_is_the_same_answer(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # The collector absorbs NoData and writes nothing, so nothing was collected
        # and the route says exactly that. The distinction between never collected
        # and collected and empty is not one this route can draw, and inventing a
        # third answer here would be inventing it.
        seed(engine, tenant_id, FakeCommitmentReport(holds_nothing=True))
        client, token = client_for(engine, everything(tenant_id), settings)
        response = client.get(PATH, headers=auth(token))
        assert response.status_code == 404
