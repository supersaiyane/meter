"""What a plan is priced with: quotes, components and the catalog they come from. FEAT-095.

Shared by `plan_pricing`, which prices instances and volumes and runs the estimate, and
`plan_services`, which prices the managed services, TASK-P16-003 and TASK-P16-004. Every figure
is modelled: list price, on demand, 730 hours a month, in USD.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final, Protocol, TypeIs

#: The month a figure is for: 730 hours, the convention AWS's own calculator uses.
HOURS_PER_MONTH: Final = Decimal(730)
CURRENCY: Final = "USD"


@dataclass(frozen=True)
class Quote:
    """One price as the catalog holds it."""

    sku_price_id: str
    unit_price: Decimal
    unit: str
    version: str


class Catalogue(Protocol):
    """The catalog as a plan is priced from it. Each answer is a quote, or why there is none."""

    def instance_hour(self, region: str, instance_type: str) -> Quote | str:
        """EC2's comparable hourly price for a type: Linux, shared tenancy, on demand."""
        ...

    def volume_month(self, region: str, volume_type: str, term: str) -> Quote | str:
        """An EBS volume type's monthly price for one term: storage, iops or throughput."""
        ...

    def service_price(
        self, service: str, region: str, attributes: Mapping[str, str], term: str
    ) -> Quote | str:
        """A managed service's on demand price: the one row holding every attribute named, for a
        term, hours, storage, iops or throughput, read by the unit it is sold in."""
        ...


@dataclass(frozen=True)
class Component:
    """One priced part of a resource: what it is, how much a month, at what price."""

    what: str
    quantity: Decimal
    quote: Quote

    @property
    def monthly(self) -> Decimal:
        return self.quantity * self.quote.unit_price


@dataclass(frozen=True)
class Side:
    """A resource's monthly cost on one side of a change."""

    components: tuple[Component, ...]

    @property
    def monthly(self) -> Decimal:
        return sum((one.monthly for one in self.components), Decimal(0))


@dataclass(frozen=True)
class Values:
    """One side of a change as a pricer reads it: the values kept, and the names it lacks."""

    values: Mapping[str, Any]
    unknown: frozenset[str] = frozenset()
    withheld: frozenset[str] = frozenset()

    def absent(self, name: str) -> str | None:
        """Why a named value is missing, where it is unknown or withheld."""
        if name in self.withheld:
            return f"{name} is marked sensitive, so Meter does not keep it"
        if name in self.unknown:
            return f"{name} is known only after apply"
        return None


#: A side priced: its components and its notes. A pricer returns this, or the reason it cannot.
Priced = tuple[tuple[Component, ...], tuple[str, ...]]
Pricer = Callable[[Values, str, Catalogue], "Priced | str"]


def positive(value: Any) -> TypeIs[int | float]:
    """A count or a size Terraform gave: a number above nought, never a boolean."""
    return isinstance(value, int | float) and not isinstance(value, bool) and value > 0


def decimal_of(value: int | float) -> Decimal:
    """A quantity as a Decimal from its text, so a float carries no binary remainder."""
    return Decimal(str(value))


def hours(count: int | float = 1) -> Decimal:
    """The hours a month of `count` nodes running all of it."""
    return HOURS_PER_MONTH * decimal_of(count)
