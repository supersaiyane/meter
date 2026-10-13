"""What ends in each coming month, against the tenant's ladder limit. FEAT-088, TASK-P14-005.

P14 spec sections 5.4 and 8. A commitment that ends unnoticed puts its usage back on demand the next
day, and a month in which much of the estate's commitment ends at once is a cliff. The calendar
groups what is held by the month it ends in and says what share of the organization's hourly
commitment that is, flagging a month above the ladder limit.

**A share needs one unit, and only a Savings Plan states one.** A Savings Plan commits an amount an
hour, measured. A reservation buys instances, so its hourly value is modelled: its count times its
recurring hourly charge and its upfront price spread over the term's hours, 730 a month, AWS's own
convention, on the assumption that both prices are per instance. A month whose share includes a
reservation says modelled.

**Twelve months, every one present.** A month in which nothing ends is a row with a share of nought,
because that is a measurement: the inventory was read and nothing in it ends that month.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Final

from finops_core.domain.commitments import SAVINGS_PLAN

#: The hours AWS bills a month by, for spreading a reservation's upfront price over its term.
HOURS_A_MONTH: Final = 730
#: Four places of a fraction: a share to a hundredth of a percent.
SHARE_PLACES: Final = Decimal("0.0001")
MEASURED: Final = "measured"
MODELLED: Final = "modelled"


@dataclass(frozen=True, kw_only=True)
class Held:
    """What the calendar needs of one commitment in the inventory."""

    commitment_id: str
    kind: str
    program: str
    ends_at: datetime
    quantity: int | None
    hourly_commitment: Decimal | None
    recurring_hourly: Decimal
    upfront_amount: Decimal
    term_months: int


@dataclass(frozen=True, kw_only=True)
class CalendarMonth:
    month: date
    commitments: tuple[str, ...]
    hourly_value: Decimal
    share: Decimal | None
    basis: str
    over_limit: bool


def hourly_value(held: Held) -> tuple[Decimal, str]:
    """What a commitment is worth an hour, and how that was arrived at."""
    if held.kind == SAVINGS_PLAN and held.hourly_commitment is not None:
        return held.hourly_commitment, MEASURED
    count = Decimal(held.quantity or 0)
    spread = held.upfront_amount / Decimal(held.term_months * HOURS_A_MONTH)
    return count * (held.recurring_hourly + spread), MODELLED


def _first_of(value: date) -> date:
    return date(value.year, value.month, 1)


def _add_months(first: date, count: int) -> date:
    index = first.year * 12 + first.month - 1 + count
    return date(index // 12, index % 12 + 1, 1)


def calendar(
    held: Iterable[Held], *, today: date, months: int, ladder_limit: Decimal
) -> tuple[list[CalendarMonth], Decimal, str]:
    """Each of the next `months` months from today's, and the total hourly value held now."""
    active = [one for one in held if one.ends_at.date() >= today]
    valued = [(one, *hourly_value(one)) for one in active]
    total = sum((value for _one, value, _basis in valued), Decimal(0))
    total_basis = MODELLED if any(basis == MODELLED for *_, basis in valued) else MEASURED
    start = _first_of(today)
    out: list[CalendarMonth] = []
    for offset in range(months):
        first = _add_months(start, offset)
        ending: Sequence[tuple[Held, Decimal, str]] = [
            row for row in valued if _first_of(row[0].ends_at.date()) == first
        ]
        value = sum((row[1] for row in ending), Decimal(0))
        share = (value / total).quantize(SHARE_PLACES) if total > 0 else None
        out.append(
            CalendarMonth(
                month=first,
                commitments=tuple(sorted(row[0].commitment_id for row in ending)),
                hourly_value=value,
                share=share,
                basis=MODELLED if any(row[2] == MODELLED for row in ending) else MEASURED,
                over_limit=share is not None and share > ladder_limit,
            )
        )
    return out, total, total_basis
