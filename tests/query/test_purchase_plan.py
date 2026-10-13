"""Meter's purchase plan, tested without a database. TASK-P14-007, FEAT-089, spec section 9.

A quiet weekend sets the baseline, a day the bill does not hold is not a day of nothing, a family
with no P9 rate is unpriced rather than priced at zero, and the ladder holds the limit given what
already expires. OPEN-40: steady families buy family bound plans, usage that moves buys flexible.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from finops_core.domain.commitments import ALL_UPFRONT, DEFAULT_POLICY, CommitmentPolicy
from finops_query.purchase_plan import (
    FAMILY_BOUND,
    FLEXIBLE,
    Advice,
    Bought,
    Held,
    Plan,
    Rate,
    Seen,
    Usage,
    difference,
    draft,
    match,
    months_after,
    tenth_percentile,
)

START = date(2026, 10, 13)
WINDOW_START = START - timedelta(days=30)
DAYS = tuple(WINDOW_START + timedelta(days=n) for n in range(30))
LATER = date(2027, 6, 1)
#: On demand 0.10 an hour; the flexible rate takes 30 percent off, the family bound one 40.
PRICED = Rate(on_demand=Decimal("0.10"), flexible=Decimal("0.07"), family_bound=Decimal("0.06"))
RATES = {
    ("r1", "m.large"): PRICED,
    ("r1", "c.large"): PRICED,
    ("r2", "m.large"): PRICED,
    ("r1", "x.large"): Rate(on_demand=Decimal("0.10"), flexible=None, family_bound=None),
}
#: Everything bought in the first tranche, so a test of the baseline is not a test of the ladder.
OPEN_LADDER = CommitmentPolicy(
    target_coverage=Decimal("0.8"),
    term_years=1,
    payment_option="No Upfront",
    ladder_limit=Decimal("1"),
)


def day_of(spend: Decimal, day: date, family: str = "m", region: str = "r1") -> Usage:
    return Usage(day=day, region=region, family=family, kind=f"{family}.large", on_demand=spend)


def every_day(hourly: str, family: str = "m", region: str = "r1") -> list[Usage]:
    return [day_of(Decimal(hourly) * 24, day, family, region) for day in DAYS]


def alternating(region: str = "r1") -> list[Usage]:
    """An hour of usage every day, on one family one day and another the next."""
    return [
        day_of(Decimal(24), day, family="m" if index % 2 else "c", region=region)
        for index, day in enumerate(DAYS)
    ]


def plan_of(
    usage: list[Usage],
    *,
    held: tuple[Held, ...] = (),
    days: tuple[date, ...] = DAYS,
    policy: CommitmentPolicy = OPEN_LADDER,
) -> Plan:
    return draft(
        usage=usage,
        rates=RATES,
        held=held,
        days_held=days,
        policy=policy,
        start=START,
        window_start=WINDOW_START,
        window_end=START,
    )


def test_the_tenth_percentile_interpolates_between_ranks() -> None:
    values = [Decimal(n) for n in range(1, 12)]
    assert tenth_percentile(values) == Decimal(2)
    assert tenth_percentile([Decimal(4), Decimal(8)]) == Decimal("4.4")
    assert tenth_percentile([Decimal(7)]) == Decimal(7)
    assert tenth_percentile([]) == Decimal(0)


def test_months_after_crosses_a_year() -> None:
    assert months_after(date(2026, 11, 1), 14) == date(2028, 1, 1)


def test_a_quiet_weekend_sets_the_baseline() -> None:
    usage = [day_of(Decimal(12) if day.weekday() >= 5 else Decimal(24), day) for day in DAYS]
    plan = plan_of(usage)
    # Nine weekend days of 30: the tenth percentile is a weekend's half an hour, not the average.
    assert plan.steady_hourly == Decimal("0.5000")
    assert plan.target_hourly == Decimal("0.2400")


def test_a_day_the_bill_does_not_hold_is_not_a_day_of_nothing() -> None:
    plan = plan_of(every_day("1")[:20], days=DAYS[:20])
    assert plan.days_held == 20
    assert plan.steady_hourly == Decimal("1.0000")


def test_a_held_day_a_kind_did_not_run_is_a_day_of_nothing_for_it() -> None:
    # Gone for four of thirty days the bill holds: the tenth percentile lands on a zero.
    plan = plan_of(every_day("1")[4:])
    assert plan.steady_hourly == Decimal(0)
    assert plan.reason == "No eligible usage ran on every day the bill holds."
    assert plan.lines == ()


def test_too_few_days_held_is_said_and_nothing_is_drafted() -> None:
    plan = plan_of(every_day("1")[:10], days=DAYS[:10])
    assert plan.reason is not None
    assert "holds 10 of the last 30 days" in plan.reason
    assert (plan.lines, plan.steady_hourly) == ((), None)


def test_a_steady_family_buys_a_family_bound_plan() -> None:
    plan = plan_of(every_day("1"))
    (line,) = plan.lines
    assert (line.program, line.family, line.region) == (FAMILY_BOUND, "m", "r1")
    # 80 percent of one an hour on demand, at 40 percent off: 0.48 an hour committed.
    assert line.hourly_commitment == Decimal("0.480")
    assert line.discount_percent == Decimal("40.0000")
    assert line.covers_hourly == Decimal("0.8000")
    assert line.monthly_saving == Decimal("233.60")
    assert line.usage_floor_percent == Decimal("60.0")
    assert line.upfront_cost == Decimal("0.00")
    assert plan.reason is None


def test_usage_that_moves_between_families_buys_a_flexible_plan() -> None:
    plan = plan_of(alternating())
    # Neither family runs every day, but the estate runs one an hour every day.
    (line,) = plan.lines
    assert (line.program, line.family, line.region) == (FLEXIBLE, None, None)
    assert line.discount_percent == Decimal("30.0000")
    assert line.hourly_commitment == Decimal("0.560")


def test_a_family_with_no_rate_is_unpriced_and_named_never_priced_at_zero() -> None:
    plan = plan_of(every_day("1") + every_day("2", family="x"))
    (unpriced,) = plan.unpriced
    assert (unpriced.family, unpriced.region, unpriced.steady_hourly) == ("x", "r1", Decimal("2"))
    assert "no Savings Plans rate" in unpriced.reason
    assert {line.family for line in plan.lines} == {"m"}
    assert plan.steady_hourly == Decimal("3.0000")


def test_moving_usage_with_no_flexible_rate_is_unpriced_too() -> None:
    rates = {
        ("r1", "m.large"): Rate(Decimal("0.10"), None, Decimal("0.06")),
        ("r1", "c.large"): Rate(Decimal("0.10"), None, Decimal("0.06")),
    }
    plan = draft(
        usage=alternating(),
        rates=rates,
        held=(),
        days_held=DAYS,
        policy=OPEN_LADDER,
        start=START,
        window_start=WINDOW_START,
        window_end=START,
    )
    (moving,) = plan.unpriced
    assert (moving.family, moving.region, moving.steady_hourly) == (None, None, Decimal(1))
    assert plan.reason == "No part of the steady baseline has a rate to price it."


def test_nothing_priced_at_all_says_so() -> None:
    plan = plan_of(every_day("2", family="x"))
    assert plan.reason == "No part of the steady baseline has a rate to price it."
    assert plan.lines == ()


def test_a_family_bound_commitment_held_counts_against_its_own_family() -> None:
    usage = every_day("1") + every_day("1", region="r2")
    held = (Held(hourly=Decimal("0.3"), ends=LATER, family="m", region="r1"),)
    plan = plan_of(usage, held=held)
    by_region = {line.region: line.hourly_commitment for line in plan.lines}
    # 0.3 held at 40 percent off covers 0.5 on demand of r1's 0.8 target: 0.3 on demand left.
    assert by_region == {"r1": Decimal("0.180"), "r2": Decimal("0.480")}


def test_what_a_family_holds_beyond_its_target_spills_to_the_flexible_plan() -> None:
    held = (Held(hourly=Decimal("0.6"), ends=LATER, family="m", region="r2"),)
    plan = plan_of(alternating() + every_day("1", region="r2"), held=held)
    # r2 holds 1.0 on demand against a 0.8 target; the 0.2 over reduces the flexible need.
    (line,) = plan.lines
    assert (line.program, line.region, line.hourly_commitment) == (FLEXIBLE, None, Decimal("0.420"))


def test_a_flexible_commitment_held_covers_a_family_when_nothing_moves() -> None:
    held = (Held(hourly=Decimal("0.21"), ends=LATER),)
    (line,) = plan_of(every_day("1"), held=held).lines
    # 0.21 at the flexible 30 percent off covers 0.3 on demand of the family's 0.8 target.
    assert line.hourly_commitment == Decimal("0.300")


def test_a_commitment_ending_within_the_month_does_not_count() -> None:
    soon = Held(hourly=Decimal("0.48"), ends=START + timedelta(days=20), family="m", region="r1")
    later = Held(hourly=Decimal("0.48"), ends=START + timedelta(days=60), family="m", region="r1")
    assert plan_of(every_day("1"), held=(soon,)).target_hourly == Decimal("0.4800")
    covered = plan_of(every_day("1"), held=(later,))
    assert covered.lines == ()
    assert covered.reason is not None and "80 percent" in covered.reason


def test_the_ladder_holds_the_limit_given_what_already_expires() -> None:
    # A year's term bought this month ends in October 2027, when 0.3 of what is held ends too.
    held = (
        Held(hourly=Decimal("0.3"), ends=date(2027, 10, 20)),
        Held(hourly=Decimal("0.3"), ends=date(2028, 3, 20)),
    )
    plan = plan_of(every_day("10"), held=held, policy=DEFAULT_POLICY)
    assert plan.target_hourly is not None and plan.held_hourly is not None
    limit = DEFAULT_POLICY.ladder_limit * (plan.held_hourly + plan.target_hourly)
    bought: dict[date, Decimal] = defaultdict(Decimal)
    for line in plan.lines:
        bought[line.tranche] += line.hourly_commitment
    ending = {date(2027, 10, 1): Decimal("0.3"), date(2028, 3, 1): Decimal("0.3")}
    for tranche, amount in bought.items():
        assert amount + ending.get(months_after(tranche, 12), Decimal(0)) <= limit, tranche
    # The month that already loses 0.3 buys less than the month after it.
    assert bought[date(2026, 10, 1)] < bought[date(2026, 11, 1)]
    assert len(bought) == 12
    assert plan.beyond_hourly is not None and plan.beyond_hourly > 0


def test_a_payer_holding_nothing_still_buys_a_twelfth_a_month() -> None:
    plan = plan_of(every_day("1"), policy=DEFAULT_POLICY)
    first = [line for line in plan.lines if line.tranche == date(2026, 10, 1)]
    assert sum(line.hourly_commitment for line in first) == Decimal("0.039")
    assert {line.tranche for line in plan.lines} == {
        months_after(date(2026, 10, 1), index) for index in range(12)
    }


@pytest.mark.parametrize(
    ("payment", "upfront"),
    [("No Upfront", "0.00"), ("Partial Upfront", "6307.20"), (ALL_UPFRONT, "12614.40")],
)
def test_the_upfront_cost_follows_the_payment_option(payment: str, upfront: str) -> None:
    policy = CommitmentPolicy(
        target_coverage=Decimal("0.8"),
        term_years=3,
        payment_option=payment,
        ladder_limit=Decimal("1"),
    )
    (line,) = plan_of(every_day("1"), policy=policy).lines
    # 0.48 an hour for three years of 8,760 hours.
    assert line.upfront_cost == Decimal(upfront)


def said(plan: Plan, advice: list[Advice]) -> tuple[str, ...]:
    return difference(
        target_coverage=Decimal("0.8"),
        ladder_limit=Decimal("0.0833"),
        days_held=plan.days_held,
        window_days=30,
        lines=plan.lines,
        currency="USD",
        advice=advice,
    )


def test_the_difference_names_the_lookback_the_coverage_and_the_ladder() -> None:
    plan = plan_of(every_day("1") + alternating(region="r2"), policy=DEFAULT_POLICY)
    advice = [
        Advice(FLEXIBLE, 30, Decimal("0.9"), failed=False),
        Advice(FAMILY_BOUND, 30, None, failed=False),
    ]
    lookback, coverage, ladder, split, provider = said(plan, advice)
    assert "tenth percentile of the 30 days" in lookback and "looked back 30 days" in lookback
    assert "80 percent" in coverage
    assert "8.33 percent" in ladder and "this month" in ladder
    assert "bound to families" in split
    assert (
        provider
        == "The provider recommends 0.9 USD an hour of Compute Savings Plans, bought at once."
    )


def test_a_provider_that_could_not_be_read_leaves_meters_plan_alone() -> None:
    plan = plan_of(every_day("1"))
    sentences = said(plan, [Advice(FLEXIBLE, 0, None, failed=True)])
    assert (
        sentences[0]
        == "The provider's recommendation could not be read, so Meter's plan is shown alone."
    )
    assert not any("recommends" in one for one in sentences)


def test_a_provider_advising_nothing_says_so() -> None:
    plan = plan_of(every_day("1"))
    sentences = said(plan, [Advice(FLEXIBLE, 30, None, failed=False)])
    assert sentences[-1] == "The provider recommends buying no Savings Plan."


APPROVED_AT = datetime(2026, 10, 14, 9, tzinfo=UTC)


def bought(line_no: int = 1, hourly: str = "0.480", **overrides: object) -> Bought:
    values: dict[str, object] = {
        "plan_id": "plan-1",
        "line_no": line_no,
        "program": FAMILY_BOUND,
        "family": "m6i",
        "region": "r1",
        "hourly_commitment": Decimal(hourly),
        "term_months": 12,
        "payment_option": "No Upfront",
        "approved_at": APPROVED_AT,
    }
    values.update(overrides)
    return Bought(**values)  # type: ignore[arg-type]


def seen(commitment_id: str, hourly: str = "0.480", **overrides: object) -> Seen:
    values: dict[str, object] = {
        "commitment_id": commitment_id,
        "program": FAMILY_BOUND,
        "family": "m6i",
        "region": "r1",
        "hourly_commitment": Decimal(hourly),
        "term_months": 12,
        "payment_option": "No Upfront",
        "starts_at": APPROVED_AT + timedelta(hours=3),
    }
    values.update(overrides)
    return Seen(**values)  # type: ignore[arg-type]


def test_a_bought_line_matches_the_commitment_that_is_its_purchase() -> None:
    assert match([bought()], [seen("sp-1", "0.4848")]) == {("plan-1", 1): "sp-1"}


def test_a_commitment_more_than_one_percent_away_is_not_the_purchase() -> None:
    assert match([bought()], [seen("sp-1", "0.4850")]) == {}


def test_a_commitment_bought_before_the_approval_is_not_the_purchase() -> None:
    early = seen("sp-1", starts_at=APPROVED_AT - timedelta(minutes=1))
    assert match([bought()], [early]) == {}


@pytest.mark.parametrize(
    "different",
    [
        {"family": "c6i"},
        {"region": "r2"},
        {"term_months": 36},
        {"payment_option": "All Upfront"},
        {"program": FLEXIBLE, "family": None, "region": None},
    ],
)
def test_a_family_bound_line_needs_its_own_family_region_term_and_payment(
    different: dict[str, Any],
) -> None:
    assert match([bought()], [seen("sp-1", **different)]) == {}


def test_a_flexible_line_matches_whatever_family_and_region() -> None:
    line = bought(program=FLEXIBLE, family=None, region=None)
    assert match([line], [seen("sp-1", program=FLEXIBLE, family=None, region=None)]) == {
        ("plan-1", 1): "sp-1"
    }


def test_each_commitment_is_matched_once_and_to_the_closest_line() -> None:
    lines = [bought(1, "0.480"), bought(2, "0.300")]
    found = match(lines, [seen("sp-far", "0.4801"), seen("sp-near", "0.4800"), seen("sp-b", "0.3")])
    assert found == {("plan-1", 1): "sp-near", ("plan-1", 2): "sp-b"}
    assert match([*lines[:1], bought(3)], [seen("sp-only")]) == {("plan-1", 1): "sp-only"}
