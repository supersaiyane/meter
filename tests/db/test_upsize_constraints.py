"""An Upsize's added cost, held by the database. TASK-P9-008, migration 0039, constraint 11.

An Upsize states what it adds to the bill and saves nothing, so no total of savings can fall by
it; nothing else carries an added cost.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from tests.db.test_price_catalog_constraints import AT, REGION

pytestmark = pytest.mark.integration


def write(engine: Engine, tenant: UUID, **overrides: Any) -> None:
    fields: dict[str, Any] = {
        "id": uuid4(),
        "t": tenant,
        "ref": f"meter:i-{uuid4().hex[:8]}:UPSIZE_INSTANCE",
        "class": "UPSIZE_INSTANCE",
        "saving": Decimal(0),
        "added": Decimal("181.04"),
        **overrides,
    }
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO recommendation (recommendation_id, tenant_id, sub_account_id, "
                "source, source_reference, waste_class, resource_id, region_id, "
                "estimated_monthly_saving, confidence, severity, observation_days, lifecycle, "
                "rationale, as_of, collected_at, added_monthly_cost) "
                "VALUES (:id, :t, '111122223333', 'METER', :ref, :class, 'i-0001', :region, "
                ":saving, 'HIGH', 'HIGH', 30, 'OPEN', 'because', :at, :at, :added)"
            ),
            {**fields, "region": REGION, "at": AT},
        )


def test_an_upsize_with_its_added_cost_is_admitted(engine: Engine, tenant_id: UUID) -> None:
    write(engine, tenant_id)


@pytest.mark.parametrize(
    "overrides",
    [
        {"added": None},
        {"added": Decimal(0)},
        {"saving": Decimal("5")},
        {"class": "RIGHTSIZE_INSTANCE", "saving": Decimal("5")},
    ],
)
def test_an_added_cost_out_of_place_is_refused(
    engine: Engine, tenant_id: UUID, overrides: dict[str, Any]
) -> None:
    with pytest.raises(IntegrityError, match="ck_recommendation__upsize_costs"):
        write(engine, tenant_id, **overrides)


def test_anything_else_without_an_added_cost_is_admitted(engine: Engine, tenant_id: UUID) -> None:
    write(engine, tenant_id, **{"class": "RIGHTSIZE_INSTANCE", "saving": Decimal(5), "added": None})
