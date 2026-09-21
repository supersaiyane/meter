"""The fake estate's past, which is what lets a trend be more than a flat line.

The property under test is not that the numbers go up. It is that they go up
for the right reason: the estate ran its queries more often as time went on, and
each run scanned what it always scanned. A fake that made every run hungrier
would also draw a rising line, and it would be drawing the wrong claim, because
the finding's cost per run is a figure people argue about separately from how
busy the estate is.
"""

from __future__ import annotations

from typing import Any

from finops_fakes.evidence import DAILY_GROWTH, FakeQueryEvidence
from finops_query.parser import GrafanaQueryParser

BUSY = "fields @timestamp, @message | filter @message like /ERROR/"


def observed(days_ago: int) -> dict[str, Any]:
    """Every log record the fake reports for a day that far back."""
    evidence = FakeQueryEvidence(GrafanaQueryParser(), days_ago=days_ago)
    logs = evidence.observations(account_id="111122223333", region="eu-west-1", lookback_days=30)[
        "logs"
    ]
    assert isinstance(logs, dict)
    return logs


def record(days_ago: int, query: str = BUSY) -> dict[str, Any]:
    parser = GrafanaQueryParser()
    found = observed(days_ago)[parser.normalise(query)]
    assert isinstance(found, dict)
    return found


class TestTheNewestDayIsUnchanged:
    def test_the_default_reports_the_records_as_written(self) -> None:
        """No history asked for, nothing moved.

        Every existing fixture and the single day seed depend on this. A fake
        that quietly rescaled itself would change figures in tests that never
        mentioned a history and never opted into one.
        """
        assert record(0) == record(0)
        assert record(0)["runs"] == 2400

    def test_day_zero_of_a_history_is_the_same_day_zero(self) -> None:
        # The newest day of a seven day seed is the day a one day seed writes,
        # so the two estates agree about the present and differ only about the
        # past.
        assert (
            record(0)["runs"]
            == FakeQueryEvidence(GrafanaQueryParser()).observations(
                account_id="111122223333", region="eu-west-1", lookback_days=30
            )["logs"][GrafanaQueryParser().normalise(BUSY)]["runs"]
        )


class TestTheEstateWasQuieter:
    def test_an_older_day_ran_the_query_fewer_times(self) -> None:
        assert record(6)["runs"] < record(0)["runs"]

    def test_every_step_back_is_a_step_down(self) -> None:
        """Monotonic, so the line rises rather than wandering.

        A curve that dipped anywhere would be indistinguishable on screen from
        a real estate that went quiet for a day, which is a thing a reader would
        go and investigate.
        """
        counts = [record(days_ago)["runs"] for days_ago in range(30)]
        assert counts == sorted(counts, reverse=True)
        # A flat list is sorted too, so the line above passes against a fake
        # with no history at all. This is the half that notices.
        assert counts[-1] < counts[0]

    def test_it_falls_at_the_stated_rate(self) -> None:
        # Not a magic slope. Six days back at four percent a day is the record
        # divided by 1.04 to the sixth, and the test says so rather than
        # restating whatever the code produced.
        assert record(6)["runs"] == round(2400 * DAILY_GROWTH**-6)


class TestEachRunScansWhatItScans:
    def test_the_cost_per_run_does_not_move(self) -> None:
        """The measurement divides bytes by the number of runs to get a per run
        figure, and that figure is what a finding reports as its scan size. It
        has to hold steady while the count carries the trend, or the screen
        reports an estate whose queries are getting more expensive one at a
        time, which is a different problem with a different fix.
        """
        for days_ago in (0, 3, 6, 29):
            row = record(days_ago)
            per_run = row["runs_bytes"]
            assert isinstance(per_run, list)
            assert set(per_run) == {2_147_483_648.0}

    def test_the_total_is_the_sum_of_the_runs(self) -> None:
        # `measure_logs_query` computes the average as bytes over the length of
        # the per run list. The two disagreeing would put a plausible and wrong
        # number on the screen rather than an obvious one.
        for days_ago in (0, 1, 6, 29):
            row = record(days_ago)
            assert row["bytes"] == sum(row["runs_bytes"])


class TestTheAdHocQueriesHaveAPastToo:
    def test_the_unowned_query_thins_out_as_well(self) -> None:
        """FEAT-051's rows are written from the same records, so a history that
        moved only the owned queries would leave the ad hoc screen flat while
        the findings list rose, and the two would be describing different
        estates.
        """
        unowned = "stats count() by bin(5m) | filter status >= 500"  # allow-hardcoded: query text
        assert record(6, unowned)["runs"] < record(0, unowned)["runs"]

    def test_a_small_query_still_reports_whole_runs(self) -> None:
        # A query cannot run 9.4 times. The count is what the database stores
        # and what the screen prints.
        assert isinstance(record(6, unowned_timeout())["runs"], int)


def unowned_timeout() -> str:
    return "fields @timestamp, @message | filter @message like /timeout/ | sort @timestamp desc"
