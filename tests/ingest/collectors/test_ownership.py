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
from finops_core.domain.account import AccountKey
from finops_core.domain.ownership import (
    BeforeHistory,
    CatalogueApplication,
    Creator,
    OwnerKind,
)
from finops_core.errors import AccessDenied, CollectionError
from finops_fakes.ownership import (
    APPLICATION_TAG,
    CHECKOUT,
    REPORTING_STACK,
    SANDBOX,
    STACK_TAG,
    FakeServiceCatalogue,
)
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


# --- the catalogue, TASK-P11-003 ---------------------------------------------------------


PLANTED = "fake-product-b"
REGION = "us-fake-1"


def catalogue_nodes(engine: Engine, tenant: UUID, *found: tuple[str, dict[str, str]]) -> None:
    run = uuid4()
    with engine.begin() as connection:
        connection.execute(INSERT_RUN, {"run": run, "t": tenant, "key": str(run), "at": AT})
        for provider, tags in found:
            connection.execute(
                INSERT_NODE,
                {
                    "node": uuid4(),
                    "t": tenant,
                    "run": run,
                    "account": PLANTED,
                    "provider": provider,
                    "region": REGION,
                    "tags": json.dumps(tags),
                    "at": AT,
                },
            )


def catalogued(
    engine: Engine, tenant: UUID, settings: Settings, catalogue: Any
) -> CollectorOutcome:
    with engine.begin() as connection:
        return OwnershipCollector(clock=lambda: NOW, catalogue=catalogue)(
            CollectorContext(
                unit=Unit(tenant_id=tenant),
                connection=connection,
                run_id=uuid4(),
                settings=settings,
            )
        )


def from_catalogue(engine: Engine, tenant: UUID) -> dict[str, tuple[str, str, str]]:
    return {
        resource: (row["owner"], row["owner_kind"], row["detail"])
        for resource, row in owners(engine, tenant).items()
        if row["source"] == "CATALOGUE"
    }


MARKED: tuple[tuple[str, dict[str, str]], ...] = (
    ("i-checkout", {APPLICATION_TAG: CHECKOUT}),
    ("db-reporting", {STACK_TAG: REPORTING_STACK}),
    ("i-sandbox", {APPLICATION_TAG: SANDBOX}),
    ("i-unmarked", {}),
)


def test_an_application_naming_an_owner_suggests_it_for_the_resources_it_marks(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    catalogue_nodes(engine, tenant_id, *MARKED)
    outcome = catalogued(engine, tenant_id, settings, FakeServiceCatalogue())
    # By the application's own tag, and by the stack's; `sandbox` names nobody, so says nothing.
    assert from_catalogue(engine, tenant_id) == {
        "i-checkout": ("payments", "TEAM", "checkout"),
        "db-reporting": ("analytics", "TEAM", "reporting"),
    }
    assert outcome.items_written == 2


class _Addressed:
    """A catalogue whose one application names a person by address."""

    def applications(self, account: Any, region: str) -> tuple[CatalogueApplication, ...]:
        return (
            CatalogueApplication(
                account_key=account,
                region_id=region,
                name="checkout",
                application_id="app-1",
                owner="a.person@fake.example",
                marks=frozenset({(APPLICATION_TAG, CHECKOUT)}),
                as_of=AT,
                collected_at=AT,
            ),
        )


def test_an_owner_named_by_address_is_a_person(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    catalogue_nodes(engine, tenant_id, *MARKED)
    catalogued(engine, tenant_id, settings, _Addressed())
    assert from_catalogue(engine, tenant_id)["i-checkout"][:2] == (
        "a.person@fake.example",
        "PERSON",
    )


def test_a_refused_catalogue_is_typed_and_keeps_what_was_known(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    catalogue_nodes(engine, tenant_id, *MARKED)
    catalogued(engine, tenant_id, settings, FakeServiceCatalogue())
    catalogued(engine, tenant_id, settings, FakeServiceCatalogue(failure=AccessDenied))
    assert set(from_catalogue(engine, tenant_id)) == {"i-checkout", "db-reporting"}
    with engine.connect() as connection:
        cause = connection.execute(
            text(
                "SELECT error_type FROM sync_error WHERE tenant_id = :t AND collector = 'ownership'"
            ),
            {"t": tenant_id},
        ).scalar_one()
    assert cause == "AccessDenied"


def test_a_resource_no_longer_marked_loses_its_suggestion(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    catalogue_nodes(engine, tenant_id, *MARKED)
    catalogued(engine, tenant_id, settings, FakeServiceCatalogue())
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE topology_node SET tags = '{}' WHERE tenant_id = :t AND provider_id = :p"),
            {"t": tenant_id, "p": "i-checkout"},
        )
    outcome = catalogued(engine, tenant_id, settings, FakeServiceCatalogue())
    assert set(from_catalogue(engine, tenant_id)) == {"db-reporting"}
    assert outcome.items_removed == 1


# --- creators, TASK-P11-004 ------------------------------------------------------------

LOOKUPS = text(
    "SELECT resource_id, outcome, history_starts, as_of, collected_at FROM creator_lookup "
    "WHERE tenant_id = :t"
)
#: A tagged resource, one CloudTrail saw created, and one older than its history.
UNNAMED: tuple[tuple[str, str | None, dict[str, str]], ...] = (
    ("i-team", "eu-west-2", {"team": "platform"}),
    ("i-made", "eu-west-2", {}),
    ("i-older", "eu-west-2", {}),
)
CREATED = AT - timedelta(days=9)


class Creators:
    """A record of creators that keeps what it was asked, and refuses where it is told to."""

    def __init__(self, refusal: type[CollectionError] | None = None) -> None:
        self.asked: list[str] = []
        self._refusal = refusal

    def creator(
        self, account: AccountKey, region: str, resource_id: str
    ) -> Creator | BeforeHistory:
        self.asked.append(resource_id)
        if self._refusal is not None:
            raise self._refusal(scope_key=f"{account.account_id}:{region}", collector="ownership")
        if resource_id == "i-made":
            return Creator(
                account_key=account,
                region_id=region,
                resource_id=resource_id,
                principal="dev.lead@fake.example",
                kind=OwnerKind.PERSON,
                event_id="evt-made",
                created_at=CREATED,
                as_of=CREATED,
                collected_at=NOW,
            )
        return BeforeHistory(
            account_key=account,
            region_id=region,
            resource_id=resource_id,
            history_starts=NOW - timedelta(days=90),
            as_of=NOW,
            collected_at=NOW,
        )


def asked_of(
    engine: Engine, tenant: UUID, settings: Settings, creators: Creators, cap: int = 200
) -> CollectorOutcome:
    configured = settings.model_copy(update={"creator_lookups_per_run": cap})
    with engine.begin() as connection:
        return OwnershipCollector(clock=lambda: NOW, creators=creators)(
            CollectorContext(
                unit=Unit(tenant_id=tenant),
                connection=connection,
                run_id=uuid4(),
                settings=configured,
            )
        )


def lookups(engine: Engine, tenant: UUID) -> dict[str, dict[str, Any]]:
    with engine.connect() as connection:
        return {
            row["resource_id"]: dict(row)
            for row in connection.execute(LOOKUPS, {"t": tenant}).mappings()
        }


def test_a_resource_nothing_else_names_is_asked_who_created_it(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    nodes(engine, tenant_id, *UNNAMED)
    creators = Creators()
    outcome = asked_of(engine, tenant_id, settings, creators)
    assert sorted(creators.asked) == ["i-made", "i-older"], "a tagged resource is not asked"
    row = owners(engine, tenant_id)["i-made"]
    assert (row["source"], row["owner"], row["owner_kind"], row["detail"]) == (
        "CREATOR",
        "dev.lead@fake.example",
        "PERSON",
        "evt-made",
    )
    assert (row["as_of"], row["collected_at"]) == (CREATED, NOW)
    found = lookups(engine, tenant_id)
    assert (found["i-made"]["outcome"], found["i-made"]["history_starts"]) == ("FOUND", None)
    assert (found["i-older"]["outcome"], found["i-older"]["history_starts"]) == (
        "BEFORE_HISTORY",
        NOW - timedelta(days=90),
    )
    assert "i-older" not in owners(engine, tenant_id), "older than the history names nobody"
    # The tag, and the two resources answered.
    assert outcome.items_written == 3


def test_a_resource_once_asked_is_never_asked_again_and_keeps_its_creator(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    nodes(engine, tenant_id, *UNNAMED)
    asked_of(engine, tenant_id, settings, Creators())
    again = Creators()
    outcome = asked_of(engine, tenant_id, settings, again)
    assert again.asked == []
    assert owners(engine, tenant_id)["i-made"]["source"] == "CREATOR"
    assert outcome.items_removed == 0


def test_a_run_asks_no_more_than_its_cap_and_the_next_run_the_rest(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    nodes(engine, tenant_id, *UNNAMED)
    first, second = Creators(), Creators()
    asked_of(engine, tenant_id, settings, first, cap=1)
    asked_of(engine, tenant_id, settings, second, cap=1)
    assert (first.asked, second.asked) == (["i-made"], ["i-older"])


def test_a_refused_account_is_typed_and_asked_again_on_the_next_run(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    nodes(engine, tenant_id, *UNNAMED)
    refusing = Creators(AccessDenied)
    asked_of(engine, tenant_id, settings, refusing)
    assert refusing.asked == ["i-made"], "the rest of the account and Region waits"
    assert lookups(engine, tenant_id) == {}, "a refusal is not recorded as asked"
    with engine.connect() as connection:
        errors = connection.execute(
            text(
                "SELECT error_type, scope_key FROM sync_error "
                "WHERE tenant_id = :t AND collector = 'ownership'"
            ),
            {"t": tenant_id},
        ).all()
    assert [tuple(row) for row in errors] == [("AccessDenied", f"{ACCOUNT}:eu-west-2")]
    retried = Creators()
    asked_of(engine, tenant_id, settings, retried)
    assert sorted(retried.asked) == ["i-made", "i-older"]


def test_a_resource_no_region_holds_is_not_asked(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    nodes(engine, tenant_id, ("global-1", None, {}))
    creators = Creators()
    asked_of(engine, tenant_id, settings, creators)
    assert creators.asked == []
