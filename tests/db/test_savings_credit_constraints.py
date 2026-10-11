"""The rules of a savings credit, held by the database. TASK-P11-006, constraint 11.

Migration 0043. One credit per verified saving, a saving above nought, an owner and a closer who
are named, a team named or absent but never blank, nothing collected before it was true, and a
verification that cannot be removed while a credit rests on it.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from tests.db.test_price_catalog_constraints import insert, refused
from tests.ingest.collectors.test_savings_ledger import ACCOUNT, finished

pytestmark = pytest.mark.integration

AT = datetime(2026, 9, 21, 5, 0, tzinfo=UTC)
TABLE = "savings_credit"


@pytest.fixture
def verified(engine: Engine, tenant_id: UUID) -> tuple[UUID, UUID]:
    """A verified saving to credit: its recommendation and its verification."""
    recommendation = finished(engine, tenant_id, "i-0123")
    with engine.connect() as connection:
        realized = connection.execute(
            text("SELECT realized_id FROM realized_saving WHERE recommendation_id = :id"),
            {"id": recommendation},
        ).scalar_one()
    return recommendation, realized


def credit(tenant: UUID, verified: tuple[UUID, UUID], **overrides: Any) -> dict[str, Any]:
    return {
        "credit_id": uuid4(),
        "tenant_id": tenant,
        "ingest_run_id": uuid4(),
        "sub_account_id": ACCOUNT,
        "recommendation_id": verified[0],
        "realized_id": verified[1],
        "owner": "platform@example.local",
        "team": "platform",
        "closed_by": "alice",
        "verified_monthly_saving": Decimal("40"),
        "verified_on": date(2026, 9, 20),
        "as_of": AT,
        "collected_at": AT,
        **overrides,
    }


def test_a_credit_with_or_without_a_team_is_kept(
    engine: Engine, tenant_id: UUID, verified: tuple[UUID, UUID]
) -> None:
    insert(engine, TABLE, credit(tenant_id, verified, team=None))


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"owner": " "}, "ck_savings_credit__named"),
        ({"closed_by": ""}, "ck_savings_credit__named"),
        ({"team": "  "}, "ck_savings_credit__named"),
        ({"verified_monthly_saving": Decimal("0")}, "ck_savings_credit__saved"),
        ({"collected_at": AT - timedelta(seconds=1)}, "ck_savings_credit__collected_after_true"),
    ],
)
def test_a_credit_breaking_a_rule_is_refused(
    engine: Engine,
    tenant_id: UUID,
    verified: tuple[UUID, UUID],
    overrides: dict[str, Any],
    constraint: str,
) -> None:
    refused(engine, TABLE, credit(tenant_id, verified, **overrides), constraint)


def test_a_verified_saving_is_credited_once(
    engine: Engine, tenant_id: UUID, verified: tuple[UUID, UUID]
) -> None:
    insert(engine, TABLE, credit(tenant_id, verified))
    refused(engine, TABLE, credit(tenant_id, verified), "uq_savings_credit__realized")


def test_a_credited_verification_cannot_be_removed(
    engine: Engine, tenant_id: UUID, verified: tuple[UUID, UUID]
) -> None:
    insert(engine, TABLE, credit(tenant_id, verified))
    with (
        pytest.raises(IntegrityError, match="fk_savings_credit__realized"),
        engine.begin() as connection,
    ):
        connection.execute(
            text("DELETE FROM realized_saving WHERE realized_id = :r"), {"r": verified[1]}
        )
