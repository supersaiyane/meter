"""Fingerprinting, and the reason it is template aware.

The failure this prevents is quiet. A panel with a `$region` variable and four
regions produces four different query strings, so a fingerprint built from the
raw text makes four rows where there is one query. Each has a quarter of the
cost, none has enough history to trend, and the dashboard looks cheap.
"""

from __future__ import annotations

import pytest

from finops_query import policy


def test_formatting_does_not_change_the_key() -> None:
    assert policy.normalise("  SELECT   x  FROM y ") == policy.normalise("select x from y")


@pytest.mark.parametrize(
    "query",
    [
        "fields @timestamp | filter region = '$region'",
        "fields @timestamp | filter region = '${region}'",
        "fields @timestamp | filter region = '[[region]]'",
    ],
)
def test_all_three_template_syntaxes_are_recognised(query: str) -> None:
    """Grafana has three, and dashboards in the wild use all of them."""
    assert policy.has_template_vars(query)


def test_a_templated_query_is_one_key_whatever_the_variable_resolves_to() -> None:
    """The whole reason the module exists."""
    template = "fields @timestamp | filter region = '$region'"
    other = "fields @timestamp | filter region = '${region}'"

    assert policy.template_key(template) == policy.template_key(other)


def test_two_different_queries_are_not_the_same_key() -> None:
    """Collapsing variables must not collapse everything."""
    assert policy.template_key("filter a = '$x'") != policy.template_key("filter b = '$x'")


def test_a_fingerprint_is_stable_across_variable_values() -> None:
    common = {
        "account_id": "acct",
        "workspace_name": "ws",
        "dashboard_uid": "uid",
        "panel": "p",
        "ref_id": "A",
    }
    first = policy.fingerprint(**common, query="filter r = '$region'")
    second = policy.fingerprint(**common, query="filter r = '${region}'")

    assert first == second
    assert len(first) == policy.FINGERPRINT_LENGTH


def test_a_fingerprint_changes_when_the_panel_changes() -> None:
    """Otherwise two panels on one dashboard would trend as one query."""
    common = {
        "account_id": "acct",
        "workspace_name": "ws",
        "dashboard_uid": "uid",
        "ref_id": "A",
        "query": "up",
    }

    assert policy.fingerprint(**common, panel="one") != policy.fingerprint(**common, panel="two")


def test_a_dashboard_with_no_uid_falls_back_to_its_title() -> None:
    """It still needs a stable key, and the title is the only other identifier."""
    by_title = policy.fingerprint_of(
        {"dashboard": "My board", "panel": "p", "ref_id": "A", "query": "up"}
    )
    explicit = policy.fingerprint(
        account_id="",
        workspace_name="",
        dashboard_uid="My board",
        panel="p",
        ref_id="A",
        query="up",
    )

    assert by_title == explicit


def test_a_pattern_matches_the_resolved_form_of_its_own_template() -> None:
    """Which is what lets a CloudTrail execution attach to a templated panel."""
    pattern = policy.match_pattern("fields @timestamp | filter region = '$region'")

    assert pattern is not None
    assert pattern.match("fields @timestamp | filter region = 'eu-west-1'")


def test_a_pattern_does_not_match_a_different_query() -> None:
    """A pattern that matched everything would attribute every execution to the
    first templated panel it found."""
    pattern = policy.match_pattern("filter region = '$region'")

    assert pattern is not None
    assert not pattern.match("filter service = 'api'")


def test_an_empty_query_produces_no_pattern() -> None:
    """None means attribute nothing. An empty pattern would match everything."""
    assert policy.match_pattern("") is None
    assert policy.match_pattern(None) is None


def test_a_query_that_is_only_a_variable_produces_a_usable_pattern() -> None:
    pattern = policy.match_pattern("$everything")

    assert pattern is not None
    assert pattern.match("anything")


def test_the_placeholder_cannot_occur_in_a_real_query() -> None:
    """A control character on purpose. A word would collide with real text."""
    assert policy.PLACEHOLDER == "\u0001"
    assert not policy.PLACEHOLDER.isprintable()
