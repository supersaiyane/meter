"""The fake estate's bill.

A fake that is easier than reality is worse than no fake, because every test
above it passes and none of them mean anything. This estate has to contain the
states the cost screens exist to tell apart: more than one service so a ranking
is a ranking, rows nobody tagged so the unallocated bucket is not empty, a part
month so the open period label has something to label, and an account Meter
cannot assume a role into, which still appears on the bill because the bill
comes from the payer.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from finops_core import errors
from finops_core.domain.cost import CostRecord
from finops_providers.fake import cur, fixtures
from finops_providers.fake.cur import (
    CLOSED_PERIOD,
    OPEN_PERIOD,
    RETRACTED_FINGERPRINT,
    FakeCostExport,
)


def rows_in(export: FakeCostExport, period: date) -> list[CostRecord]:
    return list(export.read_period(period, _next_month(period)))


def _next_month(day: date) -> date:
    return date(day.year + (day.month // 12), (day.month % 12) + 1, 1)


class TestTheEstateHasTheStatesAScreenMustTellApart:
    def test_more_than_one_service_so_a_ranking_ranks(self) -> None:
        services = {row.service_name for row in rows_in(FakeCostExport(), CLOSED_PERIOD)}
        assert len(services) > 1

    def test_the_services_do_not_all_cost_the_same(self) -> None:
        # A ranking of identical numbers is a list. The screen's whole claim is
        # that the top row is worth looking at first.
        totals: dict[str, Decimal] = {}
        for row in rows_in(FakeCostExport(), CLOSED_PERIOD):
            totals[row.service_name] = totals.get(row.service_name, Decimal(0)) + row.effective_cost
        assert len(set(totals.values())) == len(totals)

    def test_something_is_untagged_so_the_unallocated_bucket_is_not_empty(self) -> None:
        """Written before the allocation screen exists, on purpose.

        An estate where everything is tagged lets the screen look finished while
        never rendering the row that matters most.
        """
        rows = rows_in(FakeCostExport(), CLOSED_PERIOD)
        assert any(not row.tags for row in rows)
        assert any(row.tags for row in rows)

    def test_some_rows_name_a_resource_and_some_cannot(self) -> None:
        rows = rows_in(FakeCostExport(), CLOSED_PERIOD)
        assert any(row.resource_id for row in rows)
        assert any(row.resource_id is None for row in rows)

    def test_the_account_meter_cannot_read_is_still_on_the_bill(self) -> None:
        """The bill comes from the payer, not from the member account.

        Role health for this account is AccessDenied and always will be, and its
        cost is known anyway. An estate that dropped it would teach every screen
        above it that unreadable and unbilled are the same thing.
        """
        accounts = {row.sub_account_id for row in rows_in(FakeCostExport(), CLOSED_PERIOD)}
        assert fixtures.DENIED_ACCOUNT_KEY.account_id in accounts


class TestTheOpenPeriodIsShorter:
    def test_the_open_period_holds_fewer_days_than_the_closed_one(self) -> None:
        # This is what makes the open period label worth having. A part month
        # rendered beside a whole month with no warning reads as a collapse in
        # spend.
        closed_days = {
            row.charge_period_start.date() for row in rows_in(FakeCostExport(), CLOSED_PERIOD)
        }
        open_days = {
            row.charge_period_start.date() for row in rows_in(FakeCostExport(), OPEN_PERIOD)
        }
        assert open_days
        assert len(open_days) < len(closed_days)

    def test_the_latest_period_is_the_open_one(self) -> None:
        assert FakeCostExport().latest_available_period() == OPEN_PERIOD


class TestRestatement:
    def test_a_restated_period_changes_one_row_and_drops_another(self) -> None:
        before = {row.source_fingerprint: row for row in rows_in(FakeCostExport(), CLOSED_PERIOD)}
        after = {
            row.source_fingerprint: row
            for row in rows_in(FakeCostExport(restated=True), CLOSED_PERIOD)
        }

        assert RETRACTED_FINGERPRINT in before
        assert RETRACTED_FINGERPRINT not in after, "the retracted row is still there"

        changed = [
            key
            for key in before.keys() & after.keys()
            if before[key].effective_cost != after[key].effective_cost
        ]
        assert len(changed) == 1, f"expected exactly one changed row, got {len(changed)}"

    def test_a_restatement_leaves_the_rest_alone(self) -> None:
        # Otherwise TASK-P1-005 cannot tell a retraction from a rewrite.
        before = {row.source_fingerprint for row in rows_in(FakeCostExport(), CLOSED_PERIOD)}
        after = {
            row.source_fingerprint for row in rows_in(FakeCostExport(restated=True), CLOSED_PERIOD)
        }
        assert before - after == {RETRACTED_FINGERPRINT}
        assert not after - before


class TestFailureIsAskedForAndRaised:
    def test_a_planned_failure_is_raised_not_returned(self) -> None:
        export = FakeCostExport(failure=errors.AccessDenied)
        with pytest.raises(errors.AccessDenied):
            export.latest_available_period()
        with pytest.raises(errors.AccessDenied):
            list(export.read_period(CLOSED_PERIOD, OPEN_PERIOD))

    def test_a_period_with_nothing_in_it_raises_no_data(self) -> None:
        """NoData is the one cause a caller may draw as a zero, so it is said
        rather than returned as an empty list that looks like a quiet month."""
        with pytest.raises(errors.NoData):
            list(FakeCostExport().read_period(date(2020, 1, 1), date(2020, 2, 1)))

    def test_an_export_that_has_published_nothing_is_not_an_export_that_is_missing(self) -> None:
        # The port's own distinction. None means the export is there and empty.
        assert FakeCostExport(rows=()).latest_available_period() is None


class TestTheRowsAreNotEasierThanReality:
    def test_every_row_carries_both_timestamps_and_collected_is_not_earlier(self) -> None:
        for row in rows_in(FakeCostExport(), CLOSED_PERIOD):
            assert row.collected_at >= row.as_of

    def test_money_is_decimal_everywhere(self) -> None:
        for row in rows_in(FakeCostExport(), CLOSED_PERIOD):
            assert isinstance(row.effective_cost, Decimal)
            assert isinstance(row.billed_cost, Decimal)

    def test_the_fingerprint_is_the_real_one_and_is_unique_per_row(self) -> None:
        """Not `fake:account`, which is what the four row smoke fixture used.

        The collector keys its upsert on this. A fake with a fingerprint the
        collector would never produce proves the upsert against a shape that
        cannot occur.
        """
        rows = rows_in(FakeCostExport(), CLOSED_PERIOD)
        prints = [row.source_fingerprint for row in rows]
        assert len(set(prints)) == len(prints)
        assert all(len(p) == 64 for p in prints), "expected a sha256 hex digest"

    def test_the_estate_holds_one_day_that_does_not_look_like_the_others(self) -> None:
        """TASK-P1-019. The spike is in the bill, not in the findings table.

        A demo that writes a row straight into `cost_anomaly` shows a finding the
        detector never made, and the first question anybody asks in a demo is whether
        the product found it or somebody typed it.
        """
        wrong_day = cur.spike_day()
        pair = [
            row
            for row in cur.ESTATE
            if row.sub_account_id == cur.SPIKE_ACCOUNT
            and row.service_name == cur.SPIKE_SERVICE
            and row.billing_period_start == cur.OPEN_PERIOD
        ]
        spiked = [row for row in pair if row.charge_period_start.date() == wrong_day]
        normal = [row for row in pair if row.charge_period_start.date() != wrong_day]
        assert len(spiked) == 1
        assert normal
        worst_normal = max(row.effective_cost for row in normal)
        assert spiked[0].effective_cost > worst_normal * 4

    def test_the_spike_is_on_the_last_day_the_estate_bills(self) -> None:
        # Not a fixture convenience. The collector judges the most recent day with
        # data, so a spike anywhere earlier is part of the baseline by the time the
        # detector looks, and a median baseline does not move for one outlier.
        assert cur.spike_day() == max(row.charge_period_start.date() for row in cur.ESTATE)

    def test_an_estate_asked_for_without_a_spike_has_none(self) -> None:
        # The other half of proving the detector works: it has to find nothing in a
        # quiet estate, and that needs a quiet estate to exist.
        quiet = cur.estate(spike=False)
        wrong_day = cur.spike_day()
        pair = [
            row
            for row in quiet
            if row.sub_account_id == cur.SPIKE_ACCOUNT
            and row.service_name == cur.SPIKE_SERVICE
            and row.billing_period_start == cur.OPEN_PERIOD
        ]
        spiked = [row for row in pair if row.charge_period_start.date() == wrong_day]
        others = [row.effective_cost for row in pair if row.charge_period_start.date() != wrong_day]
        assert spiked[0].effective_cost < max(others) * 2

    def test_the_estate_is_the_same_every_time(self) -> None:
        # A fake whose numbers move between runs cannot be asserted against.
        first = [row.effective_cost for row in rows_in(FakeCostExport(), CLOSED_PERIOD)]
        second = [row.effective_cost for row in rows_in(FakeCostExport(), CLOSED_PERIOD)]
        assert first == second
