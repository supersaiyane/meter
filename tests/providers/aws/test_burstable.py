"""The burstable baselines, held to the EC2 guide and to every type that needs one. TASK-P9-005.

P9 spec section 5.4 asks for a test that fails when a burstable type is missing from the table.
The types a real description or the fake estate names as burstable are the ones this repository
can see; a live description of a new family would surface the same gap as NoData in sync_error.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from finops_fakes.catalog import SPECS
from finops_providers.aws import burstable
from finops_providers.aws.burstable import (
    FAMILIES,
    SOURCE,
    TABLE,
    Baseline,
    baseline_of,
    counterpart,
    is_burstable_name,
)

EXTRACTS = Path(__file__).resolve().parent / "extracts"


def test_every_burstable_type_the_fake_estate_prices_has_a_row() -> None:
    burstable_types = {name for name, spec in SPECS.items() if spec[3]}
    assert burstable_types, "the fake estate prices no burstable type, so this proves nothing"
    assert burstable_types - TABLE.keys() == set()


def test_every_burstable_type_a_real_description_names_has_a_row() -> None:
    described = json.loads((EXTRACTS / "describe-instance-types-t2-micro.json").read_text())
    named = {
        raw["InstanceType"]
        for raw in described["InstanceTypes"]
        if raw["BurstablePerformanceSupported"]
    }
    assert named
    assert named - TABLE.keys() == set()


def test_every_row_is_one_of_the_burstable_families() -> None:
    assert {name.split(".")[0] for name in TABLE} == FAMILIES


@pytest.mark.parametrize(
    ("name", "per_vcpu", "maximum"),
    [
        ("t3.large", "0.30", "864"),
        ("t2.xlarge", "0.225", "1296"),
        ("t2.2xlarge", "0.17", "1958.4"),
        ("t4g.nano", "0.05", "144"),
        ("t8i.medium", "0.20", "576"),
    ],
)
def test_the_guides_figures_are_held(name: str, per_vcpu: str, maximum: str) -> None:
    assert TABLE[name].per_vcpu == Decimal(per_vcpu)
    assert TABLE[name].maximum_credits == Decimal(maximum)


def test_a_row_copied_wrongly_fails_the_guides_own_formulas() -> None:
    wrong = {"t3.large": Baseline(Decimal(36), Decimal(800), 2, Decimal("0.30"))}
    with pytest.raises(ValueError, match=r"t3\.large"):
        burstable._check(wrong)


@pytest.mark.parametrize(
    ("name", "ec2"),
    [
        ("db.t3.micro", "t3.micro"),
        ("cache.t4g.small", "t4g.small"),
        ("t3.small.search", "t3.small"),
        ("t3.small.elasticsearch", "t3.small"),
        ("m5.large", "m5.large"),
    ],
)
def test_a_managed_class_is_read_as_the_ec2_type_it_is_named_after(name: str, ec2: str) -> None:
    assert counterpart(name) == ec2


def test_a_baseline_names_its_source_and_any_row_it_was_borrowed_from() -> None:
    own = baseline_of("t3.micro")
    borrowed = baseline_of("db.t3.micro")
    assert own is not None and borrowed is not None
    assert own[1] == SOURCE
    assert borrowed[1] == f"{SOURCE}, the row for t3.micro"
    assert baseline_of("t9.micro") is None


@pytest.mark.parametrize(
    ("name", "expected"),
    [("db.t3.micro", True), ("t2.nano", True), ("cache.m5.large", False), ("t5.micro", False)],
)
def test_a_burstable_family_is_known_by_its_name(name: str, expected: bool) -> None:
    assert is_burstable_name(name) is expected
