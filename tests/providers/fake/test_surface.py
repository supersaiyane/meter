"""The fake estate's dashboards, as they stood on an earlier day.

A modelled cost is computed from the definition, so the only thing that can
move one over time is somebody editing the dashboard. This is that edit, and
the test that matters most here is not that the numbers change: it is that the
fingerprints do not, because a trend line is attached to a finding by its
fingerprint and a history of renamed queries would draw sixteen one day lines
that look like a trend and are not.
"""

from __future__ import annotations

from dataclasses import replace

from finops_fakes.surface import QUERIES, REFRESH_HISTORY, queries_as_of

ALERT = "fp-alert-0004"
TEAM = "fp-team-0001"


def definition(days_ago: int, fingerprint: str):  # type: ignore[no-untyped-def]
    for definitions in queries_as_of(days_ago).values():
        for found in definitions:
            if found.fingerprint == fingerprint:
                return found
    raise AssertionError(f"{fingerprint} is not in the estate {days_ago} days ago")


class TestTodayIsUntouched:
    def test_no_history_asked_for_returns_the_estate_itself(self) -> None:
        # Every existing fixture builds `FakeQuerySurface()` with no queries at
        # all, and a fake that quietly rewrote itself would change costs in
        # tests that never mentioned a history.
        assert queries_as_of(0) is QUERIES

    def test_the_newest_day_of_a_history_is_today(self) -> None:
        assert definition(0, ALERT).refresh_seconds == 1800


class TestTheDashboardsWereDifferent:
    def test_the_alert_used_to_run_hourly(self) -> None:
        assert definition(4, ALERT).refresh_seconds == 3600

    def test_it_is_a_step_and_not_a_ramp(self) -> None:
        """A definition does not drift. It holds still and then changes on the
        day a person changed it, which is what makes the step actionable: the
        reader can go and find out who did it and why.
        """
        before = [definition(days_ago, ALERT).refresh_seconds for days_ago in (3, 4, 5, 6)]
        after = [definition(days_ago, ALERT).refresh_seconds for days_ago in (0, 1, 2)]
        assert len(set(before)) == 1
        assert len(set(after)) == 1
        assert before[0] > after[0], "the alert got slower rather than faster over time"

    def test_the_step_lands_where_the_history_says(self) -> None:
        older_than, previous = REFRESH_HISTORY[ALERT]
        assert definition(older_than, ALERT).refresh_seconds == previous
        assert definition(older_than - 1, ALERT).refresh_seconds != previous

    def test_the_template_moved_every_panel_at_once(self) -> None:
        # Editing a template edits every panel built from it, which is what
        # makes twelve small findings move together and become the largest
        # single change in the estate.
        moved = [
            found
            for definitions in queries_as_of(6).values()
            for found in definitions
            if found.fingerprint.startswith("fp-team-")
        ]
        assert len(moved) == 12
        assert {found.refresh_seconds for found in moved} == {60}


class TestNothingElseMoves:
    def test_the_fingerprints_are_the_same_on_every_day(self) -> None:
        """The trend hangs off these. A history that renamed anything would
        draw a fresh finding per day, which reads on screen as a trend and is
        sixteen unconnected points.
        """
        today = {found.fingerprint for definitions in QUERIES.values() for found in definitions}
        for days_ago in range(30):
            earlier = {
                found.fingerprint
                for definitions in queries_as_of(days_ago).values()
                for found in definitions
            }
            assert earlier == today, f"the estate changed shape {days_ago} days ago"

    def test_only_the_refresh_interval_differs(self) -> None:
        # A history that also moved the query text or the window would make the
        # step impossible to attribute: the reader could not say which of the
        # three changes cost the money.
        for definitions in QUERIES.values():
            for found in definitions:
                earlier = definition(6, found.fingerprint)
                assert replace(earlier, refresh_seconds=found.refresh_seconds) == found
