"""The fake's commitments, asked about at clocks other than the one it was born at.

The contract suite holds both adapters to one sentence, but it builds its providers at
a single fixed clock and cannot ask them about another month. This file exists for the
bug that fact hid.

`FakeCommitmentReport` sized its commitments from `cur.ESTATE`, the module level
constant built at `fixtures.AS_OF`, whose periods are June to August 2026. Every test
asked about August, so every test passed. Then a demo seeded on 2026-09-20 asked about
September, the estate held no September charges, and all four commitments reported a
committed, used and wasted of zero. Nothing raised: the screen showed an estate that
had committed nothing, which reads as data rather than as a fault, and that is the
worst way for a fixture to be wrong.

So the questions here are all the same question at different clocks.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from finops_core.domain.cost import ACTIVE, QUEUED
from finops_providers.fake import fixtures
from finops_providers.fake.commitment import FakeCommitmentReport, coverages, uses

#: Three clocks, none of them the one the module level estate was built at, and one of
#: them in a different year. A fake that only works at its own birthday is a fake that
#: will be wrong on the day somebody demonstrates the product.
CLOCKS = [
    datetime(2026, 9, 20, 6, 0, tzinfo=UTC),
    datetime(2026, 12, 3, 9, 30, tzinfo=UTC),
    datetime(2027, 4, 11, 18, 0, tzinfo=UTC),
]


def window_of(at: datetime) -> tuple[date, date]:
    """The whole month containing `at`, exclusive end, as the collector computes it."""
    start = date(at.year, at.month, 1)
    end = date(start.year + start.month // 12, start.month % 12 + 1, 1)
    return start, end


class TestItIsSizedAtTheClockItWasAsked:
    @pytest.mark.parametrize("at", CLOCKS)
    def test_an_active_commitment_obliges_real_money(self, at: datetime) -> None:
        """The regression. Four commitments obliging zero is the failure it replaces.

        Asserted per clock rather than once, because the bug was invisible at exactly
        one clock and present at every other.
        """
        start, end = window_of(at)
        active = [use for use in uses(start, end, at=at) if use.status == ACTIVE]
        assert active
        for use in active:
            assert use.committed > Decimal("0"), f"{use.commitment_id} obliged nothing at {at}"

    @pytest.mark.parametrize("at", CLOCKS)
    def test_something_was_eligible_for_a_commitment(self, at: datetime) -> None:
        start, end = window_of(at)
        found = coverages(start, end, at=at)
        assert found
        assert any(slice_.eligible_spend > Decimal("0") for slice_ in found)

    @pytest.mark.parametrize("at", CLOCKS)
    def test_the_over_bought_reservation_still_wastes_money(self, at: datetime) -> None:
        # The one row the screen exists to show. A demo where nothing is wasted
        # demonstrates nothing.
        start, end = window_of(at)
        rds = next(use for use in uses(start, end, at=at) if use.commitment_id == "fake-ri-rds")
        assert rds.wasted > Decimal("0")

    @pytest.mark.parametrize("at", CLOCKS)
    def test_the_queued_commitment_is_the_only_one_obliging_nothing(self, at: datetime) -> None:
        # Otherwise a zero everywhere would satisfy the tests above by accident, since
        # the queued row is legitimately zero.
        start, end = window_of(at)
        nothing = [use for use in uses(start, end, at=at) if use.committed == Decimal("0")]
        assert [use.status for use in nothing] == [QUEUED]


class TestItStillRelatesToTheBill:
    @pytest.mark.parametrize("at", CLOCKS)
    def test_coverage_never_exceeds_what_the_estate_billed(self, at: datetime) -> None:
        """The property that makes the fake worth having.

        Its figures are summed from the same rows the cost screens read, so a coverage
        percentage on the commitments screen and a service total on the spend screen
        are two views of one number rather than two numbers that happen to be close.
        """
        start, end = window_of(at)
        for slice_ in coverages(start, end, at=at):
            assert slice_.covered_spend <= slice_.eligible_spend

    def test_the_default_clock_still_answers_for_its_own_month(self) -> None:
        # The case every other test used to rely on, kept so the fix cannot be a swap
        # of one pinned month for another.
        start, end = window_of(fixtures.AS_OF)
        report = FakeCommitmentReport()
        active = [use for use in report.utilization(start, end) if use.status == ACTIVE]
        assert active
        assert all(use.committed > Decimal("0") for use in active)
