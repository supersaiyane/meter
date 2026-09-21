"""The five P3 tables refuse an out of scope read, before any route reads them.

This file exists because TASK-P2-021 wrote six routes over six unguarded tables
and every one returned 500 on its first real call while importing cleanly and
passing its tests, and because ISS-184 later found two more carrying the rule
`None` on the widest tables in the schema. The guard goes in first, every time, and
the proof that it is in goes in with it.

The interesting one is `recommendation_event`. It has no account column: an event
inherits the account of the recommendation it hangs off, and a denormalised copy
would be a second version of a fact and therefore a second chance to disagree.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_api.db import models
from finops_api.guards import SCOPED_TABLES, ByAccount, Through, scope_predicate
from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.tenant import Scope

pytestmark = pytest.mark.integration

P3_TABLES = (
    "recommendation",
    "recommendation_event",
    "realized_saving",
    "finops_score",
    "finops_score_component",
)


def narrow(tenant: UUID, account: str = "111122223333") -> Scope:
    return Scope(
        tenant_id=tenant,
        is_global=False,
        accounts=frozenset({AccountKey(provider=Provider.AWS, account_id=account)}),
    )


def everything(tenant: UUID) -> Scope:
    return Scope(tenant_id=tenant, is_global=True, accounts=frozenset())


class TestEveryP3TableHasARule:
    @pytest.mark.parametrize("name", P3_TABLES)
    def test_it_is_in_scoped_tables(self, name: str) -> None:
        # A table absent from the mapping fails closed at read time with a loud
        # error rather than a quiet leak, but failing closed in production is a
        # worse way to find out than failing here.
        assert name in SCOPED_TABLES

    def test_a_recommendation_is_scoped_by_its_account(self) -> None:
        assert SCOPED_TABLES["recommendation"] == ByAccount("sub_account_id")

    @pytest.mark.parametrize("name", ("recommendation_event", "realized_saving"))
    def test_the_hanging_tables_inherit_rather_than_copy(self, name: str) -> None:
        """Neither has an account column, and neither should grow one.

        A denormalised account here would be a second copy of a fact and therefore
        a second chance to disagree with the first.
        """
        rule = SCOPED_TABLES[name]
        assert isinstance(rule, Through)
        assert rule.table == "recommendation"
        assert "sub_account_id" not in {
            column.name for column in models.metadata.tables[name].columns
        }


class TestThePredicateNarrows:
    @pytest.mark.parametrize("name", P3_TABLES)
    def test_a_narrow_scope_produces_a_predicate(self, name: str) -> None:
        clause = str(scope_predicate(models.metadata.tables[name], narrow(uuid4())))
        assert "tenant_id" in clause
        # Either it matches an account directly or it reaches one through the
        # recommendation. What it must never be is the tenant filter alone.
        assert "sub_account_id" in clause or "recommendation_id IN" in clause

    @pytest.mark.parametrize("name", P3_TABLES)
    def test_a_global_scope_is_still_confined_to_its_tenant(self, name: str) -> None:
        clause = str(scope_predicate(models.metadata.tables[name], everything(uuid4())))
        assert "tenant_id" in clause


class TestAnOutOfScopeReadReturnsNothing:
    """The assertion that would have caught ISS-184, run against a real database."""

    def seed(self, engine: Engine, tenant: UUID, account: str) -> UUID:
        recommendation_id = uuid4()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO recommendation (recommendation_id, tenant_id, sub_account_id, "
                    "source, source_reference, waste_class, resource_id, region_id, "
                    "estimated_monthly_saving, confidence, severity, observation_days, "
                    "lifecycle, rationale, as_of, collected_at) VALUES "
                    "(:id, :t, :a, 'METER', :ref, 'IDLE_INSTANCE', 'i-x', 'eu-west-1', "
                    "100, 'HIGH', 'HIGH', 30, 'OPEN', 'because', now(), now())"
                ),
                {"id": recommendation_id, "t": tenant, "a": account, "ref": f"ref-{account}"},
            )
            connection.execute(
                text(
                    "INSERT INTO recommendation_event (event_id, recommendation_id, tenant_id, "
                    "from_lifecycle, to_lifecycle, actor, occurred_at, as_of, collected_at) "
                    "VALUES (:e, :id, :t, NULL, 'OPEN', 'test', now(), now(), now())"
                ),
                {"e": uuid4(), "id": recommendation_id, "t": tenant},
            )
        return recommendation_id

    def test_a_reader_entitled_to_one_account_sees_only_that_one(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        self.seed(engine, tenant_id, "111122223333")
        self.seed(engine, tenant_id, "444455556666")

        table = models.metadata.tables["recommendation"]
        with engine.connect() as connection:
            rows = connection.execute(
                table.select().where(scope_predicate(table, narrow(tenant_id)))
            ).all()
        assert len(rows) == 1
        assert rows[0].sub_account_id == "111122223333"

    def test_an_event_hanging_off_an_unreachable_recommendation_is_unreachable(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        """The inheritance working, end to end.

        The event carries no account of its own, so if the chain were broken it
        would be visible to everybody in the tenant.
        """
        self.seed(engine, tenant_id, "111122223333")
        self.seed(engine, tenant_id, "444455556666")

        table = models.metadata.tables["recommendation_event"]
        with engine.connect() as connection:
            rows = connection.execute(
                table.select().where(scope_predicate(table, narrow(tenant_id)))
            ).all()
        assert len(rows) == 1

    def test_a_global_reader_sees_both(self, engine: Engine, tenant_id: UUID) -> None:
        # The other half. A guard that returned nothing to everybody would pass
        # every test above and be useless.
        self.seed(engine, tenant_id, "111122223333")
        self.seed(engine, tenant_id, "444455556666")

        table = models.metadata.tables["recommendation"]
        with engine.connect() as connection:
            rows = connection.execute(
                table.select().where(scope_predicate(table, everything(tenant_id)))
            ).all()
        assert len(rows) == 2


class TestTheScoreTables:
    """FEAT-043, and the one table in P3 whose subject is sometimes not an account.

    A team spans accounts. So a team score has no `sub_account_id`, a narrowed reader
    is served none of them, and that is the deliberate answer rather than an
    oversight: a team score computed from the two accounts a reader can see, shown
    under the whole team's name, is worse than no score at all.
    """

    def seed_score(
        self, engine: Engine, tenant: UUID, *, account: str | None, team: str | None
    ) -> UUID:
        score_id = uuid4()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO finops_score (score_id, tenant_id, sub_account_id, team, "
                    "total, available_weight, why, as_of, collected_at) "
                    "VALUES (:id, :t, :a, :team, 70, 100, 'because', now(), now())"
                ),
                {"id": score_id, "t": tenant, "a": account, "team": team},
            )
            connection.execute(
                text(
                    "INSERT INTO finops_score_component (component_id, score_id, tenant_id, "
                    "name, points, weight, why, as_of, collected_at) "
                    "VALUES (:c, :id, :t, 'waste', 30, 40, 'because', now(), now())"
                ),
                {"c": uuid4(), "id": score_id, "t": tenant},
            )
        return score_id

    def test_an_account_score_out_of_scope_is_unreachable(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        self.seed_score(engine, tenant_id, account="111122223333", team=None)
        self.seed_score(engine, tenant_id, account="444455556666", team=None)

        table = models.metadata.tables["finops_score"]
        with engine.connect() as connection:
            rows = connection.execute(
                table.select().where(scope_predicate(table, narrow(tenant_id)))
            ).all()
        assert len(rows) == 1
        assert rows[0].sub_account_id == "111122223333"

    def test_a_team_score_is_not_served_to_a_narrowed_reader(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        # Deliberate, and the reason is in the class docstring. A partial team score
        # under a whole team's name is worse than none.
        self.seed_score(engine, tenant_id, account=None, team="platform")

        table = models.metadata.tables["finops_score"]
        with engine.connect() as connection:
            narrowed = connection.execute(
                table.select().where(scope_predicate(table, narrow(tenant_id)))
            ).all()
            global_reader = connection.execute(
                table.select().where(scope_predicate(table, everything(tenant_id)))
            ).all()
        assert narrowed == []
        assert len(global_reader) == 1

    def test_a_component_hanging_off_an_unreachable_score_is_unreachable(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        self.seed_score(engine, tenant_id, account="111122223333", team=None)
        self.seed_score(engine, tenant_id, account="444455556666", team=None)

        table = models.metadata.tables["finops_score_component"]
        with engine.connect() as connection:
            rows = connection.execute(
                table.select().where(scope_predicate(table, narrow(tenant_id)))
            ).all()
        assert len(rows) == 1

    def test_neither_score_table_grows_a_second_copy_of_the_account(self) -> None:
        # The component reaches its account through the score, for the same reason
        # an event reaches one through its recommendation.
        columns = {
            column.name for column in models.metadata.tables["finops_score_component"].columns
        }
        assert "sub_account_id" not in columns
        assert "team" not in columns
