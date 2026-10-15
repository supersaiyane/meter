"""A fix a person asked for, its pull request, and every step. FEAT-092, TASK-P15-004.

Revision ID: 0060_fix_pull_request
Revises: 0059_code_host
Create Date: 2026-10-15

P15 spec sections 5.5, 6 and 7. `fix_pull_request` is one row per recommendation asked to be fixed:
its status, the repository, branch, number and link of its pull request once opened, who asked and
when, who merged it, and why there is none where there is none. A partial unique index allows one
live fix per recommendation, so asking twice while one is requested or open is refused by the
database as well as by the route, constraint 11. Each status's facts are held by a check: an open
fix names its pull request, and one not authored or failed says why.

`fix_pull_request_event` is every step, append only, with its principal: a person, Meter, or the
code host's login of whoever merged or closed it. Both carry the recommendation's account, so the
guard scopes them as the recommendation is.

The `fix_pull_requests` collector's cadence, every ten minutes, is installed for every tenant that
exists, as `DEFAULT_SCHEDULE` installs it for a new one. Backward compatible, constraint 12: new
tables nothing old reads, and a schedule row nothing old runs. The downgrade removes them.
"""

from __future__ import annotations

from alembic import op

revision = "0060_fix_pull_request"
down_revision = "0059_code_host"
branch_labels = None
depends_on = None

_BY = "migration 0060_fix_pull_request"

_SCHEDULE = {
    "fix_pull_requests": (
        600,
        (
            "Opens each fix a person asked for, follows each open pull request and, under the "
            "tenant's merge policy, merges, P15 spec section 7. Every ten minutes, so a person who "
            "asks sees the pull request within ten minutes and each later step within the next "
            "run. GitHub's API is free within its rate limit and the worker's NAT carries "
            "kilobytes: modelled at 0.00 USD a run. ADR-0012 and constraint 9."
        ),
        "0.00",
    ),
}

_FIX = """
CREATE TABLE IF NOT EXISTS fix_pull_request (
    fix_id             UUID        NOT NULL,
    tenant_id          UUID        NOT NULL REFERENCES tenant(tenant_id),
    recommendation_id  UUID        NOT NULL REFERENCES recommendation(recommendation_id),
    sub_account_id     TEXT        NOT NULL,
    status             TEXT        NOT NULL,
    repository         TEXT,
    branch             TEXT,
    number             INTEGER,
    url                TEXT,
    note               TEXT,
    requested_by       TEXT        NOT NULL,
    requested_at       TIMESTAMPTZ NOT NULL,
    merged_by          TEXT,
    reason             TEXT,
    failure_cause      TEXT,
    as_of              TIMESTAMPTZ NOT NULL,
    collected_at       TIMESTAMPTZ NOT NULL,
    CONSTRAINT pk_fix_pull_request PRIMARY KEY (fix_id),
    CONSTRAINT ck_fix_pull_request__status CHECK (
        status IN ('REQUESTED', 'OPEN', 'MERGED', 'CLOSED', 'NOT_AUTHORED', 'FAILED')),
    CONSTRAINT ck_fix_pull_request__opened_names_it CHECK (
        status NOT IN ('OPEN', 'MERGED', 'CLOSED')
        OR (repository IS NOT NULL AND branch IS NOT NULL AND number IS NOT NULL
            AND url IS NOT NULL)),
    CONSTRAINT ck_fix_pull_request__none_says_why CHECK (
        status NOT IN ('NOT_AUTHORED', 'FAILED') OR length(trim(coalesce(reason, ''))) > 0),
    CONSTRAINT ck_fix_pull_request__failure_typed CHECK (
        (status = 'FAILED') = (failure_cause IS NOT NULL)),
    CONSTRAINT ck_fix_pull_request__cause CHECK (failure_cause IS NULL OR failure_cause IN (
        'AccessDenied', 'Throttled', 'NotOptedIn', 'NoData', 'Unreachable', 'Misconfigured',
        'SchemaDrift')),
    CONSTRAINT ck_fix_pull_request__collected_after_true CHECK (collected_at >= as_of)
)
"""

_LIVE = (
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_fix_pull_request__live "
    "ON fix_pull_request (tenant_id, recommendation_id) WHERE status IN ('REQUESTED', 'OPEN')"
)

_EVENT = """
CREATE TABLE IF NOT EXISTS fix_pull_request_event (
    event_id        UUID        NOT NULL,
    fix_id          UUID        NOT NULL REFERENCES fix_pull_request(fix_id),
    tenant_id       UUID        NOT NULL REFERENCES tenant(tenant_id),
    sub_account_id  TEXT        NOT NULL,
    from_status     TEXT,
    to_status       TEXT        NOT NULL,
    principal       TEXT        NOT NULL,
    note            TEXT,
    at              TIMESTAMPTZ NOT NULL,
    CONSTRAINT pk_fix_pull_request_event PRIMARY KEY (event_id),
    CONSTRAINT ck_fix_pull_request_event__principal CHECK (length(trim(principal)) > 0)
)
"""


def _literal(text: str) -> str:
    """A SQL string literal, its apostrophes doubled."""
    return "'" + text.replace("'", "''") + "'"


def upgrade() -> None:
    op.execute(_FIX)
    op.execute(_LIVE)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fix_pull_request__status "
        "ON fix_pull_request (tenant_id, status)"
    )
    op.execute(_EVENT)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fix_pull_request_event__fix "
        "ON fix_pull_request_event (fix_id, at)"
    )
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
    op.execute("DROP TABLE IF EXISTS fix_pull_request_event")
    op.execute("DROP TABLE IF EXISTS fix_pull_request")
