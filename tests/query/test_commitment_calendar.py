"""What ends each month, against the ladder limit. TASK-P14-005, FEAT-088."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from finops_core.domain.commitments import RESERVATION, SAVINGS_PLAN
from finops_query.commitment_calendar import MEASURED, MODELLED, Held, calendar, hourly_value

TODAY = date(2026, 10, 13)


def held(commitment_id: str, ends: date, **overrides: Any) -> Held:
    values: dict[str, Any] = {
        "commitment_id": commitment_id,
        "kind": SAVINGS_PLAN,
        "program": "Compute",
        "ends_at": datetime(ends.year, ends.month, ends.day, tzinfo=UTC),
        "quantity": None,
        "hourly_commitment": Decimal("1"),
        "recurring_hourly": Decimal("1"),
        "upfront_amount": Decimal(0),
        "term_months": 12,
    }
    values.update(overrides)
    return Held(**values)


def reservation(commitment_id: str, ends: date) -> Held:
    return held(
        commitment_id,
        ends,
        kind=RESERVATION,
        program="EC2",
        quantity=2,
        hourly_commitment=None,
        recurring_hourly=Decimal("0.10"),
        upfront_amount=Decimal("876"),
    )


def test_a_reservations_hourly_value_spreads_its_upfront_over_the_term_and_is_modelled() -> None:
    value, basis = hourly_value(reservation("ri-1", date(2027, 1, 1)))
    # Two instances at 0.10 an hour and 876 upfront spread over 12 months of 730 hours.
    assert (value, basis) == (Decimal(2) * (Decimal("0.10") + Decimal("0.1")), MODELLED)
    assert hourly_value(held("sp-1", date(2027, 1, 1))) == (Decimal("1"), MEASURED)


def test_a_month_holding_more_than_the_limit_is_flagged() -> None:
    months, total, basis = calendar(
        [
            held("sp-1", date(2026, 11, 3)),
            held("sp-2", date(2027, 6, 1), hourly_commitment=Decimal(3)),
        ],
        today=TODAY,
        months=12,
        ladder_limit=Decimal("0.0833"),
    )
    assert len(months) == 12 and months[0].month == date(2026, 10, 1)
    november = months[1]
    assert (november.commitments, november.share, november.over_limit) == (
        ("sp-1",),
        Decimal("0.2500"),
        True,
    )
    assert (total, basis) == (Decimal(4), MEASURED)


def test_a_month_in_which_nothing_ends_is_a_measured_nought_and_not_flagged() -> None:
    months, _total, _basis = calendar(
        [held("sp-1", date(2027, 3, 1))], today=TODAY, months=3, ladder_limit=Decimal("0.0833")
    )
    assert [(one.share, one.over_limit) for one in months] == [(Decimal("0.0000"), False)] * 3


def test_an_ended_commitment_is_not_held_and_a_reservation_makes_the_month_modelled() -> None:
    months, total, basis = calendar(
        [held("sp-old", date(2026, 9, 1)), reservation("ri-1", date(2026, 12, 15))],
        today=TODAY,
        months=3,
        ladder_limit=Decimal("0.5"),
    )
    assert basis == MODELLED and total == Decimal("0.4")
    assert months[2].basis == MODELLED and months[2].commitments == ("ri-1",)


def test_with_nothing_held_there_is_no_share_rather_than_a_share_of_nought() -> None:
    months, total, _basis = calendar([], today=TODAY, months=1, ladder_limit=Decimal("0.5"))
    assert (total, months[0].share, months[0].over_limit) == (Decimal(0), None, False)
