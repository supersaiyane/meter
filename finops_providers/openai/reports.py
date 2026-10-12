"""OpenAI's cost and usage reports for one organization, as FOCUS rows and AI usage. FEAT-083.

P13 spec section 5.5, TASK-P13-004. Two endpoints of the organization API, read with an admin key:
the costs report, daily buckets of money grouped by line item and project, and the completions
usage report, daily buckets of tokens and requests grouped by model, project, key and user. The
costs become FOCUS rows in `cost_focus_daily` with `ingest_source` openai, the organization as the
billing account and the project as the sub account; the usage becomes `AiUsage`.

A line item reads `<model>, <kind>`, and three kinds are tokens: input, output and cached input. A
line item of another kind, or with no model, keeps its cost and names no token type, never a
guess. OpenAI's `input_tokens` includes the cached ones, so the uncached input is the difference.

Like every adapter here this has made no real call. The field names are the ones OpenAI documents
for the organization API, read on 2026-10-12, and ISS-285 holds them open until a key exists.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Final
from uuid import UUID

import httpx

from finops_core.domain.ai import CACHE_READ, INPUT, OUTPUT, AiUsage, ProviderAccount
from finops_core.domain.cost import CostRecord, source_fingerprint
from finops_core.errors import SchemaDrift
from finops_providers.ai_reports import ReportApi

COLLECTOR = "openai_usage"
#: The source, as `cost_focus_daily.ingest_source` and `ai_usage_daily.provider` name it.
SOURCE: Final = "openai"
PROVIDER_NAME: Final = "OpenAI"
SERVICE_NAME: Final = "OpenAI API"
SERVICE_CATEGORY: Final = "AI and Machine Learning"

BASE_URL: Final = "https://api.openai.com"  # allow-hardcoded: the provider's documented API host
COSTS: Final = "/v1/organization/costs"
COMPLETIONS: Final = "/v1/organization/usage/completions"
#: Days a page holds. One bucket a day, and a month fits on one page.
PAGE_DAYS: Final = 31  # allow-hardcoded: a page size within the provider's documented maximum

#: What the kind after a line item's model means, where it is a kind of token.
TOKEN_KINDS: Final[dict[str, str]] = {
    "input": INPUT,
    "output": OUTPUT,
    "cached input": CACHE_READ,
}


class OpenAiReports:
    """`AiProviderReports` over OpenAI's organization API, for one organization at a time."""

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
            headers=lambda: {"Authorization": f"Bearer {self._key()}"},
            scope_key=scope_of(account),
            collector=COLLECTOR,
            transport=self._transport,
            **extra,
        )

    # -- the port ----------------------------------------------------------

    def costs(
        self, account: ProviderAccount, start: datetime, end: datetime
    ) -> Iterable[CostRecord]:
        params = {
            **_window(start, end),
            "group_by": ["line_item", "project_id"],
        }
        rows: list[CostRecord] = []
        for bucket in self._api(account).pages(COSTS, params):
            begins, ends = _bucket(bucket, account)
            for result in _results(bucket, account):
                rows.append(self._cost(account, begins, ends, result))
        return tuple(rows)

    def usage(self, account: ProviderAccount, start: datetime, end: datetime) -> Iterable[AiUsage]:
        params = {
            **_window(start, end),
            "group_by": ["model", "project_id", "api_key_id", "user_id"],
        }
        rows: list[AiUsage] = []
        at = self._clock()
        for bucket in self._api(account).pages(COMPLETIONS, params):
            begins, ends = _bucket(bucket, account)
            for result in _results(bucket, account):
                rows.append(_usage(account, begins, ends, result, at, self._tenant_id))
        return tuple(rows)

    # -- mapping -----------------------------------------------------------

    def _cost(
        self, account: ProviderAccount, begins: datetime, ends: datetime, result: dict[str, Any]
    ) -> CostRecord:
        amount = result.get("amount") or {}
        value = _decimal(amount.get("value"), account)
        currency = str(amount.get("currency") or "").upper() or None
        line_item = result.get("line_item")
        line = str(line_item) if line_item else None
        model, token_type = _line(line)
        project = result.get("project_id") or None
        period = date(begins.year, begins.month, 1)
        return CostRecord(
            tenant_id=self._tenant_id,
            ingest_run_id=self._run_id,
            source_fingerprint=source_fingerprint(
                billing_account_id=account.organization_id,
                sub_account_id=project,
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
            sub_account_id=project,
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
            x_ai_model=model,
            x_ai_token_type=token_type,
        )


def scope_of(account: ProviderAccount) -> str:
    """How a failure for one organization is recorded and reported."""
    return f"{account.provider}:{account.organization_id}"


def _line(line: str | None) -> tuple[str | None, str | None]:
    """A line item's model and token type: `gpt-4o, input` is gpt-4o's input tokens."""
    if not line or "," not in line:
        return None, None
    model, _, kind = line.rpartition(",")
    model = model.strip()
    if not model:
        return None, None
    return model, TOKEN_KINDS.get(kind.strip().lower())


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
            detail="a completions usage result named no model, though the report groups by it",
        )
    cached = _count(result.get("input_cached_tokens"), account)
    every_input = _count(result.get("input_tokens"), account)
    return AiUsage(
        tenant_id=tenant_id,
        provider=SOURCE,
        account_id=account.organization_id,
        usage_date=begins.date(),
        model=str(model),
        workspace=str(result.get("project_id") or ""),
        api_key_id=str(result.get("api_key_id") or ""),
        caller=str(result.get("user_id") or ""),
        # OpenAI counts cached tokens inside input_tokens; the uncached input is the rest.
        input_tokens=max(every_input - cached, 0),
        cache_read_tokens=cached,
        output_tokens=_count(result.get("output_tokens"), account),
        requests=_count(result.get("num_model_requests"), account),
        as_of=ends,
        collected_at=max(at, ends),
    )


def _window(start: datetime, end: datetime) -> dict[str, Any]:
    return {
        "start_time": int(start.timestamp()),
        "end_time": int(end.timestamp()),
        "bucket_width": "1d",
        "limit": PAGE_DAYS,
    }


def _bucket(bucket: Any, account: ProviderAccount) -> tuple[datetime, datetime]:
    try:
        return (
            datetime.fromtimestamp(int(bucket["start_time"]), tz=UTC),
            datetime.fromtimestamp(int(bucket["end_time"]), tz=UTC),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise SchemaDrift(
            scope_key=scope_of(account),
            collector=COLLECTOR,
            detail="a report bucket had no readable start and end time",
        ) from error


def _results(bucket: Any, account: ProviderAccount) -> list[dict[str, Any]]:
    results = bucket.get("results") if isinstance(bucket, dict) else None
    if not isinstance(results, list):
        raise SchemaDrift(
            scope_key=scope_of(account), collector=COLLECTOR, detail="a bucket had no results list"
        )
    return [result for result in results if isinstance(result, dict)]


def _decimal(raw: Any, account: ProviderAccount) -> Decimal:
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError) as error:
        raise SchemaDrift(
            scope_key=scope_of(account),
            collector=COLLECTOR,
            detail=f"a cost result's amount {raw!r} is not a number",
        ) from error


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
