"""The prefix rule, and the three different absences it has to keep apart.

FEAT-061. The cases that carry this file are the ones where returning the wrong thing puts real
resources on the wrong continent or removes them from the estate entirely.
"""

from __future__ import annotations

import pytest

from finops_core.domain.geography import GEOGRAPHIES, geography_of, is_global


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
    ],
)
def test_reads_the_geography_from_the_prefix(region: str, expected: str) -> None:
    geography = geography_of(region)
    assert geography is not None
    assert geography.key == expected


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


def test_every_geography_key_is_the_prefix_it_matches() -> None:
    # The table is the index. A row whose key is not the prefix its regions carry would be a row
    # that never matches anything, and nothing else here would notice.
    for geography in GEOGRAPHIES:
        resolved = geography_of(f"{geography.key}-central-1")
        assert resolved is not None
        assert resolved.key == geography.key


def test_keys_are_unique() -> None:
    keys = [geography.key for geography in GEOGRAPHIES]
    assert len(keys) == len(set(keys))
