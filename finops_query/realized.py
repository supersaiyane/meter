"""Whether the bill actually moved, and whether that movement can be claimed.

No database, no clock, no provider. It takes four numbers and two window pairs and
returns a verdict with its working, which is what lets the rule below be tested
against a list of cases rather than against a seeded estate.

This is the most careful arithmetic in the product, because it is where a FinOps
tool usually starts lying. A resource that cost 100 dollars before and 60 after did
not necessarily save 40. It may simply have been used less. The honest
counterfactual, what that resource would have cost had nothing changed, is
unobservable, and any tool claiming to know it is modelling and calling it
measurement.

So the claim is exactly this: **the amortized cost of the affected resource fell by
this much, and its usage quantity moved by this much over the same window.** Both
numbers are shown, and where the usage fall is large enough to explain the cost
fall on its own, the verdict says so rather than taking credit for it.

Three verdicts, not two, and the third is the one that makes the metric worth
having. `INCONCLUSIVE` is expected to be common. A north star metric that is only
ever green is the vanity metric ISS-029 warns about, and the inconclusive verdicts
are the evidence that this one is not.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum


class Verdict(StrEnum):
    """What the two windows support saying.

    The names are the database's `ck_realized_saving__verdict` values, and the
    lifecycle's `VERIFIED` and `REGRESSED` are deliberately the same two words: a
    recommendation whose saving verified is a recommendation in the `VERIFIED`
    state. There is no `INCONCLUSIVE` lifecycle, because a measurement nobody can
    read either way does not move a recommendation anywhere.
    """

    VERIFIED = "VERIFIED"
    REGRESSED = "REGRESSED"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class Window:
    """One comparison period. Half open, `start` included and `end` excluded."""

    start: date
    end: date


@dataclass(frozen=True)
class Realization:
    """One verdict and the working behind it.

    `monthly_saving` is the cost difference and nothing else. It is not adjusted
    toward a counterfactual, and it is zero on anything but `VERIFIED`, because a
    figure that is only sometimes claimable is a figure somebody will sum over
    every row.
    """

    verdict: Verdict
    monthly_saving: Decimal
    why: str


def _fraction(before: Decimal, after: Decimal) -> Decimal:
    """How much of `before` went away. Negative where it grew."""
    return (before - after) / before


def _money(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"))


def judge(
    *,
    before: Window,
    after: Window,
    cost_before: Decimal,
    cost_after: Decimal,
    usage_before: Decimal | None,
    usage_after: Decimal | None,
) -> Realization:
    """The verdict, from two costs, two usage quantities and the two windows.

    `usage_before` or `usage_after` of None means the billing rows carried no usage
    quantity for this resource, which is unobserved rather than zero. The control is
    then missing and the verdict cannot be `VERIFIED`, per constraint 5: a check
    nobody could run must not read as a check that passed.
    """
    working = (
        f"{before.start} to {before.end} cost {_money(cost_before)}, "
        f"{after.start} to {after.end} cost {_money(cost_after)}"
    )

    if cost_before <= 0:
        # Nothing to fall from. This is not a regression, because no cost was ever
        # there to lose, and it is not a saving either.
        return Realization(
            verdict=Verdict.INCONCLUSIVE,
            monthly_saving=Decimal("0.00"),
            why=(
                f"{working}. The before window billed nothing for this resource, so "
                f"there is no fall to measure. Either the resource was created inside "
                f"the window or its charges are attributed somewhere this cannot see"
            ),
        )

    if cost_after >= cost_before:
        return Realization(
            verdict=Verdict.REGRESSED,
            monthly_saving=Decimal("0.00"),
            why=(
                f"{working}. Cost did not fall, so whatever was done either did not "
                f"take effect or did not persist"
            ),
        )

    saving = _money(cost_before - cost_after)
    cost_fall = _fraction(cost_before, cost_after)

    if usage_before is None or usage_after is None:
        return Realization(
            verdict=Verdict.INCONCLUSIVE,
            monthly_saving=Decimal("0.00"),
            why=(
                f"{working}, a fall of {cost_fall * 100:.1f} percent. The billing rows "
                f"carry no usage quantity for this resource, so there is no control: "
                f"this cannot be told apart from a workload that shrank on its own. "
                f"Unobserved, not zero"
            ),
        )

    usage = f"usage moved from {usage_before} to {usage_after}"

    if usage_before <= 0:
        return Realization(
            verdict=Verdict.INCONCLUSIVE,
            monthly_saving=Decimal("0.00"),
            why=(
                f"{working}, a fall of {cost_fall * 100:.1f} percent, and {usage}. "
                f"The before window recorded no usage, so the fall cannot be compared "
                f"against anything"
            ),
        )

    usage_fall = _fraction(usage_before, usage_after)

    if usage_fall > cost_fall:
        return Realization(
            verdict=Verdict.INCONCLUSIVE,
            monthly_saving=Decimal("0.00"),
            why=(
                f"{working}, a fall of {cost_fall * 100:.1f} percent, and {usage}, "
                f"a fall of {usage_fall * 100:.1f} percent. Usage fell by more than "
                f"cost did, so the unit price went up and the fall is explained by a "
                f"smaller workload rather than by a cheaper one"
            ),
        )

    return Realization(
        verdict=Verdict.VERIFIED,
        monthly_saving=saving,
        why=(
            f"{working}, a fall of {saving} at {cost_fall * 100:.1f} percent, and "
            f"{usage}, a change of {usage_fall * 100:.1f} percent. Cost fell at least "
            f"as fast as usage, so the resource is cheaper per unit of work"
        ),
    )
