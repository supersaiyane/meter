"""Every target a provider ranked for a recommendation, each priced from the catalog or not.

Revision ID: 0038_recommendation_option
Revises: 0037_spot_prices_schedule
Create Date: 2026-10-08

TASK-P9-006, P9 spec section 5.5, constraint 11. The spec's data model gave the recommendation one
target, 0033, and asked for every ranked option to be kept; OPEN-23 records the table this adds to
hold them, with the recommendation for it.

**Priced, or says why not, never both and never neither.** An option's price is a recorded
`price` row, by a foreign key, with its version and its hourly price beside it; an option the
catalog cannot price has none of the three and a reason instead. So an unpriced option is never a
price of nought, and a priced one is never a figure from nowhere.

**The provider's figures are kept as it gave them.** The rank, the performance risk on its own
scale of nought to four, its monthly saving where it gives one, the migration effort and the
platform differences. The saving has no sign constraint: an option to a larger type costs more,
and its figure says so.

**Per tenant, scoped through its recommendation**, as `recommendation_event` is, so a reader who
may not see a finding cannot see what it was compared with.

Backward compatible, constraint 12: one new table nothing old reads or writes. The downgrade
drops it.
"""

from __future__ import annotations

from alembic import op

revision = "0038_recommendation_option"
down_revision = "0037_spot_prices_schedule"
branch_labels = None
depends_on = None

_UP = (
    """
    CREATE TABLE IF NOT EXISTS recommendation_option (
        option_pk                UUID            PRIMARY KEY,
        tenant_id                UUID            NOT NULL REFERENCES tenant(tenant_id),
        recommendation_id        UUID            NOT NULL
            REFERENCES recommendation(recommendation_id),
        region                   TEXT            NOT NULL,
        rank                     SMALLINT        NOT NULL,
        instance_type            TEXT            NOT NULL,
        performance_risk         NUMERIC(3, 1)   NOT NULL,
        provider_monthly_saving  NUMERIC(20, 10),
        migration_effort         TEXT,
        platform_differences     TEXT[]          NOT NULL DEFAULT '{}',
        sku_price_id             TEXT,
        price_version            TEXT,
        hourly_price             NUMERIC(20, 10),
        unpriced_reason          TEXT,
        as_of                    TIMESTAMPTZ     NOT NULL,
        collected_at             TIMESTAMPTZ     NOT NULL,
        CONSTRAINT uq_recommendation_option__rank UNIQUE (recommendation_id, rank),
        CONSTRAINT ck_recommendation_option__ranked CHECK (rank >= 1),
        CONSTRAINT ck_recommendation_option__named CHECK (length(instance_type) > 0),
        CONSTRAINT ck_recommendation_option__risk
            CHECK (performance_risk >= 0 AND performance_risk <= 4),
        CONSTRAINT ck_recommendation_option__priced_or_says_why CHECK (
            (sku_price_id IS NULL) = (price_version IS NULL)
            AND (sku_price_id IS NULL) = (hourly_price IS NULL)
            AND (sku_price_id IS NULL) = (unpriced_reason IS NOT NULL)
            AND (unpriced_reason IS NULL OR length(unpriced_reason) > 0)
        ),
        CONSTRAINT ck_recommendation_option__price_positive
            CHECK (hourly_price IS NULL OR hourly_price > 0),
        CONSTRAINT fk_recommendation_option__price
            FOREIGN KEY (tenant_id, region, sku_price_id, price_version)
            REFERENCES price (tenant_id, region, sku_price_id, version),
        CONSTRAINT ck_recommendation_option__collected_after_true CHECK (collected_at >= as_of)
    )
    """,
    # The read the screen and the alternatives table make: one recommendation's options in rank.
    """
    CREATE INDEX IF NOT EXISTS ix_recommendation_option__recommendation
        ON recommendation_option (tenant_id, recommendation_id, rank)
    """,
)

_DOWN = ("DROP TABLE IF EXISTS recommendation_option",)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWN:
        op.execute(statement)
