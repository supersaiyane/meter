"""The three verdicts, and the cases that decide between them.

The rule this file protects is the one in the P3 spec section 5.5: a cost fall is
only a saving when usage did not fall faster. Every case here is chosen because the
naive implementation, cost before minus cost after, gets it wrong.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from finops_query.realized import Realization, Verdict, Window, judge

BEFORE = Window(start=date(2026, 6, 1), end=date(2026, 7, 1))
AFTER = Window(start=date(2026, 8, 1), end=date(2026, 8, 31))


def verdict_for(
    cost_before: str,
    cost_after: str,
    usage_before: str | None,
    usage_after: str | None,
) -> Realization:
    return judge(
        before=BEFORE,
        after=AFTER,
        cost_before=Decimal(cost_before),
        cost_after=Decimal(cost_after),
        usage_before=None if usage_before is None else Decimal(usage_before),
        usage_after=None if usage_after is None else Decimal(usage_after),
    )


class TestVerified:
    def test_cost_fell_and_usage_held(self) -> None:
        """The clean case. Same work, less money."""
        found = verdict_for("100", "60", "720", "720")
        assert found.verdict is Verdict.VERIFIED
        assert found.monthly_saving == Decimal("40.00")

    def test_cost_fell_and_usage_rose(self) -> None:
        # More work for less money, which is the strongest possible case.
        assert verdict_for("100", "60", "720", "900").verdict is Verdict.VERIFIED

    def test_a_deleted_resource_is_verified_rather_than_inconclusive(self) -> None:
        """Both fell to nothing, and that is a real saving.

        The boundary is strict: usage falling by *more* than cost is
        inconclusive, and an equal fall is not. A deleted idle volume takes its
        usage and its cost to zero together, and calling that unprovable would
        make the metric useless on the one class of finding it is most certain
        about.
        """
        found = verdict_for("30", "0", "30", "0")
        assert found.verdict is Verdict.VERIFIED
        assert found.monthly_saving == Decimal("30.00")

    def test_an_equal_proportional_fall_is_the_boundary(self) -> None:
        # Both down 40 percent exactly. On the verified side of the line, and the
        # test exists so that moving the line is a deliberate act.
        assert verdict_for("100", "60", "1000", "600").verdict is Verdict.VERIFIED


class TestRegressed:
    def test_cost_did_not_move(self) -> None:
        found = verdict_for("100", "100", "720", "720")
        assert found.verdict is Verdict.REGRESSED
        assert found.monthly_saving == Decimal("0.00")

    def test_cost_went_up(self) -> None:
        assert verdict_for("100", "140", "720", "720").verdict is Verdict.REGRESSED

    def test_a_regression_says_which_of_the_two_reasons(self) -> None:
        # Either it never took effect or it did not persist, and the working says
        # both are possible rather than picking one it cannot know.
        why = verdict_for("100", "140", "720", "720").why
        assert "did not take effect" in why
        assert "did not persist" in why


class TestInconclusive:
    def test_usage_fell_faster_than_cost(self) -> None:
        """The case the whole module exists for.

        Cost down 40 percent, usage down 60. The resource got more expensive per
        unit of work, so the bill fell because the workload shrank.
        """
        found = verdict_for("100", "60", "1000", "400")
        assert found.verdict is Verdict.INCONCLUSIVE
        assert found.monthly_saving == Decimal("0.00")
        assert "smaller workload" in found.why

    @pytest.mark.parametrize(
        ("usage_before", "usage_after"),
        [(None, "720"), ("720", None), (None, None)],
    )
    def test_an_unobserved_control_can_never_verify(
        self, usage_before: str | None, usage_after: str | None
    ) -> None:
        """Constraint 5. A check nobody could run is not a check that passed.

        The billing rows carry no usage quantity for some resources, and treating
        that as a usage of zero would make every one of them look like a workload
        that vanished, or worse, like a verified saving.
        """
        found = verdict_for("100", "60", usage_before, usage_after)
        assert found.verdict is Verdict.INCONCLUSIVE
        assert "Unobserved, not zero" in found.why

    def test_nothing_was_billed_before(self) -> None:
        # Not a regression: no cost was ever there to lose.
        found = verdict_for("0", "0", "0", "0")
        assert found.verdict is Verdict.INCONCLUSIVE
        assert "billed nothing" in found.why

    def test_no_usage_before_but_cost_before(self) -> None:
        found = verdict_for("100", "60", "0", "0")
        assert found.verdict is Verdict.INCONCLUSIVE
        assert "recorded no usage" in found.why


def test_only_a_verified_verdict_carries_money() -> None:
    """The invariant that stops a screen summing the wrong rows.

    An inconclusive saving is not a saving, and a figure that is only sometimes
    claimable is a figure somebody will total over every row in the table.
    """
    cases = [
        verdict_for("100", "60", "720", "720"),
        verdict_for("100", "140", "720", "720"),
        verdict_for("100", "60", "1000", "400"),
        verdict_for("100", "60", None, None),
        verdict_for("0", "0", None, None),
    ]
    for found in cases:
        if found.verdict is Verdict.VERIFIED:
            assert found.monthly_saving > 0
        else:
            assert found.monthly_saving == Decimal("0.00")


def test_every_verdict_carries_both_windows_and_both_costs() -> None:
    """The acceptance criterion, asserted over every branch rather than one.

    A verdict a reader cannot argue with is one they take on trust, and nobody
    takes a cost claim on trust twice.
    """
    for found in (
        verdict_for("100", "60", "720", "720"),
        verdict_for("100", "140", "720", "720"),
        verdict_for("100", "60", "1000", "400"),
        verdict_for("100", "60", None, "720"),
        verdict_for("0", "0", "0", "0"),
        verdict_for("100", "60", "0", "0"),
    ):
        assert "2026-06-01" in found.why
        assert "2026-08-31" in found.why
        assert "100.00" in found.why or "0.00" in found.why
