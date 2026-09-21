"""A posture score that can be taken apart, or no score.

FEAT-043 was adopted over an objection, and the objection became the ship
condition: a composite number nobody can decompose tells a reader nothing about
what to do. So the decomposition is not a reporting feature added afterwards, it is
the return type. `score()` cannot return a bare number, because there is no shape
for one.

No database, no clock, no provider. It takes a `Posture` of counted things and
returns a `Score` of components.

Four rules carry this file.

**A component that cannot be computed is not zero.** It is excluded from the
numerator and from the denominator, and it says why. An estate with no bill has no
waste ratio, and scoring that as nought out of forty would report the worst possible
posture for the one estate that has no posture at all. Constraint 5, applied to a
number rather than to a failure.

**An estate nobody has looked at has no score.** Not one hundred. That is the output
a naive implementation produces on its first day, and it is the worst thing this
feature could say.

**Nothing to respond to is not credit for responding.** An estate with no findings
has no responsiveness component, rather than full marks for a queue that does not
exist.

**Inconclusive verification counts neither way.** A change whose effect the bill
cannot settle is excluded from that component's denominator, which is the same
treatment `realized.py` gives it and for the same reason.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from finops_core.domain.waste import Lifecycle
from finops_query.realized import Verdict

#: The share of monthly spend identified as avoidable at which the waste component
#: scores nothing. Twenty percent: an estate where a fifth of the bill is known
#: waste has a posture problem no other component should be able to mask.
WASTE_CEILING = Decimal("0.20")

#: How much each component can contribute. They sum to one hundred, but the total is
#: scaled to the components that could actually be computed, so this is a set of
#: relative weights rather than a budget.
WEIGHT_WASTE = 40
WEIGHT_COVERAGE = 20
WEIGHT_RESPONSIVENESS = 25
WEIGHT_VERIFICATION = 15

#: The whole weight, when every component is computable.
WEIGHT_TOTAL = WEIGHT_WASTE + WEIGHT_COVERAGE + WEIGHT_RESPONSIVENESS + WEIGHT_VERIFICATION

#: What an owned but untouched finding is worth against one being worked on.
#: Somebody's name on it is worth something and is not worth the same as progress.
OWNED_CREDIT = Decimal("0.5")

#: The lifecycles that count as work in progress for the responsiveness component.
MOVING = frozenset({Lifecycle.ACCEPTED, Lifecycle.IN_PROGRESS, Lifecycle.DONE})

#: The lifecycles that are still somebody's problem. VERIFIED, REGRESSED and
#: DISMISSED are closed, and a closed finding neither costs money nor waits.
OPEN_STATES = frozenset({Lifecycle.OPEN, Lifecycle.ACCEPTED, Lifecycle.IN_PROGRESS, Lifecycle.DONE})


@dataclass(frozen=True)
class Finding:
    """One open recommendation, as the score needs to see it."""

    recommendation_id: str
    monthly_saving: Decimal
    lifecycle: Lifecycle
    owner: str | None
    opened_on: date


@dataclass(frozen=True)
class Verification:
    """One completed recommendation and what the bill said about it."""

    recommendation_id: str
    verdict: Verdict


@dataclass(frozen=True)
class Posture:
    """Everything the score is computed from, and nothing it is not.

    `subjects_judged` against `subjects_in_scope` is the honest counterweight to an
    empty findings list. An estate where nothing could be measured has not earned a
    good score by having no findings.

    `subject_unit` names what is being counted, and it is a field rather than a
    constant because the caller decides. A coverage figure whose unit is implied has
    been the defect four times in this product; see `tasks/lessons.md`. The collector
    counts accounts, because which individual resources a waste collector managed to
    observe is not recorded anywhere. ISS-192.
    """

    monthly_spend: Decimal
    findings: Sequence[Finding]
    verifications: Sequence[Verification]
    subjects_judged: int
    subjects_in_scope: int
    subject_unit: str = "resources"


@dataclass(frozen=True)
class Component:
    """One part of the score, with the findings that produced it.

    `points` of None means this part could not be computed. It is not a zero, it is
    excluded, and `why` says what was missing.
    """

    name: str
    points: Decimal | None
    weight: int
    why: str
    #: The recommendations that moved this component, so a reader can go and look at
    #: them. Empty where the component is about what is absent rather than present.
    findings: tuple[str, ...] = ()

    @property
    def is_available(self) -> bool:
        return self.points is not None


@dataclass(frozen=True)
class Score:
    """A number that can be taken apart, which is the only kind this ships."""

    total: int
    components: tuple[Component, ...]
    why: str

    @property
    def available_weight(self) -> int:
        return sum(part.weight for part in self.components if part.is_available)


def _percent(value: Decimal) -> str:
    return f"{value * 100:.1f} percent"


def _open(findings: Sequence[Finding]) -> tuple[Finding, ...]:
    return tuple(finding for finding in findings if finding.lifecycle in OPEN_STATES)


def _waste(posture: Posture) -> Component:
    """How much of the bill is known to be avoidable.

    Linear from full marks at nothing identified to no marks at `WASTE_CEILING`.
    Linear rather than stepped because a threshold makes a score jump on a dollar,
    and a score that jumps is one nobody trusts the next morning.
    """
    findings = _open(posture.findings)
    identified = sum((finding.monthly_saving for finding in findings), Decimal("0"))
    if posture.subjects_judged <= 0:
        # The hole this closes: with nothing judged there are no findings, and a
        # ratio of nought against the bill would award full marks for an estate
        # nobody could look at. An absence of findings is only evidence when
        # somebody went looking.
        return Component(
            name="waste",
            points=None,
            weight=WEIGHT_WASTE,
            why=(
                f"None of the {posture.subjects_in_scope} {posture.subject_unit} in scope "
                f"could be judged, so finding no waste is not evidence that there is "
                f"none. Excluded rather than scored as clean"
            ),
        )
    if posture.monthly_spend <= 0:
        return Component(
            name="waste",
            points=None,
            weight=WEIGHT_WASTE,
            why=(
                "No spend in scope, so there is no bill for the identified saving to be "
                "a share of. Excluded rather than scored, because nought out of forty "
                "would report the worst posture for an estate that has no posture"
            ),
            findings=tuple(finding.recommendation_id for finding in findings),
        )

    ratio = identified / posture.monthly_spend
    kept = max(Decimal("0"), Decimal("1") - ratio / WASTE_CEILING)
    return Component(
        name="waste",
        points=kept * WEIGHT_WASTE,
        weight=WEIGHT_WASTE,
        why=(
            f"{identified.quantize(Decimal('0.01'))} of identified monthly saving against "
            f"{posture.monthly_spend.quantize(Decimal('0.01'))} of spend, "
            f"{_percent(ratio)}, against a ceiling of {_percent(WASTE_CEILING)}"
        ),
        findings=tuple(finding.recommendation_id for finding in findings),
    )


def _coverage(posture: Posture) -> Component:
    """How much of the estate could be judged at all.

    The component that stops an unobserved estate scoring well. A hundred instances
    publishing no metrics produce no findings, and without this that would look
    exactly like a hundred correctly sized ones.
    """
    if posture.subjects_in_scope <= 0:
        return Component(
            name="coverage",
            points=None,
            weight=WEIGHT_COVERAGE,
            why=f"No {posture.subject_unit} in scope, so there is nothing to have covered",
        )
    if posture.subjects_judged <= 0:
        # Nought out of twenty would be a collection failure rendered as a number,
        # which is constraint 5 with a score in place of a cost. With this excluded
        # too, a wholly unobserved scope has no score at all, which is FEAT-043's
        # stated failure behaviour rather than a bad mark.
        return Component(
            name="coverage",
            points=None,
            weight=WEIGHT_COVERAGE,
            why=(
                f"None of the {posture.subjects_in_scope} {posture.subject_unit} in scope "
                f"could be judged. That is a collection failure rather than a posture "
                f"of nought, so it is excluded and the scope has no score"
            ),
        )
    judged = min(posture.subjects_judged, posture.subjects_in_scope)
    ratio = Decimal(judged) / Decimal(posture.subjects_in_scope)
    return Component(
        name="coverage",
        points=ratio * WEIGHT_COVERAGE,
        weight=WEIGHT_COVERAGE,
        why=(
            f"{judged} of {posture.subjects_in_scope} {posture.subject_unit} had enough "
            f"observation to judge, {_percent(ratio)}. The rest published too little to "
            f"be assessed, which is a gap rather than a pass"
        ),
    )


def _responsiveness(posture: Posture) -> Component:
    """Whether the money identified is being acted on.

    Weighted by money rather than by count, because ten trivial findings being closed
    while the expensive one sits untouched is not responsiveness. ISS-021: an unowned
    finding is never fixed, so an unowned one earns nothing at all.
    """
    findings = _open(posture.findings)
    total = sum((finding.monthly_saving for finding in findings), Decimal("0"))
    if not findings or total <= 0:
        return Component(
            name="responsiveness",
            points=None,
            weight=WEIGHT_RESPONSIVENESS,
            why=(
                "No open findings with money attached, so there is nothing to be "
                "responding to. Excluded rather than awarded, because full marks for a "
                "queue that does not exist is the same mistake as a score of one hundred "
                "for an estate nobody has looked at"
            ),
        )

    earned = Decimal("0")
    stalled: list[str] = []
    for finding in findings:
        if finding.lifecycle in MOVING:
            earned += finding.monthly_saving
        elif finding.owner:
            earned += finding.monthly_saving * OWNED_CREDIT
        else:
            stalled.append(finding.recommendation_id)
    ratio = earned / total
    return Component(
        name="responsiveness",
        points=ratio * WEIGHT_RESPONSIVENESS,
        weight=WEIGHT_RESPONSIVENESS,
        why=(
            f"{_percent(ratio)} of the identified money is owned or in progress. "
            f"{len(stalled)} of {len(findings)} findings are open with no owner, and an "
            f"unowned finding is never fixed"
        ),
        findings=tuple(stalled),
    )


def _verification(posture: Posture) -> Component:
    """Whether the changes this estate makes actually land in the bill.

    Inconclusive verdicts are excluded from the denominator entirely. They say
    nothing either way, and counting them as half of anything would put a number on
    the absence of evidence.
    """
    decided = [
        verification
        for verification in posture.verifications
        if verification.verdict is not Verdict.INCONCLUSIVE
    ]
    inconclusive = len(posture.verifications) - len(decided)
    if not decided:
        return Component(
            name="verification",
            points=None,
            weight=WEIGHT_VERIFICATION,
            why=(
                f"Nothing has been verified either way. {inconclusive} verdicts are "
                f"inconclusive, which says nothing about posture rather than something "
                f"bad about it"
            ),
        )
    regressed = tuple(
        verification.recommendation_id
        for verification in decided
        if verification.verdict is Verdict.REGRESSED
    )
    ratio = Decimal(len(decided) - len(regressed)) / Decimal(len(decided))
    return Component(
        name="verification",
        points=ratio * WEIGHT_VERIFICATION,
        weight=WEIGHT_VERIFICATION,
        why=(
            f"{len(decided) - len(regressed)} of {len(decided)} completed changes were "
            f"confirmed in the bill, {_percent(ratio)}. {inconclusive} more were "
            f"inconclusive and are excluded rather than counted against"
        ),
        findings=regressed,
    )


def score(posture: Posture) -> Score | None:
    """The posture score, or None where there is nothing to score.

    None rather than zero and never one hundred. A scope where no component can be
    computed has not been looked at, and the honest output is the absence of a
    number, which the screen renders as a sentence.
    """
    components = (
        _waste(posture),
        _coverage(posture),
        _responsiveness(posture),
        _verification(posture),
    )
    available = [part for part in components if part.points is not None]
    if not available:
        return None

    earned = sum((part.points for part in available if part.points is not None), Decimal("0"))
    weight = sum(part.weight for part in available)
    total = (earned / weight * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    missing = [part.name for part in components if part.points is None]
    accounted = (
        f" Not computed, and excluded rather than scored as nought: {', '.join(missing)}"
        if missing
        else " Every component was computable"
    )
    return Score(
        total=int(total),
        components=components,
        why=(
            f"{total} out of 100, from {len(available)} of {len(components)} components "
            f"carrying {weight} of {WEIGHT_TOTAL} weight.{accounted}"
        ),
    )


@dataclass(frozen=True)
class Movement:
    """What changed in one component between two runs.

    FEAT-043's ship condition again, at the level of a pair of runs rather than a
    single one: a difference between two scores resolves to findings that opened or
    closed. A total that moved with no list behind it is the opinion with a number on
    it that this feature was adopted against.
    """

    name: str
    was: Decimal | None
    now: Decimal | None
    opened: tuple[str, ...]
    closed: tuple[str, ...]

    @property
    def points_moved(self) -> Decimal | None:
        """How far this component moved, or None where either end is unavailable.

        None rather than a difference against zero, because a component that could
        not be computed last time did not score nought last time.
        """
        if self.was is None or self.now is None:
            return None
        return self.now - self.was


def movement(previous: Score, current: Score) -> tuple[Movement, ...]:
    """Component by component, what moved and which findings moved it.

    Matched on name rather than on position, because a component added between two
    releases would otherwise line up against the wrong one and report every finding
    as both opened and closed.
    """
    before = {part.name: part for part in previous.components}
    moved: list[Movement] = []
    for part in current.components:
        was = before.get(part.name)
        had = set(was.findings) if was else set()
        has = set(part.findings)
        moved.append(
            Movement(
                name=part.name,
                was=was.points if was else None,
                now=part.points,
                opened=tuple(sorted(has - had)),
                closed=tuple(sorted(had - has)),
            )
        )
    return tuple(moved)
