"""Anthropic's cost and usage reports for one organization, as FOCUS rows and AI usage. FEAT-083.

P13 spec section 5.5, TASK-P13-005. Two endpoints of the Admin API, read with an admin key: the
cost report, daily buckets of money grouped by workspace and description, and the messages usage
report, daily buckets of tokens grouped by model, workspace and key. The costs become FOCUS rows
in `cost_focus_daily` with `ingest_source` anthropic, the organization as the billing account and
the workspace as the sub account; the usage becomes `AiUsage`.

Two things differ from OpenAI and both are written down here because both would be wrong quietly.
The cost report states an amount in the currency's lowest unit, cents for USD, as a decimal
string, so it is divided by a hundred and never read as dollars. And a cost line grouped by
description names its model and token type in fields of their own, so nothing is parsed out of
the prose; a line whose cost is not tokens, web search or code execution, names no token type.
The usage report counts tokens and not requests, so `requests` is None and never a zero.

Like every adapter here this has made no real call. The field names are the ones Anthropic
documents for the Admin API, read on 2026-10-12, and ISS-285 holds them open until a key exists.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Final
from uuid import UUID

import httpx

from finops_core.domain.ai import CACHE_READ, CACHE_WRITE, INPUT, OUTPUT, AiUsage, ProviderAccount
from finops_core.domain.cost import CostRecord, source_fingerprint
from finops_core.errors import SchemaDrift
from finops_providers.ai_reports import ReportApi

COLLECTOR = "anthropic_usage"
#: The source, as `cost_focus_daily.ingest_source` and `ai_usage_daily.provider` name it.
SOURCE: Final = "anthropic"
PROVIDER_NAME: Final = "Anthropic"
SERVICE_NAME: Final = "Claude API"
SERVICE_CATEGORY: Final = "AI and Machine Learning"

BASE_URL: Final = "https://api.anthropic.com"  # allow-hardcoded: the provider's documented API host
#: The API version the requests are written for, which Anthropic requires on every request.
API_VERSION: Final = "2023-06-01"  # allow-hardcoded: the documented version header value
COSTS: Final = "/v1/organizations/cost_report"
MESSAGES: Final = "/v1/organizations/usage_report/messages"
#: Days a page holds. One bucket a day, and a month fits on one page.
PAGE_DAYS: Final = 31  # allow-hardcoded: a page size within the provider's documented maximum
#: The cost report's amounts are in the currency's lowest unit; a USD amount is in cents.
LOWEST_UNITS_PER_UNIT: Final = Decimal(100)  # allow-hardcoded: cents in a dollar, by definition

#: What each token type the cost report names means here.
TOKEN_TYPES: Final[dict[str, str]] = {
    "uncached_input_tokens": INPUT,
    "output_tokens": OUTPUT,
    "cache_read_input_tokens": CACHE_READ,
    "cache_creation.ephemeral_5m_input_tokens": CACHE_WRITE,
    "cache_creation.ephemeral_1h_input_tokens": CACHE_WRITE,
}


class AnthropicReports:
    """`AiProviderReports` over Anthropic's Admin API, for one organization at a time."""

    def __init__(
        self,
        tenant_id: UUID,
        ingest_run_id: UUID,
        key: Callable[[], str],
        *,
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._tenant_id = tenant_id
        self._run_id = ingest_run_id
        self._key = key
        self._transport = transport
        self._sleeper = sleeper
        self._clock = clock or (lambda: datetime.now(UTC))

    def _api(self, account: ProviderAccount) -> ReportApi:
        extra = {"sleeper": self._sleeper} if self._sleeper else {}
        return ReportApi(
            base_url=BASE_URL,
            headers=lambda: {"x-api-key": self._key(), "anthropic-version": API_VERSION},
            scope_key=scope_of(account),
            collector=COLLECTOR,
            transport=self._transport,
            **extra,
        )

    # -- the port ----------------------------------------------------------

    def costs(
        self, account: ProviderAccount, start: datetime, end: datetime
    ) -> Iterable[CostRecord]:
        params = {**_window(start, end), "group_by[]": ["workspace_id", "description"]}
        rows: list[CostRecord] = []
        for bucket in self._api(account).pages(COSTS, params):
            begins, ends = _bucket(bucket, account)
            for result in _results(bucket, account):
                rows.append(self._cost(account, begins, ends, result))
        return tuple(rows)

    def usage(self, account: ProviderAccount, start: datetime, end: datetime) -> Iterable[AiUsage]:
        params = {
            **_window(start, end),
            "bucket_width": "1d",
            "group_by[]": ["model", "workspace_id", "api_key_id"],
        }
        rows: list[AiUsage] = []
        at = self._clock()
        for bucket in self._api(account).pages(MESSAGES, params):
            begins, ends = _bucket(bucket, account)
            for result in _results(bucket, account):
                rows.append(_usage(account, begins, ends, result, at, self._tenant_id))
        return tuple(rows)

    # -- mapping -----------------------------------------------------------

    def _cost(
        self, account: ProviderAccount, begins: datetime, ends: datetime, result: dict[str, Any]
    ) -> CostRecord:
        lowest = _decimal(result.get("amount"), account)
        value = lowest / LOWEST_UNITS_PER_UNIT
        currency = str(result.get("currency") or "").upper() or None
        description = result.get("description")
        line = str(description) if description else None
        model = result.get("model") or None
        token_type = TOKEN_TYPES.get(str(result.get("token_type") or ""))
        workspace = result.get("workspace_id") or None
        period = date(begins.year, begins.month, 1)
        return CostRecord(
            tenant_id=self._tenant_id,
            ingest_run_id=self._run_id,
            source_fingerprint=source_fingerprint(
                billing_account_id=account.organization_id,
                sub_account_id=workspace,
                charge_period_start=begins,
                charge_period_end=ends,
                service_name=SERVICE_NAME,
                resource_id=None,
                sku_id=line,
                charge_category="Usage",
                commitment_discount_id=None,
            ),
            as_of=ends,
            collected_at=max(self._clock(), ends),
            billing_account_id=account.organization_id,
            sub_account_id=workspace,
            billing_period_start=period,
            billing_period_end=_next_month(period),
            charge_period_start=begins,
            charge_period_end=ends,
            provider_name=PROVIDER_NAME,
            publisher_name=PROVIDER_NAME,
            invoice_issuer_name=PROVIDER_NAME,
            service_name=SERVICE_NAME,
            service_category=SERVICE_CATEGORY,
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
            billed_cost=value,
            effective_cost=value,
            list_cost=None,
            contracted_cost=None,
            commitment_discount_id=None,
            commitment_discount_type=None,
            commitment_discount_status=None,
            tags={},
            billing_account_name=account.name,
            billing_currency=currency,
            ingest_source=SOURCE,
            x_ai_model=str(model) if model else None,
            x_ai_token_type=token_type if model else None,
        )


def scope_of(account: ProviderAccount) -> str:
    """How a failure for one organization is recorded and reported."""
    return f"{account.provider}:{account.organization_id}"


def _usage(
    account: ProviderAccount,
    begins: datetime,
    ends: datetime,
    result: dict[str, Any],
    at: datetime,
    tenant_id: UUID,
) -> AiUsage:
    model = result.get("model")
    if not model:
        raise SchemaDrift(
            scope_key=scope_of(account),
            collector=COLLECTOR,
            detail="a messages usage result named no model, though the report groups by it",
        )
    creation = result.get("cache_creation") or {}
    if not isinstance(creation, dict):
        raise SchemaDrift(
            scope_key=scope_of(account), collector=COLLECTOR, detail="cache_creation is not a map"
        )
    return AiUsage(
        tenant_id=tenant_id,
        provider=SOURCE,
        account_id=account.organization_id,
        usage_date=begins.date(),
        model=str(model),
        # The default workspace is reported as null, which is a workspace with no id.
        workspace=str(result.get("workspace_id") or ""),
        api_key_id=str(result.get("api_key_id") or ""),
        input_tokens=_count(result.get("uncached_input_tokens"), account),
        output_tokens=_count(result.get("output_tokens"), account),
        cache_read_tokens=_count(result.get("cache_read_input_tokens"), account),
        cache_write_tokens=_count(creation.get("ephemeral_5m_input_tokens"), account)
        + _count(creation.get("ephemeral_1h_input_tokens"), account),
        # Anthropic counts tokens and not requests, which is not a count of none.
        requests=None,
        as_of=ends,
        collected_at=max(at, ends),
    )


def _window(start: datetime, end: datetime) -> dict[str, Any]:
    return {
        "starting_at": start.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ending_at": end.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "limit": PAGE_DAYS,
    }


def _bucket(bucket: Any, account: ProviderAccount) -> tuple[datetime, datetime]:
    try:
        return (
            _moment(bucket["starting_at"]),
            _moment(bucket["ending_at"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise SchemaDrift(
            scope_key=scope_of(account),
            collector=COLLECTOR,
            detail="a report bucket had no readable start and end",
        ) from error


def _moment(raw: Any) -> datetime:
    moment = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError("a bucket boundary without a zone")
    return moment.astimezone(UTC)


def _results(bucket: Any, account: ProviderAccount) -> list[dict[str, Any]]:
    results = bucket.get("results") if isinstance(bucket, dict) else None
    if not isinstance(results, list):
        raise SchemaDrift(
            scope_key=scope_of(account), collector=COLLECTOR, detail="a bucket had no results list"
        )
    return [result for result in results if isinstance(result, dict)]


def _decimal(raw: Any, account: ProviderAccount) -> Decimal:
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError) as error:
        raise SchemaDrift(
            scope_key=scope_of(account),
            collector=COLLECTOR,
            detail=f"a cost result's amount {raw!r} is not a number",
        ) from error
    if not value.is_finite():
        raise SchemaDrift(
            scope_key=scope_of(account),
            collector=COLLECTOR,
            detail=f"a cost result's amount {raw!r} is not a number",
        )
    return value


def _count(raw: Any, account: ProviderAccount) -> int:
    if raw is None:
        return 0
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        raise SchemaDrift(
            scope_key=scope_of(account), collector=COLLECTOR, detail=f"{raw!r} is not a count"
        )
    return raw


def _next_month(period: date) -> date:
    return date(period.year + (period.month == 12), period.month % 12 + 1, 1)
