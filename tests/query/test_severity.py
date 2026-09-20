"""Severity from money, and the cause a finding is grouped by. ADR-0016."""

from __future__ import annotations

from decimal import Decimal

import pytest

from finops_query.severity import (
    ALERT_ALWAYS_ON,
    CRITICAL,
    ENGINE_SCAN,
    HIGH,
    LOW,
    MEDIUM,
    VERY_WIDE_WINDOW,
    WIDE_WINDOW,
    Thresholds,
    primary_cause,
    severity_for,
    thresholds_from,
)

BANDS = Thresholds(critical=Decimal("1000"), high=Decimal("100"), medium=Decimal("20"))


class Settings:
    severity_critical_usd = Decimal("2000")
    severity_high_usd = Decimal("200")
    severity_medium_usd = Decimal("40")


def test_the_band_is_the_money() -> None:
    assert severity_for(5000, BANDS) == CRITICAL
    assert severity_for(500, BANDS) == HIGH
    assert severity_for(50, BANDS) == MEDIUM
    assert severity_for(5, BANDS) == LOW


def test_a_figure_exactly_on_a_threshold_takes_the_higher_band() -> None:
    # Otherwise 1,000 USD is not critical and nobody can say what is.
    assert severity_for(Decimal("1000"), BANDS) == CRITICAL
    assert severity_for(Decimal("100"), BANDS) == HIGH
    assert severity_for(Decimal("20"), BANDS) == MEDIUM


def test_the_bands_come_from_settings_rather_than_from_here() -> None:
    # 100 USD a month is material to one organization and rounding error to
    # another, which is why ADR-0016 makes them configurable per tenant.
    bands = thresholds_from(Settings())
    # The same figure, a different band. 150 USD is HIGH on ADR-0016's numbers
    # and MEDIUM to an organization that set its bar at 200.
    assert severity_for(150, BANDS) == HIGH
    assert severity_for(150, bands) == MEDIUM
    assert severity_for(2500, bands) == CRITICAL


def test_bands_that_do_not_descend_are_refused() -> None:
    # An unordered set silently makes one band unreachable, and the finding that
    # never reaches CRITICAL is the one that mattered.
    with pytest.raises(ValueError, match="descend"):
        Thresholds(critical=Decimal("10"), high=Decimal("100"), medium=Decimal("20"))


def test_the_cause_is_the_one_a_reader_would_change_first() -> None:
    # An alert running 24x7 is a different conversation from a dashboard nobody
    # has open, even at the same monthly figure.
    assert primary_cause((WIDE_WINDOW, ALERT_ALWAYS_ON)) == ALERT_ALWAYS_ON
    assert primary_cause((WIDE_WINDOW, VERY_WIDE_WINDOW)) == VERY_WIDE_WINDOW


def test_a_finding_with_no_sharper_cause_is_filed_under_the_scan() -> None:
    # True of every priced query, so it is the honest default rather than a
    # guess, and it keeps every finding groupable.
    assert primary_cause(()) == ENGINE_SCAN
