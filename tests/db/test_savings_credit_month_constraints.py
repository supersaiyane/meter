"""The rules of a month a saving held, held by the database. TASK-P11-007, constraint 11.

Migration 0044. A month is the first of a month; HELD, REGRESSED or UNOBSERVED; unobserved exactly
when it has neither a cost nor a saving; a held month saved more than nought and a regressed one
did not; no cost below nought; one row per credit per month; nothing collected before it was true;
and a credit cannot be removed while a month rests on it.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from tests.db.test_price_catalog_constraints import insert, refused
from tests.ingest.collectors.test_savings_ledger import ACCOUNT, AT, finished, ledger

pytestmark = pytest.mark.integration

TABLE = "savings_credit_month"
OCTOBER = date(2026, 10, 1)


@pytest.fixture
def credit_id(engine: Engine, tenant_id: UUID) -> UUID:
    """A credit for a verified saving, written by the ledger as it would be."""
    finished(engine, tenant_id, "i-0123")
    ledger(engine, tenant_id)
    with engine.connect() as connection:
        found: UUID = connection.execute(
            text("SELECT credit_id FROM savings_credit WHERE tenant_id = :t"), {"t": tenant_id}
        ).scalar_one()
    return found


def month(tenant: UUID, credit: UUID, **overrides: Any) -> dict[str, Any]:
    return {
        "month_pk": uuid4(),
        "tenant_id": tenant,
        "ingest_run_id": uuid4(),
        "sub_account_id": ACCOUNT,
        "credit_id": credit,
        "month": OCTOBER,
        "state": "HELD",
        "cost": Decimal("40"),
        "saving": Decimal("53"),
        "as_of": AT,
        "collected_at": AT,
        **overrides,
    }


def test_each_state_is_kept(engine: Engine, tenant_id: UUID, credit_id: UUID) -> None:
    insert(engine, TABLE, month(tenant_id, credit_id))
    insert(
        engine,
        TABLE,
        month(
            tenant_id,
            credit_id,
            month=date(2026, 11, 1),
            state="REGRESSED",
            cost=Decimal("100"),
            saving=Decimal("-10"),
        ),
    )
    insert(
        engine,
        TABLE,
        month(
            tenant_id,
            credit_id,
            month=date(2026, 12, 1),
            state="UNOBSERVED",
            cost=None,
            saving=None,
        ),
    )


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"state": "GUESSED"}, "ck_savings_credit_month__state"),
        ({"month": date(2026, 10, 2)}, "ck_savings_credit_month__first_of_month"),
        ({"state": "UNOBSERVED"}, "ck_savings_credit_month__observed"),
        ({"cost": None, "saving": None}, "ck_savings_credit_month__observed"),
        ({"saving": None}, "ck_savings_credit_month__observed"),
        ({"saving": Decimal("0")}, "ck_savings_credit_month__held_saved"),
        (
            {"state": "REGRESSED", "saving": Decimal("5")},
            "ck_savings_credit_month__regressed_did_not",
        ),
        ({"cost": Decimal("-1")}, "ck_savings_credit_month__cost_not_negative"),
        (
            {"collected_at": AT - timedelta(seconds=1)},
            "ck_savings_credit_month__collected_after_true",
        ),
    ],
)
def test_a_month_breaking_a_rule_is_refused(
    engine: Engine,
    tenant_id: UUID,
    credit_id: UUID,
    overrides: dict[str, Any],
    constraint: str,
) -> None:
    refused(engine, TABLE, month(tenant_id, credit_id, **overrides), constraint)


def test_a_credit_has_one_row_a_month(engine: Engine, tenant_id: UUID, credit_id: UUID) -> None:
    insert(engine, TABLE, month(tenant_id, credit_id))
    refused(engine, TABLE, month(tenant_id, credit_id), "uq_savings_credit_month__month")


def test_a_credit_cannot_be_removed_while_a_month_rests_on_it(
    engine: Engine, tenant_id: UUID, credit_id: UUID
) -> None:
    insert(engine, TABLE, month(tenant_id, credit_id))
    with (
        pytest.raises(IntegrityError, match="fk_savings_credit_month__credit"),
        engine.begin() as connection,
    ):
        connection.execute(
            text("DELETE FROM savings_credit WHERE credit_id = :c"), {"c": credit_id}
        )
