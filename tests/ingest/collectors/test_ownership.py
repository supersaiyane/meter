"""Owners from tags, read into `resource_owner`. TASK-P11-002, P11 spec section 5.2."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.config import Settings
from finops_ingest.collectors.ownership import OwnershipCollector, team_of
from finops_ingest.registry import CollectorContext, CollectorOutcome

pytestmark = pytest.mark.integration

AT = datetime(2026, 10, 8, 5, 0, tzinfo=UTC)
NOW = AT + timedelta(hours=1)
ACCOUNT = "111111111111"

INSERT_RUN = text(
    "INSERT INTO ingest_run (run_id, tenant_id, collector, scope_key, idempotency_key, "
    "status, as_of_window_start, as_of_window_end) "
    "VALUES (:run, :t, 'inventory', 'scope', :key, 'SUCCEEDED', :at, :at)"
)
INSERT_NODE = text(
    "INSERT INTO topology_node (node_id, tenant_id, ingest_run_id, sub_account_id, "
    "provider_id, node_kind, resource_type, region_id, availability_zone, name, tags, as_of, "
    "collected_at) VALUES (:node, :t, :run, :account, :provider, 'INSTANCE', "
    "'AWS::EC2::Instance', :region, NULL, :provider, CAST(:tags AS jsonb), :at, :at)"
)
OWNERS = text(
    "SELECT resource_id, region_id, source, owner, owner_kind, detail, as_of, collected_at "
    "FROM resource_owner WHERE tenant_id = :t"
)


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID


def nodes(engine: Engine, tenant: UUID, *found: tuple[str, str | None, dict[str, str]]) -> None:
    run = uuid4()
    with engine.begin() as connection:
        connection.execute(INSERT_RUN, {"run": run, "t": tenant, "key": str(run), "at": AT})
        for provider, region, tags in found:
            connection.execute(
                INSERT_NODE,
                {
                    "node": uuid4(),
                    "t": tenant,
                    "run": run,
                    "account": ACCOUNT,
                    "provider": provider,
                    "region": region,
                    "tags": json.dumps(tags),
                    "at": AT,
                },
            )


def collect(
    engine: Engine, tenant: UUID, settings: Settings | None, keys: str = "team"
) -> CollectorOutcome:
    configured = None if settings is None else settings.model_copy(update={"owner_tag_keys": keys})
    with engine.begin() as connection:
        return OwnershipCollector(clock=lambda: NOW)(
            CollectorContext(
                unit=Unit(tenant_id=tenant),
                connection=connection,
                run_id=uuid4(),
                settings=configured,
            )
        )


def owners(engine: Engine, tenant: UUID) -> dict[str, dict[str, Any]]:
    with engine.connect() as connection:
        return {
            row["resource_id"]: dict(row)
            for row in connection.execute(OWNERS, {"t": tenant}).mappings()
        }


ESTATE: tuple[tuple[str, str | None, dict[str, str]], ...] = (
    ("i-team", "eu-west-2", {"team": "platform", "owner": "someone-else"}),
    ("i-owner", "eu-west-2", {"owner": "data-platform"}),
    ("i-blank", "eu-west-2", {"team": "  "}),
    ("i-bare", "eu-west-2", {}),
)


def test_the_first_owner_tag_key_a_resource_carries_names_its_team(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    nodes(engine, tenant_id, *ESTATE)
    outcome = collect(engine, tenant_id, settings, keys="team, owner")
    found = owners(engine, tenant_id)
    assert set(found) == {"i-team", "i-owner"}
    assert (found["i-team"]["owner"], found["i-team"]["detail"]) == ("platform", "team")
    assert (found["i-owner"]["owner"], found["i-owner"]["detail"]) == ("data-platform", "owner")
    assert {row["source"] for row in found.values()} == {"TAG"}
    assert {row["owner_kind"] for row in found.values()} == {"TEAM"}
    assert outcome.items_written == 2


def test_by_default_only_the_team_tag_is_read(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    nodes(engine, tenant_id, *ESTATE)
    collect(engine, tenant_id, settings)
    assert set(owners(engine, tenant_id)) == {"i-team"}


def test_a_row_is_true_when_the_inventory_read_it_and_collected_by_the_run(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    nodes(engine, tenant_id, *ESTATE)
    collect(engine, tenant_id, settings)
    row = owners(engine, tenant_id)["i-team"]
    assert (row["as_of"], row["collected_at"]) == (AT, NOW)


def test_a_tag_taken_off_stops_suggesting_its_team(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    nodes(engine, tenant_id, *ESTATE)
    collect(engine, tenant_id, settings)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE topology_node SET tags = '{}' WHERE tenant_id = :t"), {"t": tenant_id}
        )
    outcome = collect(engine, tenant_id, settings)
    assert owners(engine, tenant_id) == {}
    assert outcome.items_removed == 1


def test_another_sources_rows_are_left_standing(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO resource_owner (owner_pk, tenant_id, ingest_run_id, sub_account_id, "
                "region_id, resource_id, source, owner, owner_kind, detail, as_of, collected_at) "
                "VALUES (:pk, :t, :run, :a, 'eu-west-2', 'i-catalogued', 'CATALOGUE', 'payments', "
                "'TEAM', 'checkout', :at, :at)"
            ),
            {"pk": uuid4(), "t": tenant_id, "run": uuid4(), "a": ACCOUNT, "at": AT},
        )
    nodes(engine, tenant_id, *ESTATE)
    collect(engine, tenant_id, settings)
    found = owners(engine, tenant_id)
    assert found["i-catalogued"]["source"] == "CATALOGUE"


def test_a_resource_no_region_holds_keeps_a_null_region(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    nodes(engine, tenant_id, ("global-1", None, {"team": "platform"}))
    collect(engine, tenant_id, settings)
    assert owners(engine, tenant_id)["global-1"]["region_id"] is None


def test_without_settings_the_keys_are_not_guessed(engine: Engine, tenant_id: UUID) -> None:
    with pytest.raises(ValueError, match="owner tag keys are configuration"):
        collect(engine, tenant_id, None)


@pytest.mark.parametrize(
    ("tags", "keys", "named"),
    [
        ({"team": "a", "owner": "b"}, ("owner", "team"), ("owner", "b")),
        ({"team": " a "}, ("team",), ("team", "a")),
        ({"team": ""}, ("team",), None),
        ({"team": 7}, ("team",), None),
        ({"x": "a"}, (), None),
    ],
)
def test_the_first_key_with_a_value_wins(
    tags: dict[str, Any], keys: tuple[str, ...], named: tuple[str, str] | None
) -> None:
    assert team_of(tags, keys) == named
