"""A held commitment's own rules. TASK-P14-002, FEAT-086."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest

from finops_core.domain.commitments import RESERVATION, SAVINGS_PLAN, HeldCommitment, term_months

START = datetime(2026, 1, 1, tzinfo=UTC)


def held(**overrides: Any) -> HeldCommitment:
    values: dict[str, Any] = {
        "tenant_id": uuid4(),
        "kind": SAVINGS_PLAN,
        "commitment_id": "sp-1",
        "program": "Compute",
        "account_id": "111122223333",
        "region_id": None,
        "applies_to": None,
        "quantity": None,
        "hourly_commitment": Decimal("1"),
        "term_months": 12,
        "payment_option": "No Upfront",
        "upfront_amount": Decimal(0),
        "recurring_hourly": Decimal("1"),
        "currency": "USD",
        "starts_at": START,
        "ends_at": START + timedelta(days=365),
        "state": "active",
        "as_of": START,
        "collected_at": START,
    }
    values.update(overrides)
    return HeldCommitment(**values)


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"quantity": 2}, "exactly one"),
        ({"kind": RESERVATION, "hourly_commitment": None}, "exactly one"),
        ({"term_months": 0}, "term"),
        ({"ends_at": START}, "ends before"),
        ({"kind": "lease"}, "savings plan or a reservation"),
        ({"collected_at": START - timedelta(seconds=1)}, "collected before"),
    ],
)
def test_a_commitment_that_cannot_exist_is_refused(overrides: dict[str, Any], reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        held(**overrides)


@pytest.mark.parametrize(("seconds", "months"), [(31536000, 12), (94608000, 36), (1, 1)])
def test_a_term_in_seconds_is_whole_months(seconds: int, months: int) -> None:
    assert term_months(seconds) == months


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"target_coverage": Decimal(0)}, "target coverage"),
        ({"target_coverage": Decimal("1.1")}, "target coverage"),
        ({"term_years": 2}, "terms"),
        ({"payment_option": "Monthly"}, "payment option"),
        ({"ladder_limit": Decimal(0)}, "ladder limit"),
    ],
)
def test_a_policy_no_plan_could_follow_is_refused(overrides: dict[str, Any], reason: str) -> None:
    from dataclasses import replace

    from finops_core.domain.commitments import DEFAULT_POLICY

    with pytest.raises(ValueError, match=reason):
        replace(DEFAULT_POLICY, **overrides)
