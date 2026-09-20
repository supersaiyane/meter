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


class TestFingerprintAndQueryKey:
    """The three properties TASK-P2-011 exists to guarantee.

    `fingerprint` and `query_key` answer different questions, and the tests
    below are mostly about keeping them apart. A fingerprint says which
    definition this is; a query key says what the query is. Collapsing them
    would either lose a panel to an upsert or stop measured evidence attaching
    to more than one.
    """

    QUERY = "fields @timestamp, @message | filter region = $region"

    def test_a_fingerprint_survives_template_substitution(self) -> None:
        # A panel with a $region variable and four regions is one query, not
        # four each holding a quarter of the cost and none of the history.
        templated = policy.fingerprint(
            account_id="1",
            workspace_name="ws",
            dashboard_uid="d1",
            panel="p",
            ref_id="A",
            query=self.QUERY,
        )
        again = policy.fingerprint(
            account_id="1",
            workspace_name="ws",
            dashboard_uid="d1",
            panel="p",
            ref_id="A",
            query="fields @timestamp, @message | filter region = ${region}",
        )
        assert templated == again

    def test_whitespace_and_comments_do_not_move_a_fingerprint(self) -> None:
        # Annotating a query has not changed what it costs, and a key that moved
        # would abandon every day of history behind it.
        plain = policy.fingerprint(
            account_id="1",
            workspace_name="ws",
            dashboard_uid="d1",
            panel="p",
            ref_id="A",
            query="fields @timestamp | filter x",
        )
        decorated = policy.fingerprint(
            account_id="1",
            workspace_name="ws",
            dashboard_uid="d1",
            panel="p",
            ref_id="A",
            query="# owned by platform\nfields   @timestamp\n  | filter x  -- trailing",
        )
        assert plain == decorated

    def test_two_panels_on_different_dashboards_share_a_query_key(self) -> None:
        """The criterion, and why it is a second key rather than a wider first.

        Measured evidence has to attach to both panels. It cannot be done by
        widening `fingerprint`, because `uq_query_definition__fingerprint` makes
        that the identity of a row: two panels sharing one would upsert over each
        other and a panel would disappear from the estate.
        """
        first = policy.query_key("logs_insights", self.QUERY, ("/aws/a",))
        second = policy.query_key("logs_insights", self.QUERY, ("/aws/a",))
        assert first == second

        # And their definitions stay distinct, so neither is lost.
        left = policy.fingerprint(
            account_id="1",
            workspace_name="ws",
            dashboard_uid="dashboard-one",
            panel="p",
            ref_id="A",
            query=self.QUERY,
        )
        right = policy.fingerprint(
            account_id="1",
            workspace_name="ws",
            dashboard_uid="dashboard-two",
            panel="p",
            ref_id="A",
            query=self.QUERY,
        )
        assert left != right

    def test_a_query_key_separates_different_targets(self) -> None:
        # The same text over a different log group is a different cost, so it
        # must not inherit the other's measured evidence.
        one = policy.query_key("logs_insights", self.QUERY, ("/aws/a",))
        other = policy.query_key("logs_insights", self.QUERY, ("/aws/b",))
        assert one != other

    def test_a_query_key_does_not_depend_on_target_order(self) -> None:
        one = policy.query_key("logs_insights", self.QUERY, ("/aws/a", "/aws/b"))
        other = policy.query_key("logs_insights", self.QUERY, ("/aws/b", "/aws/a"))
        assert one == other

    def test_a_query_key_separates_engines(self) -> None:
        assert policy.query_key("logs_insights", "up", ()) != policy.query_key(
            "prometheus", "up", ()
        )
