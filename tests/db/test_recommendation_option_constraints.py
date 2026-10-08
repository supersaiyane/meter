"""A ranked option's rules, held by the database. TASK-P9-006, migration 0038, constraint 11.

An option is priced from a recorded price, with its version and hourly price beside it, or it
says why not; never both and never neither. The helpers are the price catalog's, so a price
here is one the catalog's own constraints admit.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine

from tests.db.test_price_catalog_constraints import (
    AT,
    PUBLISHED,
    REGION,
    VERSION,
    a_version,
    insert,
    price,
    recommendation,
    refused,
)

pytestmark = pytest.mark.integration


def option(tenant: UUID, recommendation_id: UUID, **overrides: Any) -> dict[str, Any]:
    return {
        "option_pk": uuid4(),
        "tenant_id": tenant,
        "recommendation_id": recommendation_id,
        "region": REGION,
        "rank": 1,
        "instance_type": "m6g.large",
        "performance_risk": Decimal("1.5"),
        "unpriced_reason": "the catalog holds no Linux on demand price for m6g.large",
        "as_of": PUBLISHED,
        "collected_at": AT,
        **overrides,
    }


def priced_option(
    engine: Engine, tenant: UUID, recommendation_id: UUID, **overrides: Any
) -> dict[str, Any]:
    a_version(engine, tenant)
    target = price(tenant)
    insert(engine, "price", target)
    fields: dict[str, Any] = {
        "instance_type": "m5.xlarge",
        "sku_price_id": target["sku_price_id"],
        "price_version": VERSION,
        "hourly_price": target["recurring_unit_price"],
        "unpriced_reason": None,
        **overrides,
    }
    return option(tenant, recommendation_id, **fields)


def test_a_priced_option_and_one_saying_why_it_is_not_are_admitted(
    engine: Engine, tenant_id: UUID
) -> None:
    held = recommendation(engine, tenant_id)
    insert(engine, "recommendation_option", priced_option(engine, tenant_id, held))
    insert(
        engine,
        "recommendation_option",
        option(tenant_id, held, rank=2, provider_monthly_saving=Decimal("-40")),
    )


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"rank": 0}, "ck_recommendation_option__ranked"),
        ({"instance_type": ""}, "ck_recommendation_option__named"),
        ({"performance_risk": Decimal("4.5")}, "ck_recommendation_option__risk"),
        ({"unpriced_reason": None}, "ck_recommendation_option__priced_or_says_why"),
        ({"unpriced_reason": ""}, "ck_recommendation_option__priced_or_says_why"),
        ({"price_version": VERSION}, "ck_recommendation_option__priced_or_says_why"),
        ({"collected_at": PUBLISHED.replace(year=2025)}, "collected_after_true"),
    ],
)
def test_an_option_that_breaks_a_rule_is_refused(
    engine: Engine, tenant_id: UUID, overrides: dict[str, Any], constraint: str
) -> None:
    held = recommendation(engine, tenant_id)
    refused(engine, "recommendation_option", option(tenant_id, held, **overrides), constraint)


def test_a_price_and_a_reason_together_are_refused(engine: Engine, tenant_id: UUID) -> None:
    held = recommendation(engine, tenant_id)
    both = priced_option(engine, tenant_id, held, unpriced_reason="and yet")
    refused(engine, "recommendation_option", both, "priced_or_says_why")


def test_a_price_of_nought_is_refused(engine: Engine, tenant_id: UUID) -> None:
    held = recommendation(engine, tenant_id)
    nought = priced_option(engine, tenant_id, held, hourly_price=Decimal(0))
    refused(engine, "recommendation_option", nought, "ck_recommendation_option__price_positive")


def test_a_price_the_catalog_never_recorded_is_refused(engine: Engine, tenant_id: UUID) -> None:
    held = recommendation(engine, tenant_id)
    invented = option(
        tenant_id,
        held,
        sku_price_id="NOTINTHECATALOG.JRTCKXETXF",
        price_version=VERSION,
        hourly_price=Decimal("0.19"),
        unpriced_reason=None,
    )
    refused(engine, "recommendation_option", invented, "fk_recommendation_option__price")


def test_two_options_of_one_recommendation_never_share_a_rank(
    engine: Engine, tenant_id: UUID
) -> None:
    held = recommendation(engine, tenant_id)
    insert(engine, "recommendation_option", option(tenant_id, held))
    refused(
        engine,
        "recommendation_option",
        option(tenant_id, held, instance_type="m5.large"),
        "uq_recommendation_option__rank",
    )
