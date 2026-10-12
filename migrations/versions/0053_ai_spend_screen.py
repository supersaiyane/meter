"""The AI spend screen admitted as a saved view's screen.

Revision ID: 0053_ai_spend_screen
Revises: 0052_gpu_utilization_daily
Create Date: 2026-10-13

TASK-P13-008, FEAT-085 and FEAT-068. A saved view names a screen the navigation knows, and
0045's constraint holds the list as it stood on 2026-10-11. The navigation gains
`/analyze/ai`, so the constraint is widened to the list below, a copy of
`finops_api.screens.SCREEN_PATHS` on 2026-10-13 rather than an import, because a migration
records the schema on the day it ran. `tests/api/test_saved_views.py` fails when the
constraint and the module disagree.

Backward compatible, constraint 12: the old code never writes the new path, and the widened
check admits every row the narrower one did. The downgrade restores 0045's list, and refuses
while a saved view names the screen rather than deleting a person's view to make a schema
change succeed.
"""

from __future__ import annotations

from alembic import op

revision = "0053_ai_spend_screen"
down_revision = "0052_gpu_utilization_daily"
branch_labels = None
depends_on = None

NEW = "/analyze/ai"

#: The screens and tabs the navigation knew on 2026-10-13. A copy, see the docstring.
_SCREENS = (
    "/",
    "/analyze/explorer",
    "/analyze/allocation",
    "/analyze/anomalies",
    "/analyze/kubernetes-cost",
    "/analyze/kubernetes-rightsizing",
    "/analyze/clusters",
    "/analyze/ai",
    "/plan/budgets",
    "/plan/forecasts",
    "/plan/score",
    "/plan/unit-economics",
    "/optimize",
    "/optimize/commitments",
    "/optimize/savings",
    "/optimize/ledger",
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
    "/report/reconciliation",
    "/assist",
    "/assist/digests",
    "/platform/freshness",
    "/platform/ingest",
    "/platform/cost",
    "/platform/flags",
)

_BEFORE = tuple(path for path in _SCREENS if path != NEW)


def _check(paths: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{path}'" for path in paths)
    return (
        "ALTER TABLE saved_view ADD CONSTRAINT ck_saved_view__screen "
        f"CHECK (screen_path IN ({quoted}))"
    )


_UP = (
    "ALTER TABLE saved_view DROP CONSTRAINT IF EXISTS ck_saved_view__screen",
    _check(_SCREENS),
)

_DOWN = (
    f"""
    DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM saved_view WHERE screen_path = '{NEW}') THEN
            RAISE EXCEPTION
                'a saved view still names {NEW}. Remove it before downgrading: this '
                'migration will not delete a person''s view to make a schema change succeed.';
        END IF;
    END $$
    """,
    "ALTER TABLE saved_view DROP CONSTRAINT IF EXISTS ck_saved_view__screen",
    _check(_BEFORE),
)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWN:
        op.execute(statement)
