"""One row of cost, in FOCUS 1.1, with the Meter columns alongside it.

ADR-0002. The column names are the specification's, not ours. They are not
renamed to something more readable, because the entire value of adopting a
standard is that it is not ours to improve, and a rename is a mapping that
someone maintains forever.

`tests/core/test_domain.py::test_cost_record_matches_focus_columns` reads the
column list out of `docs/07-DATA-MODEL.md`, so this class and the table it is
stored in cannot drift apart in either direction.

Money is `Decimal` and never `float`. A float total over a month of line items
is wrong in the last places, and a cost report that does not reconcile with the
provider's invoice is a cost report nobody uses twice.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from types import MappingProxyType
from uuid import UUID

from finops_core.domain.fact import Fact


@dataclass(frozen=True, kw_only=True)
class CostRecord(Fact):
    """A FOCUS 1.1 charge row. Field names are the specification's."""

    # Meter columns, alongside the FOCUS namespace and never inside it.
    tenant_id: UUID
    ingest_run_id: UUID
    source_fingerprint: str

    # FOCUS 1.1
    billing_account_id: str
    sub_account_id: str | None
    billing_period_start: date
    billing_period_end: date
    charge_period_start: datetime
    charge_period_end: datetime
    provider_name: str
    publisher_name: str | None
    invoice_issuer_name: str | None
    service_name: str
    service_category: str | None
    resource_id: str | None
    resource_name: str | None
    region_id: str | None
    availability_zone: str | None
    charge_category: str
    charge_description: str | None
    sku_id: str | None
    pricing_quantity: Decimal | None
    consumed_quantity: Decimal | None
    consumed_unit: str | None
    billed_cost: Decimal
    effective_cost: Decimal
    list_cost: Decimal | None
    contracted_cost: Decimal | None
    commitment_discount_id: str | None
    commitment_discount_type: str | None
    commitment_discount_status: str | None
    tags: Mapping[str, str]

    def __post_init__(self) -> None:
        # Frozen stops the attribute being rebound. It does not stop the dict
        # behind it being edited, and a shared tag dictionary quietly mutated by
        # one caller is the kind of defect that only shows up in aggregate.
        object.__setattr__(self, "tags", MappingProxyType(dict(self.tags)))
