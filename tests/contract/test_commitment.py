"""One sentence about commitments, asked of every adapter that claims to be one.

The value is not that each adapter works. Each has its own suite. It is that the
fake and the real one answer the same way, because the fake is what every test
above this line is written against, and a fake kinder than the provider makes all
of them meaningless at once.

Four sentences matter most.

Utilization and coverage are separate figures at separate grains, and no adapter
may report coverage per commitment. A commitment that expired inside the window is
reported as expired, not dropped. A commitment that has not started has no
utilization at all, rather than a utilization of zero. And money is Decimal, never
float, because a percentage computed from two floats is a percentage that does not
add up on a screen.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal

import pytest

from finops_core.domain.cost import (
    ACTIVE,
    EXPIRED,
    QUEUED,
    CommitmentCoverage,
    CommitmentUse,
)

from .conftest import COMMITMENT_REPORT, ProviderUnderTest

pytestmark = pytest.mark.contract

WINDOW_START = date(2026, 8, 1)
WINDOW_END = date(2026, 9, 1)

STATUSES = frozenset({ACTIVE, EXPIRED, QUEUED})


@pytest.fixture(autouse=True)
def _skip_when_unimplemented(requires_port: Callable[[str], None]) -> None:
    requires_port(COMMITMENT_REPORT)


def _uses(subject: ProviderUnderTest) -> list[CommitmentUse]:
    return list(subject.provider.utilization(WINDOW_START, WINDOW_END))


def _coverages(subject: ProviderUnderTest) -> list[CommitmentCoverage]:
    return list(subject.provider.coverage(WINDOW_START, WINDOW_END))


class TestTheTwoFiguresStaySeparate:
    def test_a_commitment_never_carries_a_coverage_figure(self, subject: ProviderUnderTest) -> None:
        """The sharpest assertion in this file.

        A dollar of covered spend cannot be attributed to one of several
        overlapping plans, so an adapter that put `covered_spend` on a commitment
        would be inventing a number. Asserting the absence is what stops that
        being added later as a convenience.
        """
        for use in _uses(subject):
            assert not hasattr(use, "covered_spend")
            assert not hasattr(use, "coverage")

    def test_coverage_is_reported_per_dimension_and_never_per_commitment(
        self, subject: ProviderUnderTest
    ) -> None:
        found = _coverages(subject)
        assert found
        for slice_ in found:
            assert slice_.dimension in {"SERVICE", "REGION"}
            assert slice_.dimension_value
            assert not hasattr(slice_, "commitment_id")

    def test_one_dimension_value_appears_once_per_commitment_type(
        self, subject: ProviderUnderTest
    ) -> None:
        # Two rows for one service and one commitment type would be summed by a
        # screen, and the same eligible dollar would be counted twice.
        seen = [(s.commitment_type, s.dimension, s.dimension_value) for s in _coverages(subject)]
        assert len(seen) == len(set(seen))


class TestWhatIsReportedAndWhatIsNotDropped:
    def test_a_commitment_that_expired_inside_the_window_is_still_reported(
        self, subject: ProviderUnderTest
    ) -> None:
        """The money was spent, and the gap the expiry leaves is the finding.

        Dropping it would make the estate look like it never had the commitment,
        which is exactly the situation somebody needs to be told about.
        """
        assert any(use.is_expired for use in _uses(subject))

    def test_every_status_is_one_of_the_three(self, subject: ProviderUnderTest) -> None:
        for use in _uses(subject):
            assert use.status in STATUSES

    def test_a_commitment_that_has_not_started_has_no_utilization_rather_than_zero(
        self, subject: ProviderUnderTest
    ) -> None:
        """Zero would say the whole commitment was wasted. It has not started.

        Both adapters must agree here, because the screen renders None as a
        sentence and zero as a red percentage, and those are opposite claims.
        """
        queued = [use for use in _uses(subject) if use.status == QUEUED]
        assert queued, "every adapter's fixture holds a commitment that has not started"
        for use in queued:
            assert use.committed == Decimal("0")
            assert use.utilization is None


class TestTheArithmetic:
    def test_waste_is_the_difference_and_is_never_taken_from_the_provider(
        self, subject: ProviderUnderTest
    ) -> None:
        for use in _uses(subject):
            assert use.wasted == use.committed - use.used

    def test_nothing_is_covered_beyond_what_was_eligible(self, subject: ProviderUnderTest) -> None:
        # Coverage above one renders as more than a hundred percent, which a reader
        # reads as a bug in the screen rather than in the data, and they are right.
        for slice_ in _coverages(subject):
            assert slice_.covered_spend <= slice_.eligible_spend
            if slice_.coverage is not None:
                assert Decimal("0") <= slice_.coverage <= Decimal("1")

    def test_a_service_that_is_eligible_and_uncovered_reports_zero_not_none(
        self, subject: ProviderUnderTest
    ) -> None:
        """Zero says buy. None says there was nothing to buy for.

        Both fixtures hold a service with eligible spend and no commitment against
        it, because that is the row a reader acts on.
        """
        uncovered = [
            slice_
            for slice_ in _coverages(subject)
            if slice_.eligible_spend > Decimal("0") and slice_.covered_spend == Decimal("0")
        ]
        assert uncovered
        for slice_ in uncovered:
            assert slice_.coverage == Decimal("0")

    def test_money_is_decimal_and_never_float(self, subject: ProviderUnderTest) -> None:
        for use in _uses(subject):
            assert isinstance(use.committed, Decimal)
            assert isinstance(use.used, Decimal)
            assert isinstance(use.wasted, Decimal)
        for slice_ in _coverages(subject):
            assert isinstance(slice_.eligible_spend, Decimal)
            assert isinstance(slice_.covered_spend, Decimal)


class TestACommitmentObligesRealMoney:
    """The shape of the bug a seeded database found.

    Four commitments all obliging zero is what a fixture pinned to the wrong month
    looks like, and it renders as an estate that has committed nothing rather than as
    an error. Every figure being zero is the one state that reads as data.

    The clock varying half of this lives in `tests/providers/fake/test_commitment.py`,
    because this harness builds its providers at one fixed clock and cannot ask them
    about another.
    """

    def test_an_active_commitment_obliges_something(self, subject: ProviderUnderTest) -> None:
        active = [use for use in _uses(subject) if use.status == ACTIVE]
        assert active
        assert all(use.committed > Decimal("0") for use in active)

    def test_something_in_the_window_was_eligible(self, subject: ProviderUnderTest) -> None:
        assert any(slice_.eligible_spend > Decimal("0") for slice_ in _coverages(subject))


class TestFreshness:
    def test_every_row_carries_both_timestamps(self, subject: ProviderUnderTest) -> None:
        # Constraint 10. `as_of` is when the figure was true at the source and
        # `collected_at` is when it was fetched, and conflating them makes a month
        # old window look fresh.
        for fact in (*_uses(subject), *_coverages(subject)):
            assert fact.as_of is not None
            assert fact.collected_at is not None
            assert fact.as_of <= fact.collected_at

    def test_every_row_reports_the_window_it_was_asked_for(
        self, subject: ProviderUnderTest
    ) -> None:
        # Two loops rather than one over both lists. `window_start` is on each
        # entity and not on the `Fact` they share, so a combined tuple widens to
        # the base class and the assertion stops being type checked.
        for use in _uses(subject):
            assert use.window_start == WINDOW_START
            assert use.window_end == WINDOW_END
        for slice_ in _coverages(subject):
            assert slice_.window_start == WINDOW_START
            assert slice_.window_end == WINDOW_END
