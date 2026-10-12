"""What a line of AI spend bought, in the words FOCUS does not have yet. P13, FEAT-081.

FOCUS has no column for a model or a token, so Meter carries them in `x_` columns, the prefix FOCUS
reserves for a producer's own, until FOCUS 1.5 names them, OPEN-34. The kinds of token are the
same for every source; how a source spells its model is the source's own, and an adapter reads it,
which is why nothing here names a vendor, ADR-0028.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final
from uuid import UUID

from finops_core.domain.fact import Fact

INPUT: Final = "input"
OUTPUT: Final = "output"
CACHE_READ: Final = "cache_read"
CACHE_WRITE: Final = "cache_write"

#: Every token type a row can carry, which the table's constraint also holds.
TOKEN_TYPES: Final = frozenset({INPUT, OUTPUT, CACHE_READ, CACHE_WRITE})


@dataclass(frozen=True, kw_only=True)
class AiUsage(Fact):
    """Tokens and requests one caller spent on one model in one day, P13 spec section 6.

    From the invocation logs, TASK-P13-003, and the providers' usage reports, TASK-P13-004 and
    005. Never a cost: what a caller's tokens cost is modelled when read, from the bill's unit cost
    for the same model and day, because only the bill knows the price paid.

    An empty string in a dimension means the source does not report it, which is different from
    a caller nobody knows, and the table's key needs the difference spelled out. Which providers
    exist is the table's constraint, ADR-0028 keeping a vendor's name out of this package.
    """

    tenant_id: UUID
    #: The source, as its collector names it.
    provider: str
    #: A cloud account, or the provider's organization.
    account_id: str
    usage_date: date
    model: str
    #: The Region, the project or the workspace, whichever the source divides usage by.
    workspace: str = ""
    api_key_id: str = ""
    #: An IAM ARN or a provider's user identifier, either of which can name a person: class P.
    caller: str = ""
    #: The value of the request metadata key a deployment names for its applications.
    application: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    #: None where the source counts tokens and not requests, which is never a zero.
    requests: int | None = None

    def __post_init__(self) -> None:
        if not self.provider:
            raise ValueError("an AI usage row names its source")
        if not self.model:
            raise ValueError("an AI usage row names its model")
        counts = (
            self.input_tokens,
            self.output_tokens,
            self.cache_read_tokens,
            self.cache_write_tokens,
            self.requests or 0,
        )
        if min(counts) < 0:
            raise ValueError("a token or request count is never negative")
