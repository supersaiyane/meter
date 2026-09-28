"""Every quota, including the ones nothing can measure.

Revision ID: 0020_quotas
Revises: 0019_sizing_refusal
Create Date: 2026-09-28

TASK-P5-002. The plan called this file `0012_quotas.py` when it was written; 0012
through 0019 were taken in the meantime, so it is 0020.

**The biconditional is the whole sub project in one CHECK.** `used_value IS NULL` if
and only if `usage_source = 'NONE'`. It makes it impossible to record a usage figure
without naming where it came from, and impossible to name a source while recording no
usage. The first matters because a figure with no provenance cannot be audited a year
later and renders identically to one that was measured. The second matters because a
source with no figure would put the quota in the measurable list with nothing to show.

`finops_core.domain.quota` refuses both as well, and the duplication is deliberate:
constraint 11 says application code is not what should stop a bad row, and the entity
is what makes the failure arrive at the line that caused it rather than at the commit.
Written here before TASK-P5-004 writes a collector that could violate it, which is the
plan's first P5 rule.

**`limit_value` is nullable and that is not the same absence.** A quota whose ceiling
AWS does not publish still has to produce a row, because TASK-P5-003 has to write one
for every quota Service Quotas returns. Zero is a real and different value meaning the
thing is switched off here, which is why the check is at or above zero rather than
above it.

**`unmeasurable_reason` exists only where nothing measured it, and is required there.**
A quota in the unmeasurable list with a blank reason is the screen TASK-P5-006 forbids,
and it teaches a reader that the explanations there are empty so they stop reading the
ones that are not. Same argument as `ck_sizing_refusal__reason_is_a_sentence` in 0019,
and the check is a length rather than a NOT NULL because an empty string satisfies
NOT NULL.

**`submitted_by_meter` is a column that is always false.** It is spec section 6 written
into the schema rather than into a comment: Meter drafts a quota increase and never
submits one, constraint 6, and the check refuses any other value. If that decision is
ever reversed it will be reversed by a migration somebody has to write and defend,
which is the point. The IAM permission is absent too, and TASK-P5-007 adds the test
that names the API.

**Nullable `region_id` needs NULLS NOT DISTINCT.** A global quota, IAM roles per
account and the like, is counted once for the whole account rather than once per
region. Under the default NULLS DISTINCT every collection would insert another copy of
it, because two NULLs never conflict, and the screen would show one limit five times.
PostgreSQL 15 added the clause and the deployed version is 16.
"""

from __future__ import annotations

from alembic import op

revision = "0020_quotas"
down_revision = "0019_sizing_refusal"
branch_labels = None
depends_on = None

_UP = (
    """
    CREATE TABLE IF NOT EXISTS quota_usage (
        quota_pk UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenant(tenant_id),
        ingest_run_id UUID NOT NULL,
        sub_account_id TEXT NOT NULL,
        region_id TEXT,
        service_code TEXT NOT NULL,
        quota_code TEXT NOT NULL,
        quota_name TEXT NOT NULL,
        limit_value NUMERIC(20, 10),
        used_value NUMERIC(20, 10),
        usage_source TEXT NOT NULL,
        unmeasurable_reason TEXT,
        is_adjustable BOOLEAN NOT NULL,
        as_of TIMESTAMPTZ NOT NULL,
        collected_at TIMESTAMPTZ NOT NULL
    )
    """,
    # One current row per quota per slice. A global quota carries no region, and without
    # NULLS NOT DISTINCT every run would insert another copy of it.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_quota_usage__identity
        ON quota_usage (tenant_id, sub_account_id, region_id, service_code, quota_code)
        NULLS NOT DISTINCT
    """,
    # The four the domain allows, and NONE is the common case rather than the error path.
    """
    ALTER TABLE quota_usage
        ADD CONSTRAINT ck_quota_usage__usage_source
        CHECK (usage_source IN ('AWS_USAGE_METRIC', 'TRUSTED_ADVISOR', 'SERVICE_API', 'NONE'))
    """,
    # The constraint this sub project exists for. Both directions, one expression.
    """
    ALTER TABLE quota_usage
        ADD CONSTRAINT ck_quota_usage__source_iff_usage
        CHECK ((used_value IS NULL) = (usage_source = 'NONE'))
    """,
    # A quota is the ceiling, so a usage above it is a misread rather than an estate in
    # trouble, and it would render as headroom below zero and rank above every real
    # problem. Only where both are present: nothing is known about an absent ceiling.
    """
    ALTER TABLE quota_usage
        ADD CONSTRAINT ck_quota_usage__used_within_limit
        CHECK (
            limit_value IS NULL
            OR used_value IS NULL
            OR used_value <= limit_value
        )
    """,
    # Zero is a real limit and means the thing is switched off here. Negative is a misread.
    """
    ALTER TABLE quota_usage
        ADD CONSTRAINT ck_quota_usage__limit_not_negative
        CHECK (limit_value IS NULL OR limit_value >= 0)
    """,
    # A reason where nothing measured it, and no reason where something did. The first
    # half is the screen's requirement; the second stops a stale sentence surviving the
    # day a quota starts publishing usage.
    """
    ALTER TABLE quota_usage
        ADD CONSTRAINT ck_quota_usage__reason_iff_unmeasurable
        CHECK (
            (usage_source = 'NONE') = (length(trim(coalesce(unmeasurable_reason, ''))) >= 12)
        )
    """,
    # The read is every quota for an account, which is the shape the guard and the screen
    # both ask for.
    """
    CREATE INDEX IF NOT EXISTS ix_quota_usage__account
        ON quota_usage (tenant_id, sub_account_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS quota_request (
        request_pk UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenant(tenant_id),
        ingest_run_id UUID NOT NULL,
        request_id TEXT NOT NULL,
        sub_account_id TEXT NOT NULL,
        region_id TEXT,
        service_code TEXT NOT NULL,
        quota_code TEXT NOT NULL,
        -- AWS returns the name on the request, and a tracking list of bare quota codes is
        -- unreadable: `L-1216C47A` tells a person nothing about what they asked for. Stored
        -- rather than joined to `quota_usage`, because a request survives for a quota that
        -- was never collected, or that stopped being returned, and a join would lose exactly
        -- the rows somebody is chasing.
        quota_name TEXT NOT NULL,
        desired_value NUMERIC(20, 10) NOT NULL,
        status TEXT NOT NULL,
        requested_at TIMESTAMPTZ NOT NULL,
        last_updated_at TIMESTAMPTZ NOT NULL,
        submitted_by_meter BOOLEAN NOT NULL DEFAULT FALSE,
        as_of TIMESTAMPTZ NOT NULL,
        collected_at TIMESTAMPTZ NOT NULL
    )
    """,
    # AWS's own request id, which is what lets a re read update rather than accumulate.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_quota_request__request_id
        ON quota_request (tenant_id, request_id)
    """,
    # AWS's own vocabulary, not ours to improve. DENIED is in it because a product is
    # tempted to hide that one, and TASK-P5-008 asks for it by name.
    """
    ALTER TABLE quota_request
        ADD CONSTRAINT ck_quota_request__status
        CHECK (status IN ('PENDING', 'CASE_OPENED', 'APPROVED', 'DENIED', 'CASE_CLOSED', 'NOT_APPROVED', 'INVALID_REQUEST'))
    """,
    # Asking for nothing is not a request, and asking for a negative is a misread.
    """
    ALTER TABLE quota_request
        ADD CONSTRAINT ck_quota_request__desired_is_positive
        CHECK (desired_value > 0)
    """,
    """
    ALTER TABLE quota_request
        ADD CONSTRAINT ck_quota_request__updated_after_requested
        CHECK (last_updated_at >= requested_at)
    """,
    # Spec section 6, in the schema rather than in a comment. Reversing this decision
    # takes a migration somebody has to write and defend.
    """
    ALTER TABLE quota_request
        ADD CONSTRAINT ck_quota_request__meter_never_submits
        CHECK (submitted_by_meter = FALSE)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_quota_request__account
        ON quota_request (tenant_id, sub_account_id)
    """,
    # Every status a request has been in, because the current one cannot say when it was
    # approved, and FEAT-034 exists for the increase nobody checked on.
    """
    CREATE TABLE IF NOT EXISTS quota_request_history (
        history_pk UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenant(tenant_id),
        request_id TEXT NOT NULL,
        status TEXT NOT NULL,
        changed_at TIMESTAMPTZ NOT NULL
    )
    """,
    # One row per status per request. A re read of the same history updates rather than
    # doubling, so a request read twice does not appear to have been approved twice.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_quota_request_history__status
        ON quota_request_history (tenant_id, request_id, status)
    """,
    """
    ALTER TABLE quota_request_history
        ADD CONSTRAINT ck_quota_request_history__status
        CHECK (status IN ('PENDING', 'CASE_OPENED', 'APPROVED', 'DENIED', 'CASE_CLOSED', 'NOT_APPROVED', 'INVALID_REQUEST'))
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_quota_request_history__request
        ON quota_request_history (tenant_id, request_id, changed_at)
    """,
)

_DOWN = (
    "DROP TABLE IF EXISTS quota_request_history",
    "DROP TABLE IF EXISTS quota_request",
    "DROP TABLE IF EXISTS quota_usage",
)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWN:
        op.execute(statement)
