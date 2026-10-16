"""The invariants of a plan and its estimate, held by the database. TASK-P16-005, constraint 11.

A line with a reason carries no figure and no parts, and one without a reason carries a figure, so
a resource Meter could not price is never nought, constraint 5. A refusal says why, a change is the
after less the before, and a kept change is only one that changes what is billed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration

AT = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
#: Columns written as JSON text and cast, as the collectors write them.
JSON_COLUMNS = frozenset({"components", "before", "after"})


def insert(engine: Engine, table: str, values: dict[str, Any]) -> None:
    columns = ", ".join(values)
    marks = ", ".join(
        f"CAST(:{name} AS jsonb)" if name in JSON_COLUMNS else f":{name}" for name in values
    )
    with engine.begin() as connection:
        connection.execute(text(f"INSERT INTO {table} ({columns}) VALUES ({marks})"), values)


def refused(engine: Engine, table: str, values: dict[str, Any], constraint: str) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        insert(engine, table, values)


def a_plan(tenant: UUID, **overrides: Any) -> dict[str, Any]:
    return {
        "plan_id": uuid4(),
        "tenant_id": tenant,
        "repository": "acme/infra",
        "pull_request": 7,
        "head_sha": uuid4().hex[:10],
        "folder": "storage",
        "route": "test",
        "status": "RECEIVED",
        "format_version": "1.2",
        "received_at": AT,
        "as_of": AT,
        "collected_at": AT,
        **overrides,
    }


def an_estimate(plan: Any, tenant: UUID, **overrides: Any) -> dict[str, Any]:
    return {
        "plan_id": plan,
        "tenant_id": tenant,
        "monthly_before": Decimal(0),
        "monthly_after": Decimal("10"),
        "monthly_change": Decimal("10"),
        "currency": "USD",
        "priced_lines": 1,
        "unpriced_lines": 1,
        "priced_at": AT,
        "as_of": AT,
        "collected_at": AT,
        **overrides,
    }


def priced_plan(engine: Engine, tenant: UUID) -> UUID:
    plan = a_plan(tenant)
    insert(engine, "terraform_plan", plan)
    insert(engine, "plan_estimate", an_estimate(plan["plan_id"], tenant))
    return UUID(str(plan["plan_id"]))


def a_line(plan: UUID, tenant: UUID, **overrides: Any) -> dict[str, Any]:
    return {
        "plan_id": plan,
        "tenant_id": tenant,
        "address": f"aws_ebs_volume.v{uuid4().hex[:6]}",
        "resource_type": "aws_ebs_volume",
        "actions": ["create"],
        "monthly_after": Decimal("10"),
        **overrides,
    }


def test_a_priced_line_and_an_unpriced_one_are_admitted(engine: Engine, tenant_id: UUID) -> None:
    plan = priced_plan(engine, tenant_id)
    insert(engine, "plan_estimate_line", a_line(plan, tenant_id, components='[{"what": "gp3"}]'))
    unpriced = {"monthly_after": None, "reason": "aws_nat_gateway is billed by use"}
    insert(engine, "plan_estimate_line", a_line(plan, tenant_id, **unpriced))


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"reason": "not priced"}, "ck_plan_estimate_line__figure_or_reason"),
        ({"monthly_after": None}, "ck_plan_estimate_line__figure_or_reason"),
        ({"monthly_after": None, "reason": "  "}, "ck_plan_estimate_line__reason"),
        (
            {"monthly_after": None, "reason": "not priced", "components": '[{"what": "x"}]'},
            "ck_plan_estimate_line__unpriced_has_no_parts",
        ),
    ],
)
def test_a_line_that_would_show_a_figure_it_does_not_have_is_refused(
    engine: Engine, tenant_id: UUID, overrides: dict[str, Any], constraint: str
) -> None:
    plan = priced_plan(engine, tenant_id)
    refused(engine, "plan_estimate_line", a_line(plan, tenant_id, **overrides), constraint)


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"status": "REFUSED", "format_version": None}, "ck_terraform_plan__refusal_says_why"),
        ({"status": "PRICED", "format_version": None}, "ck_terraform_plan__read_has_a_format"),
        ({"status": "GUESSED"}, "ck_terraform_plan__status"),
        ({"folder": "../outside"}, "ck_terraform_plan__folder"),
        ({"head_sha": "NOT-A-SHA"}, "ck_terraform_plan__head"),
        ({"repository": "no slash"}, "ck_terraform_plan__repository"),
        ({"pull_request": 0}, "ck_terraform_plan__pull_request"),
    ],
)
def test_a_plan_that_breaks_a_rule_is_refused(
    engine: Engine, tenant_id: UUID, overrides: dict[str, Any], constraint: str
) -> None:
    refused(engine, "terraform_plan", a_plan(tenant_id, **overrides), constraint)


def test_an_estimate_whose_change_is_not_after_less_before_is_refused(
    engine: Engine, tenant_id: UUID
) -> None:
    plan = a_plan(tenant_id)
    insert(engine, "terraform_plan", plan)
    wrong = an_estimate(plan["plan_id"], tenant_id, monthly_before=Decimal("5"))
    refused(engine, "plan_estimate", wrong, "ck_plan_estimate__change")


@pytest.mark.parametrize("actions", [["read"], ["no-op"], []])
def test_a_kept_change_is_only_one_that_changes_what_is_billed(
    engine: Engine, tenant_id: UUID, actions: list[str]
) -> None:
    plan = a_plan(tenant_id)
    insert(engine, "terraform_plan", plan)
    change = {
        "plan_id": plan["plan_id"],
        "tenant_id": tenant_id,
        "address": "aws_instance.web",
        "resource_type": "aws_instance",
        "actions": actions,
    }
    refused(engine, "planned_change", change, "ck_planned_change__actions")
