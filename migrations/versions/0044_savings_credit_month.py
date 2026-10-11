"""Each closed month after a saving verified: held, regressed, or unobserved.

Revision ID: 0044_savings_credit_month
Revises: 0043_savings_credit
Create Date: 2026-10-11

TASK-P11-007, FEAT-078, P11 spec section 5.5. The `savings_ledger` collector judges every closed
month after a credit's saving verified against the cost before the change, at FEAT-029's daily
rate, `finops_query.ledger`. A credit's total is the sum of its held months.

Constraint 11: a month is the first of a month; HELD, REGRESSED or UNOBSERVED; an unobserved month
carries neither a cost nor a saving and every other carries both; a held month saved more than
nought and a regressed one did not; no cost below nought; one row per credit per month; nothing
collected before it was true. The link to the credit does not cascade: the ledger removes a
credit's months before the credit. Scoped by account, `ByAccount`, constraint 3.

Backward compatible, constraint 12: a new table an old release never reads. The downgrade drops it.
"""

from __future__ import annotations

from alembic import op

revision = "0044_savings_credit_month"
down_revision = "0043_savings_credit"
branch_labels = None
depends_on = None

_UP = (
    """
    CREATE TABLE IF NOT EXISTS savings_credit_month (
        month_pk        UUID            PRIMARY KEY,
        tenant_id       UUID            NOT NULL REFERENCES tenant(tenant_id),
        ingest_run_id   UUID            NOT NULL,
        sub_account_id  TEXT            NOT NULL,
        credit_id       UUID            NOT NULL,
        month           DATE            NOT NULL,
        state           TEXT            NOT NULL,
        cost            NUMERIC(20, 10),
        saving          NUMERIC(20, 10),
        as_of           TIMESTAMPTZ     NOT NULL,
        collected_at    TIMESTAMPTZ     NOT NULL,
        CONSTRAINT fk_savings_credit_month__credit
            FOREIGN KEY (credit_id) REFERENCES savings_credit(credit_id),
        CONSTRAINT uq_savings_credit_month__month UNIQUE (credit_id, month),
        CONSTRAINT ck_savings_credit_month__state
            CHECK (state IN ('HELD', 'REGRESSED', 'UNOBSERVED')),
        CONSTRAINT ck_savings_credit_month__first_of_month CHECK (extract(day FROM month) = 1),
        CONSTRAINT ck_savings_credit_month__observed
            CHECK (((state = 'UNOBSERVED') = (cost IS NULL))
                   AND ((cost IS NULL) = (saving IS NULL))),
        CONSTRAINT ck_savings_credit_month__held_saved CHECK (state <> 'HELD' OR saving > 0),
        CONSTRAINT ck_savings_credit_month__regressed_did_not
            CHECK (state <> 'REGRESSED' OR saving <= 0),
        CONSTRAINT ck_savings_credit_month__cost_not_negative CHECK (cost IS NULL OR cost >= 0),
        CONSTRAINT ck_savings_credit_month__collected_after_true CHECK (collected_at >= as_of)
    )
    """,
)

_DOWN = ("DROP TABLE IF EXISTS savings_credit_month",)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWN:
        op.execute(statement)
