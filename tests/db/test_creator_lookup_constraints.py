"""The rules of a creator lookup, held by the database. TASK-P11-004, constraint 11.

Migration 0042. A lookup found the creator or found the resource older than the history, and only
the second says where the history began; nothing is blank, nothing was read before it was true,
and a resource is asked about once.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine

from tests.db.test_price_catalog_constraints import insert, refused

pytestmark = pytest.mark.integration

AT = datetime(2026, 10, 8, 5, 0, tzinfo=UTC)
STARTS = AT - timedelta(days=90)
TABLE = "creator_lookup"


def lookup(tenant: UUID, **overrides: Any) -> dict[str, Any]:
    return {
        "lookup_pk": uuid4(),
        "tenant_id": tenant,
        "ingest_run_id": uuid4(),
        "sub_account_id": "111111111111",
        "region_id": "eu-west-2",
        "resource_id": "i-0123",
        "outcome": "FOUND",
        "history_starts": None,
        "as_of": AT,
        "collected_at": AT,
        **overrides,
    }


def test_each_outcome_is_kept(engine: Engine, tenant_id: UUID) -> None:
    insert(engine, TABLE, lookup(tenant_id))
    insert(
        engine,
        TABLE,
        lookup(tenant_id, resource_id="i-older", outcome="BEFORE_HISTORY", history_starts=STARTS),
    )


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"outcome": "GUESSED"}, "ck_creator_lookup__outcome"),
        ({"outcome": "BEFORE_HISTORY"}, "ck_creator_lookup__history_said"),
        ({"history_starts": STARTS}, "ck_creator_lookup__history_said"),
        ({"resource_id": " "}, "ck_creator_lookup__named"),
        ({"collected_at": AT - timedelta(seconds=1)}, "ck_creator_lookup__collected_after_true"),
    ],
)
def test_a_row_breaking_a_rule_is_refused(
    engine: Engine, tenant_id: UUID, overrides: dict[str, Any], constraint: str
) -> None:
    refused(engine, TABLE, lookup(tenant_id, **overrides), constraint)


def test_a_resource_is_asked_about_once(engine: Engine, tenant_id: UUID) -> None:
    insert(engine, TABLE, lookup(tenant_id))
    refused(
        engine,
        TABLE,
        lookup(tenant_id, outcome="BEFORE_HISTORY", history_starts=STARTS),
        "uq_creator_lookup__resource",
    )
