"""Who an estate says owns each resource, and the collector's cadence that reads it.

Revision ID: 0041_resource_owner
Revises: 0040_option_risk_optional
Create Date: 2026-10-08

TASK-P11-002, FEAT-077, P11 spec sections 5.1, 6 and 7. One row per resource per source, the
catalogue, a tag or the creator, rewritten by each run of the `ownership` collector, each with
the detail that lets a reader check it and its two timestamps, constraint 10. The rules a
suggestion keeps in `finops_core/domain/ownership.py` are constraints here too, constraint 11: a
tag names a team, and a creator is a person or a pipeline, never a team. Scoped by account, the
guard's `ByAccount`, constraint 3. The Region is null for a resource the provider holds in no
Region, as the inventory's own nodes allow.

The `ownership` schedule row is installed for every tenant before this, as
`install_default_schedule` gives a tenant onboarded later, and `tests/ingest/test_registry.py`
holds the two to the same words.

Backward compatible, constraint 12: a new table an old release never reads, and a schedule row an
old worker has no collector for and does not run. The downgrade removes both.
"""

from __future__ import annotations

from alembic import op

revision = "0041_resource_owner"
down_revision = "0040_option_risk_optional"
branch_labels = None
depends_on = None

#: A copy of the `ownership` entry in `finops_ingest.registry.DEFAULT_SCHEDULE`.
_CADENCE_SECONDS = 86400
_REASON = (
    "Daily, P11 specification section 7. Tags are read from the inventory Meter already holds, "
    "with no AWS call; the service catalogue, AWS AppRegistry, is read once per account and "
    "Region; CloudTrail's event history is asked once for each resource that has no creator "
    "yet, and never again. Owners change when teams reorganise, not by the hour, so a daily "
    "read keeps a suggestion at most a day behind. ADR-0012, constraint 9 and FEAT-077."
)
_COST_PER_RUN = "0.0005"
#: The reason as a SQL string literal: it holds apostrophes, which a literal doubles.
_REASON_LITERAL = _REASON.replace("'", "''")

_UP = (
    """
    CREATE TABLE IF NOT EXISTS resource_owner (
        owner_pk        UUID         PRIMARY KEY,
        tenant_id       UUID         NOT NULL REFERENCES tenant(tenant_id),
        ingest_run_id   UUID         NOT NULL,
        sub_account_id  TEXT         NOT NULL,
        region_id       TEXT,
        resource_id     TEXT         NOT NULL,
        source          TEXT         NOT NULL,
        owner           TEXT         NOT NULL,
        owner_kind      TEXT         NOT NULL,
        detail          TEXT         NOT NULL,
        as_of           TIMESTAMPTZ  NOT NULL,
        collected_at    TIMESTAMPTZ  NOT NULL,
        CONSTRAINT uq_resource_owner__source
            UNIQUE (tenant_id, sub_account_id, resource_id, source),
        CONSTRAINT ck_resource_owner__source
            CHECK (source IN ('CATALOGUE', 'TAG', 'CREATOR')),
        CONSTRAINT ck_resource_owner__kind
            CHECK (owner_kind IN ('TEAM', 'PERSON', 'AUTOMATION')),
        CONSTRAINT ck_resource_owner__tag_names_a_team
            CHECK (source <> 'TAG' OR owner_kind = 'TEAM'),
        CONSTRAINT ck_resource_owner__creator_is_no_team
            CHECK (source <> 'CREATOR' OR owner_kind <> 'TEAM'),
        CONSTRAINT ck_resource_owner__named
            CHECK (length(trim(owner)) > 0 AND length(trim(detail)) > 0
                   AND length(trim(resource_id)) > 0),
        CONSTRAINT ck_resource_owner__collected_after_true CHECK (collected_at >= as_of)
    )
    """,
    f"""
    INSERT INTO collector_schedule
        (tenant_id, collector, cadence_seconds, reason, est_cost_per_run, updated_by, runs_in)
    SELECT tenant_id, 'ownership', {_CADENCE_SECONDS}, '{_REASON_LITERAL}', {_COST_PER_RUN},
           'migration 0041_resource_owner', 'worker'
    FROM tenant
    ON CONFLICT (tenant_id, collector) DO NOTHING
    """,
)

_DOWN = (
    "DELETE FROM collector_schedule WHERE collector = 'ownership'",
    "DROP TABLE IF EXISTS resource_owner",
)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWN:
        op.execute(statement)
