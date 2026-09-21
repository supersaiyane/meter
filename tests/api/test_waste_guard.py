"""The three P3 tables refuse an out of scope read, before any route reads them.

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

P3_TABLES = ("recommendation", "recommendation_event", "realized_saving")


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
