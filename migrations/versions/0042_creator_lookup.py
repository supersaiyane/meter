"""Which resources CloudTrail has been asked about, so none is asked twice.

Revision ID: 0042_creator_lookup
Revises: 0041_resource_owner
Create Date: 2026-10-08

TASK-P11-004, FEAT-077, P11 spec section 5.4 and OPEN-26. A resource's creator is read once from
CloudTrail's event history and never again: either the creating event is found, and its principal
is a CREATOR row in `resource_owner`, or the resource is older than the history reaches, and that
is recorded here with how far back the history went, so it is said rather than guessed and not
asked again. A resource older than the history today stays older, so the answer never changes.

Constraint 11: a lookup is FOUND or BEFORE_HISTORY, and BEFORE_HISTORY carries the start of the
history it searched while FOUND carries none. Scoped by account, `ByAccount`, constraint 3.

Backward compatible, constraint 12: a new table an old release never reads. The downgrade drops it,
and the next run asks again.
"""

from __future__ import annotations

from alembic import op

revision = "0042_creator_lookup"
down_revision = "0041_resource_owner"
branch_labels = None
depends_on = None

_UP = (
    """
    CREATE TABLE IF NOT EXISTS creator_lookup (
        lookup_pk        UUID         PRIMARY KEY,
        tenant_id        UUID         NOT NULL REFERENCES tenant(tenant_id),
        ingest_run_id    UUID         NOT NULL,
        sub_account_id   TEXT         NOT NULL,
        region_id        TEXT         NOT NULL,
        resource_id      TEXT         NOT NULL,
        outcome          TEXT         NOT NULL,
        history_starts   TIMESTAMPTZ,
        as_of            TIMESTAMPTZ  NOT NULL,
        collected_at     TIMESTAMPTZ  NOT NULL,
        CONSTRAINT uq_creator_lookup__resource
            UNIQUE (tenant_id, sub_account_id, resource_id),
        CONSTRAINT ck_creator_lookup__outcome
            CHECK (outcome IN ('FOUND', 'BEFORE_HISTORY')),
        CONSTRAINT ck_creator_lookup__history_said
            CHECK ((outcome = 'BEFORE_HISTORY') = (history_starts IS NOT NULL)),
        CONSTRAINT ck_creator_lookup__named CHECK (length(trim(resource_id)) > 0),
        CONSTRAINT ck_creator_lookup__collected_after_true CHECK (collected_at >= as_of)
    )
    """,
)

_DOWN = ("DROP TABLE IF EXISTS creator_lookup",)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWN:
        op.execute(statement)
