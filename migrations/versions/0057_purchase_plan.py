"""Meter's purchase plans, their lines and their events, and the collector's cadence. FEAT-089.

Revision ID: 0057_purchase_plan
Revises: 0056_purchase_recommendation
Create Date: 2026-10-13

TASK-P14-007, P14 spec sections 5.2, 5.6 and 6. One plan per tenant per month, drafted under the
policy it names, with a line per program, family, Region and tranche and every figure modelled. A
plan's status is one of six names, and a transition out of order is refused by the database as well
as by the API, constraint 11: an insert must be a draft, and a change of status must be one the
lifecycle allows, so no path that forgets the rule can write a plan bought before it was approved.
Each transition is an event with the principal and the time, and an event naming a transition out
of order is refused by its own check.

And the `purchase_plan` cadence for every tenant that existed before it, ISS-287, a copy of its
`DEFAULT_SCHEDULE` entry. Backward compatible, constraint 12. The downgrade removes all of it.
"""

from __future__ import annotations

from alembic import op

revision = "0057_purchase_plan"
down_revision = "0056_purchase_recommendation"
branch_labels = None
depends_on = None

_BY = "migration 0057_purchase_plan"

#: A copy of the entry in `finops_ingest.registry.DEFAULT_SCHEDULE`: cadence, reason, cost.
_SCHEDULE: dict[str, tuple[int, str, str]] = {
    "purchase_plan": (
        86400,
        (
            "Meter's own purchase plan, P14 spec section 5.6. Daily, after the bill, the "
            "inventory and P9's rates it reads: it drafts this month's plan, redrafts a plan "
            "nobody has approved yet, and lapses a draft from an earlier month. It reads only "
            "Meter's own tables, so its cost per run is zero. ADR-0012 and constraint 9."
        ),
        "0",
    ),
}

#: The transitions the lifecycle allows, spec section 5.2. One list, read by the event's check and
#: by the plan's trigger, so the two cannot disagree.
_ALLOWED = (
    "(from_status = 'DRAFT' AND to_status IN ('APPROVED', 'WITHDRAWN', 'LAPSED')) "
    "OR (from_status = 'APPROVED' AND to_status IN ('BOUGHT', 'WITHDRAWN')) "
    "OR (from_status = 'BOUGHT' AND to_status = 'VERIFIED')"
)

_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS purchase_plan (
        plan_id             UUID           PRIMARY KEY,
        tenant_id           UUID           NOT NULL REFERENCES tenant(tenant_id),
        ingest_run_id       UUID           NOT NULL,
        plan_month          DATE           NOT NULL,
        status              TEXT           NOT NULL DEFAULT 'DRAFT',
        target_coverage     NUMERIC(4, 3)  NOT NULL,
        term_years          INTEGER        NOT NULL,
        payment_option      TEXT           NOT NULL,
        ladder_limit        NUMERIC(5, 4)  NOT NULL,
        window_start        DATE           NOT NULL,
        window_end          DATE           NOT NULL,
        days_held           INTEGER        NOT NULL,
        steady_hourly       NUMERIC(20, 4),
        held_hourly         NUMERIC(20, 4),
        target_hourly       NUMERIC(20, 4),
        beyond_hourly       NUMERIC(20, 4),
        unpriced            JSONB          NOT NULL DEFAULT '[]'::jsonb,
        no_purchase_reason  TEXT,
        currency            TEXT           NOT NULL,
        as_of               TIMESTAMPTZ    NOT NULL,
        collected_at        TIMESTAMPTZ    NOT NULL,
        CONSTRAINT uq_purchase_plan__month UNIQUE (tenant_id, plan_month),
        CONSTRAINT ck_purchase_plan__status CHECK (
            status IN ('DRAFT', 'APPROVED', 'BOUGHT', 'VERIFIED', 'WITHDRAWN', 'LAPSED')),
        CONSTRAINT ck_purchase_plan__first_of_month CHECK (EXTRACT(DAY FROM plan_month) = 1),
        CONSTRAINT ck_purchase_plan__window CHECK (window_end > window_start),
        CONSTRAINT ck_purchase_plan__days_held CHECK (days_held >= 0),
        CONSTRAINT ck_purchase_plan__unpriced_is_a_list CHECK (jsonb_typeof(unpriced) = 'array'),
        CONSTRAINT ck_purchase_plan__collected_after_true CHECK (collected_at >= as_of)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS purchase_plan_line (
        plan_id                UUID            NOT NULL REFERENCES purchase_plan(plan_id),
        line_no                INTEGER         NOT NULL,
        tenant_id              UUID            NOT NULL REFERENCES tenant(tenant_id),
        program                TEXT            NOT NULL,
        instance_family        TEXT,
        region_id              TEXT,
        tranche_month          DATE            NOT NULL,
        hourly_commitment      NUMERIC(20, 3)  NOT NULL,
        discount_percent       NUMERIC(7, 4)   NOT NULL,
        covers_hourly          NUMERIC(20, 4)  NOT NULL,
        monthly_saving         NUMERIC(20, 2)  NOT NULL,
        usage_floor_percent    NUMERIC(5, 1)   NOT NULL,
        upfront_cost           NUMERIC(20, 2)  NOT NULL,
        matched_commitment_id  TEXT,
        CONSTRAINT pk_purchase_plan_line PRIMARY KEY (plan_id, line_no),
        CONSTRAINT ck_purchase_plan_line__program CHECK (program IN ('Compute', 'EC2Instance')),
        CONSTRAINT ck_purchase_plan_line__placed_by_its_program CHECK (
            (program = 'EC2Instance' AND instance_family IS NOT NULL AND region_id IS NOT NULL)
            OR (program = 'Compute' AND instance_family IS NULL AND region_id IS NULL)),
        CONSTRAINT ck_purchase_plan_line__buys_something CHECK (hourly_commitment > 0),
        CONSTRAINT ck_purchase_plan_line__a_discount CHECK (
            discount_percent > 0 AND discount_percent < 100),
        CONSTRAINT ck_purchase_plan_line__first_of_month CHECK (
            EXTRACT(DAY FROM tranche_month) = 1)
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS purchase_plan_event (
        event_id     UUID         PRIMARY KEY,
        plan_id      UUID         NOT NULL REFERENCES purchase_plan(plan_id),
        tenant_id    UUID         NOT NULL REFERENCES tenant(tenant_id),
        from_status  TEXT,
        to_status    TEXT         NOT NULL,
        principal    TEXT         NOT NULL,
        at           TIMESTAMPTZ  NOT NULL,
        note         TEXT,
        CONSTRAINT ck_purchase_plan_event__a_transition_allowed CHECK (
            (from_status IS NULL AND to_status = 'DRAFT') OR {_ALLOWED})
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_purchase_plan_event__plan ON purchase_plan_event (plan_id, at)",
    f"""
    CREATE OR REPLACE FUNCTION purchase_plan_transition() RETURNS trigger
    LANGUAGE plpgsql AS $$
    DECLARE
        from_status TEXT;
        to_status TEXT;
    BEGIN
        IF TG_OP = 'INSERT' THEN
            IF NEW.status <> 'DRAFT' THEN
                RAISE EXCEPTION USING
                    ERRCODE = 'check_violation',
                    MESSAGE = 'a purchase plan begins as a draft';
            END IF;
            RETURN NEW;
        END IF;
        IF NEW.status IS NOT DISTINCT FROM OLD.status THEN
            RETURN NEW;
        END IF;
        from_status := OLD.status;
        to_status := NEW.status;
        IF NOT ({_ALLOWED}) THEN
            RAISE EXCEPTION USING
                ERRCODE = 'check_violation',
                MESSAGE = format('a purchase plan cannot go from %s to %s', OLD.status, NEW.status);
        END IF;
        RETURN NEW;
    END
    $$
    """,
    "DROP TRIGGER IF EXISTS tr_purchase_plan__transition ON purchase_plan",
    """
    CREATE TRIGGER tr_purchase_plan__transition
        BEFORE INSERT OR UPDATE OF status ON purchase_plan
        FOR EACH ROW EXECUTE FUNCTION purchase_plan_transition()
    """,
)


def _literal(text: str) -> str:
    """A SQL string literal, its apostrophes doubled."""
    return "'" + text.replace("'", "''") + "'"


def upgrade() -> None:
    for statement in _STATEMENTS:
        op.execute(statement)
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
    op.execute("DROP TRIGGER IF EXISTS tr_purchase_plan__transition ON purchase_plan")
    op.execute("DROP FUNCTION IF EXISTS purchase_plan_transition()")
    op.execute("DROP TABLE IF EXISTS purchase_plan_event")
    op.execute("DROP TABLE IF EXISTS purchase_plan_line")
    op.execute("DROP TABLE IF EXISTS purchase_plan")
