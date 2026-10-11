"""A credit for every verified saving, to its owner, team and closer. TASK-P11-006, spec 5.5.

Each case plants a finished recommendation as the lifecycle leaves one, accepted by one person and
closed by another, with FEAT-029's verdict written straight into `realized_saving`, because what
this collector reads is the verdict and not the bill behind it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_ingest.collectors.savings_ledger import SavingsLedgerCollector
from finops_ingest.registry import CollectorContext, CollectorOutcome

pytestmark = pytest.mark.integration

AT = datetime(2026, 9, 21, 5, 0, tzinfo=UTC)
NOW = AT + timedelta(hours=1)
DONE_AT = AT - timedelta(days=61)
ACCOUNT = "111111111111"
#: The after window FEAT-029 judged, thirty days ending sixty after the change.
AFTER = (date(2026, 8, 21), date(2026, 9, 20))

RECOMMENDATION = text(
    "INSERT INTO recommendation (recommendation_id, tenant_id, sub_account_id, source, "
    "source_reference, waste_class, resource_id, region_id, estimated_monthly_saving, "
    "confidence, severity, observation_days, lifecycle, owner, rationale, as_of, collected_at) "
    "VALUES (:id, :t, :account, 'METER', :ref, 'RIGHTSIZE_INSTANCE', :resource, 'eu-west-1', 50, "
    "'HIGH', 'HIGH', 30, :lifecycle, :owner, 'test fixture', :at, :at)"
)
EVENT = text(
    "INSERT INTO recommendation_event (event_id, recommendation_id, tenant_id, from_lifecycle, "
    "to_lifecycle, actor, reason, occurred_at, as_of, collected_at) "
    "VALUES (:e, :id, :t, :from, :to, :actor, NULL, :at, :at, :at)"
)
VERDICT = text(
    "INSERT INTO realized_saving (realized_id, recommendation_id, tenant_id, window_before_start, "
    "window_before_end, window_after_start, window_after_end, cost_before, cost_after, "
    "usage_before, usage_after, verdict, why, as_of, collected_at) VALUES (:r, :id, :t, "
    ":b0, :b1, :a0, :a1, :before, :after, :usage, :usage, :verdict, 'test fixture', :at, :at)"
)
OWNER = text(
    "INSERT INTO resource_owner (owner_pk, tenant_id, ingest_run_id, sub_account_id, region_id, "
    "resource_id, source, owner, owner_kind, detail, as_of, collected_at) VALUES (:pk, :t, :run, "
    ":account, 'eu-west-1', :resource, :source, :owner, 'TEAM', :detail, :at, :at)"
)
NODE = text(
    "INSERT INTO topology_node (node_id, tenant_id, ingest_run_id, sub_account_id, provider_id, "
    "node_kind, resource_type, region_id, availability_zone, name, tags, as_of, collected_at) "
    "VALUES (:node, :t, :run, :account, :resource, 'INSTANCE', 'AWS::EC2::Instance', "
    "'eu-west-1', NULL, :resource, CAST(:tags AS jsonb), :at, :at)"
)
RUN = text(
    "INSERT INTO ingest_run (run_id, tenant_id, collector, scope_key, idempotency_key, "
    "status, as_of_window_start, as_of_window_end) "
    "VALUES (:run, :t, 'inventory', 'scope', :key, 'SUCCEEDED', :at, :at)"
)
CREDITS = text(
    "SELECT r.resource_id, c.owner, c.team, c.closed_by, c.verified_monthly_saving, "
    "c.verified_on, c.as_of, c.collected_at FROM savings_credit c "
    "JOIN recommendation r ON r.recommendation_id = c.recommendation_id WHERE c.tenant_id = :t"
)


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID


def finished(
    engine: Engine,
    tenant: UUID,
    resource: str,
    *,
    verdict: str = "VERIFIED",
    owner: str | None = "platform@example.local",
    after: Decimal = Decimal("60"),
) -> UUID:
    """A recommendation accepted by bob, closed by alice, and judged by FEAT-029."""
    identifier = uuid4()
    lifecycle = "DONE" if verdict == "INCONCLUSIVE" else verdict
    with engine.begin() as connection:
        connection.execute(
            RECOMMENDATION,
            {
                "id": identifier,
                "t": tenant,
                "account": ACCOUNT,
                "ref": f"ref:{identifier}",
                "resource": resource,
                "lifecycle": lifecycle,
                "owner": owner,
                "at": AT,
            },
        )
        for target, actor, days in (("ACCEPTED", "bob", 3), ("IN_PROGRESS", "bob", 2)):
            connection.execute(
                EVENT,
                {
                    "e": uuid4(),
                    "id": identifier,
                    "t": tenant,
                    "from": "PREVIOUS",
                    "to": target,
                    "actor": actor,
                    "at": DONE_AT - timedelta(days=days),
                },
            )
        connection.execute(
            EVENT,
            {
                "e": uuid4(),
                "id": identifier,
                "t": tenant,
                "from": "IN_PROGRESS",
                "to": "DONE",
                "actor": "alice",
                "at": DONE_AT,
            },
        )
        connection.execute(
            VERDICT,
            {
                "r": uuid4(),
                "id": identifier,
                "t": tenant,
                "b0": date(2026, 6, 22),
                "b1": date(2026, 7, 22),
                "a0": AFTER[0],
                "a1": AFTER[1],
                "before": Decimal("100"),
                "after": after,
                "usage": Decimal("10"),
                "verdict": verdict,
                "at": AT,
            },
        )
    return identifier


def named(engine: Engine, tenant: UUID, resource: str, **sources: str) -> None:
    """The teams each source names for a resource: CATALOGUE, TAG, or a node's `team` tag."""
    with engine.begin() as connection:
        for source, team in sources.items():
            if source == "node":
                run = uuid4()
                connection.execute(RUN, {"run": run, "t": tenant, "key": str(run), "at": AT})
                connection.execute(
                    NODE,
                    {
                        "node": uuid4(),
                        "t": tenant,
                        "run": run,
                        "account": ACCOUNT,
                        "resource": resource,
                        "tags": json.dumps({"team": team}),
                        "at": AT,
                    },
                )
                continue
            connection.execute(
                OWNER,
                {
                    "pk": uuid4(),
                    "t": tenant,
                    "run": uuid4(),
                    "account": ACCOUNT,
                    "resource": resource,
                    "source": source,
                    "owner": team,
                    "detail": "checkout" if source == "CATALOGUE" else "team",
                    "at": AT,
                },
            )


def ledger(engine: Engine, tenant: UUID) -> CollectorOutcome:
    with engine.begin() as connection:
        return SavingsLedgerCollector(clock=lambda: NOW)(
            CollectorContext(unit=Unit(tenant_id=tenant), connection=connection, run_id=uuid4())
        )


def credited(engine: Engine, tenant: UUID) -> dict[str, dict[str, Any]]:
    with engine.connect() as connection:
        return {
            row["resource_id"]: dict(row)
            for row in connection.execute(CREDITS, {"t": tenant}).mappings()
        }


def test_a_verified_saving_is_credited_to_its_owner_team_and_closer(
    engine: Engine, tenant_id: UUID
) -> None:
    finished(engine, tenant_id, "i-1")
    named(engine, tenant_id, "i-1", TAG="platform", CATALOGUE="payments")
    outcome = ledger(engine, tenant_id)
    credit = credited(engine, tenant_id)["i-1"]
    assert (credit["owner"], credit["team"], credit["closed_by"]) == (
        "platform@example.local",
        "payments",
        "alice",
    )
    assert credit["verified_monthly_saving"] == Decimal("40")
    assert credit["verified_on"] == AFTER[1]
    assert (credit["as_of"], credit["collected_at"]) == (AT, NOW)
    assert outcome.items_written == 1


def test_an_inconclusive_or_regressed_verdict_earns_nothing(
    engine: Engine, tenant_id: UUID
) -> None:
    finished(engine, tenant_id, "i-unsure", verdict="INCONCLUSIVE")
    finished(engine, tenant_id, "i-worse", verdict="REGRESSED", after=Decimal("140"))
    assert ledger(engine, tenant_id).items_written == 0
    assert credited(engine, tenant_id) == {}


@pytest.mark.parametrize(
    ("sources", "team"),
    [({"node": "storage"}, "storage"), ({"node": ""}, None), ({}, None)],
)
def test_without_a_team_suggestion_the_tag_names_it_or_nobody_does(
    engine: Engine, tenant_id: UUID, sources: dict[str, str], team: str | None
) -> None:
    finished(engine, tenant_id, "i-1")
    named(engine, tenant_id, "i-1", **sources)
    ledger(engine, tenant_id)
    assert credited(engine, tenant_id)["i-1"]["team"] == team


def test_a_later_run_refreshes_the_figure_and_keeps_the_names(
    engine: Engine, tenant_id: UUID
) -> None:
    identifier = finished(engine, tenant_id, "i-1")
    named(engine, tenant_id, "i-1", TAG="platform")
    ledger(engine, tenant_id)
    # A reorganisation names another team, and late bill rows move the after window.
    named(engine, tenant_id, "i-1", CATALOGUE="payments")
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE realized_saving SET cost_after = 55 WHERE recommendation_id = :id"),
            {"id": identifier},
        )
    ledger(engine, tenant_id)
    credit = credited(engine, tenant_id)["i-1"]
    assert (credit["team"], credit["verified_monthly_saving"]) == ("platform", Decimal("45"))


def test_a_saving_that_stops_verifying_loses_its_credit(engine: Engine, tenant_id: UUID) -> None:
    identifier = finished(engine, tenant_id, "i-1")
    ledger(engine, tenant_id)
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE realized_saving SET verdict = 'INCONCLUSIVE' WHERE recommendation_id = :id"
            ),
            {"id": identifier},
        )
    outcome = ledger(engine, tenant_id)
    assert credited(engine, tenant_id) == {}
    assert outcome.items_removed == 1


def test_a_saving_nobody_owns_is_credited_to_nobody(engine: Engine, tenant_id: UUID) -> None:
    finished(engine, tenant_id, "i-1", owner=None)
    ledger(engine, tenant_id)
    assert credited(engine, tenant_id) == {}


def test_running_twice_writes_one_credit(engine: Engine, tenant_id: UUID) -> None:
    finished(engine, tenant_id, "i-1")
    ledger(engine, tenant_id)
    ledger(engine, tenant_id)
    with engine.connect() as connection:
        count = connection.execute(
            text("SELECT count(*) FROM savings_credit WHERE tenant_id = :t"), {"t": tenant_id}
        ).scalar_one()
    assert count == 1
