"""What a cost row may say about AI spend, whichever source wrote it. TASK-P13-002.

The domain checks the token type and that a row names its source; the vocabulary of sources is the
table's constraint, ADR-0028 keeping a vendor's name out of `finops_core`, and how a source spells
its model is its adapter's, `tests/providers/aws/test_bedrock_usage.py`.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from finops_core.domain.ai import INPUT
from finops_core.domain.cost import AWS_EXPORT, CostRecord


def record(**overrides: object) -> CostRecord:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    base = CostRecord(
        tenant_id=uuid4(),
        ingest_run_id=uuid4(),
        source_fingerprint="fp",
        as_of=start,
        collected_at=start,
        billing_account_id="111122223333",
        sub_account_id="444455556666",
        billing_period_start=date(2026, 8, 1),
        billing_period_end=date(2026, 9, 1),
        charge_period_start=start,
        charge_period_end=start,
        provider_name="AWS",
        publisher_name="AWS",
        invoice_issuer_name="AWS",
        service_name="Amazon Bedrock",
        service_category="AI and Machine Learning",
        resource_id=None,
        resource_name=None,
        region_id="eu-west-1",
        availability_zone=None,
        charge_category="Usage",
        charge_description=None,
        sku_id=None,
        pricing_quantity=Decimal("2000"),
        consumed_quantity=Decimal("2000"),
        consumed_unit="Tokens",
        billed_cost=Decimal("1"),
        effective_cost=Decimal("1"),
        list_cost=None,
        contracted_cost=None,
        commitment_discount_id=None,
        commitment_discount_type=None,
        commitment_discount_status=None,
        tags={},
    )
    return replace(base, **overrides)  # type: ignore[arg-type]


def test_a_row_is_the_bills_unless_its_source_says_otherwise() -> None:
    assert record().ingest_source == AWS_EXPORT


def test_the_record_keeps_what_its_source_named() -> None:
    row = record(x_usage_type="EUW1-NovaPro-output-tokens", x_ai_model="m", x_ai_token_type=INPUT)
    assert (row.x_ai_model, row.x_ai_token_type, row.x_ai_tokens) == ("m", INPUT, None)


def test_a_row_without_ai_columns_carries_none() -> None:
    row = record(x_usage_type="EUW1-NovaPro-output-tokens")
    assert (row.x_ai_model, row.x_ai_token_type, row.x_ai_tokens) == (None, None, None)


def test_a_row_without_a_source_or_with_an_unknown_token_type_is_refused() -> None:
    with pytest.raises(ValueError, match="collector that wrote it"):
        record(ingest_source="")
    with pytest.raises(ValueError, match="token type"):
        record(x_ai_model="m", x_ai_token_type="reasoning")
