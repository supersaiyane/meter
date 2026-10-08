"""The rules of a suggested owner, held by the database. TASK-P11-002, constraint 11.

Migration 0041. A tag names a team, a creator is never a team, nothing is blank, nothing was read
before it was true, and one resource has one row per source.
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
TABLE = "resource_owner"


def owner(tenant: UUID, **overrides: Any) -> dict[str, Any]:
    return {
        "owner_pk": uuid4(),
        "tenant_id": tenant,
        "ingest_run_id": uuid4(),
        "sub_account_id": "111111111111",
        "region_id": "eu-west-2",
        "resource_id": "i-0123",
        "source": "TAG",
        "owner": "platform",
        "owner_kind": "TEAM",
        "detail": "team",
        "as_of": AT,
        "collected_at": AT,
        **overrides,
    }


def test_each_source_is_kept_with_its_kind(engine: Engine, tenant_id: UUID) -> None:
    insert(engine, TABLE, owner(tenant_id))
    insert(engine, TABLE, owner(tenant_id, source="CATALOGUE", detail="checkout"))
    insert(
        engine,
        TABLE,
        owner(tenant_id, source="CREATOR", owner="dev.lead@fake.example", owner_kind="PERSON"),
    )
    insert(engine, TABLE, owner(tenant_id, resource_id="global-1", region_id=None))


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"source": "GUESS"}, "ck_resource_owner__source"),
        ({"owner_kind": "ROBOT"}, "ck_resource_owner__kind"),
        ({"owner_kind": "PERSON"}, "ck_resource_owner__tag_names_a_team"),
        ({"source": "CREATOR"}, "ck_resource_owner__creator_is_no_team"),
        ({"owner": " "}, "ck_resource_owner__named"),
        ({"detail": ""}, "ck_resource_owner__named"),
        ({"resource_id": ""}, "ck_resource_owner__named"),
        ({"collected_at": AT - timedelta(seconds=1)}, "ck_resource_owner__collected_after_true"),
    ],
)
def test_a_row_breaking_a_rule_is_refused(
    engine: Engine, tenant_id: UUID, overrides: dict[str, Any], constraint: str
) -> None:
    refused(engine, TABLE, owner(tenant_id, **overrides), constraint)


def test_a_resource_has_one_row_per_source(engine: Engine, tenant_id: UUID) -> None:
    insert(engine, TABLE, owner(tenant_id))
    refused(engine, TABLE, owner(tenant_id, owner="someone-else"), "uq_resource_owner__source")
