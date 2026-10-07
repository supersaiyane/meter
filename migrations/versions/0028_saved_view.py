"""Saved views: a person's named screen and query, private or shared with the tenant.

Revision ID: 0028_saved_view
Revises: 0027_commitment_day
Create Date: 2026-10-07

TASK-P8-010 and FEAT-068, P8 spec sections 5.6 and 6. A saved view is configuration and never
data: it holds a screen and the query string that screen reads, and nothing it rendered, so
opening one renders it in the opener's scope and sharing a view shares a question, not an
answer.

**Every invariant in the spec is a constraint.** The screen is one the navigation knows, the
name is not blank, the query is a JSON object, and the visibility is PRIVATE or SHARED. The
screen list is copied here from `finops_api.screens` rather than imported, because a migration
records the schema on the day it ran; `tests/api/test_screens.py` fails when the two disagree,
and a screen added later widens this constraint in a migration of its own.

Backward compatible, constraint 12: a new table no earlier release reads or writes, and the
downgrade drops it.
"""

from __future__ import annotations

from alembic import op

revision = "0028_saved_view"
down_revision = "0027_commitment_day"
branch_labels = None
depends_on = None

#: The screens and tabs the navigation knew on 2026-10-07. A copy, see the docstring.
_SCREENS = (
    "/",
    "/analyze/explorer",
    "/analyze/allocation",
    "/analyze/anomalies",
    "/analyze/kubernetes-cost",
    "/analyze/kubernetes-rightsizing",
    "/analyze/clusters",
    "/plan/budgets",
    "/plan/forecasts",
    "/plan/score",
    "/plan/unit-economics",
    "/optimize",
    "/optimize/commitments",
    "/optimize/savings",
    "/govern/query-cost",
    "/govern/query-cost/surfaces",
    "/govern/query-cost/adhoc",
    "/govern/quotas",
    "/govern/policies",
    "/inventory/accounts",
    "/inventory/accounts/organization",
    "/inventory/resources",
    "/inventory/topology",
    "/inventory/topology/geography",
    "/report/library",
    "/report/scheduled",
    "/report/exports",
    "/assist",
    "/assist/digests",
    "/platform/freshness",
    "/platform/ingest",
    "/platform/cost",
    "/platform/flags",
)

_IN_SCREENS = ", ".join(f"'{path}'" for path in _SCREENS)

_UP = (
    """
    CREATE TABLE IF NOT EXISTS saved_view (
        view_id      UUID         PRIMARY KEY,
        tenant_id    UUID         NOT NULL REFERENCES tenant(tenant_id),
        owner_id     TEXT         NOT NULL,
        name         TEXT         NOT NULL,
        screen_path  TEXT         NOT NULL,
        query        JSONB        NOT NULL,
        visibility   TEXT         NOT NULL,
        created_at   TIMESTAMPTZ  NOT NULL,
        updated_at   TIMESTAMPTZ  NOT NULL
    )
    """,
    """
    ALTER TABLE saved_view DROP CONSTRAINT IF EXISTS ck_saved_view__visibility
    """,
    """
    ALTER TABLE saved_view
        ADD CONSTRAINT ck_saved_view__visibility CHECK (visibility IN ('PRIVATE', 'SHARED'))
    """,
    """
    ALTER TABLE saved_view DROP CONSTRAINT IF EXISTS ck_saved_view__named
    """,
    """
    ALTER TABLE saved_view
        ADD CONSTRAINT ck_saved_view__named
        CHECK (length(trim(owner_id)) > 0 AND length(trim(name)) > 0 AND length(name) <= 120)
    """,
    """
    ALTER TABLE saved_view DROP CONSTRAINT IF EXISTS ck_saved_view__screen
    """,
    f"""
    ALTER TABLE saved_view
        ADD CONSTRAINT ck_saved_view__screen CHECK (screen_path IN ({_IN_SCREENS}))
    """,
    """
    ALTER TABLE saved_view DROP CONSTRAINT IF EXISTS ck_saved_view__query
    """,
    """
    ALTER TABLE saved_view
        ADD CONSTRAINT ck_saved_view__query CHECK (jsonb_typeof(query) = 'object')
    """,
    """
    ALTER TABLE saved_view DROP CONSTRAINT IF EXISTS ck_saved_view__times
    """,
    """
    ALTER TABLE saved_view
        ADD CONSTRAINT ck_saved_view__times CHECK (updated_at >= created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_saved_view__owner
        ON saved_view (tenant_id, owner_id, updated_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_saved_view__shared
        ON saved_view (tenant_id, updated_at) WHERE visibility = 'SHARED'
    """,
)


_DOWN = ("DROP TABLE IF EXISTS saved_view",)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWN:
        op.execute(statement)
