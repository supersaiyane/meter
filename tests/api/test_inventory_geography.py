"""The estate by continent, called rather than imported. FEAT-061.

The cases that carry this file are the three leftovers. A map that adds them together, or that
omits any of them, reports a smaller or a wronger estate than exists, and every one of those
mistakes looks entirely plausible on screen: the continents are there, the counts are numbers,
and nothing about it reads as broken.

The estate here is built to have all three at once, because a route tested against an estate
where every region places is a route whose interesting half never runs.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine

from finops_core.config import Settings
from finops_core.domain.topology import CoverageState, NodeKind
from tests.api.test_inventory_routes import (
    FETCHED,
    INSERT_ACCOUNT,
    INSERT_COVERAGE,
    INSERT_NODE,
    INSERT_RUN,
    MINE,
    NOW,
    THEIRS,
    arn,
    everything,
    get,
    identifier,
    only,
)
from tests.api.test_query_routes import client_for

pytestmark = pytest.mark.integration

GEOGRAPHY = "/api/v1/inventory/geography"
RESOURCES = "/api/v1/inventory/resources"

#: Two regions in one geography, one in another, one whose prefix no table knows, and one that
#: refused us. The fifth slice holds no nodes on purpose: a refused region is not an empty one.
DUBLIN = "eu-west-1"
FRANKFURT = "eu-central-1"
VIRGINIA = "us-east-1"
NOWHERE = "zz-central-1"
REFUSED = "eu-north-1"


def seed(engine: Engine, tenant: UUID) -> None:
    """An estate with every case the screen has to tell apart.

    Three placeable regions across two geographies, one unplaceable region with real resources
    in it, two global resources belonging to no region, and one region a collection refused.
    """
    with engine.begin() as connection:
        run = uuid4()
        for account in (MINE, THEIRS):
            connection.execute(
                INSERT_ACCOUNT, {"pk": uuid4(), "t": tenant, "a": account, "at": NOW}
            )
        connection.execute(INSERT_RUN, {"run": run, "t": tenant, "key": str(run), "at": NOW})

        def add(account: str, region: str | None, name: str) -> None:
            connection.execute(
                INSERT_NODE,
                {
                    "node": identifier(tenant, account, region, name),
                    "t": tenant,
                    "run": run,
                    "a": account,
                    "p": arn(account, region, name),
                    "k": NodeKind.VPC.value,
                    "r": region,
                    "n": name,
                    "at": NOW,
                    "fetched": FETCHED,
                },
            )

        # Europe, three resources across two regions, so the geography has to list both.
        add(MINE, DUBLIN, "vpc-dub-1")
        add(MINE, DUBLIN, "vpc-dub-2")
        add(THEIRS, FRANKFURT, "vpc-fra-1")
        # The United States, one resource.
        add(MINE, VIRGINIA, "vpc-iad-1")
        # A geography no prefix table knows. Real resources, and they must not vanish.
        add(MINE, NOWHERE, "vpc-zz-1")
        # No region at all. IAM and the like, which is a fact about the service.
        add(MINE, None, "role-a")
        add(MINE, None, "role-b")

        for account, region, state in (
            (MINE, DUBLIN, CoverageState.COMPLETE),
            (MINE, VIRGINIA, CoverageState.COMPLETE),
            (THEIRS, FRANKFURT, CoverageState.COMPLETE),
            (MINE, NOWHERE, CoverageState.COMPLETE),
            # Holds nothing, and that is the point: unknown rather than zero.
            (MINE, REFUSED, CoverageState.PARTIAL),
        ):
            connection.execute(
                INSERT_COVERAGE,
                {
                    "c": uuid4(),
                    "t": tenant,
                    "run": run,
                    "a": account,
                    "r": region,
                    "s": state.value,
                    "cause": None if state is CoverageState.COMPLETE else "AccessDenied",
                    "at": NOW,
                    "fetched": FETCHED,
                },
            )


def test_groups_the_estate_by_the_region_name_prefix(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The feature. Two geographies, and Europe holds two regions that are named."""
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    found = get(client, token, GEOGRAPHY)["data"]

    by_key = {entry["key"]: entry for entry in found["geographies"]}
    assert set(by_key) == {"eu", "us"}
    assert by_key["eu"]["resources"] == 3
    assert by_key["us"]["resources"] == 1
    # Listed rather than counted, because the prefix cannot tell Dublin from Frankfurt and a
    # reader looking at Europe needs to know which it is.
    assert by_key["eu"]["regions"] == [FRANKFURT, DUBLIN]
    assert by_key["eu"]["name"] == "Europe"


def test_orders_geographies_west_to_east_rather_than_by_size(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """A drawing that reshuffles itself whenever a region grows is one nobody can learn."""
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    found = get(client, token, GEOGRAPHY)["data"]
    # The United States has one resource and Europe has three, so size would invert this.
    assert [entry["key"] for entry in found["geographies"]] == ["us", "eu"]


def test_keeps_the_three_leftovers_apart(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The case this route exists to get right.

    Each of the three needs a different sentence and a different remedy. Global is nobody's
    problem, unplaceable means the geography table needs a row, and refused means a collection
    failed and the counts above are a floor. Adding any two together destroys that.
    """
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    found = get(client, token, GEOGRAPHY)["data"]

    assert found["global_resources"] == 2
    assert found["unplaceable"] == [NOWHERE]
    assert found["unplaceable_resources"] == 1
    assert found["refused"] == [REFUSED]
    # And the global resources are not counted as unplaceable, which is the collapse that would
    # ask somebody to go and fix IAM for not having a region.
    assert NOWHERE not in found["refused"]


def test_the_geographies_plus_the_leftovers_are_the_whole_estate(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The arithmetic that makes the screen honest.

    Seven resources were seeded. If the parts do not add to seven then the map is reporting a
    smaller estate than exists, which is the failure that would be invisible on screen.
    """
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    found = get(client, token, GEOGRAPHY)["data"]
    placed = sum(entry["resources"] for entry in found["geographies"])
    assert placed + found["global_resources"] + found["unplaceable_resources"] == 7


def test_a_narrowed_reader_sees_only_their_own_continents(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Constraint 3. The guard is in the repository, so a grouped read is scoped like a page.

    The other account's only resource is in Frankfurt, so a reader narrowed to this account must
    see Europe with Dublin alone. A geography that still listed Frankfurt would be disclosing
    where another account runs, which is exactly what scoping withholds.
    """
    seed(engine, tenant_id)
    client, token = client_for(engine, only(tenant_id, MINE), settings)
    found = get(client, token, GEOGRAPHY)["data"]
    by_key = {entry["key"]: entry for entry in found["geographies"]}
    assert by_key["eu"]["regions"] == [DUBLIN]
    assert by_key["eu"]["resources"] == 2
    assert FRANKFURT not in by_key["eu"]["regions"]


def test_carries_coverage_in_slices_so_a_continent_count_is_a_floor(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """One refused slice of five, so the envelope says four of five and the screen says so too."""
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    body = get(client, token, GEOGRAPHY)
    coverage = body["meta"]["scope_coverage"]
    assert coverage["unit"] == "slices"
    assert coverage["total"] == 5
    assert coverage["visible"] == 4
    assert coverage["is_partial"] is True


def test_the_envelope_carries_freshness_so_the_screen_is_not_blank(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Constraint 4, and the case every other test here missed.

    The first version of this route returned counts and no timestamps. `build_meta` reads
    freshness off the rows, found none because a grouped row is not a fact row, and put null in
    `as_of`. The screen reads exactly that field to decide whether anything has been collected,
    so a correct estate of ninety two resources rendered as "not yet collected by topology".

    Every case above passed while that was true, because every one of them asserted on the data
    and none on the envelope. This one asserts on the envelope.
    """
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    meta = get(client, token, GEOGRAPHY)["meta"]
    assert meta["as_of"] is not None
    assert meta["collected_at"] is not None
    # The stalest, like every other route, because an aggregate is only as fresh as its oldest
    # input and a max here would report the whole estate as fresh as its newest row.
    assert meta["as_of"].startswith("2026-09-26T06:00")
    assert meta["collected_at"].startswith("2026-09-26T06:05")


def test_an_empty_estate_is_empty_and_not_an_error(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Nothing collected yet is a real state. The screen says so; the route does not refuse."""
    client, token = client_for(engine, everything(tenant_id), settings)
    found = get(client, token, GEOGRAPHY)["data"]
    assert found["geographies"] == []
    assert found["global_resources"] == 0
    assert found["unplaceable"] == []
    assert found["refused"] == []


# --- one click from a continent to its resources ----------------------------


def test_the_resource_list_narrows_to_every_region_in_a_geography(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """What the click on the map does. FEAT-061.

    Europe holds Dublin and Frankfurt, so one click has to return the resources of both. A
    filter that took a single region would show a reader two of the three things they just
    clicked on and give them no way to tell.
    """
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    found = get(client, token, RESOURCES, geography="eu")["data"]
    assert found["total"] == 3
    assert {entry["region_id"] for entry in found["resources"]} == {DUBLIN, FRANKFURT}


def test_a_geography_with_nothing_in_it_returns_nothing_not_everything(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The failure an empty filter makes easy.

    No filter and a filter that matched no region are one line apart in the code and opposite
    on the screen: the second must be an empty list, not the whole estate.
    """
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    found = get(client, token, RESOURCES, geography="ap")["data"]
    assert found["total"] == 0
    assert found["resources"] == []


def test_the_geography_filter_is_scoped_like_every_other_read(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Constraint 3, on the filter rather than on the grouping.

    The other account's only resource is in Frankfurt, which is in Europe. A narrowed reader
    clicking Europe must get their own two Dublin resources and not the third.
    """
    seed(engine, tenant_id)
    client, token = client_for(engine, only(tenant_id, MINE), settings)
    found = get(client, token, RESOURCES, geography="eu")["data"]
    assert found["total"] == 2
    assert {entry["region_id"] for entry in found["resources"]} == {DUBLIN}


def test_the_map_and_the_list_agree_about_every_geography(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The property that makes the click trustworthy.

    Asserted across two routes on purpose. Each is plausible alone, and the way this breaks is
    that one of them resolves the prefix slightly differently, so a continent says three and the
    list it opens shows two. That is the fault a reader finds before we do.
    """
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    for entry in get(client, token, GEOGRAPHY)["data"]["geographies"]:
        listed = get(client, token, RESOURCES, geography=entry["key"])["data"]
        assert listed["total"] == entry["resources"], entry["key"]
