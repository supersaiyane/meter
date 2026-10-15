"""Every screen the web navigation knows, by path. FEAT-068, TASK-P8-010.

A saved view names a screen, and the P8 spec's data model asks that the screen be one the
navigation knows, so a view can never point at a page that does not exist. The navigation lives
in `finops-web/src/shell/sections.ts`; this is its list of paths, the screens and the tabs a
screen merged into, and `tests/api/test_screens.py` fails the moment the two disagree.

Migration 0028 copies this list into the `saved_view` table's constraint, because a migration is
a record of the schema on the day it ran and must not change when this module does. A screen
added to the navigation therefore needs three edits in one change: `sections.ts`, this list and
a migration that widens the constraint, and the tests name whichever is missing.
"""

from __future__ import annotations

from typing import Final

#: In the navigation's order, so the constraint built from it reads the way the menu does and is
#: the same text on every run, which a set's iteration order is not.
SCREEN_PATHS: Final[tuple[str, ...]] = (
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
    "/platform/fixes",
    "/platform/flags",
)
