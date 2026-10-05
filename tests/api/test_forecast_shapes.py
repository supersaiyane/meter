"""How the forecast route reports an outcome, without a database. FEAT-066, TASK-P8-008.

The integration tests prove the route agrees with the forecast about real rows, and whether that
estate's forecast is shown or withheld is the estate's business. These prove both shapes are
reported right whichever it turns out to be: a shown forecast with its backtest ranges, and a
withheld one whose backtest carries misses and never a range.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from finops_api.routes.forecast import _backtest, _month, months_before
from finops_query.forecast import HeldOut, Outcome, Range

TESTS = (
    HeldOut(month=date(2026, 9, 1), estimate=Decimal(100), actual=Decimal(110)),
    HeldOut(month=date(2026, 8, 1), estimate=Decimal(100), actual=Decimal(90)),
    HeldOut(month=date(2026, 7, 1), estimate=Decimal(100), actual=Decimal(100)),
    HeldOut(month=date(2026, 6, 1), estimate=Decimal(0), actual=Decimal(50)),
)

SHOWN = Outcome(
    month=date(2026, 10, 1),
    figure=Range(low=Decimal(900), high=Decimal(1100)),
    withheld=None,
    median_miss=Decimal("0.0909"),
    tests=TESTS,
)


def test_a_shown_forecast_reports_its_range_and_counts_only_usable_tests() -> None:
    month = _month(SHOWN)
    assert month.figure is not None
    assert (month.figure.low, month.figure.high) == (Decimal(900), Decimal(1100))
    assert month.held_out == 3


def test_a_shown_forecast_applies_its_band_to_each_tested_month() -> None:
    rows = _backtest(SHOWN)
    # Ratios of +0.1, -0.1 and 0 read at the 10th and 90th percentiles: -0.08 and +0.08.
    assert [(row.low, row.high) for row in rows] == [(Decimal(92), Decimal(108))] * 3
    assert [row.within for row in rows] == [False, False, True]


def test_a_withheld_forecast_shows_its_misses_and_never_a_range() -> None:
    withheld = Outcome(
        month=date(2026, 10, 1),
        figure=None,
        withheld="Tested on 3 months, it missed by 20.0 percent at the median.",
        median_miss=Decimal("0.2"),
        tests=TESTS,
    )
    assert _month(withheld).figure is None
    rows = _backtest(withheld)
    assert [row.miss for row in rows] == [test.miss for test in TESTS[:3]]
    assert all(row.low is None and row.high is None and row.within is None for row in rows)


def test_months_before_crosses_a_year_end() -> None:
    assert months_before(date(2026, 2, 1), 3) == date(2025, 11, 1)
