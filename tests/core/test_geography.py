"""The prefix rule, and the three different absences it has to keep apart.

FEAT-061. The cases that carry this file are the ones where returning the wrong thing puts real
resources on the wrong continent or removes them from the estate entirely.
"""

from __future__ import annotations

import pytest

from finops_core.domain.geography import GEOGRAPHIES, PREFIXES, geography_of, is_global


@pytest.mark.parametrize(
    ("region", "expected"),
    [
        ("us-east-1", "us"),
        ("us-west-2", "us"),
        # The partition is a different fact. A GovCloud region is in the United States, and a
        # geography question is not a compliance question.
        ("us-gov-west-1", "us"),
        ("eu-west-1", "eu"),
        # The point of the prefix rather than a table of regions: this region did not exist when
        # the table was written and resolves anyway.
        ("eu-south-9", "eu"),
        ("ap-southeast-4", "ap"),
        ("sa-east-1", "sa"),
        ("me-central-1", "me"),
        ("il-central-1", "il"),
        ("af-south-1", "af"),
        ("cn-north-1", "cn"),
        ("ca-central-1", "ca"),
        # Live since 2024 and missing from the first version of the table, which was written
        # from memory. Checked against the AWS region list on 2026-09-27.
        ("mx-central-1", "mx"),
        ("ap-east-2", "ap"),
        ("ap-southeast-7", "ap"),
    ],
)
def test_reads_the_geography_from_the_prefix(region: str, expected: str) -> None:
    geography = geography_of(region)
    assert geography is not None
    assert geography.key == expected


def test_a_partition_prefix_resolves_to_the_place_it_is_in() -> None:
    """`eusc-de-east-1` is the AWS European Sovereign Cloud, and it is in Europe.

    The case that broke the first design. That version keyed the places by their prefix, which
    assumed one prefix per place, and this is four letters reaching a place another prefix already
    names. A table keyed by prefix cannot express it without inventing a second Europe, which the
    drawing would then have to position twice.
    """
    geography = geography_of("eusc-de-east-1")
    assert geography is not None
    assert geography.key == "eu"
    assert geography.name == "Europe"


def test_every_place_is_named_once_however_many_prefixes_reach_it() -> None:
    # Europe has two prefixes and must still be one row on a screen and one marker on a map.
    reached = {geography.key for geography in PREFIXES.values()}
    assert reached == {geography.key for geography in GEOGRAPHIES}
    assert len(GEOGRAPHIES) < len(PREFIXES)


def test_is_case_and_whitespace_insensitive() -> None:
    # A region arrives from a provider response, a state file and a bill, and one of those three
    # will eventually hand over a capitalised or padded string.
    geography = geography_of("  EU-WEST-1 ")
    assert geography is not None
    assert geography.key == "eu"


def test_refuses_to_guess_at_a_name_with_no_prefix() -> None:
    # A guess here puts real resources on the wrong continent, which is worse than saying the
    # name does not tell us.
    assert geography_of("somewhere") is None
    assert geography_of("") is None


def test_an_unknown_prefix_is_unplaceable_and_not_an_error() -> None:
    # The case that must never raise and must never be silently dropped. A provider opening a
    # geography we have not heard of has to show up as a count somebody can act on.
    assert geography_of("zz-central-1") is None


def test_no_region_is_global_and_an_unreadable_one_is_not() -> None:
    # The distinction the screen is built on. A global resource is a real state, an unplaceable
    # one is a prompt to widen the table, and counting them together would turn every IAM role in
    # the estate into a thing somebody is asked to fix.
    assert is_global(None) is True
    assert is_global("   ") is True
    assert is_global("zz-central-1") is False
    assert is_global("us-east-1") is False


def test_every_prefix_resolves_to_a_place_that_exists() -> None:
    # A prefix pointing at a place the list does not hold would be a prefix that matches and then
    # names something no screen can draw, and nothing else here would notice.
    for prefix, geography in PREFIXES.items():
        resolved = geography_of(f"{prefix}-central-1")
        assert resolved is not None
        assert resolved.key == geography.key
        assert geography in GEOGRAPHIES


def test_keys_are_unique() -> None:
    keys = [geography.key for geography in GEOGRAPHIES]
    assert len(keys) == len(set(keys))
