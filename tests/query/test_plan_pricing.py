"""Compute and storage priced from the catalog. TASK-P16-003, FEAT-095, spec sections 5.3 and 5.4.

Against a catalog that answers from a table, with unit prices made up for the test. An instance is
its hours as Linux with its block devices as volumes; a volume is its storage with IOPS and
throughput where its type prices them apart. What cannot be priced is a reason with no figure,
and a part left out is a note.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

import pytest

from finops_query.plan_pricing import LINUX, NO_REGION, EstimateLine, price_change, price_plan
from finops_query.plan_quotes import Catalogue, Component, Quote
from finops_query.plan_reading import PlannedChange, ReducedPlan, reduce_plan

REGION = "eu-west-1"
VERSION = "20261001000000"
AWS = "registry.terraform.io/hashicorp/aws"
HOURS = {"m6i.large": Decimal("0.107"), "m6i.xlarge": Decimal("0.214")}
MONTHS = {
    ("gp2", "storage"): Decimal("0.11"),
    ("gp3", "storage"): Decimal("0.088"),
    ("gp3", "iops"): Decimal("0.0055"),
    ("gp3", "throughput"): Decimal("0.044"),
    ("io1", "storage"): Decimal("0.138"),
    ("io1", "iops"): Decimal("0.072"),
    ("io2", "storage"): Decimal("0.138"),
    ("st1", "storage"): Decimal("0.05"),
    ("standard", "storage"): Decimal("0.055"),
}
UNITS = {"storage": "GB-Mo", "iops": "IOPS-Mo", "throughput": "MiBps-Mo"}


class Shelf:
    """A catalog answering from tables, and saying what it lacks."""

    def __init__(
        self,
        hours: dict[str, Decimal] | None = None,
        months: dict[tuple[str, str], Decimal] | None = None,
    ) -> None:
        self.hours = HOURS if hours is None else hours
        self.months = MONTHS if months is None else months

    def instance_hour(self, region: str, instance_type: str) -> Quote | str:
        price = self.hours.get(instance_type) if region == REGION else None
        if price is None:
            return f"the catalog holds no on demand Linux price for {instance_type} in {region}"
        return Quote(f"{instance_type}.HRS", price, "Hrs", VERSION)

    def volume_month(self, region: str, volume_type: str, term: str) -> Quote | str:
        price = self.months.get((volume_type, term)) if region == REGION else None
        if price is None:
            return f"the catalog holds no {volume_type} {term} price in {region}"
        return Quote(f"{volume_type}.{term}", price, UNITS[term], VERSION)

    def service_price(
        self, service: str, region: str, attributes: Mapping[str, str], term: str
    ) -> Quote | str:
        return f"the catalog holds no {service} {term} price for {dict(attributes)} in {region}"


SHELF: Catalogue = Shelf()


def planned(
    resource_type: str,
    after: dict[str, Any] | None = None,
    *,
    actions: tuple[str, ...] = ("create",),
    before: dict[str, Any] | None = None,
    region: str | None = REGION,
    unknown: tuple[str, ...] = (),
    withheld: tuple[str, ...] = (),
) -> PlannedChange:
    return PlannedChange(
        address=f"{resource_type}.this",
        resource_type=resource_type,
        actions=actions,
        region=region,
        before=before or {},
        after=after or {},
        unknown=unknown,
        withheld=withheld,
    )


def priced(change: PlannedChange, catalogue: Catalogue = SHELF) -> EstimateLine:
    line = price_change(change, catalogue)
    assert line.priced, line.reason
    return line


def parts(line: EstimateLine) -> list[Component]:
    assert line.after is not None
    return list(line.after.components)


def refused(change: PlannedChange, catalogue: Catalogue = SHELF) -> str:
    line = price_change(change, catalogue)
    assert line.reason is not None, line
    assert (line.before, line.after, line.monthly_change) == (None, None, None)
    return line.reason


def gp3_root(**block: Any) -> dict[str, Any]:
    return {"instance_type": "m6i.large", "root_block_device": [{"volume_type": "gp3", **block}]}


def test_an_instance_is_its_hours_as_linux_and_its_root_volume() -> None:
    line = priced(planned("aws_instance", gp3_root(volume_size=50)))
    assert [(one.what, one.monthly) for one in parts(line)] == [
        ("m6i.large, Linux, on demand", Decimal("78.11")),
        ("gp3 storage, 50 GiB", Decimal("4.40")),
    ]
    assert (line.monthly_before, line.monthly_after) == (None, Decimal("82.51"))
    assert line.monthly_change == Decimal("82.51")
    assert line.notes == (LINUX,)
    hours = parts(line)[0].quote
    assert (hours.sku_price_id, hours.unit, hours.version) == ("m6i.large.HRS", "Hrs", VERSION)


@pytest.mark.parametrize(
    ("unknown", "note"),
    [
        (
            ("root_block_device[0].volume_size",),
            "root_block_device[0] not priced: root_block_device[0].volume_size is known only after",
        ),
        (("root_block_device",), "root_block_device not priced: root_block_device is known only"),
    ],
)
def test_a_block_device_terraform_does_not_know_yet_is_a_note_and_the_hours_stand(
    unknown: tuple[str, ...], note: str
) -> None:
    line = priced(planned("aws_instance", gp3_root(), unknown=unknown))
    assert line.monthly_after == Decimal("78.11")
    assert any(one.startswith(note) for one in line.notes), line.notes


def test_an_ebs_block_device_is_priced_beside_the_root_and_a_bad_one_is_a_note() -> None:
    after = {
        **gp3_root(volume_size=8),
        "ebs_block_device": [
            {"volume_type": "st1", "volume_size": 500},
            {"volume_type": "gp9", "volume_size": 10},
        ],
    }
    line = priced(planned("aws_instance", after))
    assert [one.what for one in parts(line)] == [
        "m6i.large, Linux, on demand",
        "gp3 storage, 8 GiB",
        "st1 storage, 500 GiB",
    ]
    bad = "ebs_block_device[1] not priced: its volume type 'gp9' is not one the catalog prices"
    assert bad in line.notes


SPOT = {"instance_type": "m6i.large", "instance_market_options": [{"market_type": "spot"}]}


@pytest.mark.parametrize(
    ("change", "says"),
    [
        (planned("aws_instance", {}, unknown=("instance_type",)), "instance_type is known only"),
        (
            planned("aws_instance", {}, withheld=("instance_type",)),
            "instance_type is marked sensitive, so Meter does not keep it",
        ),
        (planned("aws_instance", {"tenancy": "default"}), "it names no instance_type"),
        (
            planned("aws_instance", {"instance_type": "m6i.large", "tenancy": "dedicated"}),
            "its tenancy is dedicated, and the catalog holds shared tenancy prices only",
        ),
        (planned("aws_instance", SPOT), "a spot instance's price moves with the market"),
        (
            planned("aws_instance", {"instance_type": "x9z.huge"}),
            "the catalog holds no on demand Linux price for x9z.huge in eu-west-1",
        ),
        (planned("aws_instance", {"instance_type": "m6i.large"}, region=None), NO_REGION),
        (planned("aws_ebs_volume", {"type": "gp9", "size": 10}), "is not one the catalog prices"),
        (planned("aws_ebs_volume", {"type": "gp3"}), "it gives no size"),
        (planned("aws_ebs_volume", {"type": "gp3", "size": 0}), "it gives no size"),
        (planned("aws_ebs_volume", {"size": 10}, unknown=("type",)), "type is known only after"),
        (
            planned("aws_ebs_volume", {"type": "gp3", "size": 10}, region="ap-east-9"),
            "the catalog holds no gp3 storage price in ap-east-9",
        ),
        (planned("aws_nat_gateway", {}), "aws_nat_gateway is billed by use, which a plan does not"),
        (planned("aws_iam_role", {}), "aws_iam_role is not a type Meter prices"),
    ],
)
def test_a_line_that_cannot_rest_on_its_principal_part_says_why_and_has_no_figure(
    change: PlannedChange, says: str
) -> None:
    assert says in refused(change)


def test_gp3_prices_iops_and_throughput_above_what_its_storage_includes() -> None:
    volume = {"type": "gp3", "size": 1000, "iops": 6000, "throughput": 250}
    line = priced(planned("aws_ebs_volume", volume))
    assert [(one.what, one.monthly) for one in parts(line)] == [
        ("gp3 storage, 1000 GiB", Decimal("88")),
        ("gp3 iops, 3000 IOPS", Decimal("16.5")),
        ("gp3 throughput, 125 MiB/s", Decimal("5.5")),
    ]
    assert line.monthly_after == Decimal("110")
    included = priced(planned("aws_ebs_volume", {"type": "gp3", "size": 100, "iops": 3000}))
    assert included.monthly_after == Decimal("8.8")


def test_io1_prices_its_iops_and_io2_standard_and_a_missing_term_are_notes() -> None:
    io1 = priced(planned("aws_ebs_volume", {"type": "io1", "size": 400, "iops": 4000}))
    assert io1.monthly_after == Decimal("55.2") + Decimal("288")
    bare = priced(planned("aws_ebs_volume", {"type": "io1", "size": 400}))
    assert bare.notes == ("the volume iops not priced: an io1 volume gives none",)
    io2 = priced(planned("aws_ebs_volume", {"type": "io2", "size": 100, "iops": 5000}))
    assert io2.monthly_after == Decimal("13.8")
    assert "io2 IOPS are priced in tiers" in io2.notes[0]
    standard = priced(planned("aws_ebs_volume", {"type": "standard", "size": 100}))
    assert standard.notes == ("the volume I/O requests not priced: they are billed by use",)
    unknown = priced(
        planned("aws_ebs_volume", {"type": "gp3", "size": 100}, unknown=("iops", "throughput"))
    )
    assert unknown.notes == (
        "the volume iops not priced: iops is known only after apply",
        "the volume throughput not priced: throughput is known only after apply",
    )


def test_a_term_the_catalog_lacks_is_a_note_and_the_storage_stands() -> None:
    months = {key: value for key, value in MONTHS.items() if key != ("gp3", "iops")}
    volume = planned("aws_ebs_volume", {"type": "gp3", "size": 100, "iops": 4000})
    line = priced(volume, Shelf(months=months))
    assert line.monthly_after == Decimal("8.8")
    assert line.notes == (
        "the volume iops not priced: the catalog holds no gp3 iops price in eu-west-1",
    )


def test_an_update_is_both_sides_and_its_change_the_difference() -> None:
    larger = planned(
        "aws_instance",
        {"instance_type": "m6i.xlarge"},
        actions=("update",),
        before={"instance_type": "m6i.large"},
    )
    line = priced(larger)
    assert (line.monthly_before, line.monthly_after) == (Decimal("78.11"), Decimal("156.22"))
    assert line.monthly_change == Decimal("78.11")
    old = planned(
        "aws_instance",
        {"instance_type": "m6i.large"},
        actions=("update",),
        before={"instance_type": "m4.retired"},
    )
    assert refused(old).startswith("before: the catalog holds no on demand Linux price for m4")


def test_a_destroy_is_its_before_and_a_replacement_both() -> None:
    gp2 = {"type": "gp2", "size": 100}
    destroyed = priced(planned("aws_ebs_volume", actions=("delete",), before=gp2))
    assert (destroyed.monthly_before, destroyed.after) == (Decimal("11.00"), None)
    assert destroyed.monthly_change == Decimal("-11.00")
    swapped = planned(
        "aws_ebs_volume", {"type": "gp3", "size": 100}, actions=("delete", "create"), before=gp2
    )
    assert priced(swapped).monthly_change == Decimal("8.8") - Decimal("11")


def resource(address: str, resource_type: str, **change: Any) -> dict[str, Any]:
    name = address.split(".")[-1]
    entry = {"address": address, "mode": "managed", "type": resource_type, "name": name}
    return {**entry, "provider_name": AWS, "change": change}


def test_a_plan_is_priced_line_by_line_and_totals_only_what_is_priced() -> None:
    region = {"region": {"constant_value": REGION}}
    document = {
        "format_version": "1.2",
        "planned_values": {},
        "configuration": {"provider_config": {"aws": {"name": "aws", "expressions": region}}},
        "resource_changes": [
            resource(
                "aws_instance.web",
                "aws_instance",
                actions=["create"],
                before=None,
                after=gp3_root(volume_size=50),
                after_unknown={},
            ),
            resource(
                "aws_ebs_volume.old",
                "aws_ebs_volume",
                actions=["delete"],
                before={"type": "gp2", "size": 100},
                after=None,
            ),
            resource(
                "aws_s3_bucket.logs",
                "aws_s3_bucket",
                actions=["create"],
                before=None,
                after={"bucket": "logs"},
            ),
        ],
    }
    reduced = reduce_plan(json.dumps(document).encode())
    assert isinstance(reduced, ReducedPlan)
    estimate = price_plan(reduced, SHELF)
    assert [one.address for one in estimate.unpriced] == ["aws_s3_bucket.logs"]
    assert (estimate.monthly_before, estimate.monthly_after) == (Decimal("11"), Decimal("82.51"))
    assert estimate.monthly_change == Decimal("71.51")
