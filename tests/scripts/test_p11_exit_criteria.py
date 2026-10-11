"""P11's exit criteria, held against the whole demo estate. TASK-P11-009, P11 spec section 13.

Each task's tests prove its rule on the case it plants. These read the estate the demo seeds, with
every collector run in order, so a criterion that holds for the planted case and not for the rows
around it fails here rather than in front of an audience.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.config import Settings
from finops_core.domain.ownership import ORDER
from finops_core.errors import AccessDenied, Throttled
from finops_fakes.ownership import FakeResourceCreators, FakeServiceCatalogue
from finops_ingest.collectors.ownership import OwnershipCollector
from finops_ingest.collectors.savings_ledger import SavingsLedgerCollector
from finops_ingest.registry import CollectorContext
from tests.api.test_query_routes import auth, client_for
from tests.api.test_waste_routes import LIST_PATH, everything, get, only
from tests.scripts.test_seed_demo import DEMO_TENANT, _now, seed_demo

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """The seed bills months into partitions, so this module gives them back. ISS-268."""


LEDGER = "/api/v1/savings/ledger"
STRONGEST = [source.value for source in ORDER]


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID


@pytest.fixture
def seeded(engine: Engine, settings: Settings) -> Iterator[Engine]:
    seed_demo.seed(engine, settings, _now())
    try:
        yield engine
    finally:
        seed_demo.remove(engine)


def rows(engine: Engine, sql: str) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(text(sql), {"t": DEMO_TENANT}).mappings()]


def owners(engine: Engine) -> list[tuple[str, str, str, str]]:
    found = rows(
        engine,
        "SELECT source, resource_id, owner, owner_kind FROM resource_owner WHERE tenant_id = :t",
    )
    return sorted((r["source"], r["resource_id"], r["owner"], r["owner_kind"]) for r in found)


def a_new_resource(engine: Engine) -> None:
    """An untagged resource the inventory found after the seed, so CloudTrail has one to ask."""
    (where,) = rows(
        engine,
        "SELECT region_id FROM topology_node WHERE tenant_id = :t "
        "AND sub_account_id = 'fake-product-b' AND region_id IS NOT NULL LIMIT 1",
    )
    run, at = uuid4(), datetime.now(UTC) - timedelta(hours=1)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO ingest_run (run_id, tenant_id, collector, scope_key, "
                "idempotency_key, status, as_of_window_start, as_of_window_end) "
                "VALUES (:run, :t, 'inventory', 'scope', :key, 'SUCCEEDED', :at, :at)"
            ),
            {"run": run, "t": DEMO_TENANT, "key": str(run), "at": at},
        )
        connection.execute(
            text(
                "INSERT INTO topology_node (node_id, tenant_id, ingest_run_id, sub_account_id, "
                "provider_id, node_kind, resource_type, region_id, availability_zone, name, "
                "tags, as_of, collected_at) VALUES (:node, :t, :run, 'fake-product-b', "
                "'amazonec2/fake-product-b/0099', 'INSTANCE', 'AWS::EC2::Instance', :region, "
                "NULL, 'new', CAST(:tags AS jsonb), :at, :at)"
            ),
            {
                "node": uuid4(),
                "t": DEMO_TENANT,
                "run": run,
                "region": where["region_id"],
                "tags": json.dumps({}),
                "at": at,
            },
        )


def test_every_source_reads_its_planted_case_and_a_failing_one_stands_alone(
    seeded: Engine, settings: Settings
) -> None:
    """Criterion 1."""
    before = owners(seeded)
    catalogued = {(r[1], r[2]) for r in before if r[0] == "CATALOGUE"}
    assert catalogued == {
        ("amazonec2/fake-product-b/0004", "payments"),
        ("amazonrds/fake-product-b/0001", "analytics"),
    }
    assert ("TAG", "amazonebs/fake-product-b/0001", "data-platform", "TEAM") in before
    created = {(r[1], r[2], r[3]) for r in before if r[0] == "CREATOR"}
    assert created == {
        ("amazonec2/fake-product-b/0003", "dev.lead@fake.example", "PERSON"),
        ("amazonvpc/fake-product-b/nat-0001", "deploy-pipeline", "AUTOMATION"),
    }
    older = rows(
        seeded,
        "SELECT count(*) AS n FROM creator_lookup "
        "WHERE tenant_id = :t AND outcome = 'BEFORE_HISTORY'",
    )
    assert older[0]["n"] > 0

    # The catalogue refused everywhere and the event history throttled: each typed, alone.
    a_new_resource(seeded)
    configured = settings.model_copy(update={"owner_tag_keys": "team,owner"})
    with seeded.begin() as connection:
        OwnershipCollector(
            catalogue=FakeServiceCatalogue(failure=AccessDenied),
            creators=FakeResourceCreators(failure=Throttled),
        )(
            CollectorContext(
                unit=Unit(tenant_id=DEMO_TENANT),
                connection=connection,
                run_id=uuid4(),
                settings=configured,
            )
        )
    refused = rows(
        seeded,
        "SELECT DISTINCT error_type FROM sync_error "
        "WHERE tenant_id = :t AND collector = 'ownership'",
    )
    assert {r["error_type"] for r in refused} >= {"AccessDenied", "Throttled"}
    # Nothing known was lost: the tags were read again, the catalogue's rows kept, the creators'.
    assert owners(seeded) == before


def test_every_recommendation_lists_its_suggestions_and_none_becomes_an_owner(
    seeded: Engine, settings: Settings
) -> None:
    """Criterion 2."""
    client, token = client_for(seeded, everything(DEMO_TENANT), settings)
    listed = get(client, token, f"{LIST_PATH}?limit=1000")["data"]["recommendations"]
    expected: dict[tuple[str, str], list[str]] = {}
    for row in rows(
        seeded,
        "SELECT sub_account_id, resource_id, source FROM resource_owner WHERE tenant_id = :t",
    ):
        expected.setdefault((row["sub_account_id"], row["resource_id"]), []).append(row["source"])
    suggested = 0
    for one in listed:
        want = sorted(
            expected.get((one["account_id"], one["resource_id"]), []), key=STRONGEST.index
        )
        assert [s["source"] for s in one["owner_suggestions"]] == want, one["resource_id"]
        suggested += bool(want)
    assert suggested > 0
    # Only the finished work the seed planted carries an owner, the one a person named on it.
    owned = rows(
        seeded,
        "SELECT DISTINCT owner FROM recommendation WHERE tenant_id = :t AND owner IS NOT NULL",
    )
    named = {s["owner"] for one in listed for s in one["owner_suggestions"]}
    assert {r["owner"] for r in owned} == {"platform@example.local"}
    assert "platform@example.local" not in named


def test_every_verified_saving_has_one_credit_naming_its_owner_team_and_closer(
    seeded: Engine,
) -> None:
    """Criterion 3."""
    verified = rows(
        seeded,
        "SELECT s.realized_id, r.owner, r.resource_id, r.sub_account_id, "
        "(SELECT e.actor FROM recommendation_event e "
        "WHERE e.recommendation_id = s.recommendation_id "
        "AND e.to_lifecycle = 'DONE' ORDER BY e.occurred_at DESC LIMIT 1) AS closer "
        "FROM realized_saving s JOIN recommendation r ON r.recommendation_id = s.recommendation_id "
        "WHERE s.tenant_id = :t AND s.verdict = 'VERIFIED'",
    )
    credits_found = {
        r["realized_id"]: r
        for r in rows(
            seeded,
            "SELECT realized_id, owner, team, closed_by FROM savings_credit WHERE tenant_id = :t",
        )
    }
    assert verified
    assert set(credits_found) == {one["realized_id"] for one in verified if one["owner"]}
    teams = rows(
        seeded,
        "SELECT o.sub_account_id, o.resource_id, o.owner, o.source FROM resource_owner o "
        "WHERE o.tenant_id = :t AND o.owner_kind = 'TEAM'",
    )
    tags = rows(
        seeded,
        "SELECT sub_account_id, provider_id, NULLIF(tags ->> 'team', '') AS team "
        "FROM topology_node WHERE tenant_id = :t",
    )
    for one in verified:
        credit = credits_found[one["realized_id"]]
        assert (credit["owner"], credit["closed_by"]) == (one["owner"], one["closer"])
        here = (one["sub_account_id"], one["resource_id"])
        suggested = sorted(
            (t for t in teams if (t["sub_account_id"], t["resource_id"]) == here),
            key=lambda t: STRONGEST.index(t["source"]),
        )
        tagged = [t["team"] for t in tags if (t["sub_account_id"], t["provider_id"]) == here]
        known = suggested[0]["owner"] if suggested else next(iter(tagged), None)
        assert credit["team"] == known


def test_every_month_is_held_regressed_or_unobserved_and_none_unseen_is_a_zero(
    seeded: Engine,
) -> None:
    """Criterion 4. Judged a season after the seed, so months close past the bill's last day."""
    later = datetime.now(UTC) + timedelta(days=95)
    with seeded.begin() as connection:
        SavingsLedgerCollector(clock=lambda: later)(
            CollectorContext(
                unit=Unit(tenant_id=DEMO_TENANT), connection=connection, run_id=uuid4()
            )
        )
    months = rows(
        seeded,
        "SELECT m.month, m.state, m.cost, m.saving, (SELECT count(*) FROM cost_focus_daily d "
        "WHERE d.tenant_id = m.tenant_id AND d.sub_account_id = c.sub_account_id "
        "AND date_trunc('month', date(d.charge_period_start))::date = m.month) AS billed "
        "FROM savings_credit_month m JOIN savings_credit c ON c.credit_id = m.credit_id "
        "WHERE m.tenant_id = :t",
    )
    assert months
    for one in months:
        if one["billed"]:
            assert one["state"] in ("HELD", "REGRESSED") and one["cost"] is not None
        else:
            assert (one["state"], one["cost"], one["saving"]) == ("UNOBSERVED", None, None)
        if one["state"] == "HELD":
            assert one["saving"] > 0
    assert any(one["state"] == "UNOBSERVED" for one in months)


def test_the_ledger_ranks_teams_never_people_within_scope_and_exports(
    seeded: Engine, settings: Settings
) -> None:
    """Criterion 5."""
    client, token = client_for(seeded, everything(DEMO_TENANT), settings)
    teams = get(client, token, LEDGER)["data"]["teams"]
    assert teams
    assert all(not {"owner", "closed_by"} & set(one) for one in teams)
    held = [Decimal(one["saving_held"]) for one in teams]
    assert held == sorted(held, reverse=True)

    credited = {
        r["sub_account_id"]
        for r in rows(seeded, "SELECT sub_account_id FROM savings_credit WHERE tenant_id = :t")
    }
    accounts = {
        r["sub_account_id"]
        for r in rows(
            seeded, "SELECT DISTINCT sub_account_id FROM recommendation WHERE tenant_id = :t"
        )
    }
    elsewhere = sorted(accounts - credited)
    assert elsewhere, "the demo has an account with no credit to narrow to"
    narrowed, narrowed_token = client_for(seeded, only(DEMO_TENANT, elsewhere[0]), settings)
    assert get(narrowed, narrowed_token, LEDGER)["data"]["teams"] == []

    exported = client.get(f"{LEDGER}?format=csv", headers=auth(token))
    assert exported.status_code == 200, exported.text
    assert "Saving held" in exported.text
