"""The two numbers a recommendation carries, and why they stay two.

Severity answers how much money is at stake. Confidence answers how sure the
estimate is. Most of this file exists to prove that changing one does not change
the other, because a single blended score is the obvious simplification and it
hides exactly the recommendation most worth arguing about.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from finops_core.domain.observation import MINIMUM_HISTORY
from finops_core.domain.waste import (
    ALLOWED,
    Confidence,
    Lifecycle,
    RankedOption,
    RealizedSaving,
    Recommendation,
    ScopedFindings,
    Source,
    WasteClass,
    confidence_of,
)
from finops_core.errors import Throttled

NOW = datetime(2026, 9, 21, 6, 0, tzinfo=UTC)


def a_recommendation(**overrides: object) -> Recommendation:
    fields: dict[str, object] = {
        "as_of": NOW,
        "collected_at": NOW,
        "tenant_id": uuid4(),
        "sub_account_id": "111122223333",
        "source": Source.METER,
        "source_reference": "meter:i-0001:RIGHTSIZE_INSTANCE",
        "waste_class": WasteClass.RIGHTSIZE_INSTANCE,
        "resource_id": "i-0001",
        "region_id": "eu-west-1",
        "estimated_monthly_saving": Decimal("120.00"),
        "severity": "HIGH",
        "observation_days": 30,
        "lifecycle": Lifecycle.OPEN,
        "owner": None,
        "ticket_reference": None,
        "rationale": "p99 of 8 percent against 4 vCPU over 30 days",
    }
    fields.update(overrides)
    return Recommendation(**fields)  # type: ignore[arg-type]


class TestConfidenceCannotSeeTheMoney:
    def test_changing_the_saving_does_not_change_the_confidence(self) -> None:
        """The sharpest assertion in this file.

        A ten thousand dollar finding resting on three weeks of data is not a
        confident one, and a blended score would say it was.
        """
        small = a_recommendation(estimated_monthly_saving=Decimal("1.00"))
        large = a_recommendation(estimated_monthly_saving=Decimal("10000.00"))
        assert small.confidence == large.confidence

    def test_changing_the_days_does_not_change_the_severity(self) -> None:
        # The other direction. Severity arrives already computed from the money,
        # so a longer observation cannot quietly promote a cheap finding.
        brief = a_recommendation(observation_days=MINIMUM_HISTORY)
        long = a_recommendation(observation_days=365)
        assert brief.severity == long.severity
        assert brief.confidence != long.confidence

    @pytest.mark.parametrize(
        ("days", "expected"),
        [
            (14, Confidence.LOW),
            (29, Confidence.LOW),
            (30, Confidence.MEDIUM),
            (90, Confidence.HIGH),
        ],
    )
    def test_confidence_rises_with_observation(self, days: int, expected: Confidence) -> None:
        assert confidence_of(days) == expected


class TestTheFloor:
    def test_under_the_floor_there_is_no_recommendation(self) -> None:
        """Not a low confidence one. A new instance looks exactly like an idle one
        for its first fortnight."""
        with pytest.raises(ValueError, match="floor"):
            a_recommendation(observation_days=MINIMUM_HISTORY - 1)

    def test_the_floor_is_the_one_the_anomaly_detector_uses(self) -> None:
        # Imported, not repeated. Two screens that both say "not enough data"
        # should mean the same thing by it.
        from finops_query import anomaly

        assert anomaly.MINIMUM_HISTORY == MINIMUM_HISTORY

    def test_exactly_the_floor_is_allowed(self) -> None:
        assert a_recommendation(observation_days=MINIMUM_HISTORY).observation_days == 14


class TestWhatItRefuses:
    def test_money_refuses_float(self) -> None:
        with pytest.raises(TypeError, match="Decimal"):
            a_recommendation(estimated_monthly_saving=120.0)

    def test_a_negative_saving_is_not_a_recommendation(self) -> None:
        with pytest.raises(ValueError, match="never negative"):
            a_recommendation(estimated_monthly_saving=Decimal("-1.00"))

    def test_a_recommendation_with_no_working_is_refused(self) -> None:
        # A verdict a reader cannot argue with is one they take on trust, and
        # nobody takes a cost recommendation on trust twice.
        with pytest.raises(ValueError, match="argue"):
            a_recommendation(rationale="")


class TestTheLifecycle:
    def test_verified_is_terminal(self) -> None:
        """A verified saving that later regresses is a new finding, not an edit.

        The old one was true when it was made, and editing it would lose that.
        """
        assert ALLOWED[Lifecycle.VERIFIED] == frozenset()
        done = a_recommendation(lifecycle=Lifecycle.VERIFIED)
        assert not done.may_move_to(Lifecycle.OPEN)

    def test_only_the_verifier_moves_a_done_recommendation(self) -> None:
        done = a_recommendation(lifecycle=Lifecycle.DONE)
        assert done.may_move_to(Lifecycle.VERIFIED)
        assert done.may_move_to(Lifecycle.REGRESSED)
        assert not done.may_move_to(Lifecycle.IN_PROGRESS)

    def test_every_state_is_reachable_from_open(self) -> None:
        # A state nothing can reach is a state the schema allows and the product
        # can never produce, which is worse than not having it.
        reached = {Lifecycle.OPEN}
        frontier = [Lifecycle.OPEN]
        while frontier:
            for target in ALLOWED[frontier.pop()]:
                if target not in reached:
                    reached.add(target)
                    frontier.append(target)
        assert reached == set(Lifecycle)


class TestRealizedSaving:
    def a_saving(self, **overrides: object) -> RealizedSaving:
        fields: dict[str, object] = {
            "as_of": NOW,
            "collected_at": NOW,
            "recommendation_id": uuid4(),
            "tenant_id": uuid4(),
            "window_before_start": date(2026, 6, 1),
            "window_before_end": date(2026, 7, 1),
            "window_after_start": date(2026, 8, 1),
            "window_after_end": date(2026, 9, 1),
            "cost_before": Decimal("100.00"),
            "cost_after": Decimal("60.00"),
            "usage_before": Decimal("1000"),
            "usage_after": Decimal("990"),
            "verdict": "VERIFIED",
            "why": "cost fell 40.00 while usage fell 1 percent",
        }
        fields.update(overrides)
        return RealizedSaving(**fields)  # type: ignore[arg-type]

    def test_it_carries_usage_as_well_as_cost(self) -> None:
        """Without the control, a fall in cost cannot be told apart from a fall in
        use, and the counterfactual is unobservable."""
        saving = self.a_saving()
        assert saving.usage_before > 0
        assert saving.usage_after > 0

    def test_the_realized_figure_is_the_difference(self) -> None:
        assert self.a_saving().realized_monthly_saving == Decimal("40.00")

    def test_money_refuses_float(self) -> None:
        with pytest.raises(TypeError, match="Decimal"):
            self.a_saving(cost_before=100.0)

    def test_a_window_ends_after_it_starts(self) -> None:
        with pytest.raises(ValueError, match="ends after"):
            self.a_saving(window_before_start=date(2026, 7, 1), window_before_end=date(2026, 6, 1))


# --- ranked options and scoped findings, TASK-P9-006 -----------------------------------------


def option(**overrides: object) -> RankedOption:
    fields: dict[str, object] = {
        "rank": 1,
        "instance_type": "m6i.large",
        "performance_risk": Decimal("1.0"),
    }
    fields.update(overrides)
    return RankedOption(**fields)  # type: ignore[arg-type]


class TestRankedOptions:
    def test_a_recommendation_keeps_every_option_with_its_current_type(self) -> None:
        options = (option(), option(rank=2, instance_type="m6g.large"))
        held = a_recommendation(current_instance_type="m5.xlarge", options=options)
        assert held.options == options
        assert held.current_instance_type == "m5.xlarge"

    def test_two_options_sharing_a_rank_are_refused(self) -> None:
        with pytest.raises(ValueError, match="share a rank"):
            a_recommendation(options=(option(), option(instance_type="m5.large")))

    @pytest.mark.parametrize(
        ("overrides", "says"),
        [
            ({"rank": 0}, "not ranked"),
            ({"instance_type": ""}, "names the type"),
            ({"performance_risk": Decimal("4.5")}, "off the scale"),
            ({"performance_risk": Decimal("-0.1")}, "off the scale"),
        ],
    )
    def test_an_option_that_is_not_one_is_refused(
        self, overrides: dict[str, object], says: str
    ) -> None:
        with pytest.raises(ValueError, match=says):
            option(**overrides)

    def test_a_provider_saving_may_be_absent_or_negative(self) -> None:
        # An option to a larger type costs more, and its figure says so.
        assert option(provider_monthly_saving=Decimal("-40")).provider_monthly_saving == -40
        assert option().provider_monthly_saving is None


class TestScopedFindings:
    def test_it_iterates_as_its_findings_and_keeps_its_refusals(self) -> None:
        found = a_recommendation()
        refusal = Throttled(scope_key="444455556666:eu-west-1", collector="recommendations")
        scoped = ScopedFindings(
            found=(found,), read=frozenset({("111122223333", "eu-west-1")}), refused=(refusal,)
        )
        assert tuple(scoped) == (found,)
        assert scoped.refused == (refusal,)
