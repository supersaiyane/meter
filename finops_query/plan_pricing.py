"""A reduced plan priced from the catalog. TASK-P16-003, FEAT-095, spec sections 5.3 and 5.4.

Each change is priced at list, on demand, 730 hours a month, in USD, at the newest catalog version
for its service and Region, which the `Catalogue` it is given reads. Every figure is modelled. A
line rests on a principal part, an instance's hours or a volume's storage; when that cannot be
priced the line carries the reason and no figure, never zero, constraint 5. A secondary part that
cannot be priced, a block device whose size Terraform knows only after apply, is named in the
line's notes and left out, so the figure understates and says so.

Each component keeps the price identifier, the unit price and the version it used, as figures, so
the catalog pruning a superseded price never changes a past estimate.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final, Protocol

from finops_query.plan_reading import PlannedChange, ReducedPlan

#: The month a figure is for: 730 hours, the convention AWS's own calculator uses.
HOURS_PER_MONTH: Final = Decimal(730)
CURRENCY: Final = "USD"
#: What gp3 includes in its storage price, above which IOPS and throughput are priced.
GP3_IOPS: Final = 3000
GP3_MIBPS: Final = 125
#: The EBS volume types the catalog prices storage for.
VOLUME_TYPES: Final = frozenset({"gp2", "gp3", "io1", "io2", "st1", "sc1", "standard"})

LINUX: Final = (
    "priced as Linux: the image's platform is not in the plan, and a Windows or licensed image "
    "costs more"
)
NO_REGION: Final = (
    "no Region could be read for it: neither its own region, its availability zone, nor its "
    "provider's configuration gives one the plan carries"
)
#: Types billed by what they serve, which a plan does not say.
USAGE_BASED: Final = frozenset(
    {
        "aws_s3_bucket",
        "aws_lambda_function",
        "aws_nat_gateway",
        "aws_cloudwatch_log_group",
        "aws_dynamodb_table",
        "aws_sqs_queue",
        "aws_sns_topic",
        "aws_lb",
        "aws_alb",
        "aws_api_gateway_rest_api",
        "aws_apigatewayv2_api",
        "aws_cloudfront_distribution",
        "aws_kinesis_stream",
    }
)


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
class EstimateLine:
    """One resource change priced, or the reason it is not."""

    address: str
    resource_type: str
    actions: tuple[str, ...]
    region: str | None
    before: Side | None = None
    after: Side | None = None
    #: Why the line is not priced. A line with a reason carries no figure.
    reason: str | None = None
    #: The assumptions, and each part left out with its reason.
    notes: tuple[str, ...] = ()

    @property
    def priced(self) -> bool:
        return self.reason is None

    @property
    def monthly_before(self) -> Decimal | None:
        return None if self.before is None else self.before.monthly

    @property
    def monthly_after(self) -> Decimal | None:
        return None if self.after is None else self.after.monthly

    @property
    def monthly_change(self) -> Decimal | None:
        if not self.priced:
            return None
        return (self.monthly_after or Decimal(0)) - (self.monthly_before or Decimal(0))


@dataclass(frozen=True)
class Estimate:
    """A plan priced: its lines, and totals over those priced."""

    lines: tuple[EstimateLine, ...]

    @property
    def unpriced(self) -> tuple[EstimateLine, ...]:
        return tuple(one for one in self.lines if not one.priced)

    @property
    def monthly_before(self) -> Decimal:
        return sum((one.monthly_before or Decimal(0) for one in self.lines), Decimal(0))

    @property
    def monthly_after(self) -> Decimal:
        return sum((one.monthly_after or Decimal(0) for one in self.lines), Decimal(0))

    @property
    def monthly_change(self) -> Decimal:
        return self.monthly_after - self.monthly_before


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


Priced = tuple[tuple["Component", ...], tuple[str, ...]]
Pricer = Callable[[Values, str, Catalogue], "Priced | str"]


def price_plan(plan: ReducedPlan, catalogue: Catalogue) -> Estimate:
    """Every change in a reduced plan, priced or with the reason it is not."""
    return Estimate(tuple(price_change(one, catalogue) for one in plan.changes))


def price_change(change: PlannedChange, catalogue: Catalogue) -> EstimateLine:
    """One change priced on each side it has: a creation after, a destroy before, an update both."""
    line = EstimateLine(
        address=change.address,
        resource_type=change.resource_type,
        actions=change.actions,
        region=change.region,
    )
    pricer = PRICERS.get(change.resource_type)
    if pricer is None:
        return _unpriced(line, _not_priced(change.resource_type))
    if change.region is None:
        return _unpriced(line, NO_REGION)
    withheld = frozenset(change.withheld)
    sides = _sides(change)
    found: dict[str, Side] = {}
    notes: list[str] = []
    for side, values, unknown in sides:
        priced = pricer(Values(values, unknown, withheld), change.region, catalogue)
        if isinstance(priced, str):
            return _unpriced(line, f"{side}: {priced}" if len(sides) > 1 else priced)
        components, said = priced
        found[side] = Side(components)
        notes.extend(said)
    return EstimateLine(
        address=change.address,
        resource_type=change.resource_type,
        actions=change.actions,
        region=change.region,
        before=found.get("before"),
        after=found.get("after"),
        notes=tuple(dict.fromkeys(notes)),
    )


def _sides(change: PlannedChange) -> list[tuple[str, Mapping[str, Any], frozenset[str]]]:
    """The sides a change is priced on, each with its values and what Terraform does not know."""
    found: list[tuple[str, Mapping[str, Any], frozenset[str]]] = []
    updated = change.actions == ("update",)
    if "delete" in change.actions or updated:
        found.append(("before", change.before, frozenset()))
    if "create" in change.actions or updated:
        found.append(("after", change.after, frozenset(change.unknown)))
    return found


def _unpriced(line: EstimateLine, reason: str) -> EstimateLine:
    return EstimateLine(
        address=line.address,
        resource_type=line.resource_type,
        actions=line.actions,
        region=line.region,
        reason=reason,
    )


def _not_priced(resource_type: str) -> str:
    if resource_type in USAGE_BASED:
        return f"{resource_type} is billed by use, which a plan does not say"
    return f"{resource_type} is not a type Meter prices"


def _instance(side: Values, region: str, catalogue: Catalogue) -> Priced | str:
    """An instance's hours, and its root and EBS block devices as volumes."""
    absent = side.absent("instance_type")
    if absent is not None:
        return absent
    instance_type = side.values.get("instance_type")
    if not isinstance(instance_type, str) or not instance_type:
        return "it names no instance_type"
    tenancy = side.values.get("tenancy")
    if tenancy in ("dedicated", "host"):
        return f"its tenancy is {tenancy}, and the catalog holds shared tenancy prices only"
    markets = [one.get("market_type") for one in side.values.get("instance_market_options") or ()]
    if "spot" in markets:
        return "a spot instance's price moves with the market, and Meter prices on demand"
    quote = catalogue.instance_hour(region, instance_type)
    if isinstance(quote, str):
        return quote
    components = [Component(f"{instance_type}, Linux, on demand", HOURS_PER_MONTH, quote)]
    notes = [LINUX]
    for name in ("root_block_device", "ebs_block_device"):
        absent = side.absent(name)
        if absent is not None:
            notes.append(f"{name} not priced: {absent}")
            continue
        for index, block in enumerate(side.values.get(name) or ()):
            priced = _price_volume(_block(side, f"{name}[{index}]", block), region, catalogue)
            if isinstance(priced, str):
                notes.append(f"{name}[{index}] not priced: {priced}")
                continue
            components.extend(priced[0])
            notes.extend(priced[1])
    return tuple(components), tuple(notes)


def _ebs_volume(side: Values, region: str, catalogue: Catalogue) -> Priced | str:
    """A volume's storage, and the IOPS and throughput its type prices apart."""
    volume = _Volume(
        label="the volume",
        kind=side.values.get("type"),
        size=side.values.get("size"),
        iops=side.values.get("iops"),
        throughput=side.values.get("throughput"),
        absent=_absent(side, "", _VOLUME_TERMS),
    )
    return _price_volume(volume, region, catalogue)


_VOLUME_TERMS: Final = {"kind": "type", "size": "size", "iops": "iops", "throughput": "throughput"}
_BLOCK_TERMS: Final = {
    "kind": "volume_type",
    "size": "volume_size",
    "iops": "iops",
    "throughput": "throughput",
}


@dataclass(frozen=True)
class _Volume:
    label: str
    kind: Any
    size: Any
    iops: Any
    throughput: Any
    #: Why a term is missing, by term: kind, size, iops or throughput.
    absent: Mapping[str, str]


def _block(side: Values, label: str, block: Mapping[str, Any]) -> _Volume:
    return _Volume(
        label=label,
        kind=block.get("volume_type"),
        size=block.get("volume_size"),
        iops=block.get("iops"),
        throughput=block.get("throughput"),
        absent=_absent(side, f"{label}.", _BLOCK_TERMS),
    )


def _absent(side: Values, prefix: str, terms: Mapping[str, str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for term, name in terms.items():
        reason = side.absent(prefix + name)
        if reason is not None:
            found[term] = reason
    return found


def _price_volume(volume: _Volume, region: str, catalogue: Catalogue) -> Priced | str:
    """A volume's storage, which the line rests on, and its IOPS and throughput, which it does
    not: one of those that cannot be priced is a note."""
    for term in ("kind", "size"):
        if term in volume.absent:
            return volume.absent[term]
    if volume.kind not in VOLUME_TYPES:
        return f"its volume type {volume.kind!r} is not one the catalog prices"
    if not _positive(volume.size):
        return "it gives no size"
    storage = catalogue.volume_month(region, volume.kind, "storage")
    if isinstance(storage, str):
        return storage
    size = _decimal(volume.size)
    components = [Component(f"{volume.kind} storage, {size} GiB", size, storage)]
    notes: list[str] = []
    if volume.kind == "gp3":
        extra = (
            ("iops", volume.iops, GP3_IOPS, "IOPS"),
            ("throughput", volume.throughput, GP3_MIBPS, "MiB/s"),
        )
        for term, given, included, unit in extra:
            if term in volume.absent:
                notes.append(f"{volume.label} {term} not priced: {volume.absent[term]}")
            elif _positive(given) and given > included:
                _add(components, notes, volume, (region, catalogue), term, given - included, unit)
    elif volume.kind == "io1":
        if "iops" in volume.absent:
            notes.append(f"{volume.label} iops not priced: {volume.absent['iops']}")
        elif not _positive(volume.iops):
            notes.append(f"{volume.label} iops not priced: an io1 volume gives none")
        else:
            _add(components, notes, volume, (region, catalogue), "iops", volume.iops, "IOPS")
    elif volume.kind == "io2":
        notes.append(
            f"{volume.label} iops not priced: io2 IOPS are priced in tiers the catalog does not "
            "tell apart"
        )
    elif volume.kind == "standard":
        notes.append(f"{volume.label} I/O requests not priced: they are billed by use")
    return tuple(components), tuple(notes)


def _add(
    components: list[Component],
    notes: list[str],
    volume: _Volume,
    where: tuple[str, Catalogue],
    term: str,
    quantity: Any,
    unit: str,
) -> None:
    """One provisioned term of a volume: a component where the catalog prices it, else a note."""
    region, catalogue = where
    quote = catalogue.volume_month(region, volume.kind, term)
    if isinstance(quote, str):
        notes.append(f"{volume.label} {term} not priced: {quote}")
        return
    amount = _decimal(quantity)
    components.append(Component(f"{volume.kind} {term}, {amount} {unit}", amount, quote))


def _positive(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and value > 0


def _decimal(value: int | float) -> Decimal:
    """A quantity as a Decimal from its text, so a float carries no binary remainder."""
    return Decimal(str(value))


#: The pricer for each type Meter prices. A type not here is listed with the reason.
PRICERS: Final[Mapping[str, Pricer]] = {
    "aws_instance": _instance,
    "aws_ebs_volume": _ebs_volume,
}
