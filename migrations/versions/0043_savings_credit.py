"""A credit for every verified saving, to its owner, team and who closed it.

Revision ID: 0043_savings_credit
Revises: 0042_creator_lookup
Create Date: 2026-10-08

TASK-P11-006, FEAT-078, P11 spec section 5.5. When FEAT-029 records a VERIFIED saving, the
`savings_ledger` collector writes one credit: the recommendation's owner, the team its strongest
team suggestion named, the person who moved it to DONE, and the verified monthly saving, measured.
An INCONCLUSIVE or REGRESSED verdict earns nothing.

Constraint 11: one credit per verified saving, a saving above nought, an owner and a closer who
are named, a team that is named or absent but never blank, and nothing collected before it was
true. A verification cannot be removed while a credit rests on it: the ledger withdraws the
credit first, and only `principal_scope` cascades. Scoped by account, `ByAccount`, constraint 3.

Backward compatible, constraint 12: a new table, and a `collector_schedule` row for every tenant,
which an old worker has no collector for and does not run. The downgrade removes both.
"""

from __future__ import annotations

from alembic import op

revision = "0043_savings_credit"
down_revision = "0042_creator_lookup"
branch_labels = None
depends_on = None

#: A copy of the `savings_ledger` entry in `finops_ingest.registry.DEFAULT_SCHEDULE`.
_CADENCE_SECONDS = 86400
_REASON = (
    "Daily, P11 specification section 7. Reads only what Meter already holds, FEAT-029's "
    "verdicts, the recommendations' owners and the bill's daily cost, with no AWS call. A "
    "verdict is reached at most once a day, so a daily read credits a verified saving at most a "
    "day after it verifies. ADR-0012, constraint 9 and FEAT-078."
)
_COST_PER_RUN = "0"
#: The reason as a SQL string literal: it holds apostrophes, which a literal doubles.
_REASON_LITERAL = _REASON.replace("'", "''")

_UP = (
    """
    CREATE TABLE IF NOT EXISTS savings_credit (
        credit_id                UUID           PRIMARY KEY,
        tenant_id                UUID           NOT NULL REFERENCES tenant(tenant_id),
        ingest_run_id            UUID           NOT NULL,
        sub_account_id           TEXT           NOT NULL,
        recommendation_id        UUID           NOT NULL
            REFERENCES recommendation(recommendation_id),
        realized_id              UUID           NOT NULL,
        owner                    TEXT           NOT NULL,
        team                     TEXT,
        closed_by                TEXT           NOT NULL,
        verified_monthly_saving  NUMERIC(20, 10) NOT NULL,
        verified_on              DATE           NOT NULL,
        as_of                    TIMESTAMPTZ    NOT NULL,
        collected_at             TIMESTAMPTZ    NOT NULL,
        CONSTRAINT uq_savings_credit__realized UNIQUE (realized_id),
        CONSTRAINT fk_savings_credit__realized
            FOREIGN KEY (realized_id) REFERENCES realized_saving(realized_id),
        CONSTRAINT ck_savings_credit__named
            CHECK (length(trim(owner)) > 0 AND length(trim(closed_by)) > 0
                   AND (team IS NULL OR length(trim(team)) > 0)),
        CONSTRAINT ck_savings_credit__saved CHECK (verified_monthly_saving > 0),
        CONSTRAINT ck_savings_credit__collected_after_true CHECK (collected_at >= as_of)
    )
    """,
    f"""
    INSERT INTO collector_schedule
        (tenant_id, collector, cadence_seconds, reason, est_cost_per_run, updated_by, runs_in)
    SELECT tenant_id, 'savings_ledger', {_CADENCE_SECONDS}, '{_REASON_LITERAL}', {_COST_PER_RUN},
           'migration 0043_savings_credit', 'worker'
    FROM tenant
    ON CONFLICT (tenant_id, collector) DO NOTHING
    """,
)

_DOWN = (
    "DELETE FROM collector_schedule WHERE collector = 'savings_ledger'",
    "DROP TABLE IF EXISTS savings_credit",
)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWN:
        op.execute(statement)
