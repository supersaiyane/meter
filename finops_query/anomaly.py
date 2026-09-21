"""Whether a day is out of keeping with the days before it.

No database, no clock, no provider. It takes a list of numbers and returns a
verdict, which is what makes it testable at a boundary rather than against a
fixture.

Three decisions carry this file, and each is here because the obvious
alternative fails quietly.

**A median, not a mean.** One spike inside the baseline window drags a mean up
far enough to hide the next spike. That is the failure that matters for a
detector nobody is watching: the first anomaly is reported, and then the
detector goes blind for exactly as long as the window is wide. A median does not
move when one of fourteen numbers doubles.

**A dollar floor, not only a ratio.** A service costing two cents that triples
is not news. ADR-0016 says severity comes from the money, and a detector that
ranks by ratio fills the top of the screen with rounding.

**A refusal, not a cautious guess.** Fewer than `MINIMUM_HISTORY` days produces
no verdict at all. A new account looks exactly like an anomaly on its first day,
and a detector that reports it teaches the reader to ignore the screen.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from statistics import median

from finops_core.domain.observation import MINIMUM_HISTORY as _MINIMUM_HISTORY

#: Days of history a pair needs before any verdict is given.
#:
#: Imported rather than defined, since 2026-09-21. It used to be a literal here
#: with a comment saying it matched the rule P3 would use, which is a comment that
#: goes stale silently the first time somebody changes one of the two. The domain
#: owns it now and both features read the same number.
MINIMUM_HISTORY = _MINIMUM_HISTORY

#: How far from the baseline a day must sit, in multiples of the median
#: absolute deviation, before it is called out. Three is conventional and is not
#: load bearing: it is a starting point a real estate will move, which is why it
#: arrives as an argument rather than living here as a constant nobody can
#: change without a release.
DEFAULT_SENSITIVITY = Decimal("3.0")

#: The smallest dollar move worth a row, before sensitivity is considered at
#: all. Below this the ratio does not matter.
DEFAULT_FLOOR = Decimal("5.00")

#: A deviation of zero happens whenever a baseline is perfectly flat, which a
#: fake estate produces and a real one sometimes does. Dividing by it is the
#: crash, and treating every departure from it as infinitely anomalous is the
#: wrong answer that looks like a right one. A flat baseline falls back to the
#: dollar floor alone, and the verdict says so.
FLAT = Decimal("0")


@dataclass(frozen=True)
class Verdict:
    """What the detector concluded about one day.

    `is_anomaly` false with a `reason` set is a deliberate shape: a caller often
    wants to know that a pair was judged and cleared, which is a different fact
    from a pair that was never judged at all.
    """

    is_anomaly: bool
    observed: Decimal
    baseline: Decimal
    delta: Decimal
    #: How many multiples of the deviation the day sits from the baseline. None
    #: when the baseline was flat, because the question has no answer then.
    deviations: Decimal | None
    reason: str


def _median_absolute_deviation(values: Sequence[Decimal], centre: Decimal) -> Decimal:
    """The median of the distances from the centre.

    Used instead of a standard deviation for the same reason the centre is a
    median: it does not move when one value in the window is extreme.
    """
    return Decimal(str(median([abs(value - centre) for value in values])))


def judge(
    observed: Decimal,
    history: Sequence[Decimal],
    *,
    sensitivity: Decimal = DEFAULT_SENSITIVITY,
    floor: Decimal = DEFAULT_FLOOR,
) -> Verdict | None:
    """Judge one day against its own past, or refuse to.

    Returns None when there is not enough history. That is not a verdict of "no
    anomaly", and a caller must keep the two apart: one is an estate that is
    behaving, the other is an estate nobody can say anything about yet.

    `history` is the days before the one being judged and must not include it.
    Including it drags the baseline toward the value being tested, which makes a
    detector least sensitive exactly when the move is largest.
    """
    if len(history) < MINIMUM_HISTORY:
        return None

    centre = Decimal(str(median(history)))
    delta = observed - centre
    spread = _median_absolute_deviation(history, centre)

    if delta <= floor:
        # Under the floor, or cheaper than usual. A fall is not nothing, but it
        # is not this screen's business: an estate that got cheaper does not
        # need anybody woken up, and reporting it beside real increases is how
        # a reader learns to skim the page.
        return Verdict(
            is_anomaly=False,
            observed=observed,
            baseline=centre,
            delta=delta,
            deviations=None if spread == FLAT else (delta / spread),
            reason=(
                f"{delta:+.2f} against a usual {centre:.2f}, which is inside the {floor:.2f} floor"
            ),
        )

    if spread == FLAT:
        # A perfectly steady baseline. Every departure is infinitely many
        # deviations, which is arithmetically true and useless, so the floor is
        # the whole test here and the verdict says so rather than reporting a
        # confidence it does not have.
        return Verdict(
            is_anomaly=True,
            observed=observed,
            baseline=centre,
            delta=delta,
            deviations=None,
            reason=(
                f"{delta:+.2f} against a steady {centre:.2f}, a baseline that "
                f"had not moved in {len(history)} days"
            ),
        )

    deviations = delta / spread
    if deviations < sensitivity:
        return Verdict(
            is_anomaly=False,
            observed=observed,
            baseline=centre,
            delta=delta,
            deviations=deviations,
            reason=f"{deviations:.1f} deviations, under the {sensitivity:.1f} threshold",
        )

    return Verdict(
        is_anomaly=True,
        observed=observed,
        baseline=centre,
        delta=delta,
        deviations=deviations,
        reason=(
            f"{delta:+.2f} against a usual {centre:.2f}, which is {deviations:.1f} deviations out"
        ),
    )
