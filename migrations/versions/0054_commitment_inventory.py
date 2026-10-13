"""What each member account holds, and the collector's cadence. FEAT-086, TASK-P14-002.

Revision ID: 0054_commitment_inventory
Revises: 0053_ai_spend_screen
Create Date: 2026-10-13

P14 spec sections 5.3 and 6. One row per commitment, keyed by the tenant, its kind and the source's
own identifier: a Savings Plan or a reservation, with its real start, end, term, payment option and
the hourly commitment or the quantity it buys. The constraints hold what the domain holds: exactly
one of quantity and hourly commitment, a positive term, an end after a start, amounts that are not
negative, and a fact collected no earlier than it was true, constraints 10 and 11.

And the `commitment_inventory` cadence for every tenant that existed before it, ISS-287, a copy of
its `DEFAULT_SCHEDULE` entry held to it by `tests/ingest/test_registry.py`. Backward compatible,
constraint 12: a new table and rows an old worker has no collector for. The downgrade removes both.
"""

from __future__ import annotations

from alembic import op

revision = "0054_commitment_inventory"
down_revision = "0053_ai_spend_screen"
branch_labels = None
depends_on = None

_BY = "migration 0054_commitment_inventory"

#: A copy of the entry in `finops_ingest.registry.DEFAULT_SCHEDULE`: cadence, reason, cost.
_SCHEDULE: dict[str, tuple[int, str, str]] = {
    "commitment_inventory": (
        86400,
        (
            "What each member account holds, P14 spec section 5.3. Daily: a commitment's term, "
            "end and state change at most once a day, and the calendar counts months. Savings "
            "Plans and RDS reservations come through the relay, ADR-0037, EC2 reservations "
            "through its endpoint, as each account's collector role: modelled at about 0.00001 "
            "USD a run in Lambda and S3 requests, and not measured until an account is read, "
            "ISS-002. ADR-0012 and constraint 9."
        ),
        "0.00001",
    ),
}

_TABLE = """
CREATE TABLE IF NOT EXISTS commitment_inventory (
    tenant_id          UUID            NOT NULL REFERENCES tenant(tenant_id),
    ingest_run_id      UUID            NOT NULL,
    kind               TEXT            NOT NULL,
    commitment_id      TEXT            NOT NULL,
    program            TEXT            NOT NULL,
    account_id         TEXT            NOT NULL,
    region_id          TEXT,
    applies_to         TEXT,
    quantity           INTEGER,
    hourly_commitment  NUMERIC(20, 10),
    term_months        INTEGER         NOT NULL,
    payment_option     TEXT            NOT NULL,
    upfront_amount     NUMERIC(20, 10) NOT NULL,
    recurring_hourly   NUMERIC(20, 10) NOT NULL,
    currency           TEXT            NOT NULL,
    starts_at          TIMESTAMPTZ     NOT NULL,
    ends_at            TIMESTAMPTZ     NOT NULL,
    state              TEXT            NOT NULL,
    as_of              TIMESTAMPTZ     NOT NULL,
    collected_at       TIMESTAMPTZ     NOT NULL,
    CONSTRAINT pk_commitment_inventory PRIMARY KEY (tenant_id, kind, commitment_id),
    CONSTRAINT ck_commitment_inventory__kind CHECK (kind IN ('savings_plan', 'reservation')),
    CONSTRAINT ck_commitment_inventory__one_measure CHECK (
        (quantity IS NULL) <> (hourly_commitment IS NULL)),
    CONSTRAINT ck_commitment_inventory__positive CHECK (
        term_months > 0 AND (quantity IS NULL OR quantity > 0)
        AND (hourly_commitment IS NULL OR hourly_commitment > 0)
        AND upfront_amount >= 0 AND recurring_hourly >= 0),
    CONSTRAINT ck_commitment_inventory__ends_after_start CHECK (ends_at > starts_at),
    CONSTRAINT ck_commitment_inventory__collected_after_true CHECK (collected_at >= as_of)
)
"""

_INDEX = (
    "CREATE INDEX IF NOT EXISTS ix_commitment_inventory__ends "
    "ON commitment_inventory (tenant_id, ends_at)"
)


def _literal(text: str) -> str:
    """A SQL string literal, its apostrophes doubled."""
    return "'" + text.replace("'", "''") + "'"


def upgrade() -> None:
    op.execute(_TABLE)
    op.execute(_INDEX)
    for collector, (cadence, reason, cost) in _SCHEDULE.items():
        op.execute(
            "INSERT INTO collector_schedule (tenant_id, collector, cadence_seconds, reason, "
            "est_cost_per_run, updated_by, runs_in) "
            f"SELECT tenant_id, {_literal(collector)}, {cadence}, {_literal(reason)}, {cost}, "
            f"{_literal(_BY)}, 'worker' FROM tenant "
            "ON CONFLICT (tenant_id, collector) DO NOTHING"
        )


def downgrade() -> None:
    op.execute(f"DELETE FROM collector_schedule WHERE updated_by = {_literal(_BY)}")
    op.execute("DROP TABLE IF EXISTS commitment_inventory")
