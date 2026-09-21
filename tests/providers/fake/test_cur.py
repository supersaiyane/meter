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

from datetime import date, timedelta
from decimal import Decimal

import pytest

from finops_core import errors
from finops_core.domain.cost import CostRecord
from finops_fakes import cur, fixtures, prices, utilization
from finops_fakes.cur import (
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
        # Compared as daily totals rather than as rows. Since 2026-09-21 the bill
        # names every resource the utilization estate runs, so one account and one
        # service on one day is several lines, and the detector reads their sum. A
        # row count here would have asserted the old one line per service shape and
        # would fail the day the estate grew a fifth instance.
        by_day: dict[object, Decimal] = {}
        for row in pair:
            day = row.charge_period_start.date()
            by_day[day] = by_day.get(day, Decimal("0")) + row.effective_cost
        assert wrong_day in by_day
        normal = [total for day, total in by_day.items() if day != wrong_day]
        assert normal
        assert by_day[wrong_day] > max(normal) * 4

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


class TestTheBillAndTheEstateJoin:
    """`DATA_DICTIONARY.md` decision 6, closed and kept closed.

    Until 2026-09-21 the bill named `{service}/{account}/0001` for two services and
    nothing else, so of the utilization estate's 36 resources exactly two per account
    appeared on it. Every consumer that joins a charge to a resource found nothing for
    the rest: FEAT-029 could not measure what a completed recommendation did to the
    bill, and TASK-P3-013 worked around it by seeding three resources of its own with
    hand written charges.

    Asserted in both directions and derived from the estate, so a resource added to
    one and not the other fails here rather than producing a screen with a charge
    nobody can attribute or a recommendation nobody can price.
    """

    def test_every_estate_resource_is_on_the_bill(self) -> None:
        billed = {row.resource_id for row in cur.ESTATE if row.resource_id}
        missing = {spec.resource_id for spec in utilization.SPECS} - billed
        assert not missing, (
            f"these resources exist in the estate and have no charge, so nothing can "
            f"measure what changing them saved: {sorted(missing)}"
        )

    def test_every_billed_resource_is_in_the_estate(self) -> None:
        # The other direction, and a different bug. A charge against a resource the
        # estate does not model is spend a screen shows and nothing explains, which is
        # worse than a gap because it looks like data.
        billed = {row.resource_id for row in cur.ESTATE if row.resource_id}
        invented = billed - {spec.resource_id for spec in utilization.SPECS}
        assert not invented, f"billed and not modelled: {sorted(invented)}"

    def test_a_resource_is_priced_from_its_own_configuration(self) -> None:
        """Two resources of the same kind and different sizes cost different amounts.

        A bill that charged every volume the same would join correctly and rank
        uselessly, and the ranking is what the screens are for.
        """
        volumes = [spec for spec in utilization.SPECS if spec.kind == "volume"]
        assert len(volumes) > 1
        assert len({prices.monthly_usd(spec) for spec in volumes}) > 1

    def test_the_aggregate_services_still_bill_without_a_resource(self) -> None:
        # S3 and Lambda name no resource, here or in a real bill at this granularity.
        # A row with no `resource_id` is a fact about the bill rather than a gap in it,
        # and the allocation screen has to render it as one.
        aggregate = {row.service_name for row in cur.ESTATE if row.resource_id is None}
        assert aggregate == set(cur.AGGREGATE_SERVICES)


class TestAChangeThatLanded:
    """The three verdicts come out of the bill rather than out of a fixture.

    Each entry in `cur.LANDED` moves a resource's cost and its usage by different
    amounts from one day onward, and `finops_query.realized` reaches a different
    verdict for each. Nothing writes the verdicts down: this asserts the charges
    support them, which is what makes the savings screen a measurement.
    """

    def windows(self) -> tuple[date, date, date, date]:
        landed = cur.landed_on()
        return (
            landed - timedelta(days=30),
            landed,
            landed + timedelta(days=30),
            landed + timedelta(days=60),
        )

    def totals(self, resource: str, start: date, end: date) -> tuple[Decimal, Decimal]:
        rows = [
            row
            for row in cur.estate(periods=5)
            if row.resource_id == resource and start <= row.charge_period_start.date() < end
        ]
        cost = sum((row.effective_cost for row in rows), Decimal("0"))
        usage = sum((row.consumed_quantity or Decimal("0") for row in rows), Decimal("0"))
        return cost, usage

    def test_every_landed_change_has_a_full_window_either_side(self) -> None:
        # Without both windows the collector has nothing to compare and every verdict
        # would be inconclusive for a reason that is the fixture's fault.
        b_start, b_end, a_start, a_end = self.windows()
        for change in cur.LANDED:
            before_cost, _ = self.totals(change.resource_id, b_start, b_end)
            after_rows = self.totals(change.resource_id, a_start, a_end)
            assert before_cost > 0, change.resource_id
            assert after_rows[0] >= 0, change.resource_id

    def test_the_three_changes_produce_three_different_verdicts(self) -> None:
        from finops_query.realized import Window, judge

        b_start, b_end, a_start, a_end = self.windows()
        verdicts = set()
        for change in cur.LANDED:
            cost_before, usage_before = self.totals(change.resource_id, b_start, b_end)
            cost_after, usage_after = self.totals(change.resource_id, a_start, a_end)
            verdicts.add(
                judge(
                    before=Window(start=b_start, end=b_end),
                    after=Window(start=a_start, end=a_end),
                    cost_before=cost_before,
                    cost_after=cost_after,
                    usage_before=usage_before,
                    usage_after=usage_after,
                ).verdict.value
            )
        assert verdicts == {"VERIFIED", "REGRESSED", "INCONCLUSIVE"}, verdicts

    def test_a_resource_nobody_changed_bills_the_same_either_side(self) -> None:
        """The control. If the drift alone moved a cost enough to change a verdict,
        every one of these would be a verdict about the fixture's slope."""
        b_start, b_end, a_start, a_end = self.windows()
        untouched = "amazonrds/fake-platform-a/0001"
        assert untouched not in {change.resource_id for change in cur.LANDED}
        before, _ = self.totals(untouched, b_start, b_end)
        after, _ = self.totals(untouched, a_start, a_end)
        # The drift rises, so after is a little above before and nowhere near a fall.
        assert after > before
        assert after < before * Decimal("1.2")
