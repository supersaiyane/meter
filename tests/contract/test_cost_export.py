"""One sentence about a billing export, asked of every adapter that claims to be one.

The value here is not that each adapter works. Each has its own suite for that.
It is that the fake and the real one answer the same way, because the fake is
what every test above this line is written against, and a fake that is kinder
than the provider makes all of them meaningless at once.

Three sentences matter most.

An export that exists and has published nothing is not an export that is
missing. A period with no rows in it is said, not returned as an empty list
that reads as a quiet month. And a line item's identity is computed the same
way by both, or the same charge read through two adapters is two rows.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal

import pytest

from finops_core import errors
from finops_core.domain.cost import CostRecord, source_fingerprint

from .conftest import COST_EXPORT, ProviderUnderTest

pytestmark = pytest.mark.contract


@pytest.fixture(autouse=True)
def _skip_when_unimplemented(requires_port: Callable[[str], None]) -> None:
    requires_port(COST_EXPORT)


def _rows(subject: ProviderUnderTest) -> list[CostRecord]:
    period = subject.provider.latest_available_period()
    assert period is not None
    end = date(period.year + (period.month // 12), (period.month % 12) + 1, 1)
    return list(subject.provider.read_period(period, end))


def test_the_latest_period_is_a_period_or_an_honest_none(subject: ProviderUnderTest) -> None:
    period = subject.provider.latest_available_period()
    assert period is None or isinstance(period, date)


def test_a_period_that_exists_returns_rows(subject: ProviderUnderTest) -> None:
    rows = _rows(subject)
    assert rows
    assert all(isinstance(row, CostRecord) for row in rows)


def test_a_period_with_nothing_in_it_is_said_rather_than_returned_empty(
    subject: ProviderUnderTest,
) -> None:
    """`NoData` is the one cause a caller may draw as a zero.

    An empty list here reads as a month where nothing was spent, which is a
    claim. The absence of rows is not.
    """
    with pytest.raises(errors.NoData):
        list(subject.provider.read_period(date(1999, 1, 1), date(1999, 2, 1)))


def test_money_is_decimal_and_never_float(subject: ProviderUnderTest) -> None:
    for row in _rows(subject):
        assert isinstance(row.billed_cost, Decimal)
        assert isinstance(row.effective_cost, Decimal)


def test_every_row_carries_both_timestamps(subject: ProviderUnderTest) -> None:
    # Constraints 4 and 10. `collected_at` is never earlier than `as_of`,
    # because a value fetched before it was true is not a thing.
    for row in _rows(subject):
        assert row.collected_at >= row.as_of


def test_both_adapters_compute_a_line_item_identity_the_same_way(
    subject: ProviderUnderTest,
) -> None:
    """The one that would be expensive to get wrong.

    `source_fingerprint` is the key the ingest upserts on. An adapter that
    computed its own would make the same charge, read through two adapters, two
    rows, and the estate would report double.
    """
    for row in _rows(subject):
        assert row.source_fingerprint == source_fingerprint(
            billing_account_id=row.billing_account_id,
            sub_account_id=row.sub_account_id,
            charge_period_start=row.charge_period_start,
            charge_period_end=row.charge_period_end,
            service_name=row.service_name,
            resource_id=row.resource_id,
            sku_id=row.sku_id,
            charge_category=row.charge_category,
            commitment_discount_id=row.commitment_discount_id,
        )
