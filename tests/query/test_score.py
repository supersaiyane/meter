"""The score, and the four ways a posture number normally lies.

FEAT-043's ship condition is that the score decomposes, so most of this file is
about the components rather than the total. The cases that matter are the ones a
naive implementation gets wrong on its first day: a perfect score for an estate
nobody looked at, full marks for an empty queue, a zero for a missing input, and a
total that moves without anybody being able to say which part moved.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from finops_core.domain.waste import Lifecycle
from finops_query.realized import Verdict
from finops_query.score import (
    WEIGHT_COVERAGE,
    WEIGHT_RESPONSIVENESS,
    WEIGHT_TOTAL,
    WEIGHT_WASTE,
    Component,
    Finding,
    Posture,
    Score,
    Verification,
    movement,
    score,
)

OPENED = date(2026, 9, 1)


def finding(
    identifier: str,
    saving: str,
    *,
    lifecycle: Lifecycle = Lifecycle.OPEN,
    owner: str | None = None,
) -> Finding:
    return Finding(
        recommendation_id=identifier,
        monthly_saving=Decimal(saving),
        lifecycle=lifecycle,
        owner=owner,
        opened_on=OPENED,
    )


def posture(
    *,
    spend: str = "10000",
    findings: tuple[Finding, ...] = (),
    verifications: tuple[Verification, ...] = (),
    judged: int = 100,
    in_scope: int = 100,
) -> Posture:
    return Posture(
        monthly_spend=Decimal(spend),
        findings=findings,
        verifications=verifications,
        subjects_judged=judged,
        subjects_in_scope=in_scope,
    )


def component(found: Score, name: str) -> Component:
    return next(part for part in found.components if part.name == name)


class TestWhatItRefusesToSay:
    def test_an_estate_nobody_looked_at_has_no_score(self) -> None:
        """Not one hundred, and not zero either.

        No spend, no resources, no findings, no verifications. Every component is
        uncomputable, so there is no number, and the screen renders that as a
        sentence rather than as a figure.
        """
        assert score(posture(spend="0", judged=0, in_scope=0)) is None

    def test_an_estate_with_a_bill_that_nobody_could_judge_has_no_score_either(self) -> None:
        """The hole a naive implementation leaves open the longest.

        A hundred accounts in scope, a real bill, and not one of them judged. There
        are no findings, so a waste ratio of nought would award full marks, and a
        coverage of nought out of twenty would render a collection failure as a
        number. Both are excluded, so there is no score, which is the only honest
        answer about an estate nobody could look at.
        """
        assert score(posture(spend="10000", judged=0, in_scope=100)) is None

    def test_a_missing_input_is_excluded_rather_than_scored_as_nought(self) -> None:
        """Constraint 5 applied to a number instead of to a failure.

        An estate with resources but no bill has no waste ratio. Scoring that as
        nought out of forty would report the worst posture in the product for the one
        estate that has no posture at all.
        """
        found = score(posture(spend="0", judged=90, in_scope=100))
        assert found is not None
        assert component(found, "waste").points is None
        assert component(found, "waste").weight == WEIGHT_WASTE
        # The denominator shrinks with it, so the total is out of what was actually
        # measurable rather than out of a hundred that includes a gap.
        assert found.available_weight == WEIGHT_COVERAGE
        assert found.total == 90

    def test_an_empty_queue_earns_no_responsiveness_credit(self) -> None:
        # Full marks for responding to nothing is the same mistake as a score of a
        # hundred for an estate nobody has looked at, one component down.
        found = score(posture(findings=()))
        assert found is not None
        assert component(found, "responsiveness").points is None
        assert "queue that does not exist" in component(found, "responsiveness").why

    def test_inconclusive_verification_counts_neither_way(self) -> None:
        """The same treatment `realized.py` gives it, for the same reason.

        Counting an inconclusive verdict as half of anything would put a number on
        the absence of evidence.
        """
        found = score(
            posture(
                verifications=(
                    Verification(recommendation_id="rec-1", verdict=Verdict.INCONCLUSIVE),
                    Verification(recommendation_id="rec-2", verdict=Verdict.INCONCLUSIVE),
                )
            )
        )
        assert found is not None
        assert component(found, "verification").points is None
        assert "says nothing about posture" in component(found, "verification").why

    def test_a_fully_covered_estate_with_no_waste_does_score_well(self) -> None:
        """The other direction, so the refusals above are not simply a refusal to
        score anything.

        An estate that was measured and found clean has earned its number.
        """
        found = score(posture(spend="10000", findings=(), judged=100, in_scope=100))
        assert found is not None
        assert found.total == 100
        assert component(found, "waste").points == WEIGHT_WASTE
        assert component(found, "coverage").points == WEIGHT_COVERAGE

    def test_an_unmeasured_estate_does_not_look_like_a_clean_one(self) -> None:
        """The whole reason coverage is a component.

        A hundred instances publishing no metrics produce no findings, which without
        this would be indistinguishable from a hundred correctly sized ones. Here
        ten were judged out of a hundred, and the score says so.
        """
        clean = score(posture(judged=100, in_scope=100))
        blind = score(posture(judged=10, in_scope=100))
        assert clean is not None
        assert blind is not None
        assert blind.total < clean.total
        assert component(blind, "coverage").points == Decimal("0.1") * WEIGHT_COVERAGE


class TestTheDecomposition:
    def test_a_score_is_never_a_bare_number(self) -> None:
        """FEAT-043's ship condition, asserted on the type.

        There is no shape for a bare number, which is the point: the decomposition
        is the return type rather than a reporting feature added afterwards.
        """
        found = score(posture(findings=(finding("rec-1", "100"),)))
        assert found is not None
        assert {part.name for part in found.components} == {
            "waste",
            "coverage",
            "responsiveness",
            "verification",
        }
        for part in found.components:
            assert part.why, f"{part.name} has no working"

    def test_every_component_names_the_findings_that_produced_it(self) -> None:
        found = score(
            posture(
                findings=(finding("rec-1", "500"), finding("rec-2", "300")),
                verifications=(
                    Verification(recommendation_id="rec-9", verdict=Verdict.REGRESSED),
                    Verification(recommendation_id="rec-8", verdict=Verdict.VERIFIED),
                ),
            )
        )
        assert found is not None
        assert set(component(found, "waste").findings) == {"rec-1", "rec-2"}
        # The stalled ones, because those are the findings costing the points.
        assert set(component(found, "responsiveness").findings) == {"rec-1", "rec-2"}
        assert component(found, "verification").findings == ("rec-9",)

    def test_the_total_is_the_weighted_components_and_nothing_else(self) -> None:
        # A total that did not follow from the parts would make the decomposition
        # decorative, which is exactly what FEAT-043 was adopted against.
        found = score(
            posture(
                findings=(finding("rec-1", "1000", lifecycle=Lifecycle.IN_PROGRESS),),
                verifications=(Verification(recommendation_id="rec-8", verdict=Verdict.VERIFIED),),
                judged=80,
            )
        )
        assert found is not None
        earned = sum(part.points for part in found.components if part.points is not None)
        assert found.total == round(earned / found.available_weight * 100)


class TestMovingOneFinding:
    """The criterion in the plan: change one finding, and say which component moved
    and by how much."""

    def test_adding_money_moves_only_the_waste_component(self) -> None:
        before = score(posture(findings=(finding("rec-1", "500"),)))
        after = score(posture(findings=(finding("rec-1", "500"), finding("rec-2", "500"))))
        assert before is not None
        assert after is not None
        # Waste moved, and by the amount the ratio says: a thousand of identified
        # saving against ten thousand of spend is ten percent, which is half the
        # twenty percent ceiling, so half the forty points survive.
        assert component(before, "waste").points == Decimal("30")
        assert component(after, "waste").points == Decimal("20")
        # Coverage did not, because the estate is as well observed as it was.
        assert component(before, "coverage").points == component(after, "coverage").points

    def test_naming_an_owner_moves_only_responsiveness(self) -> None:
        """And by exactly half the weight, which is what `OWNED_CREDIT` says.

        ISS-021: an unowned finding is never fixed. A name on it is worth something,
        and it is not worth the same as progress.
        """
        unowned = score(posture(findings=(finding("rec-1", "500"),)))
        owned = score(posture(findings=(finding("rec-1", "500", owner="alice"),)))
        assert unowned is not None
        assert owned is not None
        assert component(unowned, "responsiveness").points == Decimal("0")
        assert component(owned, "responsiveness").points == Decimal(WEIGHT_RESPONSIVENESS) / 2
        assert component(unowned, "waste").points == component(owned, "waste").points

    def test_starting_work_is_worth_more_than_naming_somebody(self) -> None:
        owned = score(posture(findings=(finding("rec-1", "500", owner="alice"),)))
        working = score(
            posture(
                findings=(finding("rec-1", "500", owner="alice", lifecycle=Lifecycle.IN_PROGRESS),)
            )
        )
        assert owned is not None
        assert working is not None
        in_progress = component(working, "responsiveness").points
        named = component(owned, "responsiveness").points
        assert in_progress == Decimal(WEIGHT_RESPONSIVENESS)
        # Both are available here, so a None on either side is the test setup having
        # stopped exercising what it claims to.
        assert named is not None
        assert in_progress is not None
        assert in_progress > named

    def test_responsiveness_is_weighted_by_money_not_by_count(self) -> None:
        """Ten trivial findings closed while the expensive one waits is not
        responsiveness, and a count would score it as ninety percent."""
        found = score(
            posture(
                findings=(
                    finding("big", "9000"),
                    *(
                        finding(f"small-{n}", "10", lifecycle=Lifecycle.IN_PROGRESS)
                        for n in range(9)
                    ),
                )
            )
        )
        assert found is not None
        responsiveness = component(found, "responsiveness")
        assert responsiveness.points is not None
        assert responsiveness.points < Decimal(WEIGHT_RESPONSIVENESS) / 10

    def test_a_closed_finding_stops_costing_anything(self) -> None:
        # A dismissed finding is neither money on the bill nor work waiting, so it
        # leaves both components rather than lingering in one.
        open_one = score(posture(findings=(finding("rec-1", "2000"),)))
        dismissed = score(
            posture(findings=(finding("rec-1", "2000", lifecycle=Lifecycle.DISMISSED),))
        )
        assert open_one is not None
        assert dismissed is not None
        assert component(open_one, "waste").points == Decimal("0")
        assert component(dismissed, "waste").points == Decimal(WEIGHT_WASTE)
        assert component(dismissed, "responsiveness").points is None


class TestTheBoundaries:
    def test_waste_at_the_ceiling_scores_nothing_and_does_not_go_negative(self) -> None:
        # Twice the ceiling. A component that went negative would let one bad
        # dimension drag a score below nought, which no reader would believe.
        found = score(posture(spend="1000", findings=(finding("rec-1", "400"),)))
        assert found is not None
        assert component(found, "waste").points == Decimal("0")
        assert found.total >= 0

    def test_coverage_cannot_exceed_the_resources_in_scope(self) -> None:
        # A judged count above the scope count is a counting bug upstream, and it
        # must not produce more than full marks here.
        found = score(posture(judged=200, in_scope=100))
        assert found is not None
        assert component(found, "coverage").points == Decimal(WEIGHT_COVERAGE)

    def test_the_working_says_which_components_were_excluded(self) -> None:
        found = score(posture(spend="0", judged=50, in_scope=100))
        assert found is not None
        assert "waste" in found.why
        assert "responsiveness" in found.why
        assert "verification" in found.why
        assert "excluded rather than scored as nought" in found.why

    def test_every_weight_is_accounted_for(self) -> None:
        """A weight that belonged to no component would silently change every total.

        Checked against the constant rather than against a literal hundred, so
        retuning the weights is a deliberate edit in one place.
        """
        found = score(posture(findings=(finding("rec-1", "100"),)))
        assert found is not None
        assert sum(part.weight for part in found.components) == WEIGHT_TOTAL


class TestWhatMovedBetweenTwoRuns:
    """FEAT-043's condition at the level of a pair of runs.

    A total that moved with no list of findings behind it is the opinion with a
    number on it that this feature was adopted against.
    """

    def test_a_finding_that_closed_is_named(self) -> None:
        before = score(posture(findings=(finding("rec-1", "500"), finding("rec-2", "500"))))
        after = score(posture(findings=(finding("rec-1", "500"),)))
        assert before is not None
        assert after is not None
        waste = next(part for part in movement(before, after) if part.name == "waste")
        assert waste.closed == ("rec-2",)
        assert waste.opened == ()
        assert waste.points_moved == Decimal("10")

    def test_a_finding_that_opened_is_named(self) -> None:
        before = score(posture(findings=(finding("rec-1", "500"),)))
        after = score(posture(findings=(finding("rec-1", "500"), finding("rec-3", "500"))))
        assert before is not None
        assert after is not None
        waste = next(part for part in movement(before, after) if part.name == "waste")
        assert waste.opened == ("rec-3",)
        assert waste.points_moved == Decimal("-10")

    def test_a_component_that_became_computable_reports_no_movement(self) -> None:
        """None rather than a difference against zero.

        A component that could not be computed last time did not score nought last
        time, so the arithmetic that would say it gained forty points is arithmetic
        against a number nobody wrote down.
        """
        before = score(posture(spend="0", judged=100, in_scope=100))
        after = score(posture(spend="10000", judged=100, in_scope=100))
        assert before is not None
        assert after is not None
        waste = next(part for part in movement(before, after) if part.name == "waste")
        assert waste.was is None
        assert waste.now == Decimal(WEIGHT_WASTE)
        assert waste.points_moved is None

    def test_components_are_matched_by_name_rather_than_by_position(self) -> None:
        # A component added between two releases would otherwise line up against the
        # wrong one and report every finding as both opened and closed.
        found = score(posture(findings=(finding("rec-1", "500"),)))
        assert found is not None
        trimmed = Score(
            total=found.total,
            components=tuple(reversed(found.components)),
            why=found.why,
        )
        for part in movement(trimmed, found):
            assert part.opened == ()
            assert part.closed == ()
