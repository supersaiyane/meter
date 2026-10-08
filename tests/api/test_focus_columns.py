"""Every column FOCUS 1.4 makes Mandatory for Cost and Usage is on Meter's row. TASK-P10-002.

P10 spec section 12 item 1, ADR-0034. The list below is FOCUS 1.4's, read from the
specification's Cost and Usage dataset on 2026-10-07: 21 Mandatory columns, here in Meter's snake
case. The record and the table are both held, because a column on one and not the other is a
value that is collected and dropped, or stored and never filled. The spec's own section 4 is read
as well, so the document that names the gap and the code that closes it cannot disagree.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

from finops_api.db import models
from finops_core.domain.cost import CostRecord

SPEC = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "specs"
    / "2026-10-07-p10-proven-numbers-design.md"
)

FOCUS_1_4_MANDATORY = (
    "billed_cost",
    "billing_account_id",
    "billing_account_name",
    "billing_currency",
    "billing_period_end",
    "billing_period_start",
    "charge_category",
    "charge_class",
    "charge_description",
    "charge_period_end",
    "charge_period_start",
    "contracted_cost",
    "effective_cost",
    "host_provider_name",
    "invoice_issuer_name",
    "list_cost",
    "pricing_quantity",
    "pricing_unit",
    "service_category",
    "service_name",
    "service_provider_name",
)

#: The two that tie a row to its invoice, spec section 4.
INVOICE_COLUMNS = ("invoice_id", "invoice_detail_id")


def snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def test_focus_1_4_has_twenty_one_mandatory_columns() -> None:
    assert len(set(FOCUS_1_4_MANDATORY)) == 21


def test_every_mandatory_and_invoice_column_is_on_the_record() -> None:
    fields = {field.name for field in dataclasses.fields(CostRecord)}
    assert [name for name in (*FOCUS_1_4_MANDATORY, *INVOICE_COLUMNS) if name not in fields] == []


def test_every_mandatory_and_invoice_column_is_in_the_table() -> None:
    columns = set(models.cost_focus_daily.c.keys())
    assert [name for name in (*FOCUS_1_4_MANDATORY, *INVOICE_COLUMNS) if name not in columns] == []


def test_the_columns_the_spec_names_as_missing_are_among_those_now_held() -> None:
    row = next(
        line for line in SPEC.read_text().splitlines() if line.startswith("| Mandatory columns |")
    )
    named = [snake(name) for name in re.findall(r"`([A-Za-z]+)`", row)]
    assert len(named) == 6
    assert set(named) <= set(FOCUS_1_4_MANDATORY)
