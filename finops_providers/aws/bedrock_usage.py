"""What a line of Bedrock spend bought: the model and the kind of token, read from the bill.

P13 spec section 5.2, FEAT-081. AWS's knowledge, so it lives with the AWS adapters: ADR-0028
keeps every vendor's name out of `finops_core`, and a usage type is how AWS, and only AWS, spells
a model. FOCUS has no column for a model or a token yet, so Meter carries them in `x_` columns
until FOCUS 1.5 names them, OPEN-34. For Bedrock nothing states them outright: AWS encodes both
in the usage type, as a model segment followed by a token suffix, and this reads them back out.

**A usage type this does not recognise yields nothing.** The cost still counts, as Bedrock with
no model, which is true. Guessing a model from a near match would put spend against a model that
did not incur it, and nobody could tell the guess from a reading.

The suffixes are the ones AWS documents for Bedrock in the Cost and Usage Report, read on
2026-10-12. They are checkable only against a real export, ISS-002, like every column name in
`finops_providers/aws/cur.py`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from finops_core.domain.ai import CACHE_READ, CACHE_WRITE, INPUT, OUTPUT

#: The marker in a usage type and the token type it means, cache first, because a cache
#: marker contains the word input and the input marker must not claim it.
#:
#: The first four are Bedrock's own form, `EUW1-NovaPro-input-tokens`. The last four are the
#: form a model sold through AWS Marketplace takes, `USE1-MP:USE1_InputTokenCount-Units`, which
#: names no model at all, so its model comes from the service name instead.
_MARKERS: Final[tuple[tuple[str, str], ...]] = (
    ("-cache-read-input-token-count", CACHE_READ),
    ("-cache-write-input-token-count", CACHE_WRITE),
    ("-input-tokens", INPUT),
    ("-output-tokens", OUTPUT),
    ("cachereadinputtokencount", CACHE_READ),
    ("cachewriteinputtokencount", CACHE_WRITE),
    ("inputtokencount", INPUT),
    ("outputtokencount", OUTPUT),
)

#: The Region code a usage type starts with, `USE1-` or `EUW1-`. Absent in some, so optional.
_REGION_PREFIX: Final = re.compile(r"^[A-Z]{2,4}[0-9]?-")

#: What a marketplace model's service name carries after the model, which is not the model.
_EDITION: Final = re.compile(r"\s*\(Amazon Bedrock Edition\)\s*$", re.IGNORECASE)

#: A consumed unit naming thousands or millions of tokens. AWS has billed Bedrock tokens in
#: both, and a count read in the wrong one is wrong by a factor of a thousand.
_THOUSANDS: Final = re.compile(r"\b(1k|1,000|1000|thousand)\b", re.IGNORECASE)
_MILLIONS: Final = re.compile(r"\b(1m|1,000,000|1000000|million)\b", re.IGNORECASE)


@dataclass(frozen=True, kw_only=True)
class TokenLine:
    """The model and token type one usage type names. Never partial: both, or no line."""

    model: str
    token_type: str


def is_bedrock(service_name: str | None) -> bool:
    """Whether a row is Bedrock's, by the service name every Bedrock line carries.

    `Amazon Bedrock` in the FOCUS export, `AmazonBedrock` where a service code stands in, and a
    marketplace model's `Claude ... (Amazon Bedrock Edition)`. A token suffix on any other
    service is not read, because nothing documents what it would mean there.
    """
    return service_name is not None and "bedrock" in service_name.lower()


def parse_usage_type(usage_type: str | None, service_name: str | None) -> TokenLine | None:
    """The model and token type a Bedrock usage type names, or None when it names neither."""
    if not usage_type or not is_bedrock(service_name):
        return None
    lowered = usage_type.lower()
    for marker, token_type in _MARKERS:
        at = lowered.find(marker)
        if at < 0:
            continue
        if marker.startswith("-"):
            # Bedrock's own form: the model is what sits between the Region and the marker.
            # What follows the marker, a tier or `-cross-region-global`, stays in the usage type.
            model = _REGION_PREFIX.sub("", usage_type[:at]).strip("-")
        else:
            # A marketplace model: the usage type names a meter, not a model, and only a service
            # name with the edition suffix names the model. Bedrock's own name would read as one.
            if not _EDITION.search(service_name or ""):
                return None
            model = _EDITION.sub("", service_name or "").strip()
        if not model or "mp:" in model.lower():
            return None
        return TokenLine(model=model, token_type=token_type)
    return None


def tokens_from(quantity: Decimal | None, unit: str | None) -> Decimal | None:
    """A token count from a consumed quantity and its unit, or None without a quantity.

    A unit that names thousands or millions scales the count; any other unit is read as tokens,
    which is what Bedrock's token usage types meter. Never negative: a credit's negative quantity
    is not a count of tokens, so it yields nothing rather than a negative count.
    """
    if quantity is None or quantity < 0:
        return None
    if unit and _MILLIONS.search(unit):
        return quantity * 1_000_000
    if unit and _THOUSANDS.search(unit):
        return quantity * 1_000
    return quantity
