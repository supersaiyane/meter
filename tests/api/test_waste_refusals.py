"""What Meter looked at and decided not to recommend. FEAT-062, ADR-0027.

The argument on FEAT-058 concluded that Meter cannot honestly gain a performance dimension,
because it cannot verify a performance finding and verification is its whole claim. What it can
do is show that it looked, and the complaint behind the gap was about trust rather than
capability.

The cases here are the two that make this feature honest rather than decorative. A refusal must
carry no money, because ADR-0016 ranks every finding by money and a zero would read as the least
valuable action rather than as the absence of one. And it must carry a sentence somebody can
disagree with, because a refusal reading "did not qualify" would teach a reader that the
explanations are empty and they would stop reading the ones that are not.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.config import Settings
from tests.api.test_query_routes import client_for
from tests.api.test_waste_routes import everything, get, only

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 21, 6, 0, tzinfo=UTC)
PATH = "/api/v1/waste/refusals"
MINE = "fake-platform-a"
THEIRS = "fake-product-b"

INSERT = text(
    "INSERT INTO sizing_refusal (refusal_id, tenant_id, ingest_run_id, sub_account_id, "
    "region_id, resource_id, waste_class, reason, observation_days, as_of, collected_at) "
    "VALUES (:id, :t, :run, :a, :r, :res, :wc, :reason, :days, :at, :at)"
)


def seed(engine: Engine, tenant: UUID) -> None:
    """Two accounts, two rules, and two very different amounts of history behind them."""
    with engine.begin() as connection:
        run = uuid4()
        for account, resource, waste_class, reason, days in (
            (
                MINE,
                "i-busy",
                "RIGHTSIZE_INSTANCE",
                "p99 of 87.3 percent leaves no room to shrink",
                90,
            ),
            (
                MINE,
                "i-memory-bound",
                "RIGHTSIZE_INSTANCE",
                "94 percent memory ceiling, so this is memory bound and a CPU rule must "
                "not shrink it",
                90,
            ),
            (
                MINE,
                "i-young",
                "IDLE_INSTANCE",
                "4 days is under the 14 day floor",
                4,
            ),
            (
                THEIRS,
                "i-theirs",
                "RIGHTSIZE_INSTANCE",
                "p99 of 91.0 percent leaves no room to shrink",
                60,
            ),
        ):
            connection.execute(
                INSERT,
                {
                    "id": uuid4(),
                    "t": tenant,
                    "run": run,
                    "a": account,
                    "r": "us-fake-1",
                    "res": resource,
                    "wc": waste_class,
                    "reason": reason,
                    "days": days,
                    "at": NOW,
                },
            )


def test_a_refusal_carries_no_money_and_no_severity(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The property that kept this out of the recommendation table.

    ADR-0016 ranks every finding by money. A refusal has none, so a zero saving here would
    rank as the least valuable action rather than as the absence of one, which is the same
    defect as rendering a collection failure as a number.
    """
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    found = get(client, token, PATH)["data"]
    assert found["refusals"]
    for one in found["refusals"]:
        assert "saving" not in one
        assert "estimated_monthly_saving" not in one
        assert "severity" not in one


def test_every_refusal_says_something_a_reader_can_disagree_with(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """A refusal is only as good as its sentence.

    One reading "did not qualify" would be worse than no feature: it teaches a reader that the
    explanations here are empty, and they stop reading the ones that are not. So each carries a
    measurement rather than a verdict.
    """
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    for one in get(client, token, PATH)["data"]["refusals"]:
        assert len(one["reason"]) >= 12
        assert any(char.isdigit() for char in one["reason"]), (
            f"{one['reason']!r} names no measurement, so it is a verdict rather than evidence"
        )


def test_the_least_observed_judgement_comes_first(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Ordered by what the judgement rests on, because it cannot be ordered by money.

    A rule that declined after four days is the one a reader should question first; one that
    declined after ninety is the one they can rely on. Ranking by anything resembling severity
    would need a money figure this deliberately does not have.
    """
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    days = [one["observation_days"] for one in get(client, token, PATH)["data"]["refusals"]]
    assert days == sorted(days)
    assert days[0] == 4


def test_it_counts_resources_examined_and_not_rows(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    # One resource declined by two rules is one resource that was looked at. Counting rows
    # would report an estate larger than the one that exists.
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    found = get(client, token, PATH)["data"]
    assert len(found["refusals"]) == 4
    assert found["examined"] == 4


def test_a_narrowed_reader_sees_only_their_own(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Constraint 3. A refusal names a resource, so it is scoped like the finding it is the
    absence of: telling somebody we declined to recommend anything about a resource discloses
    the resource just as surely as telling them we did."""
    seed(engine, tenant_id)
    client, token = client_for(engine, only(tenant_id, MINE), settings)
    found = get(client, token, PATH)["data"]
    assert {one["account_id"] for one in found["refusals"]} == {MINE}
    assert found["examined"] == 3


def test_an_estate_with_nothing_refused_is_empty_and_not_an_error(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    # Every resource having a finding is a real state, and so is nothing having been collected.
    # Neither is a failure and the screen says which.
    client, token = client_for(engine, everything(tenant_id), settings)
    found: dict[str, Any] = get(client, token, PATH)["data"]
    assert found["refusals"] == []
    assert found["examined"] == 0
