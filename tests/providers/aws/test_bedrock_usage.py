"""Reading a model and a token type out of a Bedrock usage type. TASK-P13-002, FEAT-081.

The parser lives with the AWS adapters, ADR-0028 keeping vendors out of `finops_core`.

The parser's one rule worth a test of its own: a usage type it does not recognise yields
nothing, because a near match read as a model puts spend against a model that did not incur it.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from finops_core.domain.ai import CACHE_READ, CACHE_WRITE, INPUT, OUTPUT
from finops_providers.aws.bedrock_usage import (
    TokenLine,
    is_bedrock,
    parse_usage_type,
    tokens_from,
)

BEDROCK = "Amazon Bedrock"


@pytest.mark.parametrize(
    ("usage_type", "model", "token_type"),
    [
        ("EUW1-NovaPro-input-tokens", "NovaPro", INPUT),
        ("EUW1-NovaPro-output-tokens", "NovaPro", OUTPUT),
        ("USE1-Nova1.5-cache-read-input-token-count", "Nova1.5", CACHE_READ),
        ("USE1-Nova1.5-cache-write-input-token-count", "Nova1.5", CACHE_WRITE),
        # What follows the marker is a tier or the cross Region form, not part of the model.
        ("USE1-NovaLite-input-tokens-batch", "NovaLite", INPUT),
        ("USE1-NovaLite-output-tokens-cross-region-global", "NovaLite", OUTPUT),
        # Some usage types carry no Region code at all.
        ("TitanEmbeddingsG1-Text-input-tokens", "TitanEmbeddingsG1-Text", INPUT),
    ],
)
def test_bedrocks_own_form_names_the_model_and_the_token_type(
    usage_type: str, model: str, token_type: str
) -> None:
    assert parse_usage_type(usage_type, BEDROCK) == TokenLine(model=model, token_type=token_type)


@pytest.mark.parametrize(
    ("usage_type", "token_type"),
    [
        ("USE1-MP:USE1_InputTokenCount-Units", INPUT),
        ("USE1-MP:USE1_OutputTokenCount-Units", OUTPUT),
        ("USE1-MP:USE1_CacheReadInputTokenCount-Units", CACHE_READ),
        ("USE1-MP:USE1_CacheWriteInputTokenCount-Units", CACHE_WRITE),
    ],
)
def test_a_marketplace_model_is_named_by_its_service(usage_type: str, token_type: str) -> None:
    service = "Claude 3.5 Sonnet (Amazon Bedrock Edition)"
    assert parse_usage_type(usage_type, service) == TokenLine(
        model="Claude 3.5 Sonnet", token_type=token_type
    )


def test_a_marketplace_meter_under_bedrocks_own_name_names_no_model() -> None:
    """Without the edition suffix the service name is Bedrock's, which is not a model."""
    assert parse_usage_type("USE1-MP:USE1_InputTokenCount-Units", BEDROCK) is None


@pytest.mark.parametrize(
    ("usage_type", "service"),
    [
        ("EUW1-ProvisionedThroughput-ModelUnits", BEDROCK),
        ("EUW1-Agents-Invocations", BEDROCK),
        ("", BEDROCK),
        (None, BEDROCK),
        # A token suffix outside Bedrock is not read: nothing documents what it means there.
        ("EUW1-Something-input-tokens", "Amazon SageMaker"),
        ("EUW1-NovaPro-input-tokens", None),
        # A marker with nothing before it names no model.
        ("-input-tokens", BEDROCK),
    ],
)
def test_anything_else_yields_nothing_rather_than_a_guess(
    usage_type: str | None, service: str | None
) -> None:
    assert parse_usage_type(usage_type, service) is None


def test_bedrock_is_recognised_by_every_name_it_bills_under() -> None:
    assert is_bedrock("Amazon Bedrock")
    assert is_bedrock("AmazonBedrock")
    assert is_bedrock("Claude 3.5 Sonnet (Amazon Bedrock Edition)")
    assert not is_bedrock("Amazon Elastic Compute Cloud")
    assert not is_bedrock(None)


@pytest.mark.parametrize(
    ("quantity", "unit", "expected"),
    [
        (Decimal("1500"), "Tokens", Decimal("1500")),
        (Decimal("1500"), None, Decimal("1500")),
        (Decimal("2.5"), "1K tokens", Decimal("2500")),
        (Decimal("2.5"), "Thousand Tokens", Decimal("2500")),
        (Decimal("0.5"), "1M tokens", Decimal("500000")),
        (Decimal("0.5"), "Million tokens", Decimal("500000")),
        (None, "Tokens", None),
        # A credit's negative quantity is not a count of tokens.
        (Decimal("-10"), "Tokens", None),
    ],
)
def test_a_token_count_reads_the_unit_it_was_billed_in(
    quantity: Decimal | None, unit: str | None, expected: Decimal | None
) -> None:
    assert tokens_from(quantity, unit) == expected
