"""What the difference between an invoice and Meter's billed cost means. TASK-P10-004.

P10 spec section 5.4: every state, the tax split, and the tolerance at its edges.
"""

from __future__ import annotations

from decimal import Decimal

from finops_core.domain.reconciliation import (
    CENT,
    TOLERANCE,
    InvoicedSum,
    ReconciliationState,
    allowance,
    compare,
    without_invoice,
)


def usd(before_tax: str, tax: str = "0") -> InvoicedSum:
    return InvoicedSum(currency="USD", before_tax=Decimal(before_tax), tax=Decimal(tax))


def test_the_tolerance_is_a_hundredth_of_a_percent_with_a_cent_floor() -> None:
    assert Decimal("0.0001") == TOLERANCE
    assert Decimal("0.01") == CENT
    assert allowance(Decimal("1000000")) == Decimal("100")
    assert allowance(Decimal("0")) == CENT
    assert allowance(Decimal("-5000")) == Decimal("0.5")


def test_an_exact_sum_matches_with_zero_differences() -> None:
    found = compare(
        currency="USD", before_tax=Decimal("100"), tax=Decimal("10"), sums=(usd("100", "10"),)
    )
    assert found.state is ReconciliationState.MATCHED
    assert found.difference_before_tax == 0
    assert found.difference_tax == 0


def test_sums_in_one_currency_are_added_before_comparing() -> None:
    found = compare(
        currency="USD",
        before_tax=Decimal("100"),
        tax=Decimal("0"),
        sums=(usd("60"), usd("40")),
    )
    assert found.state is ReconciliationState.MATCHED
    assert found.meter_before_tax == Decimal("100")


def test_a_difference_within_the_tolerance_matches_and_one_past_it_does_not() -> None:
    inside = compare(
        currency="USD", before_tax=Decimal("1000000"), tax=Decimal("0"), sums=(usd("999900"),)
    )
    outside = compare(
        currency="USD", before_tax=Decimal("1000000"), tax=Decimal("0"), sums=(usd("999899.99"),)
    )
    assert inside.state is ReconciliationState.MATCHED
    assert outside.state is ReconciliationState.MISMATCHED


def test_under_a_cent_is_the_invoices_own_rounding() -> None:
    found = compare(
        currency="USD", before_tax=Decimal("10"), tax=Decimal("0"), sums=(usd("10.0099999999"),)
    )
    assert found.state is ReconciliationState.MATCHED


def test_a_mismatch_says_by_how_much_and_which_way() -> None:
    found = compare(
        currency="USD", before_tax=Decimal("100"), tax=Decimal("0"), sums=(usd("97.50"),)
    )
    assert found.state is ReconciliationState.MISMATCHED
    # Meter's less the invoice's: negative is a charge on the invoice the rows do not carry.
    assert found.difference_before_tax == Decimal("-2.50")


def test_tax_is_compared_apart_and_a_matching_total_does_not_hide_it() -> None:
    """100 plus 10 and 105 plus 5 total the same, and are not the same bill."""
    found = compare(
        currency="USD", before_tax=Decimal("100"), tax=Decimal("10"), sums=(usd("105", "5"),)
    )
    assert found.state is ReconciliationState.MISMATCHED
    assert found.difference_before_tax == Decimal("5")
    assert found.difference_tax == Decimal("-5")


def test_no_rows_carries_no_figure_rather_than_a_zero() -> None:
    found = compare(currency="USD", before_tax=Decimal("40"), tax=Decimal("0"), sums=())
    assert found.state is ReconciliationState.NO_ROWS
    assert found.meter_before_tax is None
    assert found.difference_before_tax is None


def test_another_currency_is_never_converted_or_added() -> None:
    eur = InvoicedSum(currency="EUR", before_tax=Decimal("100"), tax=Decimal("0"))
    unknown = InvoicedSum(currency=None, before_tax=Decimal("100"), tax=Decimal("0"))
    for sums in ((eur,), (usd("50"), eur), (unknown,)):
        found = compare(currency="USD", before_tax=Decimal("100"), tax=Decimal("0"), sums=sums)
        assert found.state is ReconciliationState.CURRENCY_DIFFERS
        assert found.meter_before_tax is None
        assert found.difference_before_tax is None


def test_a_period_with_no_invoice_is_open_unless_the_read_failed() -> None:
    assert without_invoice(read_failed=False) is ReconciliationState.PERIOD_OPEN
    assert without_invoice(read_failed=True) is ReconciliationState.NOT_READABLE


def test_the_states_are_the_six_the_spec_names() -> None:
    assert [state.value for state in ReconciliationState] == [
        "Matched",
        "Mismatched",
        "Period open",
        "No rows",
        "Currency differs",
        "Not readable",
    ]
