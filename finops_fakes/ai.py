"""The fake estate's AI usage: who called which model, as the invocation logs would say. P13.

TASK-P13-003. Three accounts, three answers, because the collector exists to tell them apart:

- `fake-platform-a` sends its Bedrock invocation logs to CloudWatch Logs, so its callers are read:
  two agents of the support assistant, which name their application in request metadata, and one
  person calling the model from a notebook, who names nothing.
- `fake-product-a` uses Bedrock too, and sends its logs to S3 only: NotOptedIn, with the step.
- Every other account has no invocation logging at all: NotOptedIn.

The callers' tokens are shares of the support assistant's line on the fake bill,
`finops_fakes.cur.BEDROCK_FEATURES`, with the same daily drift, so a cost per caller modelled from
the bill's unit cost lands on figures that add up to about what the bill says. Nothing here is
random: a fake whose numbers move between runs cannot be asserted against.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType

from finops_core.domain.account import AccountKey
from finops_core.domain.ai import AiUsage
from finops_core.errors import NotOptedIn
from finops_fakes import fixtures
from finops_fakes.cur import BEDROCK_FEATURES, DRIFT_CEILING, DRIFT_DIVISOR

COLLECTOR = "bedrock_invocations"
BEDROCK = "bedrock"

#: Where each account's invocation logging writes. Absent is nowhere.
LOGGING: Mapping[str, str] = MappingProxyType(
    {"fake-platform-a": "cloudwatch", "fake-product-a": "s3"}
)

#: The model the support assistant calls, as the invocation log names it.
SUPPORT_MODEL = "anthropic.claude-sonnet-4-20250514-v1:0"
SUPPORT_ACCOUNT = "fake-platform-a"
SUPPORT_APPLICATION = "support-assistant"


@dataclass(frozen=True, kw_only=True)
class Caller:
    caller: str
    application: str
    #: This caller's share of the feature's daily tokens.
    share: Decimal
    requests: int


CALLERS: tuple[Caller, ...] = (
    Caller(
        caller=f"arn:aws:sts::{SUPPORT_ACCOUNT}:assumed-role/support-assistant-service/triage",
        application=SUPPORT_APPLICATION,
        share=Decimal("0.70"),
        requests=1800,
    ),
    Caller(
        caller=f"arn:aws:sts::{SUPPORT_ACCOUNT}:assumed-role/support-assistant-service/escalation",
        application=SUPPORT_APPLICATION,
        share=Decimal("0.25"),
        requests=400,
    ),
    # A person in a notebook, who attaches no request metadata, so names no application.
    Caller(
        caller=f"arn:aws:iam::{SUPPORT_ACCOUNT}:user/fake-analyst",
        application="",
        share=Decimal("0.05"),
        requests=40,
    ),
)

#: The usage type suffix on the bill for each token type the logs count.
_SUFFIX = {
    "input_tokens": "input-tokens",
    "output_tokens": "output-tokens",
    "cache_read_tokens": "cache-read-input-token-count",
    "cache_write_tokens": "cache-write-input-token-count",
}


class FakeInvocationLogs:
    """`InvocationLogs` in memory, for the fake estate's three answers."""

    def __init__(self, *, at: datetime = fixtures.AS_OF) -> None:
        self._at = at

    def usage(
        self, account: AccountKey, region: str, start: datetime, end: datetime
    ) -> Iterable[AiUsage]:
        scope = f"{account}:{region}"
        where = LOGGING.get(account.account_id)
        if where != "cloudwatch":
            written = "to S3 only" if where == "s3" else "nowhere"
            raise NotOptedIn(
                scope_key=scope,
                collector=COLLECTOR,
                detail=f"Bedrock model invocation logging in this account and Region writes "
                f"{written}",
            )
        feature = next(f for f in BEDROCK_FEATURES if f.account == account.account_id)
        rows: list[AiUsage] = []
        for day, day_end in _days(start, end):
            drift = DRIFT_CEILING + Decimal((day.date() - self._at.date()).days) / DRIFT_DIVISOR
            for caller in CALLERS:

                def count(field: str, caller: Caller = caller, drift: Decimal = drift) -> int:
                    daily = feature.tokens.get(_SUFFIX[field], Decimal(0))
                    return int(daily * drift * caller.share)

                rows.append(
                    AiUsage(
                        tenant_id=fixtures.TENANT_ID,
                        provider=BEDROCK,
                        account_id=account.account_id,
                        usage_date=day.date(),
                        model=SUPPORT_MODEL,
                        workspace=region,
                        caller=caller.caller,
                        application=caller.application,
                        requests=caller.requests,
                        input_tokens=count("input_tokens"),
                        output_tokens=count("output_tokens"),
                        cache_read_tokens=count("cache_read_tokens"),
                        cache_write_tokens=count("cache_write_tokens"),
                        as_of=day_end,
                        collected_at=max(self._at, day_end),
                    )
                )
        return tuple(rows)


def _days(start: datetime, end: datetime) -> Iterator[tuple[datetime, datetime]]:
    day = start.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    while day < end:
        yield day, min(day + timedelta(days=1), end)
        day += timedelta(days=1)
