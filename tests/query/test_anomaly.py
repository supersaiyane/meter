"""The detector, judged on lists.

It has no database and no clock, so every case here is a handful of numbers and
an expected answer. That is the point of keeping the arithmetic in
`finops_query`: the interesting cases are boundaries, and a boundary tested
through a database is a boundary tested through three other things as well.

The cases that matter are the refusals. A detector that reports something on
every estate is a detector nobody reads twice.
"""

from __future__ import annotations

from decimal import Decimal

from finops_query.anomaly import MINIMUM_HISTORY, judge

STEADY = [Decimal("100.00")] * MINIMUM_HISTORY
#: Noisy but unremarkable: a spread of a few dollars around a hundred.
NOISY = [Decimal(str(100 + (index % 5) - 2)) for index in range(MINIMUM_HISTORY)]


class TestItRefusesRatherThanGuesses:
    def test_too_little_history_is_no_verdict_at_all(self) -> None:
        """Not a quiet "no anomaly". A new account looks exactly like a spike on
        its first day, and a detector that reports it teaches the reader to
        ignore the screen."""
        assert judge(Decimal("500.00"), STEADY[: MINIMUM_HISTORY - 1]) is None

    def test_exactly_the_minimum_is_enough(self) -> None:
        assert judge(Decimal("500.00"), STEADY) is not None

    def test_no_history_at_all_is_a_refusal_and_not_a_crash(self) -> None:
        assert judge(Decimal("500.00"), []) is None


class TestTheFloorOutranksTheRatio:
    def test_a_tiny_service_that_triples_is_not_news(self) -> None:
        """ADR-0016: severity comes from the money. A detector that ranks by
        ratio fills the top of the screen with rounding."""
        pennies = [Decimal("0.02")] * MINIMUM_HISTORY
        verdict = judge(Decimal("0.06"), pennies)
        assert verdict is not None
        assert not verdict.is_anomaly
        assert "floor" in verdict.reason

    def test_a_large_move_clears_the_floor(self) -> None:
        verdict = judge(Decimal("400.00"), NOISY)
        assert verdict is not None
        assert verdict.is_anomaly

    def test_a_fall_is_not_reported(self) -> None:
        # An estate that got cheaper does not need anybody woken up, and
        # reporting it beside real increases is how a reader learns to skim.
        verdict = judge(Decimal("10.00"), NOISY)
        assert verdict is not None
        assert not verdict.is_anomaly


class TestTheMedianIsWhatMakesItSurviveTheSecondSpike:
    def test_one_spike_in_the_window_does_not_blind_it(self) -> None:
        """The failure a mean produces, and the whole reason for a median.

        With a mean and a standard deviation, a single 1,000 inside the baseline
        drags the centre up and inflates the spread so far that the next spike
        sits inside the threshold. The detector reports once and then goes blind
        for exactly as long as the window is wide.
        """
        poisoned = [*NOISY[:-1], Decimal("1000.00")]
        verdict = judge(Decimal("400.00"), poisoned)
        assert verdict is not None
        assert verdict.is_anomaly, "one spike in the baseline hid the next one"

    def test_the_baseline_is_the_middle_and_not_the_average(self) -> None:
        poisoned = [*STEADY[:-1], Decimal("1000.00")]
        verdict = judge(Decimal("400.00"), poisoned)
        assert verdict is not None
        assert verdict.baseline == Decimal("100.00")


class TestAFlatBaseline:
    def test_a_steady_estate_still_reports_a_real_jump(self) -> None:
        """Every departure from a flat baseline is infinitely many deviations,
        which is arithmetically true and useless. The floor is the whole test,
        and the verdict says so rather than claiming a confidence it lacks."""
        verdict = judge(Decimal("400.00"), STEADY)
        assert verdict is not None
        assert verdict.is_anomaly
        assert verdict.deviations is None
        assert "had not moved" in verdict.reason

    def test_it_does_not_divide_by_zero(self) -> None:
        assert judge(Decimal("100.50"), STEADY) is not None


class TestTheVerdictCarriesTheNumbers:
    def test_it_says_what_it_was_and_what_was_expected(self) -> None:
        # A percentage alone is not actionable. Somebody has to know the money
        # before they can decide whether to care.
        verdict = judge(Decimal("400.00"), NOISY)
        assert verdict is not None
        assert verdict.observed == Decimal("400.00")
        assert verdict.delta == verdict.observed - verdict.baseline
        assert f"{verdict.delta:+.2f}" in verdict.reason

    def test_a_cleared_pair_still_explains_itself(self) -> None:
        # Judged and cleared is a different fact from never judged, and a caller
        # that wants to show "we looked" needs the reason either way.
        verdict = judge(Decimal("101.00"), NOISY)
        assert verdict is not None
        assert not verdict.is_anomaly
        assert verdict.reason

    def test_sensitivity_is_an_argument_and_not_a_constant(self) -> None:
        """It reaches this module as a parameter so meeting a real estate is a
        change of a number rather than a release."""
        quiet = judge(Decimal("108.00"), NOISY, sensitivity=Decimal("100"), floor=Decimal("1"))
        loud = judge(Decimal("108.00"), NOISY, sensitivity=Decimal("0.5"), floor=Decimal("1"))
        assert quiet is not None and loud is not None
        assert not quiet.is_anomaly
        assert loud.is_anomaly
