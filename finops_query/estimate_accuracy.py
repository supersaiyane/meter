"""An estimate set against the bill, and how close estimates come. TASK-P16-007, FEAT-097.

P16 spec section 5.6. A resource a merged plan created is compared once FEAT-057 has seen it in the
mapped state: its first full billed day after that is skipped, since a resource's first day is
partial, and the next thirty days are the window. The window's list cost, scaled to 730 hours, is
set against the line's monthly estimate; effective cost is kept beside it, since commitments lower
it and the estimate does not know of them. The verdict is read at list, like for like.

Every function here is pure. The bill is measured; the estimate is modelled; both are named so.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from statistics import median
from typing import Final

#: Within this many percent of the estimate, at list, an estimate is right.
WITHIN_PERCENT: Final = Decimal(10)
#: Days from the day a resource is seen to the window's first: that day, then its first full day.
SETTLE_DAYS: Final = 2
WINDOW_DAYS: Final = 30
#: A created resource not seen in its state this long after the merge is not compared.
SEEN_WITHIN_DAYS: Final = 60
#: The hours of the window and of the estimate's month, to scale the one to the other.
WINDOW_HOURS: Final = Decimal(WINDOW_DAYS * 24)
MONTH_HOURS: Final = Decimal(730)


class Verdict(StrEnum):
    """What a comparison found. PENDING is seen and waiting for its window to be billed."""

    PENDING = "PENDING"
    WITHIN = "WITHIN"
    ABOVE = "ABOVE"
    BELOW = "BELOW"
    NOT_COMPARED = "NOT_COMPARED"


#: The verdicts that read a figure; the others carry none.
JUDGED: Final = frozenset({Verdict.WITHIN, Verdict.ABOVE, Verdict.BELOW})


@dataclass(frozen=True)
class Window:
    """Thirty billed days, `start` included and `end` not."""

    start: date
    end: date


@dataclass(frozen=True)
class Billed:
    """A resource's rows in a window: summed list and effective cost, and how many rows had each."""

    rows: int
    listed_rows: int
    list_cost: Decimal
    effective_cost: Decimal


@dataclass(frozen=True)
class Judgement:
    """A verdict, with the measured figures scaled to a month where it read any, or why not."""

    verdict: Verdict
    list_monthly: Decimal | None = None
    effective_monthly: Decimal | None = None
    variance_percent: Decimal | None = None
    reason: str | None = None


@dataclass(frozen=True)
class Accuracy:
    """How close one resource type's estimates came, or every type's under `ALL`."""

    resource_type: str
    compared: int
    within: int
    #: The median of the absolute percentage error, none where nothing was compared.
    median_error_percent: Decimal | None


ALL: Final = "all"


def window_after(seen_at: datetime) -> Window:
    """The thirty days after the first full billed day following when the resource was seen."""
    start = seen_at.date() + timedelta(days=SETTLE_DAYS)
    return Window(start=start, end=start + timedelta(days=WINDOW_DAYS))


def billed_through(window: Window, last_billed: date | None) -> bool:
    """Whether the bill reaches the window's last day."""
    return last_billed is not None and last_billed >= window.end - timedelta(days=1)


def unseen_too_long(merged_seen_at: datetime, now: datetime) -> bool:
    """Whether a created resource has gone unseen too long after its merge to compare."""
    return now - merged_seen_at > timedelta(days=SEEN_WITHIN_DAYS)


def judge(estimate_monthly: Decimal, billed: Billed) -> Judgement:
    """The estimate at list against the window's list cost, scaled to the estimate's month."""
    if billed.rows == 0:
        return Judgement(
            Verdict.NOT_COMPARED,
            reason="the bill holds no row for it in its thirty days, NoData",
        )
    if billed.listed_rows < billed.rows:
        return Judgement(
            Verdict.NOT_COMPARED,
            reason=f"the bill gives a list cost for {billed.listed_rows} of its {billed.rows} rows",
        )
    if estimate_monthly <= 0:
        return Judgement(Verdict.NOT_COMPARED, reason="its estimate was nought")
    list_monthly = billed.list_cost * MONTH_HOURS / WINDOW_HOURS
    effective_monthly = billed.effective_cost * MONTH_HOURS / WINDOW_HOURS
    variance = (list_monthly - estimate_monthly) / estimate_monthly * 100
    if abs(variance) <= WITHIN_PERCENT:
        verdict = Verdict.WITHIN
    else:
        verdict = Verdict.ABOVE if variance > 0 else Verdict.BELOW
    return Judgement(verdict, list_monthly, effective_monthly, variance)


def accuracy(compared: Iterable[tuple[str, Verdict, Decimal | None]]) -> tuple[Accuracy, ...]:
    """Each resource type's accuracy, then every type's together under `ALL`, from the judged
    comparisons alone: pending and not compared ones say nothing about how close an estimate is."""
    by_type: dict[str, list[tuple[Verdict, Decimal]]] = {}
    for resource_type, verdict, variance in compared:
        if verdict in JUDGED and variance is not None:
            by_type.setdefault(resource_type, []).append((verdict, variance))
    every = [one for judged in by_type.values() for one in judged]
    return (
        *(_accuracy(name, judged) for name, judged in sorted(by_type.items())),
        _accuracy(ALL, every),
    )


def _accuracy(resource_type: str, judged: list[tuple[Verdict, Decimal]]) -> Accuracy:
    errors = [abs(variance) for _, variance in judged]
    return Accuracy(
        resource_type=resource_type,
        compared=len(judged),
        within=sum(1 for verdict, _ in judged if verdict is Verdict.WITHIN),
        median_error_percent=Decimal(median(errors)) if errors else None,
    )
