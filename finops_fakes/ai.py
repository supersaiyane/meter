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
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType

from finops_core.domain.account import AccountKey
from finops_core.domain.ai import CACHE_READ, INPUT, OUTPUT, AiUsage, ProviderAccount
from finops_core.domain.cost import CostRecord, source_fingerprint
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


# --- an AI provider's own reports, TASK-P13-004 -------------------------------------------

#: The fake estate's OpenAI organization, connected for the local stack. Its key's secret is a
#: name under the local path; the fake never reads it.
FAKE_OPENAI = ProviderAccount(
    provider="openai",
    organization_id="org-fake-openai",
    name="Fake OpenAI organization",
    key_secret_name="meter/local/ai/openai-fake",
)


@dataclass(frozen=True, kw_only=True)
class ProjectUse:
    """One project's day: a model, its tokens by kind, its requests and its users."""

    project: str
    model: str
    input_tokens: int
    cached_tokens: int
    output_tokens: int
    requests: int
    users: tuple[str, ...]
    #: USD per token, by the line item's kind.
    price: Mapping[str, Decimal]


PROJECTS: tuple[ProjectUse, ...] = (
    ProjectUse(
        project="proj-support-bot",
        model="gpt-fake-large",
        input_tokens=2_000_000,
        cached_tokens=800_000,
        output_tokens=300_000,
        requests=4200,
        users=("user-fake-support",),
        price=MappingProxyType(
            {
                "input": Decimal("0.0000025"),
                "cached input": Decimal("0.00000125"),
                "output": Decimal("0.00001"),
            }
        ),
    ),
    ProjectUse(
        project="proj-search",
        model="gpt-fake-mini",
        input_tokens=6_000_000,
        cached_tokens=0,
        output_tokens=900_000,
        requests=15000,
        users=("",),
        price=MappingProxyType(
            {
                "input": Decimal("0.00000015"),
                "cached input": Decimal("0"),
                "output": Decimal("0.0000006"),
            }
        ),
    ),
)


class FakeProviderReports:
    """`AiProviderReports` in memory: the fake organization's daily cost and usage."""

    def __init__(self, *, at: datetime = fixtures.AS_OF) -> None:
        self._at = at

    def costs(
        self, account: ProviderAccount, start: datetime, end: datetime
    ) -> Iterable[CostRecord]:
        rows: list[CostRecord] = []
        for day, day_end in _days(start, end):
            drift = DRIFT_CEILING + Decimal((day.date() - self._at.date()).days) / DRIFT_DIVISOR
            for use in PROJECTS:
                uncached = use.input_tokens - use.cached_tokens
                for kind, tokens in (
                    ("input", uncached),
                    ("cached input", use.cached_tokens),
                    ("output", use.output_tokens),
                ):
                    if not tokens:
                        continue
                    amount = (Decimal(tokens) * use.price[kind] * drift).quantize(Decimal("0.0001"))
                    rows.append(_provider_cost(account, day, day_end, use, kind, amount, self._at))
        return tuple(rows)

    def usage(self, account: ProviderAccount, start: datetime, end: datetime) -> Iterable[AiUsage]:
        rows: list[AiUsage] = []
        for day, day_end in _days(start, end):
            drift = DRIFT_CEILING + Decimal((day.date() - self._at.date()).days) / DRIFT_DIVISOR
            for use in PROJECTS:
                share = Decimal(1) / len(use.users)
                for user in use.users:
                    rows.append(
                        AiUsage(
                            tenant_id=fixtures.TENANT_ID,
                            provider=account.provider,
                            account_id=account.organization_id,
                            usage_date=day.date(),
                            model=use.model,
                            workspace=use.project,
                            api_key_id=f"key-{use.project}",
                            caller=user,
                            input_tokens=int(
                                (use.input_tokens - use.cached_tokens) * drift * share
                            ),
                            cache_read_tokens=int(use.cached_tokens * drift * share),
                            output_tokens=int(use.output_tokens * drift * share),
                            requests=int(use.requests * drift * share),
                            as_of=day_end,
                            collected_at=max(self._at, day_end),
                        )
                    )
        return tuple(rows)


_KIND = {"input": INPUT, "cached input": CACHE_READ, "output": OUTPUT}


def _provider_cost(
    account: ProviderAccount,
    day: datetime,
    day_end: datetime,
    use: ProjectUse,
    kind: str,
    amount: Decimal,
    at: datetime,
) -> CostRecord:
    line = f"{use.model}, {kind}"
    period = date(day.year, day.month, 1)
    return CostRecord(
        tenant_id=fixtures.TENANT_ID,
        ingest_run_id=fixtures.INGEST_RUN_ID,
        source_fingerprint=source_fingerprint(
            billing_account_id=account.organization_id,
            sub_account_id=use.project,
            charge_period_start=day,
            charge_period_end=day_end,
            service_name="OpenAI API",
            resource_id=None,
            sku_id=line,
            charge_category="Usage",
            commitment_discount_id=None,
        ),
        as_of=day_end,
        collected_at=max(at, day_end),
        billing_account_id=account.organization_id,
        sub_account_id=use.project,
        billing_period_start=period,
        billing_period_end=date(period.year + (period.month == 12), period.month % 12 + 1, 1),
        charge_period_start=day,
        charge_period_end=day_end,
        provider_name="OpenAI",
        publisher_name="OpenAI",
        invoice_issuer_name="OpenAI",
        service_name="OpenAI API",
        service_category="AI and Machine Learning",
        resource_id=None,
        resource_name=None,
        region_id=None,
        availability_zone=None,
        charge_category="Usage",
        charge_description=line,
        sku_id=line,
        pricing_quantity=None,
        consumed_quantity=None,
        consumed_unit=None,
        billed_cost=amount,
        effective_cost=amount,
        list_cost=None,
        contracted_cost=None,
        commitment_discount_id=None,
        commitment_discount_type=None,
        commitment_discount_status=None,
        tags={},
        billing_account_name=account.name,
        billing_currency="USD",
        ingest_source=account.provider,
        x_ai_model=use.model,
        x_ai_token_type=_KIND[kind],
    )
