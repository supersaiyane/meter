"""Scheduled reports: the schedule, what a run records, and which process runs the cadence.

Revision ID: 0029_report_schedule
Revises: 0028_saved_view
Create Date: 2026-10-07

TASK-P8-011 and FEAT-069, P8 spec sections 5.7 and 6.

**The schedule.** A saved view, one of the routes its screen exports, a format, a cadence and the
people it renders for. Every invariant in the spec is the database's to refuse, constraint 11,
including the one a check cannot express: that the view is one its owner can open, which a
trigger holds on every write that names the view or the owner. A view deleted afterwards leaves
its schedules in place with no view, rather than deleting other people's schedules with it; the
runner records why for each recipient once and pauses the schedule, ADR-0033.

**The run.** `report_run` already records every file an export writes. A scheduled run adds the
schedule, a status, where the file is kept, the typed cause of a failure, the freshness of what
it read and when it finished. A failure carries one of the seven causes, a stored file carries a
key, and a file streamed to the person who pressed Export carries neither.

**The cadence.** The schedules are looked at on the cadence in `collector_schedule`, ADR-0012,
but by the API rather than the ingest worker, ADR-0033, so each row now says which process runs
it. Every existing row is the worker's.

Backward compatible, constraint 12. A new table; new columns that are nullable or have a default
the old code never contradicts; a new column on `collector_schedule` that defaults to what every
row already means. The downgrade drops all three.
"""

from __future__ import annotations

from alembic import op

revision = "0029_report_schedule"
down_revision = "0028_saved_view"
branch_labels = None
depends_on = None

#: The seven causes, as in every other table that records one. A copy, as 0028 copies its screens.
_CAUSES = (
    "AccessDenied",
    "Throttled",
    "NotOptedIn",
    "NoData",
    "Unreachable",
    "SchemaDrift",
    "Misconfigured",
)
_IN_CAUSES = ", ".join(f"'{cause}'" for cause in _CAUSES)

#: The cadence row this migration installs for every tenant that exists. A copy of the
#: `report_schedules` entry in `finops_ingest.registry.DEFAULT_SCHEDULE`, which installs it for a
#: tenant onboarded later.
_CADENCE_SECONDS = 900
_REASON = (
    "A schedule falls due at a fixed hour at most once a day, so looking every fifteen minutes "
    "renders each within a quarter of an hour of its time. A look reads the due schedules and "
    "renders through the API in process, calling no provider and no model, so its cost is a "
    "query, and an S3 request for each file written. ADR-0012, ADR-0033 and FEAT-069."
)
_COST_PER_RUN = "0.000005"

_UP = (
    # ------------------------------------------------------------------ the schedule
    """
    CREATE TABLE IF NOT EXISTS report_schedule (
        schedule_id  UUID         PRIMARY KEY,
        tenant_id    UUID         NOT NULL REFERENCES tenant(tenant_id),
        owner_id     TEXT         NOT NULL,
        view_id      UUID         REFERENCES saved_view(view_id) ON DELETE SET NULL,
        export_path  TEXT         NOT NULL,
        format       TEXT         NOT NULL,
        cadence      TEXT         NOT NULL,
        recipients   TEXT[]       NOT NULL,
        enabled      BOOLEAN      NOT NULL,
        next_run_at  TIMESTAMPTZ  NOT NULL,
        created_at   TIMESTAMPTZ  NOT NULL,
        updated_at   TIMESTAMPTZ  NOT NULL
    )
    """,
    "ALTER TABLE report_schedule DROP CONSTRAINT IF EXISTS ck_report_schedule__format",
    """
    ALTER TABLE report_schedule
        ADD CONSTRAINT ck_report_schedule__format CHECK (format IN ('xlsx', 'csv'))
    """,
    "ALTER TABLE report_schedule DROP CONSTRAINT IF EXISTS ck_report_schedule__cadence",
    """
    ALTER TABLE report_schedule
        ADD CONSTRAINT ck_report_schedule__cadence
        CHECK (cadence IN ('DAILY', 'WEEKLY', 'MONTHLY', 'MONTH_CLOSE'))
    """,
    "ALTER TABLE report_schedule DROP CONSTRAINT IF EXISTS ck_report_schedule__recipients",
    """
    ALTER TABLE report_schedule
        ADD CONSTRAINT ck_report_schedule__recipients
        CHECK (cardinality(recipients) BETWEEN 1 AND 50 AND NOT ('' = ANY (recipients)))
    """,
    "ALTER TABLE report_schedule DROP CONSTRAINT IF EXISTS ck_report_schedule__named",
    """
    ALTER TABLE report_schedule
        ADD CONSTRAINT ck_report_schedule__named CHECK (length(trim(owner_id)) > 0)
    """,
    "ALTER TABLE report_schedule DROP CONSTRAINT IF EXISTS ck_report_schedule__path",
    """
    ALTER TABLE report_schedule
        ADD CONSTRAINT ck_report_schedule__path
        CHECK (export_path LIKE '/api/v1/%' AND position('format=' in export_path) = 0)
    """,
    "ALTER TABLE report_schedule DROP CONSTRAINT IF EXISTS ck_report_schedule__times",
    """
    ALTER TABLE report_schedule
        ADD CONSTRAINT ck_report_schedule__times CHECK (updated_at >= created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_report_schedule__due
        ON report_schedule (next_run_at) WHERE enabled
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_report_schedule__owner
        ON report_schedule (tenant_id, owner_id, updated_at)
    """,
    "CREATE INDEX IF NOT EXISTS ix_report_schedule__view ON report_schedule (view_id)",
    # The one invariant a check cannot hold, because it reads another table: the view must be
    # one the schedule's owner can open, their own or a shared one, in the schedule's tenant.
    """
    CREATE OR REPLACE FUNCTION report_schedule_view_visible() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.view_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM saved_view v
            WHERE v.view_id = NEW.view_id
              AND v.tenant_id = NEW.tenant_id
              AND (v.owner_id = NEW.owner_id OR v.visibility = 'SHARED')
        ) THEN
            RAISE EXCEPTION USING
                ERRCODE = 'check_violation',
                MESSAGE = 'a report schedule names a view its owner cannot open';
        END IF;
        RETURN NEW;
    END
    $$
    """,
    "DROP TRIGGER IF EXISTS tr_report_schedule__view_visible ON report_schedule",
    """
    CREATE TRIGGER tr_report_schedule__view_visible
        BEFORE INSERT OR UPDATE OF view_id, owner_id, tenant_id ON report_schedule
        FOR EACH ROW EXECUTE FUNCTION report_schedule_view_visible()
    """,
    # ------------------------------------------------------------------ the run
    """
    ALTER TABLE report_run ADD COLUMN IF NOT EXISTS schedule_id UUID
        REFERENCES report_schedule(schedule_id) ON DELETE SET NULL
    """,
    "ALTER TABLE report_run ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'STREAMED'",
    "ALTER TABLE report_run ADD COLUMN IF NOT EXISTS storage_key TEXT",
    "ALTER TABLE report_run ADD COLUMN IF NOT EXISTS failure_cause TEXT",
    "ALTER TABLE report_run ADD COLUMN IF NOT EXISTS failure_detail TEXT",
    "ALTER TABLE report_run ADD COLUMN IF NOT EXISTS as_of TIMESTAMPTZ",
    "ALTER TABLE report_run ADD COLUMN IF NOT EXISTS collected_at TIMESTAMPTZ",
    "ALTER TABLE report_run ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ",
    # Every row before this one was a file streamed to the person who asked for it, finished
    # the moment it was made.
    "UPDATE report_run SET finished_at = made_at WHERE finished_at IS NULL",
    "ALTER TABLE report_run DROP CONSTRAINT IF EXISTS ck_report_run__status",
    """
    ALTER TABLE report_run
        ADD CONSTRAINT ck_report_run__status
        CHECK (status IN ('STREAMED', 'RENDERED', 'SENT', 'FAILED'))
    """,
    "ALTER TABLE report_run DROP CONSTRAINT IF EXISTS ck_report_run__failure",
    f"""
    ALTER TABLE report_run
        ADD CONSTRAINT ck_report_run__failure
        CHECK ((status = 'FAILED') = (failure_cause IS NOT NULL)
               AND (failure_cause IS NULL OR failure_cause IN ({_IN_CAUSES})))
    """,
    "ALTER TABLE report_run DROP CONSTRAINT IF EXISTS ck_report_run__stored",
    """
    ALTER TABLE report_run
        ADD CONSTRAINT ck_report_run__stored
        CHECK (status NOT IN ('RENDERED', 'SENT') OR storage_key IS NOT NULL)
    """,
    "ALTER TABLE report_run DROP CONSTRAINT IF EXISTS ck_report_run__streamed",
    """
    ALTER TABLE report_run
        ADD CONSTRAINT ck_report_run__streamed
        CHECK (status <> 'STREAMED' OR (storage_key IS NULL AND schedule_id IS NULL))
    """,
    "ALTER TABLE report_run DROP CONSTRAINT IF EXISTS ck_report_run__finished",
    """
    ALTER TABLE report_run
        ADD CONSTRAINT ck_report_run__finished CHECK (finished_at IS NULL OR finished_at >= made_at)
    """,
    "CREATE INDEX IF NOT EXISTS ix_report_run__schedule ON report_run (schedule_id)",
    # ------------------------------------------------------------------ the cadence
    """
    ALTER TABLE collector_schedule
        ADD COLUMN IF NOT EXISTS runs_in TEXT NOT NULL DEFAULT 'worker'
    """,
    "ALTER TABLE collector_schedule DROP CONSTRAINT IF EXISTS ck_collector_schedule__runs_in",
    """
    ALTER TABLE collector_schedule
        ADD CONSTRAINT ck_collector_schedule__runs_in CHECK (runs_in IN ('worker', 'api'))
    """,
    f"""
    INSERT INTO collector_schedule
        (tenant_id, collector, cadence_seconds, reason, est_cost_per_run, updated_by, runs_in)
    SELECT tenant_id, 'report_schedules', {_CADENCE_SECONDS}, '{_REASON}', {_COST_PER_RUN},
           'migration 0029_report_schedule', 'api'
    FROM tenant
    ON CONFLICT (tenant_id, collector) DO NOTHING
    """,
)


_DOWN = (
    "DELETE FROM collector_schedule WHERE collector = 'report_schedules'",
    "ALTER TABLE collector_schedule DROP CONSTRAINT IF EXISTS ck_collector_schedule__runs_in",
    "ALTER TABLE collector_schedule DROP COLUMN IF EXISTS runs_in",
    "DROP INDEX IF EXISTS ix_report_run__schedule",
    "ALTER TABLE report_run DROP CONSTRAINT IF EXISTS ck_report_run__finished",
    "ALTER TABLE report_run DROP CONSTRAINT IF EXISTS ck_report_run__streamed",
    "ALTER TABLE report_run DROP CONSTRAINT IF EXISTS ck_report_run__stored",
    "ALTER TABLE report_run DROP CONSTRAINT IF EXISTS ck_report_run__failure",
    "ALTER TABLE report_run DROP CONSTRAINT IF EXISTS ck_report_run__status",
    "ALTER TABLE report_run DROP COLUMN IF EXISTS finished_at",
    "ALTER TABLE report_run DROP COLUMN IF EXISTS collected_at",
    "ALTER TABLE report_run DROP COLUMN IF EXISTS as_of",
    "ALTER TABLE report_run DROP COLUMN IF EXISTS failure_detail",
    "ALTER TABLE report_run DROP COLUMN IF EXISTS failure_cause",
    "ALTER TABLE report_run DROP COLUMN IF EXISTS storage_key",
    "ALTER TABLE report_run DROP COLUMN IF EXISTS status",
    "ALTER TABLE report_run DROP COLUMN IF EXISTS schedule_id",
    "DROP TABLE IF EXISTS report_schedule",
    "DROP FUNCTION IF EXISTS report_schedule_view_visible()",
)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWN:
        op.execute(statement)
